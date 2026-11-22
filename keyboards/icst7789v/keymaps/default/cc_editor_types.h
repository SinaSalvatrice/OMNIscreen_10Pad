// Versioned wire format shared with desktop-app/profile.py.
#pragma once
#include "eeprom.h"
#include <string.h>

#define OMP_LAYERS 12
#define OMP_KEYS 12
#define OMP_FIELDS 16
#define OMP_SNIPPETS 16
#define OMP_MACRO_POOL 1152
#define OMP_VIEWS 6
#define OMP_OLD_PROFILE_SIZE 6084u
#define OMP_SLOT_SIZE 6144
#define OMP_STORAGE_START 4096

enum {
    OMP_ACTION_LAYERS = 0x7E40, OMP_ACTION_CUSTOM_SCREEN, OMP_ACTION_MATRIX,
    OMP_ACTION_MENU, OMP_ACTION_HOME, OMP_ACTION_ENCODER_MODE,
    OMP_ACTION_HELP, OMP_ACTION_COLORS, OMP_ACTION_EEPROM, OMP_ACTION_NONE,
    OMP_ACTION_NAVIGATION, OMP_ACTION_DETAILS, OMP_ACTION_SETTINGS,
};

typedef struct __attribute__((packed)) {
    uint8_t mode; // 0 direct, 1 tap dance, 2 cycle
    uint16_t term;
    uint16_t codes[5]; // tap 1..4, hold
    char label[12];
} omp_key_t;

typedef struct __attribute__((packed)) {
    uint8_t effect, brightness, speed, flags;
    uint16_t color_a, color_b;
    uint8_t triggers, duration; // key=1, encoder=2, layer=4, slider=8; 10 ms
} omp_zone_t;

typedef struct __attribute__((packed)) {
    uint8_t mode, reverse, deadband, step;
    uint16_t low, high, minimum, maximum;
} omp_slider_t;

typedef struct __attribute__((packed)) {
    char name[16];
    uint16_t accent;
    omp_key_t keys[OMP_KEYS];
    uint16_t encoders[2];
    omp_slider_t slider;
    omp_zone_t zones[2];
} omp_layer_t;

typedef struct __attribute__((packed)) {
    uint16_t x, y, width, height;
    uint8_t type, binding, key, layer, icon, scale;
    uint16_t foreground, background;
    char text[20];
} omp_field_t;

typedef struct __attribute__((packed)) {
    uint8_t enabled, count;
    uint16_t background;
    omp_field_t fields[OMP_FIELDS];
} omp_screen_t;

typedef struct __attribute__((packed)) {
    uint16_t start, length;
} omp_macro_t;

typedef struct __attribute__((packed)) {
    uint8_t preset, flags;
    uint16_t background, accent;
} omp_theme_t;

typedef struct __attribute__((packed)) {
    char magic[4];
    uint8_t layer_count, default_layer, snippet_count, reserved;
    omp_layer_t layers[OMP_LAYERS];
    omp_screen_t screen;
    omp_macro_t snippets[OMP_SNIPPETS];
    uint8_t macro_pool[OMP_MACRO_POOL];
    char theme_magic[4];          // "SCR1" after legacy 6084-byte payload
    omp_theme_t themes[OMP_VIEWS]; // Six independently themed firmware views
} omp_profile_t;

typedef struct __attribute__((packed)) {
    uint32_t marker, generation, checksum, size;
} omp_slot_header_t;

_Static_assert(sizeof(omp_key_t) == 25, "Key format");
_Static_assert(sizeof(omp_layer_t) == 354, "Layer format");
_Static_assert(sizeof(omp_field_t) == 38, "Display format");
_Static_assert(sizeof(omp_theme_t) == 6, "Screen theme format");
_Static_assert(sizeof(omp_profile_t) == 6124, "Profile format");
_Static_assert(sizeof(omp_profile_t) + sizeof(omp_slot_header_t) <= OMP_SLOT_SIZE, "Profile storage");

static omp_profile_t omp_profile;
static omp_profile_t omp_incoming;
static bool omp_enabled;
static uint8_t omp_active_slot;
static uint32_t omp_generation;
static uint16_t omp_received;
static bool omp_receiving;
static uint16_t omp_transfer_timer;
static uint32_t omp_expected_checksum;

