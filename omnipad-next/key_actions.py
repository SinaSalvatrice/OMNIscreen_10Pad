"""Keyboard actions and macro bytecode shared by the editor and the pad upload."""

import re
import struct
from time import monotonic

DEFAULT_ACTION = "Werkseinstellung"
NO_ACTION = "Keine Aktion"
LIBRARY_PREFIX = "library:"
KEY_MODES = ("Direkt", "Tap Dance", "Durchschalten")
MACRO_CODE = 0x7700
MACRO_SLOTS = 16
MACRO_BYTES = 1152
LEGACY_EMPTY = "Unbelegt"

# HID key positions, matching the German layout used by the hardware.
LETTERS = {letter: 4 + index for index, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
LETTERS["Y"], LETTERS["Z"] = LETTERS["Z"], LETTERS["Y"]
NUMBERS = {digit: 30 + index for index, digit in enumerate("1234567890")}
FUNCTIONS = {f"F{i}": 57 + i if i <= 12 else 91 + i for i in range(1, 25)}
NAVIGATION = {
    "Enter": 40, "Escape": 41, "Zurück": 42, "Tab": 43, "Leertaste": 44,
    "Einfügen (Taste)": 73, "Pos1": 74, "Bild hoch": 75, "Entfernen": 76,
    "Ende": 77, "Bild runter": 78, "Pfeil rechts": 79, "Pfeil links": 80,
    "Pfeil runter": 81, "Pfeil hoch": 82,
    "Strg": 224, "Umschalt": 225, "Alt": 226, "Windows": 227, "AltGr": 230,
}
MEDIA = {
    "Play/Pause": 0xAE, "Wiedergabe stoppen": 0xAD, "Nächster Titel": 0xAB,
    "Vorheriger Titel": 0xAC, "Lauter": 0xA9, "Leiser": 0xAA, "Stumm": 0xA8,
    "Vorspulen": 0xBB, "Zurückspulen": 0xBC,
}
SHORTCUTS = {
    "Kopieren": 0x0100 | LETTERS["C"], "Einfügen": 0x0100 | LETTERS["V"],
    "Ausschneiden": 0x0100 | LETTERS["X"], "Alles auswählen": 0x0100 | LETTERS["A"],
    "Speichern": 0x0100 | LETTERS["S"], "Rückgängig": 0x0100 | LETTERS["Z"],
    "Wiederholen": 0x0100 | LETTERS["Y"], "Drucken": 0x0100 | LETTERS["P"],
    "Suchen": 0x0100 | LETTERS["F"], "Screenshot": 0x0A16,
    "Fenster wechseln": 0x042B, "Browser zurück": 0xB6, "Browser vor": 0xB7,
}
DISPLAY_SHORTCUTS = {
    "Kopieren": "CTRL C", "Einfügen": "CTRL V", "Ausschneiden": "CTRL X",
    "Alles auswählen": "CTRL A", "Speichern": "CTRL S", "Rückgängig": "CTRL Z",
    "Wiederholen": "CTRL Y", "Drucken": "CTRL P", "Suchen": "CTRL F",
    "Screenshot": "SNIP", "Fenster wechseln": "ALT TAB", "Browser zurück": "WEB BACK",
    "Browser vor": "WEB NEXT",
}
MOUSE = {"Linksklick": 0xD1, "Rechtsklick": 0xD2,
         "Mausrad hoch": 0xDA, "Mausrad runter": 0xDB}
BUILTINS = {DEFAULT_ACTION: None, NO_ACTION: 0, **LETTERS, **NUMBERS, **FUNCTIONS,
            **NAVIGATION, **MEDIA, **SHORTCUTS, **MOUSE}
MODIFIERS = {"Control": (224, 228), "Shift": (225, 229), "Alt": (226, 230),
             "Win": (227, 231), "Super": (227, 231), "Meta": (227, 231)}
KEYSYMS = {
    "Return": 40, "KP_Enter": 40, "Escape": 41, "BackSpace": 42, "Tab": 43,
    "ISO_Left_Tab": 43, "space": 44, "Print": 70, "Pause": 72, "Insert": 73,
    "Home": 74, "Prior": 75, "Delete": 76, "End": 77, "Next": 78, "Right": 79,
    "Left": 80, "Down": 81, "Up": 82, "ISO_Level3_Shift": 230,
    "KP_Divide": 84, "KP_Multiply": 85, "KP_Subtract": 86, "KP_Add": 87,
    "KP_Decimal": 99, "KP_0": 98,
    **{f"KP_{i}": 88 + i for i in range(1, 10)},
    **{f"{name}_{side}": codes[index] for name, codes in MODIFIERS.items()
       for index, side in enumerate(("L", "R"))},
}
PLAIN = {" ": 44, "\n": 40, "\t": 43, "ß": 45, "ü": 47, "ö": 51, "ä": 52,
         "+": 48, "#": 50, ",": 54, ".": 55, "-": 56, "<": 100,
         "^": 53, "´": 46, "`": 0x022E}
SHIFTED = dict(zip('!"§$%&/()=?ÜÖÄ*\';:_>', (30, 31, 32, 33, 34, 35, 36, 37, 38,
                                             39, 45, 47, 51, 52, 48, 50, 54, 55, 56, 100)))
ALTGR = {"@": 20, "€": 8, "{": 36, "[": 37, "]": 38, "}": 39,
         "\\": 45, "|": 100, "~": 48}
SYMBOLS = {
    "comma": ",", "period": ".", "minus": "-", "plus": "+", "numbersign": "#",
    "less": "<", "greater": ">", "ssharp": "ß", "adiaeresis": "ä", "odiaeresis": "ö",
    "udiaeresis": "ü", "asterisk": "*", "semicolon": ";", "colon": ":",
    "underscore": "_", "exclam": "!", "question": "?", "at": "@", "backslash": "\\",
    "slash": "/", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "braceleft": "{", "braceright": "}", "parenleft": "(", "parenright": ")",
    "bar": "|", "quotedbl": '"', "apostrophe": "'", "ampersand": "&",
    "percent": "%", "EuroSign": "€", "dollar": "$",
}


def german_key(char):
    if char.upper() in LETTERS:
        return LETTERS[char.upper()] | (0x0200 if char.isupper() else 0)
    if char in NUMBERS:
        return NUMBERS[char]
    if char in PLAIN:
        return PLAIN[char]
    if char in SHIFTED:
        return SHIFTED[char] | 0x0200
    if char in ALTGR:
        return ALTGR[char] | 0x1400
    raise ValueError(f"„{char}“ lässt sich mit dem deutschen Tastaturlayout nicht eingeben.")


def compile_entry(entry):
    """Encode one text snippet or recorded key sequence in existing OMP2 bytecode."""
    if entry["kind"] == "text":
        steps = []
        for char in entry["text"].replace("\r\n", "\n").replace("\r", "\n"):
            steps.append((1, german_key(char)))
            if char in ("~", "^", "`", "´"):
                steps.append((1, 44))  # Flush the German layout's dead key.
    else:
        steps = entry["steps"]
    if not steps:
        raise ValueError("Der Eintrag ist leer.")
    if len(steps) * 3 > MACRO_BYTES:
        raise ValueError(f"Der Eintrag ist zu lang. Das Pad hat {MACRO_BYTES} Byte Makrospeicher.")
    payload = bytearray()
    held = set()
    for op, value in steps:
        if type(op) is not int or type(value) is not int or op not in (1, 2, 3, 4):
            raise ValueError("Ungültiger Makroschritt.")
        if op == 4:
            if not 1 <= value <= 60000:
                raise ValueError("Makropausen müssen zwischen 1 und 60000 ms liegen.")
        elif not 4 <= value <= 0x1FFF:
            raise ValueError("Ein Makro kann nur Tasten und Tastenkombinationen abspielen.")
        if op == 2:
            if value in held or len(held) >= 16:
                raise ValueError("Ungültige gehaltene Tasten im Makro.")
            held.add(value)
        elif op == 3:
            if value not in held:
                raise ValueError("Das Makro lässt eine Taste los, die es nicht gedrückt hat.")
            held.remove(value)
        payload.extend(struct.pack("<BH", op, value))
    if held:
        raise ValueError("Im Makro muss jede gedrückte Taste wieder losgelassen werden.")
    return bytes(payload)


def recorded_code(keysym, char=""):
    known = KEYSYMS.get(keysym) or FUNCTIONS.get(keysym) or LETTERS.get(keysym.upper())
    if known:
        return known
    symbol = SYMBOLS.get(keysym, char or keysym)
    try:
        return german_key(symbol) if len(symbol) == 1 else None
    except ValueError:
        return None


class MacroCapture:
    """Record only events delivered to the explicit Tk recording control."""

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.steps = []
        self.pressed = {}
        self.last = None

    def event(self, pressed, keysym, keycode, char=""):
        if pressed:
            if keycode in self.pressed:
                return
            code = recorded_code(keysym, char)
            if code is None:
                raise ValueError(f"Taste „{keysym}“ wird nicht unterstützt.")
            if code in self.pressed.values():
                return
        else:
            if keycode not in self.pressed:
                return
            code = self.pressed[keycode]
        now = self.clock()
        elapsed = min(60000, round((now - self.last) * 1000)) if self.last is not None else 0
        pending = len(self.pressed) + (1 if pressed else -1)
        if pending > 16 or len(self.steps) + int(elapsed >= 20) + 1 + pending > MACRO_BYTES // 3:
            raise ValueError("Aufnahmelimit erreicht.")
        if elapsed >= 20:
            self.steps.append((4, elapsed))
        self.steps.append((2 if pressed else 3, code))
        if pressed:
            self.pressed[keycode] = code
        else:
            del self.pressed[keycode]
        self.last = now

    def finish(self):
        self.steps.extend((3, code) for code in reversed(tuple(self.pressed.values())))
        self.pressed.clear()
        return [list(step) for step in self.steps]


def step_label(step):
    op, value = step
    if op == 4:
        return f"Pause · {value} ms"
    name = next((name for name, code in BUILTINS.items() if code == value), f"0x{value:04X}")
    return f"{('Tippen', 'Drücken', 'Loslassen')[op - 1]} · {name}"


def valid_library_id(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{32}", value) is not None
