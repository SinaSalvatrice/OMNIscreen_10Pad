// OMNIscreen 10Pad PCF8575 16-bit I2C expander matrix.
// Build only after rewiring the seven matrix wires to PCF8575.
// Physical PCF8575 row/column pins come from the source keyboard.json
// via the generated pcf8575 matrix header in the QMK staging copy.
// ROW2COL diodes: select each column LOW, detect LOW on row inputs.
// I2C0 is shared with ADXL345: PCF8575 0x20; ADXL345 0x53.
#include "matrix.h"
#include "pcf8575_matrix_pins.h"
#include "i2c_master.h"
#include "timer.h"
#include <stdbool.h>
#include <stdint.h>

#define CC_PCF8575_ADDRESS          (0x20u << 1) // QMK uses shifted I2C addresses.
#define CC_PCF8575_TIMEOUT_MS       5u
 #define CC_PCF8575_RETRY_MS         500u
#define CC_PCF8575_ALL_HIGH        0xFFFFu

#if MATRIX_ROWS != CC_PCF_ROW_COUNT || MATRIX_COLS != CC_PCF_COL_COUNT
#    error "PCF8575 matrix dimensions differ from generated keyboard.json mapping"
#endif

// Bits outside the assigned row and column lines stay released during scans.
#define CC_PCF8575_UNASSIGNED CC_PCF_UNASSIGNED_MASK
static uint16_t cc_pcf_unassigned_low;
static bool cc_pcf_ready = false;
static uint16_t cc_pcf_last_retry = 0;

// PCF8575 has NO internal configuration registers: all 16 I/Os are
// quasi-bidirectional. Writing 1 releases a pin into weak pull-up/input.
// First byte = P00..P07; second byte = P10..P17.
static bool cc_pcf_write(uint16_t levels) {
    uint8_t data[2] = {(uint8_t)levels, (uint8_t)(levels >> 8)};
    return i2c_transmit(CC_PCF8575_ADDRESS, data, sizeof(data),
                        CC_PCF8575_TIMEOUT_MS) == I2C_STATUS_SUCCESS;
}

static bool cc_pcf_read(uint16_t *levels) {
    uint8_t data[2];
    if (i2c_receive(CC_PCF8575_ADDRESS, data, sizeof(data),
                    CC_PCF8575_TIMEOUT_MS) != I2C_STATUS_SUCCESS) {
        return false;
    }
    *levels = (uint16_t)data[0] | ((uint16_t)data[1] << 8);
    return true;
}

bool cc_pcf8575_online(void) {
    return cc_pcf_ready;
}

uint16_t cc_pcf8575_unassigned_low(void) {
    return cc_pcf_unassigned_low;
}

static bool cc_pcf_init(void) {
    cc_pcf_last_retry = timer_read();
    // All rows and columns released; inputs have the PCF8575 weak pull-ups.
    cc_pcf_ready = cc_pcf_write(CC_PCF8575_ALL_HIGH);
    return cc_pcf_ready;
}

void matrix_init_custom(void) {
    i2c_init();
    cc_pcf_init();
}

static bool cc_pcf_store(matrix_row_t current[], const matrix_row_t next[]) {
    bool changed = false;
    for (uint8_t row = 0; row < MATRIX_ROWS; row++) {
        if (current[row] != next[row]) {
            current[row] = next[row];
            changed = true;
        }
    }
    return changed;
}

bool matrix_scan_custom(matrix_row_t current[]) {
    matrix_row_t next[MATRIX_ROWS] = {0};

    if (!cc_pcf_ready) {
        if (timer_elapsed(cc_pcf_last_retry) >= CC_PCF8575_RETRY_MS) {
            cc_pcf_init();
        }
        if (!cc_pcf_ready) return cc_pcf_store(current, next);
    }

    bool success = true;
    uint16_t unassigned_low = 0;
    for (uint8_t column = 0; column < CC_PCF_COL_COUNT; ++column) {
        // Keep every row and unused pin at 1; pull the configured column LOW.
        uint16_t levels = (uint16_t)(CC_PCF8575_ALL_HIGH & ~((uint16_t)1u << cc_pcf_col_bits[column]));
        uint16_t sampled = 0;
        if (!cc_pcf_write(levels) || !cc_pcf_read(&sampled)) {
            success = false;
            break;
        }
        unassigned_low |= ~sampled & CC_PCF8575_UNASSIGNED;
        for (uint8_t row = 0; row < MATRIX_ROWS; ++row) {
            if (!(sampled & ((uint16_t)1u << cc_pcf_row_bits[row]))) {
                next[row] |= (matrix_row_t)(1u << column);
            }
        }
    }

    // Release all columns after scan, including on failed reads.
    if (!cc_pcf_write(CC_PCF8575_ALL_HIGH)) success = false;

    if (!success) {
        cc_pcf_ready = false;
        cc_pcf_last_retry = timer_read();
        // On bus failure release any latched keys rather than leaving Ctrl stuck.
        for (uint8_t row = 0; row < MATRIX_ROWS; ++row) next[row] = 0;
    }
    cc_pcf_unassigned_low = success ? unassigned_low : 0;
    return cc_pcf_store(current, next);
}
