// Independent per-layer lighting and the compact display-layout renderer.
#pragma once
#include "cc_editor_icons.h"
#include "rgblight_drivers.h"
#include "color.h"

// The active glow is composited on top of Matrix. Each hardware zone has
// its own timestamp so turning the encoder cannot cancel a key reaction.
static uint32_t omp_light_timer;
static uint32_t omp_light_reaction_at[OMP_MATRIX_ZONE_COUNT];
static uint8_t omp_light_reaction_mask;

static void omp_react(uint8_t zone) {
    if (!cc_rgb_master_enabled || cc_matrix_test_view ||
        !(omp_preview_active || cc_visual_profile_available)) return;
    omp_light_reaction_at[zone] = timer_read32();
    omp_light_reaction_mask |= 1u << zone;
}

static uint8_t omp_step_value(uint8_t value, int8_t step, uint8_t maximum) {
    int16_t next = (int16_t)value + step;
    return next < 0 ? 0 : next > maximum ? maximum : next;
}

static hsv_t omp_hsv(rgb_t color) {
    const uint8_t max = MAX(color.r, MAX(color.g, color.b));
    const uint8_t min = MIN(color.r, MIN(color.g, color.b));
    const uint8_t delta = max - min;
    if (!delta) return (hsv_t){0, 0, max};

    int16_t hue;
    if (max == color.r) hue = 43 * ((int16_t)color.g - color.b) / delta;
    else if (max == color.g) hue = 85 + 43 * ((int16_t)color.b - color.r) / delta;
    else hue = 171 + 43 * ((int16_t)color.r - color.g) / delta;
    return (hsv_t){(uint8_t)hue, delta * 255u / max, max};
}

static bool omp_native_lighting(uint16_t code, bool pressed) {
    if (code < QK_UNDERGLOW_TOGGLE || code > RGB_MODE_TWINKLE) return false;
    if (!pressed || !cc_rgb_master_enabled) return true;
    if (!omp_matrix_override) {
        omp_runtime_matrix = omp_profile.layers[cc_active].zones[0];
        omp_matrix_override = true;
    }
    omp_zone_t *matrix = &omp_runtime_matrix;
    const int8_t direction = get_mods() & MOD_MASK_SHIFT ? -1 : 1;
    switch (code) {
        case QK_UNDERGLOW_TOGGLE: matrix->flags ^= 1u; break;
        case QK_UNDERGLOW_MODE_NEXT:
        case QK_UNDERGLOW_MODE_PREVIOUS: {
            const int8_t step = code == QK_UNDERGLOW_MODE_NEXT ? direction : -direction;
            matrix->effect = (matrix->effect + OMP_EFFECT_COUNT + step) % OMP_EFFECT_COUNT;
            break;
        }
        case QK_UNDERGLOW_VALUE_UP:
        case QK_UNDERGLOW_VALUE_DOWN: {
            const uint8_t level = omp_brightness_override[0] == 255
                ? matrix->brightness : omp_brightness_override[0];
            omp_brightness_override[0] = omp_step_value(
                level, (code == QK_UNDERGLOW_VALUE_UP ? 8 : -8) * direction, RGBLIGHT_LIMIT_VAL);
            break;
        }
        case QK_UNDERGLOW_SPEED_UP:
        case QK_UNDERGLOW_SPEED_DOWN:
            matrix->speed = omp_step_value(matrix->speed, (code == QK_UNDERGLOW_SPEED_UP ? 16 : -16) * direction, 255);
            break;
        case QK_UNDERGLOW_HUE_UP:
        case QK_UNDERGLOW_HUE_DOWN:
        case QK_UNDERGLOW_SATURATION_UP:
        case QK_UNDERGLOW_SATURATION_DOWN: {
            hsv_t color = omp_hsv(omp_rgb(matrix->color_a));
            if (code == QK_UNDERGLOW_HUE_UP) color.h += 8 * direction;
            if (code == QK_UNDERGLOW_HUE_DOWN) color.h -= 8 * direction;
            if (code == QK_UNDERGLOW_SATURATION_UP) color.s = omp_step_value(color.s, 16 * direction, 255);
            if (code == QK_UNDERGLOW_SATURATION_DOWN) color.s = omp_step_value(color.s, -16 * direction, 255);
            const rgb_t rgb = hsv_to_rgb_nocie(color);
            matrix->color_a = ((uint16_t)(rgb.r >> 3) << 11) | ((uint16_t)(rgb.g >> 2) << 5) | (rgb.b >> 3);
            break;
        }
        default: {
            static const uint8_t effects[] = {0, 5, 11, 8, 6, 9, 1, 3, 8, 7};
            matrix->effect = effects[code - RGB_MODE_PLAIN];
            break;
        }
    }
    return true;
}

