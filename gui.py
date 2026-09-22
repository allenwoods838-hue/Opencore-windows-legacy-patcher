#!/usr/bin/env python3
"""
OWLP - OpenCore Windows Legacy Patcher
Full Graphical User Interface (CustomTkinter Engine)
"""

import os
import sys
import time
import threading

# Auto-locate MacPorts Tcl/Tk libraries if present
if os.path.exists("/opt/local/lib/tcl8.6"):
    os.environ["TCL_LIBRARY"] = "/opt/local/lib/tcl8.6"
if os.path.exists("/opt/local/lib/tk8.6"):
    os.environ["TK_LIBRARY"] = "/opt/local/lib/tk8.6"

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Import Stage 1-7 engines
from hardware import MacHardwareProfile
from mac_database import get_all_models
from disk_manager import DiskEngine
from driver_manager import DriverEngine
from iso_manager import WindowsISOManager
from opencore_engine import OpenCoreEngine

# Set Theme & Appearance
ctk.set_appearance_mode("System")  # Automatically matches macOS Dark/Light mode
ctk.set_default_color_theme("blue")


class OWLPApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OpenCore Windows Legacy Patcher (OWLP)")
        self.geometry("780x890")
        self.minsize(740, 780)

        self.profile = MacHardwareProfile()
        self.disk_engine = DiskEngine()
        self.drives = []

        self.setup_ui()
        self.refresh_drives()
        self.update_hardware_display()
        self.check_internal_apfs()

    def setup_ui(self):
        # Scrollable master container to fit all screens cleanly
        self.main_frame = ctk.CTkScrollableFrame(self, corner_radius=12, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=16)

        # Header Title
        title_label = ctk.CTkLabel(
            self.main_frame,
            text="OpenCore Windows Legacy Patcher",
            font=ctk.CTkFont(family="SF Pro Display", size=22, weight="bold")
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="Unified Windows 10 & 11 Deployment Engine for Intel Macs",
            font=ctk.CTkFont(family="SF Pro Text", size=13),
            text_color="gray"
        )
        subtitle_label.pack(anchor="w", pady=(0, 10))

        # -------------------------------------------------------------
        # 1. Hardware Configuration & Advanced Quirks
        # -------------------------------------------------------------
        self.hw_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        self.hw_card.pack(fill="x", pady=5)

        hw_header_layout = ctk.CTkFrame(self.hw_card, fg_color="transparent")
        hw_header_layout.pack(fill="x", padx=14, pady=(10, 4))

        self.spoof_var = ctk.BooleanVar(value=False)
        self.spoof_chk = ctk.CTkCheckBox(
            hw_header_layout,
            text="Build for another Mac (Target Model Spoofing)",
            variable=self.spoof_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_spoof_toggle
        )
        self.spoof_chk.pack(side="left")

        # Models Dropdown
        self.models_list = get_all_models()
        self.model_names = [f"{name} [{m_id}]" for m_id, name in self.models_list]
        self.model_combo = ctk.CTkComboBox(
            hw_header_layout,
            values=self.model_names,
            width=320,
            command=self.on_model_select,
            state="disabled"
        )
        if self.model_names:
            self.model_combo.set(self.model_names[0])
        self.model_combo.pack(side="right", padx=(10, 0))

        self.lbl_model = ctk.CTkLabel(self.hw_card, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_model.pack(anchor="w", padx=14, pady=(2, 2))

        self.lbl_board = ctk.CTkLabel(self.hw_card, text="", font=ctk.CTkFont(size=12))
        self.lbl_board.pack(anchor="w", padx=14, pady=(0, 2))

        self.lbl_gpu = ctk.CTkLabel(self.hw_card, text="", font=ctk.CTkFont(size=12))
        self.lbl_gpu.pack(anchor="w", padx=14, pady=(0, 2))

        self.lbl_quirks = ctk.CTkLabel(self.hw_card, text="", font=ctk.CTkFont(size=12), text_color="#E5A93C")
        self.lbl_quirks.pack(anchor="w", padx=14, pady=(0, 6))

        # Dead AMD dGPU Power-Down Toggle (Radeongate Fix)
        self.dgpu_off_var = ctk.BooleanVar(value=False)
        self.dgpu_off_chk = ctk.CTkCheckBox(
            self.hw_card,
            text="Disable failing AMD dGPU (Force Intel HD Graphics on 2011/2012 15\" MacBook Pro)",
            variable=self.dgpu_off_var,
            font=ctk.CTkFont(size=11),
            text_color="#FF9500"
        )
        self.dgpu_off_chk.pack(anchor="w", padx=14, pady=(0, 10))

        # -------------------------------------------------------------
        # 2. Internal APFS Auto-Partitioning
        # -------------------------------------------------------------
        self.apfs_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        self.apfs_card.pack(fill="x", pady=5)

        apfs_title = ctk.CTkLabel(self.apfs_card, text="Internal Drive Setup (Create BOOTCAMP Partition)", font=ctk.CTkFont(size=13, weight="bold"))
        apfs_title.pack(anchor="w", padx=14, pady=(10, 4))

        self.lbl_apfs_info = ctk.CTkLabel(self.apfs_card, text="Scanning internal drive layout...", font=ctk.CTkFont(size=12))
        self.lbl_apfs_info.pack(anchor="w", padx=14, pady=(0, 6))

        apfs_row = ctk.CTkFrame(self.apfs_card, fg_color="transparent")
        apfs_row.pack(fill="x", padx=14, pady=(0, 12))

        lbl_size = ctk.CTkLabel(apfs_row, text="Partition Size (GB):", font=ctk.CTkFont(size=12))
        lbl_size.pack(side="left", padx=(0, 8))

        self.apfs_size_entry = ctk.CTkEntry(apfs_row, width=80)
        self.apfs_size_entry.insert(0, "64")
        self.apfs_size_entry.pack(side="left", padx=(0, 12))

        self.btn_partition = ctk.CTkButton(
            apfs_row,
            text="Partition Mac Now",
            width=150,
            fg_color="#34C759",
            hover_color="#28a745",
            command=self.start_apfs_partition
        )
        self.btn_partition.pack(side="left")

        # -------------------------------------------------------------
        # 3. Windows ISO Selection
        # -------------------------------------------------------------
        iso_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        iso_card.pack(fill="x", pady=5)

        iso_title = ctk.CTkLabel(iso_card, text="Windows 10 / 11 ISO Source", font=ctk.CTkFont(size=13, weight="bold"))
        iso_title.pack(anchor="w", padx=14, pady=(10, 4))

        iso_row = ctk.CTkFrame(iso_card, fg_color="transparent")
        iso_row.pack(fill="x", padx=14, pady=(0, 12))

        self.iso_entry = ctk.CTkEntry(iso_row, placeholder_text="Select path to Windows ISO file...")
        self.iso_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_browse = ctk.CTkButton(iso_row, text="Browse...", width=100, command=self.browse_iso)
        btn_browse.pack(side="right")

        # -------------------------------------------------------------
        # 4. Target USB Flash Drive
        # -------------------------------------------------------------
        drv_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        drv_card.pack(fill="x", pady=5)

        drv_title = ctk.CTkLabel(drv_card, text="Target USB Flash Drive", font=ctk.CTkFont(size=13, weight="bold"))
        drv_title.pack(anchor="w", padx=14, pady=(10, 4))

        drv_row = ctk.CTkFrame(drv_card, fg_color="transparent")
        drv_row.pack(fill="x", padx=14, pady=(0, 12))

        self.drv_combo = ctk.CTkComboBox(drv_row, values=["Scanning drives..."], state="readonly")
        self.drv_combo.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_refresh = ctk.CTkButton(drv_row, text="Refresh", width=100, command=self.refresh_drives)
        btn_refresh.pack(side="right")

        # -------------------------------------------------------------
        # 5. Status & Progress
        # -------------------------------------------------------------
        prog_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        prog_card.pack(fill="x", pady=5)

        self.lbl_status = ctk.CTkLabel(prog_card, text="Ready.", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_status.pack(anchor="w", padx=14, pady=(8, 2))

        self.prog_bar = ctk.CTkProgressBar(prog_card)
        self.prog_bar.set(0.0)
        self.prog_bar.pack(fill="x", padx=14, pady=(0, 10))

        # -------------------------------------------------------------
        # 6. Embedded Console Log
        # -------------------------------------------------------------
        log_card = ctk.CTkFrame(self.main_frame, corner_radius=10)
        log_card.pack(fill="both", expand=True, pady=5)

        log_title = ctk.CTkLabel(log_card, text="Console Output", font=ctk.CTkFont(size=12, weight="bold"))
        log_title.pack(anchor="w", padx=14, pady=(6, 2))

        self.txt_log = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family="Menlo", size=11), text_color="#4af626", fg_color="#121212", height=100)
        self.txt_log.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        # -------------------------------------------------------------
        # 7. Action Button
        # -------------------------------------------------------------
        self.btn_build = ctk.CTkButton(
            self.main_frame,
            text="Build Windows USB Installer",
            height=46,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.start_build
        )
        self.btn_build.pack(fill="x", pady=(8, 12))

    def update_hardware_display(self):
        report = self.profile.evaluate_windows_support()
        tag = "(Target Model Spoofing)" if self.profile.is_spoofed else "(Host Mac)"

        self.lbl_model.configure(text=f"Model: {self.profile.friendly_name} [{self.profile.model_id}]  {tag}")
        self.lbl_board.configure(text=f"Board ID: {self.profile.board_id}   |   T2 Security: {'Yes' if self.profile.has_t2 else 'No'}")
        self.lbl_gpu.configure(text=f"GPU(s): {', '.join(self.profile.gpus) if self.profile.gpus else 'Integrated Graphics'}")

        quirks = report.get("quirks_needed", [])
        if quirks:
            self.lbl_quirks.configure(text=f"Applied Patches: {', '.join(quirks)}")
        else:
            self.lbl_quirks.configure(text="Applied Patches: Standard UEFI (No ACPI Audio Patches Needed)")

        # Show/hide dGPU disable option for 2011/2012 models
        if any(x in self.profile.model_id for x in ["MacBookPro8,2", "MacBookPro9,1"]):
            self.dgpu_off_chk.configure(state="normal")
        else:
            self.dgpu_off_chk.configure(state="disabled")
            self.dgpu_off_var.set(False)

    def check_internal_apfs(self):
        info = self.disk_engine.get_internal_apfs_info()
        if not info:
            self.lbl_apfs_info.configure(text="No APFS container detected or unsupported drive layout.")
            self.btn_partition.configure(state="disabled")
            return

        if info["has_bootcamp"]:
            self.lbl_apfs_info.configure(text="A 'BOOTCAMP' partition is already present on this Mac.")
            self.btn_partition.configure(state="disabled")
        else:
            self.lbl_apfs_info.configure(
                text=f"Container: {info['container_id']} (Total: {info['current_gb']} GB) | Safe to allocate: Up to {info['allocatable_gb']} GB"
            )
            self.btn_partition.configure(state="normal")

    def start_apfs_partition(self):
        try:
            size_gb = int(self.apfs_size_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Size", "Please enter a valid number of GB (e.g. 64).")
            return

        confirm = messagebox.askyesno(
            "Confirm Partition",
            f"This will non-destructively shrink your macOS APFS container and create a {size_gb} GB 'BOOTCAMP' partition.\n\nProceed?"
        )
        if not confirm:
            return

        self.btn_partition.configure(state="disabled")
        self.log(f"[*] Starting APFS partition resize ({size_gb} GB for BOOTCAMP)...")

        def _worker():
            success, msg = self.disk_engine.create_bootcamp_partition(size_gb)
            if success:
                self.log(f"[+] {msg}")
                messagebox.showinfo("Success", f"{msg}\n\nYou can now boot from your USB and install Windows directly into this partition!")
            else:
                self.log(f"[!] Error: {msg}")
                messagebox.showerror("Partition Failed", msg)
            self.check_internal_apfs()

        threading.Thread(target=_worker, daemon=True).start()

    def on_spoof_toggle(self):
        enabled = self.spoof_var.get()
        self.model_combo.configure(state="normal" if enabled else "disabled")
        if enabled:
            self.on_model_select(self.model_combo.get())
        else:
            self.profile = MacHardwareProfile()
            self.update_hardware_display()

    def on_model_select(self, choice):
        if self.spoof_var.get():
            for m_id, name in self.models_list:
                if f"{name} [{m_id}]" == choice:
                    self.profile = MacHardwareProfile(target_model=m_id)
                    self.update_hardware_display()
                    break

    def browse_iso(self):
        path = filedialog.askopenfilename(title="Select Windows ISO", filetypes=[("ISO Files", "*.iso")])
        if path:
            self.iso_entry.delete(0, "end")
            self.iso_entry.insert(0, path)

    def refresh_drives(self):
        self.drives = self.disk_engine.list_external_usb_drives()
        if not self.drives:
            self.drv_combo.configure(values=["No eligible USB drives found (>= 8GB)"])
            self.drv_combo.set("No eligible USB drives found (>= 8GB)")
            self.btn_build.configure(state="disabled")
        else:
            vals = [f"{d.device_node} - {d.media_name} ({d.size_gb} GB)" for d in self.drives]
            self.drv_combo.configure(values=vals)
            self.drv_combo.set(vals[0])
            self.btn_build.configure(state="normal")

    def log(self, text):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")

    def set_status(self, text, progress_pct):
        self.lbl_status.configure(text=text)
        self.prog_bar.set(progress_pct / 100.0)

    def start_build(self):
        iso = self.iso_entry.get().strip().strip("'\"")
        if not iso or not os.path.isfile(iso):
            messagebox.showerror("Error", "Please select a valid Windows ISO file.")
            return

        selected_str = self.drv_combo.get()
        target_disk = None
        for d in self.drives:
            if d.device_node in selected_str:
                target_disk = d.device_node
                break

        if not target_disk:
            messagebox.showerror("Error", "Please select a valid target USB drive.")
            return

        confirm = messagebox.askyesno(
            "Confirm Erase",
            f"WARNING: ALL DATA ON {target_disk} WILL BE ERASED!\n\nTarget Model: {self.profile.model_id}\n\nProceed?"
        )
        if not confirm:
            return

        self.btn_build.configure(state="disabled")
        self.btn_partition.configure(state="disabled")
        self.txt_log.delete("1.0", "end")

        threading.Thread(target=self._run_pipeline, args=(iso, target_disk), daemon=True).start()

    def _run_pipeline(self, iso_path, usb_node):
        try:
            # 1. Format USB Drive
            self.set_status("Formatting USB as GPT FAT32...", 10)
            self.log(f"[*] Initializing {usb_node}...")
            if not self.disk_engine.format_usb_for_installer(usb_node, "WININSTALL"):
                raise RuntimeError("Failed to format USB drive. Check administrator permissions.")

            time.sleep(2)

            # 2. Deploy OpenCore (STRICT: ABORT ON FAILURE)
            self.set_status(f"Injecting OpenCore for {self.profile.model_id}...", 35)
            self.log("[*] Injecting OpenCore EFI bootloader with Advanced Hardware Quirks...")
            oc = OpenCoreEngine(
                usb_node,
                self.profile,
                disable_dead_dgpu=self.dgpu_off_var.get()
            )
            
            # STRICT CHECK: Never continue if OpenCore deployment or ocvalidate fails!
            if not oc.deploy_opencore():
                raise RuntimeError(
                    "OpenCore deployment or schema validation failed!\n\n"
                    "Build aborted immediately to prevent creating an unbootable installer."
                )

            self.log("[+] OpenCore deployment and validation succeeded.")

            # 3. Process Windows ISO (WIM splitting + Zero-Touch autounattend.xml)
            self.set_status("Extracting Windows ISO & splitting WIM...", 65)
            mount = self.disk_engine.find_partition_mount("WININSTALL") or "/Volumes/WININSTALL"
            iso_mgr = WindowsISOManager(iso_path, mount)
            if not iso_mgr.process_and_copy():
                raise RuntimeError("Failed to unpack Windows ISO or split install.wim.")

            # 4. Download and Stage Apple Boot Camp Drivers
            self.set_status("Downloading Boot Camp drivers...", 85)
            self.log(f"[*] Searching Apple catalog for {self.profile.model_id}...")
            driver_eng = DriverEngine(self.profile.model_id)
            pkg = driver_eng.find_driver_package()
            if pkg:
                driver_eng.download_and_extract(pkg["package_url"], mount)
                self.log("[+] Boot Camp drivers staged successfully.")

            self.set_status("Complete! Media Ready.", 100)
            self.log("[+] Windows USB Installer creation complete!")
            messagebox.showinfo("Success", "Installer Ready!\n\nRestart holding Option (Alt) and select 'EFI Boot'.")

        except Exception as e:
            self.set_status("Build Failed", 0)
            self.log(f"[!] Error: {str(e)}")
            messagebox.showerror("Build Failed", str(e))
        finally:
            self.btn_build.configure(state="normal")
            self.check_internal_apfs()


if __name__ == "__main__":
    app = OWLPApp()
    app.mainloop()