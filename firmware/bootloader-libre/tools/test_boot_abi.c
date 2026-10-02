/* SPDX-License-Identifier: MIT
 * Execute bootloader.c's real table selection, F1D preparation and ABI builder
 * on the host. Only CODE/XDATA access and external peripherals are mocked.
 */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t code_memory[0x10000];
static uint8_t xdata_memory[0x10000];
static uint16_t write_addresses[0x1200];
static unsigned write_count, bank_calls, bus_calls;
static uint8_t selected_bank;
static uint8_t joystick_direction;
static unsigned joystick_reads, flash_init_calls;
static jmp_buf boot_exit;
static int running_boot;

static void mock_write(uint16_t address, uint8_t value)
{
    assert(write_count < sizeof(write_addresses) / sizeof(write_addresses[0]));
    write_addresses[write_count++] = address;
    xdata_memory[address] = value;
    if (running_boot && address == 0xF1D0) {
        assert(value == 0x87);
        longjmp(boot_exit, 1);
    }
}

/* Retain real register constants, replacing only SDCC storage declarations. */
#define __sfr uint8_t
#define __sbit uint8_t
#define __at(address)
#define __code
#include "../src/nt68503.h"
#undef CREG
#undef xread
#undef xwrite
#define CREG(address) code_memory[(uint16_t)(address)]
#define xread(address) xdata_memory[(uint16_t)(address)]
#define xwrite(address, value) mock_write((uint16_t)(address), (uint8_t)(value))
#define main bootloader_entry
#include "../src/bootloader.c"
#undef main

void flash_controller_init(void) { ++flash_init_calls; }
uint8_t flash_is_supported(void) { return 1; }
uint8_t flash_get_bank(void) { return selected_bank; }
void flash_set_bank(uint8_t bank) { ++bank_calls; selected_bank = bank; }
void flash_configure_bus(void) { ++bus_calls; }
void joystick_init(void) {}
uint8_t joystick_report(void) { ++joystick_reads; return joystick_direction; }
void enter_recovery(void)
{
    assert(running_boot);
    longjmp(boot_exit, 2);
}
void uart_init(uint8_t variant) { (void)variant; }
void uart_puts(const char *text) { (void)text; }
void uart_drain(void) {}
void uart_hex16(uint16_t value) { (void)value; }

/* Independent literal oracle from docs/bootloader.md section 6. Deliberately
 * do not use boot_abi.h types, offsets or constants to compute expected bytes.
 */
static void expected_share(uint16_t table, uint8_t out[0x9A])
{
    static const unsigned copies[][3] = {
        /* table offset, share offset, byte count */
        {0x08, 0x02, 8}, {0x10, 0x0E, 8},
        {0x18, 0x16, 4}, {0x1C, 0x1E, 4}, {0x20, 0x22, 4},
        {0x28, 0x32, 8}, {0x30, 0x3A, 4}, {0x34, 0x42, 4},
        {0x40, 0x46, 8}, {0x38, 0x5A, 8},
        {0x48, 0x6A, 8}, {0x50, 0x76, 8}, {0x58, 0x82, 8}, {0x60, 0x8E, 8},
    };
    unsigned i;
    memset(out, 0, 0x9A);
    out[1] = 1;
    for (i = 0; i < sizeof(copies) / sizeof(copies[0]); ++i) {
        memcpy(out + copies[i][1], code_memory + table + copies[i][0], copies[i][2]);
    }
    memcpy(out + 0x1A, "\x9f\x06\x00\x00", 4);
    memcpy(out + 0x3E, "\x9f\x19\x60\x00", 4);
    memcpy(out + 0x54, "\x07\xff", 2);
    memcpy(out + 0x66, "\x87\x20\x05\x00", 4);
}

