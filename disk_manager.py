import subprocess
import plistlib
import sys
from typing import List, Dict, Any, Optional

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
        self.partitions: list[str] = []

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / (1024 ** 3), 2)

    def __repr__(self) -> str:
        return f"USBDisk({self.device_id}, {self.media_name}, {self.size_gb} GB, Node: {self.device_node})"


class DiskEngine:
    def __init__(self):
        pass

    def _run_cmd(self, cmd: List[str]) -> tuple[int, str, str]:
        """Runs a system command and returns (returncode, stdout, stderr)."""
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def get_disk_info(self, disk_id: str) -> Optional[Dict[str, Any]]:
        """Queries diskutil for detailed plist metadata about a specific disk."""
        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", disk_id])
        if code != 0 or not stdout:
            return None
        try:
            return plistlib.loads(stdout.encode("utf-8"))
        except Exception:
            return None

    def list_external_usb_drives(self) -> List[USBDisk]:
        """
        Scans system for external physical USB storage devices suitable for an installer.
        Ignores all internal drives and read-only media.
        """
        code, stdout, _ = self._run_cmd(["diskutil", "list", "-plist"])
        if code != 0 or not stdout:
            print("[!] Error querying diskutil list.")
            return []

        try:
            data = plistlib.loads(stdout.encode("utf-8"))
        except Exception as e:
            print(f"[!] Failed to parse diskutil plist: {e}")
            return []

        all_disks = data.get("WholeDisks", [])
        eligible_drives: List[USBDisk] = []

        for disk_id in all_disks:
            info = self.get_disk_info(disk_id)
            if not info:
                continue

            # Strict Safety Checks:
            # 1. Must NOT be an internal drive
            if info.get("Internal", True):
                continue

            # 2. Must be on USB or an ejectable external bus
            bus = info.get("BusProtocol", "")
            if bus != "USB" and not info.get("Ejectable", False):
                continue

            # 3. Must be writable
            if not info.get("Writable", True):
                continue

            # 4. Filter out drives smaller than 7 GB (Windows ISO won't fit)
            size = info.get("TotalSize", 0)
            if size < 7 * (1024 ** 3):
                continue

            drive = USBDisk(info)
            eligible_drives.append(drive)

        return eligible_drives

    def unmount_disk(self, disk_node: str) -> bool:
        """Unmounts all volumes on the disk prior to partitioning."""
        code, _, stderr = self._run_cmd(["diskutil", "unmountDisk", disk_node])
        if code != 0:
            print(f"[!] Warning: Failed to unmount {disk_node}: {stderr}")
            return False
        return True

    def format_usb_for_installer(self, disk_node: str, volume_label: str = "WININSTALL") -> bool:
        """
        Formats disk to GPT + FAT32.
        Creates:
          - /dev/diskXs1 -> EFI (FAT32, 200MB)
          - /dev/diskXs2 -> WININSTALL (FAT32, remainder of disk)
        """
        print(f"[*] Preparing target disk: {disk_node}")
        self.unmount_disk(disk_node)

        print(f"[*] Formatting {disk_node} as GPT FAT32 ('{volume_label}')...")
        
        # 'diskutil eraseDisk FAT32 <LABEL> GPT <DISK>'
        # Requires sudo if permission is denied.
        cmd = ["diskutil", "eraseDisk", "FAT32", volume_label, "GPT", disk_node]
        code, stdout, stderr = self._run_cmd(cmd)

        if code != 0:
            print(f"[!] Partitioning failed: {stderr}")
            if "root" in stderr.lower() or "permission denied" in stderr.lower():
                print("[!] Tip: You may need to run this command with 'sudo'.")
            return False

        print(f"[+] Successfully initialized {disk_node} for Windows Installer!")
        return True

    def find_partition_mount(self, volume_label: str = "WININSTALL") -> Optional[str]:
        """Finds the mount point of our newly formatted volume (e.g., /Volumes/WININSTALL)."""
        code, stdout, _ = self._run_cmd(["diskutil", "info", "-plist", volume_label])
        if code == 0 and stdout:
            try:
                info = plistlib.loads(stdout.encode("utf-8"))
                return info.get("MountPoint")
            except Exception:
                pass
        return f"/Volumes/{volume_label}"


if __name__ == "__main__":
    engine = DiskEngine()
    print("=" * 55)
    print("   STAGE 2: USB STORAGE & PARTITION ENGINE")
    print("=" * 55)
    print("[*] Scanning for connected external USB drives (>= 8GB)...")
    
    usb_drives = engine.list_external_usb_drives()

    if not usb_drives:
        print("[!] No eligible external USB drives detected.")
        print("    Please plug in a USB flash drive (8GB or larger) and retry.")
        sys.exit(0)

    print("\nFound the following USB drive(s):")
    for idx, drive in enumerate(usb_drives):
        print(f"  [{idx + 1}] {drive.device_node} - {drive.media_name} ({drive.size_gb} GB)")

    print("\n[Safety Notice] Formatting will PERMANENTLY ERASE all data on the selected drive.")
    choice = input("\nEnter number of drive to format (or 'q' to quit): ").strip()

    if choice.lower() == 'q':
        print("Aborted.")
        sys.exit(0)

    try:
        selection_idx = int(choice) - 1
        if selection_idx < 0 or selection_idx >= len(usb_drives):
            print("Invalid selection.")
            sys.exit(1)
            
        target_drive = usb_drives[selection_idx]
        
        confirm = input(f"Are you ABSOLUTELY sure you want to erase '{target_drive.device_node}'? (type 'YES'): ")
        if confirm == "YES":
            success = engine.format_usb_for_installer(target_drive.device_node, volume_label="WININSTALL")
            if success:
                mount_point = engine.find_partition_mount("WININSTALL")
                print(f"[+] Mount Point verified at: {mount_point}")
        else:
            print("Action cancelled.")

    except ValueError:
        print("Invalid input.")