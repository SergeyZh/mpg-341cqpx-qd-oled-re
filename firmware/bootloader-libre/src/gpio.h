/* SPDX-License-Identifier: MIT */
#ifndef GPIO_H
#define GPIO_H

#include <stdint.h>
#include "gpio_regs.h"

typedef uint8_t gpio_bank_t;
typedef uint8_t gpio_pin_t;

/* Banks are numbered 1..17 (decimal), bits 0..7. Use side-effect-free arguments.
 * Check before packing so invalid banks/bits cannot wrap to another real pin.
 */
#define GPIO_BANK_COUNT NT_GPIO_COUNT
#define GPIO_INVALID_PIN ((gpio_pin_t)0u)
#define GPIO_PIN(bank, bit) \
    (((uint32_t)(bank) >= 1u && (uint32_t)(bank) <= GPIO_BANK_COUNT && \
      (uint32_t)(bit) <= 7u) \
     ? (gpio_pin_t)(((uint8_t)(bank) << 3) | (uint8_t)(bit)) : GPIO_INVALID_PIN)

enum gpio_register {
    GPIO_REG_DATA,
    GPIO_REG_DIR,
    GPIO_REG3,
    GPIO_REG4,
};

enum gpio_action {
    GPIO_INPUT,
    GPIO_OUTPUT_LOW,
    GPIO_OUTPUT_HIGH,
};

enum gpio_level {
    GPIO_LOW,
    GPIO_HIGH,
};

/* Recovery subset of Main's cold-start state. REG4 is deliberately untouched. */
struct gpio_bank_state {
    gpio_bank_t bank;
    uint8_t reg3;
    uint8_t data;
    uint8_t direction;
};

void gpio_apply_bank_state(const struct gpio_bank_state __code *state);

/* Invalid bank/register: address/read returns 0, update is a no-op (no MMIO).
 * Address is the 8051 XDATA alias, not the Leon2 AHB address.
 */
uint16_t gpio_register_address(gpio_bank_t bank, enum gpio_register reg);
uint8_t gpio_read_bank(gpio_bank_t bank, enum gpio_register reg);

/* Replace only masked bits. DATA reads pad levels, so input latches outside
 * mask are released HIGH as in Main's HAL; other output bits are preserved.
 * DIR/REG3/REG4 use ordinary RMW. mask=0 performs no MMIO.
 * Not atomic against other GPIO writers. No implicit REG3/REG4 mode changes.
 */
void gpio_update_bank(gpio_bank_t bank, enum gpio_register reg,
                      uint8_t mask, uint8_t value);

/* Set direction and output level; leave the bank state's REG3 unchanged. */
void gpio_configure(gpio_pin_t gpio, enum gpio_action action);

/* Change one output, preserving other outputs and releasing input latches high. */
void gpio_write(gpio_pin_t gpio, enum gpio_level level);
uint8_t gpio_read(gpio_pin_t gpio);

uint8_t gpio_read_reg3(gpio_bank_t bank);
uint8_t gpio_read_reg4(gpio_bank_t bank);
uint8_t gpio_read_data(gpio_bank_t bank);
uint8_t gpio_read_direction(gpio_bank_t bank);

#endif
