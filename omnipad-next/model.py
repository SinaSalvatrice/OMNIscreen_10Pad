"""OmniPad Next: validated, atomic local projects; no firmware writes."""
from __future__ import annotations
import json
import os
from pathlib import Path
from key_actions import BUILTINS, KEY_MODES, LEGACY_EMPTY, LIBRARY_PREFIX, compile_entry, valid_library_id

ROOT = Path(__file__).resolve().parents[1]
LAYER_DATA = json.loads((ROOT / "design/layer_system.json").read_text(encoding="utf-8"))
LAYER_IDS = tuple(x["id"] for x in LAYER_DATA["layers"])
SCHEMA = "omnipad-next-v1"
SUBZONES = ("keys", "slider", "encoder", "k0", "display")
ZONES = ("matrix", *SUBZONES, "frame")
NAMES = {"matrix": "Matrix gesamt (30)", "keys": "Tasten (16)", "slider": "Regler (3)",
         "encoder": "Encoder (2)", "k0": "K0 (2)", "display": "Display (7)",
         "frame": "Rahmen (43)"}
BASE_GROUPS = ("matrix", "frame")
EFFECTS = ("Aus", "Statisch", "Atmen", "Wellenlauf", "Lauflicht", "Farbwechsel",
           "Pingpong", "Doppellauflicht", "Glitzern", "Verlauf", "Streifen",
           "Geteilt", "Wandernde Streifen")
REACTIONS = ("Lichtimpuls", "Aufblitzen", "Welle", "Nachleuchten", "Farbsprung",
             "Komet", "Pingpong", "Glitzern")
COLOR_MODES = ("Fest", "Farbwechsel", "Regenbogen")
REACTION_PALETTES = ("Eine Farbe", "Zwei Farben", "Bunt", "Bei jedem Auslösen neu")
BLENDS = ("Überlagern", "Ersetzen", "Addieren")
TRIGGERS = ("Tastendruck", "Encoder drehen", "Encoder drücken", "Regler bewegen",
            "Zusatzbutton", "Layerwechsel")
MATRIX_TRIGGER_ZONES = dict(zip(TRIGGERS, ("keys", "encoder", "encoder", "slider", "k0", "display")))
GESTURES = ("1×", "2×", "3×", "4×", "Halten")
PROTECTED = {"K0 lang": "Settings", "K0 3×": "Matrixtester",
             "Encoder lang": "Layerliste"}
SCREENS = ("active-layer", "layer-list", "matrix-tester", "settings")


def physical_zone(i):
    if i >= 30:
        return "frame"
    if i < 0:
        raise ValueError(i)
    row, col = divmod(i, 5)
    if (row == 0 and col <= 3) or (row == 1 and col <= 2):
        return "display"
    if col == 4 and row <= 1:
        return "encoder"
    if (row == 1 and col == 3) or (row == 2 and col == 4):
        return "k0"
    if col == 4 and row >= 3:
        return "slider"
    return "keys"


ZONE_LEDS = {zone: tuple(i for i in range(73) if physical_zone(i) == zone)
             for zone in SUBZONES + ("frame",)}
ZONE_LEDS["matrix"] = tuple(range(30))


def new_light(zone="matrix"):
    return {
        "enabled": True, "animation": "Wellenlauf" if zone == "matrix" else "Statisch",
        "color_a": "#55A69D" if zone != "frame" else "#C28B60",
        "color_b": "#283A53" if zone != "frame" else "#624C80",
        "color_a_mode": COLOR_MODES[0], "color_b_mode": COLOR_MODES[0],
        "color_a_brightness": 100, "color_b_brightness": 100,
        "brightness": 48, "speed": 30, "reverse": False,
        "reactive": {"enabled": False, "triggers": list(TRIGGERS) if zone == "matrix" else ["Layerwechsel"],
                     "palette": REACTION_PALETTES[0],
                     "effect": "Lichtimpuls", "color": "#FFE7A8",
                     "blend": "Überlagern", "duration": 400},
    }


def group_reaction(layer, group):
    local = layer["groups"][group]["reactive"]
    previous = layer.get("reaction")
    if previous is None:
        return {"palette": REACTION_PALETTES[0], **local}
    triggers = previous["triggers"]
    if group == "frame":
        # Shared presets only routed layer changes to the frame.
        triggers = [trigger for trigger in triggers if trigger == "Layerwechsel"]
    return {"palette": REACTION_PALETTES[0], **local, **previous, "triggers": list(triggers)}


def new_project():
    layers = []
    for spec in LAYER_DATA["layers"]:
        groups = {zone: new_light(zone) for zone in ZONES}
        for zone in SUBZONES:
            groups[zone]["override"] = False
        assignments = {f"K{i}": {g: "Unbelegt" for g in GESTURES} for i in range(1, 11)}
        for name in ("Encoder links", "Encoder rechts", "Encoder kurz", "Regler", "Zusatzbutton"):
            assignments[name] = {"1×": "Unbelegt"}
        layers.append({"id": spec["id"], "name": spec["name"], "groups": groups,
                       "led_overrides": {}, "actions": assignments})
    return {"schema": SCHEMA, "active_layer": 1, "layers": layers,
            "display_templates": {name: "" for name in SCREENS}, "library": []}


def valid_color(s):
    return (isinstance(s, str) and len(s) == 7 and s.startswith("#") and
            all(c in "0123456789abcdefABCDEF" for c in s[1:]))


