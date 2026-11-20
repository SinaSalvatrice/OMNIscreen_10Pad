"""Shared layer and screen assignments stored in the key's existing action slots."""

from profile import label_for_code

SLOTS = (
    ("Beim Drücken",),
    ("1× tippen", "2× tippen", "3× tippen", "4× tippen", "Halten"),
    ("Schritt 1", "Schritt 2", "Schritt 3", "Schritt 4"),
)

LAYER_ACTIONS = {
    0x5200: "Layer wechseln",
    0x5220: "Layer während des Haltens",
    0x5260: "Layer ein/aus",
}

DISPLAY_ACTIONS = {
    0x7E40: "Layer-Ansicht",
    0x7E41: "Eigenes Displaylayout",
    0x7E42: "Matrixmodus umschalten",
    0x7E43: "Modulmenü",
    0x7E44: "Startlayer anzeigen",
    0x7E45: "Display-/Encoder-Modus wechseln",
    0x7E46: "Hilfe",
    0x7E47: "Farbfelder",
    0x7E48: "Clear EEPROM …",
}
DISABLED = 0x7E49
K0_DEFAULTS = (0x7E45, 0x7E44, 0x7E42, 0, 0x7E43)


def layer_action(code):
    for base in LAYER_ACTIONS:
        if base <= code < base + 32:
            return base, code - base
    return None


def action_name(profile, code):
    if code in DISPLAY_ACTIONS:
        return DISPLAY_ACTIONS[code]
    if code == DISABLED:
        return "Keine Aktion"
    target = layer_action(code)
    if target:
        kind, layer = target
        layers = profile["layers"]
        destination = layers[layer]["name"] if layer < len(layers) else "Fehlender Layer"
        return f"{LAYER_ACTIONS[kind]} · {layer + 1} {destination}"
    if 0x7700 <= code < 0x7710:
        index = code - 0x7700
        snippets = profile["snippets"]
        if index < len(snippets):
            return f"Snippet · {snippets[index]['name']}"
    return label_for_code(code)


def default_k0(key, index):
    return index == 11 and all(code <= 1 for code in key["codes"][:len(SLOTS[key["mode"]])])


def change_key_mode(key, index, mode):
    if mode == 1 and default_k0(key, index) and key["mode"] != mode:
        key["codes"] = list(K0_DEFAULTS)
    key["mode"] = mode


def set_key_action(key, index, mode, slot, code):
    target = layer_action(code)
    if target and target[0] == 0x5220 and not (mode == 0 or mode == 1 and slot == 4):
        raise ValueError("„Layer während des Haltens“ gehört zu Direkt oder zur Geste Halten.")
    if mode == 1 and default_k0(key, index):
        key["codes"] = list(K0_DEFAULTS)
    key["mode"] = mode
    key["codes"][slot] = DISABLED if index == 11 and code == 0 else code


def action_for_slot(key, index, mode, slot):
    if mode == 1 and default_k0(key, index):
        return K0_DEFAULTS[slot]
    return key["codes"][slot]


def layer_choices(profile):
    return [(base + index, f"{caption} · {index + 1} {layer['name']}")
            for base, caption in LAYER_ACTIONS.items() for index, layer in enumerate(profile["layers"])]


def requires_device_actions(profile):
    for layer in profile["layers"]:
        codes = [code for key in layer["keys"] for code in key["codes"]]
        codes.extend((*layer["encoders"], layer["slider"]["low"], layer["slider"]["high"]))
        if any(code in DISPLAY_ACTIONS or code == DISABLED for code in codes):
            return True
    for snippet in profile["snippets"]:
        if any(step["type"] in ("tap", "down", "up") and (step["value"] in DISPLAY_ACTIONS or step["value"] == DISABLED)
               for step in snippet["steps"]):
            return True
    return False
