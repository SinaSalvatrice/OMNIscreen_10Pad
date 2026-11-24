// QMK Tap Dance + dedicated K0 + dual-mode EC11 controls.
#pragma once
#include "cc_editor_actions.h"
#include "cc_detect.h"
#include "cc_editor_protocol.h"
#include "cc_via_rgb.h"
#include "cc_editor_visuals.h"
#include "cc_omni_keymap.h"

static void cc_clear_eeprom(void) {
    eeprom_update_dword((uint32_t *)(uintptr_t)omp_slot_address(0), 0);
    eeprom_update_dword((uint32_t *)(uintptr_t)omp_slot_address(1), 0);
    eeconfig_init();
    soft_reset_keyboard();
}


// Firmware-owned controls: never trigger a destructive operation without a
// second, explicit press of the same physical key.
// Menu navigation takes precedence over normal QMK keys on every non-layer screen.
static bool cc_on_menu_screen(void) {
    return cc_internal_mode || cc_screen_selection == CC_SCREEN_LAYERS ||
           cc_matrix_test_view || cc_menu_view || cc_help_view || cc_color_view;
}
static uint8_t cc_internal_count(void) {
    return cc_internal_mode == 2 ? 5 : cc_internal_mode == 4 ? 3 : 9;
}
static void cc_internal_step(int8_t delta) {
    if (!cc_internal_mode || cc_internal_mode == 3) return;
    const int8_t count = (int8_t)cc_internal_count();
    int8_t next = (int8_t)cc_internal_selected + delta;
    if (delta == 5 || delta == -5) {
        if (cc_internal_mode != 1 || next < 0 || next >= count) return;
    } else {
        if (next < 0) next = count - 1;
        if (next >= count) next = 0;
    }
    cc_internal_selected = (uint8_t)next;
    cc_dirty = true;
}
static void cc_menu_back(void) {
    cc_internal_confirm = 255;
    if (cc_matrix_test_view) cc_matrix_test_exit();
    else if (cc_internal_mode == 2 || cc_internal_mode == 3 || cc_internal_mode == 4) {
        cc_internal_mode = 1;
        cc_internal_selected = 0;
    } else {
        cc_internal_mode = 0;
        cc_open_home();
    }
    cc_dirty = true;
}
static void cc_switch_source(bool use_app) {
    if (use_app && !cc_visual_profile_available) return;
    if (omp_enabled) omp_release_all();
    clear_keyboard();
    cc_use_app_profile = use_app;
    omp_enabled = use_app && cc_visual_profile_available;
    cc_ui_config_save();
    cc_activate_layer(omp_enabled ? omp_profile.default_layer : 1);
    cc_internal_mode = 0;
    cc_open_home();
}
static void cc_internal_press(uint8_t index) {
    if (!cc_internal_mode || index >= cc_internal_count()) return;
    cc_ui_activity();
    if (cc_internal_confirm != 255) {
        const uint8_t pending = cc_internal_confirm;
        cc_internal_confirm = 255;
        // K9 confirms the highlighted dangerous action, K5 cancels.
        if (index != pending) { cc_dirty = true; return; }
        if (pending == 5) { soft_reset_keyboard(); return; }
        if (pending == 6) { reset_keyboard(); return; }
        if (pending == 7) { cc_clear_eeprom(); return; }
        return;
    }
    cc_internal_selected = index;
    if (cc_internal_mode == 3) {
        cc_menu_back();
    } else if (cc_internal_mode == 4) {
        if (index == 0) cc_switch_source(false);
        else if (index == 1) cc_switch_source(true);
        else cc_menu_back();
    } else if (cc_internal_mode == 2) {
        switch (index) {
            case 0: cc_internal_mode = 0; cc_open_home(); break;
            case 1: cc_internal_mode = 0; cc_open_layer_list(); break;
            case 2: cc_internal_mode = 0; cc_matrix_test_enter(); break;
            case 3:
                cc_backlight_awake = !cc_backlight_awake;
                gpio_write_pin(LCD_BL, cc_backlight_awake);
                break;
            case 4: cc_menu_back(); break;
        }
    } else {
        switch (index) {
            case 0:
                cc_rgb_master_enabled = !cc_rgb_master_enabled;
                omp_light_reaction_mask = 0;
                cc_ui_config_save();
                break;
            case 1: cc_internal_mode = 2; cc_internal_selected = 0; break;
            case 2: cc_internal_mode = 4; cc_internal_selected = cc_use_app_profile ? 1 : 0; break;
            case 3: cc_internal_mode = 0; cc_matrix_test_enter(); break;
            case 4: cc_internal_mode = 3; break;
            case 5: case 6: case 7: cc_internal_confirm = index; break;
            case 8: cc_menu_back(); break;
        }
    }
    cc_dirty = true;
}
static bool cc_ui_menu_key(uint8_t index, bool pressed) {
    if (cc_matrix_test_view) return false; // tester sees raw physical keys
    if (!cc_internal_mode && cc_screen_selection != CC_SCREEN_LAYERS) return false;
    if (!pressed) return true;
    if (index == 4) { cc_menu_back(); return true; }  // K5 back
    if (cc_internal_mode) {
        if (index == 8) { // K9 confirms highlighted item
            cc_internal_press(cc_internal_selected);
            return true;
        }
        if (index == 2) cc_internal_step(-1);       // K3 up
        else if (index == 6) cc_internal_step(1);   // K7 down
        else if (index == 5) cc_internal_step(-5);  // K6 left column
        else if (index == 7) cc_internal_step(5);   // K8 right column
        return true;
    }
    if (index == 8) { cc_activate_layer(cc_preview); cc_open_home(); }
    else if (index == 2 || index == 5) cc_preview = (cc_preview + omp_layer_count() - 1) % omp_layer_count();
    else if (index == 6 || index == 7) cc_preview = (cc_preview + 1) % omp_layer_count();
    cc_dirty = true;
    return true;
}

