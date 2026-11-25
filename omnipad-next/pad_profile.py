"""Merge app assignments into the firmware's transactional OMP2 profile."""

import re
import struct
import unicodedata

from key_actions import (BUILTINS, DEFAULT_ACTION, DISPLAY_SHORTCUTS, KEY_MODES, LEGACY_EMPTY,
                         LIBRARY_PREFIX, MACRO_BYTES, MACRO_CODE, MACRO_SLOTS, NO_ACTION, compile_entry)
from model import GESTURES, LAYER_DATA

PROFILE_SIZE = 6124
LAYER_SIZE = 354
KEY = struct.Struct("<BH5H12s")
U16 = struct.Struct("<H")
MAX_LAYERS = 12
KEY_OFFSET = 18
ENCODER_OFFSET = KEY_OFFSET + KEY.size * 12
SLIDER_OFFSET = ENCODER_OFFSET + 4
MACRO_TABLE = 8 + LAYER_SIZE * MAX_LAYERS + 4 + 16 * 38
MACRO_POOL = MACRO_TABLE + MACRO_SLOTS * 4
TO_LAYER = 0x5200
DEFAULT_DOUBLE = (1, 2, 3, 4, None, 7, 7, 5, 0, None)
KEY_NAMES = tuple(f"K{i}" for i in range(1, 11))
ROTATION_ACTIONS = ("Encoder links", "Encoder rechts")
SLIDER_ACTIONS = ("Regler runter", "Regler hoch")
FIRMWARE_KEYS = {
    "KC_NO": 0, "KC_ESC": 41, "KC_ENT": 40, "KC_TAB": 43, "KC_BSPC": 42,
    "KC_LSFT": 225, "KC_DEL": 76, "KC_LCTL": 224, "KC_LALT": 226,
    "KC_HOME": 74, "KC_PGUP": 75, "KC_UP": 82, "KC_END": 77, "KC_LEFT": 80,
    "KC_DOWN": 81, "KC_RGHT": 79, "KC_SPC": 44,
    "KC_MUTE": 0xA8, "KC_VOLD": 0xAA, "KC_VOLU": 0xA9, "KC_MSTP": 0xAD,
    "KC_MPRV": 0xAC, "KC_MNXT": 0xAB, "KC_MPLY": 0xAE,
    "MS_WHLU": 0xDA, "MS_WHLD": 0xDB, "MS_BTN1": 0xD1,
    "UG_TOGG": 0x7820, "UG_HUED": 0x7824, "UG_HUEU": 0x7823,
    "UG_VALD": 0x7828, "UG_VALU": 0x7827, "UG_SPDU": 0x7829,
}


def firmware_code(symbol):
    if symbol in FIRMWARE_KEYS:
        return FIRMWARE_KEYS[symbol]
    if symbol.startswith("QK_MACRO_"):
        # The native macro bank is selected in Firmware mode, separate from this profile.
        return 0
    if symbol.startswith("KC_"):
        key = symbol[3:]
        return BUILTINS[{"Y": "Z", "Z": "Y"}.get(key, key)]
    modifier, inner = re.fullmatch(r"(LCTL|LSFT|LALT|LGUI)\((.*)\)", symbol).groups()
    return {"LCTL": 0x0100, "LSFT": 0x0200, "LALT": 0x0400, "LGUI": 0x0800}[modifier] | firmware_code(inner)


def packed_text(text, length):
    ascii_text = unicodedata.normalize("NFKD", text.upper()).encode("ascii", "ignore")
    return ascii_text[:length - 1].ljust(length, b"\0")


def factory_key(layer, index, spec):
    if index >= 10:
        code = firmware_code(spec["encoder"]["press"]) if index == 10 else 0
        return KEY.pack(0, 180, code, 0, 0, 0, 0, packed_text("PUSH" if index == 10 else "K0", 12))
    key = spec["keys"][index]
    code = firmware_code(key["tap"])
    target = DEFAULT_DOUBLE[index]
    if index == 8 and layer not in (4, 5):
        target = None  # Immediate Ctrl double-tap is handled by firmware.
    return KEY.pack(int(target is not None), 180, code, TO_LAYER + target if target is not None else 0,
                    0, 0, code if target is not None else 0, packed_text(key["label"], 12))


