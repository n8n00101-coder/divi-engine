"""Pluggable TTS generation backends for the Julie AI Voice Engine.

The built-in routes are free but slow: Telugu/Hindi ride the public
IndicF5 Hugging Face Space (long free queue, outage streaks) and English
runs Chatterbox on local CPU. If you have access to a faster model —
your own ElevenLabs voice, or any model server you run yourself — point
the engine at it and generation stops being the bottleneck. The five
gates, the re-roll loop and the QC report apply unchanged on top of
every backend: a fast backend still cannot ship a defective take.

Backend selection (env JULIE_TTS_BACKEND):

    unset            default route per language (en -> chatterbox,
                     te/hi -> indicf5-space) — the original behaviour
    indicf5-space    IndicF5 via the ai4bharat HF Space (te/hi)
    chatterbox       Chatterbox TTS local clone (en)
    elevenlabs       ElevenLabs API — needs env ELEVENLABS_API_KEY and a
                     voice id (env JULIE_EL_VOICE_ID, or
                     backends.elevenlabs.voice_id in voice/settings.json);
                     model via env JULIE_EL_MODEL (default
                     eleven_multilingual_v2)
    http             any HTTP model server — env JULIE_TTS_URL; the
                     engine POSTs JSON {"text", "lang", "voice"} and
                     expects audio bytes (mp3 or wav) back; optional env
                     JULIE_TTS_KEY is sent as "Authorization: Bearer …"
    github           NOT a synthesis backend — a stub that names the
                     free GitHub Actions route (.github/workflows/
                     voice-batch.yml): up to 10 free runners generate a
                     whole lines file in parallel with this same engine
                     in batch mode. Selecting it fails fast with the
                     dispatch instructions. See README, "Fast batch
                     mode".

Keys are read from the environment ONLY — never hardcoded, never
logged, never written to the QC report. Every failure is a fast, loud
RuntimeError whose message starts with the backend name in brackets;
HTTP backends time out at 120 s per take (no silent hangs).
"""
import os

import requests

HTTP_TIMEOUT_S = 120
BACKENDS = ("indicf5-space", "chatterbox", "elevenlabs", "http", "github")
_DEFAULTS = {"en": "chatterbox", "te": "indicf5-space", "hi": "indicf5-space"}


def resolve_backend(lang, settings=None):
    """The backend name for this language: env override, else the
    locked per-language default."""
    backend = (os.environ.get("JULIE_TTS_BACKEND") or "").strip().lower()
    if not backend:
        return _DEFAULTS[lang]
    if backend not in BACKENDS:
        raise RuntimeError(
            f"[backends] unknown JULIE_TTS_BACKEND {backend!r}; "
            f"valid values: {', '.join(BACKENDS)}")
    return backend


def _post_audio(backend, url, **kwargs):
    """POST and return audio bytes, or raise a fast named error.
    Never puts headers (which may carry a key) into the message."""
    try:
        r = requests.post(url, timeout=HTTP_TIMEOUT_S, **kwargs)
    except requests.RequestException as e:
        raise RuntimeError(f"[{backend}] request failed: {e}") from e
    if r.status_code != 200:
        raise RuntimeError(
            f"[{backend}] HTTP {r.status_code}: {r.text[:200].strip()}")
    if len(r.content) < 1000:
        raise RuntimeError(
            f"[{backend}] suspiciously small audio response "
            f"({len(r.content)} bytes)")
    return r.content


def synthesize_elevenlabs(text, lang, settings):
    """One ElevenLabs take; returns mp3 bytes. The voice comes from the
    ElevenLabs voice_id — the reference wavs are not used by this
    backend. Language follows the text/model, as on the platform."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "[elevenlabs] ELEVENLABS_API_KEY is not set — export it first "
            "(keys live in the environment only, never in this repo)")
    cfg = ((settings or {}).get("backends") or {}).get("elevenlabs") or {}
    voice_id = os.environ.get("JULIE_EL_VOICE_ID") or cfg.get("voice_id")
    if not voice_id:
        raise RuntimeError(
            "[elevenlabs] no voice id — set env JULIE_EL_VOICE_ID or "
            "backends.elevenlabs.voice_id in voice/settings.json")
    model_id = (os.environ.get("JULIE_EL_MODEL") or cfg.get("model_id")
                or "eleven_multilingual_v2")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    return _post_audio(
        "elevenlabs", url,
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
        json={"text": text, "model_id": model_id})


def synthesize_http(text, lang, settings):
    """One take from a generic HTTP model server; returns audio bytes
    (mp3 or wav — the engine's ffmpeg step normalises either)."""
    url = os.environ.get("JULIE_TTS_URL")
    if not url:
        raise RuntimeError(
            "[http] JULIE_TTS_URL is not set — point it at your model "
            "server's TTS endpoint")
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("JULIE_TTS_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    voice = (settings or {}).get("voice_name", "Julie AI")
    return _post_audio(
        "http", url, headers=headers,
        json={"text": text, "lang": lang, "voice": voice})


def synthesize(backend, text, lang, settings):
    """Dispatch for the service backends (the local routes —
    indicf5-space and chatterbox — live in engine.py)."""
    if backend == "elevenlabs":
        return synthesize_elevenlabs(text, lang, settings)
    if backend == "http":
        return synthesize_http(text, lang, settings)
    if backend == "github":
        raise RuntimeError(
            "[github] 'github' is not a synthesis backend — it names the "
            "free GitHub Actions route: put your lines in a file in this "
            "repo, then dispatch .github/workflows/voice-batch.yml "
            "(gh workflow run voice-batch.yml -f lines_path=lines.txt "
            "-f lang=en -f chunks=10) and download the "
            "julie-voice-batch-all artifact. See README, 'Fast batch mode'.")
    raise RuntimeError(f"[backends] {backend!r} is not a service backend")
