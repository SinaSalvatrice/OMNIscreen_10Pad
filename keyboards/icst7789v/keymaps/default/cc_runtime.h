// 320x240 Layer Map runtime. Included only from keymap.c after SPI routines.
#pragma once
#include "cc_font.h"
#include "cc_editor_types.h"
#include <stdlib.h>
#include <stdio.h> // Compact numeric diagnostics for the matrix tester.
#if CC_PCF8575_MATRIX
extern bool cc_pcf8575_online(void);
extern uint8_t cc_pcf8575_address(void);
extern uint16_t cc_pcf8575_unassigned_low(void);
#endif
#define CC_K0_TAPS_MS 250
#define CC_K0_HOLD_MS 620
#define CC_DEBOUNCE_MS 25
#define CC_EEPROM_HOLD_MS 5000u

static uint8_t cc_active = 1;
static uint8_t cc_previous = 0;
static uint8_t cc_preview = 1;
static uint8_t cc_last_key = 255;
static uint8_t cc_menu_selection = 0;
static bool cc_display_mode = true;
static bool cc_home_view = false;
static bool cc_menu_view = false;
// Protected firmware menus do not consume QMK/VIA layer slots.
static uint8_t cc_internal_mode = 0; // 0 normal, 1 system, 2 display, 3 info
static uint8_t cc_internal_selected = 0;
static uint8_t cc_internal_confirm = 255;
static bool cc_internal_skip_k0_release = false;
static bool cc_use_app_profile = false; // persisted config source
static bool cc_visual_profile_available = false; // templates work in firmware mode
static bool cc_rgb_master_enabled = true; // persisted RGB power
static void cc_internal_press(uint8_t index);
static void cc_user_layer_change(uint8_t from, uint8_t to);
static bool cc_help_view = false;
static bool cc_color_view = false;
static bool cc_matrix_test_view = false;
static bool cc_tester_active;
typedef enum { CC_SCREEN_AUTO, CC_SCREEN_LAYERS, CC_SCREEN_CUSTOM,
               CC_SCREEN_NAV, CC_SCREEN_DETAILS } cc_screen_selection_t;
static cc_screen_selection_t cc_screen_selection;
static bool cc_eeprom_confirm;
static bool cc_eeprom_confirm_visible;
static uint16_t cc_eeprom_confirm_at;
// Stabilized ADC count (0..1023) and calibrated position.
static uint16_t cc_slider_raw = 0;
static uint16_t cc_slider_pct = 0;
static uint16_t cc_slider_last_sample = 0;
static uint16_t cc_slider_last_drawn = UINT16_MAX;
static bool cc_slider_valid = false;
// Physical switch status is tracked separately from QMK Tap Dance.
static bool cc_matrix_down[CC_KEY_COUNT] = {false};
static matrix_row_t cc_matrix_sampled[MATRIX_ROWS];
static uint16_t cc_matrix_changed = 0;
static uint16_t cc_matrix_hits = 0;
static uint8_t cc_matrix_last_key = 255;
static bool cc_matrix_full_redraw = true;
static bool cc_matrix_return_home = true;
static bool cc_matrix_return_encoder_mode = true;
static uint8_t cc_matrix_return_preview = 0;
static bool cc_dirty = true;
static uint16_t cc_last_draw = 0;
#if CC_PCF8575_MATRIX
static bool cc_pcf_last_online = false;
#endif

typedef struct {
    bool sample;
    bool stable;
    uint16_t changed;
} cc_button_t;
static cc_button_t cc_k0 = {true, true, 0};
static cc_button_t cc_encoder_button = {true, true, 0};
static uint8_t cc_k0_tap_count = 0;
static uint16_t cc_k0_pressed = 0;
static uint16_t cc_k0_released = 0;
static bool cc_k0_held = false;
typedef enum { CC_RESET_WAIT_RELEASE, CC_RESET_IDLE, CC_RESET_HOLDING } cc_reset_state_t;
static cc_reset_state_t cc_reset_state;

static const uint8_t *cc_glyph(char ch) {
    if (ch >= '0' && ch <= '9') return font_numbers[ch - '0'];
    if (ch >= 'A' && ch <= 'Z') return font_letters[ch - 'A'];
    static const uint8_t dash[5] = {0, 0x08, 0x08, 0x08, 0};
    static const uint8_t colon[5] = {0, 0x36, 0x36, 0, 0};
    static const uint8_t slash[5] = {0x20, 0x10, 0x08, 0x04, 0x02};
    static const uint8_t plus[5] = {0x08, 0x08, 0x3E, 0x08, 0x08};
    static const uint8_t dot[5] = {0, 0x40, 0x40, 0, 0};
    if (ch == '-') return dash;
    if (ch == ':') return colon;
    if (ch == '/') return slash;
    if (ch == '+') return plus;
    if (ch == '.') return dot;
    return NULL;
}

