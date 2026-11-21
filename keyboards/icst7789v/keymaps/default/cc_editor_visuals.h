// Independent per-layer lighting and the compact display-layout renderer.
#pragma once
#include "cc_editor_icons.h"
#include "rgblight_drivers.h"
#include "color.h"
#include "process_underglow.h"

static uint16_t omp_light_timer;
static uint8_t omp_phase;

static bool omp_native_lighting(uint16_t code, bool pressed) {
    if (code < QK_UNDERGLOW_TOGGLE || code > RGB_MODE_TWINKLE) return false;
    keyrecord_t record = {.event = {.pressed = pressed}};
    process_underglow(code, &record);
    if (pressed) {
        omp_qmk_lighting_override = true;
        omp_qmk_effect = (rgblight_get_mode() - 1u) % 9u;
        rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);
    }
    return true;
}

static rgb_t omp_rgb(uint16_t packed) {
    return (rgb_t){
        .r = ((packed >> 11) & 31u) * 255u / 31u,
        .g = ((packed >> 5) & 63u) * 255u / 63u,
        .b = (packed & 31u) * 255u / 31u,
    };
}

static rgb_t omp_mix(rgb_t a, rgb_t b, uint8_t blend) {
    return (rgb_t){
        .r = ((uint16_t)a.r * (255u - blend) + (uint16_t)b.r * blend) / 255u,
        .g = ((uint16_t)a.g * (255u - blend) + (uint16_t)b.g * blend) / 255u,
        .b = ((uint16_t)a.b * (255u - blend) + (uint16_t)b.b * blend) / 255u,
    };
}

static void omp_lighting_tick(bool preview) {
    if (timer_elapsed(omp_light_timer) < 30u) return;
    omp_light_timer = timer_read();
    ++omp_phase;
    // QMK's main animation must not overwrite either editor-controlled zone.
    if (!preview) {
        if (!omp_qmk_lighting_override && !rgblight_is_enabled()) rgblight_enable_noeeprom();
        if (rgblight_get_mode() != RGBLIGHT_MODE_STATIC_LIGHT) rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);
    }
    for (uint8_t zone = 0; zone < 2; ++zone) {
        const omp_zone_t *z = preview ? &omp_preview_zones[zone] : &omp_profile.layers[cc_active].zones[zone];
        uint8_t count = zone ? CC_RGB_FRAME_LED_COUNT : CC_RGB_MAIN_LED_COUNT;
        uint8_t start = zone ? CC_RGB_FRAME_LED_START : 0;
        uint8_t brightness = preview || omp_brightness_override[zone] == 255 ? z->brightness : omp_brightness_override[zone];
        uint16_t phase = ((uint32_t)timer_read() * (z->speed + 16u) / 1024u);
        uint16_t elapsed = timer_elapsed(omp_trigger_at);
        uint16_t duration = (uint16_t)z->duration * 10u;
        bool triggered = (z->triggers & omp_trigger) && elapsed < duration;
        uint8_t effect = z->effect;
        bool enabled = z->flags & 1u;
        rgb_t a = omp_rgb(z->color_a), b = omp_rgb(z->color_b);
        if (!preview && zone == 0 && omp_qmk_lighting_override) {
            brightness = rgblight_get_val();
            if (brightness > RGBLIGHT_LIMIT_VAL) brightness = RGBLIGHT_LIMIT_VAL;
            enabled = rgblight_is_enabled();
            effect = omp_qmk_effect;
            a = hsv_to_rgb((hsv_t){rgblight_get_hue(), rgblight_get_sat(), 255});
        }
        for (uint8_t led = 0; led < count; ++led) {
            uint8_t position = (z->flags & 2u) ? count - 1u - led : led;
            uint8_t wave = 0;
            uint8_t level = brightness;
            switch (effect) {
                case 1: wave = (position & 1u) ? 255 : 0; break;
                case 2: wave = position >= count / 2u ? 255 : 0; break;
                case 3: wave = (uint16_t)position * 255u / (count - 1u); break;
                case 4: wave = ((position + phase) % count) < 4u ? 0 : 255; break;
                case 5: {
                    uint8_t breath = phase & 255u;
                    wave = breath < 128u ? breath * 2u : (255u - breath) * 2u;
                    level = (uint16_t)brightness * (32u + wave * 7u / 8u) / 255u;
                    wave = 0;
                    break;
                }
                case 6: {
                    uint8_t distance = (position + count - phase % count) % count;
                    wave = 0;
                    level = distance < 8u ? (uint16_t)brightness * (8u - distance) / 8u : brightness / 16u;
                    break;
                }
                case 7: wave = ((uint16_t)position * 37u + phase * 13u) % 97u < 8u ? 255 : 0; break;
                default: break;
            }
            rgb_t color = omp_mix(a, b, wave);
            if (effect == 8) color = hsv_to_rgb((hsv_t){(uint8_t)(position * 256u / count + phase), 255, 255});
            if (triggered) {
                uint8_t center = omp_trigger == 2 ? omp_encoder_position % count :
                    (omp_last_key < OMP_KEYS ? (uint16_t)omp_last_key * count / OMP_KEYS : 0);
                int16_t step = elapsed / 35u;
                if (omp_trigger == 2 && omp_encoder_direction < 0) step = -step;
                int16_t head = (center + step + count * 8u) % count;
                uint8_t distance = (position + count - head) % count;
                if (distance < 6) {
                    uint8_t blend = (uint32_t)(duration - elapsed) * (6u - distance) * 255u / (duration * 6u);
                    color = omp_mix(color, b, blend);
                }
            }
            if (!enabled) level = 0;
            rgblight_driver.set_color(start + led, (uint16_t)color.r * level / 255u,
                (uint16_t)color.g * level / 255u, (uint16_t)color.b * level / 255u);
        }
    }
    if (preview) rgblight_driver.flush();
    else rgblight_set(); // One flush for the complete chain.
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
