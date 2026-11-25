// MZ04 stores a palette and two color brightness values per group and layer.
#pragma once

#define CC_NEXT_LAYER_COUNT 8u
#define CC_NEXT_ZONE_COUNT 6u

enum {
    CC_NEXT_KEY = 1, CC_NEXT_ENCODER_TURN = 2, CC_NEXT_ENCODER_PUSH = 4,
    CC_NEXT_SLIDER = 8, CC_NEXT_K0 = 16, CC_NEXT_LAYER = 32
};

static uint32_t cc_next_event_time[CC_NEXT_ZONE_COUNT];
static uint8_t cc_next_event_armed, cc_next_hue;
static uint8_t cc_next_event_hue[CC_NEXT_ZONE_COUNT];
static uint8_t cc_next_event_layer = 255;

static bool cc_next_active(void) {
    return cc_matrix_version() >= 2;
}

static const omp_zone_t *cc_next_frame_zone(uint8_t layer) {
    return &cc_rgb.matrix_zones[8u + layer / OMP_MATRIX_ZONE_COUNT][layer % OMP_MATRIX_ZONE_COUNT];
}

static uint16_t cc_next_tint(uint8_t layer, uint8_t zone) {
    const uint8_t *all = (const uint8_t *)cc_rgb.matrix_zones;
    uint16_t result = 0;
    memcpy(&result, all + CC_NEXT_TINT_OFFSET + (layer * CC_NEXT_ZONE_COUNT + zone) * 2u, 2u);
    return result;
}

static void cc_next_trigger(uint8_t mask) {
    if (cc_matrix_test_view) return;
    cc_live_triggers |= mask;
    if (!cc_next_active() || !cc_rgb_master_enabled) return;
    if (cc_next_event_layer != cc_active) {
        cc_next_event_layer = cc_active;
        cc_next_event_armed = 0;
    }
    const uint32_t now = timer_read32();
    cc_next_hue += 73u;
    for (uint8_t i = 0; i < CC_NEXT_ZONE_COUNT; ++i) {
        if (mask & (1u << i)) {
            cc_next_event_time[i] = now;
            cc_next_event_hue[i] = cc_next_hue;
            cc_next_event_armed |= (1u << i);
        }
    }
}

static uint32_t cc_next_reaction_age(const omp_zone_t *z, uint32_t now, uint8_t *hue) {
    const uint32_t duration = (uint32_t)z->duration * 10u;
    uint32_t age = duration;
    for (uint8_t i = 0; i < CC_NEXT_ZONE_COUNT; ++i) {
        if (!(z->triggers & cc_next_event_armed & (1u << i))) continue;
        const uint32_t elapsed = now - cc_next_event_time[i];
        if (elapsed < age) {
            age = elapsed;
            *hue = cc_next_event_hue[i];
        }
    }
    return age;
}

static uint8_t cc_next_alpha(const omp_zone_t *z, uint8_t position, uint8_t count, uint32_t now) {
    if (!(z->flags & 4u)) return 0;
    uint8_t hue;
    const uint32_t duration = (uint32_t)z->duration * 10u;
    const uint32_t age = cc_next_reaction_age(z, now, &hue);
    if (age >= duration) return 0;
    uint32_t alpha = 255u * (duration - age) / duration;
    const uint8_t effect = z->flags >> 5;
    switch (effect) {
        case 1: // Flash: short bright start
            alpha = age < duration / 5u ? 255u : 0u;
            break;
        case 2: { // Spatial wave of illumination
            const uint8_t head = (uint32_t)age * count / duration;
            const uint8_t distance = position > head ? position - head : head - position;
            alpha = distance < 4u ? alpha * (4u - distance) / 4u : 0u;
            break;
        }
        case 3: alpha = alpha * alpha / 255u; break; // Afterglow
        case 4: alpha = age < duration * 3u / 4u ? 255u : alpha; break;
        default: break; // Impulse, linear fade
    }
    return (uint8_t)alpha;
}

static rgb_t cc_next_color(uint16_t packed, uint8_t mode, uint8_t phase,
                           uint8_t position, uint8_t count) {
    if (!mode) return omp_rgb(packed);
    if (mode == 2) phase += position * 256u / count;
    return hsv_to_rgb((hsv_t){phase, 255, 255});
}

typedef struct {
    uint8_t palette, brightness_a, brightness_b;
} cc_next_colors_t;

