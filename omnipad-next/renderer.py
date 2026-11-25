"""Deterministic rendering for Matrix and Frame with fixed reactive zones."""
from __future__ import annotations

from colorsys import hsv_to_rgb
from dataclasses import dataclass
import math

from model import BASE_GROUPS, MATRIX_TRIGGER_ZONES, ZONE_LEDS, group_reaction, physical_zone

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Pulse:
    trigger: str
    at: float
    layer: int
    hue: float = 0.


def color(value: str) -> RGB:
    return tuple(int(value[j:j + 2], 16) for j in (1, 3, 5))


def rainbow(hue: float) -> RGB:
    return tuple(round(x * 255) for x in hsv_to_rgb(hue % 1.0, 1, 1))


def mix(a: RGB, b: RGB, alpha: float) -> RGB:
    alpha = max(0., min(1., alpha))
    return tuple(round(x * (1 - alpha) + y * alpha) for x, y in zip(a, b))


def scale(c: RGB, amount: float) -> RGB:
    return tuple(round(x * amount) for x in c)


def animation_color(light, channel, phase, position, count):
    mode = light.get(f"color_{channel}_mode", "Fest")
    if mode == "Fest":
        return color(light[f"color_{channel}"])
    if channel == "b":
        phase += .5
    if mode == "Regenbogen":
        phase += position / count
    return rainbow(phase)


def base_color(light, position, count, t, *, palette=None, event_hue=0, duration=0):
    effect = light["animation"]
    if not light["enabled"] or effect == "Aus":
        return 0, 0, 0
    if light["reverse"]:
        position = count - position - 1
    level = light["brightness"] / 100
    rate = 1 / 12 + (light["speed"] / 100) ** 2 * (6 - 1 / 12)
    phase = t * (max(rate, 1 / duration) if duration else rate)
    a = animation_color(light, "a", phase, position, count)
    b = animation_color(light, "b", phase, position, count)
    if palette == "Eine Farbe":
        b = a
    elif palette == "Bunt":
        a = b = rainbow(phase + position / count)
    elif palette == "Bei jedem Auslösen neu":
        a = b = rainbow(event_hue)
    a = scale(a, light.get("color_a_brightness", 100) / 100)
    b = a if palette == "Eine Farbe" else scale(b, light.get("color_b_brightness", 100) / 100)
    head = phase * count % count
    blend = float(palette == "Zwei Farben" and bool(position % 2))
    if effect == "Atmen":
        level *= .125 + .875 * (1 - abs(2 * (phase % 1) - 1))
    elif effect == "Farbwechsel":
        blend = (1 - math.cos(phase * math.tau)) / 2
    elif effect == "Wellenlauf":
        blend = (math.sin((phase - position / count) * math.tau) + 1) / 2
    elif effect in ("Lauflicht", "Doppellauflicht"):
        distance = (position - int(head)) % count
        if effect == "Doppellauflicht":
            distance = min(distance, (distance - count // 2) % count)
        level *= (8 - distance) / 8 if distance < 8 else 1 / 16
    elif effect == "Pingpong":
        span = count - 1
        sweep = phase * 2 % 2
        distance = abs(position - span * min(sweep, 2 - sweep))
        level *= (4 - distance) / 4 if distance < 4 else 1 / 16
    elif effect == "Glitzern":
        blend = float((position * 37 + int(phase * count) * 13) % 97 < 8)
    elif effect == "Verlauf":
        blend = position / max(1, count - 1)
    elif effect == "Streifen":
        blend = float(position % 2)
    elif effect == "Geteilt":
        blend = float(position >= count // 2)
    elif effect == "Wandernde Streifen":
        blend = float((position + int(head)) % count >= 4)
    return scale(mix(a, b, blend), level)


def render(project: dict, layer: int, now: float, events: list[Pulse]) -> list[RGB]:
    config = project["layers"][layer]
    groups = config["groups"]
    reactions = {group: group_reaction(config, group) for group in BASE_GROUPS}
    active = {}
    for event in events:
        if event.layer != layer:
            continue
        age = now - event.at
        for group, reaction in reactions.items():
            if (reaction["enabled"] and 0 <= age < reaction["duration"] / 1000
                    and event.trigger in reaction["triggers"]):
                zone = "frame" if group == "frame" else MATRIX_TRIGGER_ZONES[event.trigger]
                active[zone] = event
    out = []
    for index in range(73):
        zone = physical_zone(index)
        group = "frame" if index >= 30 else "matrix"
        light = groups[group]
        reaction = reactions[group]
        if reaction["enabled"]:
            event = active.get(zone)
            if event is None:
                out.append((0, 0, 0))
                continue
            leds = ZONE_LEDS[zone]
            value = base_color(light, leds.index(index), len(leds), now - event.at,
                               palette=reaction["palette"], event_hue=event.hue,
                               duration=reaction["duration"] / 1000)
        else:
            position, count = (index, 30) if index < 30 else (index - 30, 43)
            value = base_color(light, position, count, now)
        out.append(value)
    return out


def hexrgb(rgb: RGB) -> str:
    return "#%02X%02X%02X" % rgb
