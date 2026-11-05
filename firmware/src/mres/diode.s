@ =============================================================================
@ diode.s - MRES / DIODE (hy3131_modes_misc.md 6.3)
@ Replaces the v2.05 functions fn_08007E84 0x08007E84 (mean path), fn_080159C8 0x080159C8 (RANGE 3 V <-> 15 V), and the code DIODE
@ of fn_08007E60 0x08007E60 (0x08007E64..0x08007E7C); the v2.05 function addresses 0x08007E60, 0x08007E84 and 0x080159C8 are kept
@ as labels.
@ DIODE: one range, 3 V (full scale 30000, dp 4) or 15 V (15000, dp 3; the HY3131 row is the same, the displayed count is divided by 10).
@ Short-circuit tone: a smoothed reading in -999..999 counts; the tone decision is made on the calibrated per-sample value,
@ which must be inside the window for two consecutive conversions (K = 2, port RAM mres_diode_k; IMP-04, ARS 8.2).
@
@ TMP-IMP-01: the chirp reports the contact, not the jump: one double beep per confirmed contact with a diode,
@ silence while the reading stays connected (settling and junction drift included), silence at overload (open leads or a
@ reverse-biased diode, |D| >= full scale) and on the way back to open; see the state machine in fn_08007E84.
@ OF-23: the RANGE key no longer writes the 3 V / 15 V choice to EEPROM 0x12 (it was never restored, Q6).
@ =============================================================================

    .syntax unified
    .cpu cortex-m3
    .thumb
    .include "macros.inc"
    .include "hw.inc"
    .include "ram_v205.inc"
    .include "config.inc"

    @ TMP-IMP-01: chirp state machine.  The mean branch runs about every 100 ms in DIODE (a mean of 16 samples at about
    @ 6 ms per sample, emulator measurement), so both counts are times of about 0.2 s.
    .equ DIODE_AWAY_REARM,   2            @ consecutive OPEN / short-window means that re-arm the chirp
    .equ DIODE_REGION_CHIRP, 2            @ consecutive DIODE-region means that confirm a contact (then one chirp)

    .section .text.mres.diode, "ax", %progbits

