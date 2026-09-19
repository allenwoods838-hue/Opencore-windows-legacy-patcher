"""
OWLP - Intel Mac Hardware Database
Maps historical Intel Macs (2008-2020) to Board IDs, T2 chips, and required patches.
"""

from typing import Dict, Any, Optional

MAC_MODELS_DB: Dict[str, Dict[str, Any]] = {
    # ---------------- MacBook Pro ----------------
    "MacBookPro8,1": {
        "name": "MacBook Pro (13-inch, Early/Late 2011)",
        "board_id": "Mac-94245B3640C91C81",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 3000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookPro8,2": {
        "name": "MacBook Pro (15-inch, Early/Late 2011)",
        "board_id": "Mac-94245A3940C91C80",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 3000", "AMD Radeon HD 6490M/6750M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)", "Dual-GPU setup detected"]
    },
    "MacBookPro9,1": {
        "name": "MacBook Pro (15-inch, Mid 2012)",
        "board_id": "Mac-4B7AC7E43945597E",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000", "NVIDIA GeForce GT 650M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)", "Dual-GPU setup detected"]
    },
    "MacBookPro9,2": {
        "name": "MacBook Pro (13-inch, Mid 2012)",
        "board_id": "Mac-6F01561E16C75D06",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookPro10,1": {
        "name": "MacBook Pro (Retina, 15-inch, Mid 2012 / Early 2013)",
        "board_id": "Mac-C3EC7CD22292981F",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000", "NVIDIA GeForce GT 650M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)", "Dual-GPU setup detected"]
    },
    "MacBookPro10,2": {
        "name": "MacBook Pro (Retina, 13-inch, Late 2012 / Early 2013)",
        "board_id": "Mac-AFD4A619801A8333",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookPro11,1": {
        "name": "MacBook Pro (Retina, 13-inch, Late 2013 / Mid 2014)",
        "board_id": "Mac-189A3D4F975D5FFC",
        "has_t2": False,
        "gpus": ["Intel Iris 5100"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookPro11,2": {
        "name": "MacBook Pro (Retina, 15-inch, Late 2013 / Mid 2014, Iris Pro)",
        "board_id": "Mac-3CBD00234E554E41",
        "has_t2": False,
        "gpus": ["Intel Iris Pro 5200"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookPro11,3": {
        "name": "MacBook Pro (Retina, 15-inch, Late 2013 / Mid 2014, Dual GPU)",
        "board_id": "Mac-2E6FAB96566FE58C",
        "has_t2": False,
        "gpus": ["Intel Iris Pro 5200", "NVIDIA GeForce GT 750M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)", "Dual-GPU setup detected"]
    },
    "MacBookPro11,4": {
        "name": "MacBook Pro (Retina, 15-inch, Mid 2015, Integrated)",
        "board_id": "Mac-06F11F11946D27C5",
        "has_t2": False,
        "gpus": ["Intel Iris Pro 5200"],
        "quirks": []
    },
    "MacBookPro11,5": {
        "name": "MacBook Pro (Retina, 15-inch, Mid 2015, Dual GPU)",
        "board_id": "Mac-06F11FD93F0323C5",
        "has_t2": False,
        "gpus": ["Intel Iris Pro 5200", "AMD Radeon R9 M370X"],
        "quirks": ["Dual-GPU setup detected"]
    },
    "MacBookPro12,1": {
        "name": "MacBook Pro (Retina, 13-inch, Early 2015)",
        "board_id": "Mac-E43C1C25D4880AD6",
        "has_t2": False,
        "gpus": ["Intel Iris Graphics 6100"],
        "quirks": []
    },
    "MacBookPro13,1": {
        "name": "MacBook Pro (13-inch, 2016, Two Thunderbolt 3 ports)",
        "board_id": "Mac-473D31EABEB93F4B",
        "has_t2": False,
        "gpus": ["Intel Iris Graphics 540"],
        "quirks": []
    },
    "MacBookPro13,3": {
        "name": "MacBook Pro (15-inch, 2016)",
        "board_id": "Mac-A5C67F76ED83108C",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 530", "AMD Radeon Pro 450/455/460"],
        "quirks": ["Dual-GPU setup detected"]
    },
    "MacBookPro15,1": {
        "name": "MacBook Pro (15-inch, 2018 / 2019)",
        "board_id": "Mac-937A206F2EE63C01",
        "has_t2": True,
        "gpus": ["Intel UHD Graphics 630", "AMD Radeon Pro 555X/560X"],
        "quirks": ["Requires Apple T2 controller driver injection", "Dual-GPU setup detected"]
    },
    "MacBookPro16,1": {
        "name": "MacBook Pro (16-inch, 2019)",
        "board_id": "Mac-E1008331FDC96864",
        "has_t2": True,
        "gpus": ["Intel UHD Graphics 630", "AMD Radeon Pro 5300M/5500M"],
        "quirks": ["Requires Apple T2 controller driver injection", "Dual-GPU setup detected"]
    },

    # ---------------- MacBook Air ----------------
    "MacBookAir5,2": {
        "name": "MacBook Air (13-inch, Mid 2012)",
        "board_id": "Mac-2E71B2A07024E3FF",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookAir6,2": {
        "name": "MacBook Air (13-inch, Mid 2013 / Early 2014)",
        "board_id": "Mac-7DF21CB3ED6977E5",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 5000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "MacBookAir7,2": {
        "name": "MacBook Air (13-inch, Early 2015 / 2017)",
        "board_id": "Mac-937CB26E2E02BB01",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 6000"],
        "quirks": []
    },
    "MacBookAir8,1": {
        "name": "MacBook Air (Retina, 13-inch, 2018)",
        "board_id": "Mac-827FB448E656EC26",
        "has_t2": True,
        "gpus": ["Intel UHD Graphics 617"],
        "quirks": ["Requires Apple T2 controller driver injection"]
    },

    # ---------------- iMac ----------------
    "iMac12,2": {
        "name": "iMac (27-inch, Mid 2011)",
        "board_id": "Mac-942B59F58194171B",
        "has_t2": False,
        "gpus": ["AMD Radeon HD 6770M/6970M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "iMac13,2": {
        "name": "iMac (27-inch, Late 2012)",
        "board_id": "Mac-FC02E91DDD3FA6A4",
        "has_t2": False,
        "gpus": ["NVIDIA GeForce GTX 660M/675MX/680MX"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "iMac14,2": {
        "name": "iMac (27-inch, Late 2013)",
        "board_id": "Mac-27ADBB7B4CEE8E61",
        "has_t2": False,
        "gpus": ["NVIDIA GeForce GT 755M/GTX 775M/780M"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "iMac18,3": {
        "name": "iMac (Retina 5K, 27-inch, 2017)",
        "board_id": "Mac-BE088AF8C5EB4FA2",
        "has_t2": False,
        "gpus": ["AMD Radeon Pro 570/575/580"],
        "quirks": []
    },
    "iMac20,1": {
        "name": "iMac (Retina 5K, 27-inch, 2020)",
        "board_id": "Mac-CFF7D910A743CAAF",
        "has_t2": True,
        "gpus": ["AMD Radeon Pro 5300/5500 XT/5700/5700 XT"],
        "quirks": ["Requires Apple T2 controller driver injection"]
    },

    # ---------------- Mac mini ----------------
    "Macmini6,2": {
        "name": "Mac mini (Late 2012)",
        "board_id": "Mac-F65AE981FFA204ED",
        "has_t2": False,
        "gpus": ["Intel HD Graphics 4000"],
        "quirks": ["Needs EFI Audio / DSDT Patch (Cirrus Logic sound issue)"]
    },
    "Macmini7,1": {
        "name": "Mac mini (Late 2014)",
        "board_id": "Mac-35C5E08120C70D89",
        "has_t2": False,
        "gpus": ["Intel Iris 5100 / HD Graphics 5000"],
        "quirks": []
    },
    "Macmini8,1": {
        "name": "Mac mini (2018)",
        "board_id": "Mac-7BA5B2D9E42DDD94",
        "has_t2": True,
        "gpus": ["Intel UHD Graphics 630"],
        "quirks": ["Requires Apple T2 controller driver injection"]
    },

    # ---------------- Mac Pro ----------------
    "MacPro6,1": {
        "name": "Mac Pro (Late 2013 / Trashcan)",
        "board_id": "Mac-F60DEB81FF30ACF6",
        "has_t2": False,
        "gpus": ["Dual AMD FirePro D300/D500/D700"],
        "quirks": ["Dual-GPU setup detected"]
    },
    "MacPro7,1": {
        "name": "Mac Pro (2019)",
        "board_id": "Mac-27AD20918AE68F61",
        "has_t2": True,
        "gpus": ["AMD Radeon Pro 580X/W5700X/Vega II"],
        "quirks": ["Requires Apple T2 controller driver injection"]
    }
}


def get_all_models() -> list[tuple[str, str]]:
    """Returns a list of (model_id, friendly_name) tuples for UI dropdowns."""
    return [(model_id, data["name"]) for model_id, data in MAC_MODELS_DB.items()]


def lookup_model(model_id: str) -> Optional[Dict[str, Any]]:
    return MAC_MODELS_DB.get(model_id)