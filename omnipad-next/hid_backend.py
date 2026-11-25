"""Load compiled hidapi even when the conflicting ctypes hid package exists.

The system contains two distributions competing for the Python module name
hid. Prefer the compiled extension, leaving the global packages unchanged.
"""
from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path


def load_hidapi():
    base = Path(sysconfig.get_paths()["platlib"])
    paths = sorted(base.glob("hid*.pyd")) + sorted(base.glob("hid*.so"))
    for path in paths:
        if not path.name.startswith("hid."):
            continue
        try:
            spec = importlib.util.spec_from_file_location("hid", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except (ImportError, OSError):
            continue
    try:
        import hid
        hid.enumerate()
        return hid
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "HID-Treiber fehlt. In PowerShell installieren: py -3 -m pip install hidapi "
            "(das Paket hid ohne hidapi.dll allein reicht unter Windows nicht)."
        ) from exc
