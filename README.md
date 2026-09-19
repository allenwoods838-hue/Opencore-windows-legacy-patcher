# OpenCore Windows Legacy Patcher (OWLP)

[![Release](https://img.shields.io/github/v/release/allenwoods838-hue/Opencore-windows-legacy-patcher?color=brightgreen)](https://github.com/allenwoods838-hue/Opencore-windows-legacy-patcher/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An automated OpenCore-assisted Windows 10 & 11 deployment engine specifically engineered for Intel Macs (2008–2020).

---

## Features

- **Automated Boot Camp Driver Fetcher**: Scrapes Apple's master catalog and extracts `$WinPEDriver$` and `BootCamp` drivers matching your exact Mac Model ID.
- **Windows 11 Hardware Bypass**: Automatically injects an `autounattend.xml` answer file bypassing TPM 2.0, Secure Boot, RAM, and CPU generation requirements.
- **WIM Splitting**: Automatically splits `install.wim` into FAT32-compatible `.swm` chunks using `wimlib-imagex`.
- **Cirrus Logic EFI Audio Patch**: Injects OpenCore with `SSDT-XOSI` to fix the notorious broken audio bug on 2011–2014 Macs booted via UEFI.
- **Pure USB Target Mode**: Prepares an external installer without touching your internal drive's EFI partition.

---

## Quick Start (Terminal One-Liner)

Open Terminal on your Mac and run:

curl -fsSL https://raw.githubusercontent.com/allenwoods838-hue/Opencore-windows-legacy-patcher/main/install.sh | bash