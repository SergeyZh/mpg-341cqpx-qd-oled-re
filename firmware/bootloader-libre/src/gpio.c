/* SPDX-License-Identifier: MIT
 *
 * GPIO register mapping and pin-level operations for all 17 NT68503 banks.
 */

#include <stdint.h>
#include "gpio.h"
#include "nt68503.h"

#define NO_REGISTER 0u

uint16_t gpio_register_address(gpio_bank_t bank, enum gpio_register reg)
{
    if (bank == 0u || bank > GPIO_BANK_COUNT) {
        return NO_REGISTER;
    }

    /* Piecewise map recovered from Main's switches, not one linear array.
     * XDATA = 0xF000 + (AHB - 0xCF03C000) / 4.
     * Evidence: FW.037 Main 7A864 (DATA), 7ABC4 (DIR), 7AD80 (REG3/4).
     */
    switch (reg) {
    case GPIO_REG_DATA:
    case GPIO_REG_DIR:
        if (bank <= 5u) {
            return (reg == GPIO_REG_DATA ? NT_GPIO_DATA_1_5(1u) : NT_GPIO_DIR_1_5(1u)) + bank - 1u;
        }
        if (bank <= 7u) {
            return NT_GPIO_DATA_6_7(6u) + (uint16_t)(bank - 6u) * 2u +
                   (reg == GPIO_REG_DIR ? 1u : 0u);
        }
        if (bank <= 13u) {
            return NT_GPIO_DATA_8_13(8u) + (uint16_t)(bank - 8u) * 2u +
                   (reg == GPIO_REG_DIR ? 1u : 0u);
        }
        return (reg == GPIO_REG_DATA ? NT_GPIO_DATA_14_17(14u) : NT_GPIO_DIR_14_17(14u)) + bank - 14u;
    case GPIO_REG3:
        if (bank <= 7u) {
            return NT_GPIO_REG3_1_7(1u) + bank - 1u;
        }
        if (bank <= 13u) {
            return NT_GPIO_REG3_8_13(8u) + bank - 8u;
        }
        return NT_GPIO_REG3_14_17(14u) + bank - 14u;
    case GPIO_REG4:
        if (bank <= 5u) {
            return NT_GPIO_REG4_1_5(1u) + bank - 1u;
        }
        if (bank <= 7u) {
            /* F0CC/F0CD are NOT REG4 of banks 6/7. */
            return NT_GPIO_REG4_6_7(6u) + bank - 6u;
        }
        if (bank <= 13u) {
            return NT_GPIO_REG4_8_13(8u) + bank - 8u;
        }
        return NT_GPIO_REG4_14_17(14u) + bank - 14u;
    default:
        return NO_REGISTER;
    }
}

uint8_t gpio_read_bank(gpio_bank_t bank, enum gpio_register reg)
{
    uint16_t address = gpio_register_address(bank, reg);
    return address == NO_REGISTER ? 0u : xread(address);
}

void gpio_update_bank(gpio_bank_t bank, enum gpio_register reg,
                      uint8_t mask, uint8_t value)
{
    uint16_t address = gpio_register_address(bank, reg);
    uint8_t current;

    if (address == NO_REGISTER || mask == 0u) {
        return;
    }
    current = xread(address);
    if (reg == GPIO_REG_DATA) {
        /* DATA reads pads, not latches: release unselected input latches. */
        current |= gpio_read_direction(bank);
    }
    xwrite(address, (current & (uint8_t)~mask) | (value & mask));
}

static gpio_bank_t gpio_bank(gpio_pin_t gpio)
{
    return gpio >> 3;
}

static uint8_t gpio_mask(gpio_pin_t gpio)
{
    return (uint8_t)(1u << (gpio & 7u));
}

void gpio_apply_bank_state(const struct gpio_bank_state __code *state)
{
    uint16_t reg3_register = gpio_register_address(state->bank, GPIO_REG3);
    uint16_t data_register = gpio_register_address(state->bank, GPIO_REG_DATA);
    uint16_t direction_register = gpio_register_address(state->bank, GPIO_REG_DIR);

    if (reg3_register == NO_REGISTER || data_register == NO_REGISTER ||
        direction_register == NO_REGISTER) {
        return;
    }

    /* GPIO8.0: REG3 enables strong HIGH drive (push-pull), measured on NT68503.
     * Other banks remain unverified; retain the neutral name and stock values.
     * See docs/gpio.md, experiment of 2026-09-13.
     */
    xwrite(reg3_register, state->reg3);
    xwrite(data_register, state->data);
    xwrite(direction_register, state->direction);
}

void gpio_write(gpio_pin_t gpio, enum gpio_level level)
{
    if (level != GPIO_LOW && level != GPIO_HIGH) {
        return;
    }
    gpio_update_bank(gpio_bank(gpio), GPIO_REG_DATA, gpio_mask(gpio),
                     level == GPIO_HIGH ? 0xFFu : 0u);
}

uint8_t gpio_read(gpio_pin_t gpio)
{
    return (gpio_read_data(gpio_bank(gpio)) & gpio_mask(gpio)) != 0u;
}

void gpio_configure(gpio_pin_t gpio, enum gpio_action action)
{
    uint16_t direction_register = gpio_register_address(gpio_bank(gpio), GPIO_REG_DIR);
    uint8_t mask = gpio_mask(gpio);
    uint8_t direction;

    if (direction_register == NO_REGISTER) {
        return;
    }

    direction = xread(direction_register);
    switch (action) {
    case GPIO_INPUT:
        direction |= mask;
        break;
    case GPIO_OUTPUT_LOW:
        gpio_write(gpio, GPIO_LOW);
        direction &= (uint8_t)~mask;
        break;
    case GPIO_OUTPUT_HIGH:
        gpio_write(gpio, GPIO_HIGH);
        direction &= (uint8_t)~mask;
        break;
    default:
        return;
    }
    xwrite(direction_register, direction);
}

uint8_t gpio_read_reg3(gpio_bank_t bank)
{
    return gpio_read_bank(bank, GPIO_REG3);
}

uint8_t gpio_read_reg4(gpio_bank_t bank)
{
    return gpio_read_bank(bank, GPIO_REG4);
}

uint8_t gpio_read_data(gpio_bank_t bank)
{
    return gpio_read_bank(bank, GPIO_REG_DATA);
}

uint8_t gpio_read_direction(gpio_bank_t bank)
{
    return gpio_read_bank(bank, GPIO_REG_DIR);
}
