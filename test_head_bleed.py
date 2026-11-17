#!/usr/bin/env python3
"""Gate 8 (head bleed) tests.

Tier 1 (always): the pure matcher (gates.head_bleed_check) on synthetic
token streams + the ship plumbing (flag discipline in head_bleed_gate /
engine.ship_decision). No ASR, no model loads.

Tier 2 (JULIE_RUN_ASR_TESTS=1): the real gate end-to-end on the
calibration corpus. THE CONTROLS (the reason the gate ships ACTIVE):
  * the two gate-2 ear-check takes (strict-audit convicted, 2026-11-17)
    must FAIL -- they open with the natspan2 reference passage's own
    closing phrase (reference bleed);
  * the ear-approved fixed13 takes must PASS -- they carry the
    natspan3 tail's echo, which the owner approved; it is recorded as
    advisory tail_echo, never failed;
  * her genuine natspan1/2/3 reference spans must PASS against their
    own transcripts (fw-base garbles her genuine openings too).
The shipped fixed14 takes are also run: S4/S6/S9 must FAIL (wide
margins on the calibration corpus); S3/S5/S7/S10 sit in the decoder's
borderline band, so >= 3 of those 4 must FAIL; S1/S2/S8/S11 verdicts
are printed for the record (fw-base is nondeterministic across
processes -- the deterministic per-take table lives in the audit).

Run:  python3 test_head_bleed.py
      JULIE_RUN_ASR_TESTS=1 python3 test_head_bleed.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


def toks_of(words, step=0.35):
    import gates
    out = []
    t = 0.0
    for w in words:
        out.append({"tok": w, "phon": gates._head_phon(w), "prob": 0.9,
                    "start": round(t, 2), "end": round(t + step, 2)})
        t += step
    return out


def tier1():
    import gates
    on = {"gates": {"head_bleed_gate": True}}
    off = {"gates": {"head_bleed_gate": False}}

    s_clean = "మీరు నిద్రలోకి జారుకున్న ప్రతిసారీ మెదడు పని చేస్తుంది"
    chk = gates.head_bleed_check(toks_of(s_clean.split()), s_clean.split(), "te")
    check("t1 clean head passes", chk["pass"] is True, chk["fails"])

    s5 = "పోలీసులు క్రిమినల్ కేసులో థియరీని రివ్యూ చేశారు."
    bleed = ["కొత్త", "క్రిమినల్", "చట్టాలు"] + s5.split()
    chk = gates.head_bleed_check(toks_of(bleed), s5.split(), "te")
    check("t1 telugu-script bleed fails", chk["pass"] is False
          and chk["tail_match"] is not None, chk["fails"])

    s7 = "స్టూడెంట్స్ సేఫ్టీ గురించి కమిటీ రిపోర్ట్ విడుదల చేశారు."
    bleed_ta = ["கொத்த", "கிரிமினல்", "சட்டாலு", "Student", "Safety",
                "Guruji", "Committee", "Report"]
    chk = gates.head_bleed_check(toks_of(bleed_ta), s7.split(), "te")
    check("t1 tamil-script bleed fails", chk["pass"] is False
          and chk["tail_match"] is not None, chk["fails"])

    loan = ["Student", "Safety", "Guruji", "Committee", "Report"]
    chk = gates.head_bleed_check(toks_of(loan), s7.split(), "te")
    check("t1 loanword opener passes", chk["pass"] is True, chk["fails"])

    lines = [ln.strip() for ln in open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "jobs",
        "fixed14-lines.txt"), encoding="utf-8") if ln.strip()]
    echo = ["తీసుకొచ్చే", "మార్కెటింగ్", "ఆసెట్స్", "అన్నారు"] + lines[1].split()
    chk = gates.head_bleed_check(toks_of(echo), lines[1].split(), "te")
    check("t1 non-default ref echo recorded, not failed",
          chk["pass"] is True and chk["tail_echo"] is not None
          and chk["tail_echo"]["ref"] == "natspan3"
          and chk["tail_echo"]["score"] >= 0.7,
          (chk["fails"], chk["tail_echo"]))

    chk = gates.head_bleed_check(
        toks_of(["zanzibar", "quixote", "wolverine"]), s_clean.split(), "te")
    check("t1 unrecognizable head fails", chk["pass"] is False, chk["fails"])

    dead = [{"tok": "அஅ", "phon": "", "prob": 0.9, "start": 0.0, "end": 0.4},
            {"tok": "இஇ", "phon": "", "prob": 0.9, "start": 0.4, "end": 0.8},
            {"tok": "మీరు", "phon": gates.any_simple("మీరు"), "prob": 0.9,
             "start": 0.8, "end": 1.1}]
    chk = gates.head_bleed_check(dead, s_clean.split(), "te")
    check("t1 unrenderable lead fails", chk["pass"] is False, chk["fails"])

    chk = gates.head_bleed_check([], s_clean.split(), "te")
    check("t1 empty head fails closed", chk["pass"] is False, chk["fails"])

    wav = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "voice", "telugu-reference.wav")
    rep = gates.head_bleed_gate(wav, "te", s_clean, off)
    check("t1 flag off -> inactive pass",
          rep["pass"] is True and rep["active"] is False, rep)
    rep = gates.head_bleed_gate(wav, "en", s_clean, on)
    check("t1 en -> inactive pass",
          rep["pass"] is True and rep["active"] is False, rep)

    import engine
    base = {"gate1_nohint_language": {"pass": True},
            "gate2_ghost_words": {"pass": True},
            "gate7_cut_word": {"pass": True}}
    rep = dict(base, gate8_head_bleed={"pass": False, "active": True})
    ship, extra = engine.ship_decision("unused.wav", "te", "x", on, rep)
    check("t1 ship blocked by gate8 when flag on",
          ship is False and extra.get("blocked_by") == "gate8_head_bleed",
          extra)
    ship, extra = engine.ship_decision("unused.wav", "te", "x", off, rep)
    check("t1 gate8 ignored when flag off",
          extra.get("blocked_by") != "gate8_head_bleed", extra)
    rep = dict(base, gate8_head_bleed={"pass": True, "active": True})
    ship, extra = engine.ship_decision("unused.wav", "te", "x", on, rep)
    check("t1 gate8 pass -> not blocked by gate8",
          extra.get("blocked_by") != "gate8_head_bleed", extra)


def tier2():
    import gates
    on = {"gates": {"head_bleed_gate": True}}
    here = os.path.dirname(os.path.abspath(__file__))
    lines = [ln.strip() for ln in open(os.path.join(
        here, "jobs", "fixed14-lines.txt"), encoding="utf-8") if ln.strip()]
    refs = json.load(open(os.path.join(
        here, "voice", "refs", "refs.json"), encoding="utf-8"))["refs"]
    g2 = os.path.expanduser("~/workspace/julie-voice-gatefix/proof/gate2")
    w = os.path.expanduser("~/workspace/voice-lib/tripti/proof/fixed14/work")

    def run(name, path, text, expect):
        rep = gates.head_bleed_gate(path, "te", text, on)
        got = rep["pass"]
        print("  %s: pass=%s tail=%s echo=%s fails=%s" % (
            name, got, (rep.get("tail_match") or {}).get("score"),
            (rep.get("tail_echo") or {}).get("score"),
            [f[:50] for f in rep.get("fails", [])]))
        if expect is not None:
            check("t2 " + name, got is expect, rep.get("fails"))
        return got

    run("ctrl5 gate-2 sample-5", os.path.join(
        g2, "sample-5-short-criminal-case.mp3"),
        "పోలీసులు క్రిమినల్ కేసులో థియరీని రివ్యూ చేశారు.", False)
    run("ctrl7 gate-2 sample-7", os.path.join(
        g2, "sample-7-short-safety-report.mp3"),
        "స్టూడెంట్స్ సేఫ్టీ గురించి కమిటీ రిపోర్ట్ విడుదల చేశారు.", False)
    run("fixed13-s1", os.path.join(
        here, "voice/samples/telugu-approved-s1-fixed13.mp3"), lines[0], True)
    run("fixed13-s2", os.path.join(
        here, "voice/samples/telugu-approved-s2-fixed13.mp3"), lines[1], True)
    for rn in ("natspan1", "natspan2", "natspan3"):
        run(rn, os.path.join(here, refs[rn]["wav"]), refs[rn]["text"], True)

    picks = {3: "fixed15/s1_r8_t1.wav", 4: "fixed15/s2_r3_t1.wav",
             5: "te-base6/indicf5-runner-6/s5_r6_t1.wav",
             6: "te-base6/indicf5-runner-3/s6_r3_t1.wav",
             7: "te-base6/indicf5-runner-9/s7_r9_t1.wav",
             9: "te-base6/indicf5-runner-6/s9_r6_t1.wav",
             10: "te-base6/indicf5-runner-3/s10_r3_t1.wav"}
    strict = {4, 6, 9}
    band = {3, 5, 7, 10}
    band_fails = 0
    for n, rel in sorted(picks.items()):
        got = run("shipped-s%d" % n, os.path.join(w, rel), lines[n - 1],
                  False if n in strict else None)
        if n in band and got is False:
            band_fails += 1
    check("t2 borderline band >=3 of 4 fail", band_fails >= 3, band_fails)
    run("shipped-s1", os.path.join(w, "approved-s1.wav"), lines[0], None)
    run("shipped-s2", os.path.join(w, "approved-s2.wav"), lines[1], None)
    run("shipped-s8", os.path.join(w, "s8-ns3/s1_r0_t2.wav"), lines[7], None)
    run("shipped-s11", os.path.join(
        w, "te-base6/indicf5-runner-5/s11_r5_t1.wav"), lines[10], None)


if __name__ == "__main__":
    tier1()
    if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
        tier2()
    print("RESULT:", "ALL PASS" if not FAILS else "FAILURES: %s" % FAILS)
    sys.exit(1 if FAILS else 0)
