// QMK Tap Dance + dedicated K0 + dual-mode EC11 controls.
#pragma once
#include "cc_editor_actions.h"
#include "cc_detect.h"
#include "cc_editor_protocol.h"
#include "cc_editor_visuals.h"
#include "cc_via_rgb.h"

static void cc_encoder_press_action(void) {
    if (cc_matrix_test_view) {
        ++cc_detect_encoder_pushes;
        if (!cc_tester_active) cc_matrix_test_exit();
        return;
    }
    if (cc_color_view || cc_help_view) {
        cc_color_view = false;
        cc_help_view = false;
        cc_dirty = true;
        return;
    }
    if (cc_menu_view) {
        switch (cc_menu_selection) {
            case 0: cc_switch_encoder(true); break;
            case 1: cc_switch_encoder(false); break;
            case 2: cc_open_home(); break;
            case 3: cc_matrix_test_enter(); break;
            case 4:
                cc_menu_view = false;
                cc_help_view = true;
                cc_dirty = true;
                break;
            case 5:
                cc_menu_view = false;
                cc_color_view = true;
                cc_dirty = true;
                break;
        }
        return;
    }
    if (omp_enabled && !cc_display_mode) return;
    if (cc_display_mode) {
        cc_activate_layer(cc_preview);
    } else {
        uint16_t kc = cc_layers[cc_active].encoder_press;
        if (kc != KC_NO) tap_code16(kc);
    }
}

// Immediate fixed modifiers: physical K5=Shift, K9=Ctrl, K10=Alt.
// K9's double-tap is recognized on two clean short Ctrl presses without
// delaying Ctrl in combinations such as Ctrl+C or Ctrl+Shift+Z.
static bool cc_k9_down = false;
static bool cc_k9_chord = false;
static bool cc_k9_armed = false;
static bool cc_k9_second = false;
static uint16_t cc_k9_pressed_at = 0;
static uint16_t cc_k9_released_at = 0;

static bool cc_handle_fixed_modifier(uint8_t row, uint8_t col, bool pressed) {
    if (row == 1 && col == 0) {
        if (pressed) register_code(KC_LSFT); else unregister_code(KC_LSFT);
        return true;
    }
    if (row == 2 && col == 3) {
        if (pressed) register_code(KC_LALT); else unregister_code(KC_LALT);
        return true;
    }
    if (row != 2 || col != 2) return false;
    if (pressed) {
        cc_k9_second = cc_k9_armed && timer_elapsed(cc_k9_released_at) <= CC_K9_DOUBLE_TAP_MS;
        cc_k9_armed = false;
        cc_k9_chord = false;
        cc_k9_down = true;
        cc_k9_pressed_at = timer_read();
        register_code(KC_LCTL);
    } else {
        unregister_code(KC_LCTL);
        cc_k9_down = false;
        const bool clean = !cc_k9_chord && timer_elapsed(cc_k9_pressed_at) <= CC_K9_DOUBLE_TAP_MS;
        if (clean && cc_k9_second) {
            cc_k9_armed = false;
            cc_activate_layer(0); // CC Studio
        } else {
            cc_k9_armed = clean;
            cc_k9_released_at = timer_read();
        }
        cc_k9_second = false;
    }
    return true;
}

void keyboard_post_init_user(void) {
    gpio_set_pin_input_high(ENCODER_SW);
    gpio_set_pin_input_high(K0_SW);
#ifdef RGBLIGHT_ENABLE
    cc_rgb_load(); // Restrict QMK RGB effects to LEDs 0..13; load independent Frame settings.
#endif
    omp_load();
    layer_move(omp_enabled ? omp_profile.default_layer : 1); // Default is layer 1 on every USB boot.
    lcd_init(); // Known-good GPIO bootstrap then QMK HW SPI.
    cc_adxl_init(); // No I2C pin ownership unless enabled after matrix relocation.
    cc_dirty = true;
}

static bool omp_k0_custom(void) {
    if (!omp_enabled) return false;
    const omp_key_t *key = &omp_profile.layers[cc_active].keys[11];
    for (uint8_t i = 0; i < 5; ++i) if (key->codes[i] > KC_TRNS) return true;
    return false;
}

