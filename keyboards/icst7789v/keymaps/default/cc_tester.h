// Signal recording is scoped to the explicit PC tester mode.
#pragma once

enum {
    CC_SIGNAL_MATRIX = 1, CC_SIGNAL_K0, CC_SIGNAL_ENCODER_PUSH,
    CC_SIGNAL_ENCODER_TURN, CC_SIGNAL_SLIDER, CC_SIGNAL_ADXL,
    CC_SIGNAL_PCF, CC_SIGNAL_PCF_PIN,
};

typedef struct {
    uint8_t source, detail;
    uint16_t value;
} cc_signal_t;

static cc_signal_t cc_signals[32];
static uint8_t cc_signal_head, cc_signal_count;
static bool cc_signal_overflow;
static uint8_t cc_tester_output;
static uint16_t cc_tester_output_at, cc_tester_last_poll;

static void cc_tester_record(uint8_t source, uint8_t detail, uint16_t value) {
    if (!cc_tester_active || !cc_matrix_test_view) return;
    if (cc_signal_count == ARRAY_SIZE(cc_signals)) {
        cc_signal_head = (cc_signal_head + 1u) % ARRAY_SIZE(cc_signals);
        --cc_signal_count;
        cc_signal_overflow = true;
    }
    uint8_t end = (cc_signal_head + cc_signal_count) % ARRAY_SIZE(cc_signals);
    cc_signals[end] = (cc_signal_t){source, detail, value};
    ++cc_signal_count;
}

static void cc_tester_matrix(uint8_t row, uint8_t col, bool pressed) {
    cc_tester_record(CC_SIGNAL_MATRIX, (row << 4) | col, pressed);
    cc_matrix_test_record(row, col, pressed);
}

static bool cc_tester_report(uint8_t *data) {
    cc_tester_last_poll = timer_read();
    data[3] = cc_tester_active && cc_matrix_test_view;
    data[4] = cc_signal_overflow;
    uint8_t count = cc_signal_count > 6 ? 6 : cc_signal_count;
    data[5] = count;
    for (uint8_t i = 0; i < count; ++i) {
        const cc_signal_t *event = &cc_signals[cc_signal_head];
        uint8_t offset = 6 + 4 * i;
        data[offset] = event->source;
        data[offset + 1] = event->detail;
        data[offset + 2] = (uint8_t)event->value;
        data[offset + 3] = (uint8_t)(event->value >> 8);
        cc_signal_head = (cc_signal_head + 1u) % ARRAY_SIZE(cc_signals);
    }
    cc_signal_count -= count;
    cc_signal_overflow = false;
    return true;
}

static void cc_tester_sample(void) {
    static bool started;
    static bool slider_seen, adxl_seen;
    static uint16_t slider_value;
#if CC_PCF8575_MATRIX
    static uint16_t pcf_pins;
#endif
    static int16_t x, y, z;

    if (cc_tester_active && timer_elapsed(cc_tester_last_poll) >= 5000u) {
        cc_matrix_test_exit();
        cc_tester_active = false;
    }
    if (!cc_tester_active || !cc_matrix_test_view) {
        started = false;
        return;
    }
    if (!started) {
        slider_seen = adxl_seen = false;
        started = true;
#if CC_PCF8575_MATRIX
        pcf_pins = 0;
        if (cc_pcf8575_online()) cc_tester_record(CC_SIGNAL_PCF, 0, 0);
#endif
    }
    if (cc_slider_valid) {
        int16_t delta = (int16_t)cc_slider_raw - slider_value;
        if (slider_seen && (delta >= 7 || delta <= -7 || (delta &&
            (cc_slider_pct == 0 || cc_slider_pct == 100)))) {
            cc_tester_record(CC_SIGNAL_SLIDER, cc_slider_pct, cc_slider_raw);
            slider_seen = false; // Take a new baseline after the event.
        }
        if (!slider_seen) {
            slider_value = cc_slider_raw;
            slider_seen = true;
        }
    } else slider_seen = false;

    if (cc_adxl.status == CC_ADXL_OK && cc_adxl.valid) {
        int32_t delta = abs((int)cc_adxl.x - x) + abs((int)cc_adxl.y - y) + abs((int)cc_adxl.z - z);
        if (!adxl_seen || delta >= 12) {
            cc_tester_record(CC_SIGNAL_ADXL, adxl_seen, 0);
            x = cc_adxl.x;
            y = cc_adxl.y;
            z = cc_adxl.z;
            adxl_seen = true;
        }
    } else adxl_seen = false;

#if CC_PCF8575_MATRIX
    uint16_t next = cc_pcf8575_unassigned_low();
    uint16_t active = next & ~pcf_pins;
    for (uint8_t i = 0; i < 16; ++i) {
        if (active & (1u << i)) cc_tester_record(CC_SIGNAL_PCF_PIN, i, 0);
    }
    pcf_pins = next;
#endif
}
