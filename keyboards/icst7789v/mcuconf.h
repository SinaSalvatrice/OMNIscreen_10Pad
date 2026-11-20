#pragma once

#include_next <mcuconf.h>

#undef RP_SPI_USE_SPI0
#define RP_SPI_USE_SPI0 TRUE

// Enable the RP2040 ADC peripheral for the GP28 slide potentiometer.
#undef RP_ADC_USE_ADC1
#define RP_ADC_USE_ADC1 TRUE
