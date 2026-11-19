// ADXL345 diagnostic sensor for the OMNIscreen 10Pad.
// Enabled only after GP0 is removed from the keyboard matrix.
// No gesture -> USB key events; diagnostics are read only.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum {
    CC_ADXL_DISABLED,
    CC_ADXL_SEARCH,
    CC_ADXL_OK,
    CC_ADXL_MISSING,
    CC_ADXL_BAD_ID,
    CC_ADXL_IO_ERROR
} cc_adxl_status_t;

typedef struct {
    cc_adxl_status_t status;
    int16_t x;
    int16_t y;
    int16_t z;
    uint16_t last_probe;
    uint16_t last_read;
    uint8_t failed_reads;
    bool valid;
    bool changed;
} cc_adxl_state_t;

static cc_adxl_state_t cc_adxl = {
    .status = CC_ADXL_DISABLED,
    .changed = true,
};

#if CC_ADXL345_ENABLE
#    include "i2c_master.h"

// QMK's I2C API takes an eight-bit, left-shifted device address.
// The 7-bit address depends on SDO: LOW=0x53, HIGH=0x1D.
#    define CC_ADXL_ADDR_LOW  0x53u
#    define CC_ADXL_ADDR_HIGH 0x1Du
static uint8_t cc_adxl_address = CC_ADXL_ADDR_LOW;
#    define CC_ADXL_TIMEOUT_MS 5

static bool cc_adxl_read(uint8_t reg, uint8_t *data, uint8_t length) {
    return i2c_read_register((uint8_t)(cc_adxl_address << 1), reg, data, length,
                             CC_ADXL_TIMEOUT_MS) == I2C_STATUS_SUCCESS;
}

static bool cc_adxl_write(uint8_t reg, uint8_t value) {
    return i2c_write_register((uint8_t)(cc_adxl_address << 1), reg, &value, 1,
                              CC_ADXL_TIMEOUT_MS) == I2C_STATUS_SUCCESS;
}

static void cc_adxl_status(cc_adxl_status_t status) {
    if (cc_adxl.status != status) {
        cc_adxl.status = status;
        cc_adxl.changed = true;
    }
}

static void cc_adxl_init(void) {
    i2c_init();
    cc_adxl.valid = false;
    cc_adxl.failed_reads = 0;
    cc_adxl.last_probe = (uint16_t)(timer_read() - 1500u);
    cc_adxl.last_read = timer_read();
    cc_adxl_status(CC_ADXL_SEARCH);
}

static void cc_adxl_probe(void) {
    uint8_t devid = 0;
    bool wrong_id = false;
    bool found = false;
    cc_adxl.last_probe = timer_read();
    // Check both legal ADXL345 addresses; only accept the actual DEVID 0xE5.
    // This also permits a breakout with SDO strapped HIGH to work.
    const uint8_t candidates[2] = {CC_ADXL_ADDR_LOW, CC_ADXL_ADDR_HIGH};
    for (uint8_t i = 0; i < 2; ++i) {
        cc_adxl_address = candidates[i];
        if (!cc_adxl_read(0x00u, &devid, 1)) continue;
        if (devid == 0xE5u) {
            found = true;
            break;
        }
        wrong_id = true;
    }
    if (!found) {
        cc_adxl.valid = false;
        cc_adxl_status(wrong_id ? CC_ADXL_BAD_ID : CC_ADXL_MISSING);
        return;
    }
    // Full-resolution +/-2g; 100 Hz output data rate; start measurements.
    if (!cc_adxl_write(0x31u, 0x08u) ||
        !cc_adxl_write(0x2Cu, 0x0Au) ||
        !cc_adxl_write(0x2Du, 0x08u)) {
        cc_adxl.valid = false;
        cc_adxl_status(CC_ADXL_IO_ERROR);
        return;
    }
    cc_adxl.failed_reads = 0;
    cc_adxl.valid = false;
    cc_adxl.last_read = (uint16_t)(timer_read() - 200u);
    cc_adxl_status(CC_ADXL_OK);
}

static void cc_adxl_poll(void) {
    // Sensor reads run only while the MATRIX/detection screen is open.
    if (cc_adxl.status != CC_ADXL_OK) {
        if (timer_elapsed(cc_adxl.last_probe) >= 1500u) cc_adxl_probe();
        return;
    }
    if (timer_elapsed(cc_adxl.last_read) < 170u) return;
    cc_adxl.last_read = timer_read();

    uint8_t data[6];
    if (!cc_adxl_read(0x32u, data, sizeof(data))) {
        if (++cc_adxl.failed_reads >= 3u) {
            cc_adxl.failed_reads = 0;
            cc_adxl.valid = false;
            cc_adxl.last_probe = timer_read();
            cc_adxl_status(CC_ADXL_IO_ERROR);
        }
        return;
    }
    cc_adxl.failed_reads = 0;
    const int16_t x = (int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8));
    const int16_t y = (int16_t)((uint16_t)data[2] | ((uint16_t)data[3] << 8));
    const int16_t z = (int16_t)((uint16_t)data[4] | ((uint16_t)data[5] << 8));
    if (!cc_adxl.valid || cc_adxl.x != x || cc_adxl.y != y || cc_adxl.z != z) {
        cc_adxl.x = x;
        cc_adxl.y = y;
        cc_adxl.z = z;
        cc_adxl.valid = true;
        cc_adxl.changed = true;
    }
}
#else
static void cc_adxl_init(void) {}
static void cc_adxl_poll(void) {}
#endif
