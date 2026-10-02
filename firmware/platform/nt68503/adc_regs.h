/* SPDX-License-Identifier: MIT */
#ifndef NT68503_ADC_REGS_H
#define NT68503_ADC_REGS_H
/* 8051 XDATA ADC register aliases. Values are raw8-bit samples.
 * Unchecked channel expressions require the range in the macro name.
 * Hardware map: docs/nt68503-hardware.md; firmware evidence: CODE C072. */
#define NT_ADC_ENABLE_H 0xF080u
#define NT_ADC_CTRL_0 0xF3C0u
#define NT_ADC_CTRL_1 0xF3C1u
#define NT_ADC_CTRL_2 0xF3C2u
#define NT_ADC_CTRL_3 0xF3C3u
#define NT_ADC_VALUE_1_8(c) (0xF3C5u+(c)-1u)
#define NT_ADC_VALUE_9_10(c) (0xF3D5u+(c)-9u)
#define NT_ADC_VALUE_11_12(c) (0xF5D5u+(c)-11u)
#endif
