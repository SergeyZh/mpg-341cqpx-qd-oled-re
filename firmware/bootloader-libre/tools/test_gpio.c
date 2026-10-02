/* SPDX-License-Identifier: MIT
 * Execute the real gpio.c on the host with MMIO replaced by a register model.
 * This checks addresses, masks and ordering, NOT the electrical GPIO behavior.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static uint8_t registers[0x10000];
static unsigned reads, writes;
static uint16_t written_address[4];
static uint8_t written_value[4];

static uint8_t mock_read(uint16_t address)
{
    assert(address >= 0xF000u);
    ++reads;
    return registers[address];
}

static void mock_write(uint16_t address, uint8_t value)
{
    assert(address >= 0xF000u);
    assert(writes < 4u);
    written_address[writes] = address;
    written_value[writes++] = value;
    registers[address] = value;
}

/* Skip the target-only SFR declarations; gpio.c itself is included unchanged. */
#define NT68503_H
#define __code
#define xread(address) mock_read(address)
#define xwrite(address, value) mock_write((address), (uint8_t)(value))
#include "../src/gpio.c"

/* Independent literal oracle: Ghidra FW.037 Main 7A864 / 7ABC4 / 7AD80,
 * AHB addresses translated to XDATA. Rows: banks 1..17; DATA, DIR, REG3, REG4.
 * Deliberately do not reproduce the implementation's address formulas here.
 */
static const uint16_t expected[17][4] = {
    {0xF000, 0xF005, 0xF0B0, 0xF0C7},
    {0xF001, 0xF006, 0xF0B1, 0xF0C8},
    {0xF002, 0xF007, 0xF0B2, 0xF0C9},
    {0xF003, 0xF008, 0xF0B3, 0xF0CA},
    {0xF004, 0xF009, 0xF0B4, 0xF0CB},
    {0xF010, 0xF011, 0xF0B5, 0xF0CE},
    {0xF012, 0xF013, 0xF0B6, 0xF0CF},
    {0xF114, 0xF115, 0xF130, 0xF138},
    {0xF116, 0xF117, 0xF131, 0xF139},
    {0xF118, 0xF119, 0xF132, 0xF13A},
    {0xF11A, 0xF11B, 0xF133, 0xF13B},
    {0xF11C, 0xF11D, 0xF134, 0xF13C},
    {0xF11E, 0xF11F, 0xF135, 0xF13D},
    {0xF300, 0xF310, 0xF320, 0xF330},
    {0xF301, 0xF311, 0xF321, 0xF331},
    {0xF302, 0xF312, 0xF322, 0xF332},
    {0xF303, 0xF313, 0xF323, 0xF333},
};

static void reset_accesses(void)
{
    reads = writes = 0;
}

static void test_map_and_invalid(void)
{
    unsigned bank, reg, pin;
    static const enum gpio_register invalid_regs[] = {
        (enum gpio_register)-1, (enum gpio_register)4, (enum gpio_register)255
    };
    struct gpio_bank_state state = {0, 0x12, 0x34, 0x56};

    for (bank = 0; bank < 256; ++bank) {
        int valid = bank >= 1 && bank <= 17;
        for (reg = 0; reg < 4; ++reg) {
            uint16_t address = gpio_register_address(bank, reg);
            assert(address == (valid ? expected[bank - 1][reg] : 0));
            reset_accesses();
            gpio_update_bank(bank, reg, 0, 0xFF);
            assert(reads == 0 && writes == 0);
            if (!valid) {
                assert(gpio_read_bank(bank, reg) == 0);
                gpio_update_bank(bank, reg, 0xFF, 0xFF);
                assert(reads == 0 && writes == 0);
            } else {
                registers[address] = 0xA5;
                assert(gpio_read_bank(bank, reg) == 0xA5);
                assert(reads == 1 && writes == 0);
            }
        }
        for (reg = 0; reg < sizeof(invalid_regs) / sizeof(invalid_regs[0]); ++reg) {
            reset_accesses();
            assert(gpio_register_address(bank, invalid_regs[reg]) == 0);
            assert(gpio_read_bank(bank, invalid_regs[reg]) == 0);
            gpio_update_bank(bank, invalid_regs[reg], 0xFF, 0xFF);
            assert(reads == 0 && writes == 0);
        }
        if (!valid) {
            state.bank = bank;
            reset_accesses();
            gpio_apply_bank_state(&state);
            assert(reads == 0 && writes == 0);
        }
    }
    /* Invalid packed values and macro arguments must never alias a real pin. */
    for (pin = 0; pin < 256; ++pin) {
        if (pin >= 8 && pin <= 143) continue;
        reset_accesses();
        gpio_write(pin, GPIO_LOW);
        gpio_write(pin, GPIO_HIGH);
        gpio_configure(pin, GPIO_INPUT);
        gpio_configure(pin, GPIO_OUTPUT_LOW);
        gpio_configure(pin, GPIO_OUTPUT_HIGH);
        assert(gpio_read(pin) == 0);
        assert(reads == 0 && writes == 0);
    }
    assert(GPIO_PIN(0, 0) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(18, 0) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(33, 0) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(256, 0) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(-1, 0) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(1, 8) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(1, 256) == GPIO_INVALID_PIN);
    assert(GPIO_PIN(1, -1) == GPIO_INVALID_PIN);
}

