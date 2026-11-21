"""Editable OmniPad profiles and the versioned firmware representation."""

from copy import deepcopy
import json
import struct
import unicodedata
from pathlib import Path

MAX_LAYERS = 12
KEY_COUNT = 12
MAX_SNIPPETS = 16
MACRO_POOL_SIZE = 1152
MAX_STEPS_BYTES = MACRO_POOL_SIZE
MAX_FIELDS = 16
PROFILE_VERSION = 2
KEY_STRUCT = struct.Struct("<BH5H12s")
ZONE_STRUCT = struct.Struct("<4B2H2B")
SLIDER_STRUCT = struct.Struct("<4B4H")
FIELD_STRUCT = struct.Struct("<4H6B2H20s")
PROFILE_SIZE = 8 + MAX_LAYERS * 354 + 4 + MAX_FIELDS * FIELD_STRUCT.size + MAX_SNIPPETS * 4 + MACRO_POOL_SIZE
MODES = ["Direkt", "Tap Dance", "Durchschalten"]
EFFECTS = ["Statisch", "Abwechselnd", "Geteilt", "Farbverlauf", "Lauflicht",
           "Atmen", "Komet", "Funkeln", "Regenbogen"]
SLIDER_MODES = ["Aus", "Tasten pro Schritt", "Main-Helligkeit", "Frame-Helligkeit", "Beide Helligkeiten",
                "Windows-Lautstärke absolut (App erforderlich)"]
BINDINGS = ["Text", "Layername", "Tastenbeschriftung", "Reglerwert", "Letzte Taste",
            "Encoder-Modus", "Erkannte Anschläge", "Sensor X", "Sensor Y", "Sensor Z"]
ICONS = ["Zahnrad", "Musik", "Pfeile", "Herz", "Blitz", "Speichern", "Sonne", "Werkzeug"]
MATRIX = [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0), (1, 1), (1, 2), (1, 3), (2, 2), (2, 3)]
ROOT = Path(__file__).resolve().parent.parent
USER_DATA = ROOT / "desktop-app" / "user-data"

BASIC_CODES = {chr(65 + i): 4 + i for i in range(26)}
BASIC_CODES["Y"], BASIC_CODES["Z"] = BASIC_CODES["Z"], BASIC_CODES["Y"]
BASIC_CODES.update({str((i + 1) % 10): 30 + i for i in range(10)})
BASIC_CODES.update({
    "Leer": 0, "Transparent": 1, "Enter": 40, "Escape": 41, "Rücktaste": 42,
    "Tab": 43, "Leertaste": 44, "Entfernen": 76, "Home": 74, "Ende": 77,
    "Bild hoch": 75, "Bild runter": 78, "Rechts": 79, "Links": 80, "Runter": 81, "Hoch": 82,
    "Strg": 224, "Shift": 225, "Alt": 226, "Windows": 227, "AltGr": 230,
    "Lauter": 0xA9, "Leiser": 0xAA, "Stumm": 0xA8, "Play / Pause": 0xAE,
    "Nächster Titel": 0xAB, "Voriger Titel": 0xAC,
    "Mausrad hoch": 0xDA, "Mausrad runter": 0xDB,
    "Kopieren": 0x0106, "Einfügen": 0x0119, "Ausschneiden": 0x011B,
    "Alles auswählen": 0x0104, "Speichern": 0x0116, "Rückgängig": 0x011C,
    "Wiederholen": 0x011D, "Screenshot": 0x0A16,
    "Zoom +": 0x0157, "Zoom −": 0x0156,
})
BASIC_CODES.update({f"F{i}": 57 + i if i <= 12 else 91 + i for i in range(1, 25)})


def label_for_code(code):
    return next((name for name, value in BASIC_CODES.items() if value == code), f"0x{code:04X}")


def ascii_text(value, length):
    value = value.replace("ß", "ss")
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    return text.encode("ascii")[:length - 1].ljust(length, b"\0")


def unpack_text(data):
    return data.split(b"\0", 1)[0].decode("ascii", "replace")


def color565(value):
    r, g, b = (int(value[index:index + 2], 16) for index in (1, 3, 5))
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def colorhex(value):
    return f"#{((value >> 11) & 31) * 255 // 31:02x}{((value >> 5) & 63) * 255 // 63:02x}{(value & 31) * 255 // 31:02x}"


