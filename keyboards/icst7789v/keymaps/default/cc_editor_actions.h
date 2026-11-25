// Runtime actions. Every press keeps its original configuration until release.
#pragma once
#include "action.h"
#include "cc_editor_modifiers.h"

typedef struct {
    bool down, holding;
    uint8_t taps, layer, origin_layer;
    uint16_t pressed_at, released_at, held_code;
    omp_key_t key;
} omp_key_state_t;

static omp_key_state_t omp_keys[OMP_KEYS];
static uint8_t omp_cycles[OMP_LAYERS][OMP_KEYS];
static uint16_t omp_down_mask;
static uint8_t omp_last_key = 255;
static uint8_t omp_last_gesture;
static uint8_t omp_last_layer = 255;
static int16_t omp_slider_reference = -1;
static bool omp_matrix_override;
static omp_zone_t omp_runtime_matrix;
static bool omp_native_lighting(uint16_t code, bool pressed);
static void omp_react(uint8_t zone);
static bool omp_device_action(uint16_t code, bool pressed);
static uint8_t omp_brightness_override[2] = {255, 255};
static uint16_t omp_macro_position, omp_macro_end, omp_macro_wait;
static uint16_t omp_macro_timer;
static bool omp_macro_running;
static uint16_t omp_macro_held[16];
static uint8_t omp_macro_held_count;
static uint8_t omp_macro_queue[8], omp_macro_head, omp_macro_tail;
static uint16_t omp_held_codes[32];
static uint8_t omp_held_refs[32];
static uint16_t omp_taps[32];
static uint8_t omp_tap_head, omp_tap_tail;
static uint16_t omp_tap_active, omp_tap_timer;

// A synchronous TFT draw can span several taps or extend a short HID pulse.
static bool omp_display_waits_for_input(void) {
    if (omp_tap_active || omp_tap_head != omp_tap_tail) return true;
    for (uint8_t index = 0; index < OMP_KEYS; ++index) {
        const omp_key_state_t *state = &omp_keys[index];
        if (state->key.mode == 1 && !state->holding && (state->down || state->taps)) return true;
    }
    return false;
}

static void omp_emit(uint16_t code, bool pressed) {
    if (code <= KC_TRNS || omp_device_action(code, pressed) || omp_native_lighting(code, pressed)) return;
    uint8_t slot;
    for (slot = 0; slot < ARRAY_SIZE(omp_held_codes); ++slot) {
        if (omp_held_refs[slot] && omp_held_codes[slot] == code) break;
    }
    if (pressed) {
        if (slot < ARRAY_SIZE(omp_held_codes)) {
            ++omp_held_refs[slot];
            return;
        }
        for (slot = 0; slot < ARRAY_SIZE(omp_held_codes); ++slot) if (!omp_held_refs[slot]) break;
        if (slot == ARRAY_SIZE(omp_held_codes)) return;
        omp_held_codes[slot] = code;
        omp_held_refs[slot] = 1;
    } else {
        if (slot == ARRAY_SIZE(omp_held_codes) || --omp_held_refs[slot]) return;
    }
    // Shortcuts require strong modifiers: QMK clears weak modifiers whenever
    // another physical key event arrives. This used to turn Undo into plain Z.
    if (IS_QK_MODS(code)) {
        const uint8_t key = QK_MODS_GET_BASIC_KEYCODE(code);
        const uint8_t mods = omp_mod_mask(code);
        // Send the key and its modifiers in the same keyboard report.
        const bool changed = omp_mod_change(mods, pressed);
        if (key != KC_NO) {
            if (pressed) register_code(key);
            else unregister_code(key);
        } else if (changed) {
            send_keyboard_report();
        }
        return;
    }
    if (IS_MODIFIER_KEYCODE(code)) {
        omp_mod_update(omp_mod_mask(code), pressed);
        return;
    }

    // Layer actions should not depend on a synthetic QMK row/column event.
    // In particular the second Tap Dance slot can enter a layer directly.
    if (IS_QK_TO(code)) {
        if (pressed && QK_TO_GET_LAYER(code) < omp_profile.layer_count)
            layer_move(QK_TO_GET_LAYER(code));
        return;
    }
    if (IS_QK_MOMENTARY(code)) {
        if (QK_MOMENTARY_GET_LAYER(code) < omp_profile.layer_count) {
            if (pressed) layer_on(QK_MOMENTARY_GET_LAYER(code));
            else layer_off(QK_MOMENTARY_GET_LAYER(code));
        }
        return;
    }
    if (IS_QK_TOGGLE_LAYER(code)) {
        if (pressed && QK_TOGGLE_LAYER_GET_LAYER(code) < omp_profile.layer_count)
            layer_invert(QK_TOGGLE_LAYER_GET_LAYER(code));
        return;
    }

    // Other QMK keycodes continue using the standard QMK action decoder.
    keyrecord_t record = {
        .event = {.key = {.row = 0, .col = 0}, .pressed = pressed, .time = timer_read(), .type = KEY_EVENT},
    };
    process_action(&record, action_for_keycode(code));
}

