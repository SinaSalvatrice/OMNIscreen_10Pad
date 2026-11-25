import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from key_actions import MACRO_CODE, MacroCapture, compile_entry
from model import new_project, validate
from pad_profile import (KEY, KEY_OFFSET, LAYER_SIZE, MACRO_POOL, MACRO_TABLE,
                         PROFILE_SIZE, factory_profile, profile_with_assignments)
from protocol import Usb

K1 = 8 + LAYER_SIZE + KEY_OFFSET
SNIPPET = {"id": "c" * 32, "kind": "text", "name": "Gruß", "text": "Grüße!"}


class MockDevice(Usb):
    def __init__(self):
        self.profile = None
        self.generation = 0
        self.commits = 0
        self.active = False
        self.layer = 1
        self.features = 32 | 64

    def exchange(self, data, *, timeout=4500):
        raw = bytes(data)
        response = bytearray(32)
        response[:3] = raw[:3]
        cmd = raw[2]
        if cmd == 0x71:
            response[3:7] = b"OMP2"
            response[7] = self.profile is not None
            struct.pack_into("<HI", response, 9, PROFILE_SIZE, self.generation)
            response[16] = self.features
        elif cmd == 0x72:
            offset, size = struct.unpack_from("<HB", raw, 3)
            response[6:6 + size] = self.profile[offset:offset + size]
        elif cmd == 0x73:
            self.checksum, generation = struct.unpack_from("<II", raw, 3)
            assert generation == self.generation
            self.pending = bytearray()
        elif cmd == 0x74:
            offset, size = struct.unpack_from("<HB", raw, 3)
            assert len(self.pending) == offset
            self.pending.extend(raw[6:6 + size])
        elif cmd == 0x75:
            checksum = 2166136261
            for value in self.pending:
                checksum = ((checksum ^ value) * 16777619) & 0xFFFFFFFF
            assert len(self.pending) == PROFILE_SIZE and checksum == self.checksum
            self.profile = bytes(self.pending)
            self.generation += 1
            self.commits += 1
        elif cmd == 0x7C and raw[0] == 7:
            assert raw[3] == 1 and struct.unpack_from("<I", raw, 5)[0] == self.generation
            self.active = True
            self.layer = raw[4]
        elif cmd == 0x7C:
            response[5] = 1
            response[6] = self.active
            response[8] = self.layer
            struct.pack_into("<I", response, 10, self.generation)
        else:
            raise AssertionError(cmd)
        return bytes(response)


class AssignmentsTests(unittest.TestCase):
    def test_media_snippet_and_cycle_preserve_untouched_layers(self):
        project = new_project()
        project["library"].append(SNIPPET.copy())
        layer = project["layers"][1]
        layer["key_modes"] = {"K1": "Durchschalten", "K2": "Tap Dance"}
        layer["actions"]["K1"].update({"1×": "Play/Pause", "2×": "library:" + SNIPPET["id"]})
        layer["actions"]["K2"]["Halten"] = "Stumm"
        previous = factory_profile()
        saved = profile_with_assignments(validate(project), bytes(previous))
        self.assertEqual(KEY.unpack_from(saved, K1)[0:7], (2, 180, 0xAE, MACRO_CODE, 0, 0, 0))
        self.assertEqual(KEY.unpack_from(saved, K1 + KEY.size)[6], 0xA8)
        self.assertEqual(saved[8:8 + LAYER_SIZE], previous[8:8 + LAYER_SIZE])
        macro = compile_entry(SNIPPET)
        self.assertEqual(struct.unpack_from("<2H", saved, MACRO_TABLE), (0, len(macro)))
        self.assertEqual(saved[MACRO_POOL:MACRO_POOL + len(macro)], macro)
        self.assertEqual(saved, profile_with_assignments(project, saved))

    def test_capture_keeps_shortcuts_and_releases_held_key_at_stop(self):
        ticks = iter([1., 1.05, 1.08])
        recording = MacroCapture(clock=lambda: next(ticks))
        recording.event(True, "Control_L", 10)
        recording.event(True, "c", 11)
        recording.event(True, "c", 11)
        recording.event(False, "C", 11)
        steps = recording.finish()
        payload = compile_entry({"kind": "macro", "steps": steps})
        self.assertEqual(steps, [[2, 224], [4, 50], [2, 6], [4, 30], [3, 6], [3, 224]])
        self.assertEqual(len(payload), len(steps) * 3)

    def test_upload_uses_transaction_and_verified_readback(self):
        device = MockDevice()
        project = new_project()
        project["active_layer"] = 2
        project["layers"][2]["actions"]["K1"]["1×"] = "Fenster wechseln"
        self.assertIn("Display zeigt NAV", device.upload_assignments(project))
        self.assertEqual(device.commits, 1)
        key = KEY.unpack_from(device.profile, K1 + LAYER_SIZE)
        self.assertEqual(key[2], 0x042B)
        self.assertEqual(key[-1].rstrip(b"\0"), b"ALT TAB")
        self.assertEqual(device.read_active_profile(), (True, 2, 1))
        device.active = False
        self.assertIn("Display zeigt NAV", device.upload_assignments(project))
        self.assertTrue(device.active)
        self.assertEqual(device.commits, 1)

    def test_older_firmware_reports_that_the_source_needs_switching(self):
        device = MockDevice()
        device.features = 32
        self.assertIn("Config Source", device.upload_assignments(new_project()))
        self.assertEqual(device.commits, 1)
        self.assertFalse(device.active)