static bool omp_device_action(uint16_t code, bool pressed) {
    if (code < OMP_ACTION_LAYERS || code > OMP_ACTION_SETTINGS) return false;
    if (!pressed || cc_tester_active || code == OMP_ACTION_NONE) return true;
    // Only four protected screens are supported. Legacy app actions no longer
    // inject alternate screens over the physical-key navigation.
    switch (code) {
        case OMP_ACTION_MATRIX:
            cc_matrix_test_toggle();
            break;
        case OMP_ACTION_LAYERS:
        case OMP_ACTION_NAVIGATION:
            if (omp_enabled) omp_release_all();
            cc_open_layer_list();
            break;
        case OMP_ACTION_SETTINGS:
        case OMP_ACTION_MENU:
            if (omp_enabled) omp_release_all();
            cc_internal_mode = 1;
            cc_internal_selected = 0;
            cc_internal_confirm = 255;
            cc_dirty = true;
            break;
        case OMP_ACTION_EEPROM:
            cc_internal_mode = 1;
            cc_internal_selected = 7; // Confirm in Settings; never erase immediately.
            cc_dirty = true;
            break;
        default:
            cc_open_home();
            break;
    }
    omp_screen_invalid = true;
    return true;
}

static void cc_encoder_press_action(void) {
    if (cc_internal_mode) {
        cc_internal_press(cc_internal_selected);
        return;
    }
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
    if (cc_screen_selection == CC_SCREEN_LAYERS) {
        cc_activate_layer(cc_preview);
    } else {
        uint16_t kc = cc_layers[cc_active].encoder_press;
        if (kc == MS_BTN1) cc_mouse_left_click();
        else if (kc != KC_NO) tap_code16(kc);
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
        if (cc_active == CC_MACRO_LAYER || cc_active == CC_RGB_LAYER) return false;
        if (pressed) register_code(KC_LSFT); else unregister_code(KC_LSFT);
        return true;
    }
    if (row == 2 && col == 3) {
        if (cc_active == CC_TEXT_LAYER || cc_active == CC_MACRO_LAYER || cc_active == CC_RGB_LAYER)
            return false;
        if (pressed) register_code(KC_LALT); else unregister_code(KC_LALT);
        return true;
    }
    if (row != 2 || col != 1) return false;
    if (cc_active == CC_TEXT_LAYER) {
        if (pressed) register_code(KC_SPC); else unregister_code(KC_SPC);
        return true;
    }
    if (cc_active == 4 || cc_active == CC_MACRO_LAYER || cc_active == CC_RGB_LAYER)
        return false;
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
            cc_activate_layer(0);
            cc_display_mode = false;
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
    cc_rgb_load(); // 30 matrix LEDs, followed by unchanged 43 Frame LEDs.
#endif
    omp_load();
    cc_visual_profile_available = omp_enabled;
    cc_ui_config_load();
    if (!cc_use_app_profile) omp_enabled = false;
    cc_active = omp_enabled ? omp_profile.default_layer : 1;
    cc_preview = cc_active;
    layer_move(cc_active);
    cc_display_mode = false;
    cc_home_view = false; // Active layer map at every startup.
    cc_screen_selection = CC_SCREEN_DETAILS;
    lcd_init(); // Known-good GPIO bootstrap then QMK HW SPI.
    cc_adxl_init(); // No I2C pin ownership unless enabled after matrix relocation.
    cc_dirty = true;
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


static void cc_k0_update(bool changed) {
    if (changed) {
        cc_ui_activity();
        if (!cc_k0.stable) {
            cc_k0_pressed = timer_read();
            cc_k0_held = false;
        } else if (!cc_k0_held) {
            ++cc_k0_tap_count;
            cc_k0_released = timer_read();
            if (cc_k0_tap_count >= 3) {
                cc_k0_tap_count = 0;
                cc_matrix_test_toggle();
            }
        }
    }
    if (!cc_k0.stable && !cc_k0_held &&
        timer_elapsed(cc_k0_pressed) >= CC_K0_HOLD_MS) {
        cc_k0_held = true;
        cc_k0_tap_count = 0;
        if (omp_enabled) omp_release_all();
        if (cc_matrix_test_view) cc_matrix_test_exit();
        // K0 long-press opens the protected firmware system settings.
        // Do not change the active typing layer.
        cc_internal_mode = 1;
        cc_internal_selected = 0;
        cc_internal_confirm = 255;
        cc_internal_skip_k0_release = true;
        cc_dirty = true;
    }
    if (cc_k0.stable && cc_k0_tap_count &&
        timer_elapsed(cc_k0_released) >= CC_K0_TAPS_MS) {
        const uint8_t taps = cc_k0_tap_count;
        cc_k0_tap_count = 0;
        if (taps == 2) cc_open_home();
        else if (cc_matrix_test_view) cc_matrix_test_exit();
        // One tap does not change modes; the active map stays visible.
    }
}

static uint16_t cc_encoder_pressed_at;
static bool cc_encoder_pressed_in_layer;
static void cc_encoder_button_action(void) {
    const bool pressed = !cc_encoder_button.stable;
    if (pressed) {
        cc_encoder_pressed_at = timer_read();
        cc_encoder_pressed_in_layer = !cc_on_menu_screen();
        // Delay the click until release so a long hold cannot perform an action.
        if (cc_encoder_pressed_in_layer) return;
    } else if (cc_encoder_pressed_in_layer) {
        cc_encoder_pressed_in_layer = false;
        if (timer_elapsed(cc_encoder_pressed_at) >= 620u) {
            cc_open_layer_list();
        } else {
            cc_encoder_press_action();
        }
        return;
    }
    if (cc_internal_mode) {
        if (!pressed) cc_internal_press(cc_internal_selected);
        return;
    }
    if (cc_screen_selection == CC_SCREEN_LAYERS) {
        if (!pressed) cc_activate_layer(cc_preview);
        return;
    }
    if (cc_user_encoder_push(pressed)) return;
    bool custom = false;
    if (omp_enabled && !cc_matrix_test_view && !cc_menu_view) {
        const omp_key_t *key = &omp_profile.layers[cc_active].keys[10];
        uint8_t slots = key->mode == 0 ? 1 : key->mode == 1 ? 5 : 4;
        for (uint8_t i = 0; i < slots; ++i)
            if (key->codes[i] > KC_TRNS) { custom = true; break; }
    }
    if (omp_keys[10].down || (omp_enabled && !cc_matrix_test_view &&
                              !cc_menu_view && custom)) {
        omp_key_event(10, pressed);
        return;
    }
    // Built-in clicks fire on release; this makes K0+PUSH race-free.
    if (!pressed) cc_encoder_press_action();
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
    if (cc_k9_down && record->event.pressed && !(row == 2 && col == 1)) {
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
        cc_user_layer_change(cc_active, highest);
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
    static bool combo_latched;
    const bool k0_changed = cc_button_update(&cc_k0, K0_SW);
    const bool encoder_changed = cc_button_update(&cc_encoder_button, ENCODER_SW);
    if (k0_changed) {
        cc_tester_record(CC_SIGNAL_K0, 0, !cc_k0.stable);
        if (!cc_k0.stable) omp_react(OMP_ZONE_K0);
    }
    if (encoder_changed) {
        cc_tester_record(CC_SIGNAL_ENCODER_PUSH, 0, !cc_encoder_button.stable);
        if (!cc_encoder_button.stable) omp_react(OMP_ZONE_ENCODER);
    }
    if (!cc_k0.stable && !cc_encoder_button.stable) {
        if (!combo_latched) {
            combo_latched = true;
            if (omp_enabled) omp_release_all();
            cc_enc_down = cc_enc_moved = false;
            if (cc_nav_alt_down) {
                unregister_code(KC_LALT);
                cc_nav_alt_down = false;
            }
            for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) cc_td[i].pending = false;
            cc_k0_tap_count = 0; cc_k0_held = true;
            cc_internal_mode = 1;
            cc_internal_selected = 0;
            cc_internal_confirm = 255;
            cc_menu_view = cc_color_view = cc_help_view = false;
            cc_ui_activity();
            cc_dirty = true;
        }
        return;
    }
    if (combo_latched) {
        if (cc_k0.stable && cc_encoder_button.stable) combo_latched = false;
        return;
    }
    if (cc_internal_mode) {
        if (k0_changed && cc_k0.stable) {
            if (cc_internal_skip_k0_release) {
                cc_internal_skip_k0_release = false;
            } else {
                cc_menu_back();
            }
        }
        if (encoder_changed) cc_user_encoder_push(!cc_encoder_button.stable);
        return;
    }
    if (cc_eeprom_confirm) {
        if (k0_changed && cc_k0.stable) {cc_eeprom_confirm = false; cc_dirty = true;}
        if (encoder_changed && !cc_encoder_button.stable && cc_eeprom_confirm_visible)
            cc_clear_eeprom();
        return;
    }
    cc_k0_update(k0_changed);
    if (encoder_changed) cc_encoder_button_action();
}

static bool cc_encoder_rotate(bool clockwise) {
    if (cc_matrix_test_view) {
        cc_tester_record(CC_SIGNAL_ENCODER_TURN, clockwise, 0);
        if (clockwise) ++cc_detect_clockwise;
        else ++cc_detect_counterclockwise;
        return false; // Never emit encoder host actions during diagnosis.
    }
    // Menus own the encoder exclusively, even with an app profile loaded.
    if (!cc_internal_mode && cc_screen_selection != CC_SCREEN_LAYERS && !cc_menu_view)
        omp_react(OMP_ZONE_ENCODER);
    if (cc_internal_mode) {
        cc_internal_step(clockwise ? 1 : -1);
    } else if (cc_menu_view) {
        cc_menu_selection = (cc_menu_selection + (clockwise ? 1 : 5)) % 6;
        cc_dirty = true;
    } else if (cc_screen_selection == CC_SCREEN_LAYERS) {
        if (cc_help_view || cc_color_view) return false;
        cc_preview = (cc_preview + (clockwise ? 1 : omp_layer_count() - 1)) %
                     omp_layer_count();
        cc_home_view = false;
        cc_dirty = true;
    } else if (cc_user_encoder_turn(clockwise)) {
        return false;
    } else if (omp_enabled) {
        omp_tap(omp_profile.layers[cc_active].encoders[clockwise ? 1 : 0]);
        return false;
    } else {
        // Factory encoder never executes stale VIA-EEPROM mappings.
        uint16_t code = clockwise ? cc_layers[cc_active].encoder_cw : cc_layers[cc_active].encoder_ccw;
        if (code != KC_NO && code != KC_TRNS) tap_code16(code);
        return false;
    }
    return false;
}

// ENCODER_MAP_ENABLE delivers rotation as key events instead of calling
// encoder_update_user. Intercept both edges before QMK sends a host keycode.
bool pre_process_record_user(uint16_t keycode, keyrecord_t *record) {
    (void)keycode;
    if (IS_KEYEVENT(record->event)) {
        const uint8_t row = record->event.key.row, col = record->event.key.col;
        if (record->event.pressed) cc_ui_activity();
        if (cc_k9_down && record->event.pressed && !(row == 2 && col == 1))
            cc_k9_chord = true;
        if (cc_nav_alt_down && record->event.pressed) {
            unregister_code(KC_LALT);
            cc_nav_alt_down = false;
        }
        if (cc_matrix_test_view && !cc_internal_mode) {
            cc_matrix_test_record(row, col, record->event.pressed);
            return false;
        }
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
            if (cc_matrix_row[i] != row || cc_matrix_col[i] != col) continue;
            if (cc_ui_menu_key(i, record->event.pressed)) return false;
            if (record->event.pressed) omp_react(OMP_ZONE_KEYS);
            cc_last_key = record->event.pressed ? i : 255;
            if (!cc_home_view) cc_dirty = true;
            if (cc_special_key(i, record->event.pressed)) return false;
            // Fixed K5/K9/K10 have priority over profile and fallback
            // gestures. K9 is physically wired at row 2, column 1.
            if (cc_handle_fixed_modifier(row, col, record->event.pressed)) return false;
            if (omp_enabled) {
                // Exactly one gesture engine can own an event. The former
                // ordering sent K1-K8 through cc_td_event and silently
                // bypassed saved OmniPad Tap Dance / multi-slot actions.
                omp_key_event(i, record->event.pressed);
                return false;
            }
            if (cc_td_event(i, record->event.pressed)) return false;
            // All other keys also use the factory map, never stale VIA EEPROM.
            if (!omp_enabled) {
                const uint16_t factory_code = cc_layers[cc_active].taps[i];
                if (factory_code != KC_NO && factory_code != KC_TRNS) {
                    if (record->event.pressed) register_code16(factory_code);
                    else unregister_code16(factory_code);
                }
                return false;
            }
            break;
        }
        return true;
    }
    if (!IS_ENCODEREVENT(record->event)) return true;
    if (!record->event.pressed) {
        if (cc_internal_mode || cc_active == CC_NAV_LAYER ||
            cc_active == CC_TEXT_LAYER || cc_active == CC_RGB_LAYER ||
            cc_active == CC_MACRO_LAYER) return false;
        return !omp_enabled && !cc_matrix_test_view && !cc_display_mode && !cc_menu_view;
    }
    return cc_encoder_rotate(record->event.key.row == KEYLOC_ENCODER_CW);
}

