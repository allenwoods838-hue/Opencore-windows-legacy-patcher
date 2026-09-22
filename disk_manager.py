"""
OWLP - Hardened Defensive Disk & APFS Safety Engine
Includes multi-stage APFS container pre-flight audits, local snapshot
thinning, battery/power checks, and POSIX error diagnostics.
"""

import subprocess
import plistlib
import re
import hashlib
import shutil
from typing import List, Dict, Any, Optional, Tuple


class USBDisk:
    def __init__(self, raw_info: Dict[str, Any]):
        self.device_id: str = raw_info.get("DeviceIdentifier", "")
        self.device_node: str = raw_info.get("DeviceNode", f"/dev/{self.device_id}")
        self.media_name: str = raw_info.get("MediaName", "Generic USB Drive")
        self.size_bytes: int = raw_info.get("TotalSize", 0)
        self.is_internal: bool = raw_info.get("Internal", True)
        self.bus_protocol: str = raw_info.get("BusProtocol", "")
        self.is_removable: bool = raw_info.get("RemovableMedia", False) or raw_info.get("Ejectable", False)
        self.mount_point: Optional[str] = raw_info.get("MountPoint")
        self.warning_flags: List[str] = []

        self.is_large_storage: bool = self.size_bytes > 128 * (10**9)
        if self.is_large_storage:
            self.warning_flags.append("Drive is > 128 GB (Verify this is not your personal backup!)")

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 2)

    @property
    def identity_fingerprint(self) -> str:
        data = f"{self.device_node}_{self.media_name}_{self.size_bytes}_{self.bus_protocol}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def __repr__(self) -> str:
        large_tag = " [⚠️ LARGE DRIVE]" if self.is_large_storage else ""
        return f"USBDisk({self.device_node}, '{self.media_name}', {self.size_gb} GB{large_tag})"


class APFSSafetyEngine:
    """Specialized safety inspector for APFS containers and system health."""

    @staticmethod
    def _run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    @classmethod
    def check_power_safety(cls) -> Tuple[bool, str]:
        """Ensures Mac is either on AC power or has > 50% battery."""
        code, stdout, _ = cls._run_cmd(["pmset", "-g", "batt"])
        if code != 0:
            return True, "Power check bypassed (desktop Mac)."

        is_ac = "AC Power" in stdout
        percent_match = re.search(r"(\d+)%", stdout)
        battery_pct = int(percent_match.group(1)) if percent_match else 100

        if not is_ac and battery_pct < 50:
            return False, f"Mac is on battery power ({battery_pct}%). Connect charger to prevent corruption mid-resize."

        return True, "Power level safe."

    @classmethod
    def check_filevault_state(cls) -> Tuple[bool, str]:
        """Checks if FileVault is currently encrypting or decrypting."""
        code, stdout, _ = cls._run_cmd(["fdesetup", "status"])
        if code != 0:
            return True, "FileVault check bypassed."

        if "in progress" in stdout.lower():
            return False, f"FileVault is actively encrypting/decrypting ({stdout}). Wait for it to finish."

        return True, "FileVault state idle."

    @classmethod
    def check_local_snapshots(cls) -> List[str]:
        """Lists local Time Machine snapshots pinning APFS container blocks."""
        code, stdout, _ = cls._run_cmd(["tmutil", "listlocalsnapshots", "/"])
        if code != 0 or not stdout:
            return []

        # Snapshots follow format: com.apple.TimeMachine.2026-09-21-xxxxxx
        snapshots = [line.strip() for line in stdout.splitlines() if "com.apple." in line]
        return snapshots

    @classmethod
    def thin_snapshots(cls, target_bytes: int) -> bool:
        """Purges old local snapshots to release pinned blocks at container edge."""
        print(f"[*] Thinning APFS local snapshots to release pinned blocks...")
        code, _, _ = cls._run_cmd(["tmutil", "thinlocalsnapshots", "/", str(target_bytes), "4"])
        return code == 0