@ -----------------------------------------------------------------------------
@ fn_08007E84 - DIODE: mean branch (value, short-circuit chirp) and per-sample value
@ Replaces : 0x08007E84 FUN_08007E84 (v2.05)
@ In       : -
@ Out      : -
@ Clobbers : r0-r3, r12, flags
@ Context  : main
@ RAM      : reads  mres_diode_k, 0x20007D64, 0x20007D68, 0x20007FDF, 0x20008081, 0x2000808A, 0x200080B3, 0x20007D60 (full scale)
@            and the chirp state (mres_diode_chirp_st, mres_diode_in_cnt, mres_diode_away_cnt)
@            writes mres_diode_k, 0x20007D64, 0x20007D68, 0x2000805D and the chirp state
@ Spec     : analysis/hy3131_modes_misc.md 6.3 (DIODE); autorange_and_scheduler.md 8.2
@ Deviation: IMP-04, TMP-IMP-01
@ Mean branch: D = fn_08006418(mean), divided by 10 in 15 V (0x200080B3 = 1), smoothed (2, 2); 15 V on units with 0x20007FDF = 1 (PF8 strap):
@ D > 14000 gets +500 (not in calibration mode).  Short window -999..999: a re-arm dwell mean (TMP-IMP-01).  Elsewhere:
@ the contact state machine (TMP-IMP-01); 0x2000805D = 1.
@ TMP-IMP-01 chirp (per mean): |D| >= full scale (0x20007D60: 30000 / 15000 counts) is the OPEN region - the leads
@ open or a reverse-biased diode - and the short window is the SHORT region; both are silent and count toward the
@ re-arm (DIODE_AWAY_REARM consecutive means set the state ARMED).  Between the regions (DIODE region) the state
@ LATCHED (mres_diode_chirp_st = 1) is silent; while ARMED, DIODE_REGION_CHIRP consecutive means confirm the contact
@ and give one fn_0800EE6C double beep, then LATCHED.  Entering the mode resets the state (mres_diode_chirp_reset, MODE).
@ Per sample: fn_080064D6, divided by 10 in 15 V; IMP-04 tone on K=2 confirmed samples in the short window.
@ -----------------------------------------------------------------------------
FUNC fn_08007E84
    push {r7, lr}                      @ 0x08007E84
    @ ---- mean branch (0x20008081 = 1) ----
    ldr r0, =v_20008081                @ 0x08007E84 pool 0x080087E4 = 0x20008081
    ldrb r0, [r0, #0]                  @ 0x08007E88
    cmp r0, #0                         @ 0x08007E8A
    beq .L08007F6A                     @ 0x08007E8C

    @ ---- mean value: D = fn_08006418(raw mean), stored to v_20007D64 by the callee ----
    bl fn_08006418                     @ 0x08007E8E
    @ 15 V (0x200080B3 = 1): the displayed count is the reading divided by 10
    ldr r0, =v_200080B3                @ 0x08007E92 pool 0x080087CC = 0x200080B3
    ldrb r0, [r0, #0]                  @ 0x08007E96
    cmp r0, #0                         @ 0x08007E98
    beq .L08007EB4                     @ 0x08007E9A  (0 = 3 V, 1 = 15 V)
    ldr r0, =v_20007D64                @ 0x08007E9C pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007E9E
    movs r1, #10                       @ 0x08007EA0
    sdiv r0, r0, r1                    @ 0x08007EA2
    ldr r1, =v_20007D64                @ 0x08007EA6 pool 0x08007F94 = 0x20007D64
    str r0, [r1, #0]                   @ 0x08007EA8
.L08007EB4:                              @ reached from 0x08007EA0 bne
    @ display smoothing (threshold 2, depth 2)
    movs r2, #2                        @ 0x08007EB4
    movs r1, #2                        @ 0x08007EB6
    ldr r0, =v_20007D64                @ 0x08007EB8 pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007EBA
    bl fn_0800B754                     @ 0x08007EB2
    ldr r1, =v_20007D64                @ 0x08007EC0 pool 0x08007F94 = 0x20007D64
    str r0, [r1, #0]                   @ 0x08007EC4

    @ 15 V on a unit with the PF8 strap (0x20007FDF = 1), not in calibration mode: readings above 14000 get +500 (v2.05 0x08007EBA..0x08007EF4)
    ldr r0, =v_2000808A                @ 0x08007EBA pool 0x080087C0 = 0x2000808A
    ldrb r0, [r0, #0]                  @ 0x08007EBE
    ldr r1, =v_20007FDF                @ 0x08007EC0 pool 0x080087D0 = 0x20007FDF
    ldrb r1, [r1, #0]                  @ 0x08007EC4
    eors.w r1, r1, #1                  @ 0x08007EC6
    orrs r0, r1                        @ 0x08007ECA
    ldr r1, =v_200080B3                @ 0x08007ECC pool 0x080087CC = 0x200080B3
    ldrb r1, [r1, #0]                  @ 0x08007ED0
    eors.w r1, r1, #1                  @ 0x08007ED2
    orrs r0, r1                        @ 0x08007ED6
    uxtb r0, r0                        @ 0x08007ED8
    cmp r0, #0                         @ 0x08007EDA
    bne .L08007EF6                     @ 0x08007EDC
    ldr r0, =v_20007D64                @ 0x08007EDE pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007EE0
    movw r1, #14001                    @ 0x08007EE2
    cmp r0, r1                         @ 0x08007EE6
    blt .L08007EF6                     @ 0x08007EE8
    ldr r0, =v_20007D64                @ 0x08007EEA pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007EEC
    adds.w r0, r0, #500                @ 0x08007EEE
    ldr r1, =v_20007D64                @ 0x08007EF2 pool 0x08007F94 = 0x20007D64
    str r0, [r1, #0]                   @ 0x08007EF4
.L08007EF6:                              @ reached from 0x08007EDC bne, 0x08007EE8 blt
    @ short-circuit window -999 .. 999: a re-arm dwell mean (TMP-IMP-01)
    ldr r0, =v_20007D64                @ 0x08007EF6 pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007EF8
    cmp.w r0, #1000                    @ 0x08007EFA
    bge .L08007F20                     @ 0x08007EFE
    ldr r0, =v_20007D64                @ 0x08007F00 pool 0x08007F94 = 0x20007D64
    ldr r0, [r0, #0]                   @ 0x08007F02
    ldr r1, =0xFFFFFC19                @ 0x08007F04 pool 0x080087D4 = 0xFFFFFC19
    cmp r0, r1                         @ 0x08007F08
    blt .L08007F20                     @ 0x08007F0A
    bl mres_diode_chirp_away              @ TMP-IMP-01: a short-window mean counts toward the re-arm of the chirp
    b .L08007F64                       @ 0x08007F1E
.L08007F20:                              @ reached from 0x08007EFE bge, 0x08007F0A blt
    @ ---- TMP-IMP-01: outside the window (r0 = D): OPEN (|D| >= full scale: silent, re-arm dwell) against the DIODE
    @ region (one confirmed double beep per contact, then silent until the reading leaves to OPEN or SHORT) ----
    cmp r0, #0
    bge .Ldi29_abs
    rsbs r0, r0, #0                         @ r0 = |D|
.Ldi29_abs:
    ldr r1, =v_20007D60                     @ mode_full_scale (load_full_scale: 30000 on 3 V, 15000 on 15 V counts)
    ldr r1, [r1, #0]
    cmp r0, r1
    bge .Ldi29_open                         @ |D| >= full scale: overload (OL / -OL) = leads open or a reverse diode
    @ ---- DIODE region ----
    movs r0, #0
    ldr r1, =mres_diode_away_cnt
    strb r0, [r1, #0]                       @ the away dwell is broken
    ldr r1, =mres_diode_chirp_st
    ldrb r0, [r1, #0]
    cmp r0, #0
    bne .L08007F64                          @ LATCHED: silent while the contact continues (settling and drift)
    ldr r1, =mres_diode_in_cnt
    ldrb r0, [r1, #0]
    adds r0, r0, #1                         @ one more consecutive mean in the region
    strb r0, [r1, #0]
    cmp r0, #DIODE_REGION_CHIRP
    blt .L08007F64                          @ the contact is not confirmed yet
    movs r0, #0
    strb r0, [r1, #0]                       @ in_cnt = 0
    movs r0, #1
    ldr r1, =mres_diode_chirp_st
    strb r0, [r1, #0]                       @ LATCHED: this contact has chirped
    bl fn_0800EE6C                          @ the double beep (refusal pattern; OF-63: gated by the buzzer setting)
    b .L08007F64
.Ldi29_open:
    bl mres_diode_chirp_away                @ an OPEN mean counts toward the re-arm of the chirp
.L08007F64:                              @ reached from 0x08007F1E b, 0x08007F42 bge, 0x08007F4C bne;
                                         @ production also from the TMP-IMP-01 branches above
    @ 0x2000805D = 1: new value
    movs r0, #1                        @ 0x08007F64
    ldr r1, =v_2000805D                @ 0x08007F66 pool 0x08007F9C = 0x2000805D
    strb r0, [r1, #0]                  @ 0x08007F68
.L08007F6A:                              @ reached from 0x08007E8C bne
    @ ---- per-sample value: 0x20007D68 = divide_by_gain(sample - offset), divided by 10 in 15 V ----
    bl fn_080064D6                     @ 0x08007F6A
    ldr r0, =v_200080B3                @ 0x08007F6E pool 0x080087CC = 0x200080B3
    ldrb r0, [r0, #0]                  @ 0x08007F72
    cmp r0, #0                         @ 0x08007F74
    beq .L08007F8A                     @ 0x08007F76  (3 V: no /10; 15 V: divide by 10)
    ldr r0, =v_20007D68                @ 0x08007F78 pool 0x08008340 = 0x20007D68
    ldr r0, [r0, #0]                   @ 0x08007F7A
    movs r1, #10                       @ 0x08007F7C
    sdiv r0, r0, r1                    @ 0x08007F80
    ldr r1, =v_20007D68                @ 0x08007F84 pool 0x08008340 = 0x20007D68
    str r0, [r1, #0]                   @ 0x08007F88
.L08007F8A:                              @ reached from 0x08007F76 bne
    @ ---- IMP-04: tone decision on confirmed per-sample values.  v = 0x20007D68 (15 V: already divided by 10 above) ----
    ldr r0, =v_20007D68
    ldr r0, [r0]
    movw r1, #999
    cmp r0, r1
    bgt .Ldi_out
    ldr r1, =0xFFFFFC19                     @ -999
    cmp r0, r1
    blt .Ldi_out
    @ inside the short-circuit window: one more confirmed sample (K = 2)
    ldr r1, =mres_diode_k
    ldrb r0, [r1]
    adds r0, r0, #1
    cmp r0, #2
    blo .Ldi_kstore
    movs r0, #2                             @ saturate at K
.Ldi_kstore:
    strb r0, [r1]
    cmp r0, #2
    bne .Ldi_done                           @ not confirmed yet
    mov.w r0, #500
    bl fn_0800EEA8                          @ OF-63: gated by the buzzer setting (pe7_on_with_timeout)
    b .Ldi_done
.Ldi_out:
    movs r0, #0
    ldr r1, =mres_diode_k
    strb r0, [r1]                           @ outside the window: restart the confirmation
.Ldi_done:
    pop {r7, pc}                       @ 0x08007F8A
    .ltorg
ENDFUNC fn_08007E84

@ -----------------------------------------------------------------------------
@ mres_diode_chirp_away - TMP-IMP-01: one mean of the OPEN or SHORT region
@ In/Out   : - / -
@ Clobbers : r0-r1
@ Context  : main only (fn_08007E84)
@ RAM      : writes mres_diode_in_cnt, mres_diode_away_cnt, mres_diode_chirp_st
@ A contact confirmation is broken at once; the chirp re-arms only after DIODE_AWAY_REARM consecutive away means.
@ -----------------------------------------------------------------------------
LFUNC mres_diode_chirp_away
    movs r0, #0
    ldr r1, =mres_diode_in_cnt
    strb r0, [r1, #0]                       @ the contact confirmation is broken
    ldr r1, =mres_diode_away_cnt
    ldrb r0, [r1, #0]
    cmp r0, #0xFF
    bhs .Ldca_test                          @ saturated: stays away
    adds r0, r0, #1
    strb r0, [r1, #0]
.Ldca_test:
    cmp r0, #DIODE_AWAY_REARM
    blt .Ldca_done
    ldr r1, =mres_diode_chirp_st
    movs r0, #0
    strb r0, [r1, #0]                       @ ARMED: the next confirmed contact chirps
.Ldca_done:
    bx lr
ENDFUNC mres_diode_chirp_away

@ -----------------------------------------------------------------------------
@ mres_diode_chirp_reset - TMP-IMP-01: clear the chirp state machine
@ In/Out   : - / -
@ Clobbers : r0-r1
@ Context  : main only (meter_apply_mode_range on a mode change to DIODE)
@ RAM      : writes mres_diode_chirp_st = 0 (ARMED), mres_diode_in_cnt = 0, mres_diode_away_cnt = 0
@ -----------------------------------------------------------------------------
FUNC mres_diode_chirp_reset
    movs r0, #0
    ldr r1, =mres_diode_chirp_st
    strb r0, [r1, #0]
    ldr r1, =mres_diode_in_cnt
    strb r0, [r1, #0]
    ldr r1, =mres_diode_away_cnt
    strb r0, [r1, #0]
    bx lr
ENDFUNC mres_diode_chirp_reset
    .ltorg

FUNC fn_080159C8
    push {r7, lr}                      @ 0x080159C8
    ldr r0, =v_200080B3                @ 0x080159CA pool 0x08016224 = 0x200080B3
    ldrb r0, [r0, #0]                  @ 0x080159CE
    teq r0, #1                         @ 0x080159D0
    beq .L080159E0                     @ 0x080159D4
    movs r0, #1                        @ 0x080159D6
    ldr r1, =v_200080B3                @ 0x080159D8 pool 0x08016224 = 0x200080B3
    strb r0, [r1, #0]                  @ 0x080159DC
    b .L080159E8                       @ 0x080159DE
.L080159E0:                              @ reached from 0x080159D4 beq
    movs r0, #0                        @ 0x080159E0
    ldr r1, =v_200080B3                @ 0x080159E2 pool 0x08016224 = 0x200080B3
    strb r0, [r1, #0]                  @ 0x080159E6
.L080159E8:                              @ reached from 0x080159DE b
    @ OF-23: no EEPROM write of 0x200080B3 (v2.05 called FUN_08011384(0x200080B3) here)
    ldr r0, =meter_range               @ 0x080159F2 pool 0x080161E0 = 0x2000803D
    ldrb r1, [r0, #0]                  @ 0x080159F6
    ldr r0, =meter_mode                @ 0x080159F8 pool 0x08015E70 = 0x2000803C
    ldrb r0, [r0, #0]                  @ 0x080159FC
    bl decimal_position_for_mode_range @ 0x080159FE
    ldr r1, =v_2000803F                @ 0x08015A02 pool 0x08015D28 = 0x2000803F
    strb r0, [r1, #0]                  @ 0x08015A04
    ldr r0, =meter_mode                @ 0x08015A06 pool 0x08015E70 = 0x2000803C
    ldrb r0, [r0, #0]                  @ 0x08015A0A
    bl fn_0800FD30                     @ 0x08015A0C
    bl load_full_scale                 @ 0x08015A10
    movs r0, #10                       @ 0x08015A14
    ldr r1, =v_20008037                @ 0x08015A16 pool 0x08015A70 = 0x20008037
    strb r0, [r1, #0]                  @ 0x08015A18
    movs r0, #1                        @ 0x08015A1A
    ldr r1, =v_20008062                @ 0x08015A1C pool 0x08015AB8 = 0x20008062
    strb r0, [r1, #0]                  @ 0x08015A1E
    pop {r0, pc}                       @ 0x08015A20
    .ltorg
ENDFUNC fn_080159C8
    .ltorg

    .section .bss_port.mres, "aw", %nobits
    .global mres_diode_k
mres_diode_k: .space 1                      @ IMP-04: consecutive per-sample readings inside the short-circuit window (0..2)
    .global mres_diode_chirp_st
mres_diode_chirp_st: .space 1               @ TMP-IMP-01: 0 = ARMED (the next confirmed contact chirps), 1 = LATCHED (silent)
    .global mres_diode_in_cnt
mres_diode_in_cnt: .space 1                 @ TMP-IMP-01: consecutive means in the DIODE region (0..DIODE_REGION_CHIRP)
    .global mres_diode_away_cnt
mres_diode_away_cnt: .space 1               @ TMP-IMP-01: consecutive means in the OPEN / SHORT region (saturates at 255)

