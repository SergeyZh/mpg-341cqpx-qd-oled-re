/* SPDX-License-Identifier: MIT
 *
 * Minimal GD25Q256E setup needed by the primary boot path.
 */

#include <stdint.h>
#include "flash.h"
#include "nt68503.h"
#include "timing.h"
#include "uart.h"

static uint8_t code_read(uint16_t address)
{
    return *((const __code uint8_t *)address);
}

static void fifo_reset(void)
{
    xwrite(REG_FLASH_START, xread(REG_FLASH_START) | FLASH_ENGINE_FIFO_RESET);
    xwrite(REG_FLASH_START, xread(REG_FLASH_START) & (uint8_t)~FLASH_ENGINE_FIFO_RESET);
}

static void wait_engine(uint8_t mask)
{
    while ((xread(REG_FLASH_START) & mask) != 0u) {
        delay_flash_poll();
    }
}

static void spi_command(uint8_t opcode)
{
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_COMMAND);
    xwrite(REG_FLASH_CMD, opcode);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 0u);
    xwrite(REG_FLASH_LEN_L, 0u);
    xwrite(REG_FLASH_START, FLASH_ENGINE_COMMAND);
    wait_engine(FLASH_ENGINE_COMMAND);
}

static uint8_t spi_read_register(uint8_t opcode)
{
    xwrite(REG_UNKNOWN_F00A, F00A_STOCK_POLL_VALUE);
    xwrite(REG_FIFO, FLASH_FIFO_IDLE);
    xwrite(REG_FLASH_OPCODE, opcode);
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_COMMAND);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 0u);
    xwrite(REG_FLASH_LEN_L, 0u);
    xwrite(REG_FLASH_FORMAT, FLASH_FORMAT_REGISTER_READ);
    xwrite(REG_FLASH_START, FLASH_ENGINE_READ);
    wait_engine(FLASH_ENGINE_READ);
    return xread(REG_FLASH_RESULT);
}

static void spi_write_byte(uint8_t opcode, uint8_t value)
{
    xwrite(REG_FIFO, FLASH_FIFO_RESET);
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_COMMAND);
    xwrite(REG_FLASH_FORMAT, FLASH_FORMAT_COMMAND);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 0u);
    xwrite(REG_FLASH_LEN_L, 1u);
    xwrite(REG_FLASH_CMD, opcode);
    xwrite(REG_FIFO, FLASH_FIFO_HOST_ACCESS);
    xwrite(REG_FIFO_TX, value);
    xwrite(REG_FIFO, FLASH_FIFO_EXECUTE);
    xwrite(REG_FLASH_START, FLASH_ENGINE_COMMAND);
    wait_engine(FLASH_ENGINE_COMMAND);
}

static void spi_wait_wel(void)
{
    while ((spi_read_register(SPI_NOR_CMD_RDSR1) & SPI_NOR_SR1_WEL) == 0u) {
    }
}

static void spi_wait_ready(void)
{
    while ((spi_read_register(SPI_NOR_CMD_RDSR1) & SPI_NOR_SR1_WIP) != 0u) {
    }
}

static void spi_write_register(uint8_t opcode, uint8_t value)
{
    spi_command(SPI_NOR_CMD_WREN);
    spi_wait_wel();
    spi_write_byte(opcode, value);
    spi_wait_ready();
}

static void spi_write_status(uint8_t status1, uint8_t status2)
{
    /* Stock WRSR1 path sends SR1 then SR2. GD25Q256E Rev1.1 section 7.4
     * documents 01/31/11 as separate one-byte writes; do not silently change
     * this inherited two-byte transaction as part of naming constants.
     */
    spi_command(SPI_NOR_CMD_WREN);
    spi_wait_wel();
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_COMMAND);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 0u);
    xwrite(REG_FLASH_LEN_L, 2u);
    xwrite(REG_FLASH_FORMAT, FLASH_FORMAT_STATUS_WRITE);
    xwrite(REG_FLASH_CMD, SPI_NOR_CMD_WRSR1);
    xwrite(REG_FIFO, FLASH_FIFO_HOST_ACCESS);
    xwrite(REG_FIFO_TX, status1);
    xwrite(REG_FIFO_TX, status2);
    xwrite(REG_FIFO, FLASH_FIFO_EXECUTE);
    xwrite(REG_FIFO_DATA, FLASH_DATA_FIFO_ARM);
    xwrite(REG_FLASH_START, FLASH_ENGINE_COMMAND);
    wait_engine(FLASH_ENGINE_COMMAND);
    xwrite(REG_FIFO, FLASH_FIFO_RESET);
    xwrite(REG_FIFO_DATA, FLASH_DATA_FIFO_RESET);
    spi_wait_ready();
    while ((spi_read_register(SPI_NOR_CMD_RDSR1) & SPI_NOR_SR1_WEL) != 0u) {
    }
}

static void flash_read_start(uint8_t opcode)
{
    xwrite(REG_FLASH_OPCODE, opcode);
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_STREAM);
    xwrite(REG_FLASH_FORMAT, FLASH_FORMAT_STREAM_READ);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 2u);
    xwrite(REG_FLASH_LEN_L, 0u);
    xwrite(REG_FLASH_ADDR_H, 0u);
    xwrite(REG_FLASH_ADDR_M, 0u);
    xwrite(REG_FLASH_ADDR_L, 0u);
    xwrite(REG_FIFO, FLASH_FIFO_ARM_STREAM);
    xwrite(REG_FLASH_START, FLASH_ENGINE_READ);
    wait_engine(FLASH_ENGINE_READ);
    xwrite(REG_FIFO, FLASH_FIFO_HOST_ACCESS);
    (void)xread(REG_FIFO); /* controller FIFO dummy read, not an SPI command */
}

