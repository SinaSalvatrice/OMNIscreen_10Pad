"""Safe Layerverwaltung: preserve logical targets when indexes change.

The firmware encodes layer references as numeric QMK keycodes (TO/MO/TG).
All profile links must be remapped together when layers are reordered/deleted.
"""

from copy import deepcopy
import unicodedata

from bindings import DISABLED, LAYER_ACTIONS

# The wire format has 16 bytes per name, including NUL termination.
MAX_LAYER_NAME_BYTES = 15


def wire_name(name):
    if not isinstance(name, str):
        raise ValueError("Der Layername muss Text sein.")
    return unicodedata.normalize("NFKD", name.replace("ß", "ss")).encode(
        "ascii", "ignore").decode("ascii").strip().upper()


def valid_layer_name(profile, name, exclude=None):
    cleaned = name.strip() if isinstance(name, str) else ""
    normalized = wire_name(cleaned)
    if not normalized:
        raise ValueError("Layername darf nicht leer sein.")
    if len(normalized.encode("ascii")) > MAX_LAYER_NAME_BYTES:
        raise ValueError("Der Layername darf maximal 15 Zeichen auf dem Display haben.")
    used = {wire_name(layer["name"]) for index, layer in enumerate(profile["layers"])
            if index != exclude}
    if normalized in used:
        raise ValueError("Ein Layer mit diesem Namen existiert bereits.")
    return cleaned


def unique_copy_name(profile, source):
    existing = {wire_name(layer["name"]) for layer in profile["layers"]}
    root = wire_name(source) or "LAYER"
    for ordinal in range(1, 1000):
        suffix = " KOPIE" if ordinal == 1 else f" KOPIE{ordinal}"
        candidate = root[:MAX_LAYER_NAME_BYTES - len(suffix)].rstrip() + suffix
        if candidate not in existing:
            return candidate.title()
    raise ValueError("Kein eindeutiger Name für die Layerkopie gefunden.")


def rename_layer(profile, index, name):
    profile["layers"][index]["name"] = valid_layer_name(profile, name, exclude=index)


def duplicate_layer(profile, index, max_layers):
    if len(profile["layers"]) >= max_layers:
        raise ValueError(f"Diese Firmware unterstützt maximal {max_layers} Layer.")
    copied = deepcopy(profile["layers"][index])
    copied["name"] = unique_copy_name(profile, copied["name"])
    profile["layers"].append(copied)
    return len(profile["layers"]) - 1


def _layer_destination(code):
    for base in LAYER_ACTIONS:
        if base <= code < base + 32:
            return base, code - base
    return None


def layer_references(profile, index, *, exclude_layer=None):
    """Count references which need clearing if this layer is removed."""
    actions = 0
    for layer_index, layer in enumerate(profile["layers"]):
        if layer_index == exclude_layer:
            continue
        codes = [code for key in layer["keys"] for code in key["codes"]]
        codes += list(layer["encoders"])
        codes += [layer["slider"]["low"], layer["slider"]["high"]]
        actions += sum(1 for code in codes
                       if (dest := _layer_destination(code)) and dest[1] == index)
    for snippet in profile["snippets"]:
        for step in snippet["steps"]:
            if step["type"] not in ("tap", "down", "up"):
                continue
            dest = _layer_destination(step["value"])
            if dest and dest[1] == index:
                actions += 1
    fields = sum(1 for field in profile["screen"]["fields"] if field["layer"] == index)
    return actions, fields


def _remap_links(profile, old_to_new):
    """Map all external numeric links while preserving their old layer identity.

    Missing destination layers become a deliberate No Action (never a nearby
    layer). Fields scoped to a removed layer are deleted, not shown globally.
    """
    def update_code(code):
        destination = _layer_destination(code)
        if destination is None:
            return code
        base, index = destination
        if index not in old_to_new:
            return DISABLED
        return base + old_to_new[index]

    for layer in profile["layers"]:
        for key in layer["keys"]:
            key["codes"] = [update_code(code) for code in key["codes"]]
        layer["encoders"] = [update_code(code) for code in layer["encoders"]]
        slider = layer["slider"]
        slider["low"] = update_code(slider["low"])
        slider["high"] = update_code(slider["high"])

    for snippet in profile["snippets"]:
        for step in snippet["steps"]:
            if step["type"] in ("tap", "down", "up"):
                step["value"] = update_code(step["value"])

    fields = profile["screen"]["fields"]
    profile["screen"]["fields"] = [
        {**field, "layer": (old_to_new[field["layer"]]
                             if field["layer"] >= 0 else -1)}
        for field in fields if field["layer"] == -1 or field["layer"] in old_to_new
    ]


def move_layer(profile, source, destination):
    count = len(profile["layers"])
    if not (0 <= source < count and 0 <= destination < count):
        raise ValueError("Ungültige Layerposition.")
    if source == destination:
        return source
    order = list(range(count))
    moving = order.pop(source)
    order.insert(destination, moving)
    mapping = {old: new for new, old in enumerate(order)}
    default = profile["default_layer"]
    profile["layers"] = [profile["layers"][old] for old in order]
    profile["default_layer"] = mapping[default]
    _remap_links(profile, mapping)
    return destination


def delete_layer(profile, index):
    count = len(profile["layers"])
    if count < 2:
        raise ValueError("Der letzte Layer kann nicht gelöscht werden.")
    if not (0 <= index < count):
        raise ValueError("Ungültiger Layer.")
    actions, fields = layer_references(profile, index, exclude_layer=index)
    order = [old for old in range(count) if old != index]
    mapping = {old: new for new, old in enumerate(order)}
    default = profile["default_layer"]
    profile["layers"] = [profile["layers"][old] for old in order]
    profile["default_layer"] = (mapping[default] if default in mapping
                                else min(index, len(order) - 1))
    _remap_links(profile, mapping)
    return actions, fields