// CC Studio analog slider (GP28): relative Ctrl+Numpad+/− zoom.
// Movement is quantized around the last position, never jumps at startup.
static int16_t cc_zoom_reference = -1;
static uint8_t cc_zoom_layer = 255;
static void cc_zoom_slider_update(int16_t sample) {
    if (sample < 0) return;
    if (cc_zoom_layer != cc_active) { cc_zoom_layer = cc_active; cc_zoom_reference = -1; }
    if (cc_zoom_reference < 0) { cc_zoom_reference = sample; return; }
    // 64 ADC units plus upstream ~1% noise filter; cap burst at 3 steps.
    for (uint8_t steps = 0; steps < 3; ++steps) {
        const int16_t delta = sample - cc_zoom_reference;
        if (delta < 64 && delta > -64) break;
        const bool upward = delta > 0;
        cc_zoom_reference += upward ? 64 : -64;
        switch (cc_active) {
            case 0: case 1: case 2: case 4:
                tap_code16(upward ? LCTL(KC_PPLS) : LCTL(KC_PMNS));
                break;
            case 3:
                tap_code16(upward ? MS_WHLU : MS_WHLD);
                break;
            case CC_MEDIA_LAYER:
                tap_code16(upward ? KC_VOLU : KC_VOLD);
                break;
            case CC_RGB_LAYER:
                cc_rgb_key(upward ? 6 : 5);
                break;
            default: break;
        }
    }
}