def valid_light(s):
    if not isinstance(s, dict):
        return False
    return (type(s.get("enabled")) is bool and s.get("animation") in EFFECTS
            and type(s.get("brightness")) is int and 0 <= s["brightness"] <= 100
            and type(s.get("speed")) is int and 0 <= s["speed"] <= 100
            and type(s.get("reverse")) is bool
            and valid_color(s.get("color_a")) and valid_color(s.get("color_b"))
            and s.get("color_a_mode", COLOR_MODES[0]) in COLOR_MODES
            and s.get("color_b_mode", COLOR_MODES[0]) in COLOR_MODES
            and all(type(s.get(k, 100)) is int and 0 <= s.get(k, 100) <= 100
                    for k in ("color_a_brightness", "color_b_brightness"))
            and valid_reaction(s.get("reactive")))


def valid_reaction(r):
    return (isinstance(r, dict) and type(r.get("enabled")) is bool
            and r.get("effect") in REACTIONS and r.get("blend") in BLENDS
            and type(r.get("duration")) is int and 50 <= r["duration"] <= 2000
            and isinstance(r.get("triggers"), list)
            and all(t in TRIGGERS for t in r["triggers"])
            and valid_color(r.get("color"))
            and r.get("palette", REACTION_PALETTES[0]) in REACTION_PALETTES
            and valid_color(r.get("color_b", r["color"])))


def validate(p):
    if not isinstance(p, dict) or p.get("schema") != SCHEMA:
        raise ValueError("Unbekanntes OmniPad-Projektformat.")
    if type(p.get("active_layer")) is not int or not 0 <= p["active_layer"] < len(LAYER_IDS):
        raise ValueError("Ungültiger aktiver Layer.")
    if not isinstance(p.get("layers"), list) or len(p["layers"]) != len(LAYER_IDS):
        raise ValueError("Das Projekt benötigt alle Firmware-Layer.")
    ids = set()
    entries = p.get("library", [])
    if not isinstance(entries, list):
        raise ValueError("Ungültige Snippetbibliothek.")
    for entry in entries:
        if (not isinstance(entry, dict) or not valid_library_id(entry.get("id")) or entry["id"] in ids
                or not isinstance(entry.get("name"), str) or not entry["name"].strip()
                or not (entry.get("kind") == "text" and isinstance(entry.get("text"), str)
                        or entry.get("kind") == "macro" and isinstance(entry.get("steps"), list)
                        and all(isinstance(step, list) and len(step) == 2 for step in entry["steps"]))):
            raise ValueError("Ungültiger Eintrag in der Snippetbibliothek.")
        compile_entry(entry)
        ids.add(entry["id"])
    choices = set(BUILTINS) | {LEGACY_EMPTY} | {LIBRARY_PREFIX + identifier for identifier in ids}
    for i, layer in enumerate(p["layers"]):
        if not isinstance(layer, dict) or layer.get("id") != LAYER_IDS[i]:
            raise ValueError("Layer-Reihenfolge ist ungültig.")
        groups = layer.get("groups")
        if not isinstance(groups, dict) or any(not valid_light(groups.get(z)) for z in ZONES):
            raise ValueError("Ungültige LED-Einstellungen.")
        if any(type(groups[z].get("override")) is not bool for z in SUBZONES):
            raise ValueError("Ungültige Unterzonen.")
        if "reaction" in layer and not valid_reaction(layer["reaction"]):
            raise ValueError("Ungültige Reaktionseinstellungen.")
        overrides = layer.get("led_overrides")
        if not isinstance(overrides, dict):
            raise ValueError("Ungültige Einzel-LEDs.")
        for key, value in overrides.items():
            if not key.isdigit() or not 0 <= int(key) < 73 or not valid_light(value):
                raise ValueError(f"Ungültige Einzel-LED {key}.")
        if not isinstance(layer.get("actions"), dict):
            raise ValueError("App-Tasten fehlen.")
        if any(k in PROTECTED or k == "K0" for k in layer["actions"]):
            raise ValueError("Systemgesten sind fest reserviert.")
        modes = layer.get("key_modes", {})
        if not isinstance(modes, dict) or any(
            name not in {f"K{i}" for i in range(1, 11)} or mode not in KEY_MODES
            for name, mode in modes.items()
        ):
            raise ValueError("Ungültiger Modus für eine Taste.")
        for gestures in layer["actions"].values():
            if not isinstance(gestures, dict) or any(
                k not in GESTURES or not isinstance(v, str) or v not in choices
                for k, v in gestures.items()
            ):
                raise ValueError("Ungültige App-Belegung.")
    if not isinstance(p.get("display_templates"), dict) or set(p["display_templates"]) != set(SCREENS):
        raise ValueError("Display-Vorlagen fehlen.")
    return p


def save_project(p, path):
    validate(p)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def load_project(path):
    with Path(path).open("r", encoding="utf-8") as f:
        project = validate(json.load(f))
    project.setdefault("library", [])
    for layer in project["layers"]:
        for group in BASE_GROUPS:
            light = layer["groups"][group]
            light["reactive"] = group_reaction(layer, group)
            light.setdefault("color_a_mode", COLOR_MODES[0])
            light.setdefault("color_b_mode", COLOR_MODES[0])
            light.setdefault("color_a_brightness", 100)
            light.setdefault("color_b_brightness", 100)
        layer.pop("reaction", None)
    return project
