import subprocess
import plistlib
import re
from typing import Dict, Any, Optional
from mac_database import lookup_model, MAC_MODELS_DB


class MacHardwareProfile:
    def __init__(self, target_model: Optional[str] = None):
        """
        :param target_model: If provided, spoofs the profile using the database.
                             If None, probes the local host Mac.
        """
        self.is_spoofed: bool = bool(target_model)
        self.model_id: str = ""
        self.friendly_name: str = ""
        self.board_id: str = ""
        self.cpu_name: str = ""
        self.gpus: list[str] = []
        self.has_t2: bool = False
        self.is_apple_silicon: bool = False
        self.custom_quirks: list[str] = []

        if target_model:
            self._load_spoofed_model(target_model)
        else:
            self.scan_host_system()

    def _run_cmd(self, cmd: list[str]) -> str:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception:
            return ""

    def _load_spoofed_model(self, model_id: str):
        data = lookup_model(model_id)
        if data:
            self.model_id = model_id
            self.friendly_name = data["name"]
            self.board_id = data["board_id"]
            self.has_t2 = data["has_t2"]
            self.gpus = data["gpus"]
            self.cpu_name = "Target Intel Core / Xeon CPU"
            self.is_apple_silicon = False
            self.custom_quirks = data.get("quirks", [])
        else:
            # Fallback for manually typed model
            self.model_id = model_id
            self.friendly_name = f"Custom Mac ({model_id})"
            self.board_id = "Unknown"
            self.has_t2 = False
            self.cpu_name = "Intel Core Processor"
            self.is_apple_silicon = False
            self.custom_quirks = []

    def scan_host_system(self):
        arch = self._run_cmd(["uname", "-m"])
        self.is_apple_silicon = (arch == "arm64")

        self.model_id = self._run_cmd(["sysctl", "-n", "hw.model"])
        self.cpu_name = self._run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])

        # Check if model exists in database to grab friendly name
        db_match = lookup_model(self.model_id)
        if db_match:
            self.friendly_name = db_match["name"]
            self.board_id = db_match["board_id"]
            self.has_t2 = db_match["has_t2"]
            self.custom_quirks = db_match.get("quirks", [])
        else:
            self.friendly_name = f"Host Mac ({self.model_id})"
            t2_check = self._run_cmd(["ioreg", "-p", "IODeviceTree", "-r", "-n", "AppleT2Controller"])
            self.has_t2 = bool(t2_check)

        self._detect_gpus()

    def _detect_gpus(self):
        try:
            sp_data = self._run_cmd(["system_profiler", "SPDisplaysDataType", "-xml"])
            if sp_data:
                plists = plistlib.loads(sp_data.encode("utf-8"))
                for display_card in plists[0].get("_items", []):
                    card_name = display_card.get("sppci_model")
                    if card_name and card_name not in self.gpus:
                        self.gpus.append(card_name)
        except Exception:
            pass

    def evaluate_windows_support(self) -> Dict[str, Any]:
        if self.is_apple_silicon and not self.is_spoofed:
            return {
                "supported": False,
                "reason": "Host Mac is Apple Silicon. Please select an Intel Target Model."
            }

        quirks = list(self.custom_quirks)
        if not self.is_spoofed:
            if "MacBookPro8," in self.model_id or "MacBookPro9," in self.model_id or "MacBookPro10," in self.model_id:
                if "Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)" not in quirks:
                    quirks.append("Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)")

            if self.has_t2 and "Requires Apple T2 controller driver injection" not in quirks:
                quirks.append("Requires Apple T2 controller driver injection")

        return {
            "supported": True,
            "model": self.model_id,
            "friendly_name": self.friendly_name,
            "board_id": self.board_id,
            "cpu": self.cpu_name,
            "gpus": self.gpus,
            "has_t2": self.has_t2,
            "is_spoofed": self.is_spoofed,
            "quirks_needed": quirks
        }