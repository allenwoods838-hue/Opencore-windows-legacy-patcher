import subprocess
import plistlib
import re
from typing import Dict, Any, Optional

class MacHardwareProfile:
    def __init__(self):
        self.model_id: str = ""
        self.board_id: str = ""
        self.cpu_name: str = ""
        self.gpus: list[str] = []
        self.has_t2: bool = False
        self.is_apple_silicon: bool = False
        self.boot_mode: str = "UEFI"
        
        self.scan_system()

    def _run_cmd(self, cmd: list[str]) -> str:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _get_ioreg_property(self, prop_name: str) -> Optional[str]:
        output = self._run_cmd(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        match = re.search(rf'"{prop_name}"\s*=\s*<?"?([^">]+)"?>?', output)
        if match:
            val = match.group(1)
            # If hex encoded string, try to decode
            try:
                if all(c in "0123456789abcdefABCDEF" for c in val) and len(val) % 2 == 0:
                    decoded = bytes.fromhex(val).decode("utf-8", errors="ignore").strip("\x00")
                    if decoded:
                        return decoded
            except Exception:
                pass
            return val
        return None

    def scan_system(self):
        # 1. Architecture & Model
        arch = self._run_cmd(["uname", "-m"])
        self.is_apple_silicon = (arch == "arm64")

        self.model_id = self._run_cmd(["sysctl", "-n", "hw.model"])
        self.cpu_name = self._run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])

        # 2. Board ID
        board_id = self._get_ioreg_property("board-id")
        self.board_id = board_id if board_id else "Unknown"

        # 3. T2 Security Chip Detection
        t2_check = self._run_cmd(["ioreg", "-p", "IODeviceTree", "-r", "-n", "AppleT2Controller"])
        self.has_t2 = bool(t2_check)

        # 4. GPU Detection
        self._detect_gpus()

    def _detect_gpus(self):
        try:
            sp_data = self._run_cmd(["system_profiler", "SPDisplaysDataType", "-xml"])
            if sp_data:
                plists = plistlib.loads(sp_data.encode("utf-8"))
                for display_card in plists[0].get("_items", []):
                    card_name = display_card.get("sppci_model")
                    if card_name:
                        self.gpus.append(card_name)
        except Exception:
            pass

    def evaluate_windows_support(self) -> Dict[str, Any]:
        """Analyzes what patches this Mac requires for Windows."""
        if self.is_apple_silicon:
            return {
                "supported": False,
                "reason": "Apple Silicon (M1/M2/M3/M4) does not support native Windows x86/x64 bare-metal installation."
            }

        quirks = []
        year_match = re.search(r"(\d+),(\d+)", self.model_id)
        
        # Checking for older models that need ACPI sound fixes (mainly 2011-2014)
        if any(prefix in self.model_id for prefix in ["MacBookPro", "iMac", "Macmini", "MacPro"]):
            if "MacBookPro8," in self.model_id or "MacBookPro9," in self.model_id or "MacBookPro10," in self.model_id:
                quirks.append("Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)")

        if self.has_t2:
            quirks.append("Requires Apple T2 controller driver injection for internal SSD & keyboard/trackpad")

        if len(self.gpus) > 1:
            quirks.append("Dual-GPU setup detected: May require hybrid GPU power state management")

        return {
            "supported": True,
            "model": self.model_id,
            "board_id": self.board_id,
            "cpu": self.cpu_name,
            "gpus": self.gpus,
            "has_t2": self.has_t2,
            "quirks_needed": quirks
        }

if __name__ == "__main__":
    profile = MacHardwareProfile()
    report = profile.evaluate_windows_support()
    
    print("=" * 45)
    print("   STAGE 1: HARDWARE PROFILER REPORT")
    print("=" * 45)
    for key, value in report.items():
        if isinstance(value, list):
            print(f"{key.replace('_', ' ').capitalize()}:")
            for item in value:
                print(f"  - {item}")
        else:
            print(f"{key.replace('_', ' ').capitalize()}: {value}")
    print("=" * 45)