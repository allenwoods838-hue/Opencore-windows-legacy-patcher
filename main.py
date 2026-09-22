#!/usr/bin/env python3
"""
OWLP - OpenCore Windows Legacy Patcher
Master CLI Orchestrator & Deployment Engine
"""

import os
import sys
import time
import shutil

# Import Stage 1-7 engines
from hardware import MacHardwareProfile
from mac_database import get_all_models, lookup_model
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
    """Warns if not running with root/administrator privileges."""
    if os.geteuid() != 0:
        print(f"{ANSI.YELLOW}[!] Notice: Running without sudo. If disk operations fail, restart with 'sudo python3 main.py'.{ANSI.RESET}\n")


def prompt_iso_path() -> str:
    """Prompts the user to drag and drop or enter their Windows ISO path."""
    while True:
        raw_path = input(f"\n{ANSI.BOLD}Drag and drop your Windows 10/11 ISO file here:{ANSI.RESET} ").strip().strip("'\"")
        expanded = os.path.abspath(os.path.expanduser(raw_path))
        if os.path.isfile(expanded) and expanded.lower().endswith(".iso"):
            return expanded
        print(f"{ANSI.RED}[!] Invalid file. Please provide a valid .iso file path.{ANSI.RESET}")


def select_usb_drive(engine: DiskEngine) -> USBDisk:
    """Scans and prompts the user to select an external USB flash drive."""
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


def setup_target_hardware() -> tuple[MacHardwareProfile, bool]:
    """Handles Target Model Spoofing and dead dGPU toggle."""
    host_profile = MacHardwareProfile()
    
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 1/6] Hardware Profile & Target Selection ---{ANSI.RESET}")
    
    # Handle Apple Silicon host
    if host_profile.is_apple_silicon:
        print(f"{ANSI.YELLOW}[*] Apple Silicon Mac detected. You must select an Intel target model.{ANSI.RESET}")
        use_spoof = True
    else:
        print(f"Detected Host Mac: {ANSI.BOLD}{host_profile.friendly_name} [{host_profile.model_id}]{ANSI.RESET}")
        print("  [1] Build for this Mac (Host)")
        print("  [2] Build for another Mac (Target Model Spoofing)")
        choice = input("Select option (1 or 2) [1]: ").strip() or "1"
        use_spoof = (choice == "2")

    profile = host_profile
    if use_spoof:
        models = get_all_models()
        print(f"\n{ANSI.BOLD}Available Intel Mac Target Models:{ANSI.RESET}")
        for idx, (m_id, name) in enumerate(models):
            print(f"  [{idx + 1:2d}] {m_id:<16} - {name}")

        while True:
            selection = input(f"\nEnter model number (1-{len(models)}): ").strip()
            try:
                s_idx = int(selection) - 1
                if 0 <= s_idx < len(models):
                    target_id = models[s_idx][0]
                    profile = MacHardwareProfile(target_model=target_id)
                    print(f"[+] Spoofing target: {ANSI.GREEN}{profile.friendly_name} [{profile.model_id}]{ANSI.RESET}")
                    break
            except ValueError:
                pass
            print(f"{ANSI.RED}[!] Invalid selection.{ANSI.RESET}")

    # Display hardware audit
    eval_report = profile.evaluate_windows_support()
    print(f"\nHardware Configuration:")
    print(f"  Model ID    : {profile.model_id}")
    print(f"  Board ID    : {profile.board_id}")
    print(f"  T2 Security : {'Yes' if profile.has_t2 else 'No'}")
    print(f"  GPU(s)      : {', '.join(profile.gpus) if profile.gpus else 'Integrated'}")

    quirks = eval_report.get("quirks_needed", [])
    if quirks:
        print(f"{ANSI.YELLOW}  Quirks Flagged:{ANSI.RESET}")
        for q in quirks:
            print(f"    • {q}")
    else:
        print(f"  Quirks Flagged: Standard UEFI")

    # Option to disable dead AMD GPU on 2011/2012 15" MacBook Pros
    disable_dgpu = False
    if any(x in profile.model_id for x in ["MacBookPro8,2", "MacBookPro9,1"]):
        print(f"\n{ANSI.YELLOW}[Optional Radeongate Fix]{ANSI.RESET}")
        opt = input("Does this Mac have a failing AMD graphics card? Disable it to force Intel HD graphics? [y/N]: ").strip().lower()
        disable_dgpu = (opt == "y")
        if disable_dgpu:
            print(f"{ANSI.GREEN}[+] Dead AMD dGPU will be powered down via SSDT-dGPU-Off.{ANSI.RESET}")

    return profile, disable_dgpu


