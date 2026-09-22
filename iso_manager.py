"""
OWLP - Dynamic Windows ISO Engine
Inspects Windows build versions and generates modular autounattend.xml
only when explicitly requested.
"""

import os
import sys
import shutil
import plistlib
import subprocess
import time
import re
from typing import Optional, Tuple, Dict, Any

FAT32_LIMIT_BYTES = 4 * 1024 * 1024 * 1024 - (100 * 1024 * 1024)  # ~3.9 GB threshold


class WindowsISOManager:
    def __init__(
        self,
        iso_path: str,
        target_volume: str,
        apply_win11_bypass: bool = False,
        auto_launch_drivers: bool = True
    ):
        self.iso_path = os.path.abspath(os.path.expanduser(iso_path))
        self.target_volume = os.path.abspath(target_volume)
        self.apply_win11_bypass = apply_win11_bypass
        self.auto_launch_drivers = auto_launch_drivers
        self.mount_point: Optional[str] = None

    def _run_cmd(self, cmd: list[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def check_wimlib(self) -> bool:
        return shutil.which("wimlib-imagex") is not None

    def mount_iso(self) -> Optional[str]:
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
                    return self.mount_point
        except Exception as e:
            print(f"[!] Failed to parse hdiutil plist: {e}")

        return None

    def unmount_iso(self):
        if self.mount_point:
            self._run_cmd(["hdiutil", "detach", self.mount_point, "-force"])
            self.mount_point = None

    def detect_windows_version(self, wim_path: str) -> Dict[str, Any]:
        """
        Uses wimlib-imagex to inspect the image metadata and extract the exact OS build.
        """
        if not self.check_wimlib():
            return {"version": "Unknown", "build": 0, "is_win11": True}

        code, stdout, _ = self._run_cmd(["wimlib-imagex", "info", wim_path, "1"])
        if code != 0 or not stdout:
            return {"version": "Unknown", "build": 0, "is_win11": True}

        build = 0
        build_match = re.search(r"Build:\s+(\d+)", stdout)
        if build_match:
            build = int(build_match.group(1))

        # Windows 11 starts at Build 22000
        is_win11 = build >= 22000
        ver_name = "Windows 11" if is_win11 else "Windows 10" if build >= 10240 else "Legacy Windows"

        return {
            "version": ver_name,
            "build": build,
            "is_win11": is_win11
        }

    def generate_unattend_xml(self) -> Optional[str]:
        """
        Dynamically constructs autounattend.xml based on active flags.
        Returns None if no bypasses or automations are selected (clean vanilla media).
        """
        if not self.apply_win11_bypass and not self.auto_launch_drivers:
            return None  # No answer file needed!

        xml_sections = []

        # 1. Windows PE Pass (TPM / CPU / Secure Boot Bypass)
        if self.apply_win11_bypass:
            xml_sections.append("""    <settings pass="windowsPE">
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
    </settings>""")

        # 2. Specialize Pass (Bypass Microsoft Account requirement on Win11)
        if self.apply_win11_bypass:
            xml_sections.append("""    <settings pass="specialize">
        <component name="Microsoft-Windows-Deployment" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <Path>reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\OOBE /v BypassNRO /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
        </component>
    </settings>""")

        # 3. oobeSystem Pass (Zero-Touch Driver Launcher)
        if self.auto_launch_drivers:
            xml_sections.append("""    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <FirstLogonCommands>
                <SynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <CommandLine>cmd.exe /c for %i in (C D E F G H I J K) do if exist %i:\\BootCamp\\setup.exe (start %i:\\BootCamp\\setup.exe &amp; exit)</CommandLine>
                    <Description>Auto-Launch Apple Boot Camp Installer</Description>
                </SynchronousCommand>
            </FirstLogonCommands>
        </component>
    </settings>""")

        inner_body = "\n".join(xml_sections)
        return f"""<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
{inner_body}
</unattend>
"""

    def process_and_copy(self) -> bool:
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

            main_image = wim_path if os.path.exists(wim_path) else esd_path if os.path.exists(esd_path) else None
            if not main_image:
                print("[!] Error: Neither install.wim nor install.esd found in ISO!")
                return False

            # Detect Windows Version
            os_info = self.detect_windows_version(main_image)
            print(f"[*] Detected Media: {os_info['version']} (Build {os_info['build']})")

            image_size = os.path.getsize(main_image)
            needs_split = image_size > FAT32_LIMIT_BYTES

            if needs_split and not self.check_wimlib():
                print("[!] 'wimlib-imagex' is required to split install.wim. Install via brew or MacPorts.")
                return False

            # 1. Copy ISO base files
            print("[*] Copying base installer files to USB...")
            for item in os.listdir(mount):
                src_item = os.path.join(mount, item)
                dst_item = os.path.join(self.target_volume, item)

                if item.lower() == "sources":
                    os.makedirs(dst_item, exist_ok=True)
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

            # 2. Write or split main image
            dst_sources = os.path.join(self.target_volume, "sources")
            if needs_split:
                print("[*] Splitting install.wim into 3800MB .swm chunks...")
                dst_swm = os.path.join(dst_sources, "install.swm")
                code, _, stderr = self._run_cmd(["wimlib-imagex", "split", main_image, dst_swm, "3800"])
                if code != 0:
                    print(f"[!] Split failed: {stderr}")
                    return False
            else:
                shutil.copy2(main_image, os.path.join(dst_sources, os.path.basename(main_image)))

            # 3. Dynamic autounattend.xml generation
            unattend_xml = self.generate_unattend_xml()
            unattend_dst = os.path.join(self.target_volume, "autounattend.xml")

            if unattend_xml:
                print(f"[*] Staging autounattend.xml (Win11 Bypass: {self.apply_win11_bypass}, Auto-Drivers: {self.auto_launch_drivers})...")
                with open(unattend_dst, "w", encoding="utf-8") as f:
                    f.write(unattend_xml)
            else:
                print("[*] No autounattend.xml requested. Media is 100% clean/vanilla Microsoft.")
                if os.path.exists(unattend_dst):
                    os.remove(unattend_dst)

            print("[+] Windows media preparation completed successfully!")
            return True

        finally:
            self.unmount_iso()