#!/usr/bin/env python3
"""Ear-check sample hunt, round 3 (after a VM restart wiped round 2's
work dir). Same selection rule: a take ships ONLY because of the new
matcher (ship under flag-ON, not under flag-OFF), judged by the
production paths (engine --gen-take, gates.run_all_gates,
engine.ship_decision) with per-file measurements memoized across the
OFF/ON runs so both bars judge the identical detection. The committed
settings.json flag is never written — flipped in memory only.
Progress is appended to rolls-log.json after every roll.
"""
import json
import os
import subprocess
import sys

PROXY_ENV = {k: v for k, v in os.environ.items() if "proxy" in k.lower()}
HERE = "/home/hatch/workspace/julie-voice-gatefix"
sys.path.insert(0, HERE)
os.chdir(HERE)

import engine  # noqa: E402
import gates  # noqa: E402

_det_cache, _fc_cache, _id_cache, _pace_cache = {}, {}, {}, {}
_orig_detect, _orig_fc = gates.nohint_detect, gates.forced_check
_orig_id, _orig_pace = engine._take_identity, engine._take_pace_wps


def cached_detect(path):
    if path not in _det_cache:
        _det_cache[path] = _orig_detect(path)
    return _det_cache[path]


def cached_fc(path, lang, words, settings=None):
    key = (path, lang)
    if key not in _fc_cache:
        _fc_cache[key] = _orig_fc(path, lang, words, settings)
    return _fc_cache[key]


def cached_id(path):
    if path not in _id_cache:
        _id_cache[path] = _orig_id(path)
    return _id_cache[path]


def cached_pace(path, lang, n):
    key = (path, lang, n)
    if key not in _pace_cache:
        _pace_cache[key] = _orig_pace(path, lang, n)
    return _pace_cache[key]


gates.nohint_detect = cached_detect
gates.forced_check = cached_fc
engine._take_identity = cached_id
engine._take_pace_wps = cached_pace

OUT = os.path.join(HERE, "proof", "gate2")
WORK = "/tmp/gate2_work3"
os.makedirs(WORK, exist_ok=True)

OFF = gates.load_settings()
ON = gates.load_settings()
ON["gates"]["gate2_loanword_aware"] = True
assert OFF["gates"]["gate2_loanword_aware"] is False

SENTENCES = [
    ("sample-4-police-criminal-case",
     "పోలీసులు క్రిమినల్ కేసులో థియరీని మళ్ళీ రివ్యూ చేశారు, కానీ "
     "ఎవిడెన్స్ మాత్రం దొరకలేదు."),
    ("sample-5-short-criminal-case",
     "పోలీసులు క్రిమినల్ కేసులో థియరీని రివ్యూ చేశారు."),
    ("sample-6-short-college-fee",
     "కాలేజీ ఫీజు గురించి కమిటీ రిపోర్ట్ ఇచ్చింది."),
    ("sample-7-short-safety-report",
     "స్టూడెంట్స్ సేఫ్టీ గురించి కమిటీ రిపోర్ట్ విడుదల చేశారు."),
]
MAX_ROLLS = 12
PY = "/home/hatch/workspace/voice-lib/venv/bin/python"
LOG = os.path.join(OUT, "rolls-log.json")
results = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}


def save():
    json.dump(results, open(LOG, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


for name, text in SENTENCES:
    entry = results.setdefault(name, {"text": text, "rolls": [],
                                      "picked_roll": None})
    if entry.get("picked_roll"):
        print(f"{name}: already picked", flush=True)
        continue
    done = {r["roll"] for r in entry["rolls"]
            if r.get("ghosts_off") is not None or r.get("gen_error")}
    picked = None
    for roll in range(1, MAX_ROLLS + 1):
        if roll in done:
            continue
        wav = os.path.join(WORK, f"{name}-r{roll}.wav")
        if not os.path.exists(wav):
            env = dict(os.environ)
            env.update(PROXY_ENV)
            p = subprocess.run(
                [PY, "engine.py", "--gen-take", "te", text, wav],
                cwd=HERE, env=env, capture_output=True, text=True)
            if p.returncode != 0 or not os.path.exists(wav):
                entry["rolls"].append({"roll": roll, "gen_error":
                                       (p.stderr or p.stdout)[-300:]})
                save()
                print(f"{name} roll {roll}: GEN ERROR", flush=True)
                continue
        rep_off = gates.run_all_gates(wav, "te", text, OFF)
        rep_on = gates.run_all_gates(wav, "te", text, ON)
        ship_off, ex_off = engine.ship_decision(wav, "te", text, OFF, rep_off)
        ship_on, ex_on = engine.ship_decision(wav, "te", text, ON, rep_on)
        g_off = rep_off["gate2_ghost_words"]["ghosts"]
        g_on = rep_on["gate2_ghost_words"]["ghosts"]
        entry["rolls"].append({
            "roll": roll, "ship_off": ship_off, "ship_on": ship_on,
            "ghosts_off": g_off, "ghosts_on": g_on,
            "identity": ex_on.get("identity"), "pace_wps": ex_on.get("pace_wps"),
            "blocked_by": ex_on.get("blocked_by"),
            "gate1_pass": rep_on["gate1_nohint_language"]["pass"],
            "unhinted": rep_on["gate1_nohint_language"]["unhinted_text"],
        })
        save()
        print(f"{name} roll {roll}: ship {ship_off}->{ship_on} "
              f"ghosts {len(g_off)}->{len(g_on)} id={ex_on.get('identity')} "
              f"wps={ex_on.get('pace_wps')} blocked={ex_on.get('blocked_by')}",
              flush=True)
        if ship_on and not ship_off:
            picked = {"wav": wav, "roll": roll, "rep_off": rep_off,
                      "rep_on": rep_on, "extra_on": ex_on}
            break
    if picked:
        mp3 = os.path.join(OUT, name + ".mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", picked["wav"],
                        "-codec:a", "libmp3lame", "-b:a", "192k", mp3],
                       check=True)
        qc = {"sentence": text, "picked_roll": picked["roll"],
              "gate_report_flag_OFF": picked["rep_off"],
              "gate_report_flag_ON": picked["rep_on"],
              "ship_extra_flag_ON": picked["extra_on"]}
        with open(os.path.join(OUT, name + ".qc.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)
        entry["picked_roll"] = picked["roll"]
        save()
        print(f"{name}: PICKED roll {picked['roll']} -> {mp3}", flush=True)
    else:
        print(f"{name}: NO FLIP in {MAX_ROLLS} rolls", flush=True)

print("DONE")