def setup_internal_apfs(disk_engine: DiskEngine):
    """Optional interactive internal APFS auto-partitioning."""
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 2/6] Internal Drive Auto-Partitioning (Optional) ---{ANSI.RESET}")
    info = disk_engine.get_internal_apfs_info()
    
    if not info:
        print("[*] No internal APFS container detected or unsupported drive scheme. Skipping.")
        return

    if info["has_bootcamp"]:
        print(f"{ANSI.GREEN}[*] A 'BOOTCAMP' partition already exists on your internal SSD. Skipping.{ANSI.RESET}")
        return

    print(f"Internal APFS Container: {info['container_id']} (Total: {info['current_gb']} GB)")
    print(f"Maximum safe space to allocate: Up to {ANSI.BOLD}{info['allocatable_gb']} GB{ANSI.RESET}")

    opt = input("\nWould you like OWLP to partition your internal SSD for Windows right now? [y/N]: ").strip().lower()
    if opt == "y":
        while True:
            size_input = input(f"Enter size in GB for BOOTCAMP [64]: ").strip() or "64"
            try:
                size_gb = int(size_input)
                print(f"[*] Resizing internal container to create {size_gb} GB BOOTCAMP partition...")
                success, msg = disk_engine.create_bootcamp_partition(size_gb)
                if success:
                    print(f"{ANSI.GREEN}[+] {msg}{ANSI.RESET}")
                else:
                    print(f"{ANSI.RED}[!] Partitioning failed: {msg}{ANSI.RESET}")
                break
            except ValueError:
                print("[!] Please enter a valid whole number.")


