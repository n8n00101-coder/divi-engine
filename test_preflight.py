"""Divi Engine — script pre-flight tests (owner's order, 2026-11-16
20:28 IST + Hindi parity emphasis 20:31 IST).

Planted-flaw scripts per correction class and per language; a clean
script must pass through BYTE-IDENTICAL with an empty corrections
log; and an end-to-end run must prove the generation stage consumed
ONLY the corrected script (the stub server records what it was sent).
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
import preflight  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          ((" — " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


def classes(res):
    return [c["class"] for c in res["corrections"]]


# ------------------------------------------------------------ unit tests --
def unit_tests():
    # EN typo (known misspellings map — never-correct forms only)
    r = preflight.preflight_text(
        "The results will definately seperate the groups.", "en")
    check("en typo corrected", "definitely separate" in r["text"],
          r["text"])
    check("en typo logged", classes(r).count("typo") == 2,
          str(r["corrections"]))

    # EN spelled percent -> symbol; year digits untouched
    r = preflight.preflight_text("Sales grew by 50 percent in 2024.",
                                 "en")
    check("en percent -> symbol", r["text"] ==
          "Sales grew by 50% in 2024.", r["text"])
    check("en percent logged as format", "format" in classes(r))

    # EN clean text is NOT corrupted by the typo pass (regression:
    # a corpus-sized lexicon once 'corrected' Sales->Safes)
    clean_en = "Sales grew steadily while detailed reviews continued."
    r = preflight.preflight_text(clean_en, "en")
    check("en clean sentence byte-identical", r["text"] == clean_en,
          r["text"])
    check("en clean sentence: no corrections", r["corrections"] == [])

    # EN duplicated line removed + logged
    r = preflight.preflight_text("Hello world.\nHello world.", "en")
    check("en duplicate removed", r["text"] == "Hello world.",
          r["text"])
    check("en duplicate logged", "duplicate" in classes(r))

    # EN missing terminator supplied
    r = preflight.preflight_text("This line has no terminator", "en")
    check("en terminator supplied",
          r["text"] == "This line has no terminator.", r["text"])

    # EN markdown / emoji stripped
    r = preflight.preflight_text("**Bold** claim 🎉 today.", "en")
    check("en markdown+emoji stripped", r["text"] == "Bold claim today.",
          r["text"])

    # EN over-long sentence split at a clause boundary
    long_en = ("The committee reviewed the long report in the morning "
               "session, and every member asked detailed questions "
               "about the findings, the methods, the costs, the "
               "timelines, and the risks before the final vote was "
               "taken by the chair.")
    r = preflight.preflight_text(long_en, "en")
    check("en over-long split", "sentence_shape" in classes(r)
          and r["text"].count(".") >= 2
          and "morning session." in r["text"], r["text"])

    # TE banned English connective -> Telugu (english-mix policy)
    r = preflight.preflight_text("అతను వచ్చాడు and ఆమె వెళ్ళింది.", "te")
    check("te connective corrected",
          r["text"] == "అతను వచ్చాడు మరియు ఆమె వెళ్ళింది.", r["text"])
    check("te connective class english_mix",
          "english_mix" in classes(r))

    # TE spelled percent (శాతం after a number) -> symbol
    r = preflight.preflight_text("వృద్ధి 50 శాతం నమోదైంది.", "te")
    check("te percent -> symbol", "50%" in r["text"], r["text"])

    # TE third-language word WITH a clear equivalent -> corrected
    r = preflight.preflight_text("అతను వచ్చాడు और ఆమె వెళ్ళింది.", "te")
    check("te purity corrected",
          "మరియు" in r["text"] and "और" not in r["text"], r["text"])
    check("te purity class", "purity" in classes(r))

    # TE third-language word WITHOUT an equivalent -> flagged, kept
    r = preflight.preflight_text("అతను कल వచ్చాడు.", "te")
    check("te purity flagged not rewritten",
          "कल" in r["text"]
          and any(f["class"] == "purity" for f in r["flags"]),
          str(r))

    # TE unattested English word with clear equivalent -> converted
    r = preflight.preflight_text("అతను water తాగాడు.", "te")
    check("te unattested word converted", "నీరు" in r["text"],
          r["text"])

    # TE banned pronoun -> flagged at top, never rewritten
    r = preflight.preflight_text("you చెప్పావు.", "te")
    check("te pronoun flagged not rewritten",
          r["text"].startswith("you")
          and any(f["word"] == "you" for f in r["flags"]), str(r))

    # HI planted flaws (parity case): spelled percent + connective
    r = preflight.preflight_text("बिक्री 50 प्रतिशत बढ़ी।", "hi")
    check("hi percent -> symbol", "50%" in r["text"], r["text"])
    check("hi percent logged", "format" in classes(r))
    r = preflight.preflight_text("वह आया and वह गई।", "hi")
    check("hi connective corrected",
          r["text"] == "वह आया और वह गई।", r["text"])
    check("hi connective logged", len(r["corrections"]) == 1,
          str(r["corrections"]))
    # HI clean line byte-identical
    hi_clean = open(os.path.join(HERE, "jobs", "fixed14-lines-hi.txt"),
                    encoding="utf-8").read().strip().splitlines()[0]
    r = preflight.preflight_text(hi_clean, "hi")
    check("hi clean line byte-identical", r["text"] == hi_clean,
          r["text"])
    check("hi clean line: no corrections", r["corrections"] == [],
          str(r["corrections"]))

    # TE clean line byte-identical
    te_clean = "వాతావరణం ఈ రోజు చాలా బాగుంది."
    r = preflight.preflight_text(te_clean, "te")
    check("te clean line byte-identical", r["text"] == te_clean
          and r["corrections"] == [], str(r))

    # Batch lines: duplicates removed, indices renumber over the
    # corrected set (engine-side), corrections logged
    r = preflight.preflight_lines(
        ["First line.", "First line.", "Second line"], "en")
    check("batch dup line removed",
          r["lines"] == ["First line.", "Second line."], str(r["lines"]))
    check("batch missing terminator supplied",
          r["lines"][1] == "Second line.")


# ------------------------------------------------------------- end-to-end --
class StubHandler(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        StubHandler.seen.append(json.loads(body.decode("utf-8")))
        ref = os.path.join(HERE, "voice", "english-reference.wav")
        data = open(ref, "rb").read()
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
    tmp = tempfile.mkdtemp(prefix="divi_preflight_e2e_")
    try:
        out = os.path.join(tmp, "line.mp3")
        p = subprocess.run(
            [sys.executable, os.path.join(HERE, "engine.py"),
             "--text", "Sales grew by 50 percent in 2024.",
             "--lang", "en", "--out", out, "--rolls", "1",
             "--candidates", "1"],
            capture_output=True, text=True, env=env, timeout=900)
        check("engine run completes (0 or honest 2)",
              p.returncode in (0, 2),
              f"rc={p.returncode} " + (p.stderr or "")[-300:])
        sent = " ".join(s.get("text", "") for s in StubHandler.seen)
        check("generation consumed ONLY the corrected script",
              "50%" in sent and "percent" not in sent, sent)
        corrected = os.path.join(tmp, "script.corrected.txt")
        check("script.corrected.txt saved beside the output",
              os.path.exists(corrected)
              and "50%" in open(corrected).read())
        qc_path = os.path.splitext(out)[0] + ".qc.json"
        if os.path.exists(qc_path):
            qc = json.load(open(qc_path))
            check("QC carries the Script Corrections log",
                  any(c["class"] == "format"
                      for c in qc.get("script_corrections", [])),
                  str(qc.get("script_corrections")))
            check("QC carries script_flags", "script_flags" in qc)
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS
                  else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
