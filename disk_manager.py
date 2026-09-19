import subprocess
import plistlib
import sys
import re
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

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 2)


class DiskEngine:
    def __init__(self):
        pass

    def _run_cmd(self, cmd: List[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def get_disk_info(self, disk_id: str) -> Optional[Dict[str, Any]]:
        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", disk_id])
        if code != 0 or not stdout:
            return None
        try:
            return plistlib.loads(stdout.encode("utf-8"))
        except Exception:
            return None

    def list_external_usb_drives(self) -> List[USBDisk]:
        code, stdout, _ = self._run_cmd(["diskutil", "list", "-plist"])
        if code != 0 or not stdout:
            return []

        try:
            data = plistlib.loads(stdout.encode("utf-8"))
        except Exception:
            return []

        all_disks = data.get("WholeDisks", [])
        eligible: List[USBDisk] = []

        for disk_id in all_disks:
            info = self.get_disk_info(disk_id)
            if not info:
                continue

            if info.get("Internal", True):
                continue

            bus = info.get("BusProtocol", "")
            if bus != "USB" and not info.get("Ejectable", False):
                continue

            if not info.get("Writable", True):
                continue

            if info.get("TotalSize", 0) < 7 * (1024 ** 3):
                continue

            eligible.append(USBDisk(info))

        return eligible

    def format_usb_for_installer(self, disk_node: str, volume_label: str = "WININSTALL") -> bool:
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
    # INTERNAL APFS AUTO-PARTITIONING ENGINE
    # -------------------------------------------------------------
    def get_internal_apfs_info(self) -> Optional[Dict[str, Any]]:
        """
        Inspects the running macOS internal drive to find the APFS Container
        and calculate the safe maximum size allocatable for Windows.
        """
        # Find root APFS volume
        root_info = self.get_disk_info("/")
        if not root_info:
            return None

        container_ref = root_info.get("APFSContainerReference")
        if not container_ref:
            return None

        # Check if BOOTCAMP partition already exists
        code, stdout, _ = self._run_cmd(["diskutil", "list"])
        has_bootcamp = "BOOTCAMP" in stdout

        # Query container resize limits
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

        # Leave a 10 GB breathing safety buffer for macOS
        allocatable_gb = max(0, int(cur_gb - min_gb - 10))

        return {
            "container_id": container_ref,
            "current_gb": cur_gb,
            "min_gb": min_gb,
            "allocatable_gb": allocatable_gb,
            "has_bootcamp": has_bootcamp
        }

    def create_bootcamp_partition(self, windows_size_gb: int, label: str = "BOOTCAMP") -> Tuple[bool, str]:
        """
        Shrinks internal APFS container and carves out a FAT32 BOOTCAMP partition.
        """
        info = self.get_internal_apfs_info()
        if not info:
            return False, "Could not detect internal APFS container."

        if info["has_bootcamp"]:
            return False, "A 'BOOTCAMP' partition already exists on your Mac."

        if windows_size_gb > info["allocatable_gb"]:
            return False, f"Requested {windows_size_gb} GB exceeds maximum safe limit ({info['allocatable_gb']} GB)."

        if windows_size_gb < 30:
            return False, "Windows requires at least 30 GB of disk space."

        # Calculate new container size (Current - Windows size)
        new_container_size = int(info["current_gb"] - windows_size_gb)
        container_id = info["container_id"]

        # diskutil apfs resizeContainer <ID> <size>g FAT32 BOOTCAMP 0b
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
            return False, f"Partitioning failed: {stderr or stdout}"

        return True, f"Successfully created {windows_size_gb} GB '{label}' partition!"