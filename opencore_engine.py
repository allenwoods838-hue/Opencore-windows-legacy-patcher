import os
import sys
import json
import zipfile
import plistlib
import subprocess
import shutil
from typing import Optional, Dict, Any
from urllib.request import urlopen, Request

from hardware import MacHardwareProfile
from quirks_engine import AdvancedQuirksEngine

OPENCORE_API_URL = "https://api.github.com/repos/acidanthera/OpenCorePkg/releases/latest"
SSDT_XOSI_URL = "https://github.com/dortania/Getting-Started-With-ACPI/raw/master/extra-files/SSDT-XOSI.aml"
CACHE_DIR = os.path.expanduser("~/.cache/owlp")


class OpenCoreEngine:
    def __init__(self, target_disk_id: str, hardware_profile: Optional[MacHardwareProfile] = None, disable_dead_dgpu: bool = False):
        self.raw_disk_id = target_disk_id.replace("/dev/", "").strip()
        self.efi_partition_node = f"/dev/{self.raw_disk_id}s1"
        self.hw = hardware_profile or MacHardwareProfile()
        self.disable_dead_dgpu = disable_dead_dgpu
        self.efi_mount_point: Optional[str] = None
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _run_cmd(self, cmd: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def mount_efi_partition(self) -> Optional[str]:
        print(f"[*] Mounting USB EFI partition: {self.efi_partition_node}...")
        self._run_cmd(["diskutil", "mount", self.efi_partition_node])

        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", self.efi_partition_node])
        if code == 0 and stdout:
            try:
                info = plistlib.loads(stdout.encode("utf-8"))
                mount = info.get("MountPoint")
                if mount:
                    self.efi_mount_point = mount
                    return mount
            except Exception:
                pass
        return None

    def unmount_efi_partition(self):
        if self.efi_mount_point:
            self._run_cmd(["diskutil", "unmount", self.efi_partition_node])
            self.efi_mount_point = None

    def download_opencore_binaries(self) -> str:
        cached_zip = os.path.join(CACHE_DIR, "OpenCore-Latest.zip")
        if os.path.exists(cached_zip):
            return cached_zip

        req = Request(OPENCORE_API_URL, headers={"User-Agent": "OWLP-Bootloader/1.0"})
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        download_url = None
        for asset in data.get("assets", []):
            if asset.get("name", "").endswith("-RELEASE.zip"):
                download_url = asset.get("browser_download_url")
                break

        if not download_url:
            raise RuntimeError("Could not resolve OpenCore RELEASE zip asset URL.")

        req_dl = Request(download_url, headers={"User-Agent": "OWLP-Bootloader/1.0"})
        with urlopen(req_dl) as resp, open(cached_zip, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        return cached_zip

    def download_ssdt_xosi(self) -> str:
        target_path = os.path.join(CACHE_DIR, "SSDT-XOSI.aml")
        if os.path.exists(target_path):
            return target_path

        req = Request(SSDT_XOSI_URL, headers={"User-Agent": "OWLP-Bootloader/1.0"})
        with urlopen(req) as resp, open(target_path, "wb") as out_file:
            shutil.copyfileobj(resp, out_file)
        return target_path

    def deploy_opencore(self) -> bool:
        mount = self.mount_efi_partition()
        if not mount:
            return False

        try:
            zip_path = self.download_opencore_binaries()
            self.download_ssdt_xosi()

            # Target directory structure on USB EFI
            boot_dir = os.path.join(mount, "EFI", "BOOT")
            oc_dir = os.path.join(mount, "EFI", "OC")
            drivers_dir = os.path.join(oc_dir, "Drivers")
            acpi_dir = os.path.join(oc_dir, "ACPI")

            os.makedirs(boot_dir, exist_ok=True)
            os.makedirs(drivers_dir, exist_ok=True)
            os.makedirs(acpi_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                with z.open("X64/EFI/BOOT/BOOTx64.efi") as src, open(os.path.join(boot_dir, "BOOTx64.efi"), "wb") as dst:
                    shutil.copyfileobj(src, dst)
                with z.open("X64/EFI/OC/OpenCore.efi") as src, open(os.path.join(oc_dir, "OpenCore.efi"), "wb") as dst:
                    shutil.copyfileobj(src, dst)
                for drv in ["OpenRuntime.efi", "ResetNvramEntry.efi"]:
                    with z.open(f"X64/EFI/OC/Drivers/{drv}") as src, open(os.path.join(drivers_dir, drv), "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # --- ADVANCED QUIRKS INJECTION ---
            print(f"[*] Applying Advanced Hardware Quirks for {self.hw.model_id}...")
            quirks_mgr = AdvancedQuirksEngine(self.hw, disable_dead_dgpu=self.disable_dead_dgpu)
            acpi_entries = quirks_mgr.stage_acpi_tables(acpi_dir)

            base_config = self._get_base_config()
            final_config = quirks_mgr.patch_opencore_config(base_config, acpi_entries)

            config_path = os.path.join(oc_dir, "config.plist")
            with open(config_path, "wb") as f:
                plistlib.dump(final_config, f)

            print("[+] OpenCore bootloader & advanced hardware quirks staged successfully!")
            return True

        except Exception as e:
            print(f"[!] Error deploying OpenCore: {e}")
            return False
        finally:
            self.unmount_efi_partition()

    def _get_base_config(self) -> Dict[str, Any]:
        return {
            "ACPI": {
                "Add": [],
                "Delete": [],
                "Patch": [
                    {
                        "Base": "",
                        "BaseSkip": 0,
                        "Comment": "_OSI to XOSI rename",
                        "Count": 0,
                        "Enabled": True,
                        "Find": b"_OSI",
                        "Limit": 0,
                        "Mask": b"",
                        "OemTableId": b"",
                        "Replace": b"XOSI",
                        "ReplaceMask": b"",
                        "Skip": 0,
                        "TableLength": 0,
                        "TableSignature": b""
                    }
                ],
                "Quirks": {"FadtEnableReset": False, "NormalizeHeaders": False, "RebaseRegions": False, "ResetHwSig": False, "ResetLogoStatus": False}
            },
            "Booter": {
                "MmioWhitelist": [],
                "Patch": [],
                "Quirks": {
                    "AllowRelocationBlock": False,
                    "AvoidRuntimeDefrag": True,
                    "DevirtualiseMmio": False,
                    "DisableSingleUser": False,
                    "DisableVariableWrite": False,
                    "DiscardHibernateMap": False,
                    "EnableSafeModeSlide": True,
                    "EnableWriteUnprotector": True,
                    "ForceBooterSignature": False,
                    "ForceExitBootServices": False,
                    "ProtectMemoryRegions": False,
                    "ProtectSecureBoot": False,
                    "ProtectUefiServices": False,
                    "ProvideCustomSlide": True,
                    "ProvideMaxSlide": 0,
                    "RebuildAppleMemoryMap": True,
                    "ResizeAppleGpuBars": -1,
                    "SetupVirtualMap": True,
                    "SignalAppleOS": False,
                    "SyncRuntimePermissions": True
                }
            },
            "DeviceProperties": {"Add": {}, "Delete": {}},
            "Kernel": {"Add": [], "Block": [], "Emulate": {}, "Force": [], "Patch": [], "Quirks": {}, "Scheme": {}},
            "Misc": {
                "BlessOverride": [],
                "Boot": {"ConsoleAttributes": 0, "HibernateMode": "None", "HideAuxiliary": False, "LauncherOption": "Disabled", "LauncherPath": "Default", "PickerAttributes": 17, "PickerAudioAssist": False, "PickerMode": "Builtin", "PickerVariant": "Default", "PollAppleHotKeys": True, "ShowPicker": True, "TakeoffDelay": 0, "Timeout": 5},
                "Debug": {"AppleDebug": False, "ApplePanic": False, "DisableWatchDog": True, "DisplayDelay": 0, "DisplayLevel": 2147483650, "LogModules": "*", "Target": 3},
                "Security": {"AllowSetDefault": True, "ApECID": 0, "AuthRestart": False, "BlacklistAppleUpdate": True, "DmgLoading": "Signed", "EnablePassword": False, "ExposeSensitiveData": 6, "HaltLevel": 2147483648, "PasswordHash": b"", "PasswordSalt": b"", "ScanPolicy": 0, "SecureBootModel": "Disabled", "Vault": "Optional"},
                "Tools": []
            },
            "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": "-v"}}, "Delete": {}, "LegacyOverwrite": False, "WriteFlash": True},
            "PlatformInfo": {"Automatic": True, "CustomMemory": False, "Generic": {"AdviseFeatures": True, "MaxBIOSVersion": False, "ProcessorType": 0, "SpoofVendor": True, "SystemMemoryStatus": "Auto"}, "UpdateDataHub": True, "UpdateNVRAM": True, "UpdateSMBIOS": True, "UpdateSMBIOSMode": "Create"},
            "UEFI": {
                "APFS": {"EnableJumpstart": False, "GlobalConnect": False, "HideVerbose": False, "JumpstartHotPlug": False, "MinDate": 0, "MinVersion": 0},
                "AppleInput": {"AppleEvent": "Builtin", "CustomDelays": False, "KeyInitialDelay": 50, "KeySubsequentDelay": 5},
                "ConnectDrivers": True,
                "Drivers": [
                    {"Arguments": "", "Comment": "OpenRuntime", "Enabled": True, "LoadEarly": False, "Path": "OpenRuntime.efi"},
                    {"Arguments": "", "Comment": "ResetNVRAM", "Enabled": True, "LoadEarly": False, "Path": "ResetNvramEntry.efi"}
                ],
                "Input": {"KeyFiltering": False, "KeyForgetThreshold": 5, "KeySupport": True, "KeySupportMode": "Auto"},
                "Output": {"ClearScreenOnModeSwitch": False, "ConsoleFont": "", "ConsoleMode": "", "DirectGopCacheMode": "", "GopBurstMode": False, "GopPassThrough": "Disabled", "IgnoreTextInGraphics": False, "InitialMode": "Auto", "ProvideConsoleGop": True, "ReconnectGraphicsOnConnect": False, "ReconnectOnResChange": False, "ReplaceTabWithSpace": False, "Resolution": "Max", "SanitiseClearScreen": False, "TextRenderer": "BuiltinGraphics", "UIScale": 0, "UgaPassThrough": False},
                "ProtocolOverrides": {"AppleAudio": False, "AppleBootPolicy": False, "AppleDebugLog": False, "AppleEg2Info": False, "AppleFramebufferInfo": False, "AppleImageConversion": False, "AppleImg4Verification": False, "AppleKeyMap": False, "AppleRtcRam": False, "AppleSecureBoot": False, "AppleSmcIo": False, "AppleUserInterfaceTheme": False, "DataHub": False, "DeviceProperties": False, "FirmwareVolume": False, "HashServices": False, "OSInfo": False, "PciIo": False, "UnicodeCollation": False},
                "Quirks": {"ActivateHpetSupport": False, "DisableSecurityPolicy": False, "EnableVectorAcceleration": True, "EnableVmx": False, "ExitBootServicesDelay": 0, "ForceOcWriteFlash": False, "ForgeUefiSupport": False, "IgnoreInvalidFlexRatio": False, "ReleaseUsbOwnership": True, "ReloadOptionRoms": False, "RequestBootVarRouting": True, "ResizeGpuBars": -1, "TscSyncTimeout": 0, "UnblockFsConnect": False},
                "ReservedMemory": []
            }
        }
        return config

    def deploy_opencore(self) -> bool:
        """Extracts required OpenCore binaries and installs them onto the USB's EFI partition."""
        mount = self.mount_efi_partition()
        if not mount:
            return False

        try:
            zip_path = self.download_opencore_binaries()
            ssdt_xosi_path = self.download_ssdt_xosi()

            print("[*] Extracting OpenCore EFI files...")
            with zipfile.ZipFile(zip_path, "r") as z:
                # 1. Target Directory Paths on EFI
                boot_dir = os.path.join(mount, "EFI", "BOOT")
                oc_dir = os.path.join(mount, "EFI", "OC")
                drivers_dir = os.path.join(oc_dir, "Drivers")
                acpi_dir = os.path.join(oc_dir, "ACPI")

                os.makedirs(boot_dir, exist_ok=True)
                os.makedirs(drivers_dir, exist_ok=True)
                os.makedirs(acpi_dir, exist_ok=True)

                # 2. Extract BOOTx64.efi
                with z.open("X64/EFI/BOOT/BOOTx64.efi") as src, open(os.path.join(boot_dir, "BOOTx64.efi"), "wb") as dst:
                    shutil.copyfileobj(src, dst)

                # 3. Extract OpenCore.efi
                with z.open("X64/EFI/OC/OpenCore.efi") as src, open(os.path.join(oc_dir, "OpenCore.efi"), "wb") as dst:
                    shutil.copyfileobj(src, dst)

                # 4. Extract Drivers
                for drv in ["OpenRuntime.efi", "ResetNvramEntry.efi"]:
                    with z.open(f"X64/EFI/OC/Drivers/{drv}") as src, open(os.path.join(drivers_dir, drv), "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # 5. Copy SSDT-XOSI
            shutil.copy2(ssdt_xosi_path, os.path.join(acpi_dir, "SSDT-XOSI.aml"))

            # 6. Generate and save config.plist
            print("[*] Generating tailored OpenCore config.plist...")
            needs_audio_quirk = any("Audio" in q for q in self.hw.evaluate_windows_support().get("quirks_needed", []))
            config = self.generate_config_plist(needs_audio_patch=needs_audio_quirk)

            config_path = os.path.join(oc_dir, "config.plist")
            with open(config_path, "wb") as f:
                plistlib.dump(config, f)

            print("[+] OpenCore EFI bootloader successfully configured!")
            return True

        except Exception as e:
            print(f"[!] Error deploying OpenCore: {e}")
            return False
        finally:
            self.unmount_efi_partition()


if __name__ == "__main__":
    profile = MacHardwareProfile()
    print("=" * 55)
    print("   STAGE 5: BOOTLOADER & ACPI PATCHING ENGINE")
    print("=" * 55)
    print(f"Target Mac Model: {profile.model_id}")

    disk_input = input("Enter target USB identifier (e.g., 'disk2'): ").strip()
    if not disk_input:
        print("[!] Disk identifier cannot be empty.")
        sys.exit(1)

    engine = OpenCoreEngine(disk_input, profile)
    success = engine.deploy_opencore()

    if success:
        print("\n[+] Stage 5 completed successfully!")