def key_config(code=0, label=""):
    return {"mode": 0, "term": 240, "codes": [code, 0, 0, 0, 0], "label": label}


def zone_config(color="#ce865e"):
    return {"effect": 0, "brightness": 24, "speed": 128, "reverse": False,
            "enabled": True, "color_a": color, "color_b": "#709fba",
            "triggers": 7, "duration": 50}


def encode_lighting(zones):
    if len(zones) != 2:
        raise ValueError("Es werden Main- und Frame-Beleuchtung benötigt.")
    payload = bytearray()
    for zone in zones:
        for name, low, high in (("effect", 0, 8), ("brightness", 0, 64), ("speed", 0, 255),
                                ("triggers", 0, 15), ("duration", 1, 255)):
            integer(zone[name], low, high, f"Beleuchtung {name}")
        flags = int(zone["enabled"]) | (int(zone["reverse"]) << 1)
        payload.extend(ZONE_STRUCT.pack(zone["effect"], zone["brightness"], zone["speed"], flags,
                                        color565(valid_color(zone["color_a"])), color565(valid_color(zone["color_b"])),
                                        zone["triggers"], zone["duration"]))
    return bytes(payload)


def layer_config(index):
    return {"name": f"Layer {index + 1}", "color": "#ce865e",
            "keys": [key_config() for _ in range(KEY_COUNT)], "encoders": [0, 0],
            "slider": {"mode": 0, "reverse": False, "deadband": 4, "step": 64,
                       "low": 0x0156, "high": 0x0157, "min": 0, "max": 1023},
            "lighting": [zone_config(), zone_config("#709fba")]}


def screen_config():
    return {"schema": "omnipad-screen", "version": 1, "width": 320, "height": 240,
            "enabled": False, "background": "#10171f", "fields": []}



def zones_from_via(snapshot):
    import colorsys
    values = snapshot.get("lighting", {})
    def number(channel, value, default):
        return values.get(f"{channel}:{value}", [default])[0]
    def color(channel, value, default):
        hs = values.get(f"{channel}:{value}", default)
        rgb = colorsys.hsv_to_rgb(hs[0] / 255, hs[1] / 255, 1)
        return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
    main = zone_config()
    palette = number(0, 1, 0)
    main.update(brightness=min(64, number(2, 1, 24)), speed=number(0, 4, 128),
                color_a=color(0 if palette else 2, 2 if palette else 4, (14, 255)),
                color_b=color(0, 3, (150, 255)))
    if palette:
        main["effect"] = (0, 0, 1, 2, 4)[min(palette, 4)]
    else:
        effect = number(2, 2, 1)
        main["enabled"] = bool(effect)
        main["effect"] = 0 if effect <= 1 else 5 if effect <= 5 else 8 if effect <= 14 else 4 if effect <= 23 else 3 if effect <= 34 else 7
    frame = zone_config()
    frame.update(enabled=bool(number(0, 5, 1)), brightness=min(64, number(0, 7, 24)),
                 effect=(0, 1, 2, 4, 8, 5)[min(number(0, 6, 0), 5)],
                 speed=number(0, 10, 128), reverse=bool(number(0, 11, 0)),
                 color_a=color(0, 8, (14, 255)), color_b=color(0, 9, (150, 255)))
    return [main, frame]