static void cc_draw_text(uint16_t x, uint16_t y, const char *str, uint8_t scale, uint16_t color) {
    for (uint8_t n = 0; *str && n < 52 && x + 5u * scale < LCD_W; n++, str++) {
        const uint8_t *glyph = cc_glyph(*str);
        if (glyph) {
            for (uint8_t i = 0; i < 5; i++) {
                for (uint8_t j = 0; j < 7; j++) {
                    if (glyph[i] & (1u << j)) {
                        lcd_fill(x + i * scale, y + j * scale, scale, scale, color);
                    }
                }
            }
        }
        x += 6u * scale;
    }
}

static void cc_draw_icon(uint8_t layer_index, uint16_t accent) {
    const cc_layer_desc_t *desc = &cc_layers[layer_index < CC_LAYER_COUNT ? layer_index : 0];
    for (uint8_t y = 0; y < 16; ++y) {
        for (uint8_t x = 0; x < 16; ++x) {
            if (desc->icon[y] & ((uint16_t)0x8000u >> x)) {
                lcd_fill(29 + x * 4, 63 + y * 4, 4, 4, accent);
            }
        }
    }
}

static void cc_activate_layer(uint8_t layer_index) {
    if (layer_index >= omp_layer_count()) return;
    if (cc_active != layer_index) {
        cc_user_layer_change(cc_active, layer_index);
        cc_previous = cc_active;
    }
    cc_active = layer_index;
    cc_preview = layer_index;
    cc_home_view = false; // The active layer map IS the home view.
    cc_display_mode = false;
    cc_screen_selection = CC_SCREEN_DETAILS;
    cc_menu_view = false;
    cc_help_view = false;
    cc_color_view = false;
    cc_matrix_test_view = false;
    cc_last_key = 255;
    layer_move(layer_index); // Actual exclusive QMK layer.
    cc_dirty = true;
}

static void cc_open_home(void) {
    // The only home view is the active layer map, never a separate landing page.
    cc_home_view = false;
    cc_display_mode = false;
    cc_screen_selection = CC_SCREEN_DETAILS;
    cc_preview = cc_active;
    cc_menu_view = cc_help_view = cc_color_view = false;
    cc_dirty = true;
}

static void cc_open_layer_list(void) {
    cc_display_mode = true;
    cc_screen_selection = CC_SCREEN_LAYERS;
    cc_preview = cc_active;
    cc_home_view = cc_menu_view = cc_help_view = cc_color_view = false;
    cc_dirty = true;
}


static void cc_switch_encoder(bool display_mode) {
    cc_display_mode = display_mode;
    cc_menu_view = false;
    cc_help_view = false;
    cc_color_view = false;
    cc_matrix_test_view = false;
    if (!display_mode) {
        cc_preview = cc_active;
        cc_home_view = cc_active == 0;
    }
    cc_dirty = true;
}

// Screen IDs are the same in firmware and desktop profile:
 // 0 HOME, 1 INDEX, 2 DETAILS, 3 SETTINGS, 4 NAVIGATION, 5 TESTER.
static uint8_t cc_view_kind(void) {
    if (cc_matrix_test_view) return 5;
    if (cc_internal_mode || cc_menu_view) return 3;
    if (cc_home_view) return 0;
    if (cc_screen_selection == CC_SCREEN_LAYERS) return 1;
    if (cc_screen_selection == CC_SCREEN_NAV) return 4;
    return 2;
}

static uint16_t cc_view_bg(void) {
    return cc_visual_profile_available ? omp_profile.themes[cc_view_kind()].background : C_BLACK;
}
static uint16_t cc_view_accent(void) {
    return cc_visual_profile_available ? omp_profile.themes[cc_view_kind()].accent : C_CYAN;
}
static uint8_t cc_view_preset(void) {
    return cc_visual_profile_available ? omp_profile.themes[cc_view_kind()].preset : 0;
}
static const char cc_default_footer[] = "ENC HOLD: LIST  K0 HOLD: MENU  K0 3X: TEST";

