#!/usr/bin/env python3
"""Gate 9b (absorbed tail grunt) tests.

Tier 1 (always): synthetic harmonic-stack takes through
acoustic_gates.absorbed_tail_detect — the collapse-return shape
with a creak return and a flat-plateau return must convict; a
stop-closure + declining final syllable (the TE S1/S4 shape) and a
noise return must pass — plus the flag discipline in
gates.absorbed_tail_gate and the repair/ship plumbing
(repair.defect_classes / take_score, engine.ship_decision).
No model loads.

Tier 2 (JULIE_RUN_ASR_TESTS=1): the real calibration corpus — the
ear-convicted v2 Hindi S1 take (hi_u1_a1: energy collapse
[4.525-4.575] inside करता's aligner span, then an 85 ms creak
return at F0 73 Hz against a 171 Hz word core) must be convicted
with the large-v3-turbo word spans recorded in word_audit.json;
the clean v2 sentences and the stop-closure TE takes must pass;
the v1 Hindi S3 take convicts unanchored (flat-plateau class).

Run:  python3 test_absorbed_tail.py
      JULIE_RUN_ASR_TESTS=1 python3 test_absorbed_tail.py
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
    """Build a synthetic take whose aligner word spans the WHOLE
    phonation (the absorbed condition), with realistic head/tail
    silence padding. Returns (y, word_start, word_end)."""
    import numpy as np
    head = np.zeros(int(0.4 * SR), np.float32)
    word = stack(215, 185, 0.85)
    collapse = np.full(int(0.055 * SR), 0.002, np.float32)
    tail = np.zeros(int(0.6 * SR), np.float32)
    if kind == "clean":
        y = np.concatenate([head, word, tail])
        return y, 0.4, 0.4 + 0.85
    if kind == "plateau":
        ret = stack(150, 150, 0.18, amp=0.32)
        y = np.concatenate([head, word, collapse, ret, tail])
        return y, 0.4, 0.4 + 0.85 + 0.055 + 0.18
    if kind == "creak":
        ret = stack(73, 73, 0.12, amp=0.34)
        y = np.concatenate([head, word, collapse, ret, tail])
        return y, 0.4, 0.4 + 0.85 + 0.055 + 0.12
    if kind == "stop_syllable":
        p1 = stack(215, 200, 0.45)
        clo = np.full(int(0.045 * SR), 0.002, np.float32)
        fin = stack(185, 148, 0.19, amp=0.40)   # slope ~ -195 Hz/s
        y = np.concatenate([head, p1, clo, fin, tail])
        return y, 0.4, 0.4 + 0.45 + 0.045 + 0.19
    if kind == "noise":
        rng = np.random.default_rng(7)
        ret = (0.008 * rng.standard_normal(int(0.15 * SR))).astype(np.float32)
        y = np.concatenate([head, word, collapse, ret, tail])
        return y, 0.4, 0.4 + 0.85 + 0.055 + 0.15
    raise ValueError(kind)


def with_bed(y):
    """A whisper of room noise across the take, so the island
    floor estimate behaves as it does on real takes."""
    import numpy as np
    rng = np.random.default_rng(11)
    bed = (0.001 * rng.standard_normal(len(y))).astype(np.float32)
    return (y + bed).astype(np.float32)


def tier1():
    import soundfile as sf
    import acoustic_gates as ag

    want = {"clean": False, "plateau": True, "creak": True,
            "stop_syllable": False, "noise": False}
    for kind, w in want.items():
        y, ws, we = synth(kind)
        y = with_bed(y)
        path = f"/tmp/at_{kind}.wav"
        sf.write(path, y, SR)
        try:
            det = ag.absorbed_tail_detect(path, ws, we)
            check(f"t1 detect {kind} present={w}",
                  det["present"] is w, det.get("reason"))
            if kind == "plateau":
                check("t1 plateau regime named",
                      det.get("regime") == "flat_plateau", det.get("regime"))
            if kind == "creak":
                check("t1 creak regime named",
                      det.get("regime") == "creak", det.get("regime"))
            gate = ag.absorbed_tail_gate(path, ws, we)
            check(f"t1 gate {kind} pass={not w}",
                  gate["pass"] is (not w), gate["pass"])
        finally:
            os.unlink(path)

    # -- gates.absorbed_tail_gate flag discipline (no ASR on these)
    import gates
    txt = "कुछ पाठ यहाँ है"
    off = {"gates": {"absorbed_tail_gate": False}}
    on = {"gates": {"absorbed_tail_gate": True}}
    r = gates.absorbed_tail_gate("unused.wav", "te", txt, off)
    check("t1 flag off -> inactive pass",
          r["active"] is False and r["pass"] is True, r)
    r = gates.absorbed_tail_gate("unused.wav", "en", txt, on)
    check("t1 en -> inactive pass",
          r["active"] is False and r["pass"] is True, r)

    # -- repair plumbing
    import repair
    base = {"gate1_nohint_language": {"pass": True},
            "gate2_ghost_words": {"pass": True, "ghosts": []},
            "gate3_pronunciation": {"pass": True, "rows": [],
                                    "min_prob": 0.9},
            "gate4_phys_swallowed": {"pass": True, "fail_words": []},
            "gate5_pitch": {"pass": True, "f0_med": 200,
                            "band": [185, 220]},
            "gate6_head_grunt": {"pass": True},
            "gate7_cut_word": {"pass": True},
            "gate8_head_bleed": {"active": True, "pass": True},
            "gate9_tail_grunt": {"active": True, "pass": True},
            "gate9b_absorbed_tail": {"active": True, "pass": True},
            "gate10_flagged_word": {"active": True, "pass": True}}
    bad = json.loads(json.dumps(base))
    bad["gate9b_absorbed_tail"] = {"active": True, "pass": False}
    check("t1 defect_classes sees absorbed tail as tail_grunt",
          repair.TAIL_GRUNT in repair.defect_classes(bad),
          repair.defect_classes(bad))
    check("t1 defect_classes clean without gate9b fail",
          repair.TAIL_GRUNT not in repair.defect_classes(base))
    check("t1 take_score penalises absorbed tail by 20",
          repair.take_score(base) - repair.take_score(bad) == 20.0,
          (repair.take_score(base), repair.take_score(bad)))

    # -- engine ship plumbing
    import engine
    settings = {"gates": {"head_bleed_gate": True,
                          "tail_grunt_gate": True,
                          "absorbed_tail_gate": True,
                          "flagged_word_gate": True,
                          "identity_min_te_hi": 0.85,
                          "pace_wps_te_hi": [1.9, 2.5]}}
    rep = json.loads(json.dumps(base))
    rep["gate9b_absorbed_tail"] = {"active": True, "pass": False}
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings, rep)
    check("t1 ship blocked by gate9b when enabled",
          ship is False
          and extra.get("blocked_by") == "gate9b_absorbed_tail",
          extra.get("blocked_by"))
    settings2 = json.loads(json.dumps(settings))
    settings2["gates"]["absorbed_tail_gate"] = False
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings2, rep)
    check("t1 flag off -> not blocked by gate9b",
          extra.get("blocked_by") != "gate9b_absorbed_tail",
          extra.get("blocked_by"))


def tier2():
    import acoustic_gates as ag
    work2 = "/home/hatch/workspace/turbo-run-work/space_run2"
    work1 = "/home/hatch/workspace/turbo-run-work/space_run"
    audit_p = "/home/hatch/workspace/turbo-run-work/word_audit.json"
    if not (os.path.isdir(work2) and os.path.exists(audit_p)):
        print("SKIP tier2 (calibration corpus not present)")
        return
    audit = json.load(open(audit_p, encoding="utf-8"))

    def spans(tag):
        w = audit[tag]["words"][-1]
        return w["s"], w["e"]

    p = os.path.join(work2, "hi_u1_a1.wav")
    ws, we = spans("hi_u1_a1")
    det = ag.absorbed_tail_detect(p, ws, we)
    check("t2 convicted v2 hi_u1_a1 -> absorbed grunt (creak)",
          det["present"] is True and det.get("regime") == "creak", det)
    for tag in ("hi_u2_a1", "hi_u4_a1", "hi_u8_a1",
                "te_u1_a1", "te_u4_a1", "te_u3_a1"):
        ws, we = spans(tag)
        det = ag.absorbed_tail_detect(os.path.join(work2, tag + ".wav"),
                                      ws, we)
        check(f"t2 clean {tag} -> pass", det["present"] is False,
              det.get("reason"))
    det = ag.absorbed_tail_detect(os.path.join(work1, "hi_u3_a1.wav"))
    check("t2 v1 hi_u3_a1 unanchored -> flat-plateau conviction",
          det["present"] is True and det.get("regime") == "flat_plateau",
          det)
    # Controls: her genuine reference spans — printed, not asserted
    # (mid-passage cuts, not true sentence endings).
    repo = os.path.dirname(os.path.abspath(__file__))
    for span in ("natspan1", "natspan2", "natspan3"):
        p = os.path.join(repo, "voice", "refs", f"{span}.wav")
        if os.path.exists(p):
            ev = ag.absorbed_tail_detect(p)
            print(f"  control {span}: present={ev['present']} "
                  f"reason={ev.get('reason')}")


if __name__ == "__main__":
    tier1()
    if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
        tier2()
    else:
        print("SKIP tier2 (set JULIE_RUN_ASR_TESTS=1 for the real corpus)")
    print("FAILS:", FAILS if FAILS else "none")
    sys.exit(1 if FAILS else 0)
