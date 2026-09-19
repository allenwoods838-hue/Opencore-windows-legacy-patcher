# OpenCore Windows Legacy Patcher (OWLP)

Easily create a bootable Windows 10 or 11 USB installer tailored for Intel Macs (2008–2020), complete with Apple Boot Camp drivers, Windows 11 hardware bypasses, and audio fixes.

---

## ⚡ Quick Setup and Clone the Repository

Open **Terminal** and run these commands to install requirements:

```bash
git clone https://github.com/allenwoods838-hue/Opencore-windows-legacy-patcher.git
cd Opencore-windows-legacy-patcher
# 1. Install the GUI library
pip3 install customtkinter
```


# 2. Install wimlib (required to handle large Windows files)
## If using Homebrew:
```bash
brew install wimlib
```

## If using MacPorts:
```bash
sudo port install wimlib tk +quartz
```

## 🚀 How to Run
Launch the modern graphical interface:

```Bash
sudo python3 gui.py
```
(Or run sudo python3 main.py for the terminal version).

## 🛠 How to Use
Target Model: Leave on default (Host Mac), or check "Build for another Mac" to pick an older Mac model.
Select ISO: Choose your downloaded Windows 10 or 11 .iso file.
Select USB: Pick your plugged-in USB flash drive (8 GB or larger).
Build: Click Build Windows Installer and wait for it to complete.


## 💻 Installing Windows on Your Mac
Partition: Open macOS Disk Utility, click Partition, and create a new partition named BOOTCAMP formatted as MS-DOS (FAT).
Boot: Restart your Mac and immediately hold down the Option (Alt) key. Select the yellow EFI Boot icon, then choose Windows.
Install: In Windows setup, select the BOOTCAMP partition, click Format, and proceed.
Drivers: Once on the Windows desktop, open your USB drive, go to the BootCamp folder, and run Setup.exe.

## ❓ Troubleshooting
Missing Tkinter / GUI won't open?
MacPorts: 
```bash
sudo port install py312-tkinter tk +quartz
```
Homebrew:
```bash
brew install python-tk@3.12
```