static void cc_background(const char *footer, uint16_t footer_color) {
    uint16_t bg = cc_view_bg();
    uint16_t panel = cc_view_preset() == 1 ? 0x0000 : 0x18C7;
    lcd_fill(0, 0, LCD_W, LCD_H, bg);
    lcd_fill(0, 0, LCD_W, 27, panel);
    lcd_fill(0, 216, LCD_W, 24, panel);
    lcd_fill(0, 0, LCD_W, 2, cc_view_accent());
    if (cc_view_preset() == 2) {
        // Spectrum: three restrained color rails. Style affects only visuals.
        lcd_fill(0, 2, LCD_W / 3u, 3, cc_view_accent());
        lcd_fill(LCD_W / 3u, 2, LCD_W / 3u, 3, C_CYAN);
        lcd_fill((LCD_W / 3u) * 2u, 2, LCD_W - (LCD_W / 3u) * 2u, 3, C_YELLOW);
    }
    cc_draw_text(7, 9, "CC / OMNIPAD", 1, C_WHITE);
    const char *view_label = cc_matrix_test_view ? "TEST" :
                             cc_internal_mode ? "MENU" :
                             cc_screen_selection == CC_SCREEN_LAYERS ? "LIST" :
                             omp_enabled ? "APP MAP" : "FW MAP";
    cc_draw_text(270, 9, view_label, 1, cc_view_accent());
    if (footer) cc_draw_text(7, 225, footer, 1, footer_color);
}

static void cc_layer_key_tile(uint8_t i, uint8_t selected, const cc_layer_desc_t *desc, uint16_t accent) {
    // Coordinates come from the physical-key geometry in layer_system.json.
    // K5 is double-height; K9 is double-width; K10 is bottom-right.
    const cc_key_shape_t *shape = &cc_key_shapes[i];
    const uint16_t x = shape->x;
    const uint16_t y = shape->y;
    const uint16_t w = shape->w;
    const uint16_t h = shape->h;
    const omp_key_t *key = omp_enabled ? &omp_profile.layers[selected].keys[i] : NULL;
    const char *label = key ? key->label : desc->labels[i];
    const bool highlight = cc_last_key == i;
    lcd_fill(x, y, w, h, highlight ? 0x3A90 : 0x29E8);
    lcd_fill(x, y, w, 2, highlight ? accent : 0x426A);
    cc_draw_text(x + 4, y + 5, "K", 1, 0xAD75);
    if (i < 9) {
        char number[2] = {(char)('1' + i), 0};
        cc_draw_text(x + 10, y + 5, number, 1, 0xAD75);
    } else {
        cc_draw_text(x + 10, y + 5, "10", 1, 0xAD75);
    }
    if (key && key->mode) {
        cc_draw_text(x + w - 22, y + 5, key->mode == 1 ? "TD" : "SEQ", 1, accent);
    }
    const uint8_t columns = MIN(11u, (w - 8u) / 6u);
    const uint8_t length = MIN(strlen(label), 11u);
    uint8_t first = MIN(columns, length);
    if (length > columns) {
        for (uint8_t i = first; i > 0; --i) {
            if (label[i] == ' ') {
                first = i;
                break;
            }
        }
    }
    char line[12] = {0};
    memcpy(line, label, first);
    const uint16_t top = y + h / 2u;
    cc_draw_text(x + 5, top, line, 1, C_WHITE);
    if (length > first) {
        const char *rest = label + first + (label[first] == ' ');
        memset(line, 0, sizeof(line));
        memcpy(line, rest, MIN(strlen(rest), columns));
        cc_draw_text(x + 5, top + 10, line, 1, C_WHITE);
    }
}

// Renderers for distinct protected system screens. The settings/tester
// controls themselves remain firmware-owned; themes never change their actions.

static uint8_t cc_layer_list_last_selection = 255;
static uint8_t cc_layer_list_last_active = 255;
static void cc_layer_index_row(uint8_t i, uint16_t accent) {
    if (i >= omp_layer_count() || i >= OMP_LAYERS) return;
    const uint16_t x = 10 + (i / 6u) * 152u;
    const uint16_t y = 70 + (i % 6u) * 23u;
    const uint16_t color = i == cc_preview ? accent : 0x3206;
    lcd_fill(x, y, 146, 21, color);
    if (i == cc_active) lcd_fill(x, y, 4, 21, C_GREEN);
    const char *name = omp_enabled ? omp_profile.layers[i].name : cc_layers[i].name;
    cc_draw_text(x + 6, y + 7, name, 1, C_WHITE);
}
static void cc_layer_index_screen(bool full_redraw) {
    const uint16_t accent = cc_view_accent();
    if (full_redraw || cc_active != cc_layer_list_last_active) {
        cc_background("K3 UP  K7 DOWN  K9 OPEN  K5 BACK", C_WHITE);
        cc_draw_text(10, 36, "LAYER LIST", 2, accent);
        for (uint8_t i = 0; i < omp_layer_count() && i < OMP_LAYERS; ++i)
            cc_layer_index_row(i, accent);
    } else if (cc_preview != cc_layer_list_last_selection) {
        cc_layer_index_row(cc_layer_list_last_selection, accent);
        cc_layer_index_row(cc_preview, accent);
    }
    cc_layer_list_last_selection = cc_preview;
    cc_layer_list_last_active = cc_active;
}

