#!/usr/bin/env python3
"""Proof for gates 6 + 7 (head grunt / cut word, added 2026-11-16 on
the owner's orders after his ear caught both defects in the OmniVoice
Sample B test).

Runs the REAL gate code (acoustic_gates.py) over the REAL evidence
files from ~/workspace/voicestudio-omnivoice-test/:

  1. Gate 6 detection fires on ALL 8 Sample B v1 sentence files
     (every one carries the head grunt).
  2. Gate 6 stays silent on genuine narration (the canonical
     natspan2 reference, the Telugu reference, the English reference
     — none may be muted).
  3. Gate 7 FAILS Sample B v1 sentence 6 — the take whose ending
     "mana varaku vasthayi" never landed (detached weak tail) — and
     passes the other seven v1 sentences and all four Sample A
     sentences (their endings decay naturally).
  4. Gate 6's mute, applied to a copy of sentence 6, removes the
     detection and changes no file length.
  5. The v3 sentence set (v2's cleaned sentences with the
     regenerated sentence 6) passes BOTH gates on every sentence.

Run: python3 proof_omnivoice_gates.py [--sample-dir DIR]
(exit 0 = all pass; output of the 2026-11-16 run is committed next to
this file as proof_omnivoice_gates.out.txt)
"""
import argparse
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import acoustic_gates as ag  # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name
          + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-dir",
                    default=os.path.expanduser(
                        "~/workspace/voicestudio-omnivoice-test"))
    args = ap.parse_args()
    W = args.sample_dir

    print("== 1. gate 6 fires on all 8 Sample B v1 sentences ==")
    for i in range(1, 9):
        d = ag.head_grunt_detect(os.path.join(W, f"sentB{i}.wav"))
        check(f"B{i} head grunt detected", d["present"],
              str(d.get("checks")))

    print("== 2. gate 6 silent on genuine narration ==")
    for rel in ("voice/refs/natspan2.wav", "voice/telugu-reference.wav",
                "voice/english-reference.wav"):
        d = ag.head_grunt_detect(os.path.join(HERE, rel))
        check(f"no grunt in {rel}", not d["present"], str(d))

    print("== 3. gate 7 flags B6 v1 only ==")
    for i in range(1, 9):
        r = ag.cut_word_gate(os.path.join(W, f"sentB{i}.wav"))
        check(f"B{i} cut-word {'fails' if i == 6 else 'passes'}",
              r["pass"] == (i != 6), str(r["fails"]))
    for i in range(1, 5):
        r = ag.cut_word_gate(os.path.join(W, f"sent{i}.wav"))
        check(f"A{i} cut-word passes", r["pass"], str(r["fails"]))

    print("== 4. gate 6 mute round-trip on a copy of B6 ==")
    tmp = tempfile.mkdtemp(prefix="julie_grunt_proof_")
    try:
        probe = os.path.join(tmp, "b6.wav")
        shutil.copy(os.path.join(W, "sentB6.wav"), probe)
        import soundfile as sf
        n0 = len(sf.read(probe)[0])
        act = ag.mute_head_grunt(probe)
        n1 = len(sf.read(probe)[0])
        check("mute applied", act["muted"] is True, str(act))
        check("file length unchanged", n0 == n1, f"{n0} -> {n1}")
        d = ag.head_grunt_detect(probe)
        check("grunt gone after mute", not d["present"], str(d))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("== 5. v3 sentence set passes both gates ==")
    v3 = {i: os.path.join(W, f"sentB{i}_v2.wav") for i in range(1, 9)}
    v3[6] = os.path.join(W, "sentB6_v3.wav")
    for i in range(1, 9):
        p = v3[i]
        if not os.path.exists(p):
            check(f"v3 sentence {i} exists", False, p)
            continue
        hg = ag.head_grunt_gate(p)
        cw = ag.cut_word_gate(p)
        check(f"v3 B{i} gate 6 passes", hg["pass"], str(hg["detection"]))
        check(f"v3 B{i} gate 7 passes", cw["pass"], str(cw["fails"]))

    print("\n" + ("ALL PASS" if not FAILS
                  else f"{len(FAILS)} FAILURES: {FAILS}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
