/* SPDX-License-Identifier: MIT */
#ifndef RECOVERY_H
#define RECOVERY_H

#include <stdint.h>

#define JOYSTICK_RIGHT 1u
#define JOYSTICK_LEFT  2u
#define JOYSTICK_DOWN  3u
#define JOYSTICK_UP    4u

/* Configure channel 5 before the UART banner provides ADC settling time. */
void joystick_init(void);

/* Sample once, report a recognized direction and return JOYSTICK_* or zero. */
uint8_t joystick_report(void);

/* Bring up USB-B and raw service I2C, then retain the stock F00A polling writes. */
void enter_recovery(void);

#endif