static void cc_navigation_screen(void) {
    cc_background(cc_default_footer, cc_view_accent());
    const uint16_t accent = cc_view_accent();
    const uint8_t selected = cc_preview < omp_layer_count() ? cc_preview : 0;
    const char *name = omp_enabled ? omp_profile.layers[selected].name : cc_layers[selected].name;
    lcd_fill(16, 50, 288, 132, cc_view_preset() == 1 ? 0x0000 : 0x2186);
    lcd_fill(16, 50, 288, 5, accent);
    cc_draw_text(26, 70, "NAVIGATION", 2, accent);
    cc_draw_text(26, 111, name, 2, C_WHITE);
    cc_draw_text(26, 154, "TURN SELECT  PUSH ENTER", 1, C_WHITE);
}

static void cc_layer_screen(bool full_redraw) {
    static uint8_t drawn_layer, drawn_active, drawn_key = UINT8_MAX;
    static bool drawn_display_mode, drawn_app;
    static uint32_t drawn_generation;
    const uint8_t selected = cc_preview;
    const cc_layer_desc_t *desc = &cc_layers[selected < CC_LAYER_COUNT ? selected : 0];
    const uint16_t accent = cc_visual_profile_available ? cc_view_accent() : desc->accent_rgb565;
    if (full_redraw || selected != drawn_layer || cc_active != drawn_active ||
        cc_display_mode != drawn_display_mode || omp_enabled != drawn_app ||
        omp_generation != drawn_generation) {
        cc_background(cc_default_footer, cc_view_accent());
        lcd_fill(7, 33, 109, 171, 0x2186);
        lcd_fill(7, 33, 109, 4, accent);
        cc_draw_icon(selected, accent);
        cc_draw_text(12, 151, omp_enabled ? omp_profile.layers[selected].name : desc->name, 2, C_WHITE);
        cc_draw_text(12, 180, "K9 2X CC  K0 2X DEF", 1, accent);
        cc_draw_text(12, 192, selected == cc_active ? "ACTIVE" : "PREVIEW", 1, C_WHITE);
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) cc_layer_key_tile(i, selected, desc, accent);
        drawn_layer = selected;
        drawn_active = cc_active;
        drawn_display_mode = cc_display_mode;
        drawn_app = omp_enabled;
        drawn_generation = omp_generation;
    } else if (cc_last_key != drawn_key) {
        if (drawn_key < CC_KEY_COUNT) cc_layer_key_tile(drawn_key, selected, desc, accent);
        if (cc_last_key < CC_KEY_COUNT) cc_layer_key_tile(cc_last_key, selected, desc, accent);
    }
    drawn_key = cc_last_key;
}

// Physical matrix test: highlight held switches, count presses and display R/C.
// No host keycodes or Tap Dance effects may escape while this view is active.
static void cc_matrix_test_enter(void) {
    if (cc_matrix_test_view) return;
    cc_eeprom_confirm = false;
    cc_matrix_return_home = cc_home_view;
    cc_matrix_return_preview = cc_preview;
    cc_matrix_return_encoder_mode = cc_display_mode;
    cc_matrix_test_view = true;
    cc_menu_view = false;
    cc_help_view = false;
    cc_color_view = false;
    cc_display_mode = true;
    cc_matrix_last_key = 255;
    cc_matrix_hits = 0;
    memset(cc_matrix_sampled, 0, sizeof(cc_matrix_sampled));
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) cc_matrix_down[i] = false;
    cc_matrix_changed = (1u << CC_KEY_COUNT) - 1u;
    cc_matrix_full_redraw = true;
    cc_slider_last_drawn = UINT16_MAX;
    cc_slider_last_sample = timer_read() - 60;
    cc_adxl.changed = true;
#if CC_PCF8575_MATRIX
    cc_pcf_last_online = cc_pcf8575_online();
#endif
    cc_dirty = true;
}

static void cc_matrix_test_exit(void) {
    if (!cc_matrix_test_view) return;
    cc_matrix_test_view = false;
    cc_home_view = cc_matrix_return_home;
    cc_preview = cc_matrix_return_preview;
    cc_display_mode = cc_matrix_return_encoder_mode;
    cc_matrix_changed = 0;
    cc_matrix_full_redraw = false;
    cc_dirty = true;
}

static void cc_matrix_test_toggle(void) {
    if (cc_matrix_test_view) cc_matrix_test_exit();
    else cc_matrix_test_enter();
}

