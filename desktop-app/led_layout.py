"""73-LED physical layout: 30 matrix + unchanged 43 Frame, editable preview."""

import json
from math import isfinite

from profile import USER_DATA, atomic_json
from led_zones import (LED_COUNT, MATRIX_COUNT, FRAME_COUNT, matrix_positions)

MAIN_COUNT = MATRIX_COUNT
LED_LAYOUT_PATH = USER_DATA / "led-layout.json"
PADDING = 26


def default_positions():
    """LED indices are fixed in the real serial chain, regardless of placement."""
    points = []
    points.extend(matrix_positions())
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
    if not isinstance(data, dict) or data.get("schema") != "omnipad-led-layout" or data.get("version") not in (1, 2):
        raise ValueError("Unbekanntes LED-Layoutformat.")
    points = data.get("positions")
    # Legacy 57-LED layout: preserve the original frame's physical positions,
    # discard only the superseded 14-LED Main section.
    if data.get("version") == 1 and data.get("led_count") == 57 and isinstance(points, list) and len(points) == 57:
        points = matrix_positions() + points[14:]
    if not isinstance(points, list) or len(points) != LED_COUNT:
        raise ValueError("Es werden 30 Matrix- und 43 Frame-Positionen benötigt.")
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
    data = {"schema": "omnipad-led-layout", "version": 2,
            "led_count": LED_COUNT, "positions": positions}
    validate_positions(data)
    atomic_json(path, data)


def square_bounds(width, height):
    """Centered 1:1 LED arrangement within the available editor canvas."""
    size = max(1, min(width, height) - 24)
    left, top = (width - size) / 2, (height - size) / 2
    return left, top, left + size, top + size


def to_canvas(point, width, height):
    left, top, right, _ = square_bounds(width, height)
    span = max(1, right - left - 2 * PADDING)
    return left + PADDING + point[0] * span, top + PADDING + point[1] * span


def from_canvas(x, y, width, height):
    left, top, right, _ = square_bounds(width, height)
    span = max(1, right - left - 2 * PADDING)
    return [round(min(1, max(0, (x - left - PADDING) / span)), 5),
            round(min(1, max(0, (y - top - PADDING) / span)), 5)]
