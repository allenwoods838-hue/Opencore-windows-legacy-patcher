#!/usr/bin/env python3
"""
OWLP - OpenCore Windows Legacy Patcher
Master Unified Application Entry Point (GUI & CLI Dual Architecture)
"""

import os
import sys
import time
import shutil
import argparse

# Pre-flight environment: auto-locate MacPorts Tcl/Tk paths before any UI imports
if os.path.exists("/opt/local/lib/tcl8.6"):
    os.environ["TCL_LIBRARY"] = "/opt/local/lib/tcl8.6"
if os.path.exists("/opt/local/lib/tk8.6"):
    os.environ["TK_LIBRARY"] = "/opt/local/lib/tk8.6"

from hardware import MacHardwareProfile
from mac_database import get_all_models
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
    if os.geteuid() != 0:
        print(f"{ANSI.YELLOW}[!] Notice: Running without sudo. If disk operations fail, restart with 'sudo python3 main.py'.{ANSI.RESET}\n")


def prompt_iso_path() -> str:
    while True:
        raw_path = input(f"\n{ANSI.BOLD}Drag and drop your Windows 10/11 ISO file here:{ANSI.RESET} ").strip().strip("'\"")
        expanded = os.path.abspath(os.path.expanduser(raw_path))
        if os.path.isfile(expanded) and expanded.lower().endswith(".iso"):
            return expanded
        print(f"{ANSI.RED}[!] Invalid file. Please provide a valid .iso file path.{ANSI.RESET}")


def select_usb_drive(engine: DiskEngine) -> USBDisk:
    print(f"\n{ANSI.BOLD}[*] Scanning for safe external USB flash drives (Defensive Mode)...{ANSI.RESET}")
    drives = engine.list_external_usb_drives()

    if not drives:
        print(f"{ANSI.RED}[!] No eligible safe USB drives found (>= 8GB).{ANSI.RESET}")
        print("    Plug in an external USB flash drive and press Enter to re-scan.")
        input()
        return select_usb_drive(engine)

    print(f"\n{ANSI.GREEN}Verified Safe USB Drive(s):{ANSI.RESET}")
    for idx, d in enumerate(drives):
        tag = f" {ANSI.YELLOW}[⚠️ LARGE DRIVE > 128GB]{ANSI.RESET}" if d.is_large_storage else ""
        print(f"  [{idx + 1}] {d.device_node} - {d.media_name} ({d.size_gb} GB){tag}")

    while True:
        choice = input(f"\nSelect target drive number (1-{len(drives)}) or 'q' to quit: ").strip()
        if choice.lower() == 'q':
            print("Aborted by user.")
            sys.exit(0)
        try:
            sel = int(choice) - 1
            if 0 <= sel < len(drives):
                selected_drive = drives[sel]
                if selected_drive.is_large_storage:
                    print(f"\n{ANSI.YELLOW}{ANSI.BOLD}⚠️ CAUTION: {selected_drive.device_node} is larger than 128 GB!{ANSI.RESET}")
                    print("Please verify this is NOT your personal backup or media drive.")

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
    host_profile = MacHardwareProfile()
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 1/6] Hardware Profile & Target Selection ---{ANSI.RESET}")

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

    disable_dgpu = False
    if any(x in profile.model_id for x in ["MacBookPro8,2", "MacBookPro9,1"]):
        print(f"\n{ANSI.YELLOW}[Optional Radeongate Fix]{ANSI.RESET}")
        opt = input("Does this Mac have a failing AMD graphics card? Disable it to force Intel HD graphics? [y/N]: ").strip().lower()
        disable_dgpu = (opt == "y")

    return profile, disable_dgpu


def setup_internal_apfs(disk_engine: DiskEngine):
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 2/6] Internal Drive Auto-Partitioning (Optional) ---{ANSI.RESET}")
    info = disk_engine.get_internal_apfs_info()
    if not info or not info.get("is_safe_to_partition", False):
        print("[*] Internal APFS container cannot be partitioned safely at this time. Skipping.")
        return

    print(f"Internal APFS Container: {info['container_id']} (Total: {info['current_gb']} GB)")
    print(f"Maximum safe space to allocate: Up to {ANSI.BOLD}{info['allocatable_gb']} GB{ANSI.RESET} (Buffer: {info['safe_buffer_gb']} GB)")

    opt = input("\nWould you like OWLP to partition your internal SSD for Windows right now? [y/N]: ").strip().lower()
    if opt == "y":
        size_input = input("Enter size in GB for BOOTCAMP [64]: ").strip() or "64"
        try:
            size_gb = int(size_input)
            print(f"[*] Resizing internal container to create {size_gb} GB BOOTCAMP partition...")
            success, msg = disk_engine.create_bootcamp_partition(size_gb)
            if success:
                print(f"{ANSI.GREEN}[+] {msg}{ANSI.RESET}")
            else:
                print(f"{ANSI.RED}[!] Partitioning failed: {msg}{ANSI.RESET}")
        except ValueError:
            print("[!] Invalid number. Skipping partitioning.")