// The physical row/column mapping is generated from design/layer_system.json.
static void cc_matrix_test_record(uint8_t row, uint8_t col, bool pressed) {
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
        if (row == cc_matrix_row[i] && col == cc_matrix_col[i]) {
            if (cc_matrix_down[i] != pressed) {
                cc_matrix_down[i] = pressed;
                cc_matrix_changed |= (uint16_t)(1u << i);
                if (pressed) {
                    cc_matrix_last_key = i;
                    if (cc_matrix_hits != UINT16_MAX) ++cc_matrix_hits;
                }
                cc_dirty = true;
            }
            return;
        }
    }
}

static void cc_matrix_key_tile(uint8_t i) {
    const cc_key_shape_t *shape = &cc_key_shapes[i];
    const uint16_t x = shape->x;
    const uint16_t y = shape->y;
    const uint16_t w = shape->w;
    const uint16_t h = shape->h;
    const bool down = cc_matrix_down[i];
    const uint16_t background = down ? 0x05E7 : 0x29E8;
    const uint16_t foreground = down ? C_WHITE : 0xC618;
    lcd_fill(x, y, w, h, background);
    lcd_fill(x, y, w, down ? 5 : 2, down ? C_GREEN : 0x426A);
    char id[4] = {'K', (char)('0' + (i + 1) / 10),
                       (char)('0' + (i + 1) % 10), 0};
    char position[5] = {'R', (char)('0' + cc_matrix_row[i]),
                        'C', (char)('0' + cc_matrix_col[i]), 0};
    cc_draw_text(x + 5, y + 11, id, 1, foreground);
    cc_draw_text(x + 5, y + 27, position, 1, foreground);
    if (h > 70) cc_draw_text(x + 5, y + 65, down ? "DOWN" : "UP", 1, foreground);
}

static void cc_matrix_test_status(void) {
    lcd_fill(8, 115, 107, 89, 0x2186);
    uint8_t active = 0;
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
        if (cc_matrix_down[i]) ++active;
    }
    char count[6];
    (void)snprintf(count, sizeof(count), "%02u", (unsigned)active);
    cc_draw_text(13, 126, "DOWN", 1, C_CYAN);
    cc_draw_text(71, 126, count, 1, C_WHITE);
    (void)snprintf(count, sizeof(count), "%u", (unsigned)cc_matrix_hits);
    cc_draw_text(13, 143, "HITS", 1, C_CYAN);
    cc_draw_text(13, 157, count, 1, C_WHITE);
    if (cc_matrix_last_key == 255) {
        cc_draw_text(13, 175, "LAST -", 1, C_WHITE);
    } else {
        const uint8_t i = cc_matrix_last_key;
        char last[5] = {'K', (char)('0' + (i + 1) / 10),
                            (char)('0' + (i + 1) % 10), 0};
        char rc[5] = {'R', (char)('0' + cc_matrix_row[i]),
                          'C', (char)('0' + cc_matrix_col[i]), 0};
        cc_draw_text(13, 175, last, 1, C_YELLOW);
        cc_draw_text(13, 190, rc, 1, C_WHITE);
    }
}

// Slider lives in the left information panel, away from the ten key tiles.
static void cc_matrix_slider_widget(void) {
    // Preserve the title above (ends at y=69) and status panel below (starts y=115).
    lcd_fill(9, 78, 105, 37, 0x2186);
    cc_draw_text(13, 80, "SLIDER", 1, C_CYAN);
    lcd_fill(13, 95, 97, 8, 0x39C7);
    const uint16_t fill = (uint16_t)(((uint32_t)cc_slider_pct * 97u) / 100u);
    if (fill) lcd_fill(13, 95, fill, 8, cc_slider_valid ? C_GREEN : C_RED);
    char value[12];
    if (cc_slider_valid) {
        (void)snprintf(value, sizeof(value), "%3u%%", (unsigned)cc_slider_pct);
    } else {
        (void)snprintf(value, sizeof(value), "ADC ERR");
    }
    cc_draw_text(13, 106, value, 1, C_WHITE);
    cc_slider_last_drawn = cc_slider_pct;
}

