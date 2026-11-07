"""Induced emulator test of the DIODE chirp, both SETUP settings (production image, IMP-51).

    python -I emulator/scripts/test_diode_chirp.py [image]      default firmware/build/EEVBlog.bin

SETUP page CH in DIODE (EEPROM 0x02C, set_dch) selects the behaviour:
  0 (off, default) - the original v2.05 jump chirp: a double beep (fn_0800EE6C) on every >1000-count change against the
    last reference (v_20007CD4), at most once per lockout (v_200080B4 = 100); the reference is updated in the short
    window (-999..999) and on a chirp.
  1 (on, IMP-51) - one double beep per confirmed contact with a diode; silence while the reading stays connected
    (settling and junction drift included); silence at overload (open leads or a reverse-biased diode, |D| >= full
    scale) and on the way back to open.

The short-circuit tone (window -999..999 counts, IMP-04, per-sample, K=2 confirmed) is unchanged in both modes.  The
baseline image has the original jump chirp only, so this test is for the production image only.

Dial Ohm/beep position (5) with EEPROM 0x0B = 11 (DIODE), buzzer setting on (0x01E = 1).  PE7 is sampled every 1 ms
(2 ms in windows that must stay silent).  In contact-chirp mode a contact is confirmed after two consecutive means
(~0.2 s); a disconnect of at least two means re-arms it.
"""
import os
import sys

sys.dont_write_bytecode = True                       # keep the tree free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_backlight_timer as T  # noqa: E402

ADDR_MODE = 0x2000803C
ADDR_D = 0x20007D64                                  # the smoothed mean in display counts


def s32(e, addr):
    v = T.rd(e, addr, 4)
    return v - (1 << 32) if v >= 1 << 31 else v


def record(e, dur, step=0.001):
    """Sample PE7 every step seconds for dur seconds: (initial level, transitions [(t_rel, level)], high samples,
    samples).  e.m.run between the samples, as in test_buzzer_off.py."""
    n = int(e.m.sysclk_hz * step)
    s = e.snapshot()
    t0 = s['time_ms']
    init = 1 if s['buzzer'] else 0
    prev = init
    ev = []
    hi = 0
    tot = 0
    for _ in range(int(round(dur / step))):
        e.m.run(n)
        s = e.snapshot()
        b = 1 if s['buzzer'] else 0
        tot += 1
        hi += b
        if b != prev:
            ev.append((round(s['time_ms'] / 1000.0 - t0 / 1000.0, 4), b))
            prev = b
    return init, ev, hi, tot


def high_pulses(init, ev):
    """The high phases of a record as [(start, end)]; a phase that is open at the window start begins at 0.0, one
    still high at the window end ends with None."""
    out = []
    t = 0.0 if init else None
    for te, b in ev:
        if b:
            t = te
        else:
            if t is not None:
                out.append((t, te))
            t = None
    if t is not None:
        out.append((t, None))
    return out


def is_double_beep(init, ev):
    """Exactly two complete high pulses of 30..80 ms with a 20..100 ms gap, nothing else in the window; the window
    must start silent (a pulse open at the start is the tail of an earlier pattern, e.g. the short-circuit tone)."""
    if init:
        return False
    ps = high_pulses(init, ev)
    if len(ps) != 2 or any(a is None or b is None for a, b in ps):
        return False
    (a0, b0), (a1, b1) = ps
    return 0.03 <= b0 - a0 <= 0.08 and 0.03 <= b1 - a1 <= 0.08 and 0.02 <= a1 - b0 <= 0.10


def is_silent(init, ev):
    return init == 0 and ev == []


def has_double_beep(init, ev):
    """The window contains at least one double-beep pattern (two 30..80 ms high pulses 20..100 ms apart).  Used for the
    original jump chirp, where lockout timing may place the chirp at a variable offset."""
    ps = [(a, b) for a, b in high_pulses(init, ev) if a is not None and b is not None]
    for i in range(len(ps) - 1):
        a0, b0 = ps[i]
        a1, b1 = ps[i + 1]
        if 0.03 <= b0 - a0 <= 0.08 and 0.03 <= b1 - a1 <= 0.08 and 0.02 <= a1 - b0 <= 0.10:
            return True
    return False


def report(init, ev):
    return 'PE7 init=%d events=%r' % (init, ev)


def make_diode(image, dch):
    e = T.make(image, {0x0B: 11, 0x1E: 1, 0x02C: dch})
    e.command({'dial': 5})
    e.advance(3.0)
    return e


