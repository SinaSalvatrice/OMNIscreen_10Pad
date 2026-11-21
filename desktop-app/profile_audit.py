"""Read-only comparison of OmniPad layer and multi-action assignments."""

SLOT_NAMES = ("1x", "2x", "3x", "4x", "Halten")
MODES = ("Direkt", "Tap Dance", "Durchschalten")


def action_differences(expected, actual):
    diffs = []
    if expected["default_layer"] != actual["default_layer"]:
        diffs.append("Startlayer: Entwurf {} / Pad {}".format(expected["default_layer"], actual["default_layer"]))
    a_layers = expected["layers"]
    b_layers = actual["layers"]
    if len(a_layers) != len(b_layers):
        diffs.append("Layeranzahl: Entwurf {} / Pad {}".format(len(a_layers), len(b_layers)))
    for layer_number, (a, b) in enumerate(zip(a_layers, b_layers)):
        label = "Layer {} ({})".format(layer_number + 1, a["name"])
        if a["name"] != b["name"]:
            diffs.append("{}: anderer Name am Pad".format(label))
        for key_number, (ak, bk) in enumerate(zip(a["keys"], b["keys"])):
            prefix = "{} K{}".format(label, key_number + 1)
            if ak["mode"] != bk["mode"]:
                diffs.append("{} Modus: {} / {}".format(prefix, MODES[ak["mode"]], MODES[bk["mode"]]))
            if ak["term"] != bk["term"]:
                diffs.append("{} Tippfenster: {} / {} ms".format(prefix, ak["term"], bk["term"]))
            for slot, (code_a, code_b) in enumerate(zip(ak["codes"], bk["codes"])):
                if code_a != code_b:
                    diffs.append("{} {}: 0x{:04X} / 0x{:04X}".format(prefix, SLOT_NAMES[slot], code_a, code_b))
        for direction, (code_a, code_b) in enumerate(zip(a["encoders"], b["encoders"])):
            if code_a != code_b:
                diffs.append("{} Encoder {}: 0x{:04X} / 0x{:04X}".format(label, ("links", "rechts")[direction], code_a, code_b))
    return diffs