// Compact read-only ADXL345 indicator in the detection screen footer.
// Raw x/y/z samples must move when the module is tilted; the test never
// sends motion events or macros to the host.
static void cc_matrix_adxl_widget(void) {
    if (!cc_adxl.changed) return;
    char line[52];
    uint16_t color = C_RED;
    switch (cc_adxl.status) {
        case CC_ADXL_OK:
            if (cc_adxl.valid) {
                (void)snprintf(line, sizeof(line), "ADXL OK X:%+5d Y:%+5d Z:%+5d",
                               (int)cc_adxl.x, (int)cc_adxl.y, (int)cc_adxl.z);
                color = C_GREEN;
            } else {
                (void)snprintf(line, sizeof(line), "ADXL OK  READ WAIT");
                color = C_YELLOW;
            }
            break;
        case CC_ADXL_SEARCH:
            (void)snprintf(line, sizeof(line), "ADXL SEARCHING");
            color = C_YELLOW;
            break;
        case CC_ADXL_MISSING:
            (void)snprintf(line, sizeof(line), "ADXL NOT FOUND  ADDR 53");
            break;
        case CC_ADXL_BAD_ID:
            (void)snprintf(line, sizeof(line), "ADXL WRONG CHIP ID");
            break;
        case CC_ADXL_IO_ERROR:
            (void)snprintf(line, sizeof(line), "ADXL I2C ERROR");
            break;
        default:
            (void)snprintf(line, sizeof(line), "ADXL OFF - GP0 IS MATRIX");
            color = C_YELLOW;
            break;
    }
    lcd_fill(0, 216, LCD_W, 24, 0x18C7);
    cc_draw_text(7, 218, line, 1, color);
    cc_draw_text(7, 230, cc_tester_active ? "PC TESTER / HOLD K0 TO EXIT" : "K0 1X EXIT 3X TOGGLE / PUSH EXIT", 1, C_CYAN);
    cc_adxl.changed = false;
}

static void cc_matrix_test_screen(void) {
    if (cc_matrix_full_redraw) {
        cc_background(NULL, 0);
        lcd_fill(7, 33, 109, 171, cc_view_preset() == 1 ? 0x0000 : 0x2186);
        lcd_fill(7, 33, 109, 4, cc_view_accent());
        cc_draw_text(13, 55, "MATRIX", 2, C_WHITE);
        cc_draw_text(13, 72, "4-4-2", 1, cc_view_accent());
#if CC_PCF8575_MATRIX
        char pcf_label[18];
        if (cc_pcf8575_online()) {
            (void)snprintf(pcf_label, sizeof(pcf_label), "PCF %02X OK",
                           (unsigned)cc_pcf8575_address());
        } else {
            (void)snprintf(pcf_label, sizeof(pcf_label), "PCF NO I2C");
        }
        cc_draw_text(124, 9, pcf_label, 1,
                     cc_pcf8575_online() ? C_GREEN : C_RED);
#else
        cc_draw_text(124, 9, "GPIO MATRIX", 1, C_YELLOW);
#endif
        cc_adxl.changed = true; // Background overwrote the last footer.
        cc_matrix_changed = (1u << CC_KEY_COUNT) - 1u;
        cc_matrix_full_redraw = false;
    }
    const uint16_t changed = cc_matrix_changed;
    cc_matrix_changed = 0;
    for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
        if (changed & (1u << i)) cc_matrix_key_tile(i);
    }
    if (cc_slider_last_drawn != cc_slider_pct || !cc_slider_valid) {
        cc_matrix_slider_widget();
    }
    cc_matrix_test_status();
    cc_matrix_adxl_widget();
}

static void cc_menu_screen(void) {
    static const char *options[6] = {"DISPLAY", "ENCODER", "HOME", "MATRIX", "HELP", "COLORS"};
    cc_background(cc_default_footer, cc_view_accent());
    lcd_fill(7, 33, 109, 171, cc_view_preset() == 1 ? 0x0000 : 0x2186);
    cc_draw_text(17, 64, "MODULE", 2, cc_view_accent());
    cc_draw_text(15, 105, "K0 ONLY", 1, C_WHITE);
    cc_draw_text(16, 164, "NO USB", 1, C_YELLOW);
    for (uint8_t i = 0; i < 6; ++i) {
        const uint16_t y = 34 + i * 29;
        lcd_fill(125, y, 187, 25, cc_menu_selection == i ? 0x2C96 : (cc_view_preset() == 1 ? 0x0000 : 0x2145));
        lcd_fill(125, y, 4, 25, cc_menu_selection == i ? cc_view_accent() : 0x4AAB);
        cc_draw_text(141, y + 9, options[i], 1, C_WHITE);
    }
}

