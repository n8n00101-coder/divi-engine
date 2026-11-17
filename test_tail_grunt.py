#!/usr/bin/env python3
"""Gate 9 (tail grunt) tests.

Tier 1 (always): synthetic harmonic-stack takes through
turbo.tail_grunt_check + acoustic_gates.tail_grunt_detect (ASR mode),
the flag discipline in gates.tail_grunt_gate, and the repair/ship
plumbing (repair.defect_classes / take_score / candidate_plan,
engine.ship_decision). No model loads.

Tier 2 (JULIE_RUN_ASR_TESTS=1): the real convicting path — the
shipped samples' convicted raw take (te_u4_a2: phonation 80 ms past
the large-v3-turbo last-word end at a flat 140 Hz, measured
2026-11-17) must be convicted by turbo.tail_grunt_check driven by
the judge subprocess; her genuine reference spans are printed as
controls.

Run:  python3 test_tail_grunt.py
      JULIE_RUN_ASR_TESTS=1 python3 test_tail_grunt.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []
SR = 24000


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))
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
    """Build a synthetic take. Returns (y, word_end_s)."""
    import numpy as np
    word = stack(215, 195, 1.20)          # the "last word", ends 1.20
    # decay the word's own release so phonation ends ~1.15
    word[int(1.05 * SR):] *= np.linspace(1, 0.05, len(word) - int(1.05 * SR))
    if kind == "clean":
        return np.concatenate([word, np.zeros(int(0.4 * SR), np.float32)]), 1.10
    grunt = stack(140, 140, 0.22, amp=0.30)   # flat 140 Hz grunt stack
    dip = np.full(int(0.03 * SR), 0.004, np.float32)  # glued: shallow dip
    if kind == "grunt":
        return np.concatenate([word, dip, grunt,
                               np.zeros(int(0.3 * SR), np.float32)]), 1.20
    if kind == "noise":
        rng = np.random.default_rng(7)
        noise = (0.008 * rng.standard_normal(int(0.30 * SR))).astype(np.float32)
        return np.concatenate([word, noise,
                               np.zeros(int(0.2 * SR), np.float32)]), 1.10
    raise ValueError(kind)


def tier1():
    import numpy as np
    import soundfile as sf
    import turbo
    import acoustic_gates as ag

    txt = "the brain works quietly"
    # -- clean take: no action (the aligner end tracks the acoustic
    # end on a clean take, as measured on the shipped finals:
    # residual <= 0.03 s)
    y, _ = synth("clean")
    isl, _peak = turbo._islands(y)
    lwe = isl[-1][1] / SR - 0.03
    info, cut = turbo.tail_grunt_check(
        y, {"last_word_end": lwe, "hyp": txt, "cer": 0.0}, txt)
    check("t1 clean take -> no action", info["action"] == "none"
          and info["present"] is False, info)
    # -- glued grunt, aligner last word matches: CUT at the word end
    y, lwe = synth("grunt")
    info, cut = turbo.tail_grunt_check(
        y, {"last_word_end": lwe, "hyp": txt, "cer": 0.0}, txt)
    check("t1 glued grunt -> present", info["present"] is True, info)
    check("t1 glued grunt -> cut", info["action"] == "cut" and cut is not None,
          info)
    if cut is not None:
        check("t1 cut lands at the word end", abs(len(cut) / SR - lwe) < 0.01,
              len(cut) / SR)
        info2, _ = turbo.tail_grunt_check(
            cut, {"last_word_end": lwe, "hyp": txt, "cer": 0.0}, txt)
        check("t1 cut take re-checks clean", info2["action"] == "none",
              info2)
    # -- same grunt, aligner last word is NOT the script's: FAIL
    info, cut = turbo.tail_grunt_check(
        y, {"last_word_end": lwe, "hyp": "the brain works loudly",
            "cer": 0.4}, txt)
    check("t1 grunt + last-word mismatch -> fail",
          info["action"] == "fail" and cut is None, info)
    # -- unvoiced tail past the word end: no action
    y, lwe = synth("noise")
    info, cut = turbo.tail_grunt_check(
        y, {"last_word_end": lwe, "hyp": txt, "cer": 0.0}, txt)
    check("t1 noise tail -> no action", info["action"] == "none", info)    # -- unmeasurable without an ASR end: no action, reason recorded
    info, cut = turbo.tail_grunt_check(y, {"hyp": txt}, txt)
    check("t1 no ASR end -> unmeasurable, no action",
          info["action"] == "none" and "reason" in info, info)

    # -- acoustic_gates ASR-anchored detection on written wavs
    import tempfile
    for kind, lwe, want in (("grunt", 1.20, True), ("clean", 1.10, False)):
        y, _ = synth(kind)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            sf.write(path, y, SR)
            det = ag.tail_grunt_detect(path, lwe)
            check(f"t1 acoustic detect {kind} -> present={want}",
                  det["present"] is want, det)
            gate = ag.tail_grunt_gate(path, lwe)
            check(f"t1 acoustic gate {kind} pass={not want}",
                  gate["pass"] is (not want), gate["pass"])
        finally:
            os.unlink(path)

    # -- gates.tail_grunt_gate flag discipline (no ASR on these paths)
    import gates
    off = {"gates": {"tail_grunt_gate": False}}
    on = {"gates": {"tail_grunt_gate": True}}
    r = gates.tail_grunt_gate("unused.wav", "te", txt, off)
    check("t1 flag off -> inactive pass", r["active"] is False
          and r["pass"] is True, r)
    r = gates.tail_grunt_gate("unused.wav", "en", txt, on)
    check("t1 en -> inactive pass", r["active"] is False
          and r["pass"] is True, r)

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
            "gate9_tail_grunt": {"active": True, "pass": True}}
    bad = json.loads(json.dumps(base))
    bad["gate9_tail_grunt"] = {"active": True, "pass": False}
    check("t1 defect_classes sees tail_grunt",
          repair.TAIL_GRUNT in repair.defect_classes(bad),
          repair.defect_classes(bad))
    check("t1 defect_classes clean without gate9 fail",
          repair.TAIL_GRUNT not in repair.defect_classes(base))
    check("t1 take_score penalises tail_grunt by 20",
          repair.take_score(base) - repair.take_score(bad) == 20.0,
          (repair.take_score(base), repair.take_score(bad)))
    plan = repair.candidate_plan("te", "omnivoice", 2,
                                 [repair.TAIL_GRUNT], 2)
    check("t1 wave-2 tail_grunt escalates route (te)",
          all(s["backend"] == "indicf5-space" for s in plan), plan)

    # -- engine ship plumbing
    import engine
    settings = {"gates": {"head_bleed_gate": True,
                          "tail_grunt_gate": True,
                          "identity_min_te_hi": 0.85,
                          "pace_wps_te_hi": [1.9, 2.5]}}
    rep = {"pass": False,
           "gate1_nohint_language": {"pass": True},
           "gate2_ghost_words": {"pass": True},
           "gate7_cut_word": {"pass": True},
           "gate8_head_bleed": {"active": True, "pass": True},
           "gate9_tail_grunt": {"active": True, "pass": False}}
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings, rep)
    check("t1 ship blocked by gate9 when enabled",
          ship is False and extra.get("blocked_by") == "gate9_tail_grunt",
          extra.get("blocked_by"))
    settings2 = json.loads(json.dumps(settings))
    settings2["gates"]["tail_grunt_gate"] = False
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings2, rep)
    check("t1 flag off -> not blocked by gate9",
          extra.get("blocked_by") != "gate9_tail_grunt",
          extra.get("blocked_by"))


def tier2():
    import subprocess
    import numpy as np
    import soundfile as sf
    import turbo
    venv_py = os.path.expanduser("~/workspace/voice-lib/venv/bin/python")
    judge = "/home/hatch/workspace/turbo-run-work/space_run/judge_one.py"
    work = "/home/hatch/workspace/turbo-run-work/space_run"

    def judge_of(path, lang, text):
        out = subprocess.run([venv_py, judge, path, lang, text],
                             capture_output=True, text=True, timeout=1200)
        return json.loads(out.stdout.strip().split("\n")[-1])

    # The convicted shipped take: TE sentence 4, attempt 2 (raw).
    text = ("కానీ అవి అక్కడే ఉంటే, మరుసటి రోజు కల్లా కలిసిపోతాయి.")
    raw = os.path.join(work, "te_u4_a2.wav")
    y, sr0 = sf.read(raw, dtype="float32")
    if y.ndim > 1:
        y = y[:, 0]
    if sr0 != SR:
        import librosa
        y = librosa.resample(y, orig_sr=sr0, target_sr=SR)
    y = turbo.trim(np.asarray(y, dtype=np.float32))
    tmp = raw + ".tier2.wav"
    sf.write(tmp, y, SR)
    try:
        full = judge_of(tmp, "te", text)
    finally:
        os.unlink(tmp)
    info, cut = turbo.tail_grunt_check(
        y, {"last_word_end": full.get("last_word_end"),
            "hyp": full.get("hyp", ""), "cer": full.get("cer", 9.0)}, text)
    check("t2 convicted te_u4_a2 -> grunt present",
          info["present"] is True, info)
    check("t2 convicted te_u4_a2 -> cut or fail (never none)",
          info["action"] in ("cut", "fail"), info)
    # Controls: her genuine reference spans — acoustic-only detect,
    # printed, not asserted (the spans are mid-passage cuts, not true
    # sentence endings; the shipped finals' 15 clean sentences are
    # the asserted genuine-voice controls, residuals <= 0.03 s).
    import acoustic_gates as ag
    repo = os.path.dirname(os.path.abspath(__file__))
    for span in ("natspan1", "natspan2", "natspan3"):
        p = os.path.join(repo, "voice", "refs", f"{span}.wav")
        if not os.path.exists(p):
            continue
        ev = ag.tail_grunt_detect(p)
        print(f"  control {span}: acoustic-only present={ev['present']} "
              f"reason={ev.get('reason')}")


def main():
    tier1()
    if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
        tier2()
    else:
        print("SKIP tier2 (set JULIE_RUN_ASR_TESTS=1 for the ASR corpus)")
    print("FAILURES:", FAILS if FAILS else "none")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
