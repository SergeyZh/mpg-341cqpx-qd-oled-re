/* SPDX-License-Identifier: MIT */

#include <stdint.h>
#include "timing.h"

void delay_recovery_periods(uint8_t periods)
{
    uint8_t middle;
    uint8_t inner;

    do {
        middle = 0xFFu;
        do {
            inner = 0xFFu;
            do {
                --inner;
            } while (inner != 0u);
            --middle;
        } while (middle != 0u);
        --periods;
    } while (periods != 0u);
}

void delay_flash_poll(void)
{
    volatile uint8_t remaining = 10u;

    while (remaining != 0u) {
        --remaining;
    }
}
