"""Divi Engine — SPEED LOCK tests (owner's order 3, 2026-11-16).

The law: by default the tool runs EXACTLY the locked recipe speeds;
speed is NEVER adjusted by the tool on its own. Any deviation happens
only via the user's explicit --speed for that job, and the QC report
prints the source (LOCKED / USER-REQUESTED).

These tests prove: the pace guard has no atempo outcome; the only
atempo call site in the codebase is speedpolicy.apply_tempo, which
refuses to run without why="recipe"|"user"; an out-of-band English
take is REJECTED (PaceBandReject) with no tempo step executed; and
an end-to-end run without --speed records LOCKED while --speed 1.1
records USER-REQUESTED in the QC report.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import speedpolicy  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          ((" — " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def unit_tests():
    s = json.load(open(os.path.join(HERE, "voice", "settings.json"),
                       encoding="utf-8"))
    # pace guard decisions: ok / regen / reject — and nothing else
    outs = {speedpolicy.pace_guard_decision(r, 5.24, 0.15)
            for r in (5.24, 5.0, 4.0, 3.0, 8.0, 12.0)}
    check("pace guard outcomes are ok/regen/reject only",
          outs <= {"ok", "regen", "reject"}, str(outs))
    check("in-band rate is ok",
          speedpolicy.pace_guard_decision(5.24, 5.24, 0.15) == "ok")
    check("out-of-band rate is regen (never a stretch)",
          speedpolicy.pace_guard_decision(1.0, 5.24, 0.15) == "regen")
    check("unmeasurable rate is reject",
          speedpolicy.pace_guard_decision(0.0, 5.24, 0.15) == "reject")

    # recipe tempo: Hindi's locked 1.20; everything else 1.0
    f, note = speedpolicy.recipe_tempo("hi", s)
    check("hindi recipe tempo is the locked 1.20", f == 1.2
          and "locked" in note.lower(), f"{f} {note}")
    check("te/en recipe tempo is 1.0",
          speedpolicy.recipe_tempo("te", s)[0] == 1.0
          and speedpolicy.recipe_tempo("en", s)[0] == 1.0)

    # user speed resolution
    check("no flag -> None (locked)",
          speedpolicy.resolve_user_speed(None) is None)
    check("valid user speed passes through",
          speedpolicy.resolve_user_speed(1.1) == 1.1)
    for bad in (0.3, 2.5, 0.0, -1.0):
        try:
            speedpolicy.resolve_user_speed(bad)
            check(f"user speed {bad} refused", False)
        except speedpolicy.SpeedPolicyError:
            check(f"user speed {bad} refused", True)

    # QC speed blocks
    b = speedpolicy.speed_block("te", s, None)
    check("QC block without flag says LOCKED",
          b["source"] == "LOCKED" and b["user_factor"] is None)
    b = speedpolicy.speed_block("te", s, 1.1)
    check("QC block with flag says USER-REQUESTED",
          b["source"] == "USER-REQUESTED" and b["user_factor"] == 1.1)

    # apply_tempo refuses any unauthorised 'why'
    import numpy as np
    import soundfile as sf
    tmp = tempfile.mkdtemp(prefix="divi_speedlock_")
    wav = os.path.join(tmp, "t.wav")
    sf.write(wav, (0.1 * np.sin(2 * np.pi * 220 *
                                np.arange(24000) / 24000)).astype("f4"),
             24000)
    for why in ("auto", "pace-guard", "correction", ""):
        try:
            speedpolicy.apply_tempo(wav, 1.1, why)
            check(f"apply_tempo why={why!r} refused", False)
        except speedpolicy.SpeedPolicyError:
            check(f"apply_tempo why={why!r} refused", True)
    check("apply_tempo factor 1.0 is a no-op",
          speedpolicy.apply_tempo(wav, 1.0, "user") is False)
    y0, _ = sf.read(wav)
    speedpolicy.apply_tempo(wav, 2.0, "user")
    y1, _ = sf.read(wav)
    check("apply_tempo user 2.0 halves the duration",
          abs(len(y1) - len(y0) / 2) < 2400,
          f"{len(y0)} -> {len(y1)}")

    # source scan: the ONLY atempo filter call site is speedpolicy.py
    offenders = []
    for fn in os.listdir(HERE):
        if fn.endswith(".py") and fn != "speedpolicy.py" \
                and not fn.startswith("test_"):
            src = open(os.path.join(HERE, fn), encoding="utf-8").read()
            if re.search(r"[\"']atempo=|atempo=\{", src):
                offenders.append(fn)
    check("no atempo call site outside speedpolicy.py", not offenders,
          str(offenders))
    src = open(os.path.join(HERE, "engine.py"), encoding="utf-8").read()
    check("engine has no _atempo_file anymore", "_atempo_file" not in src)

    # stubbed Chatterbox session: an out-of-band take raises
    # PaceBandReject and NO tempo function is ever invoked.
    import engine
    called = []
    orig = speedpolicy.apply_tempo
    speedpolicy.apply_tempo = lambda *a, **k: called.append(a) or True
    engine.speedpolicy.apply_tempo = speedpolicy.apply_tempo
    try:
        sess = engine._ChatterboxSession.__new__(
            engine._ChatterboxSession)
        sess.cfg = s["english_chatterbox"]
        sess.ref_rate = 5.24
        import numpy as np
        # one onset in 4 s -> onset rate 0.25/s, hopelessly out of band
        def fake_unit(text):
            y = np.zeros(24000 * 4, dtype="f4")
            y[1000:3000] = 0.3
            return y
        sess._gen_unit = fake_unit
        out = os.path.join(tmp, "en_take.wav")
        try:
            sess.generate("A test sentence for the pace guard.", out)
            check("out-of-band take raises PaceBandReject", False)
        except engine.PaceBandReject:
            check("out-of-band take raises PaceBandReject", True)
    finally:
        speedpolicy.apply_tempo = orig
        engine.speedpolicy.apply_tempo = orig
    check("no tempo step executed for the rejected take", not called,
          str(called))


# ------------------------------------------------------------- end-to-end --
class StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        data = open(os.path.join(HERE, "voice",
                                 "telugu-reference.wav"), "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def e2e_tests():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    env.update({"JULIE_TTS_BACKEND": "http",
                "JULIE_TTS_URL": f"http://127.0.0.1:{port}/tts",
                "NO_PROXY": "127.0.0.1"})
    ref_text = open(os.path.join(HERE, "voice",
                                 "telugu-reference-text.txt")).read().strip()
    tmp = tempfile.mkdtemp(prefix="divi_speedlock_e2e_")
    try:
        for label, extra, want in (
                ("locked", [], "LOCKED"),
                ("user", ["--speed", "1.1"], "USER-REQUESTED")):
            out = os.path.join(tmp, f"{label}.mp3")
            p = subprocess.run(
                [sys.executable, os.path.join(HERE, "engine.py"),
                 "--text", ref_text, "--lang", "te", "--out", out,
                 "--rolls", "1", "--candidates", "1"] + extra,
                capture_output=True, text=True, env=env, timeout=900)
            qc_path = os.path.splitext(out)[0] + ".qc.json"
            check(f"{label}: QC written", os.path.exists(qc_path),
                  (p.stderr or "")[-200:])
            if os.path.exists(qc_path):
                qc = json.load(open(qc_path))
                check(f"{label}: QC speed source is {want}",
                      qc.get("speed", {}).get("source") == want,
                      str(qc.get("speed")))
                gen = qc["sentences"][0]["rolls"][0].get("gen") or {}
                check(f"{label}: GEN_INFO speed_source is {want}",
                      gen.get("speed_source") == want, str(gen))
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS
                  else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
