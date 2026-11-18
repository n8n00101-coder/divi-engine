#!/usr/bin/env python3
"""Gate 6 strengthened (head grunt, creak regime + tile scan) tests.

The v3 Hindi sample shipped FOUR creak head grunts (S1/S3/S4/S5:
0.18-0.20 s islands at 62-75 Hz, ~10-12 dB under the body) because
the original gate-6 band required F0 100-190 Hz — the modal regime
of the 2026-11-16 Sample B grunt. Gates 9/9b are tail-only, so
nothing else looked at the heads. Ajju's ear convicted the v3
Hindi sample on 2026-11-18; this suite pins the fix.

Tier 1 (always): synthetic takes through
acoustic_gates.head_grunt_detect / head_creak_scan /
head_grunt_gate — modal and creak islands must convict (and the
mute remedy must clear a separated creak), a glued creak must fail
via the scan, a -41 dB residue and a body-level low onset must
pass, plus the repair plumbing for a gate-6 fail.

Tier 2 (JULIE_RUN_ASR_TESTS=1): the real corpus — the convicted
v3 Hindi raws (space_run2 hi_u3/u4/u5, space_run3 hi_u1_a2) must
convict in the creak regime, the modal raws (hi_u1_a1, hi_u2_a1)
in the modal regime; her genuine refs and the ear-approved v3
Telugu delivered slices must pass.

Run:  python3 test_head_creak.py
      JULIE_RUN_ASR_TESTS=1 python3 test_head_creak.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []
SR = 24000


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + ((" | " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def stack(f0a, f0b, dur, amp=0.45):
    """A voiced harmonic stack gliding f0a -> f0b over dur seconds."""
    import numpy as np
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = np.linspace(f0a, f0b, n)
    ph = 2 * np.pi * np.cumsum(f0) / SR
    y = (np.sin(ph) + 0.6 * np.sin(2 * ph) + 0.35 * np.sin(3 * ph)
         + 0.2 * np.sin(4 * ph))
    env = np.minimum(1.0, t / 0.03) * np.minimum(1.0, (dur - t) / 0.03 + 0.2)
    return (amp * env * y / 1.9).astype(np.float32)


def synth(kind):
    """(y, ) synthetic takes at 24 kHz with a 0.09 s head pad, like
    a raw Space take before trim. A -55 dB room-tone bed runs under
    everything: without it the island floor estimate (_floor_ref,
    5th percentile) lands ON the grunt itself and no island forms —
    real takes always carry the bed."""
    import numpy as np
    pad = np.zeros(int(0.09 * SR), np.float32)
    word = stack(215, 185, 1.20)                    # the first word
    gap = np.zeros(int(0.35 * SR), np.float32)
    if kind == "clean":
        y = np.concatenate([pad, word])
    elif kind == "modal":
        y = np.concatenate([pad, stack(145, 145, 0.20, amp=0.15),
                            gap, word])
    elif kind == "creak":
        y = np.concatenate([pad, stack(72, 72, 0.20, amp=0.15),
                            gap, word])
    elif kind == "residue":   # muted-grunt residue, ~-41 dB vs body
        y = np.concatenate([pad, stack(72, 72, 0.20, amp=0.004),
                            gap, word])
    elif kind == "glued":     # creak glued to the first word, no gap
        y = np.concatenate([pad, stack(72, 72, 0.20, amp=0.15),
                            word])
    elif kind == "low_onset":  # a real low first word at body level
        y = np.concatenate([pad, stack(160, 160, 0.30), gap, word])
    else:
        raise ValueError(kind)
    rng = np.random.default_rng(7)
    bed = (0.0018 * rng.standard_normal(len(y))).astype(np.float32)
    return y + bed


def _tmp(y):
    import tempfile
    import soundfile as sf
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    f.close()
    sf.write(f.name, y, SR)
    return f.name


def tier1():
    import acoustic_gates as ag

    for kind, want, regime in (("modal", True, "modal"),
                               ("creak", True, "creak"),
                               ("clean", False, None),
                               ("residue", False, None),
                               ("low_onset", False, None)):
        p = _tmp(synth(kind))
        try:
            det = ag.head_grunt_detect(p)
            check(f"t1 {kind} island present={want}",
                  det["present"] is want, det.get("regime"))
            if want:
                check(f"t1 {kind} regime", det["regime"] == regime,
                      det["regime"])
            gate = ag.head_grunt_gate(p)
            check(f"t1 {kind} gate pass={not want}",
                  gate["pass"] is (not want), gate["pass"])
        finally:
            os.unlink(p)

    # glued creak: the island detector must NOT convict (no mute
    # remedy inside speech) but the tile scan must fail the gate
    p = _tmp(synth("glued"))
    try:
        det = ag.head_grunt_detect(p)
        check("t1 glued island not convicted", det["present"] is False,
              det.get("checks"))
        scan = ag.head_creak_scan(p)
        check("t1 glued scan convicts", scan["present"] is True, scan)
        gate = ag.head_grunt_gate(p)
        check("t1 glued gate fails", gate["pass"] is False)
    finally:
        os.unlink(p)

    # mute remedy clears a separated creak (gate 6 apply path)
    p = _tmp(synth("creak"))
    try:
        gate = ag.head_grunt_gate(p, apply=True)
        check("t1 creak muted -> gate passes", gate["pass"] is True,
              gate.get("action"))
        det = ag.head_grunt_detect(p)
        check("t1 creak muted -> detect clean",
              det["present"] is False)
    finally:
        os.unlink(p)

    # repair plumbing: a gate-6 fail is the GRUNT defect class
    import repair
    rep = {"gate6_head_grunt": {"pass": False}}
    check("t1 defect_classes sees head_grunt",
          repair.GRUNT in repair.defect_classes(rep),
          repair.defect_classes(rep))


def tier2():
    import acoustic_gates as ag
    home = os.path.expanduser("~")
    sr2 = os.path.join(home, "workspace/turbo-run-work/space_run2")
    sr3 = os.path.join(home, "workspace/turbo-run-work/space_run3")
    hunt = os.path.join(home, "workspace/turbo-run-work/hi_hunt")
    repo = os.path.dirname(os.path.abspath(__file__))
    cases = [
        (os.path.join(sr2, "hi_u3_a1.wav"), True, "creak"),
        (os.path.join(sr2, "hi_u4_a1.wav"), True, "creak"),
        (os.path.join(sr2, "hi_u5_a1.wav"), True, "creak"),
        (os.path.join(sr3, "hi_u1_a2.wav"), True, "creak"),
        (os.path.join(sr3, "hi_u1_a1.wav"), True, "modal"),
        (os.path.join(sr2, "hi_u2_a1.wav"), True, "modal"),
        (os.path.join(hunt, "slice_hi_s3.wav"), True, "creak"),
        (os.path.join(hunt, "slice_hi_s5.wav"), True, "creak"),
        (os.path.join(hunt, "slice_hi_s2.wav"), False, None),
        (os.path.join(hunt, "slice_hi_s7.wav"), False, None),
        (os.path.join(hunt, "slice_hi_s8.wav"), False, None),
        (os.path.join(repo, "voice", "refs", "natspan1.wav"),
         False, None),
        (os.path.join(repo, "voice", "refs", "natspan2.wav"),
         False, None),
        (os.path.join(repo, "voice", "refs", "natspan3.wav"),
         False, None),
    ]
    ran = 0
    for path, want, regime in cases:
        if not os.path.exists(path):
            continue
        ran += 1
        det = ag.head_grunt_detect(path)
        scan = ag.head_creak_scan(path)
        got = bool(det["present"] or scan["present"])
        tag = os.path.basename(path)
        check(f"t2 {tag} present={want}", got is want,
              {"island": det["present"], "regime": det.get("regime"),
               "scan": scan["present"]})
        if want and regime:
            check(f"t2 {tag} regime={regime}",
                  det.get("regime") == regime, det.get("regime"))
    if not ran:
        print("SKIP tier2 (calibration corpus not present)")


def main():
    tier1()
    if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
        tier2()
    else:
        print("SKIP tier2 (set JULIE_RUN_ASR_TESTS=1 for the real corpus)")
    print("FAILURES:", FAILS if FAILS else "none")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