void housekeeping_task_user(void) {
    cc_td_tick();
    cc_nav_alt_tick();
    cc_ui_timeout_tick();
    if (cc_eeprom_confirm && timer_elapsed(cc_eeprom_confirm_at) >= 15000u) {
        cc_eeprom_confirm = false;
        cc_dirty = true;
    }
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
    static bool qmk_suspended;
    static bool master_was_on = true;
    if (omp_preview_active && (cc_matrix_test_view || timer_elapsed(omp_preview_at) >= OMP_LED_PREVIEW_MS))
        omp_preview_active = false;
    const bool own_leds = omp_preview_active || cc_visual_profile_available;
    if (own_leds || !cc_rgb_master_enabled) {
        rgblight_timer_disable();
        qmk_suspended = true;
    } else if (qmk_suspended) {
        rgblight_timer_enable();
        rgblight_sethsv_noeeprom(rgblight_get_hue(), rgblight_get_sat(), rgblight_get_val());
        cc_main_dirty = cc_frame_dirty = true;
        qmk_suspended = false;
    }
    if (!cc_rgb_master_enabled) {
        if (master_was_on) {
            rgblight_driver.set_color_all(0, 0, 0);
            rgblight_driver.flush();
        }
    } else if (!cc_tester_preview_leds()) {
        if (own_leds) omp_lighting_tick(omp_preview_active);
        else cc_rgb_tick();
    }
    master_was_on = cc_rgb_master_enabled;
#endif
    omp_actions_tick();
    if (cc_matrix_test_view && omp_enabled && omp_down_mask) omp_release_all();
    if (timer_elapsed(cc_slider_last_sample) >= 35) {
        cc_slider_last_sample = timer_read();
        const int16_t sample = analogReadPin(SLIDER_ADC_PIN);
        if (sample >= 0) {
            uint16_t previous_pct = cc_slider_pct;
            cc_slider_raw = cc_slider_valid ? omp_slider_filter_adc(sample, cc_slider_raw) : (uint16_t)sample;
            const uint16_t value = omp_slider_value(cc_slider_raw);
            cc_slider_pct = ((uint32_t)value * 100u + 511u) / 1023u;
            if (cc_slider_valid && cc_slider_pct != previous_pct) omp_react(OMP_ZONE_SLIDER);
            cc_slider_valid = true;
            if (cc_matrix_test_view || cc_custom_screen_selected()) {
                if (cc_slider_pct != previous_pct) cc_dirty = true;
            }
            if (!cc_matrix_test_view && !cc_menu_view) {
                if (omp_enabled) omp_slider_update(value);
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
    if (cc_dirty && timer_elapsed(cc_last_draw) >= 35 && !omp_display_waits_for_input()) cc_redraw();
}
