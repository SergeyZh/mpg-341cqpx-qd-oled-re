/* SPDX-License-Identifier: MIT
 *
 * Top-level orchestration for the first NT68503 8051 core.
 *
 * Hardware-specific subsystems live in separate modules.  This file describes
 * the boot policy: initialize the chip, choose recovery or normal boot, select
 * an A/B partition table, build stbc-main's ABI block and start it.
 */

#include <stdint.h>
#include "boot_abi.h"
#include "flash.h"
#include "nt68503.h"
#include "recovery.h"
#include "uart.h"

#define DUALFW_SIGNATURE 0x7FF0u

static uint8_t code_read(uint16_t address)
{
    return CREG(address);
}

static void clear_shared_memory(void)
{
    uint16_t offset;

    for (offset = 0u; offset < SHARE_CLEAR_SIZE; ++offset) {
        xwrite(SHARE_BASE + offset, 0u);
    }
}

static void copy_code_to_xdata(uint16_t source, uint16_t destination, uint8_t count)
{
    while (count-- != 0u) {
        xwrite(destination++, code_read(source++));
    }
}

static uint8_t code_equal(uint16_t source, const char __code *text, uint8_t count)
{
    while (count-- != 0u) {
        if (code_read(source++) != (uint8_t)*text++) {
            return 0u;
        }
    }
    return 1u;
}

static void apply_dualfw_register_patch(void)
{
    uint8_t high = code_read(DUALFW_SIGNATURE + 6u);
    uint16_t address;
    uint8_t value;

    address = ((uint16_t)high << 8) | code_read(DUALFW_SIGNATURE + 7u);
    value = xread(address) & code_read(DUALFW_SIGNATURE + 8u);
    xwrite(address, value);

    address = ((uint16_t)high << 8) | code_read(DUALFW_SIGNATURE + 9u);
    value = xread(address) | code_read(DUALFW_SIGNATURE + 10u);
    xwrite(address, value);

    address = ((uint16_t)high << 8) | code_read(DUALFW_SIGNATURE + 11u);
    if (code_read(DUALFW_SIGNATURE + 13u) != 0u) {
        value = xread(address) & code_read(DUALFW_SIGNATURE + 12u);
    } else {
        value = xread(address) | code_read(DUALFW_SIGNATURE + 12u);
    }
    xwrite(address, value);
    uart_puts("libre: alternate-slot register patch applied\r\n");
}

/* Constant-only writers: explicit byte order, no native multi-byte XDATA store.
 * The value argument is evaluated for each byte; use ABI constants only.
 */
#define SHARE_WRITE_BE16(field, value) \
    do { \
        xwrite(SHARE_FIELD(field.hi), (value) >> 8); \
        xwrite(SHARE_FIELD(field.lo), (value)); \
    } while (0)
#define SHARE_WRITE_BE32(field, value) \
    do { \
        xwrite(SHARE_FIELD(field.byte3), (value) >> 24); \
        xwrite(SHARE_FIELD(field.byte2), (value) >> 16); \
        xwrite(SHARE_FIELD(field.byte1), (value) >> 8); \
        xwrite(SHARE_FIELD(field.byte0), (value)); \
    } while (0)

/* table is a 16-bit CODE address of partition_table_t, not a RAM struct. */
static void build_shared_structure(uint16_t table)
{
    uint16_t record;

    SHARE_WRITE_BE16(version, SHARE_VERSION);

    copy_code_to_xdata(PARTITION_FIELD(table, stbc_aux),
                       SHARE_FIELD(stbc_aux.partition), sizeof(partition_record_t));

    record = PARTITION_FIELD(table, leon2_main_runtime);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_main.runtime),
                       sizeof(partition_record_t));

    /* id=0E: location, inserted AHB base, original table size. */
    record = PARTITION_FIELD(table, leon2_main_data);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_main.data.location),
                       sizeof(partition_location_t));
    SHARE_WRITE_BE32(leon2_main.data.ahb_base, SHARE_MAIN_DATA_AHB_BASE);
    copy_code_to_xdata(record + offsetof(partition_record_t, size),
                       SHARE_FIELD(leon2_main.data.size), sizeof(boot_be32_t));

    /* id=10 location; following memory-configuration words stay zero. */
    record = PARTITION_FIELD(table, leon2_main_code);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_main.code.location),
                       sizeof(partition_location_t));

    record = PARTITION_FIELD(table, leon2_sub_code);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_sub.code), sizeof(partition_record_t));

    /* id=0A has the same extended format as id=0E, but a different AHB base. */
    record = PARTITION_FIELD(table, leon2_sub_data);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_sub.data.location),
                       sizeof(partition_location_t));
    SHARE_WRITE_BE32(leon2_sub.data.ahb_base, SHARE_SUB_DATA_AHB_BASE);
    copy_code_to_xdata(record + offsetof(partition_record_t, size),
                       SHARE_FIELD(leon2_sub.data.size), sizeof(boot_be32_t));

    /* id=0b is record 8; record 7 (id=03) has its own group below. */
    record = PARTITION_FIELD(table, leon2_sub_hdr);
    copy_code_to_xdata(record, SHARE_FIELD(leon2_sub.hdr), sizeof(partition_record_t));
    SHARE_WRITE_BE16(leon2_sub.memory.reg204_lo, SHARE_SUB_MEMORY_204_LO);

    record = PARTITION_FIELD(table, tensilica);
    copy_code_to_xdata(record, SHARE_FIELD(tensilica.partition),
                       sizeof(partition_record_t));

    xwrite(SHARE_FIELD(flash.jedec_table_index), FLASH_INDEX_GD25Q256);
    xwrite(SHARE_FIELD(flash.erase_opcode), FLASH_ERASE_4K);
    xwrite(SHARE_FIELD(flash.size_class), FLASH_SIZE_CLASS);
    xwrite(SHARE_FIELD(flash.size_class_hi), 0u);

    /* Reserved descriptor groups 6..9 mirror table records 9..12. */
    for (record = PARTITION_RESERVED_FIRST; record <= PARTITION_RESERVED_LAST; ++record) {
        uint16_t destination = SHARE_FIELD(reserved) +
            (record - PARTITION_RESERVED_FIRST) * sizeof(shared_plain_descriptor_t);
        copy_code_to_xdata(table + record * sizeof(partition_record_t),
                           destination, sizeof(partition_record_t));
    }
}

