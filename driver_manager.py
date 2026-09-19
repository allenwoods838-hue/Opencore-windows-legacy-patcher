import os
import sys
import re
import shutil
import tempfile
import plistlib
import subprocess
import time
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List

# Stage 1 integration
from hardware import MacHardwareProfile

CATALOG_URL = (
    "https://swscan.apple.com/content/catalogs/others/"
    "index-10.15-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog"
)

CACHE_DIR = os.path.expanduser("~/.cache/owlp")
CATALOG_CACHE_FILE = os.path.join(CACHE_DIR, "sucatalog.plist")


class DriverEngine:
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or MacHardwareProfile().model_id
        os.makedirs(CACHE_DIR, exist_ok=True)

    def _download_with_progress(self, url: str, target_path: str):
        """Downloads a URL to a local path with a console progress indicator."""
        req = Request(url, headers={"User-Agent": "OWLP-DriverDownloader/1.0"})
        with urlopen(req) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            chunk_size = 1024 * 512  # 512 KB
            downloaded = 0
            start_time = time.time()

            with open(target_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    elapsed = time.time() - start_time
                    speed = (downloaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                    
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        bar = "=" * int(pct // 4) + ">"
                        sys.stdout.write(f"\r[{bar:<26}] {pct:5.1f}% ({mb_done:.1f}/{mb_total:.1f} MB) @ {speed:.2f} MB/s")
                    else:
                        mb_done = downloaded / (1024 * 1024)
                        sys.stdout.write(f"\rDownloaded {mb_done:.1f} MB @ {speed:.2f} MB/s")
                    sys.stdout.flush()
        print()

    def get_catalog(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches and caches Apple's Software Update Catalog (24h validity)."""
        cache_valid = False
        if os.path.exists(CATALOG_CACHE_FILE) and not force_refresh:
            file_age = time.time() - os.path.getmtime(CATALOG_CACHE_FILE)
            if file_age < 86400:  # 24 hours
                cache_valid = True

        if cache_valid:
            print("[*] Loading cached Apple update catalog...")
            with open(CATALOG_CACHE_FILE, "rb") as f:
                return plistlib.load(f)

        print("[*] Fetching latest catalog from Apple servers (this may take ~10-20s)...")
        req = Request(CATALOG_URL, headers={"User-Agent": "OWLP-DriverDownloader/1.0"})
        with urlopen(req) as resp:
            data = resp.read()

        catalog = plistlib.loads(data)
        with open(CATALOG_CACHE_FILE, "wb") as f:
            plistlib.dump(catalog, f)
        print("[+] Catalog loaded and cached successfully.")
        return catalog

    def _check_distribution(self, product_key: str, dist_url: str) -> Optional[str]:
        """Inspects a .dist file to check if it supports self.model_id."""
        try:
            req = Request(dist_url, headers={"User-Agent": "OWLP-DriverDownloader/1.0"})
            with urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                # Look for model identifier as standalone word/string literal
                if re.search(rf"['\"]{re.escape(self.model_id)}['\"]", content):
                    return product_key
        except Exception:
            pass
        return None

    def find_driver_package(self) -> Optional[Dict[str, Any]]:
        """Scans catalog distributions to find the latest BootCampESD for this model."""
        catalog = self.get_catalog()
        products = catalog.get("Products", {})

        # 1. Filter products that contain BootCampESD.pkg
        candidate_products: Dict[str, Dict[str, Any]] = {}
        for p_id, p_val in products.items():
            for pkg in p_val.get("Packages", []):
                url = pkg.get("URL", "")
                if url.endswith("BootCampESD.pkg"):
                    dists = p_val.get("Distributions", {})
                    # Prefer English distribution
                    dist_url = dists.get("English") or dists.get("en") or (list(dists.values())[0] if dists else None)
                    if dist_url:
                        candidate_products[p_id] = {
                            "package_url": url,
                            "dist_url": dist_url,
                            "post_date": p_val.get("PostDate", ""),
                            "size": pkg.get("Size", 0)
                        }

        print(f"[*] Checking compatibility across {len(candidate_products)} Boot Camp packages for {self.model_id}...")

        # 2. Check distributions concurrently
        matched_keys: List[str] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_key = {
                executor.submit(self._check_distribution, k, v["dist_url"]): k
                for k, v in candidate_products.items()
            }
            for future in as_completed(future_to_key):
                matched = future.result()
                if matched:
                    matched_keys.append(matched)

        if not matched_keys:
            print(f"[!] No direct Boot Camp ESD package matched model: {self.model_id}")
            return None

        # 3. Sort matches by post_date descending to grab the most recent driver package
        matched_keys.sort(key=lambda k: str(candidate_products[k].get("post_date", "")), reverse=True)
        best_match_id = matched_keys[0]
        selected = candidate_products[best_match_id]

        print(f"[+] Found matching package: {best_match_id} (Release Date: {selected['post_date']})")
        print(f"    Download URL: {selected['package_url']}")
        return selected

    def download_and_extract(self, download_url: str, final_destination: str) -> bool:
        """
        Downloads BootCampESD.pkg, extracts WindowsSupport.dmg, mounts it,
        and copies $WinPEDriver$ and BootCamp directly to final_destination (e.g., USB drive).
        """
        temp_dir = tempfile.mkdtemp(prefix="owlp_bootcamp_")
        pkg_path = os.path.join(temp_dir, "BootCampESD.pkg")
        expanded_pkg_dir = os.path.join(temp_dir, "expanded")

        try:
            print(f"[*] Downloading Boot Camp drivers...")
            self._download_with_progress(download_url, pkg_path)

            print("[*] Expanding Apple flat package (pkgutil)...")
            subprocess.run(["pkgutil", "--expand", pkg_path, expanded_pkg_dir], check=True)

            # Search for 'Payload' file
            payload_path = None
            for root, _, files in os.walk(expanded_pkg_dir):
                if "Payload" in files:
                    payload_path = os.path.join(root, "Payload")
                    break

            if not payload_path:
                print("[!] Error: Payload archive not found inside package.")
                return False

            print("[*] Extracting Payload archive...")
            subprocess.run(["tar", "-xzf", payload_path, "-C", temp_dir], check=True)

            # Search for WindowsSupport.dmg
            dmg_path = None
            for root, _, files in os.walk(temp_dir):
                if "WindowsSupport.dmg" in files:
                    dmg_path = os.path.join(root, "WindowsSupport.dmg")
                    break

            if not dmg_path:
                print("[!] Error: WindowsSupport.dmg not found in payload.")
                return False

            print(f"[+] Found WindowsSupport.dmg. Mounting image...")
            # Mount DMG via hdiutil plist output
            mount_proc = subprocess.run(
                ["hdiutil", "attach", dmg_path, "-plist", "-nobrowse", "-readonly"],
                capture_output=True, text=True, check=True
            )
            mount_info = plistlib.loads(mount_proc.stdout.encode("utf-8"))
            mount_point = None
            for entity in mount_info.get("system-entities", []):
                if "mount-point" in entity:
                    mount_point = entity["mount-point"]
                    break

            if not mount_point:
                print("[!] Failed to locate mounted DMG volume.")
                return False

            print(f"[+] DMG mounted at: {mount_point}")

            # Copy $WinPEDriver$ and BootCamp folders to target destination
            os.makedirs(final_destination, exist_ok=True)
            for item in os.listdir(mount_point):
                src_item = os.path.join(mount_point, item)
                dst_item = os.path.join(final_destination, item)
                
                if item in ["$WinPEDriver$", "BootCamp", "AutoUnattend.xml"]:
                    print(f"[*] Copying {item} to {final_destination}...")
                    if os.path.isdir(src_item):
                        if os.path.exists(dst_item):
                            shutil.rmtree(dst_item)
                        shutil.copytree(src_item, dst_item)
                    else:
                        shutil.copy2(src_item, dst_item)

            print("[*] Detaching DMG...")
            subprocess.run(["hdiutil", "detach", mount_point, "-force"], check=True)
            print(f"[+] All drivers successfully deployed to: {final_destination}")
            return True

        except Exception as e:
            print(f"[!] Error during extraction/copy: {e}")
            return False
        finally:
            print("[*] Cleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    profile = MacHardwareProfile()
    print("=" * 55)
    print("   STAGE 3: BOOT CAMP DRIVER ENGINE")
    print("=" * 55)
    print(f"Target Mac Model: {profile.model_id}")

    engine = DriverEngine(profile.model_id)
    pkg_info = engine.find_driver_package()

    if not pkg_info:
        print("[!] Exiting: No compatible package found.")
        sys.exit(1)

    print("\nTarget Options:")
    print("  [1] Deploy directly to USB (e.g. /Volumes/WININSTALL)")
    print("  [2] Extract to local folder (~/Downloads/WindowsSupport)")
    opt = input("\nSelect option (1 or 2): ").strip()

    if opt == "1":
        dest = input("Enter destination volume path [/Volumes/WININSTALL]: ").strip() or "/Volumes/WININSTALL"
    else:
        dest = os.path.expanduser("~/Downloads/WindowsSupport")

    success = engine.download_and_extract(pkg_info["package_url"], dest)
    if success:
        print("\n[+] Stage 3 completed successfully!")