def test_contact_chirp_on(image):
    """IMP-51 (set_dch = 1): one double beep per confirmed contact."""
    print('=== DIODE chirp ON (contact, IMP-51, EEPROM 0x02C=1) ===')
    e = make_diode(image, 1)
    T.check('ON: DIODE mode reached', T.rd(e, ADDR_MODE) == 11, 'mode=%d' % T.rd(e, ADDR_MODE))

    print('ON-T1 leads open: silent (v2.05 chirped once after the mode entry with open leads)')
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('ON-T1 open leads: silent', is_silent(init, ev), report(init, ev))
    T.check('ON-T1 the open reading is at overload', T.rd(e, ADDR_D, 4) >= 30000, 'D=%d' % T.rd(e, ADDR_D, 4))

    print('ON-T2 contact a diode: exactly one double beep, also through the 1 s where v2.05 repeated it')
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 3.0)
    ps = high_pulses(init, ev)
    T.check('ON-T2 contact: one double beep within 3 s', is_double_beep(init, ev), report(init, ev))
    T.check('ON-T2 the beep starts within 1 s of the contact', ps and ps[0][0] is not None and ps[0][0] <= 1.0,
            'first pulse at %r' % (ps[0][0] if ps else None,))
    d = T.rd(e, ADDR_D, 4)
    T.check('ON-T2 the reading settled at 0.6 V', 5900 <= d <= 6100, 'D=%d' % d)

    print('ON-T3 a big jump while connected (0.6 -> 1.8 V, 12000 counts): silent (LATCHED; v2.05 chirped after the lockout)')
    e.command({'input': {'kind': 'diode', 'value': 1.8}})
    init, ev, hi, tot = record(e, 3.0, 0.002)
    T.check('ON-T3 drift while connected: silent', is_silent(init, ev), report(init, ev))

    print('ON-T4 disconnect: silent (v2.05 chirped twice)')
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 3.0, 0.002)
    T.check('ON-T4 disconnect: silent', is_silent(init, ev), report(init, ev))

    print('ON-T5 re-contact after the full disconnect: one double beep again')
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('ON-T5 re-contact: one double beep', is_double_beep(init, ev), report(init, ev))

    print('ON-T6 a 60 ms disconnect bounce: no chirp (the re-arm needs two consecutive open means)')
    e.command({'input': {'kind': 'open'}})
    e.advance(0.06)
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('ON-T6 bounce: silent', is_silent(init, ev), report(init, ev))

    print('ON-T7 shorted probes: the continuous tone (unchanged); short to diode: the tone ends and the contact chirps')
    e.command({'input': {'kind': 'diode', 'value': 0.0}})
    init, ev, hi, tot = record(e, 1.5)
    T.check('ON-T7 short: the tone sounds (PE7 high in most samples)', hi * 10 >= tot * 6, 'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 1.2}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('ON-T7b short to diode: the tone ends, the chirp follows, silence at the window end',
            len(ps) >= 2 and ev and ev[-1][1] == 0, 'pulses=%r' % (ps,))
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('ON-T7c after the chirp: silent (LATCHED)', is_silent(init, ev), report(init, ev))

    print('ON-T8 reverse-biased diode (negative overload): silent; forward after it: one double beep')
    e.command({'input': {'kind': 'open'}})
    e.advance(1.0)                                   # two open means: the chirp re-arms
    e.command({'input': {'kind': 'diode', 'value': -5.0}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('ON-T8 reverse bias: silent', is_silent(init, ev), report(init, ev))
    d = s32(e, ADDR_D)
    T.check('ON-T8 the reverse reading is at negative overload', d <= -30000, 'D=%d' % d)
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('ON-T8b forward after reverse: one double beep', is_double_beep(init, ev), report(init, ev))

    print('ON-T9 the 15 V range (RANGE key): the short window is +/-1 V there, a 2 V diode chirps once per contact')
    T.press(e, 'RANGE')                              # 3 V -> 15 V
    init, ev, hi, tot = record(e, 1.5)               # 0.6 V in the short window (+/-1 V): the continuous tone
    T.check('ON-T9a 15 V, the 0.6 V diode in the short window: the tone sounds', hi * 10 >= tot * 6,
            'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 2.0}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('ON-T9b 15 V, short to a 2.0 V diode: the tone ends and the contact chirps',
            len(ps) >= 2 and ev and ev[-1][1] == 0, 'pulses=%r' % (ps,))
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 1.5)
    T.check('ON-T9c 15 V, back into the short window: the tone sounds again', hi * 10 >= tot * 6,
            'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 2.0}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('ON-T9d 15 V, the next diode contact chirps once', len(ps) >= 2 and ev and ev[-1][1] == 0,
            'pulses=%r' % (ps,))
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 2.5, 0.002)
    T.check('ON-T9e 15 V, open leads: silent', is_silent(init, ev), report(init, ev))
    T.press(e, 'RANGE')                              # back to 3 V
    e.advance(1.5)
    init, ev, hi, tot = record(e, 1.5, 0.002)
    T.check('ON-T9f 3 V open again: silent', is_silent(init, ev), report(init, ev))
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('ON-T9g and the next contact chirps', is_double_beep(init, ev), report(init, ev))

    s = e.snapshot()
    T.check('ON: no unmodelled access, no safety violation', s['unmodelled'] == 0 and not s['safety'],
            'unmodelled=%r safety=%r' % (s['unmodelled'], s['safety']))


