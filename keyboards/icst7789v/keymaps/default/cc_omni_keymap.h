// Standalone hardware-first keymap; the OmniPad app remains optional.
// Included from cc_controls.h after cc_runtime.h and the RGB/OMP modules.
#pragma once
#include "mousekey.h"
// Seven built-in slots per bank work without a configured VIA/OMP profile.

#define CC_MEDIA_LAYER 7
#define CC_RGB_LAYER 6
#define CC_TEXT_LAYER 3
#define CC_NAV_LAYER 2
#define CC_MACRO_LAYER 5

typedef struct {
    bool down, second, pending, held;
    uint8_t origin;
    uint16_t started, released, code;
} cc_td_t;
static cc_td_t cc_td[CC_KEY_COUNT];
static const uint8_t cc_td_dest[CC_KEY_COUNT] = {1, 2, 3, 4, 255, 7, 7, 5, 0, 255};
static uint8_t cc_macro_bank;
static bool cc_macro_recording;
static uint8_t cc_macro_recorded[48];
static uint8_t cc_macro_recorded_count;
static bool cc_macro_playing;
static bool cc_enc_down, cc_enc_moved, cc_nav_alt_down;
static uint16_t cc_nav_alt_at;
static bool cc_rgb_preview_active;
static cc_rgb_settings_t cc_rgb_before;
static uint8_t cc_rgb_mode_before, cc_rgb_hue_before, cc_rgb_sat_before, cc_rgb_val_before;
static uint8_t cc_rgb_zone;
static uint8_t cc_tap_term_index = 1; // 180/220/260/320 ms
static uint8_t cc_display_timeout_index; // 0/30/60/300 seconds
static uint8_t cc_display_start_index; // layers/home
static uint32_t cc_activity_at;
static bool cc_backlight_awake = true;

static uint16_t cc_tap_term(void) {
    static const uint16_t terms[4] = {180, 220, 260, 320};
    return terms[cc_tap_term_index & 3];
}
static void cc_mouse_left_click(void) {
    mousekey_on(MS_BTN1); mousekey_send();
    mousekey_off(MS_BTN1); mousekey_send();
}
static void cc_ui_activity(void) {
    cc_activity_at = timer_read32();
    if (!cc_backlight_awake) {
        cc_backlight_awake = true;
        gpio_write_pin_high(LCD_BL);
    }
}
static void cc_ui_config_load(void) {
    uint32_t value = eeconfig_read_kb();
    if ((value >> 24) == 0xC7u) {
        cc_tap_term_index = (value >> 16) & 3u;
        cc_display_timeout_index = (value >> 8) & 3u;
        cc_display_start_index = value & 1u;
    }
    cc_ui_activity();
}
static void cc_ui_config_save(void) {
    eeconfig_update_kb((0xC7u << 24) | ((uint32_t)cc_tap_term_index << 16) |
                       ((uint32_t)cc_display_timeout_index << 8) | cc_display_start_index);
}
static void cc_ui_timeout_tick(void) {
    static const uint32_t seconds[4] = {0, 30, 60, 300};
    const uint32_t timeout = seconds[cc_display_timeout_index & 3u];
    if (timeout && cc_backlight_awake &&
        timer_elapsed32(cc_activity_at) >= timeout * 1000u) {
        cc_backlight_awake = false;
        gpio_write_pin_low(LCD_BL);
    }
}

