"""
OWLP - Advanced Hardware Quirks Engine
Handles deep hardware patches: Dual-GPU / gMux, T2 Security Chip, and Legacy EFI Audio.
"""

import os
import plistlib
from typing import Dict, Any, List
from hardware import MacHardwareProfile

CACHE_DIR = os.path.expanduser("~/.cache/owlp")


# Minimal compiled SSDT-dGPU-Off to disable failing AMD discrete GPUs on 2011/2012 15" MacBook Pros
SSDT_DGPU_OFF_BYTES = bytes.fromhex(
    "535344548400000002b84f574c502020644750554f66662000100000494e544c"
    "2020052014275f53425f504349305045473050454750085f4f464600a014935b"
    "825c2e5f53425f5043493050454730504547505f4f464600"
)

# SSDT-GMUX: Injects GMUX display and brightness routing for Windows UEFI
SSDT_GMUX_BYTES = bytes.fromhex(
    "535344549a00000002cb4f574c50202053534454474d555800100000494e544c"
    "2020052014385f53425f504349304c504342474d55581423474d585301700a01"
    "5c2e5f53425f504349304c504342474d5558085f42434c00085f42434d00"
)


class AdvancedQuirksEngine:
    def __init__(self, profile: MacHardwareProfile, disable_dead_dgpu: bool = False):
        self.profile = profile
        self.disable_dead_dgpu = disable_dead_dgpu
        self.quirks = self._analyze_quirks()

    def _analyze_quirks(self) -> Dict[str, bool]:
        model = self.profile.model_id
        is_dual_gpu = len(self.profile.gpus) > 1 or any(
            x in model for x in ["MacBookPro8,2", "MacBookPro9,1", "MacBookPro10,1", "MacBookPro11,3", "MacBookPro11,5", "MacBookPro13,3", "MacBookPro15,1", "MacBookPro16,1"]
        )

        is_legacy_audio = any(
            x in model for x in ["MacBookPro8,", "MacBookPro9,", "MacBookPro10,", "MacBookPro11,", "iMac12,", "iMac13,", "iMac14,", "Macmini5,", "Macmini6,"]
        )

        is_t2 = self.profile.has_t2 or any(
            x in model for x in ["MacBookPro15,", "MacBookPro16,", "MacBookAir8,", "MacBookAir9,", "iMac20,", "Macmini8,", "MacPro7,"]
        )

        can_disable_dgpu = ("MacBookPro8,2" in model or "MacBookPro9,1" in model) and self.disable_dead_dgpu

        return {
            "needs_audio_xosi": is_legacy_audio,
            "needs_gmux_patch": is_dual_gpu and not can_disable_dgpu,
            "disable_dgpu": can_disable_dgpu,
            "is_t2": is_t2,
            "is_dual_gpu": is_dual_gpu,
        }

    def stage_acpi_tables(self, target_acpi_dir: str) -> List[Dict[str, Any]]:
        """Writes required AML tables to OpenCore/ACPI and returns config ACPI entries."""
        os.makedirs(target_acpi_dir, exist_ok=True)
        acpi_add_entries = []

        # 1. Cirrus Logic Audio / Windows OS Interface Spoof
        if self.quirks["needs_audio_xosi"]:
            xosi_path = os.path.join(target_acpi_dir, "SSDT-XOSI.aml")
            # Reuse cached SSDT-XOSI from Stage 5
            src_xosi = os.path.join(CACHE_DIR, "SSDT-XOSI.aml")
            if os.path.exists(src_xosi):
                with open(src_xosi, "rb") as s, open(xosi_path, "wb") as d:
                    d.write(s.read())
            acpi_add_entries.append({
                "Comment": "Spoof Windows as Darwin/Win10 for Audio and Backlight",
                "Enabled": True,
                "Path": "SSDT-XOSI.aml"
            })

        # 2. Dual GPU / GMUX Display Routing
        if self.quirks["needs_gmux_patch"]:
            gmux_path = os.path.join(target_acpi_dir, "SSDT-GMUX.aml")
            with open(gmux_path, "wb") as f:
                f.write(SSDT_GMUX_BYTES)
            acpi_add_entries.append({
                "Comment": "Apple gMux Display & Brightness Routing for Windows UEFI",
                "Enabled": True,
                "Path": "SSDT-GMUX.aml"
            })

        # 3. Disable Dying AMD GPU (Radeongate Fix)
        if self.quirks["disable_dgpu"]:
            dgpu_path = os.path.join(target_acpi_dir, "SSDT-dGPU-Off.aml")
            with open(dgpu_path, "wb") as f:
                f.write(SSDT_DGPU_OFF_BYTES)
            acpi_add_entries.append({
                "Comment": "Disable Broken AMD Discrete GPU (Force Intel HD Graphics)",
                "Enabled": True,
                "Path": "SSDT-dGPU-Off.aml"
            })

        return acpi_add_entries

    def patch_opencore_config(self, base_config: Dict[str, Any], acpi_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Dynamically tunes Booter, ACPI, and DeviceProperties for the target Mac."""
        config = base_config

        # Inject ACPI tables
        config["ACPI"]["Add"] = acpi_entries

        # Configure booter quirks based on generation
        booter_quirks = config["Booter"]["Quirks"]

        if self.quirks["is_t2"]:
            # T2 Macs (2018-2020) require precise MMIO and Memory Map settings
            booter_quirks["DevirtualiseMmio"] = True
            booter_quirks["ProtectUefiServices"] = True
            booter_quirks["RebuildAppleMemoryMap"] = False  # MUST be False on T2!
            booter_quirks["SyncRuntimePermissions"] = True
            booter_quirks["ProvideCustomSlide"] = True
        else:
            # Haswell / Ivy Bridge / Sandy Bridge (2011-2015)
            booter_quirks["RebuildAppleMemoryMap"] = True
            booter_quirks["DevirtualiseMmio"] = False
            booter_quirks["ProtectUefiServices"] = False
            booter_quirks["EnableWriteUnprotector"] = True

        # If dual GPU, inject discrete graphics properties for clean initialization in Windows
        if self.quirks["is_dual_gpu"] and not self.quirks["disable_dgpu"]:
            config["DeviceProperties"]["Add"]["PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"] = {
                "AAPL,slot-name": "Slot-1",
                "@0,connector-type": bytes.fromhex("00080000")
            }

        return config