def main():
    print_banner()
    check_privileges()

    # 1. Hardware Profile & Spoofing
    profile, disable_dgpu = setup_target_hardware()

    # 2. Internal APFS Auto-Partitioning
    disk_engine = DiskEngine()
    setup_internal_apfs(disk_engine)

    # 3. Target Media & ISO
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 3/6] Target Media & Windows Source ---{ANSI.RESET}")
    iso_path = prompt_iso_path()
    target_usb = select_usb_drive(disk_engine)

    # 4. Partition USB & Deploy OpenCore with Strict Abort
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 4/6] Formatting USB & Deploying OpenCore ---{ANSI.RESET}")
    format_success = disk_engine.format_usb_for_installer(target_usb.device_node, volume_label="WININSTALL")
    if not format_success:
        print(f"{ANSI.RED}[!] USB formatting failed. Aborting.{ANSI.RESET}")
        sys.exit(1)

    time.sleep(2)

    oc_engine = OpenCoreEngine(
        target_usb.device_node,
        profile,
        disable_dead_dgpu=disable_dgpu
    )
    oc_success = oc_engine.deploy_opencore()

    # STRICT ENFORCEMENT: Never continue after an OpenCore deployment failure!
    if not oc_success:
        print(f"\n{ANSI.RED}{ANSI.BOLD}======================================================{ANSI.RESET}")
        print(f"{ANSI.RED}{ANSI.BOLD} [!] CRITICAL ERROR: OPENCORE DEPLOYMENT FAILED      {ANSI.RESET}")
        print(f"{ANSI.RED}{ANSI.BOLD}======================================================{ANSI.RESET}")
        print(f"{ANSI.RED}OpenCore could not be deployed or failed schema validation (ocvalidate).{ANSI.RESET}")
        print(f"{ANSI.RED}Aborting immediately to prevent creating an unbootable drive.{ANSI.RESET}\n")
        sys.exit(1)

    print(f"{ANSI.GREEN}[+] OpenCore verified and successfully deployed!{ANSI.RESET}")

    # 5. Extract ISO, Split WIM, & Inject Zero-Touch Setup
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 5/6] Extracting Windows ISO & Injecting Zero-Touch Bypass ---{ANSI.RESET}")
    wininstall_mount = disk_engine.find_partition_mount("WININSTALL") or "/Volumes/WININSTALL"

    iso_manager = WindowsISOManager(iso_path, wininstall_mount)
    iso_success = iso_manager.process_and_copy()
    if not iso_success:
        print(f"{ANSI.RED}[!] Failed to write Windows files to USB. Aborting.{ANSI.RESET}")
        sys.exit(1)

    # 6. Boot Camp Driver Staging
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 6/6] Fetching Apple Boot Camp Drivers ---{ANSI.RESET}")
    driver_engine = DriverEngine(profile.model_id)
    pkg_info = driver_engine.find_driver_package()

    if pkg_info:
        print(f"[*] Downloading and staging drivers for {profile.model_id}...")
        driver_success = driver_engine.download_and_extract(pkg_info["package_url"], wininstall_mount)
        if driver_success:
            print(f"{ANSI.GREEN}[+] $WinPEDriver$ and BootCamp drivers staged successfully!{ANSI.RESET}")
        else:
            print(f"{ANSI.YELLOW}[!] Driver download encountered warnings. Drivers can be installed manually later.{ANSI.RESET}")
    else:
        print(f"{ANSI.YELLOW}[!] No direct Boot Camp ESD package found in Apple catalogs.{ANSI.RESET}")

    # -------------------------------------------------------------
    # COMPLETE: Instructions for Booting
    # -------------------------------------------------------------
    print(f"\n{ANSI.GREEN}{ANSI.BOLD}======================================================{ANSI.RESET}")
    print(f"{ANSI.GREEN}{ANSI.BOLD}   CONGRATULATIONS! INSTALLER DRIVE IS READY!        {ANSI.RESET}")
    print(f"{ANSI.GREEN}{ANSI.BOLD}======================================================{ANSI.RESET}")
    print(f"""
{ANSI.BOLD}HOW TO INSTALL WINDOWS ON YOUR MAC:{ANSI.RESET}

1. {ANSI.BOLD}Booting the Installer:{ANSI.RESET}
   - Shut down your Mac (keep the USB plugged in).
   - Turn it on and immediately hold down the {ANSI.CYAN}Option (Alt){ANSI.RESET} key.
   - Select the yellow {ANSI.CYAN}EFI Boot{ANSI.RESET} icon (this launches OpenCore).
   - In the OpenCore menu, select {ANSI.CYAN}Windows{ANSI.RESET}.

2. {ANSI.BOLD}During Windows Setup:{ANSI.RESET}
   - Windows 11 TPM 2.0 / Secure Boot / CPU checks are {ANSI.GREEN}automatically bypassed{ANSI.RESET}.
   - In the partition selection screen, select your {ANSI.CYAN}BOOTCAMP{ANSI.RESET} partition.
   - Click {ANSI.CYAN}Format{ANSI.RESET}, click OK, and click {ANSI.CYAN}Next{ANSI.RESET}.

3. {ANSI.BOLD}Zero-Touch Driver Finalization:{ANSI.RESET}
   - When setting up your account, click {ANSI.CYAN}"I don't have internet"{ANSI.RESET} to create a local user.
   - The moment you reach the Windows desktop, the {ANSI.CYAN}Apple Boot Camp installer will pop up automatically{ANSI.RESET}!
   - Click {ANSI.CYAN}Next -> Install -> Restart{ANSI.RESET} to finish setup.
""")


if __name__ == "__main__":
    main()