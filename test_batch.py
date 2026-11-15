#!/usr/bin/env python3
"""Offline tests for batch mode (engine.py --batch / --batch-gen).

No real TTS model runs: generation is stubbed through the http backend
(a local server returns the Telugu reference wav for every line), the
same trick as test_backends.py. The gates DO run on the stub takes, so
whether an individual line passes is the gates' business — these tests
assert batch structure and bookkeeping:

  1. Line parsing (blanks skipped, --first-index numbering), round-robin
     chunk splitting, output naming.
  2. CLI contract: --batch requires --lang and --outdir.
  3. The 'github' backend stub resolves and fails fast with dispatch
     instructions (it is a route name, not a synthesizer).
  4. --batch-gen worker: ONE process generates a whole manifest and
     reports per-item results.
  5. Full --batch run with --jobs 2: batch.qc.json shape, per-line
     rolls/timings, exactly one worker (model load) per chunk, and an
     mp3 on disk for every line the gates chose.

Run: python3 test_batch.py   (exit 0 = all pass)
The end-to-end parts load the local faster-whisper model once (the
gates), so they take a minute or two on CPU.
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

import backends  # noqa: E402
import engine  # noqa: E402

REF_WAV = os.path.join(HERE, "voice", "telugu-reference.wav")
REF_BYTES = open(REF_WAV, "rb").read()
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


class Env:
    """Temporarily set/unset env vars (restored on exit)."""

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kw}
        for k, v in self.kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---------------------------------------------------------------- unit ---
def unit_tests():
    tmp = tempfile.mkdtemp(prefix="julie_batch_unit_")
    lines_file = os.path.join(tmp, "lines.txt")
    with open(lines_file, "w") as fh:
        fh.write("First line.\n\n   \nSecond line.\n  Third line.  \n")
    lines = engine.read_batch_lines(lines_file)
    check("blank rows skipped", [l["text"] for l in lines] ==
          ["First line.", "Second line.", "Third line."])
    check("default numbering from 1", [l["index"] for l in lines] == [1, 2, 3])
    lines = engine.read_batch_lines(lines_file, first_index=21)
    check("first_index offsets numbering",
          [l["index"] for l in lines] == [21, 22, 23])

    items = list(range(10))
    chunks = engine.split_round_robin(items, 3)
    check("round-robin chunk sizes", [len(c) for c in chunks] == [4, 3, 3])
    check("round-robin covers every item once",
          sorted(x for c in chunks for x in c) == items)
    check("round-robin spreads consecutive items",
          chunks[0] == [0, 3, 6, 9] and chunks[1] == [1, 4, 7])
    check("jobs > items clamps", len(engine.split_round_robin([1, 2], 8)) == 2)
    check("jobs=1 single chunk", engine.split_round_robin(items, 1) == [items])
    check("empty items -> no chunks", engine.split_round_robin([], 4) == [])

    check("line names zero-padded", engine.batch_line_name(7) == "007.mp3"
          and engine.batch_line_name(209) == "209.mp3")

    # CLI contract
    p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                        "--batch", lines_file, "--lang", "en"],
                       capture_output=True, text=True)
    check("--batch without --outdir is an error", p.returncode == 2)
    p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                        "--help"], capture_output=True, text=True)
    check("--help documents batch mode",
          "--batch" in p.stdout and "--rerolls" in p.stdout)

    # github backend stub
    with Env(JULIE_TTS_BACKEND="github"):
        check("github backend resolves", backends.resolve_backend("en") == "github")
    try:
        backends.synthesize("github", "x", "en", {})
        check("github synthesize raises", False)
    except RuntimeError as e:
        check("github synthesize raises named instructions",
              str(e).startswith("[github]") and "voice-batch.yml" in str(e))


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
    env = stub_env(port)
    tmp = tempfile.mkdtemp(prefix="julie_batch_e2e_")
    try:
        # --batch-gen worker: one process, whole manifest
        items = []
        for i in (1, 2):
            items.append({"index": i, "roll": 1, "text": "పరీక్ష వాక్యం",
                          "out": os.path.join(tmp, f"w{i}.wav")})
        man_in = os.path.join(tmp, "man.in.json")
        man_out = os.path.join(tmp, "man.out.json")
        with open(man_in, "w") as fh:
            json.dump({"lang": "te", "items": items}, fh, ensure_ascii=False)
        p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                            "--batch-gen", man_in, man_out],
                           capture_output=True, text=True, env=env, timeout=300)
        check("batch-gen worker exits 0", p.returncode == 0,
              (p.stderr or "")[-300:])
        out = json.load(open(man_out))
        check("worker reports the backend", out.get("backend") == "http")
        check("worker reports every item",
              len(out["results"]) == 2 and all(r["ok"] for r in out["results"]))
        check("worker results carry gen timing",
              all(isinstance(r.get("gen_s"), (int, float)) for r in out["results"]))
        import soundfile as sf
        y, sr = sf.read(items[0]["out"])
        check("worker takes normalised to 24 kHz mono", sr == 24000 and y.ndim == 1)

        # full batch run: 4 lines, 2 jobs, no re-rolls
        lines_file = os.path.join(tmp, "lines.txt")
        with open(lines_file, "w") as fh:
            fh.write("\n".join(["పరీక్ష వాక్యం ఒకటి.", "పరీక్ష వాక్యం రెండు.",
                                "పరీక్ష వాక్యం మూడు.", "పరీక్ష వాక్యం నాలుగు."]) + "\n")
        outdir = os.path.join(tmp, "out")
        p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                            "--batch", lines_file, "--lang", "te",
                            "--outdir", outdir, "--jobs", "2", "--rerolls", "0"],
                           capture_output=True, text=True, env=env, timeout=1200)
        check("batch run exits 0 (all pass) or 2 (honest partial)",
              p.returncode in (0, 2), f"rc={p.returncode} " + (p.stderr or "")[-300:])
        qc_path = os.path.join(outdir, "batch.qc.json")
        check("batch.qc.json written", os.path.exists(qc_path))
        if os.path.exists(qc_path):
            qc = json.load(open(qc_path))
            check("QC mode is batch", qc.get("mode") == "batch")
            check("QC records backend + jobs",
                  qc.get("backend") == "http" and qc.get("jobs") == 2)
            check("QC has one entry per line", len(qc["lines"]) == 4)
            check("QC per-line exactly one roll (rerolls=0)",
                  all(len(l["rolls"]) == 1 for l in qc["lines"]))
            check("QC per-roll carries gen timing",
                  all(isinstance(l["rolls"][0].get("gen_s"), (int, float))
                      for l in qc["lines"]))
            check("one model load per chunk (2 chunks, 1 round)",
                  qc["timings"]["model_loads"] == 2)
            check("QC timings carry wall time",
                  isinstance(qc["timings"].get("wall_s"), (int, float)))
            for line in qc["lines"]:
                if line["chosen_roll"] is not None:
                    check(f"line {line['index']} mp3 on disk",
                          os.path.exists(os.path.join(
                              outdir, engine.batch_line_name(line["index"]))))
            passed = sum(1 for l in qc["lines"] if l["chosen_roll"] is not None)
            check("exit code matches QC verdict",
                  (p.returncode == 0) == (passed == 4))
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
