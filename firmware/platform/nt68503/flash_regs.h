/* SPDX-License-Identifier: MIT
 * NT68503 SPI controller definitions shared by bootloader and STBC.
 */
#ifndef NT68503_FLASH_REGS_H
#define NT68503_FLASH_REGS_H

#define REG_FLASH_MODE   0xF050u
#define REG_JEDEC_MFG    0xF064u
#define REG_JEDEC_TYPE   0xF065u
#define REG_JEDEC_SIZE   0xF066u
#define REG_FLASH_START  0xF0E5u
#define REG_FLASH_CFG    0xF0E6u
#define REG_FLASH_OPCODE 0xF0EAu
#define REG_FLASH_LEN_H  0xF0EBu
#define REG_FLASH_LEN_M  0xF0ECu
#define REG_FLASH_LEN_L  0xF0EDu
#define REG_FLASH_CMD    0xF0EEu
#define REG_FLASH_RESULT 0xF0EFu
#define REG_FLASH_ADDR_H 0xF0F0u
#define REG_FLASH_ADDR_M 0xF0F1u
#define REG_FLASH_ADDR_L 0xF0F2u
#define REG_FLASH_FORMAT 0xF0F4u

/* NT68503 engine control, not SPI NOR opcodes. F0E5 start bits 0/1 self-clear.
 * The COMMAND path also receives JEDEC ID; it is not a write-only SPI command.
 */
#define FLASH_ENGINE_COMMAND       0x01u
#define FLASH_ENGINE_READ          0x02u
#define FLASH_ENGINE_FIFO_RESET    0x40u

/* F0E6 presets: keep the variant-selected bits 2/3. The other fields have
 * not been fully decoded; names describe the stock transaction recipes.
 */
#define FLASH_CFG_PRESERVE_MASK     0x0Cu
#define FLASH_CFG_COMMAND          0x41u
#define FLASH_CFG_STREAM           0x01u
#define FLASH_CFG_VARIANT_20        0x00u
#define FLASH_CFG_VARIANT_OTHER     0x04u

/* F0F4 format presets, NOT commands sent to the flash (notably 0x0B). */
#define FLASH_FORMAT_COMMAND       0x03u
#define FLASH_FORMAT_REGISTER_READ 0x07u
#define FLASH_FORMAT_STREAM_READ   0x0Bu
#define FLASH_FORMAT_JEDEC_ID       0x33u
#define FLASH_FORMAT_REGISTER_WRITE_ONE 0x53u /* opcode + one payload byte */
#define FLASH_FORMAT_STATUS_WRITE  0x73u /* opcode + two payload bytes */

/* F050 bus-mode latch. */
#define FLASH_MODE_QUAD            0x04u
#define FLASH_MODE_DUAL            0x20u

#define REG_FLASH_PIN_A  0xF11Cu
#define REG_FLASH_PIN_B  0xF11Du
#define REG_FLASH_PIN_C  0xF134u
#define REG_FLASH_LATCH  0xF152u

#define REG_FIFO         0xF1C0u
#define REG_FIFO_F1C1    0xF1C1u /* page-program recipe control; fields unresolved */
#define REG_FIFO_F1C2    0xF1C2u /* page-program recipe read/write latch */
#define REG_FIFO_TX      0xF1C3u
#define REG_FIFO_DATA    0xF1C8u
#define REG_FLASH_GATE   0xF1DFu

/* F1C0 FIFO/sequencer presets recovered from the stock bootloader.
 * 0x82 prepares host FIFO access: TX staging or RX draining, per transaction.
 * The dummy read after selecting RX is a controller read, not an SPI opcode.
 */
#define FLASH_FIFO_PAGE_PREPARE    0x02u
#define FLASH_FIFO_PAGE_EXECUTE    0x04u
#define FLASH_FIFO_IDLE            0x00u
#define FLASH_FIFO_RESET           0x80u
#define FLASH_FIFO_ARM_STREAM      0x81u
#define FLASH_FIFO_HOST_ACCESS     0x82u
#define FLASH_FIFO_EXECUTE         0x84u

/* F1C8 data FIFO presets; low-bit hardware semantics remain only partly known. */
#define FLASH_DATA_FIFO_RESET      0x80u
#define FLASH_DATA_FIFO_ARM        0x81u
#define FLASH_DATA_FIFO_READ       0x82u

#define FLASH_GATE_ENABLE          0x80u /* F1DF aperture gate */
#define FLASH_LATCH_BOOT_PRESET    0x40u /* F152 stock init; full meaning unknown */

#endif