static void omp_macro_stop(void) {
    for (uint8_t i = 0; i < omp_macro_held_count; ++i) omp_emit(omp_macro_held[i], false);
    omp_macro_held_count = 0;
    omp_macro_running = false;
}

static void omp_start_macro(uint8_t index) {
    if (index >= omp_profile.snippet_count) return;
    if (omp_macro_running) {
        uint8_t next = (omp_macro_tail + 1u) % ARRAY_SIZE(omp_macro_queue);
        if (next != omp_macro_head) {
            omp_macro_queue[omp_macro_tail] = index;
            omp_macro_tail = next;
        }
        return;
    }
    const omp_macro_t *macro = &omp_profile.snippets[index];
    omp_macro_position = macro->start;
    omp_macro_end = macro->start + macro->length;
    omp_macro_timer = timer_read();
    omp_macro_wait = 0;
    omp_macro_running = true;
}

static void omp_tap(uint16_t code) {
    if (code <= KC_TRNS) return;
    if (code >= QK_MACRO_0 && code <= QK_MACRO_15) {
        omp_start_macro(code - QK_MACRO_0);
        return;
    }
    uint8_t next = (omp_tap_tail + 1u) % ARRAY_SIZE(omp_taps);
    if (next == omp_tap_head) return;
    omp_taps[omp_tap_tail] = code;
    omp_tap_tail = next;
}

static void omp_release_all(void) {
    for (uint8_t i = 0; i < OMP_KEYS; ++i) {
        if (omp_keys[i].holding) omp_emit(omp_keys[i].held_code, false);
        memset(&omp_keys[i], 0, sizeof(omp_keys[i]));
    }
    omp_macro_stop();
    omp_macro_head = omp_macro_tail = 0;
    if (omp_tap_active) omp_emit(omp_tap_active, false);
    omp_tap_active = 0;
    omp_tap_head = omp_tap_tail = 0;
    omp_down_mask = 0;
    omp_mod_release_all();
}

static void omp_finish_dance(uint8_t index) {
    omp_key_state_t *state = &omp_keys[index];
    if (!state->taps) return;
    uint8_t gesture = state->taps > 4 ? 3 : state->taps - 1;
    omp_tap(state->key.codes[gesture]);
    omp_last_key = index;
    omp_last_gesture = gesture + 1;
    state->taps = 0;
    cc_dirty = true;
}