def default_profile(snapshot=None):
    spec = json.loads((ROOT / "design/layer_system.json").read_text(encoding="utf-8"))
    profile = {"schema": "omnipad-profile", "version": PROFILE_VERSION, "default_layer": 1,
               "layers": [], "snippets": [], "screen": screen_config()}
    count = len(snapshot["layers"]) if snapshot else len(spec["layers"])
    count = min(count, MAX_LAYERS)
    if snapshot:
        while count > len(spec["layers"]):
            if any(any(row) for row in snapshot["layers"][count - 1]) or any(snapshot["encoder_ccw_cw"][count - 1]):
                break
            count -= 1
    for index in range(count):
        layer = layer_config(index)
        if index < len(spec["layers"]):
            preset = spec["layers"][index]
            layer["name"], layer["color"] = preset["name"], preset["accent"]
            for key, source in zip(layer["keys"], preset["keys"]):
                key["label"] = source["label"]
        if snapshot:
            for number, (row, col) in enumerate(MATRIX):
                code = snapshot["layers"][index][row][col]
                layer["keys"][number]["codes"][0] = code
                if index < len(spec["layers"]):
                    expected = spec["layers"][index]["keys"][number]["tap"]
                    if expected.startswith("KC_") and code != BASIC_CODES.get(expected[3:]):
                        layer["keys"][number]["label"] = label_for_code(code)
            layer["encoders"] = list(snapshot["encoder_ccw_cw"][index])
        else:
            for key in layer["keys"]:
                key["codes"][0] = BASIC_CODES.get(key["label"], 0)
        # Preserve the established fast modifier behavior while making it editable.
        for number, code, text in ((4, 225, "SHIFT"), (8, 224, "CTRL"), (9, 226, "ALT")):
            layer["keys"][number] = key_config(code, text)
        layer["keys"][10] = key_config(0, "PUSH")
        layer["keys"][11] = key_config(0, "K0")
        if index == 0:
            layer["slider"]["mode"] = 1
        layer["lighting"][0]["color_a"] = layer["color"]
        if snapshot:
            layer["lighting"] = zones_from_via(snapshot)
        profile["layers"].append(layer)
    if snapshot:
        profile["legacy_via_backup"] = snapshot
        profile["snippets"] = import_via_snippets(snapshot)
    return profile



def import_via_snippets(snapshot):
    raw = bytes.fromhex(snapshot.get("macro_buffer_hex", ""))
    snippets = []
    offset = 0
    for index in range(min(snapshot.get("macro_slots", 0), MAX_SNIPPETS)):
        steps = []
        while offset < len(raw) and raw[offset]:
            value = raw[offset]
            offset += 1
            if value == 1:
                if offset + 1 >= len(raw):
                    raise ValueError("Unvollständiges VIA-Makro.")
                kind = raw[offset]
                offset += 1
                if kind in (1, 2, 3):
                    steps.append({"type": {1: "tap", 2: "down", 3: "up"}[kind], "value": raw[offset]})
                    offset += 1
                elif kind == 4:
                    digits = bytearray()
                    while offset < len(raw) and 48 <= raw[offset] <= 57:
                        digits.append(raw[offset])
                        offset += 1
                    steps.append({"type": "delay", "value": int(digits or b"0")})
                    if offset < len(raw) and raw[offset]:
                        offset += 1
                else:
                    raise ValueError("Unbekannter Schritt im vorhandenen VIA-Makro.")
            else:
                character = chr(value)
                # Existing VIA text used the firmware's US Send String table.
                # Translate its old physical key positions before changing firmware.
                code = us_key(character)
                steps.append({"type": "tap", "value": code})
        offset += 1
        snippets.append({"name": f"VIA-Makro {index + 1}", "steps": steps})
    references = [code for layer in snapshot["layers"] for row in layer for code in row]
    references += [code for layer in snapshot["encoder_ccw_cw"] for code in layer]
    needed = max((code - 0x7700 + 1 for code in references if 0x7700 <= code <= 0x770F), default=0)
    while len(snippets) > needed and not snippets[-1]["steps"]:
        snippets.pop()
    return snippets


def us_key(character):
    if character.lower() in "abcdefghijklmnopqrstuvwxyz":
        return 4 + ord(character.lower()) - ord("a") | (0x0200 if character.isupper() else 0)
    if character in "1234567890":
        return 30 + "1234567890".index(character)
    plain = {" ": 44, "\n": 40, "\t": 43, "-": 45, "=": 46, "[": 47, "]": 48,
             "\\": 49, ";": 51, "'": 52, "`": 53, ",": 54, ".": 55, "/": 56}
    shifted = dict(zip('!@#$%^&*()_+{}|:"~<>?', [30,31,32,33,34,35,36,37,38,39,45,46,47,48,49,51,52,53,54,55,56]))
    if character in plain:
        return plain[character]
    if character in shifted:
        return shifted[character] | 0x0200
    raise ValueError(f"Das vorhandene VIA-Makro enthält ein unbekanntes Zeichen ({ord(character)}).")

def new_field(kind):
    return {"type": kind, "x": 16, "y": 16, "width": 120, "height": 32,
            "binding": 0, "key": 0, "layer": -1, "pressed_only": False,
            "icon": 0, "scale": 2, "foreground": "#f0eee9", "background": "#243341",
            "text": "TEXT"}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def integer(value, minimum, maximum, description):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{description} muss zwischen {minimum} und {maximum} liegen.")
    return value


