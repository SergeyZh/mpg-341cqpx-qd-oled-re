; SPDX-License-Identifier: MIT
;
; Minimal reset path for the first NT68503 8051 core.  Interrupts are never
; enabled by this bootloader, so the vector area is deliberately left empty.

	.module crt0
	.globl _main

	.area HOME (CODE)
reset_vector:
	ljmp startup
	.ds 0x002D

startup:
	mov r0,#0x7F
	clr a

clear_idata:
	mov @r0,a
	djnz r0,clear_idata

	mov psw,a
	mov sp,#0x5A
	clr 0xAF               ; EA = 0
	lcall _main

halt:
	sjmp halt
