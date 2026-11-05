"""Induced emulator test of the DIODE contact chirp (production image, DESIGN.md 10 TMP-IMP-01).

    python -I emulator/scripts/test_diode_chirp.py [image]      default firmware/build/EEVBlog.bin

TMP-IMP-01: the DIODE chirp reports the contact, not the jump.  One double beep (the refusal pattern: two ~50 ms pulses
with a ~50 ms gap) sounds per confirmed contact with a diode; while the reading stays connected nothing more sounds
(value settling and junction drift included); overload - open leads or a reverse-biased diode, |D| >= full scale - is
silent, and so is the way back to open.  The short-circuit tone (window -999..999 counts, IMP-04) is unchanged.  The
v2.05 jump rule (a chirp on every change of more than 1000 counts against the last chirped reference 0x20007CD4, at
most one per second) beeped twice per contact and twice per disconnect and also beeped at overload; the baseline image
still has it, so this test is for the production image only.

Dial Ohm/beep position (5) with EEPROM 0x0B = 11 (DIODE), buzzer setting on (0x01E = 1).  PE7 is sampled every 1 ms
(2 ms in windows that must stay silent); the helpers are those of test_backlight_timer.py.  A contact is confirmed
after two consecutive means in the diode region (the mean branch runs about every 100 ms), so the double beep comes
0.1..0.6 s after the stimulus step; a disconnect of at least two means (~0.2 s) re-arms the next one.
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


def report(init, ev):
    return 'PE7 init=%d events=%r' % (init, ev)


def main(argv):
    image = argv[0] if argv else os.path.join(T.ROOT, 'firmware', 'build', 'EEVBlog.bin')
    e = T.make(image, {0x0B: 11, 0x1E: 1})
    e.command({'dial': 5})
    e.advance(3.0)
    T.check('DIODE mode reached', T.rd(e, ADDR_MODE) == 11, 'mode=%d' % T.rd(e, ADDR_MODE))

    print('T1 leads open: silent (v2.05 chirped once after the mode entry with open leads)')
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('T1 open leads: silent', is_silent(init, ev), report(init, ev))
    T.check('T1 the open reading is at overload', T.rd(e, ADDR_D, 4) >= 30000, 'D=%d' % T.rd(e, ADDR_D, 4))

    print('T2 contact a diode: exactly one double beep, also through the 1 s where v2.05 repeated it')
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 3.0)
    ps = high_pulses(init, ev)
    T.check('T2 contact: one double beep within 3 s', is_double_beep(init, ev), report(init, ev))
    T.check('T2 the beep starts within 1 s of the contact', ps and ps[0][0] is not None and ps[0][0] <= 1.0,
            'first pulse at %r' % (ps[0][0] if ps else None,))
    d = T.rd(e, ADDR_D, 4)
    T.check('T2 the reading settled at 0.6 V', 5900 <= d <= 6100, 'D=%d' % d)

    print('T3 a big jump while connected (0.6 -> 1.8 V, 12000 counts): silent (LATCHED; v2.05 chirped after the lockout)')
    e.command({'input': {'kind': 'diode', 'value': 1.8}})
    init, ev, hi, tot = record(e, 3.0, 0.002)
    T.check('T3 drift while connected: silent', is_silent(init, ev), report(init, ev))

    print('T4 disconnect: silent (v2.05 chirped twice)')
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 3.0, 0.002)
    T.check('T4 disconnect: silent', is_silent(init, ev), report(init, ev))

    print('T5 re-contact after the full disconnect: one double beep again')
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('T5 re-contact: one double beep', is_double_beep(init, ev), report(init, ev))

    print('T6 a 60 ms disconnect bounce: no chirp (the re-arm needs two consecutive open means)')
    e.command({'input': {'kind': 'open'}})
    e.advance(0.06)
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('T6 bounce: silent', is_silent(init, ev), report(init, ev))

    print('T7 shorted probes: the continuous tone (unchanged); short to diode: the tone ends and the contact chirps')
    e.command({'input': {'kind': 'diode', 'value': 0.0}})
    init, ev, hi, tot = record(e, 1.5)
    T.check('T7 short: the tone sounds (PE7 high in most samples)', hi * 10 >= tot * 6, 'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 1.2}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('T7b short to diode: the tone ends, the chirp follows, silence at the window end',
            len(ps) >= 2 and ev and ev[-1][1] == 0, 'pulses=%r' % (ps,))
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('T7c after the chirp: silent (LATCHED)', is_silent(init, ev), report(init, ev))

    print('T8 reverse-biased diode (negative overload): silent; forward after it: one double beep')
    e.command({'input': {'kind': 'open'}})
    e.advance(1.0)                                   # two open means: the chirp re-arms
    e.command({'input': {'kind': 'diode', 'value': -5.0}})
    init, ev, hi, tot = record(e, 2.0, 0.002)
    T.check('T8 reverse bias: silent', is_silent(init, ev), report(init, ev))
    d = s32(e, ADDR_D)
    T.check('T8 the reverse reading is at negative overload', d <= -30000, 'D=%d' % d)
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('T8b forward after reverse: one double beep', is_double_beep(init, ev), report(init, ev))

    print('T9 the 15 V range (RANGE key): the short window is +/-1 V there, a 2 V diode chirps once per contact')
    # Note: with the SYNTHETIC calibration the emulated converter saturates at 100000 counts, so 15 V open leads
    # (15.4 V) read 10.000 V, below the 15000-count full scale: the OPEN region is unreachable in the emulator on
    # this range.  On a meter the same input reads OL (the PF8 units through the +500 step at 0x08007EEE) and is
    # silent like every overload; here the LATCHED state keeps the open leads silent instead.
    T.press(e, 'RANGE')                              # 3 V -> 15 V; the 0.6 V diode reads 600 counts: the short
    init, ev, hi, tot = record(e, 1.5)               # window (+/-1 V on this range) gives the continuous tone
    T.check('T9a 15 V, the 0.6 V diode in the short window: the tone sounds', hi * 10 >= tot * 6,
            'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 2.0}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('T9b 15 V, short to a 2.0 V diode: the tone ends and the contact chirps',
            len(ps) >= 2 and ev and ev[-1][1] == 0, 'pulses=%r' % (ps,))
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 1.5)
    T.check('T9c 15 V, back into the short window: the tone sounds again', hi * 10 >= tot * 6,
            'high in %d of %d' % (hi, tot))
    e.command({'input': {'kind': 'diode', 'value': 2.0}})
    init, ev, hi, tot = record(e, 2.5)
    ps = high_pulses(init, ev)
    T.check('T9d 15 V, the next diode contact chirps once', len(ps) >= 2 and ev and ev[-1][1] == 0,
            'pulses=%r' % (ps,))
    e.command({'input': {'kind': 'open'}})
    init, ev, hi, tot = record(e, 2.5, 0.002)
    T.check('T9e 15 V, open leads: silent', is_silent(init, ev), report(init, ev))
    T.press(e, 'RANGE')                              # back to 3 V: the open leads read OL again
    e.advance(1.5)                                   # the accept beep of the press is over
    init, ev, hi, tot = record(e, 1.5, 0.002)
    T.check('T9f 3 V open again: silent', is_silent(init, ev), report(init, ev))
    e.command({'input': {'kind': 'diode', 'value': 0.6}})
    init, ev, hi, tot = record(e, 2.5)
    T.check('T9g and the next contact chirps', is_double_beep(init, ev), report(init, ev))

    s = e.snapshot()
    T.check('no unmodelled access, no safety violation', s['unmodelled'] == 0 and not s['safety'],
            'unmodelled=%r safety=%r' % (s['unmodelled'], s['safety']))
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    return 1 if T.fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
