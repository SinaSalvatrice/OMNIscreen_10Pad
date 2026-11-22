#!/usr/bin/env python3
"""Offline QMK keymap consistency checks; no GitHub Actions or external tools."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
LAYERS = json.loads((ROOT / "design/layer_system.json").read_text(encoding="utf-8"))["layers"]
SRC = (ROOT / "keyboards/icst7789v/keymaps/default/keymap.c").read_text(encoding="utf-8")
HEADER = (ROOT / "keyboards/icst7789v/keymaps/default/generated_layers.h").read_text(encoding="utf-8")
CONTROLS = (ROOT / "keyboards/icst7789v/keymaps/default/cc_controls.h").read_text(encoding="utf-8")
FEATURES = (ROOT / "keyboards/icst7789v/keymaps/default/cc_omni_keymap.h").read_text(encoding="utf-8")
CONFIG = (ROOT / "keyboards/icst7789v/config.h").read_text(encoding="utf-8")

EXPECTED = ["CCSTUDIO", "DEFAULT", "NAV", "TEXT", "SHORTCUT", "MACROS", "SETTINGS", "MEDIA"]
assert [x["id"] for x in LAYERS] == EXPECTED, "Unexpected VIA layer indices"
assert "#define CC_LAYER_COUNT 8" in HEADER, "Missing generated eighth layer"
assert "#define DYNAMIC_KEYMAP_LAYER_COUNT 8" in CONFIG, "VIA count mismatch"
assert "KC_BTN1" not in HEADER + SRC + FEATURES, "Use MS_BTN1, not KC_BTN1"
for i, layer in enumerate(LAYERS):
    expected = f"[{i}] = LAYOUT({', '.join(x['tap'] for x in layer['keys'])}),"
    assert expected in SRC, f"Static QMK keymap mismatches design layer {i} ({layer['id']})"
    enc = f"[{i}] = {{ ENCODER_CCW_CW({layer['encoder']['ccw']}, {layer['encoder']['cw']}) }},"
    assert enc in SRC, f"Encoder mismatch in layer {i}"
assert "static const uint8_t cc_td_dest" in FEATURES, "No hardware Tap Dance"
assert "cc_user_encoder_turn" in FEATURES and "cc_user_encoder_push" in FEATURES
assert "cc_rgb_preview_commit" in FEATURES and "cc_rgb_preview_cancel" in FEATURES
assert "cc_eeprom_reset_update" not in CONTROLS, "Old destructive K0+PUSH reset still present"
assert "cc_internal_confirm = index" in CONTROLS, "Missing destructive action confirmation"
assert "cc_internal_mode = 1;" in CONTROLS, "Missing protected system menu"
print("OK: eight layers, VIA and encoder maps, safety and hardware hooks validated.")
