/* SPDX-License-Identifier: MIT */
#ifndef NT68503_H
#define NT68503_H

#include <stdint.h>
#include "adc_regs.h"

#define CREG(address) (*((const __code uint8_t *)(address)))
#define XREG(address) (*((volatile __xdata uint8_t *)(address)))
#define xread(address) ((uint8_t)XREG(address))
#define xwrite(address, value) \
    do { XREG(address) = (uint8_t)(value); } while (0)

/* Standard 8051 SFRs used by the debug UART. */
__sfr __at (0x81) SP;
__sfr __at (0x87) PCON;
__sfr __at (0x89) TMOD;
__sfr __at (0x8D) TH1;
__sfr __at (0x98) SCON;
__sfr __at (0x99) SBUF;
__sbit __at (0x8E) TR1;
__sbit __at (0x98) RI;
__sbit __at (0x99) TI;
__sbit __at (0xAF) EA;

#define REG_CHIP_VARIANT 0xD511u
#define REG_CLOCK_INDEX  0xD929u

/* Service UART port 4 and raw-I2C slave channel 1. */
#define REG_SERVICE_PINMUX  0xF030u
#define REG_SERVICE_UART    0xF06Eu
#define REG_SERVICE_UART_AUX 0xF072u
#define REG_SLAVE0_RESET_A  0xF01Cu
#define REG_SLAVE0_RESET_B  0xF181u
#define REG_RAW_SLAVE_CTRL  0xF041u
#define REG_RAW_SLAVE_CFG   0xF043u
#define REG_RAW_SLAVE_DATA  0xF045u
#define REG_RAW_SLAVE_ADDR  0xF048u

/* ADC block; channel 5 is the joystick resistor ladder. */
#define REG_ADC_ENABLE_H NT_ADC_ENABLE_H
#define REG_ADC_CTRL_0   NT_ADC_CTRL_0
#define REG_ADC_CTRL_1   NT_ADC_CTRL_1
#define REG_ADC_CTRL_2   NT_ADC_CTRL_2
#define REG_ADC_CTRL_3   NT_ADC_CTRL_3
#define REG_ADC_KEY      NT_ADC_VALUE_1_8(5u)

#include "flash_regs.h"

#define REG_BOOT_CTRL    0xF1D0u
#define REG_BOOT_DST_L   0xF1D1u
#define REG_BOOT_DST_H   0xF1D2u
#define REG_BOOT_SRC_L   0xF1D3u
#define REG_BOOT_SRC_M   0xF1D4u
#define REG_BOOT_SRC_H   0xF1D5u
#define REG_BOOT_SIZE_L  0xF1D6u
#define REG_BOOT_SIZE_M  0xF1D7u
#define REG_BOOT_SIZE_H  0xF1D8u

#define REG_STBC_CTRL    0xF1A8u
/* Measured 2026-09-03: 55 starts/reloads an approximately 6-second watchdog;
 * AA disables it. Do not infer which core each register resets.
 * bootloader-a currently writes only F0E0=DISABLE; F0E2 is not changed here.
 */
#define REG_WATCHDOG_F0E0       0xF0E0u
#define REG_WATCHDOG_F0E2       0xF0E2u
#define WATCHDOG_DISABLE        0xAAu
#define WATCHDOG_START_OR_RELOAD 0x55u

/* F00A was wrongly called WATCHDOG_A. Its function is still unknown:
 * writing 55 did not reset the monitor during a 200-second ISP test.
 * Keep the original writes, but name values by usage, not guessed semantics.
 */
#define REG_UNKNOWN_F00A        0xF00Au
#define F00A_BOOT_INIT_VALUE    0xAAu
#define F00A_STOCK_POLL_VALUE   0x55u

#endif