static uint16_t select_partition_table(uint8_t direction)
{
    /* Override this boot only; leave the persistent slot marker untouched. */
    if (direction == JOYSTICK_UP) {
        return SLOT1_TABLE;
    }
    if (direction == JOYSTICK_DOWN) {
        return SLOT0_TABLE;
    }
    return code_read(SLOT_MARKER) == SLOT_MARKER_ALTERNATE ? SLOT1_TABLE : SLOT0_TABLE;
}

static void prepare_stbc_main(uint16_t table)
{
    uint8_t bank = code_read(PARTITION_FIELD(table, stbc_main.location.bank));

    /* F1D source is 24-bit, little-endian by register address; EAR is separate. */
    xwrite(REG_BOOT_SRC_L,
           code_read(PARTITION_FIELD(table, stbc_main.location.offset.lo)));
    xwrite(REG_BOOT_SRC_M,
           code_read(PARTITION_FIELD(table, stbc_main.location.offset.hi)));
    xwrite(REG_BOOT_SRC_H,
           code_read(PARTITION_FIELD(table, stbc_main.location.id)));

    if (table == SLOT1_TABLE &&
        code_equal(DUALFW_SIGNATURE, "DUALFW", 6u)) {
        apply_dualfw_register_patch();
        flash_configure_bus();
    }

    if (bank != 0u) {
        flash_set_bank(bank);
    }

    xwrite(REG_BOOT_DST_L, 0u);
    xwrite(REG_BOOT_DST_H, 0u);
    xwrite(REG_BOOT_SIZE_L, code_read(PARTITION_FIELD(table, stbc_main.size.byte0)));
    xwrite(REG_BOOT_SIZE_M, code_read(PARTITION_FIELD(table, stbc_main.size.byte1)));
    xwrite(REG_BOOT_SIZE_H, code_read(PARTITION_FIELD(table, stbc_main.size.byte2)));

    build_shared_structure(table);
}

static void initialize_primary_core(uint8_t variant)
{
    uint8_t control;

    /* Vendor IDATA lookup tables reduce to these results for two variants. */
    xwrite(REG_CLOCK_INDEX, variant == 0x20u ? 4u : 6u);
    xwrite(REG_FLASH_CFG, variant == 0x20u ? FLASH_CFG_VARIANT_20 : FLASH_CFG_VARIANT_OTHER);
    xwrite(REG_UNKNOWN_F00A, F00A_BOOT_INIT_VALUE);
    xwrite(REG_WATCHDOG_F0E0, WATCHDOG_DISABLE);

    uart_init(variant);

    control = xread(REG_STBC_CTRL);
    xwrite(REG_STBC_CTRL, control | 2u);
    control = xread(REG_STBC_CTRL);
    xwrite(REG_STBC_CTRL, control & 0xFEu);
}

static void wait_forever(void)
{
    for (;;) {
        xwrite(REG_UNKNOWN_F00A, F00A_STOCK_POLL_VALUE);
    }
}

void main(void)
{
    uint8_t variant;
    uint8_t direction;
    uint16_t table;

    EA = 0;
    clear_shared_memory();

    variant = xread(REG_CHIP_VARIANT);
    initialize_primary_core(variant);
    joystick_init();

    uart_puts("\r\nbootloader-libre: start\r\n");
    direction = joystick_report();
    if (direction == JOYSTICK_RIGHT) {
        enter_recovery();
    }

    flash_controller_init();
    if (!flash_is_supported()) {
        uart_puts("libre: unsupported SPI NOR\r\n");
        wait_forever();
    }

    /* Reset must start from the lower half of a 32 MiB GD25Q256E. */
    if (flash_get_bank() != 0u) {
        flash_set_bank(0u);
        uart_puts("libre: reset flash bank; power cycle required\r\n");
        wait_forever();
    }

    flash_configure_bus();
    table = select_partition_table(direction);
    prepare_stbc_main(table);

    uart_puts("libre: starting stbc-main from table ");
    uart_hex16(table);
    uart_puts("\r\n");
    uart_drain();

    xwrite(REG_UNKNOWN_F00A, F00A_STOCK_POLL_VALUE);
    xwrite(REG_BOOT_CTRL, 0x87u);
    wait_forever();
}
