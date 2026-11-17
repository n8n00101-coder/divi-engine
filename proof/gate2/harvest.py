#!/usr/bin/env python3
"""Harvest gate-2 ear-check samples from an indicf5-batch run.

Usage: harvest.py <dir-with-downloaded-artifact>

The artifact holds every whole take (s<sentence>_r<runner>_t<roll>.wav
+ .json) generated on the runners with the locked natspan2 reference
at speed 1.0. Each take is re-gated locally under BOTH bars —
flag OFF (locked) and flag ON (loanword-aware), with per-file
measurements memoized so both bars judge the identical detection —
and a take is picked for a sentence iff engine.ship_decision ships
it under ON and not under OFF (identity/pace/gate7 are
flag-independent, so the delta is gate 2 by construction).
Picked takes are written here as mp3 + <name>.qc.json.
"""
import glob
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
NAMES = {1: "sample-5-short-criminal-case",
         2: "sample-6-short-college-fee",
         3: "sample-7-short-safety-report",
         4: "sample-4-police-criminal-case"}
OUT = os.path.join(HERE, "proof", "gate2")
src = sys.argv[1]
log = {}

for si, text in enumerate(LINES, start=1):
    name = NAMES[si]
    entry = {"text": text, "takes": [], "picked": None}
    for wav in sorted(glob.glob(os.path.join(src, "**", f"s{si}_r*_t*.wav"),
                                recursive=True)):
        rep_off = gates.run_all_gates(wav, "te", text, OFF)
        rep_on = gates.run_all_gates(wav, "te", text, ON)
        ship_off, _ = engine.ship_decision(wav, "te", text, OFF, rep_off)
        ship_on, ex_on = engine.ship_decision(wav, "te", text, ON, rep_on)
        g_off = rep_off["gate2_ghost_words"]["ghosts"]
        g_on = rep_on["gate2_ghost_words"]["ghosts"]
        entry["takes"].append({
            "file": os.path.basename(wav), "ship_off": ship_off,
            "ship_on": ship_on, "ghosts_off": g_off, "ghosts_on": g_on,
            "identity": ex_on.get("identity"), "pace_wps": ex_on.get("pace_wps"),
            "blocked_by": ex_on.get("blocked_by")})
        print(f"{name} {os.path.basename(wav)}: ship {ship_off}->{ship_on} "
              f"ghosts {len(g_off)}->{len(g_on)}", flush=True)
        if ship_on and not ship_off and entry["picked"] is None:
            mp3 = os.path.join(OUT, name + ".mp3")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav,
                            "-codec:a", "libmp3lame", "-b:a", "192k", mp3],
                           check=True)
            qc = {"sentence": text, "take": os.path.basename(wav),
                  "gate_report_flag_OFF": rep_off,
                  "gate_report_flag_ON": rep_on,
                  "ship_extra_flag_ON": ex_on}
            with open(os.path.join(OUT, name + ".qc.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(qc, fh, ensure_ascii=False, indent=1)
            entry["picked"] = os.path.basename(wav)
            print(f"{name}: PICKED {entry['picked']}", flush=True)
    log[name] = entry

with open(os.path.join(OUT, "harvest-log.json"), "w", encoding="utf-8") as fh:
    json.dump(log, fh, ensure_ascii=False, indent=1)
print("DONE")