static bool cc_button_update(cc_button_t *button, pin_t pin) {
    const bool raw = gpio_read_pin(pin);
    if (raw != button->sample) {
        button->sample = raw;
        button->changed = timer_read();
    }
    if (button->sample == button->stable || timer_elapsed(button->changed) < CC_DEBOUNCE_MS) return false;
    button->stable = button->sample;
    return true;
}

static bool cc_eeprom_reset_update(void) {
    switch (cc_reset_state) {
        case CC_RESET_WAIT_RELEASE:
            if (cc_k0.stable && cc_encoder_button.stable && cc_k0.sample && cc_encoder_button.sample)
                cc_reset_state = CC_RESET_IDLE;
            return true;
        case CC_RESET_IDLE:
            if (cc_k0.stable || cc_encoder_button.stable) return false;
            cc_k0_tap_count = 0;
            omp_release_all();
            cc_reset_started = timer_read();
            cc_reset_state = CC_RESET_HOLDING;
            cc_dirty = true;
            break;
        case CC_RESET_HOLDING:
            if (cc_k0.stable || cc_encoder_button.stable) {
                cc_reset_state = CC_RESET_WAIT_RELEASE;
                cc_matrix_full_redraw = true;
                cc_dirty = true;
            } else if (!cc_k0.sample && !cc_encoder_button.sample &&
                       timer_elapsed(cc_reset_started) >= CC_EEPROM_HOLD_MS) {
                // Invalidate both editor slots as well as clearing QMK/VIA settings.
                eeprom_update_dword((uint32_t *)(uintptr_t)omp_slot_address(0), 0);
                eeprom_update_dword((uint32_t *)(uintptr_t)omp_slot_address(1), 0);
                eeconfig_init();
                soft_reset_keyboard();
            }
            break;
    }
    return true;
}

static void cc_k0_update(bool changed) {
    if (changed) {
        if (cc_tester_active && cc_matrix_test_view && cc_k0.stable) return;
        if (!cc_k0.stable) {
            cc_k0_pressed = timer_read();
            cc_k0_held = false;
            if (omp_k0_custom() && !cc_matrix_test_view && !cc_menu_view) omp_key_event(11, true);
        } else if (!cc_k0_held) {
            if (omp_keys[11].down) {
                omp_key_event(11, false);
                return;
            }
            // Delay 1x and 2x until the tap window closes. Otherwise
            // 2x HOME would trigger before the intended 3x MATRIX.
            ++cc_k0_tap_count;
            cc_k0_released = timer_read();
            if (cc_k0_tap_count >= 3) {
                cc_k0_tap_count = 0;
                cc_matrix_test_toggle();
            }
        }
    }
    if (!cc_k0.stable && !cc_k0_held &&
        timer_elapsed(cc_k0_pressed) >= (omp_enabled ? 2000u : CC_K0_HOLD_MS)) {
        if (omp_enabled) omp_release_all();
        cc_k0_held = true;
        cc_k0_tap_count = 0;
        if (cc_tester_active && cc_matrix_test_view) {
            cc_matrix_test_exit();
            cc_tester_active = false;
        } else cc_open_menu();
    }
    if (cc_k0.stable && cc_k0_tap_count &&
        timer_elapsed(cc_k0_released) >= CC_K0_TAPS_MS) {
        const uint8_t taps = cc_k0_tap_count;
        cc_k0_tap_count = 0;
        if (taps == 2) {
            cc_open_home(); // Also activates DEFAULT (layer 1).
        } else if (cc_matrix_test_view) {
            // K0 1x also offers an immediate exit after the tap window.
            cc_matrix_test_exit();
        } else {
            cc_switch_encoder(!cc_display_mode);
        }
    }
}

static void cc_encoder_button_action(void) {
    if (omp_keys[10].down || (omp_enabled && !cc_matrix_test_view && !cc_menu_view && !cc_display_mode)) {
        omp_key_event(10, !cc_encoder_button.stable);
    } else if (!cc_encoder_button.stable) cc_encoder_press_action();
}