static void omp_lighting_tick(bool preview) {
    if (timer_elapsed32(omp_light_timer) < 20u) return;
    omp_light_timer = timer_read32();
    const uint8_t layer = cc_active < omp_profile.layer_count ? cc_active : omp_profile.default_layer;
    const omp_zone_t *zones = preview ? omp_preview_zones : omp_profile.layers[layer].zones;
    const bool reactive = zones[0].flags & OMP_LIGHT_REACTIVE;
    const uint32_t now = omp_light_timer;
    rgb_t tint[OMP_MATRIX_ZONE_COUNT];
    uint8_t alpha[OMP_MATRIX_ZONE_COUNT] = {0};
    for (uint8_t zone = 0; zone < OMP_MATRIX_ZONE_COUNT; ++zone) {
        if (!(omp_light_reaction_mask & (1u << zone))) continue;
        uint32_t elapsed = now - omp_light_reaction_at[zone];
        if (elapsed >= OMP_REACTIVE_MS) {
            omp_light_reaction_mask &= ~(1u << zone);
            continue;
        }
        if (!reactive) continue;
        uint16_t packed = preview ? omp_preview_tints[zone] : cc_rgb.matrix_zones[layer][zone].color_b;
        tint[zone] = omp_scale_rgb(omp_rgb(packed), 32);
        alpha[zone] = (OMP_REACTIVE_MS - elapsed) * 255u / OMP_REACTIVE_MS;
    }

    for (uint8_t group = 0; group < 2; ++group) {
        const omp_zone_t *z = !preview && !group && omp_enabled && omp_matrix_override
            ? &omp_runtime_matrix : &zones[group];
        const rgb_t a = omp_rgb(z->color_a), b = omp_rgb(z->color_b);
        const bool enabled = z->flags & 1u;
        uint8_t level = z->brightness;
        if (!preview && omp_enabled && omp_brightness_override[group] != 255)
            level = omp_brightness_override[group];
        const uint16_t interval = cc_light_interval(z->speed);
        const uint32_t step = now / interval;
        const uint8_t phase = step * 8u + (now % interval) * 8u / interval;
        const uint8_t count = group ? CC_RGB_FRAME_LED_COUNT : CC_RGB_MAIN_LED_COUNT;
        const uint8_t first = group ? CC_RGB_FRAME_LED_START : 0;
        for (uint8_t i = 0; i < count; ++i) {
            rgb_t color = {0};
            if (enabled && level) {
                const uint8_t position = z->flags & 2u ? count - 1u - i : i;
                color = omp_effect_pixel(z->effect, a, b, level, position, count, step, phase);
            }
            if (group == 0 && reactive) {
                const uint8_t zone = cc_rgb.zone_map[i];
                if (alpha[zone]) color = omp_mix(color, tint[zone], alpha[zone]);
            }
            rgblight_driver.set_color(first + i, color.r, color.g, color.b);
        }
    }
    rgblight_driver.flush();
}

static uint32_t omp_screen_generation = UINT32_MAX;
static bool omp_field_visible[OMP_FIELDS];
static char omp_field_cached[OMP_FIELDS][24];
static uint16_t omp_clip_x, omp_clip_y, omp_clip_right, omp_clip_bottom;

static void omp_fill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint16_t color) {
    uint16_t right = x + w, bottom = y + h;
    if (x < omp_clip_x) x = omp_clip_x;
    if (y < omp_clip_y) y = omp_clip_y;
    if (right > omp_clip_right) right = omp_clip_right;
    if (bottom > omp_clip_bottom) bottom = omp_clip_bottom;
    if (right > x && bottom > y) lcd_fill(x, y, right - x, bottom - y, color);
}

static void omp_field_text(const omp_field_t *field, const char *value) {
    uint16_t x = field->x, y = field->y;
    uint8_t scale = field->scale;
    for (uint8_t n = 0; value[n] && n < 52; ++n) {
        char ch = value[n];
        if (ch >= 'a' && ch <= 'z') ch -= 'a' - 'A';
        const uint8_t *glyph = cc_glyph(ch);
        if (x + 5u * scale > field->x + field->width) break;
        if (glyph) {
            for (uint8_t col = 0; col < 5; ++col) {
                for (uint8_t row = 0; row < 7; ++row) {
                    uint16_t yy = y + row * scale;
                    if (yy + scale <= field->y + field->height && (glyph[col] & (1u << row))) {
                        omp_fill(x + col * scale, yy, scale, scale, field->foreground);
                    }
                }
            }
        }
        x += 6u * scale;
    }
}