static void test_pins(void)
{
    unsigned bank, bit, pad, d, level;
    static const uint8_t directions[] = {0x00, 0x55, 0xAA, 0xFF};
    for (bank = 1; bank <= 17; ++bank) {
        uint16_t data = expected[bank - 1][0], dir = expected[bank - 1][1];
        for (bit = 0; bit < 8; ++bit) {
            gpio_pin_t pin = GPIO_PIN(bank, bit);
            uint8_t mask = (uint8_t)(1u << bit);
            assert(pin == bank * 8 + bit);
            for (pad = 0; pad < 256; ++pad) {
                registers[data] = pad;
                reset_accesses();
                assert(gpio_read(pin) == ((pad >> bit) & 1));
                assert(reads == 1 && writes == 0);
                for (d = 0; d < sizeof(directions); ++d) {
                    for (level = 0; level < 2; ++level) {
                        uint8_t want = (uint8_t)((pad | directions[d]) & ~mask);
                        if (level) want |= mask;
                        registers[data] = pad; /* Pad snapshot, not latch contents. */
                        registers[dir] = directions[d];
                        reset_accesses();
                        gpio_write(pin, level ? GPIO_HIGH : GPIO_LOW);
                        assert(writes == 1 && reads == 2);
                        assert(written_address[0] == data && written_value[0] == want);
                        assert(registers[dir] == directions[d]);
                    }
                }
            }
            for (level = 0; level < 2; ++level) {
                registers[data] = 0x3C;
                registers[dir] = 0xA5;
                reset_accesses();
                gpio_configure(pin, level ? GPIO_OUTPUT_HIGH : GPIO_OUTPUT_LOW);
                assert(writes == 2);
                assert(written_address[0] == data); /* Set latch before output enable. */
                assert(written_value[0] == (uint8_t)(((0x3C | 0xA5) & ~mask) |
                                                   (level ? mask : 0)));
                assert(written_address[1] == dir);
                assert(written_value[1] == (uint8_t)(0xA5 & ~mask));
            }
            registers[dir] = 0x5A;
            reset_accesses();
            gpio_configure(pin, GPIO_INPUT);
            assert(reads == 1 && writes == 1);
            assert(written_address[0] == dir && written_value[0] == (0x5A | mask));
            reset_accesses();
            gpio_write(pin, (enum gpio_level)2);
            assert(reads == 0 && writes == 0);
            gpio_configure(pin, (enum gpio_action)255);
            assert(writes == 0);
        }
    }
}

static void test_masks_and_states(void)
{
    unsigned bank, reg, mask, p, v;
    static const uint8_t patterns[] = {0x00, 0x5A, 0xA5, 0xFF};
    for (bank = 1; bank <= 17; ++bank) {
        const uint16_t *row = expected[bank - 1];
        struct gpio_bank_state state = {bank, 0x12, 0x34, 0x56};
        for (reg = 0; reg < 4; ++reg) {
            for (mask = 1; mask < 256; ++mask) {
                for (p = 0; p < sizeof(patterns); ++p) {
                    for (v = 0; v < sizeof(patterns); ++v) {
                        uint8_t old = patterns[p];
                        uint8_t want;
                        registers[row[1]] = 0x69;
                        registers[row[reg]] = old;
                        if (reg == GPIO_REG_DATA) old |= 0x69;
                        want = (old & (uint8_t)~mask) | (patterns[v] & mask);
                        reset_accesses();
                        gpio_update_bank(bank, reg, mask, patterns[v]);
                        assert(writes == 1);
                        assert(reads == (reg == GPIO_REG_DATA ? 2u : 1u));
                        assert(written_address[0] == row[reg] && written_value[0] == want);
                    }
                }
            }
        }
        registers[row[3]] = 0x78;
        reset_accesses();
        gpio_apply_bank_state(&state);
        assert(reads == 0 && writes == 3);
        assert(written_address[0] == row[2] && written_value[0] == 0x12);
        assert(written_address[1] == row[0] && written_value[1] == 0x34);
        assert(written_address[2] == row[1] && written_value[2] == 0x56);
        assert(registers[row[3]] == 0x78); /* Never implicitly touch REG4. */
        assert(gpio_read_reg3(bank) == 0x12);
        assert(gpio_read_data(bank) == 0x34);
        assert(gpio_read_direction(bank) == 0x56);
        assert(gpio_read_reg4(bank) == 0x78);
    }
}

int main(void)
{
    test_map_and_invalid();
    test_pins();
    test_masks_and_states();
    puts("verified GPIO: 68 addresses, 136 pins, masks, invalid inputs and MMIO ordering");
    return 0;
}
