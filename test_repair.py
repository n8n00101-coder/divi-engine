"""Divi Engine — SELF-HEALING REPAIR LOOP tests (owner's amendment,
2026-11-16 20:19 IST): fail -> auto-check -> auto-fix -> deliver.

Unit: the escalation ladder (repair.candidate_plan), defect
classification and candidate scoring.
End-to-end (http stub backend, Telugu):
  (a) a take with an injected head grunt is auto-repaired (muted at
      generation time) and the repaired take passes;
  (b) a truncated-ending take is replaced by a complete one via the
      ladder (wave 1 all truncated -> wave 2 complete wins);
  (c) a job with one sabotaged sentence still completes: the good
      sentence ships, the bad one is named in the QC verdict, and
      the job exits 2 with the mp3 delivered (work does not stop).
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
import repair  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          ((" — " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def unit_tests():
    # wave 1: best-of-N on the primary route
    specs = repair.candidate_plan("te", "indicf5-space", 1, [], 3)
    check("wave1: 3 candidates on the primary route",
          len(specs) == 3
          and all(s["backend"] == "indicf5-space" for s in specs))
    check("wave1: seeds are distinct",
          len({s["seed"] for s in specs}) == 3)

    # wave 2 with a ghost/language defect: ROUTE escalation first
    specs = repair.candidate_plan("te", "indicf5-space", 2,
                                  [repair.GHOST], 3)
    check("wave2 ghost: escalates to the alternate clone route",
          all(s["backend"] == "omnivoice" for s in specs),
          str(specs))

    # wave 2 with a cut-word defect: seed re-rolls + parallel
    # alternate-route candidates in the same wave
    specs = repair.candidate_plan("te", "indicf5-space", 2,
                                  [repair.CUT], 3)
    backs = {s["backend"] for s in specs}
    check("wave2 cut-word: primary re-rolls + alternate route",
          backs == {"indicf5-space", "omnivoice"}, str(specs))

    # wave 3: the full ladder reaches alternate reference spans
    specs = repair.candidate_plan("te", "indicf5-space", 3,
                                  [repair.CUT], 4)
    check("wave3: full ladder includes alternate references",
          any(s["ref"] for s in specs), str(specs))

    # Hindi wave 2 language defect: alternate reference span
    specs = repair.candidate_plan("hi", "indicf5-space", 2,
                                  [repair.LANGUAGE], 2)
    check("hi wave2 language: alternate reference span",
          all(s["ref"] == "natspan1" for s in specs), str(specs))

    # English: seed variants only — the locked recipe never changes
    specs = repair.candidate_plan("en", "chatterbox", 2,
                                  [repair.PITCH], 3)
    check("en ladder: chatterbox seed variants only",
          all(s["backend"] == "chatterbox" and s["ref"] is None
              for s in specs))

    # service backend: no clone ladder, honest fresh candidates
    specs = repair.candidate_plan("te", "http", 2, [repair.CUT], 2)
    check("service backend: fresh candidates, same route",
          all(s["backend"] == "http" for s in specs)
          and "no clone ladder" in specs[0]["action"])

    # defect classification from a fabricated gate report
    rep = {"gate1_nohint_language": {"pass": False},
           "gate2_ghost_words": {"pass": True, "ghosts": []},
           "gate3_pronunciation": {"pass": True, "min_prob": 0.9,
                                   "rows": []},
           "gate4_phys_swallowed": {"pass": True, "fail_words": []},
           "gate5_pitch": {"pass": True, "f0_med": 200,
                           "band": [185, 220]},
           "gate6_head_grunt": {"pass": True},
           "gate7_cut_word": {"pass": False}}
    check("defect classes read the gate report",
          repair.defect_classes(rep) == [repair.LANGUAGE, repair.CUT],
          str(repair.defect_classes(rep)))
    check("generation error class",
          repair.defect_classes(None, gen_error="boom")
          == [repair.GENERATION])

    # scoring: a clean take outscores a defective one; best_passing
    good = dict(rep, gate1_nohint_language={"pass": True},
                gate7_cut_word={"pass": True})
    s_good = repair.take_score(good, {"identity": 0.95,
                                      "pace_wps": 2.2})
    s_bad = repair.take_score(rep, {"identity": 0.86,
                                    "pace_wps": 2.45})
    check("score prefers the clean take", s_good > s_bad,
          f"{s_good} vs {s_bad}")
    pick = repair.best_passing(
        [{"ship": True, "score": 10.0, "id": "a"},
         {"ship": True, "score": 22.0, "id": "b"},
         {"ship": False, "score": 99.0, "id": "c"}])
    check("best_passing picks the best PASSING candidate only",
          pick["id"] == "b")
    check("best_passing of no passes is None",
          repair.best_passing([{"ship": False, "score": 5}]) is None)


# ------------------------------------------------------------- end-to-end --
REF_WAV = os.path.join(HERE, "voice", "telugu-reference.wav")


def _fixture():
    """(sentence, slice_bytes, truncated_bytes): the first 26 words
    of the canonical reference transcript (decimals flattened — the
    engine's sentence splitter breaks on decimal points) and the
    matching audio prefix, cut at the natural pause nearest the
    proportional point. Validated against the real ship bar: the
    slice SHIPS for this sentence (identity 0.867, pace 1.98 wps,
    gates 1/2/7 green); the 55% truncation fails gate 7 + pace."""
    import io
    import numpy as np
    import soundfile as sf
    text = open(os.path.join(HERE, "voice",
                             "telugu-reference-text.txt"),
                encoding="utf-8").read().strip()
    words = [w.replace("128.6", "128").replace("64.6", "64")
             for w in text.split()[:26]]
    sent = " ".join(words) + "."
    y, sr = sf.read(REF_WAV, dtype="float32")
    fr = int(0.02 * sr)
    n = len(y) // fr
    rms = np.array([np.sqrt(np.mean(y[i * fr:(i + 1) * fr] ** 2))
                    for i in range(n)])
    thr = 0.15 * np.median(rms[rms > 0])
    target = 26 / 32 * len(y) / sr
    gaps, i = [], 0
    while i < n:
        if rms[i] <= thr:
            j = i
            while j < n and rms[j] <= thr:
                j += 1
            if (j - i) * 0.02 >= 0.25:
                gaps.append((i + j) / 2 * 0.02)
            i = j
        else:
            i += 1
    cut = min(gaps, key=lambda g: abs(g - target))
    sl = y[:int(cut * sr)]
    buf = io.BytesIO()
    sf.write(buf, sl, sr, format="WAV")
    buf2 = io.BytesIO()
    sf.write(buf2, sl[:int(len(sl) * 0.55)], sr, format="WAV")
    return sent, buf.getvalue(), buf2.getvalue()


SENT, SLICE, TRUNC = _fixture()


def _grunt_bytes():
    """The good slice with a synthetic OmniVoice-style head grunt
    prepended (0.22 s of quiet flat 150 Hz phonation)."""
    import io
    import numpy as np
    import soundfile as sf
    y, sr = sf.read(io.BytesIO(SLICE))
    t = np.arange(int(0.22 * sr)) / sr
    grunt = (0.05 * np.sin(2 * np.pi * 150 * t)).astype("f4")
    buf = io.BytesIO()
    sf.write(buf, np.concatenate([grunt, y.astype("f4")]), sr,
             format="WAV")
    return buf.getvalue()


class ModeHandler(BaseHTTPRequestHandler):
    mode = "full"          # grunt | truncated-first | sabotage
    calls = 0
    trunc_first_n = 0

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        ModeHandler.calls += 1
        if ModeHandler.mode == "grunt":
            data = _grunt_bytes()
        elif ModeHandler.mode == "truncated-first" \
                and ModeHandler.calls <= ModeHandler.trunc_first_n:
            data = TRUNC
        elif ModeHandler.mode == "sabotage" \
                and "విఫల" in body.get("text", ""):
            data = TRUNC[:len(TRUNC) // 2]
        else:
            data = SLICE
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def _run_engine(args, env, timeout=1500):
    return subprocess.run([sys.executable,
                           os.path.join(HERE, "engine.py")] + args,
                          capture_output=True, text=True, env=env,
                          timeout=timeout)


def e2e_tests():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ModeHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    env.update({"JULIE_TTS_BACKEND": "http",
                "JULIE_TTS_URL": f"http://127.0.0.1:{port}/tts",
                "NO_PROXY": "127.0.0.1"})
    tmp = tempfile.mkdtemp(prefix="divi_repair_e2e_")
    try:
        # (a) head grunt: gen-take auto-mutes it, take ships clean
        ModeHandler.mode = "grunt"
        take = os.path.join(tmp, "grunt.wav")
        p = _run_engine(["--gen-take", "te", SENT, take], env)
        info = {}
        for line in (p.stdout or "").splitlines():
            if line.startswith("GEN_INFO "):
                info = json.loads(line[len("GEN_INFO "):])
        check("(a) grunt take generated", p.returncode == 0
              and os.path.exists(take), (p.stderr or "")[-200:])
        check("(a) grunt auto-mute recorded in GEN_INFO",
              bool(info.get("head_grunt_gate")), str(info))
        import numpy as np
        import soundfile as sf
        y, sr = sf.read(take)
        head_rms = float(np.sqrt(np.mean(y[:int(0.2 * sr)] ** 2)))
        check("(a) grunt head is silent after the mute",
              head_rms < 0.005, f"head rms {head_rms:.4f}")

        # (b) truncated endings in wave 1 -> complete take via ladder
        ModeHandler.mode = "truncated-first"
        ModeHandler.calls = 0
        ModeHandler.trunc_first_n = 2
        out = os.path.join(tmp, "ladder.mp3")
        p = _run_engine(["--text", SENT, "--lang", "te",
                         "--out", out, "--rolls", "4",
                         "--candidates", "2"], env)
        check("(b) job completes with a passing take",
              p.returncode == 0 and os.path.exists(out),
              f"rc={p.returncode} " + (p.stderr or "")[-200:])
        qc = json.load(open(os.path.splitext(out)[0] + ".qc.json"))
        sent = qc["sentences"][0]
        waves = {c["wave"] for c in sent["rolls"] if c.get("ship")}
        check("(b) winner came from a later wave (ladder worked)",
              any(w >= 2 for w in waves), str(sent["rolls"])[:300])
        check("(b) repair log records the escalation",
              len(sent.get("repairs", [])) >= 1
              and any(r.get("defects") for r in sent["repairs"]),
              str(sent.get("repairs")))

        # (c) one sabotaged sentence: job completes, other ships,
        # the failure is named, exit 2, mp3 delivered
        ModeHandler.mode = "sabotage"
        bad = "ఈ విఫల వాక్యం ఎప్పటికీ పూర్తి కాదు."
        out = os.path.join(tmp, "partial.mp3")
        p = _run_engine(["--text", SENT + " " + bad,
                         "--lang", "te", "--out", out,
                         "--rolls", "2", "--candidates", "1"], env)
        check("(c) partial job exits 2 but DELIVERS the mp3",
              p.returncode == 2 and os.path.exists(out),
              f"rc={p.returncode} exists={os.path.exists(out)}")
        qc = json.load(open(os.path.splitext(out)[0] + ".qc.json"))
        check("(c) verdict is PARTIAL and names the failed sentence",
              qc["verdict"].startswith("PARTIAL")
              and "విఫల" in qc["verdict"], qc["verdict"])
        check("(c) good sentence passed, bad one marked failed",
              qc["sentences"][0]["passed"] is True
              and qc["sentences"][1]["passed"] is False)
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS
                  else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