static uint8_t cc_internal_drawn_mode = 0;
static uint8_t cc_internal_drawn_selected = 255;
static uint8_t cc_internal_drawn_confirm = 255;
static uint8_t cc_internal_drawn_power = 255;
static uint8_t cc_internal_drawn_source = 255;
static void cc_internal_item(uint8_t i, const char *name, bool selected) {
    const uint16_t x = i < 5 ? 12 : 163;
    const uint16_t y = 65 + (i % 5u) * 28u;
    lcd_fill(x, y, 143, 24, selected ? 0x2C96 : 0x2145);
    cc_draw_text(x + 6, y + 8, name, 1, C_WHITE);
}
static void cc_internal_screen(void) {
    static const char *sys[9] = {
        "RGB POWER", "DISPLAY", "CONFIG SOURCE", "MATRIX",
        "DEVICE INFO", "RESTART", "BOOTLOADER", "CLEAR EEPROM", "BACK"
    };
    static const char *disp[5] = {
        "ACTIVE MAP", "LAYER LIST", "MATRIX", "BACKLIGHT", "BACK"
    };
    static const char *config[3] = {"FIRMWARE", "APP PROFILE", "BACK"};
    const char **items = cc_internal_mode == 2 ? disp : cc_internal_mode == 4 ? config : sys;
    const uint8_t count = cc_internal_mode == 2 ? 5 : cc_internal_mode == 4 ? 3 : 9;
    const uint8_t power = cc_rgb_master_enabled ? 1 : 0;
    const uint8_t source = cc_use_app_profile ? 1 : 0;
    const bool full = cc_internal_drawn_mode != cc_internal_mode ||
                      cc_internal_drawn_confirm != cc_internal_confirm ||
                      cc_internal_drawn_power != power ||
                      cc_internal_drawn_source != source;
    if (full) {
        const char *footer = cc_internal_confirm != 255 ? "K9 CONFIRM  K5 BACK" :
                             cc_internal_mode == 1 ? "K3 UP  K7 DOWN  K6/K8 COL  K9 OK  K5 BACK" :
                             cc_internal_mode == 3 ? "K9 OK  K5 BACK" :
                             "K3 UP  K7 DOWN  K9 OK  K5 BACK";
        cc_background(footer, C_CYAN);
        cc_draw_text(11, 37, cc_internal_mode == 2 ? "DISPLAY" :
                     cc_internal_mode == 4 ? "CONFIGURATION" :
                     cc_internal_mode == 3 ? "DEVICE INFO" : "SETTINGS", 2, C_CYAN);
        if (cc_internal_mode == 3) {
            cc_draw_text(13, 85, "RP2040 / OMNIPAD", 1, C_WHITE);
            cc_draw_text(13, 106, "QMK / VIA HID / USB", 1, C_WHITE);
            cc_draw_text(13, 127, "FIRMWARE UI REV 2", 1, C_WHITE);
            cc_draw_text(13, 152, cc_use_app_profile ? "MODE APP" : "MODE FIRMWARE", 1, C_CYAN);
        } else {
            for (uint8_t i = 0; i < count; ++i) cc_internal_item(i, items[i], i == cc_internal_selected);
            if (cc_internal_mode == 1) {
                cc_draw_text(9, 205, power ? "RGB ON" : "RGB OFF", 1, C_YELLOW);
            } else if (cc_internal_mode == 4) {
                cc_draw_text(11, 173, source ? "ACTIVE APP" : "ACTIVE FIRMWARE", 1, C_YELLOW);
                if (!cc_visual_profile_available) cc_draw_text(11, 189, "NO APP PROFILE SAVED", 1, C_RED);
            }
        }
        if (cc_internal_confirm != 255) {
            lcd_fill(5, 58, 310, 150, C_BLACK);
            cc_draw_text(12, 93, "CONFIRM FIRMWARE ACTION?", 1, C_YELLOW);
            cc_draw_text(12, 120, "K9 AGAIN TO CONFIRM", 1, C_WHITE);
            cc_draw_text(12, 144, "K5 BACK TO CANCEL", 1, C_CYAN);
        }
    } else if (cc_internal_drawn_selected != cc_internal_selected && cc_internal_mode != 3) {
        if (cc_internal_drawn_selected < count) {
            cc_internal_item(cc_internal_drawn_selected, items[cc_internal_drawn_selected], false);
        }
        if (cc_internal_confirm == 255) {
            cc_internal_item(cc_internal_selected, items[cc_internal_selected], true);
        }
    }
    cc_internal_drawn_mode = cc_internal_mode;
    cc_internal_drawn_selected = cc_internal_selected;
    cc_internal_drawn_confirm = cc_internal_confirm;
    cc_internal_drawn_power = power;
    cc_internal_drawn_source = source;
}

static void cc_help_screen(void) {
    cc_background(cc_default_footer, cc_view_accent());
    cc_draw_text(12, 40, "MODULE HELP", 2, C_CYAN);
    cc_draw_text(12, 78, "K0 1X  DISP/ENC", 1, C_WHITE);
    cc_draw_text(12, 96, "K0 2X  DEFAULT", 1, C_WHITE);
    cc_draw_text(12, 114, "K0 3X  MATRIX", 1, C_CYAN);
    cc_draw_text(12, 129, "K0 HOLD  MENU", 1, C_WHITE);
    cc_draw_text(12, 147, "K9  2X  CC STUDIO", 1, C_WHITE);
    cc_draw_text(12, 162, "ENC TURN  SELECT", 1, C_WHITE);
    cc_draw_text(12, 177, "K5 SHIFT K9 CTRL", 1, C_WHITE);
    cc_draw_text(12, 192, "K10 ALT / VIA", 1, C_YELLOW);
}