#define OMP_LED_PREVIEW_MS 1800u
static omp_zone_t omp_preview_zones[2];
static bool omp_preview_active;
static uint16_t omp_preview_at;

static bool omp_zone_valid(const omp_zone_t *zone) {
    return zone->effect <= 8 && zone->brightness <= RGBLIGHT_LIMIT_VAL &&
           zone->flags <= 3 && zone->triggers <= 15 && zone->duration;
}

static uint32_t omp_checksum(const void *data, uint16_t size) {
    const uint8_t *bytes = data;
    uint32_t result = 2166136261u;
    for (uint16_t i = 0; i < size; ++i) {
        result = (result ^ bytes[i]) * 16777619u;
    }
    return result;
}

static uint8_t omp_layer_count(void) {
    return omp_enabled ? omp_profile.layer_count : CC_LAYER_COUNT;
}

static void omp_theme_defaults(omp_profile_t *p) {
    memcpy(p->theme_magic, "SCR1", 4);
    for (uint8_t i = 0; i < OMP_VIEWS; ++i) {
        p->themes[i].preset = 0;
        p->themes[i].flags = 0;
        p->themes[i].background = 0x10E3;
        p->themes[i].accent = 0xCC2B;
    }
}

static bool omp_profile_valid(const omp_profile_t *p) {
    if (memcmp(p->theme_magic, "SCR1", 4)) return false;
    for (uint8_t i = 0; i < OMP_VIEWS; ++i)
        if (p->themes[i].preset > 2 || p->themes[i].flags) return false;
    if (memcmp(p->magic, "OMP2", 4) || p->layer_count == 0 ||
        p->layer_count > OMP_LAYERS || p->default_layer >= p->layer_count ||
        p->snippet_count > OMP_SNIPPETS || p->screen.count > OMP_FIELDS ||
        p->screen.enabled > 1) return false;
    for (uint8_t layer = 0; layer < p->layer_count; ++layer) {
        const omp_layer_t *l = &p->layers[layer];
        if (l->name[15] || l->slider.mode > 5 || l->slider.reverse > 1 ||
            !l->slider.step || l->slider.deadband > 64 ||
            l->slider.minimum >= l->slider.maximum || l->slider.maximum > 1023) return false;
        for (uint8_t i = 0; i < OMP_KEYS; ++i) {
            const omp_key_t *key = &l->keys[i];
            if (key->mode > 2 || key->term < 80 || key->term > 2000 || key->label[11]) return false;
        }
        for (uint8_t i = 0; i < 2; ++i) {
            if (!omp_zone_valid(&l->zones[i])) return false;
        }
    }
    for (uint8_t i = 0; i < p->screen.count; ++i) {
        const omp_field_t *f = &p->screen.fields[i];
        if (f->x >= LCD_W || f->y >= LCD_H || !f->width || !f->height ||
            f->width > LCD_W - f->x || f->height > LCD_H - f->y ||
            f->type > 2 || f->binding > 9 || (f->key & 0x7F) >= OMP_KEYS ||
            (f->layer != 255 && 
             !(f->layer < p->layer_count) &&
             !(f->layer >= 0x10 && f->layer <= 0x6F &&
               ((f->layer & 15u) == 15u || (f->layer & 15u) < p->layer_count))) ||
            f->icon > 7 || !f->scale || f->scale > 4 || f->text[19]) return false;
    }
    for (uint8_t i = 0; i < p->snippet_count; ++i) {
        const omp_macro_t *m = &p->snippets[i];
        if ((uint32_t)m->start + m->length > OMP_MACRO_POOL || m->length % 3) return false;
        for (uint16_t pos = m->start; pos < m->start + m->length; pos += 3) {
            if (p->macro_pool[pos] < 1 || p->macro_pool[pos] > 4) return false;
        }
    }
    return true;
}

static uint16_t omp_slot_address(uint8_t slot) {
    return OMP_STORAGE_START + (uint16_t)slot * OMP_SLOT_SIZE;
}

