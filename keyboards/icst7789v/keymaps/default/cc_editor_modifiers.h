// Strong, reference-counted modifiers for OmniPad's generated host actions.
// QMK's QK_MODS actions use weak mods, which are cleared on a new key event.
// A shortcut held through a redraw or overlapping key press must not lose Ctrl.
#pragma once
#include "quantum.h"

static uint8_t omp_mod_refs[8];

// The low four bits encode Ctrl/Shift/Alt/GUI; QK_RMODS_MIN moves them right.
static uint8_t omp_mod_mask(uint16_t code) {
    if (IS_MODIFIER_KEYCODE(code)) return (uint8_t)(1u << (code - KC_LCTL));
    if (!IS_QK_MODS(code)) return 0;
    uint8_t bits = (uint8_t)((code >> 8) & 0x0Fu);
    return code & QK_RMODS_MIN ? (uint8_t)(bits << 4) : bits;
}

static void omp_mod_update(uint8_t mask, bool pressed) {
    uint8_t changed = 0;
    for (uint8_t bit = 0; bit < 8; ++bit) {
        uint8_t flag = (uint8_t)(1u << bit);
        if (!(mask & flag)) continue;
        if (pressed) {
            if (!omp_mod_refs[bit]) changed |= flag;
            if (omp_mod_refs[bit] < UINT8_MAX) ++omp_mod_refs[bit];
        } else if (omp_mod_refs[bit]) {
            if (!--omp_mod_refs[bit]) changed |= flag;
        }
    }
    if (!changed) return;
    if (pressed) add_mods(changed);
    else del_mods(changed);
    send_keyboard_report();
}

static void omp_mod_release_all(void) {
    uint8_t leftover = 0;
    for (uint8_t bit = 0; bit < 8; ++bit) {
        if (omp_mod_refs[bit]) leftover |= (uint8_t)(1u << bit);
        omp_mod_refs[bit] = 0;
    }
    if (leftover) {
        del_mods(leftover);
        send_keyboard_report();
    }
}
