"""Offline USB protocol integration tests: safe firmware gating, staging and readback."""
import copy
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model import new_project
from protocol import (Usb, LightingPayload, LiveInputs, ProtocolError, UnsupportedFirmware,
                      prepare_lighting, zone_record, ZONE_MAP, SERPENTINE_MAP)


class EmulatedUsb(Usb):
    def __init__(self, *, new=True, bad_ack=False):
        self.new = new
        self.bad_ack = bad_ack
        base = prepare_lighting(new_project())
        self.stored = LightingPayload(copy.deepcopy(base.zones), base.tints,
                                     bytes(SERPENTINE_MAP))
        self.pending = None
        self.commands = []
        self.commits = 0
        self.writes = 0
        self.storage_version = 3

    def exchange(self, request, *, timeout=4500):
        req = tuple(request)
        op, channel, cmd = req[:3]
        self.commands.append(req)
        if channel:
            raise ProtocolError("Bad channel")
        result = bytearray(32)
        result[:3] = bytes(req[:3])
        get = op == 0x08
        if cmd == 0x71 and get:
            result[3:7] = b"OMP2"
            result[11:15] = (28).to_bytes(4, "little")
        elif cmd == 0x7B and get:
            result[3:7] = b"MZ01"
            result[7:10] = (5, 30, 43)
        elif cmd == 0x7D and get and req[3] == 255:
            if not self.new:
                raise UnsupportedFirmware("Firmware MZ01")
            result[3:7] = b"LX02"
            result[7:10] = (8, 6, 96)
            result[10:12] = (4, self.storage_version)
        elif cmd == 0x7F and get:
            result[3:7] = b"NL01"
            struct.pack_into("<HHBBB", result, 7, 0x400, 0x801, 7, 17, 1)
        elif cmd == 0x7E and not get:
            result[3:5] = bytes(req[3:5]).ljust(2, b"\0")
        elif cmd == 0x7A and get:
            layer, zone = req[3:5]
            if layer == 255:
                result[5:20] = self.stored.mapping[zone*15:(zone+1)*15]
            else:
                result[5:15] = self.stored.zones[layer, zone]
        elif cmd == 0x7D and get:
            offset, size = req[3:5]
            result[5:5+size] = self.stored.tints[offset:offset+size]
        elif cmd == 0x7A and not get:
            layer, zone = req[3:5]
            self.prepare_stage()
            if layer == 255:
                data = bytearray(self.pending.mapping)
                data[zone*15:(zone+1)*15] = bytes(req[5:20])
                self.pending.mapping = bytes(data)
            else:
                self.pending.zones[(layer, zone)] = bytes(req[5:15])
            self.writes += 1
        elif cmd == 0x7D and not get:
            offset, size = req[3:5]
            self.prepare_stage()
            tints = bytearray(self.pending.tints)
            tints[offset:offset+size] = bytes(req[5:5+size])
            self.pending.tints = bytes(tints)
            self.writes += 1
        elif cmd == 0x7B and not get:
            if req[3] == 4:
                self.stored = self.pending
                self.pending = None
                self.commits += 1
                self.storage_version = 4
            else:
                self.pending = None
        else:
            raise ProtocolError(f"Unexpected command {req}")
        if self.bad_ack and not get and cmd == 0x7A and self.writes == 4:
            raise ProtocolError("Mocked lost ACK")
        return bytes(result)

    def prepare_stage(self):
        if self.pending is None:
            self.pending = copy.deepcopy(self.stored)

    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_live_frame_follows_wiring_and_never_stages_eeprom(self):
        pad = EmulatedUsb()
        pad.preview_sequence = 0
        colors = [(i, i + 1, i + 2) for i in range(73)]
        self.assertTrue(pad.send_preview(colors, serpentine=True))
        self.assertEqual(len(pad.commands), 9)
        self.assertTrue(all(req[:3] == (7, 0, 0x7E) for req in pad.commands))
        payload = b"".join(bytes(req[5:]) for req in pad.commands)
        self.assertEqual(len(payload), 73 * 3)
        self.assertEqual(payload[15:18], bytes(colors[9]))
        self.assertEqual(payload[87:90], bytes(colors[25]))
        self.assertEqual(payload[90:93], bytes(colors[30]))
        pad.stop_preview()
        self.assertEqual(pad.commands[-1], (7, 0, 0x7E, 255))
        self.assertEqual(pad.commits, 0)
        self.assertIsNone(pad.pending)

    def test_reads_held_and_latched_presses_separately(self):
        self.assertEqual(EmulatedUsb().read_live_inputs(), LiveInputs(0x400, 0x801, 7, 17, True))

    def test_flags_and_tints_per_layer(self):
        p = new_project()
        base = p["layers"][1]["groups"]["matrix"]
        base.update(animation="Wandernde Streifen", color_a_mode="Regenbogen",
                    color_b_mode="Farbwechsel")
        reaction = base["reactive"]
        frame = p["layers"][1]["groups"]["frame"]
        frame["reactive"].update(triggers=["Tastendruck"], palette="Bunt")
        frame.update(color_a_brightness=0, color_b_brightness=52)
        reaction.update(enabled=True, duration=1750, palette="Zwei Farben")
        raw = zone_record(base, reaction, zone="encoder")
        effect, bright, _, flags, _, _, triggers, duration = struct.unpack("<BBBBHHBB", raw)
        self.assertEqual(triggers, 2 | 4)
        self.assertEqual(flags, 1 | 4)
        self.assertEqual(duration, 175)
        self.assertEqual(effect, 12 | (5 << 4))
        self.assertLessEqual(bright, 64)
        payload = prepare_lighting(p)
        self.assertEqual(len(payload.zones), 48)
        self.assertEqual(len(payload.tints), 112)
        self.assertEqual(payload.tints[97], 1)
        self.assertEqual(payload.zones[1, 0][8], 1)
        self.assertEqual(payload.zones[1, 4][8], 32)
        self.assertEqual(payload.zones[8, 1][8], 1)
        self.assertEqual(payload.tints[105], 2)
        self.assertEqual(payload.tints[4:8], bytes((100,100,0,52)))
        self.assertEqual(len(payload.mapping), 30)

    def test_old_firmware_no_writes(self):
        pad = EmulatedUsb(new=False)
        with self.assertRaises(UnsupportedFirmware):
            pad.upload(new_project())
        self.assertEqual(pad.writes, 0)
        self.assertEqual(pad.commits, 0)

    def test_exact_readback_and_existing_winding_preserved(self):
        pad = EmulatedUsb()
        p = new_project()
        p["layers"][3]["groups"]["frame"]["speed"] = 67
        self.assertIn("vollständig zurückgelesen", pad.upload(p))
        self.assertEqual(pad.commits, 1)
        self.assertEqual(pad.stored.mapping, bytes(SERPENTINE_MAP))
        frame = p["layers"][3]["groups"]["frame"]
        matrix = p["layers"][3]["groups"]["matrix"]
        self.assertEqual(pad.stored.zones[(8, 3)], zone_record(
            frame, frame["reactive"], zone="frame"))
        self.assertEqual(pad.stored.zones[(3, 1)], zone_record(
            matrix, matrix["reactive"], zone="slider"))
        self.assertEqual(pad.upload(p), "Die LED-Konfiguration ist bereits identisch.")
        self.assertEqual(pad.commits, 1)

    def test_incomplete_transfer_is_aborted(self):
        pad = EmulatedUsb(bad_ack=True)
        p = new_project()
        p["layers"][1]["groups"]["frame"]["speed"] = 90
        old = copy.deepcopy(pad.stored)
        with self.assertRaisesRegex(ProtocolError, "lost ACK"):
            pad.upload(p)
        self.assertEqual(pad.commits, 0)
        self.assertEqual(pad.stored, old)
        self.assertIsNone(pad.pending)

    def test_legacy_overrides_do_not_change_fixed_zones(self):
        p = new_project()
        before = prepare_lighting(p)
        p["layers"][0]["led_overrides"]["12"] = copy.deepcopy(
            p["layers"][0]["groups"]["matrix"])
        p["layers"][0]["led_overrides"]["12"]["brightness"] = 13
        p["layers"][0]["groups"]["slider"].update(override=True, brightness=2)
        self.assertEqual(prepare_lighting(p), before)


if __name__ == "__main__":
    unittest.main()