static void check_prepare(uint16_t table, unsigned patch_enabled, unsigned patch_and)
{
    static const uint16_t f1d_order[] = {
        0xF1D3, 0xF1D4, 0xF1D5, 0xF1D1, 0xF1D2, 0xF1D6, 0xF1D7, 0xF1D8
    };
    uint8_t expected[0x9A];
    unsigned i, f1d_count = 0;
    expected_share(table, expected);
    memset(xdata_memory, 0xA5, sizeof(xdata_memory));
    write_count = bank_calls = bus_calls = 0;
    selected_bank = 0xCC;
    clear_shared_memory();
    assert(write_count == 0x1000);
    for (i = 0; i < 0x1000; ++i) {
        assert(write_addresses[i] == 0x3000 + i);
    }
    write_count = 0;
    prepare_stbc_main(table);
    assert(memcmp(xdata_memory + 0x3000, expected, sizeof(expected)) == 0);
    for (i = 0x309A; i < 0x4000; ++i) {
        assert(xdata_memory[i] == 0);
    }
    assert(bank_calls == (code_memory[table] != 0));
    assert(selected_bank == (bank_calls ? code_memory[table] : 0xCC));
    assert(xdata_memory[0xF1D1] == 0 && xdata_memory[0xF1D2] == 0);
    assert(xdata_memory[0xF1D3] == code_memory[table + 3]);
    assert(xdata_memory[0xF1D4] == code_memory[table + 2]);
    assert(xdata_memory[0xF1D5] == code_memory[table + 1]);
    assert(xdata_memory[0xF1D6] == code_memory[table + 7]);
    assert(xdata_memory[0xF1D7] == code_memory[table + 6]);
    assert(xdata_memory[0xF1D8] == code_memory[table + 5]);
    assert(bus_calls == patch_enabled);
    for (i = 0; i < write_count; ++i) {
        uint16_t address = write_addresses[i];
        if (address >= 0xF1D1 && address <= 0xF1D8) {
            assert(f1d_count < sizeof(f1d_order) / sizeof(f1d_order[0]));
            assert(address == f1d_order[f1d_count++]);
        } else {
            assert((address >= 0x3000 && address < 0x309A) ||
                   (patch_enabled && address >= 0xF210 && address <= 0xF212));
        }
    }
    assert(f1d_count == 8);
    assert(xdata_memory[0x2FFF] == 0xA5 && xdata_memory[0x4000] == 0xA5);
    assert(xdata_memory[0xF1D0] == 0xA5); /* preparation must not start F1D */
    if (patch_enabled) {
        assert(xdata_memory[0xF210] == (0xA5 & 0x0F));
        assert(xdata_memory[0xF211] == (0xA5 | 0x80));
        assert(xdata_memory[0xF212] == (patch_and ? (0xA5 & 0x33) : (0xA5 | 0x33)));
    }
}

static void check_image(const char *path, uint16_t table)
{
    FILE *file = fopen(path, "rb");
    assert(file != NULL);
    assert(fread(code_memory, 1, sizeof(code_memory), file) == sizeof(code_memory));
    assert(fclose(file) == 0);
    assert(memcmp(code_memory + 0x7FF0, "DUALFW", 6) != 0);
    check_prepare(table, 0, 0);
}

/* Run the real entry point up to F1D/recovery, including the single joystick
 * sample retained across flash initialization. Both tables come from U4002.
 */
static void check_boot(uint8_t direction, uint8_t marker, uint16_t table)
{
    uint8_t expected[0x9A], saved_code[0x10000];
    int result;

    code_memory[0x7FFF] = marker;
    memcpy(saved_code, code_memory, sizeof(saved_code));
    expected_share(table, expected);
    memset(xdata_memory, 0xA5, sizeof(xdata_memory));
    write_count = bank_calls = bus_calls = joystick_reads = flash_init_calls = 0;
    selected_bank = 0;
    joystick_direction = direction;
    running_boot = 1;
    result = setjmp(boot_exit);
    if (result == 0) {
        bootloader_entry();
        assert(!"bootloader unexpectedly returned");
    }
    running_boot = 0;
    assert(joystick_reads == 1);
    assert(memcmp(saved_code, code_memory, sizeof(saved_code)) == 0);
    if (direction == 1) {
        assert(result == 2);
        assert(flash_init_calls == 0 && bank_calls == 0 && bus_calls == 0);
        assert(xdata_memory[0xF1D0] == 0xA5);
    } else {
        assert(result == 1 && flash_init_calls == 1 && bus_calls == 1);
        assert(selected_bank == (table == 0x7000 ? 1 : 0));
        assert(bank_calls == selected_bank);
        assert(memcmp(xdata_memory + 0x3000, expected, sizeof(expected)) == 0);
        assert(xdata_memory[0xF1D3] == code_memory[table + 3]);
        assert(xdata_memory[0xF1D4] == code_memory[table + 2]);
        assert(xdata_memory[0xF1D5] == code_memory[table + 1]);
        assert(xdata_memory[0xF1D6] == code_memory[table + 7]);
        assert(xdata_memory[0xF1D7] == code_memory[table + 6]);
        assert(xdata_memory[0xF1D8] == code_memory[table + 5]);
    }
}

