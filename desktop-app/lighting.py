"""Animation timing and pixel colors for the OmniPad preview."""

from colorsys import hsv_to_rgb

from profile import color565, colorhex

REACTIVE_DURATION_MS = 450
REACTIVE_LEVEL = 32
TWO_COLOR_EFFECTS = (1, 2, 3, 4, 7, 10, 11)


def animation_interval(speed):
    return 20 + (255 - speed) ** 2 // 130


def triangle(phase):
    phase %= 256
    return 2 * min(phase, 255 - phase)


def mix(a, b, blend):
    return tuple((x * (255 - blend) + y * blend) // 255 for x, y in zip(a, b))


def color_channels(color):
    # Preview the same RGB565 colors that will be sent to the pad.
    packed = colorhex(color565(color))
    return tuple(int(packed[i:i + 2], 16) for i in (1, 3, 5))


def led_colors(zone, count, elapsed_ms):
    if not zone["enabled"] or not zone["brightness"]:
        return [(0, 0, 0)] * count

    interval = animation_interval(zone["speed"])
    step, remainder = divmod(elapsed_ms, interval)
    phase = (step * 8 + remainder * 8 // interval) % 256
    a, b = color_channels(zone["color_a"]), color_channels(zone["color_b"])
    effect = zone["effect"]
    colors = []
    for index in range(count):
        position = count - 1 - index if zone["reverse"] else index
        blend, level = 0, zone["brightness"]
        if effect == 1:
            blend = 255 * (position % 2)
        elif effect == 2:
            blend = 255 * (position >= count // 2)
        elif effect == 3:
            blend = position * 255 // max(1, count - 1)
        elif effect == 4:
            blend = 255 * ((position + step) % count >= 4)
        elif effect == 5:
            level = level * (32 + triangle(phase) * 7 // 8) // 255
        elif effect in (6, 12):
            distance = (position - step) % count
            if effect == 12:
                distance = min(distance, (position - step - count // 2) % count)
            tail = min(8, count)
            level = level * (tail - distance) // tail if distance < tail else level // 16
        elif effect == 7:
            blend = 255 * ((position * 37 + step * 13) % 97 < 8)
        elif effect == 9:
            span = count - 1
            head = step % (2 * span)
            head = min(head, 2 * span - head)
            distance = abs(position - head)
            level = level * (4 - distance) // 4 if distance < 4 else level // 16
        elif effect == 10:
            blend = triangle(phase + position * 256 // count)
        elif effect == 11:
            blend = triangle(phase)
        if effect == 8:
            hue = ((position * 256 // count + phase) % 256) / 255
            rgb = tuple(int(channel * 255) for channel in hsv_to_rgb(hue, 1, 1))
        else:
            rgb = mix(a, b, blend)
        # Expand 0–64 device brightness to the canvas' full display range.
        colors.append(tuple(channel * level // 64 for channel in rgb))
    return colors


def reactive_color(base, color, elapsed_ms):
    if elapsed_ms >= REACTIVE_DURATION_MS:
        return base
    tint = tuple(channel * REACTIVE_LEVEL // 64 for channel in color_channels(color))
    blend = (REACTIVE_DURATION_MS - elapsed_ms) * 255 // REACTIVE_DURATION_MS
    return mix(base, tint, blend)