static bool omp_load_slot(uint8_t slot, omp_profile_t *destination, omp_slot_header_t *header) {
    uint16_t base = omp_slot_address(slot);
    eeprom_read_block(header, (const void *)(uintptr_t)base, sizeof(*header));
    if (header->marker != 0x32504D4Fu ||
        (header->size != sizeof(*destination) && header->size != OMP_OLD_PROFILE_SIZE)) return false;
    memset(destination, 0, sizeof(*destination));
    eeprom_read_block(destination, (const void *)(uintptr_t)(base + sizeof(*header)), header->size);
    // Verify the original checksum before migrating a valid old profile.
    if (omp_checksum(destination, header->size) != header->checksum) return false;
    if (header->size == OMP_OLD_PROFILE_SIZE) omp_theme_defaults(destination);
    return omp_profile_valid(destination);
}

static void omp_load(void) {
    omp_slot_header_t a, b;
    bool first = omp_load_slot(0, &omp_profile, &a);
    bool second = omp_load_slot(1, &omp_incoming, &b);
    if (second && (!first || (int32_t)(b.generation - a.generation) > 0)) {
        omp_profile = omp_incoming;
        omp_generation = b.generation;
        omp_active_slot = 1;
    } else if (first) {
        omp_generation = a.generation;
        omp_active_slot = 0;
    }
    omp_enabled = first || second;
    // Older app profiles have seven layers. Preserve all their configured
    // actions, append a working MEDIA layer in RAM, and do not rewrite flash.
    if (omp_enabled && omp_profile.layer_count == 7) {
        omp_layer_t *media = &omp_profile.layers[7];
        *media = omp_profile.layers[1];
        memset(media->name, 0, sizeof(media->name));
        memcpy(media->name, "MEDIA", 5);
        media->accent = cc_layers[7].accent_rgb565;
        for (uint8_t i = 0; i < CC_KEY_COUNT; ++i) {
            omp_key_t *key = &media->keys[i];
            key->mode = 0;
            key->term = 220;
            memset(key->codes, 0, sizeof(key->codes));
            key->codes[0] = cc_layers[7].taps[i];
            memset(key->label, 0, sizeof(key->label));
            strncpy(key->label, cc_layers[7].labels[i], sizeof(key->label)-1u);
        }
        media->keys[10].mode = 0;
        media->keys[10].term = 220;
        memset(media->keys[10].codes, 0, sizeof(media->keys[10].codes));
        media->keys[10].codes[0] = KC_MPLY;
        strcpy(media->keys[10].label, "PLAY");
        media->keys[11].mode = 0;
        media->keys[11].term = 220;
        memset(media->keys[11].codes, 0, sizeof(media->keys[11].codes));
        strcpy(media->keys[11].label, "K0");
        media->encoders[0] = KC_MPRV;
        media->encoders[1] = KC_MNXT;
        media->slider.mode = 1; // Relative volume keys work without a desktop app.
        media->slider.low = KC_VOLD;
        media->slider.high = KC_VOLU;
        media->slider.step = 64;
        media->slider.deadband = 12;
        omp_profile.layer_count = 8;
    }
}

static bool omp_store(void) {
    uint8_t next = omp_active_slot ^ 1u;
    uint16_t base = omp_slot_address(next);
    const omp_slot_header_t header = {
        .marker = 0x32504D4Fu,
        .generation = omp_generation + 1,
        .checksum = omp_checksum(&omp_incoming, sizeof(omp_incoming)),
        .size = sizeof(omp_incoming),
    };
    // Invalidate only the inactive slot. Publish its header after the payload.
    eeprom_update_dword((uint32_t *)(uintptr_t)base, 0);
    eeprom_update_block(&omp_incoming, (void *)(uintptr_t)(base + sizeof(header)), sizeof(omp_incoming));
    eeprom_update_block(&header, (void *)(uintptr_t)base, sizeof(header));
    omp_slot_header_t verify;
    if (!omp_load_slot(next, &omp_profile, &verify) ||
        verify.generation != header.generation || verify.checksum != header.checksum) {
        // A failed verification must not replace the last valid runtime profile.
        omp_load();
        return false;
    }
    omp_active_slot = next;
    omp_generation = header.generation;
    omp_enabled = true;
    return true;
}
