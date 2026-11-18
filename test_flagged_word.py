#!/usr/bin/env python3
"""Gate 10 (flagged words) tests.

Tier 1 (always): turbo.flagged_word_check on synthetic large-model
word alignments — the convicted v2 alignment (script మరుసటి
rendered 'మస్టు', sim 0.46, syllables 2 != 4, word probability
0.952) must FAIL and a correct rendering must PASS — plus the
flag/watchlist discipline in gates.flagged_word_gate and the
repair/ship plumbing. No model loads.

Tier 2 (JULIE_RUN_ASR_TESTS=1): the real takes — turbo's check
driven by the large-v3-turbo word audit recorded in
word_audit.json convicts the shipped v2 TE S4 take; the engine-side
gate (fw-base forced alignment) also fails it (its evidence reads
the rendering as script salad: sim under the bar, syllables
unmeasurable-as-4 — the documented instrument limit; the turbo
path is the convicting instrument on the OmniVoice route).

Run:  python3 test_flagged_word.py
      JULIE_RUN_ASR_TESTS=1 python3 test_flagged_word.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []
S4 = "కానీ అవి అక్కడే ఉంటే, మరుసటి రోజు కల్లా కలిసిపోతాయి."


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + ((" | " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def words_of(pairs):
    return [{"w": " " + w, "s": s, "e": e, "p": p}
            for (w, s, e, p) in pairs]


# the v2 shipped take's measured alignment (word_audit.json)
CONVICTED = words_of([
    ("కాని", 0.00, 1.18, 0.958), ("ఆవి", 1.18, 1.36, 0.903),
    ("అక్కడే", 1.36, 1.66, 0.918), ("ఉంటే", 1.66, 1.98, 0.931),
    ("మస్టు", 1.98, 2.68, 0.952), ("రోజు", 2.68, 2.90, 0.933),
    ("కల్లా", 2.90, 3.14, 0.903), ("కల్సిపోతాయి.", 3.14, 3.70, 0.890)])
CLEAN = words_of([
    ("కానీ", 0.00, 1.18, 0.958), ("అవి", 1.18, 1.36, 0.903),
    ("అక్కడే", 1.36, 1.66, 0.918), ("ఉంటే", 1.66, 1.98, 0.931),
    ("మరుసటి", 1.98, 2.68, 0.952), ("రోజు", 2.68, 2.90, 0.933),
    ("కల్లా", 2.90, 3.14, 0.903), ("కలిసిపోతాయి.", 3.14, 3.70, 0.890)])


def tier1():
    import turbo
    saved = turbo._SETTINGS_CACHE
    try:
        turbo._SETTINGS_CACHE = {
            "gates": {"flagged_word_gate": True,
                      "flagged_word_sim_min": 0.70},
            "flagged_words": {"te": ["మరుసటి"], "hi": [], "en": []}}
        r = turbo.flagged_word_check({"words": CONVICTED}, S4, "te")
        check("t1 convicted alignment -> fail", r["pass"] is False, r)
        ent = (r.get("words") or [{}])[0]
        check("t1 convicted sim ~0.46", abs(ent.get("sim", 0) - 0.46) < 0.05,
              ent)
        check("t1 convicted syllables 2 != 4",
              ent.get("rendered_syllables") == 2
              and ent.get("script_syllables") == 4, ent)
        check("t1 convicted prob recorded (0.952, non-convicting)",
              ent.get("prob") == 0.952, ent)
        r = turbo.flagged_word_check({"words": CLEAN}, S4, "te")
        check("t1 clean alignment -> pass", r["pass"] is True, r)
        r = turbo.flagged_word_check({"words": CLEAN},
                                     "మీరు నిద్రలోకి జారుకున్న క్షణం", "te")
        check("t1 no flagged word in text -> inactive",
              r["active"] is False and r["pass"] is True, r)
        turbo._SETTINGS_CACHE = {
            "gates": {"flagged_word_gate": False},
            "flagged_words": {"te": ["మరుసటి"]}}
        r = turbo.flagged_word_check({"words": CONVICTED}, S4, "te")
        check("t1 flag off -> inactive pass",
              r["active"] is False and r["pass"] is True, r)
    finally:
        turbo._SETTINGS_CACHE = saved

    # -- gates.flagged_word_gate discipline (no-ASR paths)
    import gates
    off = {"gates": {"flagged_word_gate": False},
           "flagged_words": {"te": ["మరుసటి"]}}
    r = gates.flagged_word_gate("unused.wav", "te", S4, off)
    check("t1 engine flag off -> inactive pass",
          r["active"] is False and r["pass"] is True, r)
    on = {"gates": {"flagged_word_gate": True},
          "flagged_words": {"te": ["మరుసటి"]}}
    r = gates.flagged_word_gate("unused.wav", "te",
                                "మీరు నిద్రలోకి జారుకున్న క్షణం", on)
    check("t1 engine no hit -> inactive pass",
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
    bad["gate10_flagged_word"] = {"active": True, "pass": False}
    check("t1 defect_classes sees flagged word as PRON",
          repair.PRON in repair.defect_classes(bad),
          repair.defect_classes(bad))
    check("t1 take_score penalises flagged word by 15",
          repair.take_score(base) - repair.take_score(bad) == 15.0,
          (repair.take_score(base), repair.take_score(bad)))

    # -- engine ship plumbing
    import engine
    settings = {"gates": {"head_bleed_gate": True,
                          "tail_grunt_gate": True,
                          "absorbed_tail_gate": True,
                          "flagged_word_gate": True,
                          "identity_min_te_hi": 0.85,
                          "pace_wps_te_hi": [1.9, 2.5]}}
    rep = json.loads(json.dumps(bad))
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings, rep)
    check("t1 ship blocked by gate10 when enabled",
          ship is False
          and extra.get("blocked_by") == "gate10_flagged_word",
          extra.get("blocked_by"))
    settings2 = json.loads(json.dumps(settings))
    settings2["gates"]["flagged_word_gate"] = False
    ship, extra = engine.ship_decision("/nonexistent.wav", "te",
                                       "some text", settings2, rep)
    check("t1 flag off -> not blocked by gate10",
          extra.get("blocked_by") != "gate10_flagged_word",
          extra.get("blocked_by"))


def tier2():
    import turbo
    audit_p = "/home/hatch/workspace/turbo-run-work/word_audit.json"
    raw = "/home/hatch/workspace/turbo-run-work/space_run2/te_u4_a1.wav"
    if not (os.path.exists(audit_p) and os.path.exists(raw)):
        print("SKIP tier2 (calibration corpus not present)")
        return
    audit = json.load(open(audit_p, encoding="utf-8"))
    full = {"words": audit["te_u4_a1"]["words"],
            "hyp": audit["te_u4_a1"]["hyp"]}
    r = turbo.flagged_word_check(full, S4, "te")
    check("t2 real v2 te_u4_a1 -> flagged fail (turbo/large-model)",
          r["active"] is True and r["pass"] is False, r)
    import gates
    settings = gates.load_settings()
    rep = gates.flagged_word_gate(raw, "te", S4, settings)
    check("t2 real v2 te_u4_a1 -> flagged fail (engine/fw-base)",
          rep["active"] is True and rep["pass"] is False, rep)


if __name__ == "__main__":
    tier1()
    if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
        tier2()
    else:
        print("SKIP tier2 (set JULIE_RUN_ASR_TESTS=1 for the real corpus)")
    print("FAILS:", FAILS if FAILS else "none")
    sys.exit(1 if FAILS else 0)
