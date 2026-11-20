"""Persistent 57-LED physical layout for the desktop preview (not firmware data)."""

import json
from math import isfinite

from profile import USER_DATA, atomic_json

LED_COUNT = 57
MAIN_COUNT = 14
FRAME_COUNT = 43
LED_LAYOUT_PATH = USER_DATA / "led-layout.json"
PADDING = 26


def default_positions():
    """LED indices are fixed in the real serial chain, regardless of placement."""
    points = []
    for index in range(MAIN_COUNT):
        points.append([round(0.19 + (index % 7) * 0.62 / 6, 5),
                       0.40 if index < 7 else 0.61])
    for index in range(FRAME_COUNT):
        perimeter = 4 * index / FRAME_COUNT
        edge, t = int(perimeter), perimeter % 1
        if edge == 0:
            x, y = 0.07 + 0.86 * t, 0.11
        elif edge == 1:
            x, y = 0.93, 0.11 + 0.78 * t
        elif edge == 2:
            x, y = 0.93 - 0.86 * t, 0.89
        else:
            x, y = 0.07, 0.89 - 0.78 * t
        points.append([round(x, 5), round(y, 5)])
    return points


def validate_positions(data):
    if not isinstance(data, dict) or data.get("schema") != "omnipad-led-layout" or data.get("version") != 1:
        raise ValueError("Unbekanntes LED-Layoutformat (erwartet omnipad-led-layout v1).")
    if data.get("led_count") != LED_COUNT:
        raise ValueError("LED-Layout muss 57 Positionen für die feste Kette enthalten.")
    points = data.get("positions")
    if not isinstance(points, list) or len(points) != LED_COUNT:
        raise ValueError("Das LED-Layout muss exakt 57 Positionen enthalten.")
    result = []
    for index, point in enumerate(points):
        if (not isinstance(point, list) or len(point) != 2 or
                any(type(number) not in (int, float) or
                    not isfinite(number) or not 0 <= number <= 1 for number in point)):
            raise ValueError(f"Ungültige Position für LED {index} (X/Y je 0 bis 1).")
        result.append([round(float(point[0]), 5), round(float(point[1]), 5)])
    return result


def read_positions(path=LED_LAYOUT_PATH):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default_positions()
    return validate_positions(data)


def write_positions(positions, path=LED_LAYOUT_PATH):
    data = {"schema": "omnipad-led-layout", "version": 1,
            "led_count": LED_COUNT, "positions": positions}
    validate_positions(data)
    atomic_json(path, data)


def to_canvas(point, width, height):
    span_x = max(1, width - 2 * PADDING)
    span_y = max(1, height - 2 * PADDING)
    return PADDING + point[0] * span_x, PADDING + point[1] * span_y


def from_canvas(x, y, width, height):
    span_x = max(1, width - 2 * PADDING)
    span_y = max(1, height - 2 * PADDING)
    return [round(min(1, max(0, (x - PADDING) / span_x)), 5),
            round(min(1, max(0, (y - PADDING) / span_y)), 5)]