def valid_color(value):
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise ValueError("Farbe muss im Format #RRGGBB vorliegen.")
    int(value[1:], 16)
    return value


def validate_screen(screen):
    if (screen.get("schema"), screen.get("version"), screen.get("width"), screen.get("height")) != (
            "omnipad-screen", 1, 320, 240):
        raise ValueError("Erwartet wird eine .screen.json für das OmniPad mit 320 × 240 Pixeln.")
    fields = screen["fields"]
    if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
        raise ValueError(f"Ein Displaylayout kann bis zu {MAX_FIELDS} Elemente enthalten.")
    valid_color(screen["background"])
    for field in fields:
        integer(field["type"], 0, 2, "Elementtyp")
        x, y = integer(field["x"], 0, 319, "X"), integer(field["y"], 0, 239, "Y")
        integer(field["width"], 1, 320 - x, "Breite")
        integer(field["height"], 1, 240 - y, "Höhe")
        integer(field["binding"], 0, len(BINDINGS) - 1, "Datenquelle")
        integer(field["key"], 0, KEY_COUNT - 1, "Taste")
        integer(field["layer"], -1, MAX_LAYERS - 1, "Sichtbarer Layer")
        integer(field["icon"], 0, len(ICONS) - 1, "Icon")
        integer(field["scale"], 1, 4, "Schriftgröße")
        valid_color(field["foreground"])
        valid_color(field["background"])
        if not isinstance(field["text"], str):
            raise ValueError("Displaytext muss Text sein.")
    return screen


def compile_snippet(snippet):
    output = bytearray()
    for step in snippet["steps"]:
        kind, value = step["type"], step["value"]
        if kind in ("tap", "down", "up"):
            code = integer(value, 0, 0xFFFF, "Keycode")
            if 0x7700 <= code <= 0x771F:
                raise ValueError("Ein Snippet kann kein weiteres Snippet auslösen.")
            output.extend(struct.pack("<BH", {"tap": 1, "down": 2, "up": 3}[kind], code))
        elif kind == "delay":
            output.extend(struct.pack("<BH", 4, integer(value, 0, 60000, "Pause")))
        elif kind == "text":
            if not isinstance(value, str):
                raise ValueError("Ein Textschritt benötigt Text.")
            # Text is compiled to German-layout key strokes, including umlauts.
            for character in value:
                code = german_key(character)
                output.extend(struct.pack("<BH", 1, code))
                if character in ("~", "^", "`", "´"):
                    output.extend(struct.pack("<BH", 1, 44))
        else:
            raise ValueError(f"Unbekannter Makroschritt {kind}.")
    if len(output) > MAX_STEPS_BYTES:
        raise ValueError(f"„{snippet.get('name', 'Snippet')}“ ist zu lang für den Makrospeicher des Pads.")
    held = {}
    for offset in range(0, len(output), 3):
        kind, value = struct.unpack_from("<BH", output, offset)
        if kind == 2:
            held[value] = held.get(value, 0) + 1
            if sum(held.values()) > 16:
                raise ValueError("Ein Snippet kann höchstens 16 Tasten gleichzeitig halten.")
        elif kind == 3 and held.get(value, 0):
            held[value] -= 1
    if any(held.values()):
        raise ValueError("Im Snippet müssen alle gedrückten Tasten wieder losgelassen werden.")
    return bytes(output)


def german_key(character):
    letters = "abcdefghijklmnopqrstuvwxyz"
    lower = character.lower()
    if lower in letters:
        # QMK letter codes follow US usage positions. German Y and Z are exchanged.
        lower = {"y": "z", "z": "y"}.get(lower, lower)
        code = 4 + letters.index(lower)
        return code | (0x0200 if character.isupper() else 0)
    if character in "1234567890":
        return 30 + "1234567890".index(character)
    plain = {" ": 44, "\n": 40, "\t": 43, "ß": 45, "ü": 47, "ö": 51, "ä": 52,
             "+": 48, "#": 50, ",": 54, ".": 55, "-": 56, "<": 100, "^": 53, "´": 46, "`": 0x022E}
    shifted = dict(zip('!"§$%&/()=?ÜÖÄ*\';:_>', [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45, 47, 51, 52, 48, 50, 54, 55, 56, 100]))
    altgr = {"@": 20, "€": 8, "{": 36, "[": 37, "]": 38, "}": 39, "\\": 45, "|": 100, "~": 48}
    if character in plain:
        return plain[character]
    if character in shifted:
        return shifted[character] | 0x0200
    if character in altgr:
        return altgr[character] | 0x1400
    raise ValueError(f"Zeichen „{character}“ hat noch keine deutsche Tastenabbildung.")