def level_slider(layer):
    if layer == 3:
        return 0xDB, 0xDA
    if layer == 7:
        return 0xAA, 0xA9
    if layer in (0, 1, 2, 4):
        return 0x0156, 0x0157
    return 0, 0


def factory_profile():
    profile = bytearray(PROFILE_SIZE)
    specs = LAYER_DATA["layers"]
    struct.pack_into("<4s4B", profile, 0, b"OMP2", len(specs), 1, 0, 0)
    for index, spec in enumerate(specs):
        start = 8 + index * LAYER_SIZE
        hex_color = spec["accent"]
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        struct.pack_into("<16sH", profile, start, packed_text(spec["name"], 16),
                         (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
        for key in range(12):
            offset = start + KEY_OFFSET + key * KEY.size
            profile[offset:offset + KEY.size] = factory_key(index, key, spec)
        struct.pack_into("<2H", profile, start + ENCODER_OFFSET,
                         firmware_code(spec["encoder"]["ccw"]), firmware_code(spec["encoder"]["cw"]))
        low, high = level_slider(index)
        struct.pack_into("<4B4H", profile, start + SLIDER_OFFSET, int(bool(low or high)),
                         0, 4, 64, low, high, 0, 1023)
        # The separate LED profile supplies current lighting. These are valid legacy defaults.
        struct.pack_into("<4B2H2B", profile, start + SLIDER_OFFSET + 12, 0, 24, 128, 1, 0xCC2B, 0x74F7, 7, 50)
        struct.pack_into("<4B2H2B", profile, start + SLIDER_OFFSET + 22, 0, 24, 128, 1, 0x74F7, 0xCC2B, 7, 50)
    profile[-40:-36] = b"SCR1"
    for view in range(6):
        struct.pack_into("<BBHH", profile, PROFILE_SIZE - 36 + view * 6, 0, 0, 0x10A3, 0xCC2B)
    return profile


def locked_key(layer, key):
    return (key in ("K0", "Zusatzbutton")
            or key == "K5" and layer not in (5, 6)
            or key == "K9" and layer not in (4, 5, 6)
            or key == "K10" and layer not in (3, 5, 6))


def inferred_mode(actions):
    return "Tap Dance" if any(actions.get(gesture, LEGACY_EMPTY) not in
                             (LEGACY_EMPTY, DEFAULT_ACTION) for gesture in GESTURES[1:]) else "Direkt"


def profile_with_assignments(project, existing=None, *, encoder_push=False):
    base = factory_profile()
    if existing is not None:
        if len(existing) != PROFILE_SIZE or existing[:4] != b"OMP2" or not base[4] <= existing[4] <= MAX_LAYERS:
            raise ValueError("Das gespeicherte Geräteprofil hat eine andere Layer-Struktur.")
        profile = bytearray(existing)
    else:
        profile = bytearray(base)
    library = {entry["id"]: entry for entry in project.get("library", [])}
    pending = {}

    def set_action(offset, value, factory=0):
        if value in (None, LEGACY_EMPTY, DEFAULT_ACTION):
            code = factory
        elif value.startswith(LIBRARY_PREFIX):
            identifier = value.removeprefix(LIBRARY_PREFIX)
            if identifier not in library:
                raise ValueError("Eine Belegung verweist auf einen fehlenden Bibliothekseintrag.")
            pending[offset] = identifier
            code = 0
        else:
            code = BUILTINS[value]
        U16.pack_into(profile, offset, code)
        return code

    for layer, config in enumerate(project["layers"]):
        start = 8 + layer * LAYER_SIZE
        actions = config["actions"]
        modes = config.get("key_modes", {})
        for index, name in enumerate((*KEY_NAMES, "Encoder kurz")):
            slots = actions.get(name, {})
            if locked_key(layer, name) or (name not in modes and all(v == LEGACY_EMPTY for v in slots.values())):
                continue
            if name == "Encoder kurz" and not encoder_push:
                raise ValueError("Für eine eigene Aktion am Encoder-Druck braucht das Pad die aktuelle Firmware.")
            offset = start + KEY_OFFSET + index * KEY.size
            factory = KEY.unpack_from(base, offset)
            mode = KEY_MODES.index(modes.get(name, inferred_mode(slots))) if index < 10 else 0
            active = (1, 5, 4)[mode]
            profile[offset:offset + KEY.size] = KEY.pack(mode, factory[1], 0, 0, 0, 0, 0, b"")
            label = ""
            for slot in range(active):
                value = slots.get(GESTURES[slot])
                default = factory[2] if slot == 0 and mode != 2 else 0
                if value == DEFAULT_ACTION and mode == 1:
                    default = factory[2 + slot]
                action_offset = offset + 3 + 2 * slot
                code = set_action(action_offset, value, default)
                if not label:
                    if action_offset in pending:
                        label = library[pending[action_offset]]["name"]
                    elif code and value in (None, LEGACY_EMPTY, DEFAULT_ACTION):
                        label = factory[-1].decode("ascii").rstrip("\0")
                    elif code and value != NO_ACTION:
                        label = DISPLAY_SHORTCUTS.get(value, value)
            profile[offset + KEY.size - 12:offset + KEY.size] = packed_text(label or "-", 12)
        for index, name in enumerate(ROTATION_ACTIONS):
            action = actions.get(name, {}).get("1×", LEGACY_EMPTY)
            if action != LEGACY_EMPTY:
                offset = start + ENCODER_OFFSET + index * 2
                set_action(offset, action, U16.unpack_from(base, offset)[0])
        slider = tuple(actions.get(name, {}).get("1×", LEGACY_EMPTY) for name in SLIDER_ACTIONS)
        legacy = actions.get("Regler", {}).get("1×", LEGACY_EMPTY)
        if legacy != LEGACY_EMPTY and slider == (LEGACY_EMPTY, LEGACY_EMPTY):
            slider = (legacy, legacy)
        if slider != (LEGACY_EMPTY, LEGACY_EMPTY):
            profile[start + SLIDER_OFFSET] = 1
            for index, (value, default) in enumerate(zip(slider, level_slider(layer))):
                set_action(start + SLIDER_OFFSET + 4 + index * 2, value, default)

    macros = {}
    if existing is not None:
        for index in range(existing[6]):
            offset, length = struct.unpack_from("<2H", existing, MACRO_TABLE + index * 4)
            macros[index] = existing[MACRO_POOL + offset:MACRO_POOL + offset + length]
    retained = set()
    for layer in range(profile[4]):
        start = 8 + layer * LAYER_SIZE
        codes = []
        for key in range(12):
            codes.extend(KEY.unpack_from(profile, start + KEY_OFFSET + key * KEY.size)[2:7])
        codes.extend(struct.unpack_from("<2H", profile, start + ENCODER_OFFSET))
        codes.extend(struct.unpack_from("<2H", profile, start + SLIDER_OFFSET + 4))
        retained.update(code - MACRO_CODE for code in codes if MACRO_CODE <= code < MACRO_CODE + MACRO_SLOTS)
    encoded = {}
    for offset, identifier in pending.items():
        if identifier not in encoded:
            data = compile_entry(library[identifier])
            index = next((i for i, content in macros.items() if content == data), None)
            if index is None:
                index = next((i for i in range(MACRO_SLOTS) if i not in retained and not macros.get(i)), None)
                if index is None:
                    index = next((i for i in range(MACRO_SLOTS) if i not in retained), None)
                if index is None:
                    raise ValueError(f"Auf dem Pad sind alle {MACRO_SLOTS} Makro-/Snippetplätze belegt.")
                macros[index] = data
            encoded[identifier] = index
            retained.add(index)
        U16.pack_into(profile, offset, MACRO_CODE + encoded[identifier])
    for index in sorted(macros.keys() - retained, reverse=True):
        if sum(map(len, macros.values())) <= MACRO_BYTES:
            break
        del macros[index]
    if sum(map(len, macros.values())) > MACRO_BYTES:
        raise ValueError(f"Die belegten Makros und Snippets überschreiten {MACRO_BYTES} Byte.")
    profile[6] = max(macros, default=-1) + 1
    profile[MACRO_TABLE:MACRO_POOL + MACRO_BYTES] = bytes(MACRO_SLOTS * 4 + MACRO_BYTES)
    used = 0
    for index, data in sorted(macros.items()):
        struct.pack_into("<2H", profile, MACRO_TABLE + index * 4, used, len(data))
        profile[MACRO_POOL + used:MACRO_POOL + used + len(data)] = data
        used += len(data)
    return bytes(profile)