static bool omp_key_event(uint8_t index, bool pressed) {
    if (!omp_enabled || index >= OMP_KEYS) return false;
    omp_key_state_t *state = &omp_keys[index];
    if (pressed) {
        if (state->down) return true;
        if (state->taps && (state->origin_layer != cc_active ||
            timer_elapsed(state->released_at) >= state->key.term)) omp_finish_dance(index);
        if (!state->taps) {
            state->origin_layer = cc_active;
            state->layer = cc_active;
            state->key = omp_profile.layers[cc_active].keys[index];
            if (state->key.mode == 0 && state->key.codes[0] == KC_TRNS) {
                layer_state_t active = layer_state | default_layer_state | 1u;
                for (int8_t lower = cc_active - 1; lower >= 0; --lower) {
                    if ((active & ((layer_state_t)1u << lower)) && lower < omp_profile.layer_count) {
                        state->key = omp_profile.layers[lower].keys[index];
                        state->layer = lower;
                        if (state->key.mode || state->key.codes[0] != KC_TRNS) break;
                    }
                }
            }
        }
        state->down = true;
        state->pressed_at = timer_read();
        omp_down_mask |= 1u << index;
        omp_last_key = index;
        omp_last_gesture = 0;
        if (!cc_home_view) cc_dirty = true;
        if (state->key.mode == 0) {
            uint16_t code = state->key.codes[0];
            if (code >= QK_MACRO_0 && code <= QK_MACRO_15) omp_tap(code);
            else {
                state->holding = true;
                state->held_code = code;
                omp_emit(code, true);
            }
        } else if (state->key.mode == 2) {
            uint8_t *next = &omp_cycles[state->layer][index];
            for (uint8_t attempt = 0; attempt < 4; ++attempt) {
                uint8_t position = *next;
                *next = (*next + 1u) % 4u;
                if (state->key.codes[position] > KC_TRNS) {
                    omp_tap(state->key.codes[position]);
                    omp_last_gesture = position + 1;
                    break;
                }
            }
        }
    } else {
        if (!state->down) return true;
        state->down = false;
        omp_down_mask &= ~(1u << index);
        if (state->holding) {
            omp_emit(state->held_code, false);
            state->holding = false;
            state->taps = 0;
        } else if (state->key.mode == 1) {
            state->released_at = timer_read();
            ++state->taps;
            if (state->taps >= 4) omp_finish_dance(index);
        }
        if (!cc_home_view) cc_dirty = true;
    }
    return true;
}

static void omp_actions_tick(void) {
    if (!omp_enabled) return;
    for (uint8_t index = 0; index < OMP_KEYS; ++index) {
        omp_key_state_t *s = &omp_keys[index];
        if (s->key.mode != 1) continue;
        uint16_t hold_term = index == 11 && s->key.codes[4] == OMP_ACTION_MENU ? 2000u : s->key.term;
        if (s->down && !s->holding && timer_elapsed(s->pressed_at) >= hold_term &&
            s->key.codes[4] > KC_TRNS) {
            s->holding = true;
            s->held_code = s->key.codes[4];
            s->taps = 0;
            if (s->held_code >= QK_MACRO_0 && s->held_code <= QK_MACRO_15) {
                omp_tap(s->held_code);
                s->held_code = KC_NO;
            } else omp_emit(s->held_code, true);
            omp_last_gesture = 5;
            cc_dirty = true;
        } else if (!s->down && s->taps && timer_elapsed(s->released_at) >= s->key.term) {
            omp_finish_dance(index);
        }
    }
    if (omp_tap_active) {
        if (timer_elapsed(omp_tap_timer) < 8) return;
        omp_emit(omp_tap_active, false);
        omp_tap_active = 0;
        omp_tap_timer = timer_read();
        return;
    }
    if (timer_elapsed(omp_tap_timer) < 8) return;
    if (omp_tap_head != omp_tap_tail) {
        omp_tap_active = omp_taps[omp_tap_head];
        omp_tap_head = (omp_tap_head + 1u) % ARRAY_SIZE(omp_taps);
        omp_emit(omp_tap_active, true);
        omp_tap_timer = timer_read();
        return;
    }
    if (!omp_macro_running && omp_macro_head != omp_macro_tail) {
        uint8_t next = omp_macro_queue[omp_macro_head];
        omp_macro_head = (omp_macro_head + 1u) % ARRAY_SIZE(omp_macro_queue);
        omp_start_macro(next);
    }
    if (!omp_macro_running || timer_elapsed(omp_macro_timer) < omp_macro_wait) return;
    if (omp_macro_position >= omp_macro_end) {
        omp_macro_stop();
        return;
    }
    const uint8_t *step = &omp_profile.macro_pool[omp_macro_position];
    uint16_t code = step[1] | ((uint16_t)step[2] << 8);
    omp_macro_position += 3;
    omp_macro_timer = timer_read();
    omp_macro_wait = 8;
    switch (step[0]) {
        case 1: omp_tap(code); break;
        case 2:
            if (omp_macro_held_count < ARRAY_SIZE(omp_macro_held)) {
                omp_macro_held[omp_macro_held_count++] = code;
                omp_emit(code, true);
            }
            break;
        case 3:
            for (uint8_t i = 0; i < omp_macro_held_count; ++i) {
                if (omp_macro_held[i] == code) {
                    omp_emit(code, false);
                    omp_macro_held[i] = omp_macro_held[--omp_macro_held_count];
                    break;
                }
            }
            break;
        case 4: omp_macro_wait = code; break;
    }
}

