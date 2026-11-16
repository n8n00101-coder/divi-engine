#!/usr/bin/env python3
"""Offline tests for the pluggable TTS backends (backends.py).

No real API calls and no Space/Chatterbox generation anywhere:
  1. elevenlabs + http request shaping with requests.post stubbed
     (URL, auth header, JSON body, default + overridden model).
  2. Fast-fail errors: missing key / url / voice id, unknown backend —
     each message names its backend, and no key value ever leaks.
  3. End-to-end routing: a local stub HTTP server returns the Telugu
     reference wav; `engine.py --gen-take` must route through the http
     backend and name it in GEN_INFO, and a full engine run must still
     write its QC json with the backend recorded per take and overall.

Run: python3 test_backends.py   (exit 0 = all pass)
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

import backends  # noqa: E402

REF_WAV = os.path.join(HERE, "voice", "telugu-reference.wav")
SETTINGS = json.load(open(os.path.join(HERE, "voice", "settings.json")))
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


class FakeResp:
    def __init__(self, status=200, content=b"", text=""):
        self.status_code = status
        self.content = content
        self.text = text


def stub_post(resp):
    calls = []

    def fake(url, **kw):
        calls.append({"url": url, **kw})
        return resp

    return fake, calls


REF_BYTES = open(REF_WAV, "rb").read()

# ---------------------------------------------------------------- unit ---
def unit_tests():
    orig_post = backends.requests.post
    try:
        # elevenlabs happy path
        fake, calls = stub_post(FakeResp(200, REF_BYTES))
        backends.requests.post = fake
        with Env(ELEVENLABS_API_KEY="sk-test-not-a-real-key",
                 JULIE_EL_VOICE_ID="voice123", JULIE_EL_MODEL=None):
            audio = backends.synthesize_elevenlabs("Hello there.", "en", SETTINGS)
        c = calls[0]
        check("elevenlabs returns audio bytes", audio == REF_BYTES)
        check("elevenlabs URL carries voice id",
              c["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voice123")
        check("elevenlabs xi-api-key header from env",
              c["headers"]["xi-api-key"] == "sk-test-not-a-real-key")
        check("elevenlabs default model",
              c["json"]["model_id"] == "eleven_multilingual_v2")
        check("elevenlabs body text", c["json"]["text"] == "Hello there.")
        with Env(ELEVENLABS_API_KEY="k", JULIE_EL_VOICE_ID="v",
                 JULIE_EL_MODEL="eleven_v3"):
            backends.synthesize_elevenlabs("x", "te", SETTINGS)
        check("elevenlabs JULIE_EL_MODEL override",
              calls[-1]["json"]["model_id"] == "eleven_v3")
        # voice id from settings.json when env unset
        st = json.loads(json.dumps(SETTINGS))
        st["backends"]["elevenlabs"]["voice_id"] = "settingsvoice"
        with Env(ELEVENLABS_API_KEY="k", JULIE_EL_VOICE_ID=None):
            backends.synthesize_elevenlabs("x", "hi", st)
        check("elevenlabs voice id falls back to settings.json",
              calls[-1]["url"].endswith("/settingsvoice"))

        # elevenlabs HTTP error names the backend, leaks no key
        backends.requests.post = stub_post(FakeResp(401, b"", "unauthorised"))[0]
        try:
            with Env(ELEVENLABS_API_KEY="sk-secret-value", JULIE_EL_VOICE_ID="v"):
                backends.synthesize_elevenlabs("x", "en", SETTINGS)
            check("elevenlabs 401 raises", False)
        except RuntimeError as e:
            check("elevenlabs 401 raises named error",
                  str(e).startswith("[elevenlabs]") and "401" in str(e))
            check("elevenlabs error leaks no key", "sk-secret-value" not in str(e))

        # http happy path: body shape + bearer header
        fake, calls = stub_post(FakeResp(200, REF_BYTES))
        backends.requests.post = fake
        with Env(JULIE_TTS_URL="http://127.0.0.1:9/tts", JULIE_TTS_KEY="tok123"):
            audio = backends.synthesize_http("Test line", "te", SETTINGS)
        c = calls[0]
        check("http returns audio bytes", audio == REF_BYTES)
        check("http JSON body {text, lang, voice}",
              c["json"] == {"text": "Test line", "lang": "te", "voice": "Julie AI"})
        check("http bearer header from JULIE_TTS_KEY",
              c["headers"]["Authorization"] == "Bearer tok123")
        check("http timeout is 120 s", c["timeout"] == 120)
        with Env(JULIE_TTS_URL="http://x/tts", JULIE_TTS_KEY=None):
            backends.synthesize_http("y", "hi", SETTINGS)
        check("http no key -> no Authorization header",
              "Authorization" not in calls[-1]["headers"])
    finally:
        backends.requests.post = orig_post

    # fast-fail configuration errors
    for name, fn, env, prefix in [
        ("elevenlabs missing key", backends.synthesize_elevenlabs,
         {"ELEVENLABS_API_KEY": None, "JULIE_EL_VOICE_ID": "v"}, "[elevenlabs]"),
        ("elevenlabs missing voice id", backends.synthesize_elevenlabs,
         {"ELEVENLABS_API_KEY": "k", "JULIE_EL_VOICE_ID": None}, "[elevenlabs]"),
        ("http missing url", backends.synthesize_http,
         {"JULIE_TTS_URL": None}, "[http]"),
    ]:
        try:
            with Env(**env):
                fn("x", "en", SETTINGS)
            check(name + " raises", False)
        except RuntimeError as e:
            check(name + " raises named fast-fail", str(e).startswith(prefix))

    # backend resolution
    with Env(JULIE_TTS_BACKEND=None):
        check("default backend en", backends.resolve_backend("en") == "chatterbox")
        check("default backend te", backends.resolve_backend("te") == "indicf5-space")
        check("default backend hi", backends.resolve_backend("hi") == "indicf5-space")
    with Env(JULIE_TTS_BACKEND="http"):
        check("env override wins", backends.resolve_backend("en") == "http")
    try:
        with Env(JULIE_TTS_BACKEND="bogus"):
            backends.resolve_backend("en")
        check("unknown backend raises", False)
    except RuntimeError as e:
        check("unknown backend raises", "bogus" in str(e))

    # mms routing (merged 2026-11-16): selectable for te via the env,
    # the English default stays the locked chatterbox route, the
    # service dispatcher refuses mms by name (it is a local route),
    # and the engine refuses mms for non-Telugu languages.
    with Env(JULIE_TTS_BACKEND="mms"):
        check("mms selectable for te", backends.resolve_backend("te") == "mms")
    with Env(JULIE_TTS_BACKEND=None):
        check("en default still chatterbox (mms merge untouched)",
              backends.resolve_backend("en") == "chatterbox")
    try:
        backends.synthesize("mms", "x", "te", SETTINGS)
        check("mms service dispatch raises", False)
    except RuntimeError as e:
        check("mms service dispatch raises named error",
              str(e).startswith("[mms]"))
    import engine as _engine
    try:
        _engine._gen_take_core("mms", "en", "Hello.",
                               os.path.join(tempfile.gettempdir(),
                                            "mms_route_probe.wav"),
                               SETTINGS)
        check("mms refuses en in engine routing", False)
    except RuntimeError as e:
        check("mms refuses en in engine routing",
              str(e).startswith("[mms]"))


# ------------------------------------------------------------- end-to-end --
class StubHandler(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        StubHandler.seen.append(
            {"path": self.path, "json": json.loads(body or b"{}"),
             "auth": self.headers.get("Authorization")})
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(REF_BYTES)))
        self.end_headers()
        self.wfile.write(REF_BYTES)

    def log_message(self, *a):
        pass


def e2e_tests():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
    env.update({"JULIE_TTS_BACKEND": "http",
                "JULIE_TTS_URL": f"http://127.0.0.1:{port}/tts",
                "JULIE_TTS_KEY": "e2e-token", "NO_PROXY": "127.0.0.1"})
    tmp = tempfile.mkdtemp(prefix="julie_backend_test_")
    try:
        take = os.path.join(tmp, "take.wav")
        p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                            "--gen-take", "te", "పరీక్ష వాక్యం", take],
                           capture_output=True, text=True, env=env, timeout=300)
        check("gen-take via http exits 0", p.returncode == 0,
              (p.stderr or "")[-300:])
        info = {}
        for line in (p.stdout or "").splitlines():
            if line.startswith("GEN_INFO "):
                info = json.loads(line[len("GEN_INFO "):])
        check("GEN_INFO names the http backend", info.get("backend") == "http")
        import soundfile as sf
        y, sr = sf.read(take)
        check("take normalised to 24 kHz mono", sr == 24000 and y.ndim == 1)
        seen = StubHandler.seen[-1]
        check("stub server got {text, lang, voice}",
              seen["json"].get("lang") == "te" and "text" in seen["json"]
              and "voice" in seen["json"])
        check("stub server got bearer token", seen["auth"] == "Bearer e2e-token")

        out = os.path.join(tmp, "line.mp3")
        p = subprocess.run([sys.executable, os.path.join(HERE, "engine.py"),
                            "--text", "పరీక్ష వాక్యం.", "--lang", "te",
                            "--out", out, "--rolls", "1"],
                           capture_output=True, text=True, env=env, timeout=900)
        check("full run exits 0 or honest 2", p.returncode in (0, 2),
              f"rc={p.returncode} " + (p.stderr or "")[-300:])
        qc_path = os.path.splitext(out)[0] + ".qc.json"
        check("QC json written", os.path.exists(qc_path))
        if os.path.exists(qc_path):
            qc = json.load(open(qc_path))
            check("QC records backend overall", qc.get("backend") == "http")
            roll = qc["sentences"][0]["rolls"][0]
            check("QC records backend per take", roll.get("backend") == "http")
            check("QC per-take backend matches GEN_INFO",
                  (roll.get("gen") or {}).get("backend", "http") == "http")
    finally:
        server.shutdown()


if __name__ == "__main__":
    unit_tests()
    e2e_tests()
    print("\n" + ("ALL PASS" if not FAILS else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