// Physical safety behavior precedes whatever VIA assigned at that matrix cell.
bool process_record_user(uint16_t keycode, keyrecord_t *record) {
    (void)keycode;
    const uint8_t row = record->event.key.row;
    const uint8_t col = record->event.key.col;
    if (cc_matrix_test_view) {
        cc_matrix_test_record(row, col, record->event.pressed);
        return false;
    }
    if (cc_k9_down && record->event.pressed && !(row == 2 && col == 2)) {
        cc_k9_chord = true;
    }
    if (cc_handle_fixed_modifier(row, col, record->event.pressed)) return false;
    if (record->event.pressed) {
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
            if (cc_matrix_row[i] == row && cc_matrix_col[i] == col) {
                cc_last_key = i;
                cc_dirty = true;
                break;
            }
        }
    }
    return true; // QMK/VIA dynamic keymap, macros and lighting keys.
}

layer_state_t layer_state_set_user(layer_state_t state) {
    const uint8_t highest = get_highest_layer(state);
    if (highest < omp_layer_count() && cc_active != highest) {
        cc_previous = cc_active;
        cc_active = highest;
        cc_preview = highest;
        cc_home_view = false;
        cc_dirty = true;
    }
    omp_layer_changed();
    return state;
}

void matrix_scan_user(void) {
    // K0 (GP11) and encoder PUSH (GP10) are outside the matrix.
    const bool k0_changed = cc_button_update(&cc_k0, K0_SW);
    const bool encoder_changed = cc_button_update(&cc_encoder_button, ENCODER_SW);
    if (k0_changed) cc_tester_record(CC_SIGNAL_K0, 0, !cc_k0.stable);
    if (encoder_changed) cc_tester_record(CC_SIGNAL_ENCODER_PUSH, 0, !cc_encoder_button.stable);
    if (!cc_eeprom_reset_update()) {
        cc_k0_update(k0_changed);
        if (encoder_changed) cc_encoder_button_action();
    }
}

static bool cc_encoder_rotate(bool clockwise) {
    if (cc_matrix_test_view) {
        cc_tester_record(CC_SIGNAL_ENCODER_TURN, clockwise, 0);
        if (clockwise) ++cc_detect_clockwise;
        else ++cc_detect_counterclockwise;
        return false; // Never emit encoder host actions during diagnosis.
    }
    if (omp_enabled) {
        omp_encoder_direction = clockwise ? 1 : -1;
        omp_encoder_position = (omp_encoder_position + (clockwise ? 1 : 42)) % 43;
        omp_event(2);
    }
    if (cc_menu_view) {
        cc_menu_selection = (cc_menu_selection + (clockwise ? 1 : 5)) % 6;
        cc_dirty = true;
    } else if (cc_display_mode) {
        if (cc_help_view || cc_color_view) return false;
        cc_preview = (cc_preview + (clockwise ? 1 : omp_layer_count() - 1)) %
                     omp_layer_count();
        cc_home_view = cc_preview == 0;
        cc_dirty = true;
    } else if (omp_enabled) {
        omp_tap(omp_profile.layers[cc_active].encoders[clockwise ? 1 : 0]);
        return false;
    } else {
        return true; // QMK encoder map: VIA remaps CCW/CW independently per layer.
    }
    return false;
}

// ENCODER_MAP_ENABLE delivers rotation as key events instead of calling
// encoder_update_user. Intercept both edges before QMK sends a host keycode.
bool pre_process_record_user(uint16_t keycode, keyrecord_t *record) {
    (void)keycode;
    if (IS_KEYEVENT(record->event) && cc_matrix_test_view) return false;
    if (IS_KEYEVENT(record->event) && omp_enabled) {
        const uint8_t row = record->event.key.row, col = record->event.key.col;
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
            if (cc_matrix_row[i] == row && cc_matrix_col[i] == col) {
                cc_last_key = i;
                omp_key_event(i, record->event.pressed);
                return false;
            }
        }
    }
    if (!IS_ENCODEREVENT(record->event)) return true;
    if (!record->event.pressed) return !omp_enabled && !cc_matrix_test_view && !cc_display_mode && !cc_menu_view;
    return cc_encoder_rotate(record->event.key.row == KEYLOC_ENCODER_CW);
}

