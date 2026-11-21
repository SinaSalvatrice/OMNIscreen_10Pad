#include <assert.h>
#include <stdio.h>
#include "cc_editor_modifiers.h"

static uint8_t host_mods;
static unsigned reports;
void add_mods(uint8_t mods) { host_mods |= mods; }
void del_mods(uint8_t mods) { host_mods &= (uint8_t)~mods; }
void send_keyboard_report(void) { ++reports; }

static void reset(void) {
    omp_mod_release_all();
    host_mods = 0;
    reports = 0;
}
int main(void) {
    reset();
    // German Windows: QMK LCTL(KC_Y)=0x011C, OS reads Ctrl+Z.
    assert(omp_mod_mask(0x011Cu) == 0x01u);
    omp_mod_update(omp_mod_mask(0x011Cu), true);
    assert(host_mods == 0x01u && reports == 1);
    // Unlike weak modifiers, this remains pressed through unrelated key input.
    assert(host_mods == 0x01u);
    omp_mod_update(omp_mod_mask(0x011Cu), false);
    assert(host_mods == 0 && reports == 2);

    reset();
    assert(omp_mod_mask(0x1104u) == 0x10u); // right Ctrl
    assert(omp_mod_mask(0x061Bu) == 0x06u); // left Shift+Alt
    assert(omp_mod_mask(0x00E0u) == 0x01u); // physical Ctrl
    omp_mod_update(omp_mod_mask(0x00E0u), true);
    omp_mod_update(omp_mod_mask(0x011Cu), true);
    assert(host_mods == 0x01u && omp_mod_refs[0] == 2 && reports == 1);
    omp_mod_update(omp_mod_mask(0x011Cu), false);
    assert(host_mods == 0x01u && omp_mod_refs[0] == 1);
    omp_mod_update(omp_mod_mask(0x00E0u), false);
    assert(host_mods == 0 && omp_mod_refs[0] == 0);

    reset();
    omp_mod_update(0x06u, true);
    assert(host_mods == 0x06u);
    omp_mod_update(0x02u, true);
    omp_mod_update(0x06u, false);
    assert(host_mods == 0x02u);
    omp_mod_release_all();
    assert(host_mods == 0);
    omp_mod_update(0x02u, false); // underflow must not reapply anything
    assert(host_mods == 0);
    puts("OmniPad modifier tests: PASS");
    return 0;
}