def encode_profile(profile):
    if profile.get("schema") != "omnipad-profile" or profile.get("version") != PROFILE_VERSION:
        raise ValueError("Unbekanntes OmniPad-Profilformat.")
    count = integer(len(profile["layers"]), 1, MAX_LAYERS, "Layeranzahl")
    integer(profile["default_layer"], 0, count - 1, "Startlayer")
    validate_screen(profile["screen"])
    if any(field["layer"] >= count for field in profile["screen"]["fields"]):
        raise ValueError("Das Displaylayout verweist auf einen fehlenden Layer.")
    snippets = profile["snippets"]
    integer(len(snippets), 0, MAX_SNIPPETS, "Snippetanzahl")
    def action(code):
        integer(code, 0, 65535, "Keycode")
        if 0x7700 <= code <= 0x770F and code - 0x7700 >= len(snippets):
            raise ValueError("Eine Aktion verweist auf ein fehlendes Snippet.")
        for start in (0x5200, 0x5220, 0x5260):
            if start <= code <= start + 31 and code - start >= count:
                raise ValueError("Eine Aktion verweist auf einen fehlenden Layer.")

    payload = bytearray(struct.pack("<4s4B", b"OMP2", count, profile["default_layer"], len(snippets), 0))
    layers = profile["layers"] + [layer_config(index) for index in range(count, MAX_LAYERS)]
    for layer in layers:
        payload.extend(struct.pack("<16sH", ascii_text(layer["name"], 16), color565(valid_color(layer["color"]))))
        if len(layer["keys"]) != KEY_COUNT:
            raise ValueError("Jeder Layer benötigt zehn Tasten, Encoder-Druck und K0.")
        for key in layer["keys"]:
            integer(key["mode"], 0, 2, "Tastenverhalten")
            integer(key["term"], 80, 2000, "Tap-Dance-Zeitfenster")
            if len(key["codes"]) != 5:
                raise ValueError("Ungültige Anzahl an Tastenaktionen.")
            for code in key["codes"]:
                action(code)
            payload.extend(KEY_STRUCT.pack(key["mode"], key["term"], *key["codes"], ascii_text(key["label"], 12)))
        if len(layer["encoders"]) != 2:
            raise ValueError("Es werden zwei Encoder-Drehrichtungen benötigt.")
        for code in layer["encoders"]:
            action(code)
        payload.extend(struct.pack("<2H", *layer["encoders"]))
        slider = layer["slider"]
        for name, low, high in (("mode", 0, 5), ("deadband", 0, 64), ("step", 1, 255),
                                ("min", 0, 1022), ("max", 1, 1023),
                                ("low", 0, 65535), ("high", 0, 65535)):
            integer(slider[name], low, high, f"Regler {name}")
        action(slider["low"])
        action(slider["high"])
        if slider["min"] >= slider["max"]:
            raise ValueError("Das Reglerminimum muss kleiner als das Maximum sein.")
        payload.extend(SLIDER_STRUCT.pack(slider["mode"], bool(slider["reverse"]), slider["deadband"],
                                         slider["step"], slider["low"], slider["high"], slider["min"], slider["max"]))
        payload.extend(encode_lighting(layer["lighting"]))
    screen = profile["screen"]
    fields = screen["fields"]
    payload.extend(struct.pack("<2BH", bool(screen["enabled"]), len(fields), color565(screen["background"])))
    for field in fields + [new_field(0) for _ in range(MAX_FIELDS - len(fields))]:
        visibility = 255 if field["layer"] == -1 else field["layer"]
        payload.extend(FIELD_STRUCT.pack(
            field["x"], field["y"], field["width"], field["height"], field["type"], field["binding"],
            field["key"] | (0x80 if field["pressed_only"] else 0), visibility, field["icon"], field["scale"],
            color565(field["foreground"]), color565(field["background"]), ascii_text(field["text"], 20)))
    pool = bytearray()
    for snippet in snippets:
        macro = compile_snippet(snippet)
        payload.extend(struct.pack("<2H", len(pool), len(macro)))
        pool.extend(macro)
    payload.extend(bytes((MAX_SNIPPETS - len(snippets)) * 4))
    if len(pool) > MACRO_POOL_SIZE:
        raise ValueError(f"Die Snippets benötigen {len(pool)} Byte. Auf dem Pad sind {MACRO_POOL_SIZE} Byte verfügbar.")
    payload.extend(pool.ljust(MACRO_POOL_SIZE, b"\0"))
    assert len(payload) == PROFILE_SIZE
    return bytes(payload)


