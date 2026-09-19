#!/bin/bash
set -e

REPO="allenwoods838-hue/Opencore-windows-legacy-patcher"
ZIP_URL="https://github.com/${REPO}/releases/latest/download/OWLP-macOS-x86_64.zip"

echo "=================================================="
echo "   OpenCore Windows Legacy Patcher (OWLP) Setup   "
echo "=================================================="
echo "[*] Downloading latest release from ${REPO}..."

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

curl -L -f -s "$ZIP_URL" -o "$TMP_DIR/owlp.zip"

if [ ! -f "$TMP_DIR/owlp.zip" ]; then
    echo "[!] Error: Failed to download release asset from GitHub."
    exit 1
fi

echo "[*] Unpacking binary..."
unzip -q "$TMP_DIR/owlp.zip" -d "$TMP_DIR"
chmod +x "$TMP_DIR/owlp"

# Remove quarantine attribute if present
xattr -d com.apple.quarantine "$TMP_DIR/owlp" 2>/dev/null || true

echo "[*] Starting OWLP with administrator privileges..."
sudo "$TMP_DIR/owlp"