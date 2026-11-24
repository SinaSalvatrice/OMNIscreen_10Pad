"""The layer view follows the active Pad source independently of drafts."""

from pathlib import Path
from struct import pack_into
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from via import OmniPad


class DeviceLayerTests(unittest.TestCase):
    def test_firmware_seven_exposes_the_builtin_media_layer(self):
        device = object.__new__(OmniPad)
        device.firmware = 7
        state = device.device_layer_state({"enabled": False, "generation": 3})
        layers = device.read_device_layers(state)
        self.assertEqual((state.source, len(layers), layers[-1].name), ("Firmware", 8, "MEDIA"))
        self.assertEqual(layers[-1].labels[:4], ("MUTE", "VOL-", "VOL+", "STOP"))

    def test_readout_uses_active_source_and_pad_labels(self):
        device = object.__new__(OmniPad)
        device.firmware = 9
        source = 0

        def exchange(request, *, timeout):
            _, _, _, layer, page = request
            report = bytearray(32)
            if layer == 255:
                report[5:10] = bytes((1, source, 2, 0, 1))
                pack_into("<I", report, 10, 10)
            elif page == 0:
                title = ("DEFAULT", "CUSTOM")[layer] if source else ("DEFAULT", "MEDIA")[layer]
                report[5:5 + len(title)] = title.encode()
                pack_into("<H", report, 21, 0xF800)
            elif layer == 1 and page == 1:
                report[5:9] = b"MUTE"
                report[17:21] = b"VOL-"
            return bytes(report)

        device._exchange = exchange
        state = device.device_layer_state()
        self.assertEqual((state.source, state.active, state.shown), ("Firmware", 0, 1))
        layer = device.read_device_layers(state)[1]
        self.assertEqual((layer.name, layer.color, layer.labels[:2]), ("MEDIA", "#ff0000", ("MUTE", "VOL-")))
        source = 1
        updated = device.device_layer_state()
        self.assertNotEqual(state.layout_identity, updated.layout_identity)
        self.assertEqual(updated.source, "App-Profil")
        self.assertEqual(device.read_device_layers(updated)[1].name, "CUSTOM")