def decode_profile(payload, metadata=None):
    if len(payload) != PROFILE_SIZE or payload[:4] != b"OMP2":
        raise ValueError("Unbekanntes Geräteprofil.")
    _, count, default, snippets, _ = struct.unpack_from("<4s4B", payload)
    result = {"schema": "omnipad-profile", "version": 2, "default_layer": default,
              "layers": [], "snippets": [], "screen": screen_config()}
    offset = 8
    for index in range(MAX_LAYERS):
        layer = layer_config(index)
        name, color = struct.unpack_from("<16sH", payload, offset)
        layer["name"], layer["color"] = unpack_text(name), colorhex(color)
        offset += 18
        for key in layer["keys"]:
            mode, term, *values = KEY_STRUCT.unpack_from(payload, offset)
            key.update(mode=mode, term=term, codes=values[:5], label=unpack_text(values[5]))
            offset += KEY_STRUCT.size
        layer["encoders"] = list(struct.unpack_from("<2H", payload, offset))
        offset += 4
        mode, reverse, deadband, step, low, high, minimum, maximum = SLIDER_STRUCT.unpack_from(payload, offset)
        layer["slider"].update(mode=mode, reverse=bool(reverse), deadband=deadband, step=step,
                                low=low, high=high, min=minimum, max=maximum)
        offset += SLIDER_STRUCT.size
        for zone in layer["lighting"]:
            effect, brightness, speed, flags, a, b, triggers, duration = ZONE_STRUCT.unpack_from(payload, offset)
            zone.update(effect=effect, brightness=brightness, speed=speed, enabled=bool(flags & 1),
                        reverse=bool(flags & 2), color_a=colorhex(a), color_b=colorhex(b), triggers=triggers, duration=duration)
            offset += ZONE_STRUCT.size
        if index < count:
            result["layers"].append(layer)
    screen = result["screen"]
    enabled, elements, background = struct.unpack_from("<2BH", payload, offset)
    screen.update(enabled=bool(enabled), background=colorhex(background))
    offset += 4
    for index in range(MAX_FIELDS):
        x, y, width, height, kind, binding, key, visible, icon, scale, fg, bg, text = FIELD_STRUCT.unpack_from(payload, offset)
        offset += FIELD_STRUCT.size
        if index < elements:
            screen["fields"].append({"type": kind, "x": x, "y": y, "width": width, "height": height,
                                      "binding": binding, "key": key & 127, "layer": -1 if visible == 255 else visible,
                                      "pressed_only": bool(key & 128), "icon": icon, "scale": scale,
                                      "foreground": colorhex(fg), "background": colorhex(bg), "text": unpack_text(text)})
    pool_offset = offset + MAX_SNIPPETS * 4
    for index in range(MAX_SNIPPETS):
        start, length = struct.unpack_from("<2H", payload, offset)
        offset += 4
        if start + length > MACRO_POOL_SIZE or length % 3:
            raise ValueError("Ungültiger Makrospeicher.")
        data = payload[pool_offset + start:pool_offset + start + length]
        if index < snippets:
            steps = [{"type": {1: "tap", 2: "down", 3: "up", 4: "delay"}[kind], "value": value}
                     for kind, value in struct.iter_unpack("<BH", data)]
            result["snippets"].append({"name": f"Snippet {index + 1}", "steps": steps})
    encode_profile(result)
    if metadata:
        try:
            if encode_profile(metadata) == payload:
                return deepcopy(metadata)
        except (KeyError, ValueError, TypeError):
            pass
    return result