static rgb_t cc_next_base(const omp_zone_t *z, uint8_t position, uint8_t count,
                           uint32_t now, bool fixed_zones,
                           uint16_t duration, cc_next_colors_t colors, uint8_t hue) {
    const uint8_t effect = z->effect & 15u;
    if (!(z->flags & 1u) || !z->brightness || !effect) return (rgb_t){0};
    if (z->flags & 2u) position = count - 1u - position;
    static const uint8_t effects[13] = {0, 0, 5, 10, 6, 11, 9, 12, 7, 3, 1, 2, 4};
    if (!fixed_zones) {
        const uint32_t interval = cc_light_interval(z->speed);
        const uint32_t step = now / interval;
        const uint8_t phase = step * 8u + (now % interval) * 8u / interval;
        return omp_effect_pixel(effects[effect], omp_rgb(z->color_a), omp_rgb(z->color_b),
                                z->brightness, position, count, step, phase);
    }
    const uint32_t speed = z->speed;
    const uint32_t rate = 83u + speed * speed * 5917u / 65025u;
    uint32_t period = 1000000u / rate;
    if (duration && period > duration) period = duration;
    const uint32_t elapsed = now % period;
    const uint8_t phase = elapsed * 256u / period;
    uint32_t step = elapsed * count / period;
    if (effect == 8) step += now / period * count;
    if (effect == 6) step = elapsed * (2u * (count - 1u)) / period;
    const uint8_t modes = z->effect >> 4;
    rgb_t a = cc_next_color(z->color_a, modes % 3u, phase, position, count);
    rgb_t b = cc_next_color(z->color_b, modes / 3u, phase + 128u, position, count);
    if (duration && colors.palette == 2)
        a = b = cc_next_color(0, 2, phase, position, count);
    if (duration && colors.palette == 3)
        a = b = cc_next_color(0, 1, hue, position, count);
    a = omp_scale_rgb(a, colors.brightness_a * 255u / 100u);
    b = omp_scale_rgb(b, colors.brightness_b * 255u / 100u);
    if (duration && colors.palette == 0) b = a;
    const uint8_t pattern = effects[effect];
    if (duration && colors.palette == 1 && (position & 1u) &&
        (pattern == 0 || pattern == 5 || pattern == 6 || pattern == 9 || pattern == 12))
        a = b;
    return omp_effect_pixel(effects[effect], a, b, z->brightness, position, count, step, phase);
}

static void cc_next_lighting_tick(uint32_t now) {
    const uint8_t version = cc_matrix_version();
    if (version < 2) return;
    const bool fixed_zones = version >= 3;
    const bool serpentine = cc_rgb.zone_map[5] == cc_default_matrix_zone(5, true);
    const uint8_t layer = cc_active < CC_NEXT_LAYER_COUNT ? cc_active : 1u;
    if (cc_next_event_layer != layer) {
        cc_next_event_layer = layer;
        cc_next_event_armed = 0;
    }
    const uint8_t *color_data = (const uint8_t *)cc_rgb.matrix_zones + CC_NEXT_TINT_OFFSET;
    const uint8_t *palettes = color_data + CC_NEXT_TINT_BYTES;
    const uint8_t shared_palette = fixed_zones ? palettes[layer] : 0;
    cc_next_colors_t matrix_colors = {shared_palette, 100, 100};
    cc_next_colors_t frame_colors = matrix_colors;
    if (version >= 4) {
        const uint8_t *levels = color_data + layer * 4u;
        matrix_colors = (cc_next_colors_t){palettes[layer], levels[0], levels[1]};
        frame_colors = (cc_next_colors_t){palettes[CC_NEXT_LAYER_COUNT + layer], levels[2], levels[3]};
    }
    uint8_t zone_count[CC_NEXT_ZONE_COUNT] = {0};
    uint8_t zone_position[CC_NEXT_ZONE_COUNT] = {0};
    for (uint8_t i = 0; i < CC_RGB_MAIN_LED_COUNT; ++i)
        ++zone_count[cc_rgb.zone_map[i]];
    zone_count[5] = CC_RGB_FRAME_LED_COUNT;
    for (uint8_t index = 0; index < RGBLIGHT_LED_COUNT; ++index) {
        const bool frame = index >= CC_RGB_MAIN_LED_COUNT;
        const cc_next_colors_t colors = frame ? frame_colors : matrix_colors;
        const uint8_t row = index / 5u;
        const uint8_t led = fixed_zones && !frame && serpentine && (row & 1u) ?
                            row * 5u + 4u - index % 5u : index;
        const uint8_t zone = frame ? 5u : cc_rgb.zone_map[led];
        const omp_zone_t *z = frame ? cc_next_frame_zone(layer) :
                             &cc_rgb.matrix_zones[layer][zone];
        uint8_t position = frame ? index - CC_RGB_MAIN_LED_COUNT : index;
        uint8_t count = frame ? CC_RGB_FRAME_LED_COUNT : CC_RGB_MAIN_LED_COUNT;
        const uint8_t local_position = zone_position[zone]++;
        if (!fixed_zones && !frame && !(z->triggers & 64u)) {
            position = local_position;
            count = zone_count[zone];
        }
        rgb_t rgb = {0};
        if (fixed_zones && (z->flags & 4u)) {
            uint8_t hue = 0;
            const uint16_t duration = z->duration * 10u;
            const uint32_t age = cc_next_reaction_age(z, now, &hue);
            if (age < duration)
                rgb = cc_next_base(z, local_position, zone_count[zone], age, true,
                                   duration, colors, hue);
        } else {
            rgb = cc_next_base(z, position, count, now, fixed_zones, 0, colors, 0);
            if (!fixed_zones && (z->flags & 4u) && z->triggers) {
                if (z->flags & 2u) position = count - 1u - position;
                const uint8_t alpha = cc_next_alpha(z, position, count, now);
                if (alpha) {
                    const rgb_t tint = omp_scale_rgb(omp_rgb(cc_next_tint(layer, zone)), z->brightness);
                    if (((z->flags >> 3) & 3u) == 2u) {
                        const rgb_t glow = omp_scale_rgb(tint, alpha);
                        rgb.r = MIN(255u, (uint16_t)rgb.r + glow.r);
                        rgb.g = MIN(255u, (uint16_t)rgb.g + glow.g);
                        rgb.b = MIN(255u, (uint16_t)rgb.b + glow.b);
                    } else {
                        rgb = omp_mix(rgb, tint, alpha);
                    }
                }
            }
        }
        rgblight_driver.set_color(led, rgb.r, rgb.g, rgb.b);
    }
    rgblight_driver.flush();
}
