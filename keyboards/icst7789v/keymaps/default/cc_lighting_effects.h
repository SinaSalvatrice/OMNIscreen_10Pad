// Base effects shared by the profile renderer and the standalone timing.
#pragma once
#include "color.h"

static uint16_t cc_light_interval(uint8_t speed) {
    const uint32_t inverse = 255u - speed;
    return 20u + inverse * inverse / 130u;
}

static rgb_t omp_rgb(uint16_t packed) {
    return (rgb_t){
        .r = ((packed >> 11) & 31u) * 255u / 31u,
        .g = ((packed >> 5) & 63u) * 255u / 63u,
        .b = (packed & 31u) * 255u / 31u,
    };
}

static rgb_t omp_mix(rgb_t a, rgb_t b, uint8_t blend) {
    return (rgb_t){
        .r = ((uint16_t)a.r * (255u - blend) + (uint16_t)b.r * blend) / 255u,
        .g = ((uint16_t)a.g * (255u - blend) + (uint16_t)b.g * blend) / 255u,
        .b = ((uint16_t)a.b * (255u - blend) + (uint16_t)b.b * blend) / 255u,
    };
}

static rgb_t omp_scale_rgb(rgb_t color, uint8_t level) {
    return (rgb_t){color.r * level / 255u, color.g * level / 255u, color.b * level / 255u};
}

static uint8_t omp_triangle(uint8_t phase) {
    return 2u * (phase < 128 ? phase : 255u - phase);
}

static rgb_t omp_effect_pixel(uint8_t effect, rgb_t a, rgb_t b, uint8_t level,
                              uint8_t position, uint8_t count, uint32_t step, uint8_t phase) {
    uint8_t blend = 0;
    const uint8_t offset = step % count;
    switch (effect) {
        case 1: blend = (position & 1u) ? 255 : 0; break;
        case 2: blend = position >= count / 2u ? 255 : 0; break;
        case 3: blend = (uint16_t)position * 255u / (count - 1u); break;
        case 4: blend = (position + offset) % count < 4u ? 0 : 255; break;
        case 5: level = (uint16_t)level * (32u + omp_triangle(phase) * 7u / 8u) / 255u; break;
        case 6:
        case 12: {
            uint8_t distance = (position + count - offset) % count;
            if (effect == 12) {
                const uint8_t second = (distance + count - count / 2u) % count;
                if (second < distance) distance = second;
            }
            level = distance < 8u ? (uint16_t)level * (8u - distance) / 8u : level / 16u;
            break;
        }
        case 7: blend = ((uint16_t)position * 37u + (step % 97u) * 13u) % 97u < 8u ? 255 : 0; break;
        case 8:
            a = hsv_to_rgb((hsv_t){(uint8_t)(position * 256u / count + phase), 255, 255});
            break;
        case 9: {
            const uint8_t span = count - 1u;
            uint8_t head = step % (2u * span);
            if (head > span) head = 2u * span - head;
            const uint8_t distance = position > head ? position - head : head - position;
            level = distance < 4u ? (uint16_t)level * (4u - distance) / 4u : level / 16u;
            break;
        }
        case 10: blend = omp_triangle(phase + position * 256u / count); break;
        case 11: blend = omp_triangle(phase); break;
        default: break;
    }
    return omp_scale_rgb(omp_mix(a, b, blend), level);
}
