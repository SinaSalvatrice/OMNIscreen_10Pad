"""Show startup errors when the editor is launched without a console."""

import ctypes
import os
import traceback
from pathlib import Path


if __name__ == "__main__":
    try:
        from app import main

        main()
    except Exception as error:
        log_path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OmniPad" / "startup.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
            log_message = f"Startprotokoll: {log_path}"
        except OSError:
            log_message = "Das Startprotokoll konnte nicht gespeichert werden."
        ctypes.windll.user32.MessageBoxW(
            None, f"{type(error).__name__}: {error}\n\n{log_message}",
            "OmniPad Editor konnte nicht gestartet werden", 0x10,
        )
        raise SystemExit(1) from None
