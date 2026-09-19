


#!/usr/bin/env python3
"""
OWLP - OpenCore Windows Legacy Patcher
Master Orchestrator & Deployment Engine
"""

import os
import sys
import time
import shutil

if "--cli" not in sys.argv:
    try:
        from gui import OWLPMainWindow, QApplication
        app = QApplication(sys.argv)
        win = OWLPMainWindow()
        win.show()
        sys.exit(app.exec())
    except ImportError:
        pass  # Fallback to CLI if PyQt6 is not installed



# Import modules from Stages 1 through 5
from hardware import MacHardwareProfile
from disk_manager import DiskEngine, USBDisk
from driver_manager import DriverEngine
from iso_manager import WindowsISOManager
from opencore_engine import OpenCoreEngine


class ANSI:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_banner():
    banner = f"""{ANSI.CYAN}{ANSI.BOLD}
   ____  _       __ _      ____ 
  / __ \\| |     / /| |    / __ \\
 / / / /| | /| / / | |   / /_/ /
/ /_/ / | |/ |/ /  | |___/ ____/ 
\\____/  |__/|__/   |_____/_/     
{ANSI.RESET}{ANSI.BOLD}OpenCore Windows Legacy Patcher (OWLP){ANSI.RESET}
Unified Windows 10/11 Deployment Suite for Intel Macs
"""
    print(banner)


def check_privileges():
    """Warns if not running with elevated privileges for disk operations."""
    if os.geteuid() != 0:
        print(f"{ANSI.YELLOW}[!] Notice: Running without sudo. If disk operations fail, restart with 'sudo python3 main.py'.{ANSI.RESET}\n")


def prompt_iso_path() -> str:
    while True:
        raw_path = input(f"{ANSI.BOLD}Drag and drop your Windows 10/11 ISO file here:{ANSI.RESET} ").strip().strip("'\"")
        expanded = os.path.abspath(os.path.expanduser(raw_path))
        if os.path.isfile(expanded) and expanded.lower().endswith(".iso"):
            return expanded
        print(f"{ANSI.RED}[!] Invalid file. Please specify a valid .iso file path.{ANSI.RESET}")


def select_usb_drive(engine: DiskEngine) -> USBDisk:
    print(f"\n{ANSI.BOLD}[*] Scanning for connected external USB flash drives (>= 8GB)...{ANSI.RESET}")
    drives = engine.list_external_usb_drives()
    
    if not drives:
        print(f"{ANSI.RED}[!] No eligible USB drives found.{ANSI.RESET}")
        print("    Plug in an external USB flash drive (8 GB or larger) and press Enter to re-scan.")
        input()
        return select_usb_drive(engine)

    print(f"\n{ANSI.GREEN}Detected USB Drive(s):{ANSI.RESET}")
    for idx, d in enumerate(drives):
        print(f"  [{idx + 1}] {d.device_node} - {d.media_name} ({d.size_gb} GB)")

    while True:
        choice = input(f"\nSelect target drive number (1-{len(drives)}) or 'q' to quit: ").strip()
        if choice.lower() == 'q':
            print("Aborted by user.")
            sys.exit(0)
        try:
            sel = int(choice) - 1
            if 0 <= sel < len(drives):
                selected_drive = drives[sel]
                print(f"\n{ANSI.RED}{ANSI.BOLD}!!! WARNING: ALL DATA ON {selected_drive.device_node} ({selected_drive.media_name}) WILL BE ERASED !!!{ANSI.RESET}")
                confirm = input(f"Type '{ANSI.BOLD}YES{ANSI.RESET}' to confirm erase: ").strip()
                if confirm == "YES":
                    return selected_drive
                else:
                    print("Operation cancelled. Please select again.")
        except ValueError:
            pass
        print(f"{ANSI.RED}[!] Invalid selection.{ANSI.RESET}")


