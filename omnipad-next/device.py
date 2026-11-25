"""Serialize all USB exchanges off the Tk event loop."""
from dataclasses import dataclass
import time

from protocol import LiveInputs, ProtocolError, SERPENTINE_MAP, UnsupportedFirmware, Usb


@dataclass
class DeviceInfo:
    status: str
    detail: str = ""
    inputs: LiveInputs | None = None
    preview: bool = False


class LiveUsb:
    def __init__(self):
        self.connection = None
        self.try_after = 0
        self.last_frame = None
        self.last_sent = 0
        self.serpentine = False
        self.info = DeviceInfo("OmniPad wird gesucht …")

    def connect(self):
        self.connection = Usb.connect()
        self.connection.read_live_inputs()  # Discard any presses from before the connection.
        self.serpentine = self.connection.read_map() == bytes(SERPENTINE_MAP)

    def poll(self, colors, *, reconnect=False):
        now = time.monotonic()
        if reconnect:
            self.close()
            self.try_after = 0
        if not self.connection and now < self.try_after:
            return self.info
        try:
            if not self.connection:
                self.connect()
            inputs = self.connection.read_live_inputs()
            if colors is not None and inputs.preview_allowed:
                if colors != self.last_frame or now - self.last_sent >= 0.2:
                    self.last_frame = colors if self.connection.send_preview(
                        colors, serpentine=self.serpentine) else None
                    self.last_sent = time.monotonic()
            else:
                self.stop_preview()
            self.info = DeviceInfo("OmniPad verbunden", "USB-Livefunktionen verfügbar",
                                   inputs, self.last_frame is not None)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.close()
            self.try_after = now + 1.0
            status = ("Firmware-Update für Livefunktionen nötig" if isinstance(
                exc, UnsupportedFirmware) else "USB-Liveverbindung wartet")
            self.info = DeviceInfo(status, str(exc))
        return self.info

    def stop_preview(self):
        if self.last_frame is not None:
            self.last_frame = None
            self.connection.stop_preview()

    def upload(self, project):
        self.close()
        connection = Usb.connect()
        try:
            return connection.upload(project)
        finally:
            connection.close()
            self.try_after = 0

    def close(self):
        if self.connection is not None:
            try:
                self.stop_preview()
            except (OSError, ProtocolError, ValueError):
                pass
            finally:
                self.connection.close()
                self.connection = None