ADDR_JUMP_REF = 0x20007CD4
ADDR_JUMP_LOCK = 0x200080B4


def rearm_jump(e):
    """Clear the original jump-chirp reference and lockout so the next >1000-count jump chirps."""
    e.m.uc.mem_write(ADDR_JUMP_REF, (0).to_bytes(4, 'little'))
    e.m.uc.mem_write(ADDR_JUMP_LOCK, bytes([0]))


def test_jump_chirp_off(image):
    """Original v2.05 jump chirp (set_dch = 0, default): a double beep on >1000-count jumps (lockout-gated)."""
    print('=== DIODE chirp OFF (original jump chirp, EEPROM 0x02C=0) ===')
    e = make_diode(image, 0)
    T.check('OFF: DIODE mode reached', T.rd(e, ADDR_MODE) == 11, 'mode=%d' % T.rd(e, ADDR_MODE))

    print('OFF-T1 open leads: the original jump chirp fires on a >1000-count jump (ref reset at mode entry)')
    e.command({'input': {'kind': 'open'}})
    e.advance(1.0)
    rearm_jump(e)                                    # the mode-entry jump may have fired during make_diode's advance
    init, ev, hi, tot = record(e, 3.0)
    T.check('OFF-T1 open leads: a jump chirp (double beep)', has_double_beep(init, ev), report(init, ev))
    e.advance(3.0)                                   # let the lockout clear and the reading settle

    print('OFF-T2 contact a diode: the jump from open chirps (lockout clear)')
    rearm_jump(e)
    e.command({'input': {'kind': 'open'}})
    e.advance(1.0)
    rearm_jump(e)                                    # ref = 0 while reading is open/OL
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 3.0)
    T.check('OFF-T2 contact: a jump chirp', has_double_beep(init, ev), report(init, ev))
    d = T.rd(e, ADDR_D, 4)
    T.check('OFF-T2 the reading settled at 0.6 V', 5900 <= d <= 6100, 'D=%d' % d)
    e.advance(3.0)                                   # lockout clear, ref follows on chirp

    print('OFF-T3 a big jump while connected (0.6 -> 1.8 V): the original chirps (contrast with contact-chirp mode)')
    e.advance(2.0)                                   # lockout from T2 clears; ref is 6000 (set at T2 chirp)
    e.command({'input': {'kind': 'diode', 'value': 1.8}})
    init, ev, hi, tot = record(e, 3.0)
    T.check('OFF-T3 drift/jump while connected: a jump chirp', has_double_beep(init, ev), report(init, ev))
    e.advance(3.0)

    print('OFF-T4 disconnect to open: the jump chirps')
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 3.0)
    T.check('OFF-T4 disconnect: a jump chirp', has_double_beep(init, ev), report(init, ev))
    e.advance(3.0)

    print('OFF-T5 shorted probes: the continuous short-circuit tone still works (IMP-04 per-sample, unchanged)')
    e.command({'input': {'kind': 'diode', 'value': 0.0}})
    init, ev, hi, tot = record(e, 1.5)
    T.check('OFF-T5 short: the tone sounds (PE7 high in most samples)', hi * 10 >= tot * 6, 'high in %d of %d' % (hi, tot))

    print('OFF-T6 short to diode, then stable: the tone ends (IMP-04 unchanged; the reference follows in the window)')
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    e.advance(4.0)                                   # tone ends, lockout clears, reference settles
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('OFF-T6 stable diode after settling: silent', is_silent(init, ev), report(init, ev))

    s = e.snapshot()
    T.check('OFF: no unmodelled access, no safety violation', s['unmodelled'] == 0 and not s['safety'],
            'unmodelled=%r safety=%r' % (s['unmodelled'], s['safety']))


def main(argv):
    image = argv[0] if argv else os.path.join(T.ROOT, 'firmware', 'build', 'EEVBlog.bin')
    test_contact_chirp_on(image)
    test_jump_chirp_off(image)
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    return 1 if T.fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
