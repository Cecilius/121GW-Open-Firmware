@ =============================================================================
@ dch.s - SET: SETUP page CH, DIODE contact chirp (production image only, IMP-51)
@
@ SET module.  IMP-51 changes the DIODE chirp from v2.05's jump rule (a double
@ beep on every >1000-count change against the last chirped reference, at most once
@ per second) to one double beep per confirmed contact.  The page CH (item 42,
@ offered in DIODE only, after dSP) selects the behaviour:
@     code  text     behaviour
@     0     "CH oF"  off: the original v2.05 jump chirp (default)
@     1     "CH on"  on:  one double beep per contact (IMP-51)
@ Long SETUP starts the edit (the value blinks), REL or PEAK switches, long SETUP
@ again saves, SETUP short ends the edit without a save, the edit times out after
@ about 2 minutes (fn_0800D190 then re-reads the EEPROM).
@ Storage: EEPROM 0x02C (EEPROM_MAP.md 4.1); a value above 1, 0xFF included, reads
@ as 0 (off / original behaviour).
@
@ Context: main only.
@ =============================================================================

    .syntax unified
    .cpu cortex-m3
    .thumb
    .include "macros.inc"
    .include "hw.inc"
    .include "ram_v205.inc"
    .include "config.inc"

    .equ SET_DCH_EEPROM,      0x02C         @ EEPROM offset (EEPROM_MAP.md 4.1)
    .equ SET_DCH_CODE_MAX,    1
    .equ set_dch_redraw,      v_20008062    @ sub display redraw request
    .equ set_dch_commit_req,  v_2000805B    @ LCD commit request

    .section .bss_port.set, "aw", %nobits
@ set_dch: DIODE contact chirp, 0 = off / original jump chirp (default), 1 = on / contact chirp (owner SET; read by MRES)
    .global set_dch
set_dch:        .space 1

    .section .rodata.set.dch, "a", %progbits
set_dch_texts:
    .ascii "CH oF"
    .ascii "CH on"
    .size set_dch_texts, . - set_dch_texts

    .section .text.set.dch, "ax", %progbits

@ -----------------------------------------------------------------------------
@ set_dch_load - load the DIODE chirp setting from the EEPROM
@ In/Out   : - / -
@ Clobbers : r0-r3, r12, flags (AAPCS)
@ Context  : main only (set_state_reset at boot and after a STOP wake; fn_0800D190 when an edit times out)
@ -----------------------------------------------------------------------------
FUNC set_dch_load
    push {r4, lr}
    movs r0, #SET_DCH_EEPROM
    bl eeprom_read_u8
    cmp r0, #SET_DCH_CODE_MAX
    bls 1f
    movs r0, #0                             @ off / original behaviour
1:  ldr r1, =set_dch
    strb r0, [r1]
    pop {r4, pc}
ENDFUNC set_dch_load

@ -----------------------------------------------------------------------------
@ set_dch_edit - edit action of the page CH (setup item 42)
@ In       : r0 = action: 1 up, 2 down, 100 save
@ Clobbers : r0-r3, r12, flags (AAPCS)
@ Context  : main only (fn_080165F4)
@ -----------------------------------------------------------------------------
FUNC set_dch_edit
    push {r4, lr}
    uxtb r4, r0
    ldr r1, =set_dch
    ldrb r0, [r1]
    cmp r4, #100
    beq .Lde_save
    eor r0, r0, #1                          @ up or down: the other value
    strb r0, [r1]
    b .Lde_redraw
.Lde_save:
    mov r1, r0
    movs r0, #SET_DCH_EEPROM
    movs r2, #1
    bl set_nvm_store
.Lde_redraw:
    bl mres_diode_chirp_reset               @ apply the new behaviour at once (clears contact state and jump ref)
    movs r0, #1
    ldr r1, =set_dch_redraw
    strb r0, [r1]
    pop {r4, pc}
ENDFUNC set_dch_edit

@ -----------------------------------------------------------------------------
@ set_dch_draw - draw the page CH
@ Clobbers : r0-r3, r12, flags (AAPCS)
@ Context  : main only (fn_0801797C)
@ -----------------------------------------------------------------------------
FUNC set_dch_draw
    push {r4, lr}
    ldr r0, =lcd_shadow
    ldr r1, [r0, #0x10]
    bic r1, r1, #0x20000000                 @ sub minus off
    str r1, [r0, #0x10]
    movs r0, #0
    bl fn_08017FB4                          @ sub decimal points off
    ldr r0, =set_dch
    ldrb r0, [r0]
    and r0, r0, #1
    add r0, r0, r0, lsl #2                  @ * 5
    ldr r1, =set_dch_texts
    add r1, r1, r0
    movs r0, #1                             @ sub display
    bl lcd_draw_5char
    movs r0, #1
    ldr r1, =set_dch_commit_req
    strb r0, [r1]
    pop {r4, pc}
ENDFUNC set_dch_draw

    .ltorg
