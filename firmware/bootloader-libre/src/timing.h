/* SPDX-License-Identifier: MIT */
#ifndef TIMING_H
#define TIMING_H

#include <stdint.h>

/*
 * Busy waits used before stbc-main configures the clock tree and timers.
 * One recovery period corresponds to the old 255 x 255 polling loop.  The
 * exact wall time depends on REG_CHIP_VARIANT; only the ordering and the 1:4
 * ratio between settle and USB-reset waits are part of the contract.
 */
void delay_recovery_periods(uint8_t periods);
void delay_flash_poll(void);

#endif