int main(int argc, char **argv)
{
    unsigned i, seed, direction;
    /* Export the real producer's result for other projects' contract tests.
     * No sibling application source is linked into their firmware or tests.
     */
    if (argc == 5 && strcmp(argv[1], "--export-share") == 0) {
        FILE *file;
        uint16_t table;
        assert(strcmp(argv[3], "0x6000") == 0 || strcmp(argv[3], "0x7000") == 0);
        table = strcmp(argv[3], "0x6000") == 0 ? 0x6000 : 0x7000;
        check_image(argv[2], table);
        file = fopen(argv[4], "wb");
        assert(file != NULL);
        assert(fwrite(xdata_memory + SHARE_BASE, 1, sizeof(shared_structure_t), file)
               == sizeof(shared_structure_t));
        assert(fclose(file) == 0);
        return 0;
    }
    assert(argc == 4);
    check_image(argv[1], 0x6000);
    check_image(argv[2], 0x6000);
    check_image(argv[3], 0x7000);

    /* 64 KiB is 00 01 00 00 in the shared ABI, not a wrapped u16 zero.
     * Both table choices must program length registers 00 00 01. */
    for (i = 0; i < 2; ++i) {
        uint16_t table = i ? SLOT1_TABLE : SLOT0_TABLE;
        memcpy(code_memory + PARTITION_FIELD(table, stbc_main.size), "\x00\x01\x00\x00", 4);
        check_prepare(table, i && code_equal(DUALFW_SIGNATURE, "DUALFW", 6u), 0);
        assert(xdata_memory[REG_BOOT_SIZE_L] == 0);
        assert(xdata_memory[REG_BOOT_SIZE_M] == 0);
        assert(xdata_memory[REG_BOOT_SIZE_H] == 1);
    }

    /* Every marker and direction byte: up/down override, all others retain
     * the stock marker rule. Right is intercepted by main before selection.
     */
    for (i = 0; i < 256; ++i) {
        code_memory[0x7FFF] = (uint8_t)i;
        for (direction = 0; direction < 256; ++direction) {
            uint16_t table = direction == 4 ? 0x7000 : direction == 3 ? 0x6000 :
                i == 0xAA ? 0x7000 : 0x6000;
            assert(select_partition_table((uint8_t)direction) == table);
            if (direction <= 5) {
                check_boot((uint8_t)direction, (uint8_t)i, table);
            }
        }
    }
    /* Distinct bytes expose transpositions, dropped reserved records, ignored
     * size byte3 and id=10 size, and accidental lookup by ID rather than order.
     */
    memset(code_memory, 0, sizeof(code_memory));
    for (seed = 0; seed < 32; ++seed) {
        for (i = 0; i < 104; ++i) {
            code_memory[0x6000 + i] = (uint8_t)(seed + i * 17);
            code_memory[0x7000 + i] = (uint8_t)(seed + i * 31);
        }
        check_prepare(0x6000, 0, 0);
        check_prepare(0x7000, 0, 0);
    }
    memcpy(code_memory + 0x7FF0, "DUALFW\xf2\x10\x0f\x11\x80\x12\x33\x00", 14);
    check_prepare(0x6000, 0, 0); /* signature is ignored on the primary path */
    check_prepare(0x7000, 1, 0);
    code_memory[0x7FFD] = 1;
    check_prepare(0x7000, 1, 1);
    puts("verified boot ABI: real C, three firmware tables, 64 synthetic tables, "
         "256 markers x 256 directions, 1536 entry-point runs, "
         "154 shared bytes, F1D/EAR and DUALFW branches");
    return 0;
}