static void cc_color_screen(bool show_exit) {
    lcd_fill(0, 0, 160, 120, C_RED);
    lcd_fill(160, 0, 160, 120, C_GREEN);
    lcd_fill(0, 120, 160, 120, C_BLUE);
    lcd_fill(160, 120, 160, 120, C_BLACK);
#if ICST_USE_HW_SPI
    lcd_fill(0, 116, 320, 8, C_MAGENTA);
#endif
    if (show_exit) cc_draw_text(12, 206, "PUSH TO RETURN", 1, C_WHITE);
}

#include "cc_tester.h"

static bool omp_screen_invalid = true;
static void omp_screen_render(void);
static void omp_screen_overlay_render(uint8_t view);

static bool cc_custom_screen_selected(void) {
    // Explicit custom mode retains legacy full-screen rendering. Normally the
    // firmware draws its functional screens and paints view-scoped extras.
    return omp_enabled && cc_screen_selection == CC_SCREEN_CUSTOM &&
           omp_profile.screen.enabled;
}

static void cc_redraw(void) {
    if (!panel_ready) return;
    // Partial updates require the previous frame to belong to the same renderer.
    enum cc_cached_screen { CC_SCREEN_UNCACHED, CC_SCREEN_DRAWN_LIST, CC_SCREEN_DRAWN_MAP };
    static enum cc_cached_screen drawn_screen = CC_SCREEN_UNCACHED;
    enum cc_cached_screen next_screen = CC_SCREEN_UNCACHED;
    if (!cc_internal_mode) cc_internal_drawn_mode = 0;
    if (cc_matrix_test_view || cc_color_view || cc_help_view || cc_menu_view) omp_screen_invalid = true;
    if (cc_reset_state == CC_RESET_HOLDING) {
        omp_screen_invalid = true;
        lcd_fill(0, 0, LCD_W, LCD_H, C_BLACK);
        cc_draw_text(15, 84, "HOLD BOTH 5S TO RESET", 2, C_YELLOW);
        cc_draw_text(15, 119, "RELEASE TO CANCEL", 1, C_WHITE);
    } else if (cc_internal_mode) cc_internal_screen();
    else if (cc_eeprom_confirm) {
        if (!cc_eeprom_confirm_visible) {
            omp_screen_invalid = true;
            lcd_fill(0, 0, LCD_W, LCD_H, C_BLACK);
            cc_draw_text(15, 70, "CLEAR EEPROM?", 2, C_YELLOW);
            cc_draw_text(15, 115, "PUSH ENCODER TO ERASE", 1, C_WHITE);
            cc_draw_text(15, 139, "K0 TO CANCEL", 1, C_WHITE);
            cc_eeprom_confirm_visible = true;
        }
    } else if (cc_matrix_test_view && cc_tester_output == 1) cc_color_screen(false);
    else if (cc_matrix_test_view) cc_matrix_test_screen();
    else if (cc_color_view) cc_color_screen(true);
    else if (cc_help_view) cc_help_screen();
    else if (cc_menu_view) cc_menu_screen();
    else if (cc_custom_screen_selected()) omp_screen_render();
    else if (!cc_home_view && cc_screen_selection == CC_SCREEN_LAYERS) {
        cc_layer_index_screen(drawn_screen != CC_SCREEN_DRAWN_LIST);
        next_screen = CC_SCREEN_DRAWN_LIST;
    } else if (!cc_home_view && cc_screen_selection == CC_SCREEN_NAV) {
        cc_navigation_screen();
    } else {
        cc_layer_screen(drawn_screen != CC_SCREEN_DRAWN_MAP);
        next_screen = CC_SCREEN_DRAWN_MAP;
    }
    if (next_screen != CC_SCREEN_DRAWN_MAP) cc_last_key = UINT8_MAX;
    drawn_screen = next_screen;
    // Only non-safety views permit user-positioned decorations. Menu and
    // tester are deliberately protected against obscured controls.
    if (omp_enabled && omp_profile.screen.enabled && !cc_custom_screen_selected() &&
        !cc_internal_mode && !cc_menu_view && !cc_matrix_test_view && !cc_eeprom_confirm &&
        cc_reset_state != CC_RESET_HOLDING && !cc_help_view && !cc_color_view)
        omp_screen_overlay_render(cc_view_kind());
    cc_dirty = false;
    cc_last_draw = timer_read();
}

#include "cc_controls.h"