static void omp_field_value(const omp_field_t *f, char buffer[24]) {
    uint8_t key = f->key & 0x7Fu;
    const char *text = f->text;
    switch (f->binding) {
        case 1: text = omp_profile.layers[cc_active].name; break;
        case 2: text = omp_profile.layers[cc_active].keys[key].label; break;
        case 3: snprintf(buffer, 24, "%u / 100", cc_slider_pct); return;
        case 4:
            if (omp_last_key < 10) snprintf(buffer, 24, "K%u", omp_last_key + 1u);
            else snprintf(buffer, 24, "%s", omp_last_key == 10 ? "ENC PUSH" : "K0");
            return;
        case 5: text = cc_display_mode ? "DISPLAY" : "ENCODER"; break;
        case 6: snprintf(buffer, 24, "%u", cc_matrix_hits); return;
        case 7: snprintf(buffer, 24, "%d", cc_adxl.x); return;
        case 8: snprintf(buffer, 24, "%d", cc_adxl.y); return;
        case 9: snprintf(buffer, 24, "%d", cc_adxl.z); return;
        default: break;
    }
    snprintf(buffer, 24, "%s", text);
}

static bool omp_field_for_view(const omp_field_t *f, uint8_t view) {
    if (f->layer >= 0x10 && f->layer <= 0x6F) {
        uint8_t selected_view = (f->layer >> 4) - 1u;
        uint8_t layer = f->layer & 15u;
        return selected_view == view && (layer == 15u || layer == cc_active);
    }
    // Legacy fields belong to the layer-details custom screen.
    return view == 2 && (f->layer == 255 || f->layer == cc_active);
}

static void omp_screen_overlay_render(uint8_t view) {
    if (!omp_enabled || !omp_profile.screen.enabled) return;
    omp_clip_x = 0;
    omp_clip_y = 0;
    omp_clip_right = LCD_W;
    omp_clip_bottom = LCD_H;
    for (uint8_t i = 0; i < omp_profile.screen.count; ++i) {
        const omp_field_t *f = &omp_profile.screen.fields[i];
        if (!omp_field_for_view(f, view) ||
            ((f->key & 0x80u) && !(omp_down_mask & (1u << (f->key & 0x7Fu))))) continue;
        if (f->type == 0) {
            omp_fill(f->x, f->y, f->width, f->height, f->background);
        } else if (f->type == 1) {
            char value[24] = {0};
            omp_field_value(f, value);
            omp_field_text(f, value);
        } else {
            const uint8_t scale = f->scale;
            for (uint8_t row = 0; row < 8; ++row)
                for (uint8_t col = 0; col < 8; ++col)
                    if ((omp_icons[f->icon][row] & (0x80u >> col)) &&
                        (col + 1u) * scale <= f->width && (row + 1u) * scale <= f->height)
                        omp_fill(f->x + col * scale, f->y + row * scale, scale, scale, f->foreground);
        }
    }
}

static void omp_screen_render(void) {
    const omp_screen_t *screen = &omp_profile.screen;
    bool full = omp_screen_invalid || omp_screen_generation != omp_generation;
    uint16_t left = full ? 0 : LCD_W, top = full ? 0 : LCD_H;
    uint16_t right = full ? LCD_W : 0, bottom = full ? LCD_H : 0;
    for (uint8_t i = 0; i < screen->count; ++i) {
        const omp_field_t *f = &screen->fields[i];
        bool visible = omp_field_for_view(f, 2) &&
            (!(f->key & 0x80u) || (omp_down_mask & (1u << (f->key & 0x7Fu))));
        char text[24] = {0};
        if (f->type == 1) omp_field_value(f, text);
        bool changed = visible != omp_field_visible[i] ||
            (visible && memcmp(text, omp_field_cached[i], sizeof(text)));
        if (changed) {
            if (f->x < left) left = f->x;
            if (f->y < top) top = f->y;
            if (f->x + f->width > right) right = f->x + f->width;
            if (f->y + f->height > bottom) bottom = f->y + f->height;
        }
        omp_field_visible[i] = visible;
        memcpy(omp_field_cached[i], text, sizeof(text));
    }
    if (left >= right || top >= bottom) return;
    omp_clip_x = left;
    omp_clip_y = top;
    omp_clip_right = right;
    omp_clip_bottom = bottom;
    omp_fill(left, top, right - left, bottom - top, screen->background);
    for (uint8_t i = 0; i < screen->count; ++i) {
        if (!omp_field_visible[i]) continue;
        const omp_field_t *f = &screen->fields[i];
        if (f->type == 0) omp_fill(f->x, f->y, f->width, f->height, f->background);
        else if (f->type == 1) omp_field_text(f, omp_field_cached[i]);
        else {
            uint8_t scale = f->scale;
            for (uint8_t row = 0; row < 8; ++row) {
                for (uint8_t col = 0; col < 8; ++col) {
                    if ((omp_icons[f->icon][row] & (0x80u >> col)) &&
                        (col + 1u) * scale <= f->width && (row + 1u) * scale <= f->height) {
                        omp_fill(f->x + col * scale, f->y + row * scale, scale, scale, f->foreground);
                    }
                }
            }
        }
    }
    omp_screen_invalid = false;
    omp_screen_generation = omp_generation;
}