def run_cli_wizard():
    print_banner()
    check_privileges()

    # 1. Hardware Profile & Spoofing
    profile, disable_dgpu = setup_target_hardware()

    # 2. Internal APFS Auto-Partitioning
    disk_engine = DiskEngine()
    setup_internal_apfs(disk_engine)

    # 3. Target Media & ISO Selection
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 3/6] Target Media & Windows Source ---{ANSI.RESET}")
    iso_path = prompt_iso_path()
    target_usb = select_usb_drive(disk_engine)

    # Dynamic Patch Configuration (No Hard-Coding)
    filename_lower = os.path.basename(iso_path).lower()
    is_win11_guess = "11" in filename_lower or "win11" in filename_lower

    print(f"\n{ANSI.BOLD}Windows Installation Options:{ANSI.RESET}")
    if is_win11_guess:
        print(f"[*] Detected {ANSI.CYAN}Windows 11{ANSI.RESET} media by filename.")
        default_bp = "y"
    else:
        print(f"[*] Detected {ANSI.GREEN}Windows 10{ANSI.RESET} media by filename (Clean vanilla setup).")
        default_bp = "n"

    bp_choice = input(f"Apply Windows 11 TPM 2.0 / CPU / Secure Boot bypass? [y/N] (Default: {default_bp.upper()}): ").strip().lower()
    apply_win11_bypass = (bp_choice == "y") if bp_choice else is_win11_guess

    drv_choice = input("Auto-launch Apple Boot Camp installer on first login (Zero-Touch)? [Y/n]: ").strip().lower()
    auto_drivers = (drv_choice != "n")

    print(f"[+] Configuration: Win11 Bypass={apply_win11_bypass}, Auto-Drivers={auto_drivers}")

    # 4. Format USB & Deploy OpenCore with Strict Abort
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 4/6] Formatting USB & Deploying OpenCore ---{ANSI.RESET}")
    format_success = disk_engine.format_usb_for_installer(
        target_usb.device_node,
        volume_label="WININSTALL",
        expected_fingerprint=target_usb.identity_fingerprint
    )
    if not format_success:
        print(f"{ANSI.RED}[!] Defensive safety abort: USB formatting halted.{ANSI.RESET}")
        sys.exit(1)

    time.sleep(2)

    oc_engine = OpenCoreEngine(target_usb.device_node, profile, disable_dead_dgpu=disable_dgpu)
    if not oc_engine.deploy_opencore():
        print(f"\n{ANSI.RED}{ANSI.BOLD}[!] CRITICAL ERROR: OpenCore deployment or ocvalidate failed. Aborting.{ANSI.RESET}\n")
        sys.exit(1)

    print(f"{ANSI.GREEN}[+] OpenCore verified and successfully deployed!{ANSI.RESET}")

    # 5. Extract ISO & Apply Dynamic Unattend Settings
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 5/6] Extracting Windows ISO & Processing Media ---{ANSI.RESET}")
    wininstall_mount = disk_engine.find_partition_mount("WININSTALL") or "/Volumes/WININSTALL"

    iso_manager = WindowsISOManager(
        iso_path,
        wininstall_mount,
        apply_win11_bypass=apply_win11_bypass,
        auto_launch_drivers=auto_drivers
    )
    if not iso_manager.process_and_copy():
        print(f"{ANSI.RED}[!] Failed to write Windows files to USB. Aborting.{ANSI.RESET}")
        sys.exit(1)

    # 6. Verified Boot Camp Driver Staging
    print(f"\n{ANSI.CYAN}{ANSI.BOLD}--- [Step 6/6] Fetching Apple Boot Camp Drivers ---{ANSI.RESET}")
    driver_engine = DriverEngine(profile.model_id)
    pkg_info = driver_engine.find_driver_package()

    if pkg_info:
        print(f"[*] Staging drivers deterministically for {profile.model_id}...")
        driver_success = driver_engine.download_and_extract(pkg_info, wininstall_mount)
        if not driver_success:
            print(f"{ANSI.RED}[!] Driver staging or post-staging verification failed.{ANSI.RESET}")
        else:
            print(f"{ANSI.GREEN}[+] Boot Camp driver staging complete and verified on USB!{ANSI.RESET}")
    else:
        print(f"{ANSI.YELLOW}[!] No direct Boot Camp ESD package found in Apple catalogs.{ANSI.RESET}")

    # Final Instructions
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
   - In the partition selection screen, select your {ANSI.CYAN}BOOTCAMP{ANSI.RESET} partition.
   - Click {ANSI.CYAN}Format{ANSI.RESET}, click OK, and click {ANSI.CYAN}Next{ANSI.RESET}.

3. {ANSI.BOLD}Driver Finalization:{ANSI.RESET}
   - If auto-drivers were enabled, the {ANSI.CYAN}Apple Boot Camp installer pops up automatically{ANSI.RESET} at desktop!
   - Click {ANSI.CYAN}Next -> Install -> Restart{ANSI.RESET} to complete setup.
""")


def try_launch_gui() -> bool:
    try:
        from gui import OWLPApp
        app = OWLPApp()
        app.mainloop()
        return True
    except ImportError as e:
        print(f"{ANSI.YELLOW}[!] GUI dependency missing ({e}). Falling back to CLI mode...{ANSI.RESET}\n")
        return False
    except Exception as e:
        print(f"{ANSI.YELLOW}[!] Window server error ({e}). Falling back to CLI mode...{ANSI.RESET}\n")
        return False


def main():
    parser = argparse.ArgumentParser(description="OpenCore Windows Legacy Patcher (OWLP)")
    parser.add_argument("--cli", "-c", action="store_true", help="Force Terminal / CLI wizard mode")
    parser.add_argument("--gui", "-g", action="store_true", help="Force Graphical User Interface mode")

    args, _ = parser.parse_known_args()

    if args.cli:
        run_cli_wizard()
        return

    if args.gui:
        if not try_launch_gui():
            sys.exit(1)
        return

    # Default: Try GUI first; fall back to CLI if headless or missing dependencies
    if not try_launch_gui():
        run_cli_wizard()


if __name__ == "__main__":
    main()