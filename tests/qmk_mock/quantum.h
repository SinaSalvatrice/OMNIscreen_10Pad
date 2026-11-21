// Minimal QMK contract for native unit tests of cc_editor_modifiers.h.
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <limits.h>
#define KC_LCTL 0xE0u
#define KC_RGUI 0xE7u
#define QK_MODS 0x0100u
#define QK_MODS_MAX 0x1FFFu
#define QK_RMODS_MIN 0x1000u
#define IS_MODIFIER_KEYCODE(code) ((code) >= KC_LCTL && (code) <= KC_RGUI)
#define IS_QK_MODS(code) ((code) >= QK_MODS && (code) <= QK_MODS_MAX)
void add_mods(uint8_t);
void del_mods(uint8_t);
void send_keyboard_report(void);
