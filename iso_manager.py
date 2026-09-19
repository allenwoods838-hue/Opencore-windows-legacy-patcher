import os
import sys
import shutil
import plistlib
import subprocess
import time
from typing import Optional, Tuple


# Unattended answer file to bypass Windows 11 restrictions in WinPE
AUTOUNATTEND_XML = """<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassTPMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>2</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassSecureBootCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>3</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassRAMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>4</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassStorageCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>5</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassCPUCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
        </component>
    </settings>
</unattend>
"""

FAT32_LIMIT_BYTES = 4 * 1024 * 1024 * 1024 - (100 * 1024 * 1024)  # ~3.9 GB threshold


class WindowsISOManager:
    def __init__(self, iso_path: str, target_volume: str):
        self.iso_path = os.path.abspath(os.path.expanduser(iso_path))
        self.target_volume = os.path.abspath(target_volume)
        self.mount_point: Optional[str] = None

    def _run_cmd(self, cmd: list[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def check_wimlib(self) -> bool:
        """Verifies if wimlib-imagex is installed on the host Mac."""
        return shutil.which("wimlib-imagex") is not None

    def install_wimlib_via_brew(self) -> bool:
        """Attempts to install wimlib via Homebrew if missing."""
        brew_bin = shutil.which("brew")
        if not brew_bin:
            # Common Homebrew installation locations
            for path in ["/usr/local/bin/brew", "/opt/homebrew/bin/brew"]:
                if os.path.exists(path):
                    brew_bin = path
                    break

        if not brew_bin:
            return False

        print("[*] Homebrew detected. Installing 'wimlib' to handle WIM splitting...")
        code, _, _ = self._run_cmd([brew_bin, "install", "wimlib"])
        return code == 0

    def mount_iso(self) -> Optional[str]:
        """Mounts the Windows ISO via hdiutil and parses the mount path."""
        print(f"[*] Attaching Windows ISO: {os.path.basename(self.iso_path)}...")
        cmd = ["hdiutil", "attach", self.iso_path, "-plist", "-nobrowse", "-readonly"]
        code, stdout, stderr = self._run_cmd(cmd)
        
        if code != 0 or not stdout:
            print(f"[!] Failed to attach ISO: {stderr}")
            return None

        try:
            plist_data = plistlib.loads(stdout.encode("utf-8"))
            for entity in plist_data.get("system-entities", []):
                if "mount-point" in entity:
                    self.mount_point = entity["mount-point"]
                    print(f"[+] ISO mounted at: {self.mount_point}")
                    return self.mount_point
        except Exception as e:
            print(f"[!] Failed to parse hdiutil plist: {e}")

        return None

    def unmount_iso(self):
        """Detaches the mounted ISO."""
        if self.mount_point:
            print(f"[*] Detaching ISO mount: {self.mount_point}...")
            self._run_cmd(["hdiutil", "detach", self.mount_point, "-force"])
            self.mount_point = None

    def _copy_file_with_progress(self, src: str, dst: str):
        """Copies a large file with a progress bar."""
        total_size = os.path.getsize(src)
        copied = 0
        start_time = time.time()
        chunk_size = 1024 * 1024 * 4  # 4 MB chunks

        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while True:
                buf = fsrc.read(chunk_size)
                if not buf:
                    break
                fdst.write(buf)
                copied += len(buf)
                
                pct = (copied / total_size) * 100
                elapsed = time.time() - start_time
                speed = (copied / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                mb_done = copied / (1024 * 1024)
                mb_tot = total_size / (1024 * 1024)

                sys.stdout.write(f"\r  Copying: [{pct:5.1f}%] {mb_done:.0f}/{mb_tot:.0f} MB @ {speed:.1f} MB/s")
                sys.stdout.flush()
        print()

    def process_and_copy(self) -> bool:
        """Copies all ISO files, splits install.wim if necessary, and injects bypasses."""
        if not os.path.exists(self.target_volume):
            print(f"[!] Target volume '{self.target_volume}' does not exist.")
            return False

        mount = self.mount_iso()
        if not mount:
            return False

        try:
            sources_dir = os.path.join(mount, "sources")
            wim_path = os.path.join(sources_dir, "install.wim")
            esd_path = os.path.join(sources_dir, "install.esd")

            main_image = None
            if os.path.exists(wim_path):
                main_image = wim_path
            elif os.path.exists(esd_path):
                main_image = esd_path

            if not main_image:
                print("[!] Error: Neither install.wim nor install.esd found in ISO/sources!")
                return False

            image_name = os.path.basename(main_image)
            image_size = os.path.getsize(main_image)
            needs_split = image_size > FAT32_LIMIT_BYTES

            print(f"[*] Main Windows image detected: {image_name} ({image_size / (1024**3):.2f} GB)")

            if needs_split:
                print("[*] Image exceeds FAT32 4GB limit. SWM splitting is required.")
                if not self.check_wimlib():
                    print("[!] 'wimlib-imagex' is required to split install.wim for FAT32.")
                    installed = self.install_wimlib_via_brew()
                    if not installed:
                        print("[!] Please install wimlib using: 'brew install wimlib' and run again.")
                        return False

            # 1. Copy all items from ISO root except the main image file
            print("\n[*] Copying installer boot files and directories to USB...")
            for item in os.listdir(mount):
                src_item = os.path.join(mount, item)
                dst_item = os.path.join(self.target_volume, item)

                if item.lower() == "sources":
                    os.makedirs(dst_item, exist_ok=True)
                    # Copy all files inside sources EXCEPT install.wim/install.esd
                    for s_item in os.listdir(src_item):
                        if s_item.lower() in ["install.wim", "install.esd"]:
                            continue
                        s_src = os.path.join(src_item, s_item)
                        s_dst = os.path.join(dst_item, s_item)
                        if os.path.isdir(s_src):
                            if not os.path.exists(s_dst):
                                shutil.copytree(s_src, s_dst)
                        else:
                            shutil.copy2(s_src, s_dst)
                else:
                    if os.path.isdir(src_item):
                        if not os.path.exists(dst_item):
                            shutil.copytree(src_item, dst_item)
                    else:
                        shutil.copy2(src_item, dst_item)

            print("[+] Base installer files copied.")

            # 2. Handle the large install image
            dst_sources = os.path.join(self.target_volume, "sources")
            if needs_split:
                print("[*] Splitting install.wim into 3800MB .swm chunks directly to USB...")
                dst_swm = os.path.join(dst_sources, "install.swm")
                split_cmd = ["wimlib-imagex", "split", main_image, dst_swm, "3800"]
                code, _, stderr = self._run_cmd(split_cmd)
                if code != 0:
                    print(f"[!] Error splitting WIM file: {stderr}")
                    return False
                print("[+] install.wim split and written as install.swm successfully!")
            else:
                print(f"[*] Image fits within FAT32 limit. Copying {image_name} directly...")
                self._copy_file_with_progress(main_image, os.path.join(dst_sources, image_name))

            # 3. Inject autounattend.xml bypass
            print("[*] Injecting Windows 11 TPM/SecureBoot/CPU bypass (autounattend.xml)...")
            unattend_dst = os.path.join(self.target_volume, "autounattend.xml")
            with open(unattend_dst, "w", encoding="utf-8") as f:
                f.write(AUTOUNATTEND_XML)
            print("[+] autounattend.xml written to USB root.")

            print("\n[+] Windows installation media preparation complete!")
            return True

        except Exception as e:
            print(f"[!] Error during ISO processing: {e}")
            return False
        finally:
            self.unmount_iso()


if __name__ == "__main__":
    print("=" * 55)
    print("   STAGE 4: WINDOWS ISO PROCESSOR & BYPASS ENGINE")
    print("=" * 55)

    iso_input = input("Enter path to Windows ISO file: ").strip().strip("'\"")
    if not os.path.isfile(iso_input):
        print(f"[!] File not found: {iso_input}")
        sys.exit(1)

    vol_input = input("Enter target USB volume path [/Volumes/WININSTALL]: ").strip() or "/Volumes/WININSTALL"

    manager = WindowsISOManager(iso_input, vol_input)
    success = manager.process_and_copy()

    if success:
        print("\nStage 4 completed successfully!")