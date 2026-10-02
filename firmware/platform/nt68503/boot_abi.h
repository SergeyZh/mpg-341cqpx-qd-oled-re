/* SPDX-License-Identifier: MIT */
#ifndef BOOT_ABI_H
#define BOOT_ABI_H

#include <stddef.h>
#include <stdint.h>

/* Novatek-family boot ABI, MSI NT68503 variant; not hardware registers.
 * ASUS/Samsung share the core layout, but locations and reserved tails vary.
 * See docs/stbc-main-spec.md#boot-abi-origin, docs/bootloader.md sections 5/6,
 * and docs/firmware-map.md (partition table).
 * All members are bytes: these types describe serialized layouts, not native
 * integers. No struct objects or generic pointers are needed on the 8051.
 */
typedef struct {
    uint8_t hi;
    uint8_t lo;
} boot_be16_t;

typedef struct {
    uint8_t byte3; /* bits 31..24, first byte in memory */
    uint8_t byte2; /* bits 23..16 */
    uint8_t byte1; /* bits 15..8 */
    uint8_t byte0; /* bits 7..0 */
} boot_be32_t;

typedef struct {
    uint8_t bank;       /* SPI EAR: selects the 16-MiB bank */
    uint8_t id;         /* also bits 23..16 of the flash address */
    boot_be16_t offset; /* bits 15..0 of the flash address */
} partition_location_t;

typedef struct {
    partition_location_t location;
    boot_be32_t size; /* byte3 is zero in known tables; F1D uses low 24 bits */
} partition_record_t;

#define PARTITION_RESERVED_COUNT 4u

/* MSI physical record order, NOT an array indexed by partition ID.
 * IDs below are MSI flash address bytes, not universal Novatek role IDs.
 */
typedef struct {
    partition_record_t stbc_main;           /* record 0, id=01 */
    partition_record_t stbc_aux;            /* record 1, id=02 */
    partition_record_t leon2_main_runtime;  /* record 2, id=0D */
    partition_record_t leon2_main_data;     /* record 3, id=0E */
    partition_record_t leon2_main_code;     /* record 4, id=10 */
    partition_record_t leon2_sub_code;      /* record 5, id=05 */
    partition_record_t leon2_sub_data;      /* record 6, id=0A */
    partition_record_t tensilica;           /* record 7, id=03 */
    partition_record_t leon2_sub_hdr;       /* record 8, id=0B */
    partition_record_t reserved[PARTITION_RESERVED_COUNT]; /* records 9..12 */
} partition_table_t;

#define SLOT0_TABLE            0x6000u /* CODE addresses, in the initial bank */
#define SLOT1_TABLE            0x7000u
#define SLOT_MARKER            0x7FFFu
#define SLOT_MARKER_ALTERNATE  0xAAu
#define PARTITION_FIELD(table, field) \
    ((table) + (uint16_t)offsetof(partition_table_t, field))
#define PARTITION_RESERVED_FIRST \
    (offsetof(partition_table_t, reserved) / sizeof(partition_record_t))
#define PARTITION_RESERVED_LAST \
    (PARTITION_RESERVED_FIRST + PARTITION_RESERVED_COUNT - 1u)

/* Plain descriptors occupy 12 bytes but carry an 8-byte table record.
 * Libre leaves the tail zero after clear_shared_memory(); stock code copied
 * uninitialized scratch bytes there. Extended descriptors insert an AHB base.
 */
typedef struct {
    partition_record_t partition;
    uint8_t reserved[4];
} shared_plain_descriptor_t;

typedef struct {
    partition_location_t location;
    boot_be32_t ahb_base;
    boot_be32_t size;
} shared_ahb_descriptor_t;

typedef struct {
    /* Serialized values written to Leon2 core registers +0x200/+0x204.
     * The lower half of reg204 is separate to preserve the bootloader's
     * original two-byte producer. Exact register bit semantics remain unknown.
     */
    boot_be32_t reg200;
    boot_be16_t reg204_hi;
    boot_be16_t reg204_lo;
} shared_memory_config_t;

typedef struct {
    partition_location_t location;
    shared_memory_config_t memory;
} shared_main_code_t;

