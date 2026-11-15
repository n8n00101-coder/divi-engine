#!/usr/bin/env python3
"""Tests for the WHOLE-TAKE ONLY rule for Telugu/Hindi (Ajju's order,
2026-11-16, after the 2026-11-15 ear rejections of the patchwork builds
fixed2/fixed3/fixed5).

  1. Inside-sentence splice helpers refuse te/hi: _squash_gaps_np with
     lang te/hi raises; the clause-assembly route (Chatterbox phrase
     chunking) refuses te/hi in _gen_take_core.
  2. Ship rule plumbing: ship_decision short-circuits on a gate fail,
     passes English through on the five gates alone, and the mass-roll
     route sends large te/hi budgets to dispatch, never English.
  3. End-to-end honesty: a Telugu sentence whose takes never pass the
     ship checks produces NO output mp3 and exit code 2 (generation is
     stubbed through the http backend, the test_batch.py trick — the
     stub returns the Telugu reference wav, which is the WRONG words
     for the test sentence, so no take can ship).

Run: python3 test_wholetake.py   (exit 0 = all pass)
The end-to-end part loads the local faster-whisper model once (the
gates), so it takes a minute or two on CPU.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine  # noqa: E402

REF_WAV = os.path.join(HERE, "voice", "telugu-reference.wav")
REF_BYTES = open(REF_WAV, "rb").read()
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def unit_tests():
    import numpy as np
    settings = engine.load_settings()

    # 1a. the guard itself
    for lang in ("te", "hi"):
        try:
            engine.forbid_inside_sentence_edit(lang, "unit-test")
            check(f"forbid_inside_sentence_edit raises for {lang}", False)
        except RuntimeError:
            check(f"forbid_inside_sentence_edit raises for {lang}", True)
    try:
        engine.forbid_inside_sentence_edit("en", "unit-test")
        check("forbid_inside_sentence_edit allows en", True)
    except RuntimeError:
        check("forbid_inside_sentence_edit allows en", False)

    # 1b. the in-phrase splice helper refuses te/hi, still works for en
    y = np.zeros(2400, dtype="float32")
    for lang in ("te", "hi"):
        try:
            engine._squash_gaps_np(y, 24000, lang=lang)
            check(f"_squash_gaps_np refuses {lang}", False)
        except RuntimeError:
            check(f"_squash_gaps_np refuses {lang}", True)
    try:
        engine._squash_gaps_np(y, 24000, lang="en")
        check("_squash_gaps_np still works for en", True)
    except RuntimeError:
        check("_squash_gaps_np still works for en", False)

    # 1c. the clause-assembly generation route refuses te/hi
    try:
        engine._gen_take_core("chatterbox", "te", "పరీక్ష.", "unused.wav",
                              settings)
        check("_gen_take_core chatterbox refuses te", False)
    except RuntimeError as e:
        check("_gen_take_core chatterbox refuses te",
              "indicf5" in str(e))

    # 2. ship rule plumbing (no ASR touched on these paths)
    ship, extra = engine.ship_decision("unused.wav", "te", "a b",
                                       settings, {"pass": False})
    check("te gate-fail take never ships", ship is False and extra == {})
    ship, extra = engine.ship_decision("unused.wav", "en", "a b",
                                       settings, {"pass": True})
    check("en gate-pass take ships on gates alone", ship is True and extra == {})
    ship, _ = engine.ship_decision("unused.wav", "en", "a b",
                                   settings, {"pass": False})
    check("en gate-fail take does not ship", ship is False)

    # 2b. mass-roll routing
    limit = settings["gates"]["local_roll_limit_te_hi"]
    check("te small budget stays local",
          engine.mass_roll_route("te", limit, settings) == "local")
    check("te large budget dispatches",
          engine.mass_roll_route("te", limit + 1, settings) == "dispatch")
    check("hi large budget dispatches",
          engine.mass_roll_route("hi", 60, settings) == "dispatch")
    check("en never dispatches",
          engine.mass_roll_route("en", 600, settings) == "local")


# ------------------------------------------------------------- end-to-end --
class StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(REF_BYTES)))
        self.end_headers()
        self.wfile.write(REF_BYTES)

    def log_message(self, *a):
        pass


def stub_env(port):
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env.update({"JULIE_TTS_BACKEND": "http",
                "JULIE_TTS_URL": f"http://127.0.0.1:{port}/tts",
                "NO_PROXY": "127.0.0.1"})
    return env


def e2e_tests():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tmp = tempfile.mkdtemp(prefix="julie_wholetake_e2e_")
    try:
        out_mp3 = os.path.join(tmp, "te_line.mp3")
        # The stub returns the Telugu reference narration (crime-stats
        # words) for a WEATHER sentence: no take can pass the ship
        # checks, so the engine must write NO mp3 and exit 2.
        p = subprocess.run(
            [sys.executable, os.path.join(HERE, "engine.py"),
             "--text", "వాతావరణం ఈ రోజు చాలా బాగుంది.",
             "--lang", "te", "--out", out_mp3, "--rolls", "2"],
            capture_output=True, text=True, env=stub_env(port), timeout=1200)
        check("te run with no passing take exits 2", p.returncode == 2,
              f"rc={p.returncode} " + (p.stderr or "")[-300:])
        check("no mp3 written when no te take passes",
              not os.path.exists(out_mp3))
        qc_path = os.path.splitext(out_mp3)[0] + ".qc.json"
        check("QC report still written (gate table kept)",
              os.path.exists(qc_path))
        if os.path.exists(qc_path):
            qc = json.load(open(qc_path))
            check("QC verdict is the FAIL honesty line",
                  str(qc.get("verdict", "")).startswith("FAIL"))
            check("QC records both rolls",
                  len(qc["sentences"][0]["rolls"]) == 2)
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