static void omp_layer_changed(void) {
    if (omp_last_layer == cc_active) return;
    omp_last_layer = cc_active;
    omp_slider_reference = -1;
    omp_matrix_override = false;
    omp_brightness_override[0] = omp_brightness_override[1] = 255;
    omp_react(OMP_ZONE_DISPLAY);
    // Pending multi-taps keep the actions captured on their original layer.
}

static uint16_t omp_slider_filter_adc(uint16_t sample, uint16_t previous) {
    const omp_slider_t *slider = omp_enabled ? &omp_profile.layers[cc_active].slider : NULL;
    const uint16_t minimum = slider ? slider->minimum : 0;
    const uint16_t maximum = slider ? slider->maximum : 1023;
    const uint16_t band = (maximum - minimum + 99u) / 100u;
    const uint16_t delta = sample > previous ? sample - previous : previous - sample;
    // About 1% of the calibrated travel, with at least two ADC counts.
    // Entering a calibrated endpoint bypasses the band so 0% and 100% remain reachable.
    if (delta > (band < 2u ? 2u : band) ||
        (sample <= minimum && previous > minimum) ||
        (sample >= maximum && previous < maximum)) return sample;
    return previous;
}

// A larger logical value follows the physically corrected orientation.
// The existing reverse field is an optional override, including old profiles.
static uint16_t omp_slider_value(uint16_t raw) {
    const omp_slider_t *slider = omp_enabled ? &omp_profile.layers[cc_active].slider : NULL;
    uint16_t minimum = slider ? slider->minimum : 0;
    uint16_t maximum = slider ? slider->maximum : 1023;
    if (raw < minimum) raw = minimum;
    if (raw > maximum) raw = maximum;
    uint16_t value = (uint32_t)(raw - minimum) * 1023u / (maximum - minimum);
    return slider && slider->reverse ? value : 1023u - value;
}

static void omp_slider_update(int16_t value) {
    const omp_slider_t *slider = &omp_profile.layers[cc_active].slider;
    if (omp_slider_reference < 0) {
        omp_slider_reference = value;
        return;
    }
    int16_t delta = value - omp_slider_reference;
    if (!delta || (delta > -(int16_t)slider->deadband && delta < slider->deadband)) return;
    if (slider->mode >= 2 && slider->mode <= 4) {
        uint8_t brightness = ((uint32_t)value * RGBLIGHT_LIMIT_VAL + 511u) / 1023u;
        if (slider->mode != 3) omp_brightness_override[0] = brightness;
        if (slider->mode != 2) omp_brightness_override[1] = brightness;
        omp_slider_reference = value;
    } else if (slider->mode == 5) {
        // Fallback must work with no PC app: emit relative volume events.
        // The editor can still read telemetry, but must not apply volume twice.
        if (delta >= slider->step || delta <= -(int16_t)slider->step) {
            omp_tap(delta > 0 ? KC_VOLU : KC_VOLD);
            omp_slider_reference += delta > 0 ? slider->step : -(int16_t)slider->step;
            }
    } else if (slider->mode == 1 && (delta >= slider->step || delta <= -(int16_t)slider->step)) {
        omp_tap(delta > 0 ? slider->high : slider->low);
        omp_slider_reference += delta > 0 ? slider->step : -(int16_t)slider->step;
    }
}