typedef struct {
    partition_record_t runtime;        /* id=0D: AHB base is implicit */
    shared_ahb_descriptor_t data;      /* id=0E: explicit AHB base */
    shared_main_code_t code;           /* id=10 location, then memory config */
    uint8_t reserved[4];
} shared_leon2_main_t;

typedef struct {
    partition_record_t code;           /* id=05 */
    shared_ahb_descriptor_t data;       /* id=0A */
    partition_record_t hdr;            /* id=0B */
    shared_memory_config_t memory;     /* 304E..3055: 00000000, 000007FF */
    uint8_t reserved[4];
} shared_leon2_sub_t;

typedef struct {
    uint8_t jedec_table_index;
    uint8_t erase_opcode;
    uint8_t size_class; /* low byte of the stock swapped pair 05 00 */
    uint8_t size_class_hi;
} shared_flash_info_t;

typedef struct {
    boot_be16_t version;                       /* +00, kind 0: 00 01 */
    shared_plain_descriptor_t stbc_aux;        /* +02, kind 1 */
    shared_leon2_main_t leon2_main;             /* +0E, kind 2 */
    shared_leon2_sub_t leon2_sub;               /* +32, kind 3 */
    shared_plain_descriptor_t tensilica;       /* +5A, kind 4 */
    shared_flash_info_t flash;                 /* +66, kind 5 */
    shared_plain_descriptor_t reserved[PARTITION_RESERVED_COUNT]; /* +6A, kinds 6..9 */
} shared_structure_t;

#define SHARE_BASE                  0x3000u /* XDATA, not CODE */
#define SHARE_CLEAR_SIZE            0x1000u /* whole startup window, not sizeof ABI */
#define SHARE_VERSION               0x0001u
#define SHARE_MAIN_DATA_AHB_BASE     0x9F060000UL
#define SHARE_SUB_DATA_AHB_BASE      0x9F196000UL
#define SHARE_SUB_MEMORY_204_LO     0x07FFu
#define SHARE_FIELD(field) \
    (SHARE_BASE + (uint16_t)offsetof(shared_structure_t, field))

/* Enforce the byte-only ABI with both SDCC and the host compiler. */
#define BOOT_ABI_ASSERT(name, expression) \
    typedef char boot_abi_assert_##name[(expression) ? 1 : -1]
BOOT_ABI_ASSERT(record_size, sizeof(partition_record_t) == 8u);
BOOT_ABI_ASSERT(table_size, sizeof(partition_table_t) == 104u);
BOOT_ABI_ASSERT(plain_size, sizeof(shared_plain_descriptor_t) == 12u);
BOOT_ABI_ASSERT(ahb_size, sizeof(shared_ahb_descriptor_t) == 12u);
BOOT_ABI_ASSERT(memory_size, sizeof(shared_memory_config_t) == 8u);
BOOT_ABI_ASSERT(main_code_size, sizeof(shared_main_code_t) == 12u);
BOOT_ABI_ASSERT(main_memory_offset, offsetof(shared_structure_t, leon2_main.code.memory) == 0x26u);
BOOT_ABI_ASSERT(sub_memory_offset, offsetof(shared_structure_t, leon2_sub.memory) == 0x4Eu);
BOOT_ABI_ASSERT(sub_memory_low_offset, offsetof(shared_structure_t, leon2_sub.memory.reg204_lo) == 0x54u);
BOOT_ABI_ASSERT(main_offset, offsetof(shared_structure_t, leon2_main) == 0x0Eu);
BOOT_ABI_ASSERT(sub_offset, offsetof(shared_structure_t, leon2_sub) == 0x32u);
BOOT_ABI_ASSERT(tensilica_offset, offsetof(shared_structure_t, tensilica) == 0x5Au);
BOOT_ABI_ASSERT(flash_offset, offsetof(shared_structure_t, flash) == 0x66u);
BOOT_ABI_ASSERT(reserved_offset, offsetof(shared_structure_t, reserved) == 0x6Au);
BOOT_ABI_ASSERT(shared_size, sizeof(shared_structure_t) == 0x9Au);
#undef BOOT_ABI_ASSERT

#endif
