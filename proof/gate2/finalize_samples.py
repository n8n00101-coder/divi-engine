#!/usr/bin/env python3
"""Finalize the gate-2 ear-check samples from the harvested takes.

For each candidate take (indicf5-batch run 43944853511, locked
natspan2 ref, speed 1.0 — the production mass-roll route), gate once
locally under BOTH bars with memoized measurements and export an mp3
+ QC json for every take whose GATE 2 flips (ghosts under the locked
bar, none under the recalibrated bar). Full-bar ship status is
recorded as measured — no take is presented as a ship unless
engine.ship_decision says so under the ON bar.
"""
import json
import os
import subprocess
import sys

HERE = "/home/hatch/workspace/julie-voice-gatefix"
sys.path.insert(0, HERE)
os.chdir(HERE)

import engine  # noqa: E402
import gates  # noqa: E402

_det, _fc, _id, _pace = {}, {}, {}, {}
_o_det, _o_fc = gates.nohint_detect, gates.forced_check
_o_id, _o_pace = engine._take_identity, engine._take_pace_wps
gates.nohint_detect = lambda p: _det.setdefault(p, _o_det(p))
gates.forced_check = lambda p, l, w, s=None: _fc.setdefault((p, l), _o_fc(p, l, w, s))
engine._take_identity = lambda p: _id.setdefault(p, _o_id(p))
engine._take_pace_wps = lambda p, l, n: _pace.setdefault((p, l, n), _o_pace(p, l, n))

OFF = gates.load_settings()
ON = gates.load_settings()
ON["gates"]["gate2_loanword_aware"] = True

LINES = [l.strip() for l in open(os.path.join(HERE, "jobs",
                                              "gate2-samples.txt"),
                                 encoding="utf-8") if l.strip()]
OUT = os.path.join(HERE, "proof", "gate2")
CANDS = [
    ("sample-5-short-criminal-case", 1,
     "/tmp/gate2_harvest/runner-8/s1_r8_t1.wav"),
    ("sample-5b-short-criminal-case", 1,
     "/tmp/gate2_harvest/runner-8/s1_r8_t2.wav"),
    ("sample-7-short-safety-report", 3,
     "/tmp/gate2_harvest/runner-4/s3_r4_t2.wav"),
    ("sample-7b-short-safety-report", 3,
     "/tmp/gate2_harvest/runner-9/s3_r9_t1.wav"),
    ("sample-4-police-criminal-case", 4,
     "/tmp/gate2_harvest/runner-8/s4_r8_t3.wav"),
]
log = {}
for name, si, wav in CANDS:
    text = LINES[si - 1]
    if not os.path.exists(wav):
        log[name] = {"take": wav, "missing": True}
        continue
    rep_off = gates.run_all_gates(wav, "te", text, OFF)
    rep_on = gates.run_all_gates(wav, "te", text, ON)
    ship_off, ex_off = engine.ship_decision(wav, "te", text, OFF, rep_off)
    ship_on, ex_on = engine.ship_decision(wav, "te", text, ON, rep_on)
    g_off = rep_off["gate2_ghost_words"]["ghosts"]
    g_on = rep_on["gate2_ghost_words"]["ghosts"]
    flip = bool(g_off) and not g_on
    entry = {"sentence": text, "take": os.path.basename(wav),
             "gate2_flip": flip, "ghosts_off": g_off, "ghosts_on": g_on,
             "ship_off": ship_off, "ship_on": ship_on,
             "identity": ex_on.get("identity"), "pace_wps": ex_on.get("pace_wps"),
             "blocked_by": ex_on.get("blocked_by"),
             "gate1_pass_on": rep_on["gate1_nohint_language"]["pass"],
             "gate7_pass_on": rep_on["gate7_cut_word"]["pass"],
             "unhinted": rep_on["gate1_nohint_language"]["unhinted_text"]}
    log[name] = entry
    print(f"{name}: gate2_flip={flip} ship {ship_off}->{ship_on} "
          f"id={entry['identity']} wps={entry['pace_wps']} "
          f"ghosts {len(g_off)}->{len(g_on)}", flush=True)
    if flip:
        mp3 = os.path.join(OUT, name + ".mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav,
                        "-codec:a", "libmp3lame", "-b:a", "192k", mp3],
                       check=True)
        qc = {"sentence": text, "take": os.path.basename(wav),
              "gate_report_flag_OFF": rep_off,
              "gate_report_flag_ON": rep_on,
              "ship_extra_flag_ON": ex_on, "summary": entry}
        with open(os.path.join(OUT, name + ".qc.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)

with open(os.path.join(OUT, "finalize-log.json"), "w", encoding="utf-8") as fh:
    json.dump(log, fh, ensure_ascii=False, indent=1)
print("DONE")