def main():
    print_banner()
    check_privileges()

    # -------------------------------------------------------------
    # STEP 1: Hardware Profiler & Audit
    # -------------------------------------------------------------
    print(f"{ANSI.CYAN}{ANSI.BOLD}--- [Step 1/5] System Assessment ---{ANSI.RESET}")
    profile = MacHardwareProfile()
    eval_report = profile.evaluate_windows_support()

    if not eval_report.get("supported"):
        print(f"{ANSI.RED}[!] Incompatible Machine: {eval_report.get('reason')}{ANSI.RESET}")
        sys.exit(1)

    print(f"  Model ID      : {profile.model_id}")
    print(f"  Board ID      : {profile.board_id}")
    print(f"  CPU           : {profile.cpu_name}")
    print(f"  GPU(s)        : {', '.join(profile.gpus) if profile.gpus else 'Integrated'}")
    print(f"  T2 Security   : {'Yes' if profile.has_t2 else 'No'}")
    
    quirks = eval_report.get("quirks_needed", [])
    if quirks:
        print(f"{ANSI.YELLOW}  Quirks Flagged:{ANSI.RESET}")
        for q in quirks:
            print(f"    - {q}")
    else:
        print(f"  Quirks Flagged: None (Standard UEFI installation)")

    # -------------------------------------------------------------
    # STEP 2: Input Selection (ISO & USB Drive)
    # -------------------------------------------------------------
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 2/5] Target Media & Windows Source ---{ANSI.RESET}")
    iso_path = prompt_iso_path()
    disk_engine = DiskEngine()
    target_usb = select_usb_drive(disk_engine)

    # -------------------------------------------------------------
    # STEP 3: USB Partitioning & OpenCore Injection
    # -------------------------------------------------------------
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 3/5] Initializing USB & Deploying OpenCore ---{ANSI.RESET}")
    format_success = disk_engine.format_usb_for_installer(target_usb.device_node, volume_label="WININSTALL")
    if not format_success:
        print(f"{ANSI.RED}[!] USB formatting failed. Aborting.{ANSI.RESET}")
        sys.exit(1)

    # Allow macOS time to auto-mount volumes
    time.sleep(2)

    # Deploy OpenCore to the USB's EFI partition (/dev/diskXs1)
    oc_engine = OpenCoreEngine(target_usb.device_node, profile)
    oc_success = oc_engine.deploy_opencore()
    if not oc_success:
        print(f"{ANSI.YELLOW}[!] Warning: OpenCore deployment had issues. Continuing with standard media creation...{ANSI.RESET}")

    # -------------------------------------------------------------
    # STEP 4: Windows ISO Extraction & Win11 Bypass Injection
    # -------------------------------------------------------------
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 4/5] Extracting Windows & Applying Bypasses ---{ANSI.RESET}")
    wininstall_mount = disk_engine.find_partition_mount("WININSTALL")
    if not wininstall_mount or not os.path.exists(wininstall_mount):
        wininstall_mount = "/Volumes/WININSTALL"

    iso_manager = WindowsISOManager(iso_path, wininstall_mount)
    iso_success = iso_manager.process_and_copy()
    if not iso_success:
        print(f"{ANSI.RED}[!] Failed to write Windows files to USB. Aborting.{ANSI.RESET}")
        sys.exit(1)

    # -------------------------------------------------------------
    # STEP 5: Boot Camp Driver Staging
    # -------------------------------------------------------------
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 5/5] Fetching Apple Boot Camp Drivers ---{ANSI.RESET}")
    driver_engine = DriverEngine(profile.model_id)
    pkg_info = driver_engine.find_driver_package()

    if pkg_info:
        print(f"[*] Downloading and staging Boot Camp drivers for {profile.model_id}...")
        driver_success = driver_engine.download_and_extract(pkg_info["package_url"], wininstall_mount)
        if driver_success:
            print(f"{ANSI.GREEN}[+] $WinPEDriver$ and BootCamp driver packages successfully staged!{ANSI.RESET}")
        else:
            print(f"{ANSI.YELLOW}[!] Driver download failed. You can run driver_manager.py manually later.{ANSI.RESET}")
    else:
        print(f"{ANSI.YELLOW}[!] No direct Boot Camp ESD matched in Apple catalogs. Continuing...{ANSI.RESET}")

    # -------------------------------------------------------------
    # COMPLETE: Instructions for Booting
    # -------------------------------------------------------------
    print(f"\n{ANSI.GREEN}{ANSI.BOLD}======================================================{ANSI.RESET}")
    print(f"{ANSI.GREEN}{ANSI.BOLD}   CONGRATULATIONS! INSTALLER DRIVE IS READY!        {ANSI.RESET}")
    print(f"{ANSI.GREEN}{ANSI.BOLD}======================================================{ANSI.RESET}")
    print(f"""
{ANSI.BOLD}NEXT STEPS TO INSTALL WINDOWS ON YOUR MAC:{ANSI.RESET}

1. {ANSI.BOLD}Partition Your Mac's Internal SSD for Windows:{ANSI.RESET}
   - Open macOS {ANSI.CYAN}Disk Utility{ANSI.RESET}.
   - Click '{ANSI.CYAN}Partition{ANSI.RESET}', click '+', and choose a size for Windows.
   - Format it as {ANSI.CYAN}MS-DOS (FAT){ANSI.RESET} and name it {ANSI.CYAN}BOOTCAMP{ANSI.RESET}.

2. {ANSI.BOLD}Booting the Installer:{ANSI.RESET}
   - Restart your Mac and immediately hold down the {ANSI.CYAN}Option (Alt){ANSI.RESET} key.
   - Select the yellow {ANSI.CYAN}EFI Boot{ANSI.RESET} icon (this is OpenCore).
   - In the OpenCore menu, select {ANSI.CYAN}Windows{ANSI.RESET}.

3. {ANSI.BOLD}During Windows Setup:{ANSI.RESET}
   - All Windows 11 TPM 2.0 / Secure Boot / CPU checks will be automatically bypassed.
   - In the partition selection screen, choose your {ANSI.CYAN}BOOTCAMP{ANSI.RESET} partition,
     click {ANSI.CYAN}Format{ANSI.RESET}, and then click {ANSI.CYAN}Next{ANSI.RESET}.

4. {ANSI.BOLD}Post-Installation (Driver Finalization):{ANSI.RESET}
   - Once Windows boots to the desktop, open File Explorer.
   - Open your USB drive (usually {ANSI.CYAN}D:\\{ANSI.RESET} or {ANSI.CYAN}E:\\{ANSI.RESET}).
   - Open the {ANSI.CYAN}BootCamp{ANSI.RESET} folder and double-click {ANSI.CYAN}Setup.exe{ANSI.RESET}.
   - Restart when prompted — audio, Wi-Fi, trackpad, and graphics are all set!
""")


if __name__ == "__main__":
    main()