static void cc_rgb_preview_begin(void) {
    cc_rgb_before = cc_rgb;
    cc_rgb_mode_before = rgblight_get_mode();
    cc_rgb_hue_before = rgblight_get_hue();
    cc_rgb_sat_before = rgblight_get_sat();
    cc_rgb_val_before = rgblight_get_val();
    cc_rgb_preview_active = true;
    cc_rgb_zone = 0;
}
static void cc_rgb_preview_cancel(void) {
    if (!cc_rgb_preview_active) return;
    cc_rgb = cc_rgb_before;
    rgblight_mode_noeeprom(cc_rgb_mode_before);
    rgblight_sethsv_noeeprom(cc_rgb_hue_before, cc_rgb_sat_before, cc_rgb_val_before);
    cc_main_dirty = cc_frame_dirty = true;
    cc_rgb_preview_active = false;
}
static void cc_rgb_preview_commit(void) {
    if (!cc_rgb_preview_active) return;
    rgblight_mode(rgblight_get_mode());
    rgblight_sethsv(rgblight_get_hue(), rgblight_get_sat(), rgblight_get_val());
    eeconfig_update_user_datablock(&cc_rgb, 0, sizeof(cc_rgb));
    // Committed state is now the rollback reference.
    cc_rgb_before = cc_rgb;
    cc_rgb_mode_before = rgblight_get_mode();
    cc_rgb_hue_before = rgblight_get_hue();
    cc_rgb_sat_before = rgblight_get_sat();
    cc_rgb_val_before = rgblight_get_val();
    cc_dirty = true;
}
static void cc_user_layer_change(uint8_t from, uint8_t to) {
    if (from == CC_RGB_LAYER && to != CC_RGB_LAYER) cc_rgb_preview_cancel();
    if (from != CC_RGB_LAYER && to == CC_RGB_LAYER) cc_rgb_preview_begin();
    if (from == CC_MACRO_LAYER && to != CC_MACRO_LAYER) cc_macro_recording = false;
    if (cc_nav_alt_down) {
        unregister_code(KC_LALT);
        cc_nav_alt_down = false;
    }
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
        cc_td_t *s = &cc_td[i];
        if (s->held) {
            if (s->origin == CC_NAV_LAYER && i == 1) unregister_code(KC_PGDN);
            else if (s->origin != CC_MACRO_LAYER && s->code != KC_NO &&
                     s->code != KC_TRNS) {
                if (omp_enabled) omp_emit(s->code, false);
                else unregister_code16(s->code);
            }
        }
        s->down = s->pending = s->second = s->held = false;
    }
    cc_enc_down = cc_enc_moved = false;
    cc_ui_activity();
}

