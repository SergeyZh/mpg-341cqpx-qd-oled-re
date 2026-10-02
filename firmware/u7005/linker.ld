/* Code excludes the mutable virtual disk, mode page, metadata and DataFlash. */
ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0, LENGTH = 64K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 20K }
PHDRS { code PT_LOAD FLAGS(5); ramcode PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
  .vectors : { KEEP(*(.vectors)) } > FLASH :code
  .image_info 0xC0 : { KEEP(*(.image_info)) } > FLASH :code
  .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH :code
  .ARM.exidx : { *(.ARM.exidx*) } > FLASH :code
  .ramfunc : {
    . = ALIGN(4); _data_start = .; *(.ramfunc*) . = ALIGN(4);
  } > RAM AT > FLASH :ramcode
  .data : {
    *(.data*) . = ALIGN(4); _data_end = .;
  } > RAM AT > FLASH :data
  _data_load = LOADADDR(.ramfunc);
  _code_end = LOADADDR(.data) + SIZEOF(.data);
  .bss (NOLOAD) : { . = ALIGN(4); _bss_start = .; *(.bss*) *(COMMON) . = ALIGN(4); _bss_end = .; } > RAM :data
  _stack_top = ORIGIN(RAM) + LENGTH(RAM);
  ASSERT(_bss_end <= _stack_top - 2048, "Need at least 2 KiB of stack")
  /DISCARD/ : { *(.comment*) *(.note*) }
}