class DiskEngine:
    def __init__(self):
        self.safety = APFSSafetyEngine()

    def _run_cmd(self, cmd: List[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def get_disk_info(self, disk_ref: str) -> Optional[Dict[str, Any]]:
        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", disk_ref])
        if code != 0 or not stdout:
            return None
        try:
            return plistlib.loads(stdout.encode("utf-8"))
        except Exception:
            return None

    # -------------------------------------------------------------
    # DEFENSIVE USB SCANNER
    # -------------------------------------------------------------
    def _is_disk_safe_target(self, disk_id: str) -> Tuple[bool, str]:
        info = self.get_disk_info(disk_id)
        if not info:
            return False, "Could not query disk metadata."

        if info.get("Internal", True):
            return False, "Internal system drive."

        if info.get("VirtualOrPhysical", "").lower() != "physical":
            return False, "Virtual disk or disk image (DMG)."

        bus = info.get("BusProtocol", "")
        if bus != "USB" and not (bus == "Thunderbolt" and info.get("Ejectable", False)):
            return False, f"Unsupported bus protocol ({bus}). Only external USB allowed."

        if not info.get("Writable", True):
            return False, "Disk is read-only or hardware write-protected."

        total_size = info.get("TotalSize", 0)
        if total_size < 7.5 * (1024 ** 3):
            return False, f"Disk too small ({round(total_size / (1024**3), 2)} GB)."

        # Deep partition scan
        code, stdout, _ = self._run_cmd(["diskutil", "list", "-plist", disk_id])
        if code == 0 and stdout:
            try:
                plist_data = plistlib.loads(stdout.encode("utf-8"))
                for disk_entry in plist_data.get("AllDisksAndPartitions", []):
                    for part in disk_entry.get("Partitions", []):
                        p_id = part.get("DeviceIdentifier")
                        if not p_id:
                            continue
                        p_info = self.get_disk_info(p_id)
                        if not p_info:
                            continue

                        mount = p_info.get("MountPoint")
                        if mount in ["/", "/System/Volumes/Data", "/private/var", "/Users"]:
                            return False, f"Contains active system mount point ({mount})."

                        if p_info.get("TimeMachineBackup", False) or "time machine" in p_info.get("VolumeName", "").lower():
                            return False, "Contains an Apple Time Machine backup volume."

                        apfs_roles = p_info.get("APFSVolumeRole", [])
                        critical_roles = ["System", "Data", "Recovery", "Preboot", "Boot"]
                        if any(role in critical_roles for role in apfs_roles):
                            return False, f"Contains critical macOS APFS volume ({', '.join(apfs_roles)})."
            except Exception:
                pass

        return True, "Safe"

    def list_external_usb_drives(self) -> List[USBDisk]:
        code, stdout, _ = self._run_cmd(["diskutil", "list", "-plist"])
        if code != 0 or not stdout:
            return []

        try:
            data = plistlib.loads(stdout.encode("utf-8"))
        except Exception:
            return []

        all_disks = data.get("WholeDisks", [])
        verified_drives: List[USBDisk] = []

        for disk_id in all_disks:
            is_safe, _ = self._is_disk_safe_target(disk_id)
            if not is_safe:
                continue
            info = self.get_disk_info(disk_id)
            if info:
                verified_drives.append(USBDisk(info))

        return verified_drives

    def verify_fingerprint_before_erase(self, disk_node: str, expected_fingerprint: str) -> bool:
        disk_id = disk_node.replace("/dev/", "").strip()
        info = self.get_disk_info(disk_id)
        if not info:
            return False
        current_disk = USBDisk(info)
        return current_disk.identity_fingerprint == expected_fingerprint

    def format_usb_for_installer(self, disk_node: str, volume_label: str = "WININSTALL", expected_fingerprint: Optional[str] = None) -> bool:
        disk_id = disk_node.replace("/dev/", "").strip()
        is_safe, reason = self._is_disk_safe_target(disk_id)
        if not is_safe:
            print(f"[!] CRITICAL SAFETY ABORT: {disk_node} is not a safe target ({reason})")
            return False

        if expected_fingerprint and not self.verify_fingerprint_before_erase(disk_node, expected_fingerprint):
            print(f"[!] CRITICAL ABORT: Hardware identity changed on {disk_node}!")
            return False

        self._run_cmd(["diskutil", "unmountDisk", disk_node])
        cmd = ["diskutil", "eraseDisk", "FAT32", volume_label, "GPT", disk_node]
        code, _, stderr = self._run_cmd(cmd)
        return code == 0

    def find_partition_mount(self, volume_label: str = "WININSTALL") -> Optional[str]:
        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", volume_label])
        if code == 0 and stdout:
            try:
                info = plistlib.loads(stdout.encode("utf-8"))
                return info.get("MountPoint")
            except Exception:
                pass
        return f"/Volumes/{volume_label}"

    # -------------------------------------------------------------
    # REDESIGNED APFS SAFETY & PARTITIONING PIPELINE
    # -------------------------------------------------------------
    def get_internal_apfs_info(self) -> Optional[Dict[str, Any]]:
        """
        Deep pre-flight assessment of internal APFS storage with safety gating.
        """
        root_info = self.get_disk_info("/")
        if not root_info:
            return None

        container_ref = root_info.get("APFSContainerReference")
        if not container_ref:
            return None

        container_info = self.get_disk_info(container_ref)
        if not container_info:
            return None

        # Disqualify multi-store containers (Fusion Drive safeguard)
        physical_stores = container_info.get("APFSPhysicalStores", [])
        is_fusion = len(physical_stores) > 1

        # Check existing Windows/BOOTCAMP volumes
        code, stdout, _ = self._run_cmd(["diskutil", "list"])
        has_bootcamp = any(name in stdout for name in ["BOOTCAMP", "Windows", "Microsoft Basic Data"])

        # Query container boundary limits
        code, stdout, _ = self._run_cmd(["diskutil", "apfs", "resizeContainer", container_ref, "limits"])
        if code != 0:
            return None

        min_match = re.search(r"Minimum container size:\s+([0-9]+)\s+B", stdout)
        cur_match = re.search(r"Current container size:\s+([0-9]+)\s+B", stdout)

        if not min_match or not cur_match:
            return None

        min_bytes = int(min_match.group(1))
        cur_bytes = int(cur_match.group(1))

        cur_gb = round(cur_bytes / (10**9), 1)
        min_gb = round(min_bytes / (10**9), 1)

        # Dynamic Safety Buffer: Require at least 25 GB OR 15% of container size (whichever is larger)
        dynamic_buffer_gb = max(25.0, round(cur_gb * 0.15, 1))
        allocatable_gb = max(0, int(cur_gb - min_gb - dynamic_buffer_gb))

        # Check Power & FileVault
        power_safe, power_msg = self.safety.check_power_safety()
        fv_safe, fv_msg = self.safety.check_filevault_state()
        snapshots = self.safety.check_local_snapshots()

        blocking_reasons = []
        if is_fusion:
            blocking_reasons.append("APFS Fusion Drives cannot be resized safely.")
        if not power_safe:
            blocking_reasons.append(power_msg)
        if not fv_safe:
            blocking_reasons.append(fv_msg)
        if has_bootcamp:
            blocking_reasons.append("A Windows/BOOTCAMP partition already exists.")
        if allocatable_gb < 32:
            blocking_reasons.append(f"Insufficient free space (Need 32+ GB, available: {allocatable_gb} GB after safe buffer).")

        return {
            "container_id": container_ref,
            "current_gb": cur_gb,
            "min_gb": min_gb,
            "safe_buffer_gb": dynamic_buffer_gb,
            "allocatable_gb": allocatable_gb,
            "has_bootcamp": has_bootcamp,
            "is_fusion": is_fusion,
            "snapshots": snapshots,
            "blocking_reasons": blocking_reasons,
            "is_safe_to_partition": len(blocking_reasons) == 0
        }

    def create_bootcamp_partition(self, windows_size_gb: int, label: str = "BOOTCAMP") -> Tuple[bool, str]:
        """
        Executes safe container shrinking with automated snapshot management
        and POSIX error translation.
        """
        audit = self.get_internal_apfs_info()
        if not audit:
            return False, "Could not query APFS storage topology."

        if not audit["is_safe_to_partition"]:
            reasons = "\n• ".join(audit["blocking_reasons"])
            return False, f"Safety check rejected partitioning:\n• {reasons}"

        if windows_size_gb > audit["allocatable_gb"]:
            return False, f"Requested {windows_size_gb} GB exceeds maximum safe limit ({audit['allocatable_gb']} GB)."

        if windows_size_gb < 32:
            return False, "Windows 10/11 requires at least 32 GB of disk space."

        # If local snapshots are present, thin them before resizing
        if audit["snapshots"]:
            print(f"[*] Found {len(audit['snapshots'])} local snapshots. Purging to unlock boundary blocks...")
            target_free_bytes = int((windows_size_gb + audit["safe_buffer_gb"]) * (10**9))
            self.safety.thin_snapshots(target_free_bytes)

        # Calculate new macOS APFS container size
        new_container_size = int(audit["current_gb"] - windows_size_gb)
        container_id = audit["container_id"]

        cmd = [
            "diskutil", "apfs", "resizeContainer",
            container_id,
            f"{new_container_size}g",
            "FAT32",
            label,
            "0b"
        ]

        code, stdout, stderr = self._run_cmd(cmd)
        if code != 0:
            output = stderr or stdout
            # Diagnose common APFS error codes
            if "-69531" in output or "not enough free space" in output.lower():
                diagnosis = (
                    "APFS Error -69531: Pinned blocks detected at container boundary.\n"
                    "Fix: Open Terminal and run: 'tmutil thinlocalsnapshots / 99999999999 4' and restart your Mac."
                )
            elif "-69706" in output or "verify or repair failed" in output.lower():
                diagnosis = "APFS Error -69706: Filesystem corruption. Run First Aid in Disk Utility."
            elif "-69674" in output:
                diagnosis = "APFS Error -69674: Permission denied. Run app with 'sudo'."
            else:
                diagnosis = f"Resize failed ({output})"

            return False, diagnosis

        return True, f"Successfully allocated {windows_size_gb} GB for '{label}'!"