// CC Studio analog slider (GP28): relative Ctrl+Numpad+/− zoom.
// Movement is quantized around the last position, never jumps at startup.
static int16_t cc_zoom_reference = -1;
static void cc_zoom_slider_update(int16_t sample) {
    if (sample < 0) return;
    if (cc_active != 0) { cc_zoom_reference = -1; return; }
    if (cc_zoom_reference < 0) { cc_zoom_reference = sample; return; }
    // 64 ADC units per zoom step; ignore small ADC noise.
    for (uint8_t steps = 0; steps < 3; ++steps) {
        const int16_t delta = sample - cc_zoom_reference;
        if (delta >= 64) {
            tap_code16(LCTL(KC_PPLS));
            cc_zoom_reference += 64;
        } else if (delta <= -64) {
            tap_code16(LCTL(KC_PMNS));
            cc_zoom_reference -= 64;
        } else {
            break;
        }
    }
}

void housekeeping_task_user(void) {
    if (cc_matrix_test_view) {
        cc_tester_sample_matrix();
        cc_adxl_poll(); // Slow bounded I2C reads; never in the normal key path.
        if (cc_adxl.changed) cc_dirty = true;
#if CC_PCF8575_MATRIX
        const bool online = cc_pcf8575_online();
        if (online != cc_pcf_last_online) {
            cc_pcf_last_online = online;
            if (online) cc_tester_record(CC_SIGNAL_PCF, 0, 0);
            cc_matrix_full_redraw = true;
            cc_dirty = true;
        }
#endif
    }
#ifdef RGBLIGHT_ENABLE
    static bool preview_was_active;
    static uint8_t preview_qmk_mode;
    if (omp_preview_active && (cc_matrix_test_view || timer_elapsed(omp_preview_at) >= OMP_LED_PREVIEW_MS)) {
        omp_preview_active = false;
    }
    if (omp_preview_active && !preview_was_active) {
        preview_qmk_mode = rgblight_get_mode();
        if (preview_qmk_mode > RGBLIGHT_MODE_STATIC_LIGHT) {
            rgblight_mode_noeeprom(RGBLIGHT_MODE_STATIC_LIGHT);
        }
    }
    if (preview_was_active && !omp_preview_active && !omp_enabled) {
        rgblight_driver.set_color_all(0, 0, 0);
        if (preview_qmk_mode > RGBLIGHT_MODE_STATIC_LIGHT) rgblight_mode_noeeprom(preview_qmk_mode);
        rgblight_sethsv_noeeprom(rgblight_get_hue(), rgblight_get_sat(), rgblight_get_val());
        cc_main_dirty = cc_frame_dirty = true;
    }
    if (!cc_tester_preview_leds()) {
        if (omp_preview_active || omp_enabled) omp_lighting_tick(omp_preview_active);
        else cc_rgb_tick();
    }
    preview_was_active = omp_preview_active;
#endif
    omp_actions_tick();
    if (cc_matrix_test_view && omp_enabled && omp_down_mask) omp_release_all();
    if (timer_elapsed(cc_slider_last_sample) >= 35) {
        cc_slider_last_sample = timer_read();
        const int16_t sample = analogReadPin(SLIDER_ADC_PIN);
        if (sample >= 0) {
            uint16_t previous_pct = cc_slider_pct;
            cc_slider_raw = sample;
            const uint16_t value = omp_slider_value(cc_slider_raw);
            cc_slider_pct = ((uint32_t)value * 100u + 511u) / 1023u;
            cc_slider_valid = true;
            if (cc_matrix_test_view || (omp_enabled && omp_profile.screen.enabled)) {
                if (cc_slider_pct != previous_pct) cc_dirty = true;
            }
            if (!cc_matrix_test_view && !cc_menu_view) {
                if (omp_enabled) omp_slider_update(sample);
                else cc_zoom_slider_update(value);
            }
        } else cc_slider_valid = false;
    }
    if (cc_tester_output && (!cc_matrix_test_view || timer_elapsed(cc_tester_output_at) >= 1800)) {
        cc_tester_output = 0;
        cc_matrix_full_redraw = true;
        cc_dirty = true;
    }
    if (!cc_matrix_test_view) cc_tester_active = false;
    cc_tester_sample();
    if (cc_dirty && timer_elapsed(cc_last_draw) >= 35) cc_redraw();
}