static void cc_rgb_adjust_effect(bool clockwise) {
    if (!cc_rgb_preview_active) cc_rgb_preview_begin();
    if (cc_rgb_zone == 0) {
        cc_rgb.mode = 0; // Use QMK effects rather than the two-color renderer.
        if (clockwise) rgblight_step_noeeprom();
        else rgblight_step_reverse_noeeprom();
        cc_main_dirty = true;
    } else {
        cc_rgb.frame_effect = (cc_rgb.frame_effect + (clockwise ? 1 : CC_FRAME_EFFECT_MAX)) %
                              (CC_FRAME_EFFECT_MAX + 1u);
        cc_frame_dirty = true;
    }
    cc_dirty = true;
}
static void cc_rgb_key(uint8_t index) {
    if (!cc_rgb_preview_active) cc_rgb_preview_begin();
    switch (index) {
        case 0:
            if (cc_rgb_zone) { cc_rgb.frame_enabled = !cc_rgb.frame_enabled; cc_frame_dirty = true; }
            else rgblight_toggle_noeeprom();
            break;
        case 1: case 2:
            if (cc_rgb_zone) { cc_rgb.frame_hue1 += index == 2 ? 8 : (uint8_t)-8; cc_frame_dirty = true; }
            else rgblight_sethsv_noeeprom(rgblight_get_hue() + (index == 2 ? 8 : (uint8_t)-8),
                                           rgblight_get_sat(), rgblight_get_val());
            break;
        case 3: cc_rgb_preview_commit(); break;
        case 4: cc_rgb_zone = !cc_rgb_zone; break;
        case 5: case 6:
            if (cc_rgb_zone) {
                if (index == 5 && cc_rgb.frame_brightness) --cc_rgb.frame_brightness;
                if (index == 6 && cc_rgb.frame_brightness < RGBLIGHT_LIMIT_VAL) ++cc_rgb.frame_brightness;
                cc_frame_dirty = true;
            } else {
                uint8_t v = rgblight_get_val();
                v = index == 5 ? (v >= 4 ? v - 4 : 0) :
                                 (v <= RGBLIGHT_LIMIT_VAL-4 ? v + 4 : RGBLIGHT_LIMIT_VAL);
                rgblight_sethsv_noeeprom(rgblight_get_hue(), rgblight_get_sat(), v);
            }
            break;
        case 7:
            if (cc_rgb_zone) { cc_rgb.frame_speed += 16; cc_frame_dirty = true; }
            else rgblight_increase_speed_noeeprom();
            break;
        case 8: cc_rgb.mode = (cc_rgb.mode + 1) % 5; cc_main_dirty = true; break;
        case 9: cc_activate_layer(cc_previous == CC_RGB_LAYER ? 1 : cc_previous); break;
    }
    cc_dirty = true;
}
static void cc_macro_action(uint8_t slot) {
    if (slot >= 7) return;
    if (cc_macro_recording && !cc_macro_playing) {
        if (cc_macro_recorded_count < sizeof(cc_macro_recorded))
            cc_macro_recorded[cc_macro_recorded_count++] = (cc_macro_bank ? 7 : 0) + slot;
        cc_dirty = true;
        return;
    }
    static const uint16_t a[7] = {LCTL(KC_C), LCTL(KC_V), LCTL(KC_X), LCTL(KC_A),
                                   LCTL(KC_S), LCTL(KC_Y), LCTL(KC_Z)};
    static const uint16_t b[7] = {LGUI(KC_E), LGUI(KC_D), LGUI(LSFT(KC_S)),
                                   LGUI(KC_V), LCTL(LSFT(KC_S)), LCTL(KC_T), LCTL(KC_W)};
    tap_code16(cc_macro_bank ? b[slot] : a[slot]);
}
static void cc_macro_playback(void) {
    cc_macro_playing = true;
    const uint8_t previous_bank = cc_macro_bank;
    if (cc_macro_recorded_count) {
        for (uint8_t i = 0; i < cc_macro_recorded_count; ++i) {
            cc_macro_bank = cc_macro_recorded[i] / 7u;
            cc_macro_action(cc_macro_recorded[i] % 7u);
        }
    } else {
        cc_macro_action(cc_internal_selected % 7u);
    }
    cc_macro_bank = previous_bank;
    cc_macro_playing = false;
    cc_dirty = true;
}
static void cc_single_tap(uint8_t index, uint8_t origin, uint16_t code) {
    if (origin == CC_MACRO_LAYER) {
        if (index == 8) { cc_macro_playback(); return; }
        if (!omp_enabled || cc_macro_recording) {
            if (index < 4) cc_macro_action(index);
            if (index >= 5 && index <= 7) cc_macro_action(index - 1);
            return;
        }
    }
    if (omp_enabled && origin < omp_profile.layer_count) {
        // Preserve user-edited single actions while layer entry stays fixed.
        omp_tap(code);
        return;
    }
    if (code != KC_NO && code != KC_TRNS) tap_code16(code);
}
static bool cc_td_event(uint8_t index, bool pressed) {
    if (cc_internal_mode || index >= CC_KEY_COUNT) return false;
    if (index == 8 && cc_active != 4 && cc_active != CC_MACRO_LAYER) return false;
    if (index != 8 && cc_td_dest[index] == 255) return false;
    cc_td_t *s = &cc_td[index];
    if (pressed) {
        if (s->pending && s->origin == cc_active && timer_elapsed(s->released) < cc_tap_term()) {
            s->pending = false; s->second = true; s->down = true;
            return true;
        }
        if (s->pending) {
            cc_single_tap(index, s->origin, s->code);
            s->pending = false;
        }
        s->origin = cc_active;
        s->code = omp_enabled ? omp_profile.layers[cc_active].keys[index].codes[0] :
                  dynamic_keymap_get_keycode(cc_active, cc_matrix_row[index], cc_matrix_col[index]);
        // Older VIA EEPROM layouts may contain an uninitialized eighth layer.
        if (s->code == KC_NO && cc_active < CC_LAYER_COUNT)
            s->code = cc_layers[cc_active].taps[index];
        s->started = timer_read();
        s->down = true; s->held = s->second = false;
    } else if (s->down) {
        s->down = false;
        if (s->second) {
            s->second = false;
            for (uint8_t j = 0; j < CC_KEY_COUNT; ++j) cc_td[j].pending = false;
            cc_activate_layer(cc_td_dest[index]);
            cc_display_mode = false;
        } else if (s->held) {
            s->held = false;
            if (s->origin == CC_NAV_LAYER && index == 1) unregister_code(KC_PGDN);
            else if (s->code != KC_NO && s->code != KC_TRNS &&
                     s->origin != CC_MACRO_LAYER) {
                if (omp_enabled) omp_emit(s->code, false);
                else unregister_code16(s->code);
            }
        } else {
            s->pending = true; s->released = timer_read();
        }
    }
    return true;
}
static void cc_td_tick(void) {
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
        cc_td_t *s = &cc_td[i];
        if (s->down && !s->second && !s->held &&
            timer_elapsed(s->started) >= cc_tap_term()) {
            s->held = true;
            if (s->origin == CC_NAV_LAYER && i == 1) register_code(KC_PGDN);
            else if (s->origin != CC_MACRO_LAYER &&
                     s->code != KC_NO && s->code != KC_TRNS) {
                if (omp_enabled) omp_emit(s->code, true);
                else register_code16(s->code);
            }
        }
        if (s->pending && !s->down && timer_elapsed(s->released) >= cc_tap_term()) {
            cc_single_tap(i, s->origin, s->code);
            s->pending = false;
        }
    }
}
static void cc_nav_alt_tick(void) {
    if (cc_nav_alt_down && timer_elapsed(cc_nav_alt_at) > 800) {
        unregister_code(KC_LALT);
        cc_nav_alt_down = false;
    }
}
static bool cc_user_encoder_turn(bool clockwise) {
    cc_ui_activity();
    if (cc_internal_mode) {
        cc_internal_selected = (cc_internal_selected + (clockwise ? 1 : 9)) % 10;
        cc_dirty = true;
        return true;
    }
    if (cc_active == CC_RGB_LAYER) {
        cc_rgb_adjust_effect(clockwise);
        return true;
    }
    if (cc_active == CC_NAV_LAYER) {
        if (cc_enc_down) {
            cc_enc_moved = true;
            tap_code16(clockwise ? LGUI(LCTL(KC_RGHT)) : LGUI(LCTL(KC_LEFT)));
        } else {
            if (!cc_nav_alt_down) {register_code(KC_LALT); cc_nav_alt_down = true;}
            tap_code16(clockwise ? KC_TAB : LSFT(KC_TAB));
            cc_nav_alt_at = timer_read();
        }
        return true;
    }
    if (cc_active == CC_TEXT_LAYER && cc_enc_down) {
        cc_enc_moved = true;
        tap_code16(clockwise ? LSFT(KC_RGHT) : LSFT(KC_LEFT));
        return true;
    }
    if (cc_active == CC_MACRO_LAYER) {
        // Encoder can preview seven preset actions without sending them.
        cc_internal_selected = (cc_internal_selected + (clockwise ? 1 : 6)) % 7;
        cc_dirty = true;
        return true;
    }
    return false;
}
static bool cc_user_encoder_push(bool pressed) {
    cc_ui_activity();
    if (cc_internal_mode) {
        if (!pressed) cc_internal_press(cc_internal_selected);
        return true;
    }
    if (cc_active == CC_NAV_LAYER || cc_active == CC_TEXT_LAYER) {
        if (pressed) {cc_enc_down = true; cc_enc_moved = false;}
        else {
            if (!cc_enc_moved && cc_active == CC_TEXT_LAYER) cc_mouse_left_click();
            cc_enc_down = false; cc_enc_moved = false;
        }
        return true;
    }
    if (cc_active == CC_MACRO_LAYER) {
        if (!pressed) cc_macro_action(cc_internal_selected);
        return true;
    }
    return false;
}
static bool cc_special_key(uint8_t index, bool pressed) {
    if (cc_internal_mode) {
        if (pressed) cc_internal_press(index);
        return true;
    }
    if (cc_active == CC_RGB_LAYER) {
        if (pressed) cc_rgb_key(index);
        return true;
    }
    // Reserved layer-specific modifier exceptions work regardless of app state.
    if (index == 9 && cc_active == CC_TEXT_LAYER) {
        if (pressed) register_code(KC_ENT); else unregister_code(KC_ENT);
        return true;
    }
    if (index == 9 && cc_active == 4) {
        if (pressed) tap_code16(LGUI(LSFT(KC_S)));
        return true;
    }
    if (cc_active == CC_MACRO_LAYER && index == 4) {
        if (pressed) {
            if (!cc_macro_recording) cc_macro_recorded_count = 0;
            cc_macro_recording = !cc_macro_recording;
            cc_dirty = true;
        }
        return true;
    }
    if (cc_active == CC_MACRO_LAYER && index == 9) {
        if (pressed) {cc_macro_bank = !cc_macro_bank; cc_dirty = true;}
        return true;
    }
    if (omp_enabled) return false;
    return false;
}
