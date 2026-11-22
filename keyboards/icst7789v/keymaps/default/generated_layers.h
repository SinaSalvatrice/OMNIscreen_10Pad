// GENERATED from design/layer_system.json: never edit manually.
// Regenerate with: python scripts/generate_layer_system.py
#pragma once
#include <stdint.h>
#define CC_LAYER_COUNT 8
#define CC_KEY_COUNT 10
typedef struct {
  const char *name;
  uint16_t accent_rgb565;
  const char *labels[CC_KEY_COUNT];
  uint16_t taps[CC_KEY_COUNT];
  uint16_t holds[CC_KEY_COUNT];
  uint16_t encoder_ccw;
  uint16_t encoder_cw;
  uint16_t encoder_press;
  uint16_t icon[16];
} cc_layer_desc_t;
typedef struct { uint16_t x, y, w, h; } cc_key_shape_t;
static const cc_key_shape_t cc_key_shapes[CC_KEY_COUNT] = {
  {125, 40, 43, 47},
  {172, 40, 43, 47},
  {219, 40, 43, 47},
  {266, 40, 43, 47},
  {125, 95, 43, 102},
  {172, 95, 43, 47},
  {219, 95, 43, 47},
  {266, 95, 43, 47},
  {172, 150, 90, 47},
  {266, 150, 43, 47},
};
static const uint8_t cc_matrix_row[CC_KEY_COUNT] = {0, 0, 0, 0, 1, 1, 1, 1, 2, 2};
static const uint8_t cc_matrix_col[CC_KEY_COUNT] = {0, 1, 2, 3, 0, 1, 2, 3, 1, 3};
static const cc_layer_desc_t cc_layers[CC_LAYER_COUNT] = {
  {"CCSTUDIO", 0xCC2B,
   {"HIDE", "LOCK", "PLAY", "VIEW", "SHIFT", "COMP", "ANIM", "PICK", "CTRL", "ALT"},
   {LCTL(LALT(KC_1)), LCTL(LALT(KC_2)), LCTL(LALT(KC_3)), LCTL(LALT(KC_4)), KC_LSFT, LCTL(LALT(KC_6)), LCTL(LALT(KC_7)), LCTL(LALT(KC_8)), KC_LCTL, KC_LALT},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   MS_WHLU, MS_WHLD, MS_BTN1,
   {0x0180, 0x0180, 0x1998, 0x0FF0, 0x07E0, 0x3FFC, 0x07E0, 0x0FF0, 0x1998, 0x0180, 0x0180, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000}},
  {"DEFAULT", 0x6D3C,
   {"ESC", "ENTER", "TAB", "BKSP", "SHIFT", "DEL", "EXPL", "DESK", "CTRL", "ALT"},
   {KC_ESC, KC_ENT, KC_TAB, KC_BSPC, KC_LSFT, KC_DEL, LGUI(KC_E), LGUI(KC_D), KC_LCTL, KC_LALT},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   MS_WHLU, MS_WHLD, MS_BTN1,
   {0x0180, 0x03C0, 0x07E0, 0x0E70, 0x1C38, 0x381C, 0x718E, 0x399C, 0x1DB8, 0x0F70, 0x07E0, 0x03C0, 0x0180, 0x0000, 0x0000, 0x0000}},
  {"NAV", 0x7EB9,
   {"HOME", "PGUP", "UP", "END", "SHIFT", "LEFT", "DOWN", "RIGHT", "CTRL", "ALT"},
   {KC_HOME, KC_PGUP, KC_UP, KC_END, KC_LSFT, KC_LEFT, KC_DOWN, KC_RGHT, KC_LCTL, KC_LALT},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   KC_NO, KC_NO, KC_NO,
   {0x0180, 0x03C0, 0x07E0, 0x0E70, 0x1C38, 0x381C, 0x718E, 0x399C, 0x1DB8, 0x0F70, 0x07E0, 0x03C0, 0x0180, 0x0000, 0x0000, 0x0000}},
  {"TEXT", 0xDD59,
   {"UNDO", "REDO", "BOLD", "ITAL", "SHIFT", "COPY", "PASTE", "CUT", "SPACE", "ENTER"},
   {LCTL(KC_Y), LCTL(KC_Z), LCTL(KC_B), LCTL(KC_I), KC_LSFT, LCTL(KC_C), LCTL(KC_V), LCTL(KC_X), KC_SPC, KC_ENT},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   KC_LEFT, KC_RGHT, MS_BTN1,
   {0x3FFC, 0x3FFC, 0x03C0, 0x03C0, 0x03C0, 0x03C0, 0x03C0, 0x03C0, 0x03C0, 0x03C0, 0x0FF0, 0x0FF0, 0x0000, 0x0000, 0x0000, 0x0000}},
  {"SHORTCUT", 0xED8E,
   {"COPY", "PASTE", "CUT", "ALL", "SHIFT", "UNDO", "REDO", "SAVE", "CLIP", "SHOT"},
   {LCTL(KC_C), LCTL(KC_V), LCTL(KC_X), LCTL(KC_A), KC_LSFT, LCTL(KC_Y), LCTL(KC_Z), LCTL(KC_S), LGUI(KC_V), LGUI(LSFT(KC_S))},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   LCTL(KC_Y), LCTL(KC_Z), LCTL(KC_S),
   {0x03C0, 0x1DB8, 0x33CC, 0x366C, 0x3C3C, 0x781E, 0x781E, 0x3C3C, 0x366C, 0x33CC, 0x1DB8, 0x03C0, 0x0000, 0x0000, 0x0000, 0x0000}},
  {"MACROS", 0xB4BB,
   {"M1", "M2", "M3", "M4", "REC", "M5", "M6", "M7", "PLAY", "BANK"},
   {QK_MACRO_0, QK_MACRO_1, QK_MACRO_2, QK_MACRO_3, KC_NO, QK_MACRO_4, QK_MACRO_5, QK_MACRO_6, KC_NO, KC_NO},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   KC_NO, KC_NO, KC_NO,
   {0x0C30, 0x0C30, 0x3FFC, 0x3FFC, 0x0C30, 0x0C30, 0x3FFC, 0x3FFC, 0x0C30, 0x0C30, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000}},
  {"SETTINGS", 0x95F0,
   {"RGB", "HUE-", "HUE+", "SAVE", "ZONE", "BRI-", "BRI+", "SPEED", "PAL", "BACK"},
   {UG_TOGG, UG_HUED, UG_HUEU, KC_NO, KC_NO, UG_VALD, UG_VALU, UG_SPDU, KC_NO, KC_NO},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   KC_NO, KC_NO, KC_NO,
   {0x1800, 0x1E00, 0x1F80, 0x1FE0, 0x1FF8, 0x1FFE, 0x1FFE, 0x1FF8, 0x1FE0, 0x1F80, 0x1E00, 0x1800, 0x0000, 0x0000, 0x0000, 0x0000}},
  {"MEDIA", 0xF5CE,
   {"MUTE", "VOL-", "VOL+", "STOP", "SHIFT", "PREV", "NEXT", "PLAY", "CTRL", "ALT"},
   {KC_MUTE, KC_VOLD, KC_VOLU, KC_MSTP, KC_LSFT, KC_MPRV, KC_MNXT, KC_MPLY, KC_LCTL, KC_LALT},
   {KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO, KC_NO},
   KC_MPRV, KC_MNXT, KC_MPLY,
   {0x0180, 0x03C0, 0x07E0, 0x0E70, 0x1C38, 0x381C, 0x718E, 0x399C, 0x1DB8, 0x0F70, 0x07E0, 0x03C0, 0x0180, 0x0000, 0x0000, 0x0000}},
};