static uint8_t flash_mode_selftest(uint8_t opcode)
{
    uint8_t i;

    flash_read_start(opcode);
    for (i = 0u; i < 10u; ++i) {
        if (xread(REG_FIFO) != code_read(i)) {
            return 0u;
        }
    }
    return 1u;
}

void flash_controller_init(void)
{
    xwrite(REG_FLASH_GATE, FLASH_GATE_ENABLE);
    fifo_reset();
    xwrite(REG_FLASH_LATCH, FLASH_LATCH_BOOT_PRESET);
}

uint8_t flash_is_supported(void)
{
    uint8_t manufacturer;
    uint8_t memory_type;
    uint8_t capacity;

    /* One command byte followed by three response bytes. */
    xwrite(REG_FLASH_CFG, (xread(REG_FLASH_CFG) & FLASH_CFG_PRESERVE_MASK) | FLASH_CFG_COMMAND);
    xwrite(REG_FLASH_LEN_H, 0u);
    xwrite(REG_FLASH_LEN_M, 0u);
    xwrite(REG_FLASH_LEN_L, 3u);
    xwrite(REG_FLASH_FORMAT, FLASH_FORMAT_JEDEC_ID);
    xwrite(REG_FLASH_CMD, SPI_NOR_CMD_RDID);
    xwrite(REG_FIFO, FLASH_FIFO_HOST_ACCESS);
    xwrite(REG_FIFO, FLASH_FIFO_EXECUTE);
    xwrite(REG_FIFO_DATA, FLASH_DATA_FIFO_ARM);
    xwrite(REG_FLASH_START, FLASH_ENGINE_COMMAND);
    wait_engine(FLASH_ENGINE_COMMAND);

    xwrite(REG_FIFO_DATA, FLASH_DATA_FIFO_READ);
    (void)xread(REG_FIFO_DATA);
    manufacturer = xread(REG_FIFO_DATA);
    memory_type = xread(REG_FIFO_DATA);
    capacity = xread(REG_FIFO_DATA);
    xwrite(REG_FIFO, FLASH_FIFO_RESET);
    xwrite(REG_FIFO_DATA, FLASH_DATA_FIFO_RESET);

    /* stbc-main can observe the same latched ID as the vendor boot path. */
    xwrite(REG_JEDEC_MFG, manufacturer);
    xwrite(REG_JEDEC_TYPE, memory_type);
    xwrite(REG_JEDEC_SIZE, capacity);

    return manufacturer == GD25Q256E_JEDEC_MANUFACTURER &&
           memory_type == GD25Q256E_JEDEC_MEMORY_TYPE &&
           capacity == GD25Q256E_JEDEC_CAPACITY;
}

uint8_t flash_get_bank(void)
{
    return spi_read_register(SPI_NOR_CMD_RDEAR);
}

void flash_set_bank(uint8_t bank)
{
    spi_write_register(SPI_NOR_CMD_WREAR, bank);
    uart_puts("libre: flash bank ");
    uart_hex8(bank);
    uart_puts("\r\n");
}

void flash_configure_bus(void)
{
    uint8_t status1;
    uint8_t status2 = spi_read_register(SPI_NOR_CMD_RDSR2);
    uint8_t mode;

    if ((status2 & SPI_NOR_SR2_QE) == 0u) {
        xwrite(REG_FLASH_PIN_C, xread(REG_FLASH_PIN_C) | 0xC0u);
        xwrite(REG_FLASH_PIN_A, xread(REG_FLASH_PIN_A) | 0x40u);
        xwrite(REG_FLASH_PIN_B, (xread(REG_FLASH_PIN_B) | 0x80u) & 0xBFu);
        status1 = spi_read_register(SPI_NOR_CMD_RDSR1);
        spi_write_status(status1, status2 | SPI_NOR_SR2_QE);
    }

    xwrite(REG_FLASH_PIN_C, xread(REG_FLASH_PIN_C) | 0xC0u);
    xwrite(REG_FLASH_PIN_B, (xread(REG_FLASH_PIN_B) | 0x80u) & 0xBFu);

    mode = xread(REG_FLASH_MODE);
    xwrite(REG_FLASH_MODE, (mode & (uint8_t)~FLASH_MODE_DUAL) | FLASH_MODE_QUAD);
    if (flash_mode_selftest(SPI_NOR_CMD_QUAD_OUTPUT_READ)) {
        uart_puts("libre: quad read verified\r\n");
        return;
    }

    mode = xread(REG_FLASH_MODE);
    xwrite(REG_FLASH_MODE, (mode & (uint8_t)~(FLASH_MODE_QUAD | FLASH_MODE_DUAL)) | FLASH_MODE_DUAL);
    if (flash_mode_selftest(SPI_NOR_CMD_DUAL_OUTPUT_READ)) {
        uart_puts("libre: dual read verified\r\n");
        return;
    }

    xwrite(REG_FLASH_MODE, xread(REG_FLASH_MODE) & (uint8_t)~FLASH_MODE_DUAL);
    uart_puts("libre: serial read fallback\r\n");
}
