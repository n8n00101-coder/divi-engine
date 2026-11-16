#!/usr/bin/env python3
"""Divi Engine — gated voice-clone generation for the Julie AI house voice.

    python3 engine.py --text "…" --lang te --out line.mp3
    python3 engine.py --text-file script.txt --lang en --out out.mp3 --bed
    python3 engine.py --batch lines.txt --lang en --outdir out/ --jobs 4
    python3 divi.py --text-file script.txt --lang te --out out.mp3 --cloud

SPEED LAW (owner's order, 2026-11-16): the tool NEVER adjusts speed
on its own. By default every run uses exactly the locked recipes
(voice/settings.json + the locked routes). The only legal tempo
changes are a locked recipe value (Hindi's +20%, part of its voice
definition) and an explicit user --speed for that job; the QC report
states the speed source (LOCKED or USER-REQUESTED) on every run.
speedpolicy.py is the single implementation. The English pace guard
no longer stretches a slow take with atempo — an out-of-band take is
rejected and re-rolled.

FINAL VERIFICATION: every assembled mp3 is verified as a file
(verify.py — completeness, language, head grunt, cut word, gaps,
levels, duration, identity spot check) before the run may call
itself a PASS; a failed verification removes the mp3 and exits 2.

BATCH MODE (--batch): one line per row in the lines file. The old path
reloads the TTS model and re-computes the reference conditioning for
EVERY take (a subprocess per take); batch mode loads the model once per
worker process, computes the conditioning once, and generates every
line in-process. --jobs N runs N such workers in parallel. Lines that
fail the gates are re-rolled in place (default --rerolls 2), never the
whole file. Each passing line is written to <outdir>/<nnn>.mp3 and a
batch.qc.json records per-line rolls, gate results and timings. See
README, "Fast batch mode".

For every sentence the engine generates a take, runs ALL FIVE GATES on it
(gates.py), and automatically re-rolls (up to --rolls, default 6) when any
gate fails. Only takes that pass every gate are assembled. If a sentence
never passes, the engine exits non-zero, writes the QC report with the full
gate table, and writes NO final mp3. That loop is the permanent fix: the
defects the gates name (mispronunciation, swallowed words, foreign ghost
words, pitch drift, level jumps) cannot be shipped by this tool.

WHOLE-TAKE ONLY for Telugu/Hindi (Ajju's order, 2026-11-16): te/hi
sentences are generated as WHOLE takes and ship only from a single take
that passes the five gates PLUS speaker identity (>= 0.85 vs the English
reference) PLUS the pace band. Clause/donor assembly and every
splice-inside-a-sentence edit are hard-disabled for te/hi — the patchwork
builds (fixed2/fixed3/fixed5) were rejected by the owner's ear on
2026-11-15 precisely because every splice is heard as a cut and every
regenerated segment carries a different identity. Large te/hi roll
budgets dispatch to the indicf5-batch.yml mass-roll workflow instead of
rolling locally (see dispatch_mass_rolls).

Generation routes (locked, see voice/settings.json):
  en  Chatterbox TTS zero-shot clone, exaggeration 0.35, phrase chunking,
      pace guard (regen once, then the take is REJECTED and re-rolled —
      never atempo; speed law, 2026-11-16).
  te  IndicF5 (ai4bharat HF Space) from the Telugu reference. No atempo —
      pace is fixed by take selection.
  hi  IndicF5 cross-lingual from the Telugu reference, with the owner's
      approved +20% pace calibration: ONE atempo 1.20 per take — a
      locked recipe value (the voice's definition), logged as LOCKED.

Pluggable backends (backends.py): env JULIE_TTS_BACKEND overrides the
route above for any language — "mms" (Meta MMS-TTS, native-diction
Telugu, local model — the second engine merged into this tool on
2026-11-16 alongside the locked Chatterbox English route),
"omnivoice" (OmniVoice zero-shot clone via the official k2-fsa HF
Space, Telugu, LOCKED settings — canonical natspan2 reference, speed
1.0 exactly, NO speed correction ever; added 2026-11-16 after the
owner's ear approved it over the earlier routes; weights CC-BY-NC,
see README), "elevenlabs" (your ElevenLabs voice,
key from env ELEVENLABS_API_KEY) or "http" (any model server you run,
env JULIE_TTS_URL). The gates, re-roll loop and QC report are unchanged
on top of every backend; each take's backend is recorded in the QC
report. See README, "Connect your own model (fast path)".

Every generated take, on EVERY backend, passes the gate-6 head-grunt
auto-mute (acoustic_gates.py) before gating: the OmniVoice route
prepends a short quiet flat low grunt to nearly every sentence, and
the mute — non-word phonation sitting in silence, muted in place —
is recorded per roll in the QC report. Gate 7 (cut word) runs inside
gates.run_all_gates and is a hard ship condition in ship_decision:
a take whose ending is truncated ships nothing.

Each take is synthesized in a subprocess (this file, --gen-take) so the
network environment the Space needs (proxy env intact) never contaminates
the local-ASR gate process (which strips proxies — a proxy breaks local
model loads).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backends  # noqa: E402  (pluggable TTS backends; see backends.py)
import speedpolicy  # noqa: E402  (the speed law: LOCKED or USER-REQUESTED)

VOICE_DIR = os.path.join(HERE, "voice")
EN_REF = os.path.join(VOICE_DIR, "english-reference.wav")
TE_REF = os.path.join(VOICE_DIR, "telugu-reference.wav")
TE_REF_TEXT = os.path.join(VOICE_DIR, "telugu-reference-text.txt")
SR = 24000


def load_settings():
    with open(os.path.join(VOICE_DIR, "settings.json")) as fh:
        return json.load(fh)


# =========================================================================
# Take generation (subprocess mode — network env untouched)
# =========================================================================
INDICF5_BASE = "https://ai4bharat-indicf5.hf.space"


def _indicf5_synthesize(text, ref_wav, ref_text):
    """One IndicF5 generation; returns raw audio bytes. Retries Space
    errors with backoff — ZeroGPU outages come in streaks."""
    import requests
    s = requests.Session()
    fd = None

    def upload():
        with open(ref_wav, "rb") as f:
            up = s.post(INDICF5_BASE + "/gradio_api/upload",
                        files={"files": (os.path.basename(ref_wav), f, "audio/wav")},
                        timeout=180)
        return {"path": up.json()[0], "orig_name": os.path.basename(ref_wav),
                "mime_type": "audio/wav", "meta": {"_type": "gradio.FileData"}}

    fd = upload()
    last = None
    for attempt in range(3):
        try:
            r = s.post(INDICF5_BASE + "/gradio_api/call/synthesize_speech",
                       json={"data": [text, fd, ref_text]}, timeout=180)
            eid = r.json()["event_id"]
            with s.get(INDICF5_BASE + f"/gradio_api/call/synthesize_speech/{eid}",
                       stream=True, timeout=1200) as resp:
                buf = ""
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    buf += chunk
            if "event: error" in buf and "event: complete" not in buf:
                raise RuntimeError("space error event")
            m = re.findall(r"event: complete\ndata: (.*)", buf)
            if not m:
                raise RuntimeError("no complete event: " + buf[-150:])
            out = json.loads(m[-1])[0]
            audio = s.get(INDICF5_BASE + "/gradio_api/file=" + out["path"],
                          timeout=180).content
            if len(audio) < 5000:
                raise RuntimeError(f"tiny output {len(audio)}b")
            return audio
        except Exception as e:  # Space flakiness is routine; retry
            last = e
            if attempt < 2:
                time.sleep(45)
                try:
                    fd = upload()
                except Exception:
                    pass
    raise RuntimeError(f"[indicf5-space] IndicF5 failed after retries: {last}")


WHOLE_TAKE_LANGS = ("te", "hi")


def forbid_inside_sentence_edit(lang, op):
    """Hard guard: no splice-inside-a-sentence operation may ever run on
    a Telugu/Hindi take. Patchwork assembly was rejected by the owner's
    ear three times on 2026-11-15 (fixed2, fixed3, fixed5): every splice
    is a discontinuity a native ear hears as a cut, and regenerated
    segments carry a different voice identity. te/hi sentences ship from
    ONE whole take or not at all."""
    if lang in WHOLE_TAKE_LANGS:
        raise RuntimeError(
            f"[whole-take] {op} is forbidden for lang={lang!r}: Telugu/Hindi "
            "sentences ship from one whole take only — no clause/donor "
            "assembly, no splice inside a sentence (owner's order, "
            "2026-11-16, after the 2026-11-15 ear rejections).")


def _squash_gaps_np(y, sr, max_gap=0.35, keep=0.12, thr_db=-45.0, lang=None):
    """Cut silences longer than max_gap INSIDE a phrase down to `keep`.
    (The clone invents mid-phrase pauses; her delivery flows through.)
    English-only in practice (the Chatterbox session); the lang guard
    makes the te/hi ban structural, not conventional."""
    forbid_inside_sentence_edit(lang, "_squash_gaps_np")
    import numpy as np
    hop = 256
    n = len(y) // hop
    if n == 0:
        return y
    fr = y[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    silent = db <= thr_db
    out = []
    i = 0
    while i < n:
        if silent[i]:
            j = i
            while j < n and silent[j]:
                j += 1
            run_s = (j - i) * hop / sr
            if run_s > max_gap and i > 0 and j < n:  # interior only
                out.append(y[i * hop:(i + int(keep * sr / hop)) * hop])
            else:
                out.append(y[i * hop:j * hop])
            i = j
        else:
            out.append(y[i * hop:(i + 1) * hop])
            i += 1
    import numpy as np
    return np.concatenate(out) if out else y


def _onset_rate(y, sr):
    import librosa
    import numpy as np
    env = librosa.onset.onset_strength(y=y.astype("float32"), sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=env, sr=sr, units="time")
    dur = len(y) / sr
    return (len(onsets) / dur) if dur > 0 else 0.0


class PaceBandReject(RuntimeError):
    """An English take whose onset rate stays outside the locked pace
    band after its one regeneration. Under the speed law the take is
    REJECTED (the caller's re-roll loop makes another) — the pre-law
    pace guard stretched it with atempo instead, a silent speed change
    the owner abolished on 2026-11-16."""


class _ChatterboxSession:
    """One loaded Chatterbox model with the reference conditioning
    computed ONCE and reused for every line (batch mode). The per-line
    recipe — phrase chunking, gap squash, pace guard — is the locked
    one; only the load-once lifecycle is new. The old per-take path
    rebuilt all of this for every single take."""

    def __init__(self, ref_wav, settings):
        import soundfile as sf
        import torch
        from chatterbox.tts import ChatterboxTTS

        self.settings = settings
        self.cfg = settings["english_chatterbox"]
        self.ref_wav = ref_wav
        torch.set_num_threads(max(1, int(os.environ.get("JULIE_CLONE_THREADS", "2"))))
        self.model = ChatterboxTTS.from_pretrained(device="cpu")
        self.has_prepare = hasattr(self.model, "prepare_conditionals")
        if self.has_prepare:
            self.model.prepare_conditionals(ref_wav)
        ref_y, _ = sf.read(ref_wav, dtype="float32", always_2d=False)
        if ref_y.ndim > 1:
            ref_y = ref_y[:, 0]
        self.ref_rate = _onset_rate(ref_y.astype("float32"), SR)

    def _gen_unit(self, unit):
        import numpy as np
        kw = {"exaggeration": self.cfg["exaggeration"],
              "cfg_weight": self.cfg["cfg_weight"]}
        if self.has_prepare:
            wav = self.model.generate(unit, **kw)
        else:
            wav = self.model.generate(unit, audio_prompt_path=self.ref_wav, **kw)
        data = wav.detach().cpu().float().numpy()
        return (data[0] if data.ndim == 2 else data).astype(np.float32)

    def generate(self, text, out_wav, seed=None):
        """English clone take: phrase chunking + pace guard (locked recipe).
        `seed` (repair ladder only) reseeds torch before generation so
        best-of-N candidates are distinct samples of the SAME locked
        recipe — seed is the one variation the self-healing loop is
        allowed; recipe values never change."""
        import numpy as np
        import soundfile as sf
        import torch

        if seed is not None:
            torch.manual_seed(int(seed))
        cfg = self.cfg
        join = cfg["phrase_chunking"]["comma_gap_s"]
        # phrase chunking: units end at commas/semicolons/colons (0.06 s joins)
        units = [u.strip() for u in re.split(r"(?<=[,;:])\s*", text) if u.strip()]
        if not units:
            units = [text]

        def synth_all():
            parts = []
            for ui, unit in enumerate(units):
                y = self._gen_unit(unit)
                # English clone only — this session cannot serve te/hi
                # (_gen_take_core refuses), and the guard proves it.
                y = _squash_gaps_np(y, SR, lang="en")
                parts.append(y)
                if ui < len(units) - 1:
                    parts.append(np.zeros(int(join * SR), dtype=np.float32))
            return np.concatenate(parts)

        ref_rate = self.ref_rate
        pace = {"action": "none", "ref_rate": round(ref_rate, 2)}
        y = synth_all()
        rate = _onset_rate(y, SR)
        pace["rate"] = round(rate, 2)
        band = cfg["pace_guard"]["band_frac"]
        decision = speedpolicy.pace_guard_decision(rate, ref_rate, band)
        if decision == "regen":
            y = synth_all()  # ONE regeneration (a new take, not a stretch)
            rate = _onset_rate(y, SR)
            pace["action"] = "regen"
            pace["rate_after_regen"] = round(rate, 2)
            decision = speedpolicy.pace_guard_decision(rate, ref_rate,
                                                       band)
            if decision != "ok":
                # SPEED LAW: the old guard applied an atempo nudge
                # (clamped to 1.12x) here. That silent speed change is
                # abolished — the take is rejected and re-rolled.
                raise PaceBandReject(
                    f"[pace-guard] onset rate {rate:.2f}/s still outside "
                    f"the locked band (±{band:.0%}) of the reference "
                    f"{ref_rate:.2f}/s after one regeneration — take "
                    "rejected, NOT tempo-stretched (speed law, "
                    "2026-11-16)")
        sf.write(out_wav, y, SR, subtype="PCM_16")
        return pace


def _chatterbox_take(text, ref_wav, out_wav, settings):
    """One-off English clone take (single-take subprocess path): builds a
    throwaway session, exactly the old behaviour."""
    return _ChatterboxSession(ref_wav, settings).generate(text, out_wav)


def _bytes_to_take(audio, lang, out_wav, settings, info):
    """Shared downstream path for every service backend: audio bytes in
    (mp3/wav), normalised 24 kHz mono wav out. Hindi keeps its locked
    +20% pace calibration (ONE atempo, logged) on every route — under
    the speed law that factor is a RECIPE value read from settings via
    speedpolicy (part of the Hindi voice's definition), never an
    adjustment the tool chose."""
    raw = out_wav + ".raw"
    with open(raw, "wb") as f:
        f.write(audio)
    subprocess.run(["ffmpeg", "-v", "error", "-i", raw, "-ar", str(SR),
                    "-ac", "1", out_wav, "-y"], check=True)
    os.unlink(raw)
    if lang == "hi":
        factor, note = speedpolicy.recipe_tempo("hi", settings)
        if speedpolicy.apply_tempo(out_wav, factor, "recipe"):
            info["atempo"] = factor  # approved +20% calibration, logged
            info["speed_recipe"] = note


# =========================================================================
# Meta MMS-TTS route (local model — the "big Telugu engine", merged
# into this tool 2026-11-16 next to the locked Chatterbox English)
# =========================================================================
MMS_MODEL_ID = "facebook/mms-tts-tel"
_MMS_CACHE = {}


def _mms_take(text, lang, out_wav, settings, info):
    """One Meta MMS-TTS take (Telugu only). MMS is a native-speaker
    VITS model (Massively Multilingual Speech, 1,100+ languages) — NOT
    a clone: the voice is the model's own Telugu speaker, selected for
    its native diction (proven clean on the channel's hard conjuncts
    in the Nov 14 wtu-dub route, gen_mms.py). The model runs locally;
    the load first tries the normal hub path (which also fetches the
    model on first use) and falls back to the local HF cache
    (local_files_only) when the hub is unreachable. The waveform rides
    the shared _bytes_to_take normalisation to 24 kHz mono, so
    gates/QC see the same shape as every other backend."""
    if lang != "te":
        raise RuntimeError(
            "[mms] the MMS route in this tool is Telugu-only "
            f"({MMS_MODEL_ID}); for en use chatterbox, for hi use "
            "indicf5-space, elevenlabs or http")
    if "model" not in _MMS_CACHE:
        from transformers import AutoTokenizer, VitsModel
        try:
            model = VitsModel.from_pretrained(MMS_MODEL_ID)
            tok = AutoTokenizer.from_pretrained(MMS_MODEL_ID)
        except Exception as e:  # hub unreachable — use the local cache
            try:
                model = VitsModel.from_pretrained(MMS_MODEL_ID,
                                                  local_files_only=True)
                tok = AutoTokenizer.from_pretrained(MMS_MODEL_ID,
                                                    local_files_only=True)
            except Exception:
                raise RuntimeError(
                    f"[mms] could not load {MMS_MODEL_ID} (hub: {e}; "
                    "local cache also failed)") from e
        _MMS_CACHE["model"] = model
        _MMS_CACHE["tok"] = tok
    model = _MMS_CACHE["model"]
    tok = _MMS_CACHE["tok"]
    import io

    import soundfile as sf
    import torch
    # Pace control (fixed11, 2026-11-16): MMS's native pace is slow
    # (~80 wpm vs the channel's ~130). transformers 4.49's VitsModel
    # takes NO length_scale forward kwarg; its inference computes
    # length_scale = 1.0 / self.speaking_rate (modeling_vits.py),
    # the attribute copied from config at load. Env MMS_LENGTH_SCALE
    # (default 1.0) is the phoneme-duration multiplier: <1 = faster.
    # Measured on S2 (19 words): 1.0 -> 13.87s, 0.80 -> 11.36s,
    # 0.70 -> 10.22s, 0.62 -> 9.15s (in the 7.6-10.0s band). The right
    # scale is per-sentence (S1 needed 0.80 for its 6.0-7.9s band) --
    # same per-sentence calibration rule as fixed10's IndicF5 speed.
    length_scale = float(os.environ.get("MMS_LENGTH_SCALE", "1.0"))
    if length_scale <= 0:
        raise RuntimeError(
            f"[mms] MMS_LENGTH_SCALE must be > 0, got {length_scale}")
    model.speaking_rate = 1.0 / length_scale
    inputs = tok(text, return_tensors="pt")
    with torch.no_grad():
        waveform = model(**inputs).waveform
    audio = waveform.squeeze().cpu().numpy().astype("float32")
    buf = io.BytesIO()
    sf.write(buf, audio, model.config.sampling_rate, format="WAV")
    info["mms_model"] = MMS_MODEL_ID
    info["mms_native_sr"] = model.config.sampling_rate
    info["mms_length_scale"] = length_scale
    _bytes_to_take(buf.getvalue(), lang, out_wav, settings, info)


# =========================================================================
# OmniVoice route (official k2-fsa HF Space — Telugu clone, LOCKED
# settings, added 2026-11-16 on the owner's ear approval)
# =========================================================================
OMNIVOICE_BASE = "https://k2-fsa-omnivoice.hf.space"
OMNI_REF = os.path.join(VOICE_DIR, "refs", "natspan2.wav")
# LOCKED (owner's order, 2026-11-16): same voice, same speed, every
# run. The reference is the canonical natspan2 (the same audio as
# voice/telugu-reference.wav); speed is 1.0 EXACTLY and no speed
# correction (generation-side or atempo) may ever be applied on this
# route — pace comes from the reference, as approved. Steps/guidance
# are the values the approved samples were generated with.
OMNIVOICE_LOCKED = {"space": "k2-fsa/OmniVoice", "language": "Telugu",
                    "speed": 1.0, "num_steps": 32, "guidance": 2.0,
                    "ref": "voice/refs/natspan2.wav (canonical natspan2)",
                    "speed_correction": "FORBIDDEN on this route"}


def _omnivoice_synthesize(text, ref_wav, ref_text):
    """One OmniVoice clone generation via the official Space's Gradio
    API (_clone_fn); returns raw audio bytes. Retries Space error
    events with backoff — the free anonymous quota drops calls in
    streaks; pacing clears them (nothing evaded, nothing paid)."""
    import requests
    s = requests.Session()

    def upload():
        with open(ref_wav, "rb") as f:
            up = s.post(OMNIVOICE_BASE + "/gradio_api/upload",
                        files={"files": (os.path.basename(ref_wav), f,
                                         "audio/wav")},
                        timeout=180)
        return up.json()[0]

    last = None
    for attempt in range(3):
        try:
            ref_path = upload()
            data = [text, OMNIVOICE_LOCKED["language"],
                    {"path": ref_path, "meta": {"_type": "gradio.FileData"}},
                    ref_text, "", OMNIVOICE_LOCKED["num_steps"],
                    OMNIVOICE_LOCKED["guidance"], True,
                    OMNIVOICE_LOCKED["speed"], None, True, True]
            r = s.post(OMNIVOICE_BASE + "/gradio_api/call/_clone_fn",
                       json={"data": data}, timeout=180)
            eid = r.json()["event_id"]
            with s.get(OMNIVOICE_BASE + f"/gradio_api/call/_clone_fn/{eid}",
                       stream=True, timeout=1200) as resp:
                buf = ""
                for chunk in resp.iter_content(chunk_size=None,
                                               decode_unicode=True):
                    buf += chunk
            if "event: error" in buf and "event: complete" not in buf:
                raise RuntimeError("space error event")
            m = re.findall(r"event: complete\ndata: (.*)", buf)
            if not m:
                raise RuntimeError("no complete event: " + buf[-150:])
            out = json.loads(m[-1])[0]
            audio = s.get(OMNIVOICE_BASE + "/gradio_api/file="
                          + out["path"], timeout=180).content
            if len(audio) < 5000:
                raise RuntimeError(f"tiny output {len(audio)}b")
            return audio
        except Exception as e:  # Space flakiness is routine; retry
            last = e
            if attempt < 2:
                time.sleep(45)
    raise RuntimeError(
        f"[omnivoice] OmniVoice failed after retries: {last}")


def _omnivoice_take(text, lang, out_wav, settings, info):
    """One OmniVoice take (Telugu only, locked settings). The route
    generates ONE sentence per take — the engine's main loop already
    splits text into sentences, so per-sentence generation is the
    engine's own shape, unchanged."""
    if lang != "te":
        raise RuntimeError(
            "[omnivoice] the OmniVoice route in this tool is Telugu-only "
            "(locked natspan2 house voice); for en use chatterbox, for "
            "hi use indicf5-space, elevenlabs or http")
    env_speed = os.environ.get("JULIE_OMNIVOICE_SPEED")
    if env_speed is not None and float(env_speed) != 1.0:
        raise RuntimeError(
            "[omnivoice] speed is LOCKED at 1.0 on this route — no "
            "speed correction is permitted (owner's order, 2026-11-16); "
            f"refusing JULIE_OMNIVOICE_SPEED={env_speed}")
    ref_text = open(TE_REF_TEXT).read().strip()
    audio = _omnivoice_synthesize(text, OMNI_REF, ref_text)
    _bytes_to_take(audio, lang, out_wav, settings, info)
    info["omnivoice"] = dict(OMNIVOICE_LOCKED)


def _ref_pair(ref_name):
    """(wav, text) for a canonical reference: the default Telugu
    reference (natspan2, == voice/telugu-reference.wav) or a named
    entry of voice/refs/refs.json — the repair ladder's alternate
    reference spans come from the same canonical set."""
    if not ref_name:
        return TE_REF, open(TE_REF_TEXT).read().strip()
    refs = json.load(open(os.path.join(VOICE_DIR, "refs", "refs.json"),
                          encoding="utf-8"))["refs"]
    ref = refs[ref_name]
    return os.path.join(HERE, ref["wav"]), ref["text"]


def _gen_take_core(backend, lang, text, out_wav, settings, session=None,
                   user_speed=None, ref_name=None, seed=None):
    """Synthesize ONE raw take via an already-resolved backend; returns
    the GEN_INFO dict. `session` is a reusable _ChatterboxSession —
    batch mode loads the model once and passes it in for every line;
    without one, the Chatterbox route builds a throwaway session, as
    the old per-take subprocess path always did. `user_speed` is the
    job's explicit --speed factor (speedpolicy-validated by the
    caller) or None; it is the ONLY non-recipe tempo change that may
    ever touch a take, and it is recorded in GEN_INFO either way."""
    info = {"lang": lang, "backend": backend,
            "speed_source": (speedpolicy.SOURCE_USER if user_speed
                             else speedpolicy.SOURCE_LOCKED)}
    if user_speed:
        info["user_speed"] = user_speed
    if backend == "chatterbox":
        if lang != "en":
            raise RuntimeError(
                "[chatterbox] the Chatterbox route is the English clone; "
                "for te/hi use indicf5-space, elevenlabs or http")
        sess = session or _ChatterboxSession(EN_REF, settings)
        info["pace"] = sess.generate(text, out_wav, seed=seed)
        if seed is not None:
            info["seed"] = seed
    elif backend == "indicf5-space":
        if lang == "en":
            raise RuntimeError(
                "[indicf5-space] the IndicF5 route serves te/hi; "
                "for en use chatterbox, elevenlabs or http")
        ref_wav, ref_text = _ref_pair(ref_name)
        if ref_name:
            info["ref"] = ref_name
        audio = _indicf5_synthesize(text, ref_wav, ref_text)
        _bytes_to_take(audio, lang, out_wav, settings, info)
    elif backend == "mms":
        _mms_take(text, lang, out_wav, settings, info)
    elif backend == "omnivoice":
        _omnivoice_take(text, lang, out_wav, settings, info)
    elif backend in ("elevenlabs", "http", "github"):
        audio = backends.synthesize(backend, text, lang, settings)
        _bytes_to_take(audio, lang, out_wav, settings, info)
    else:  # resolve_backend already rejects unknown values
        raise RuntimeError(f"[backends] unhandled backend {backend!r}")
    # Gate 6 (2026-11-16): auto-mute the head grunt on EVERY route
    # before the take is gated. acoustic_gates has no environment side
    # effects (unlike gates.py, which strips proxies at import), so it
    # is safe inside this generation process. The action is recorded
    # in GEN_INFO -> the QC report's per-roll "gen" entry.
    try:
        import acoustic_gates
        hg = acoustic_gates.head_grunt_gate(out_wav, apply=True)
        if hg.get("action", {}).get("muted"):
            info["head_grunt_gate"] = hg["action"]
    except Exception as e:  # a mute failure must not kill generation;
        # gate 6 in run_all_gates will still catch an unmuted grunt
        info["head_grunt_gate_error"] = str(e)[-200:]
    # Speed law: an explicit user --speed for this job is the ONLY
    # non-recipe tempo change that may touch a take. It is applied
    # once, here, after synthesis (and after the grunt mute), and the
    # gates then judge the take the user actually asked to hear.
    if user_speed:
        speedpolicy.apply_tempo(out_wav, user_speed, "user")
    return info


def gen_take(lang, text, out_wav):
    """--gen-take mode: synthesize ONE raw take via the selected backend
    (env JULIE_TTS_BACKEND, default per language). Prints a JSON info
    line that names the backend; the parent records it in the QC report.
    DIVI_USER_SPEED / DIVI_TAKE_BACKEND / DIVI_TAKE_REF in the
    environment are set ONLY by the parent process: the speed from the
    user's explicit --speed option (never computed by the tool), the
    backend/ref from the repair ladder's per-sentence escalation."""
    settings = load_settings()
    backend = (os.environ.get("DIVI_TAKE_BACKEND")
               or backends.resolve_backend(lang, settings))
    us = os.environ.get("DIVI_USER_SPEED")
    user_speed = speedpolicy.resolve_user_speed(
        float(us)) if us else None
    ref = os.environ.get("DIVI_TAKE_REF") or None
    seed = os.environ.get("DIVI_TAKE_SEED")
    info = _gen_take_core(backend, lang, text, out_wav, settings,
                          user_speed=user_speed, ref_name=ref,
                          seed=int(seed) if seed else None)
    print("GEN_INFO " + json.dumps(info))


# =========================================================================
# Batch mode: model loads once per worker, every line in-process
# =========================================================================
def read_batch_lines(path, first_index=1):
    """Batch lines file: one line per row; blank rows are skipped.
    Returns [{"index": n, "text": line}] numbered from first_index
    (the Actions workflow passes --first-index per chunk so merged
    artifacts keep the script's original line numbers)."""
    lines = []
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                lines.append({"index": first_index + len(lines), "text": line})
    return lines


def split_round_robin(items, n):
    """Split items into at most n chunks, round-robin, so long and
    short lines spread evenly across parallel workers."""
    n = max(1, min(int(n), len(items) or 1))
    chunks = [[] for _ in range(n)]
    for i, item in enumerate(items):
        chunks[i % n].append(item)
    return [c for c in chunks if c]


def batch_line_name(index):
    return f"{index:03d}.mp3"


def batch_gen_worker(in_path, out_path):
    """--batch-gen mode (hidden): generate every take listed in a JSON
    manifest with ONE model load and ONE reference conditioning for the
    whole manifest — the batch speed core. A failing item is recorded
    in the output manifest, never fatal to the rest of the chunk.
    Items may carry per-item backend / ref / seed / user_speed (the
    repair ladder's escalation); the Chatterbox session is shared by
    every chatterbox item in the manifest."""
    with open(in_path) as fh:
        manifest = json.load(fh)
    lang = manifest["lang"]
    settings = load_settings()
    default_backend = backends.resolve_backend(lang, settings)
    user_speed = manifest.get("user_speed")
    session = None
    if any((it.get("backend") or default_backend) == "chatterbox"
           for it in manifest["items"]):
        session = _ChatterboxSession(EN_REF, settings)  # load + condition ONCE
    results = []
    for item in manifest["items"]:
        t0 = time.time()
        backend = item.get("backend") or default_backend
        rec = {"index": item["index"], "roll": item["roll"],
               "backend": backend}
        try:
            rec["gen"] = _gen_take_core(
                backend, lang, item["text"], item["out"], settings,
                session=session if backend == "chatterbox" else None,
                user_speed=user_speed, ref_name=item.get("ref"),
                seed=item.get("seed"))
            rec["ok"] = os.path.exists(item["out"])
            if not rec["ok"]:
                rec["gen_error"] = "generation wrote no output file"
        except Exception as e:  # one bad line must not kill the chunk
            rec["ok"] = False
            rec["gen_error"] = str(e)[-400:]
        rec["gen_s"] = round(time.time() - t0, 1)
        results.append(rec)
    with open(out_path, "w") as fh:
        json.dump({"backend": default_backend, "results": results}, fh,
                  ensure_ascii=False)
    print(f"BATCH_GEN {len(results)} takes, backend={default_backend}")
    return 0


def run_batch(args, settings, gen_env):
    """--batch orchestration: WAVES of parallel worker processes
    implementing the self-healing repair loop (repair.py).

    Wave 1 generates --candidates takes per line (best-of-N by
    default — first-pass yield is the design goal); the parent gates
    and scores every candidate and locks each line's best PASSING
    one. Lines without a winner go to the next wave, whose candidate
    plan is defect-directed (seed re-rolls scored by completeness,
    route / reference-span escalation) — up to --rerolls extra
    waves. A line that never passes gets no mp3 and is NAMED in
    batch.qc.json; every other line ships — per-sentence
    independence: the job completes, the failure is named, the work
    does not stop. Passing lines are assembled to
    <outdir>/<nnn>.mp3; --assemble-out additionally assembles the
    shipped lines into one mp3 and runs the final assembled-file
    verification (verify.py) on it. Returns 0 when every line
    passed, 2 on any named failure or failed verification."""
    import repair

    lines = read_batch_lines(args.batch, args.first_index)
    if not lines:
        print("ERROR: no lines in batch file", file=sys.stderr)
        return 2
    os.makedirs(args.outdir, exist_ok=True)
    jobs = max(1, args.jobs or min(4, os.cpu_count() or 1))
    waves = 1 + max(0, args.rerolls)
    cand_per_wave = max(1, args.candidates)
    try:
        user_speed = speedpolicy.resolve_user_speed(args.speed)
    except speedpolicy.SpeedPolicyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    try:
        backend = backends.resolve_backend(args.lang, settings)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if mass_roll_route(args.lang, waves, settings) == "dispatch":
        # Same rule as before: a very large te/hi wave budget
        # dispatches to the mass-roll workflow instead of rolling
        # locally (takes are harvested there, not shipped here).
        try:
            dispatch_mass_rolls([ln["text"] for ln in lines], args.lang,
                                waves * cand_per_wave, settings)
            return 3
        except Exception as e:
            print(f"ERROR: mass-roll dispatch failed: {e}", file=sys.stderr)
            return 2
    worker_env = dict(gen_env)
    if backend == "chatterbox":
        # Spread the machine's cores across workers unless the user
        # pinned JULIE_CLONE_THREADS themselves.
        threads = max(1, (os.cpu_count() or 1) // jobs)
        worker_env.setdefault("JULIE_CLONE_THREADS", str(threads))
    workdir = tempfile.mkdtemp(prefix="divi_batch_")
    engine_path = os.path.abspath(__file__)
    line_by_idx = {ln["index"]: ln for ln in lines}
    records = {ln["index"]: {"index": ln["index"], "text": ln["text"],
                             "rolls": [], "chosen_roll": None,
                             "repairs": [], "status": "pending",
                             "out": None}
               for ln in lines}
    winners = {}
    model_loads = 0
    wall0 = time.time()
    pending = list(lines)
    for wave in range(1, waves + 1):
        if not pending:
            break
        n = cand_per_wave + (1 if wave >= 3 else 0)
        items_all = []
        for ln in pending:
            rec = records[ln["index"]]
            specs = repair.candidate_plan(
                args.lang, backend, wave, rec.get("last_defects") or [],
                n, seed_base=ln["index"] * 1000 + wave * 17)
            for ci, spec in enumerate(specs):
                items_all.append({
                    "index": ln["index"], "roll": wave * 100 + ci,
                    "text": ln["text"],
                    "out": os.path.join(
                        workdir,
                        f"line{ln['index']}_w{wave}c{ci}.wav"),
                    "backend": spec["backend"], "ref": spec["ref"],
                    "seed": spec["seed"], "spec": spec})
        chunks = split_round_robin(items_all, jobs)
        results = {}
        for ci, chunk in enumerate(chunks):
            man_items = [{k: it[k] for k in
                          ("index", "roll", "text", "out", "backend",
                           "ref", "seed")} for it in chunk]
            man_in = os.path.join(workdir, f"manifest_w{wave}_{ci}.in.json")
            man_out = os.path.join(workdir,
                                   f"manifest_w{wave}_{ci}.out.json")
            with open(man_in, "w") as fh:
                json.dump({"lang": args.lang, "user_speed": user_speed,
                           "items": man_items}, fh, ensure_ascii=False)
            proc = subprocess.Popen(
                [sys.executable, engine_path, "--batch-gen", man_in,
                 man_out],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=worker_env)
            model_loads += 1
            try:
                proc.communicate(timeout=1800 * len(chunk) + 1800)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            if os.path.exists(man_out):
                with open(man_out) as fh:
                    for r in json.load(fh).get("results", []):
                        results[(r["index"], r["roll"])] = r
        still = []
        for ln in pending:
            rec = records[ln["index"]]
            wave_actions = []
            for it in items_all:
                if it["index"] != ln["index"]:
                    continue
                spec = it["spec"]
                if spec["action"] not in wave_actions:
                    wave_actions.append(spec["action"])
                res = results.get((it["index"], it["roll"]))
                cand = {"roll": it["roll"], "wave": wave,
                        "backend": spec["backend"], "ref": spec["ref"],
                        "seed": spec["seed"], "action": spec["action"],
                        "ship": False}
                if res is None or not res.get("ok"):
                    cand["gen_error"] = (res or {}).get(
                        "gen_error",
                        "batch worker died before reporting")
                    cand["defects"] = [repair.GENERATION]
                else:
                    cand["gen"] = res.get("gen")
                    cand["gen_s"] = res.get("gen_s")
                    g0 = time.time()
                    rep, ship, extra, score, defects = _gate_and_score(
                        it["out"], args.lang, ln["text"], settings)
                    cand["gate_s"] = round(time.time() - g0, 1)
                    cand.update(rep)
                    if extra:
                        cand["ship_check"] = extra
                    cand["ship"] = ship
                    cand["score"] = score
                    cand["defects"] = defects
                    cand["take"] = it["out"]
                rec["rolls"].append(cand)
            best = repair.best_passing(rec["rolls"])
            if best is not None:
                rec["chosen_roll"] = best["roll"]
                rec["chosen"] = {"wave": best["wave"],
                                 "backend": best["backend"],
                                 "score": best.get("score"),
                                 "take": best["take"]}
                winners[ln["index"]] = best
                rec["status"] = "passed"
                if wave > 1:
                    rec["repairs"].append(
                        {"wave": wave, "actions": wave_actions,
                         "result": f"winner locked (score "
                                   f"{best.get('score')})"})
            else:
                wave_cands = [c for c in rec["rolls"]
                              if c["wave"] == wave]
                best_fail = max(wave_cands,
                                key=lambda c: c.get("score", -100.0)) \
                    if wave_cands else None
                rec["last_defects"] = (best_fail or {}).get(
                    "defects", [repair.GENERATION])
                rec["repairs"].append(
                    {"wave": wave, "defects": rec["last_defects"],
                     "actions": wave_actions,
                     "result": ("no passing candidate — escalating"
                                if wave < waves else
                                "no passing candidate — ladder "
                                "exhausted; sentence named as failed")})
                still.append(ln)
        pending = still

    for idx in sorted(records):
        rec = records[idx]
        if rec["chosen_roll"] is not None:
            out_mp3 = os.path.join(args.outdir, batch_line_name(idx))
            info = assemble([winners[idx]["take"]], out_mp3, settings,
                            args.bed)
            rec["out"] = out_mp3
            rec["duration_s"] = info["duration_s"]
    failed = [r for r in records.values() if r["chosen_roll"] is None]
    qc = {"engine": "Divi Engine 2.0", "mode": "batch",
          "voice": settings["voice_name"], "lang": args.lang,
          "backend": backend, "jobs": jobs, "rerolls": args.rerolls,
          "candidates_per_wave": cand_per_wave,
          "speed": speedpolicy.speed_block(args.lang, settings,
                                            user_speed),
          "lines": [records[i] for i in sorted(records)],
          "timings": {"wall_s": round(time.time() - wall0, 1),
                      "model_loads": model_loads,
                      "gen_s_total": round(sum(
                          e.get("gen_s") or 0
                          for r in records.values() for e in r["rolls"]),
                          1)},
          "verdict": ("PASS — every line passed the gates "
                      "(best-of-N repair loop)"
                      if not failed else
                      f"PARTIAL — {len(failed)} of {len(records)} "
                      "lines failed the full escalation ladder and "
                      "are named here; every other line shipped")}
    if args.assemble_out:
        shipped = [records[i] for i in sorted(records)
                   if records[i]["chosen_roll"] is not None]
        if shipped:
            info = assemble([winners[r["index"]]["take"]
                             for r in shipped],
                            args.assemble_out, settings, args.bed)
            import verify
            rep = verify.verify_file(
                args.assemble_out, [r["text"] for r in shipped],
                args.lang, settings, sentence_spans=info["spans"],
                expected_duration_s=info["duration_s"])
            final_qc = os.path.splitext(args.assemble_out)[0] + ".qc.json"
            qc["final"] = {"out": args.assemble_out, **info,
                           "verification": rep, "qc_path": final_qc}
            with open(final_qc, "w") as fh:
                json.dump({"engine": "Divi Engine 2.0",
                           "mode": "batch-final", **qc["final"]}, fh,
                          ensure_ascii=False, indent=1)
            if not rep["pass"]:
                os.unlink(args.assemble_out)
                qc["final"]["removed"] = (
                    "assembled mp3 removed — final verification failed")
                qc["verdict"] = ("FAIL — final assembled-file "
                                 "verification failed; the assembled "
                                 "mp3 was removed (per-line mp3s and "
                                 "the gate tables remain)")
                failed = failed or [1]  # force exit 2 below
        else:
            qc["final"] = {"out": args.assemble_out,
                           "error": "no line passed — nothing to "
                                    "assemble"}
    qc_path = os.path.join(args.outdir, "batch.qc.json")
    with open(qc_path, "w") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    print(f"BATCH {'OK' if not failed else 'PARTIAL'}: "
          f"{len(records) - len(failed)}/{len(records)} lines "
          f"-> {args.outdir} "
          f"({qc['timings']['wall_s']}s wall, {model_loads} model "
          f"loads) — QC: {qc_path}")
    return 0 if not failed else 2


# =========================================================================
# Assembly (only gate-passing takes reach this)
# =========================================================================
def _load24(p):
    import soundfile as sf
    y, sr = sf.read(p, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y[:, 0]
    if sr != SR:
        raise ValueError(f"{p}: sample rate {sr} != {SR}")
    return y.astype("float32")


def _speech_span(y, thr_db=-45.0):
    import numpy as np
    hop = 256
    n = len(y) // hop
    fr = y[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    idx = np.where(db > thr_db)[0]
    if len(idx) == 0:
        return 0, len(y)
    pad = int(0.06 * SR)
    return max(0, idx[0] * hop - pad), min(len(y), (idx[-1] + 1) * hop + pad)


def _gate_gaps(y):
    """Zero sustained sub-threshold regions (>=120 ms) with 18 ms fades —
    every gap becomes true digital silence (kills pause-region hum)."""
    import numpy as np
    hop = 240  # 10 ms
    n = len(y) // hop
    fr = y[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    floor = np.percentile(db, 10)
    thr = floor + 12.0
    active = db > thr
    exp = active.copy()
    for k in range(1, 4):
        exp[k:] |= active[:-k]
        exp[:-k] |= active[k:]
    gain = np.ones(n, dtype=np.float32)
    i = 0
    while i < n:
        if not exp[i]:
            j = i
            while j < n and not exp[j]:
                j += 1
            if j - i >= 12:
                gain[i:j] = 0.0
            i = j
        else:
            i += 1
    g = np.repeat(gain, hop)
    if len(g) < len(y):
        g = np.concatenate([g, np.full(len(y) - len(g), g[-1])])
    k = int(0.018 * SR)
    ker = np.ones(k) / k
    g = np.convolve(g, ker, mode="same")
    return y * np.clip(g * 1.6, 0, 1)


def _piano_bed(dur_s, sr=SR):
    """Quiet synthesized piano bed (the channel's production layer)."""
    import numpy as np
    from scipy.signal import lfilter

    def note(freq, dur, vel=1.0):
        t = np.arange(int(dur * sr)) / sr
        env = np.exp(-t / 1.9) * (1 - np.exp(-t / 0.006))
        yy = np.zeros_like(t)
        for h in range(1, 7):
            yy += (1.0 / h ** 1.5) * np.sin(2 * np.pi * freq * h * t)
        a = 1 - np.exp(-2 * np.pi * 3200 / sr)
        yy = lfilter([a], [1, -(1 - a)], yy)
        return (yy * env * vel * 0.24).astype(np.float32)

    chords = [[110.00, 220.00, 261.63, 329.63, 493.88],
              [87.31, 174.61, 220.00, 261.63, 329.63],
              [130.81, 196.00, 261.63, 329.63, 493.88],
              [98.00, 196.00, 246.94, 293.66, 329.63]]
    cd = 6.2
    bed = np.zeros(int(dur_s * sr) + sr, dtype=np.float32)
    for ci in range(int(np.ceil(dur_s / cd)) + 1):
        ch = chords[ci % len(chords)]
        t0 = ci * cd
        for f, off, vel in [(ch[0], 0.0, 1.0), (ch[1], 0.05, 0.8), (ch[2], 0.55, 0.62),
                            (ch[3], 1.15, 0.58), (ch[4], 1.75, 0.5), (ch[2], 3.1, 0.4),
                            (ch[3], 4.3, 0.38)]:
            seg = note(f, cd - off + 0.6, vel)
            s = int((t0 + off) * sr)
            if s >= len(bed):
                continue
            e = min(len(bed), s + len(seg))
            bed[s:e] += seg[:e - s]
    return bed[:int(dur_s * sr)]


def assemble(take_paths, out_mp3, settings, use_bed):
    import numpy as np
    import soundfile as sf
    acfg = settings["assembly"]
    takes = []
    for p in take_paths:
        y = _load24(p)
        a, b = _speech_span(y)
        takes.append(y[a:b])
    # plain-gain level match to the median speech RMS (no dynamics)
    rmss = [float(np.sqrt(np.mean(t ** 2)) + 1e-12) for t in takes]
    target = float(np.median(rmss))
    gap = np.zeros(int(acfg["sentence_gap_s"] * SR), dtype=np.float32)
    parts = []
    spans = []
    cursor = 0.0
    for i, t in enumerate(takes):
        g = target / rmss[i]
        parts.append((t * g).astype(np.float32))
        spans.append([round(cursor, 3), round(len(t) / SR, 3)])
        cursor += len(t) / SR
        if i < len(takes) - 1:
            parts.append(gap)
            cursor += acfg["sentence_gap_s"]
    voice = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    peak = float(np.max(np.abs(voice))) if len(voice) else 0.0
    if peak > 0.98:
        voice = voice * (0.98 / peak)
    voice = _gate_gaps(voice)
    tail = int(acfg["bed_tail_s"] * SR) if use_bed else 0
    mix = np.concatenate([voice, np.zeros(tail, dtype=np.float32)])
    if use_bed:
        bed = _piano_bed(len(mix) / SR)
        vrms = float(np.sqrt(np.mean(voice ** 2)) + 1e-12)
        brms = float(np.sqrt(np.mean(bed ** 2)) + 1e-12)
        bed_gain = vrms * 10 ** (-acfg["piano_bed_db_under_voice"] / 20.0) / brms
        fade = np.linspace(1.0, 0.0, tail, dtype=np.float32) if tail else None
        b = bed * bed_gain
        if tail:
            b[-tail:] *= fade
        if len(b) < len(mix):
            # _piano_bed works in whole seconds/steps and can land one
            # sample short of the mix; pad with silence, never crash.
            b = np.concatenate(
                [b, np.zeros(len(mix) - len(b), dtype=np.float32)])
        mix = mix + b[:len(mix)]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp_wav = tf.name
    sf.write(tmp_wav, mix, SR, subtype="PCM_16")
    # ONE loudnorm pass, straight to the final mp3
    subprocess.run(["ffmpeg", "-v", "error", "-i", tmp_wav,
                    "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
                    "-ar", "48000", "-ac", "2", "-codec:a", "libmp3lame",
                    "-q:a", "2", out_mp3, "-y"], check=True)
    os.unlink(tmp_wav)
    return {"duration_s": round(len(mix) / SR, 2), "bed": use_bed,
            "level_match_target_rms": target, "spans": spans}


# =========================================================================
# te/hi ship rule: whole take + identity + pace (Ajju's order, 2026-11-16)
# =========================================================================
_IDENTITY_ENCODER = None
_EN_REF_EMB = None


def _take_identity(path):
    """Resemblyzer cosine similarity of a take vs the 25 s English
    reference (the house voice). Raises on any failure — the caller
    fails closed."""
    global _IDENTITY_ENCODER, _EN_REF_EMB
    import numpy as np
    import soundfile as sf
    from resemblyzer import VoiceEncoder, preprocess_wav
    if _IDENTITY_ENCODER is None:
        _IDENTITY_ENCODER = VoiceEncoder(verbose=False)
        _EN_REF_EMB = _IDENTITY_ENCODER.embed_utterance(preprocess_wav(EN_REF))
    y, sr = sf.read(path)
    if sr != 16000:
        import librosa
        y = librosa.resample(y.astype("float32"), orig_sr=sr, target_sr=16000)
    emb = _IDENTITY_ENCODER.embed_utterance(preprocess_wav(y, 16000))
    return float(np.dot(emb, _EN_REF_EMB)
                 / (np.linalg.norm(emb) * np.linalg.norm(_EN_REF_EMB) + 1e-9))


def _take_pace_wps(path, lang, n_words):
    """Words per second over the ASR speech span — the same formula the
    indicf5-batch runners use. faster-whisper's default log-prob /
    no-speech thresholds silently drop segments on this material
    (fixed4 calibration), so they are disabled explicitly; the model is
    fed a librosa-decoded array because PyAV decoding is unreliable."""
    import librosa
    import numpy as np
    import gates
    y, _sr = librosa.load(path, sr=16000, mono=True)
    segs, _info = gates.get_model().transcribe(
        y, language=lang, word_timestamps=True,
        log_prob_threshold=None, no_speech_threshold=None)
    words = [w for s in segs for w in (s.words or [])]
    if len(words) < 2:
        return None
    span = words[-1].end - words[0].start
    med = float(np.median([w.end - w.start for w in words]))
    eff = span + med
    return (n_words / eff) if eff > 0 else None


def ship_decision(take_path, lang, text, settings, rep):
    """The single place a take is accepted for shipping.

    en: the five gates decide (locked recipe, unchanged) — plus
    gates 6/7, which ride inside report['pass'].
    te/hi: WHOLE-TAKE ONLY, ear-approved bar (Ajju, 2026-11-16,
    fixed13 — gates.ship_bar_te_hi in settings.json): gate 1 (no-hint
    language) AND gate 2 (ghost scan) pass, PLUS identity >=
    gates.identity_min_te_hi, PLUS pace within gates.pace_wps_te_hi,
    all on the SAME whole take. Gates 3/4/5 are still computed and
    recorded on every take but are ADVISORY for te/hi: the fixed6
    calibration proved the identical suite fails her own genuine
    narration, and the ear-approved fixed13 takes do not pass all of
    them either (S1 F0 184.2 Hz vs the 185 Hz band edge) — requiring
    all five would refuse the very takes the owner approved. GATE 7
    (cut word, added 2026-11-16 on the owner's order after Sample B
    sentence 6 shipped a truncated ending) is NOT advisory: it is a
    hard condition here, because a truncated final word is exactly
    the class of defect the ear caught and the bar exists to kill.
    A check that cannot be measured fails closed (ship=False): an
    unmeasurable take is not a passing take.
    Returns (ship, extra); extra is merged into the QC roll entry.
    """
    if lang not in WHOLE_TAKE_LANGS:
        return bool(rep["pass"]), {}
    g1 = rep.get("gate1_nohint_language", {}).get("pass")
    g2 = rep.get("gate2_ghost_words", {}).get("pass")
    if not (g1 and g2):
        return False, {}
    g = settings["gates"]
    extra = {"ship_rule": "whole-take ear-approved bar: gate1 + gate2 "
                          "+ identity + pace + gate7 cut-word "
                          "(gates 3/4/5 advisory)",
             "gate1_pass": True, "gate2_pass": True,
             "gate7_pass": rep.get("gate7_cut_word", {}).get("pass"),
             "advisory": {
                 "gate3_pass": rep.get("gate3_pronunciation", {})
                 .get("pass"),
                 "gate4_pass": rep.get("gate4_phys_swallowed", {})
                 .get("pass"),
                 "gate5_pass": rep.get("gate5_pitch", {}).get("pass")}}
    if extra["gate7_pass"] is not True:
        # Hard block (owner's order, 2026-11-16): a truncated ending
        # never ships; an unmeasured ending fails closed like the rest.
        extra["blocked_by"] = "gate7_cut_word"
        return False, extra
    try:
        ident = _take_identity(take_path)
        extra["identity"] = round(ident, 3)
        extra["identity_min"] = g["identity_min_te_hi"]
        extra["identity_pass"] = bool(ident >= g["identity_min_te_hi"])
    except Exception as e:  # fail closed: unmeasurable != passing
        extra["identity"] = None
        extra["identity_pass"] = False
        extra["identity_error"] = str(e)[-200:]
    try:
        wps = _take_pace_wps(take_path, lang, len(text.split()))
        lo, hi = g["pace_wps_te_hi"]
        extra["pace_wps"] = round(wps, 3) if wps else None
        extra["pace_band"] = [lo, hi]
        extra["pace_pass"] = bool(wps and lo <= wps <= hi)
    except Exception as e:  # fail closed
        extra["pace_wps"] = None
        extra["pace_pass"] = False
        extra["pace_error"] = str(e)[-200:]
    return bool(extra["identity_pass"] and extra["pace_pass"]), extra


def _gate_and_score(take_path, lang, text, settings):
    """Gate one candidate take and package the repair loop's view of
    it: (gate report, ship bool, ship extra, quality score, defects).
    The single funnel both run modes heal through."""
    import gates
    import repair
    rep = gates.run_all_gates(take_path, lang, text, settings)
    ship, extra = ship_decision(take_path, lang, text, settings, rep)
    score = repair.take_score(rep, extra)
    defects = repair.defect_classes(rep, extra)
    return rep, ship, extra, score, defects


def mass_roll_route(lang, rolls, settings):
    """'local' or 'dispatch': te/hi roll budgets above the local limit
    go to the indicf5-batch.yml mass-roll workflow (10 parallel
    runners); everything else rolls locally."""
    if lang in WHOLE_TAKE_LANGS and \
            rolls > settings["gates"]["local_roll_limit_te_hi"]:
        return "dispatch"
    return "local"


def dispatch_mass_rolls(sentences, lang, total_rolls, settings):
    """Hand a large te/hi roll budget to the indicf5-batch workflow:
    write the sentences to indicf5-lines.txt in this repo, commit +
    push, and dispatch the workflow via gh. The runners generate WHOLE
    takes of every line and gate them with the same ship rule; takes +
    gate JSONs come back as the run's indicf5-batch-all artifact.
    Nothing is shipped locally on this path — the caller exits without
    writing an mp3. Raises on any failure (fail loudly)."""
    import math
    repo = os.path.dirname(os.path.abspath(__file__))
    per_runner = max(1, math.ceil(total_rolls / 10))
    lines_file = os.path.join(repo, "indicf5-lines.txt")
    with open(lines_file, "w") as fh:
        fh.write("\n".join(sentences) + "\n")

    def run(cmd):
        p = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd[:3])} failed: "
                               f"{(p.stderr or p.stdout)[-300:]}")
        return p.stdout

    run(["git", "add", "indicf5-lines.txt"])
    run(["git", "commit", "-m",
         f"indicf5 mass-roll lines ({lang}, {total_rolls} rolls requested)"])
    run(["git", "push", "origin", "main"])
    run(["gh", "workflow", "run", "indicf5-batch.yml", "--ref", "main",
         "-f", f"rolls={per_runner}", "-f", "lines_path=indicf5-lines.txt"])
    url = ""
    try:
        url = run(["gh", "run", "list", "--workflow", "indicf5-batch.yml",
                   "--limit", "1", "--json", "url",
                   "--jq", ".[0].url"]).strip()
    except Exception:
        pass  # the dispatch itself already succeeded; URL is a courtesy
    print(f"DISPATCHED indicf5-batch: {total_rolls} rolls requested "
          f"({per_runner}/runner x 10) for {len(sentences)} sentence(s)."
          + (f" Run: {url}" if url else ""))
    print("Takes + gate JSONs arrive as the run's indicf5-batch-all "
          "artifact; no local mp3 is written by this dispatch.")
    return True


# =========================================================================
# Main loop: generate -> gate -> re-roll
# =========================================================================
def split_sentences(text):
    parts = re.split(r"(?<=[.!?।॥\n])\s*", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def main():
    ap = argparse.ArgumentParser(
        description="Divi Engine — the house voice engine (locked "
                    "recipes, self-healing repair loop, speed law)")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--lang", choices=["en", "te", "hi"])
    ap.add_argument("--out")
    ap.add_argument("--rolls", type=int, default=None,
                    help="max generation attempts per sentence (default: settings)")
    ap.add_argument("--speed", type=float, default=None,
                    help="USER-REQUESTED tempo factor for THIS job "
                         "only (e.g. 1.1). Default: none — the locked "
                         "recipe speed runs exactly; the tool never "
                         "adjusts speed on its own. The QC report "
                         "prints the speed source (LOCKED / "
                         "USER-REQUESTED).")
    ap.add_argument("--candidates", type=int, default=3,
                    help="candidates generated per sentence per wave "
                         "(best-of-N repair loop; default: 3)")
    ap.add_argument("--bed", action="store_true",
                    help="add the quiet piano bed under the voice")
    ap.add_argument("--keep-takes", action="store_true",
                    help="keep the per-roll take wavs next to the output")
    ap.add_argument("--batch", metavar="LINES_TXT",
                    help="batch mode: voice a whole lines file (one line "
                         "per row) with the model loaded once per worker")
    ap.add_argument("--outdir",
                    help="batch mode: directory for <nnn>.mp3 per line "
                         "plus batch.qc.json")
    ap.add_argument("--jobs", type=int, default=None,
                    help="batch mode: parallel worker processes "
                         "(default: min(4, cpu count))")
    ap.add_argument("--rerolls", type=int, default=2,
                    help="batch mode: extra repair waves per failing "
                         "line (default: 2)")
    ap.add_argument("--assemble-out",
                    help="batch mode: also assemble the shipped lines "
                         "into this single mp3 and run the final "
                         "assembled-file verification on it")
    ap.add_argument("--first-index", type=int, default=1,
                    help=argparse.SUPPRESS)
    ap.add_argument("--gen-take", nargs=3, metavar=("LANG", "TEXT", "OUT"),
                    help=argparse.SUPPRESS)
    ap.add_argument("--batch-gen", nargs=2, metavar=("IN_JSON", "OUT_JSON"),
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.gen_take:
        gen_take(args.gen_take[0], args.gen_take[1], args.gen_take[2])
        return 0

    if args.batch_gen:
        return batch_gen_worker(args.batch_gen[0], args.batch_gen[1])

    if args.batch:
        if not args.lang or not args.outdir:
            ap.error("--batch requires --lang and --outdir")
        settings = load_settings()
        gen_env = dict(os.environ)  # snapshot BEFORE the gates import
        import gates  # noqa: F401  (strips proxies in this process only;
        # batch workers are spawned with gen_env, the original env)
        return run_batch(args, settings, gen_env)

    if not args.lang or not args.out:
        ap.error("--lang and --out are required")
    if not args.text and not args.text_file:
        ap.error("--text or --text-file is required")
    text = args.text if args.text else open(args.text_file).read()
    settings = load_settings()
    max_rolls = args.rolls or settings["gates"]["max_rolls"]
    gen_env = dict(os.environ)  # snapshot BEFORE the gates import: gates
    import gates  # strips proxy vars in THIS process (local ASR loads);
    # generation subprocesses get gen_env (the original environment) —
    # with the stripped env their HTTPS calls to the TTS backend cannot
    # route through the proxy and fail with SSL errors.

    sentences = split_sentences(text)
    if not sentences:
        ap.error("no sentences in text")
    if mass_roll_route(args.lang, max_rolls, settings) == "dispatch":
        # Large te/hi budget: mass rolls belong on the 10-runner
        # indicf5-batch workflow, not on this machine. Exit 3 =
        # dispatched (not a pass, not a failure); nothing ships locally.
        try:
            dispatch_mass_rolls(sentences, args.lang, max_rolls, settings)
            return 3
        except Exception as e:
            print(f"ERROR: mass-roll dispatch failed: {e}", file=sys.stderr)
            return 2
    workdir = tempfile.mkdtemp(prefix="divi_takes_")
    try:
        backend = backends.resolve_backend(args.lang, settings)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    try:
        user_speed = speedpolicy.resolve_user_speed(args.speed)
    except speedpolicy.SpeedPolicyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if user_speed is not None:
        # The ONLY path a user speed reaches generation: the parent
        # exports it to the --gen-take subprocesses. The tool itself
        # never computes a speed (speedpolicy.py).
        gen_env["DIVI_USER_SPEED"] = str(user_speed)
    # The self-healing repair loop (repair.py): each sentence gets
    # best-of-N candidates per wave (--candidates), all gated and
    # scored; the best PASSING candidate ships. Failures escalate
    # per the playbook (seed re-rolls scored by completeness ->
    # wider best-of-N -> alternate route -> alternate reference
    # span) until the sentence's candidate budget (--rolls /
    # settings gates.max_rolls, total takes) is spent. A sentence
    # that exhausts its ladder is NAMED in the QC report and the
    # job CONTINUES with the rest — the work never stops; only when
    # NO sentence passes is nothing shipped (verdict FAIL, exit 2).
    import repair
    from concurrent.futures import ThreadPoolExecutor

    qc = {"engine": "Divi Engine 2.0", "voice": settings["voice_name"],
          "lang": args.lang, "backend": backend, "text": text,
          "max_rolls": max_rolls,
          "speed": speedpolicy.speed_block(args.lang, settings,
                                            user_speed),
          "sentences": []}
    gen_cap = (1 if backend in repair.LOCAL_MODEL_BACKENDS
               else max(1, args.jobs or 4))
    engine_path = os.path.abspath(__file__)
    chosen = []          # (1-based sentence index, take path)
    gen_calls = 0
    wall0 = time.time()

    def gen_candidate(spec, si, take, text):
        """One candidate take via a --gen-take subprocess; the spec's
        backend/ref/seed ride the environment (the repair ladder's
        only levers). Returns (gen_info, error)."""
        env = dict(gen_env)
        env["DIVI_TAKE_BACKEND"] = spec["backend"]
        if spec.get("ref"):
            env["DIVI_TAKE_REF"] = spec["ref"]
        if spec.get("seed") is not None:
            env["DIVI_TAKE_SEED"] = str(spec["seed"])
        if spec["backend"] in ("elevenlabs", "http"):
            timeout = 300  # 120 s HTTP cap per take + conversion margin
        else:
            timeout = 1800 if args.lang == "en" else 1200
        try:
            proc = subprocess.run(
                [sys.executable, engine_path, "--gen-take",
                 args.lang, text, take],
                capture_output=True, text=True, timeout=timeout,
                env=env)
        except subprocess.TimeoutExpired:
            return None, f"generation timed out ({timeout}s)"
        info = None
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GEN_INFO "):
                info = json.loads(line[len("GEN_INFO "):])
        if proc.returncode != 0 or info is None \
                or not os.path.exists(take):
            return None, (proc.stderr or "")[-400:] or \
                f"gen exit {proc.returncode}"
        return info, None

    for si, sent in enumerate(sentences, start=1):
        entry = {"index": si, "text": sent, "rolls": [],
                 "chosen_roll": None, "repairs": []}
        budget = max_rolls
        wave = 0
        defects = []
        winner = None
        while budget > 0 and winner is None:
            wave += 1
            n = min(budget, args.candidates + (1 if wave >= 3 else 0))
            specs = repair.candidate_plan(
                args.lang, backend, wave, defects, n,
                seed_base=si * 1000 + wave * 17)
            budget -= len(specs)
            jobs_spec = [(spec, os.path.join(
                workdir, f"s{si}_w{wave}c{ci}.wav"))
                for ci, spec in enumerate(specs)]
            t0 = time.time()
            with ThreadPoolExecutor(
                    max_workers=max(1, min(gen_cap,
                                           len(jobs_spec)))) as pool:
                results = list(pool.map(
                    lambda a: gen_candidate(a[0], si, a[1], sent),
                    jobs_spec))
            gen_calls += len(results)
            wave_actions = []
            for (spec, take), (info, err) in zip(jobs_spec, results):
                if spec["action"] not in wave_actions:
                    wave_actions.append(spec["action"])
                cand = {"roll": len(entry["rolls"]) + 1, "wave": wave,
                        "backend": spec["backend"],
                        "ref": spec.get("ref"), "seed": spec.get("seed"),
                        "action": spec["action"], "gen": info,
                        "gen_s": round(time.time() - t0, 1),
                        "ship": False}
                if err is not None:
                    cand["gen_error"] = err
                    cand["defects"] = [repair.GENERATION]
                else:
                    rep, ship, extra, score, cdefs = _gate_and_score(
                        take, args.lang, sent, settings)
                    cand.update(rep)
                    if extra:
                        cand["ship_check"] = extra
                    cand["ship"] = ship
                    cand["score"] = score
                    cand["defects"] = cdefs
                    cand["take"] = take
                entry["rolls"].append(cand)
            winner = repair.best_passing(entry["rolls"])
            if winner is None:
                wave_cands = [c for c in entry["rolls"]
                              if c["wave"] == wave]
                best_fail = max(wave_cands,
                                key=lambda c: c.get("score", -100.0))
                defects = best_fail.get("defects") or [repair.GENERATION]
                entry["repairs"].append(
                    {"wave": wave, "defects": defects,
                     "actions": wave_actions,
                     "result": ("no passing candidate — escalating"
                                if budget > 0 else
                                "no passing candidate — ladder "
                                "exhausted; sentence named as failed")})
            elif wave > 1:
                entry["repairs"].append(
                    {"wave": wave, "actions": wave_actions,
                     "result": f"winner locked (score "
                               f"{winner.get('score')})"})
        entry["passed"] = winner is not None
        if winner is not None:
            entry["chosen_roll"] = winner["roll"]
            dest = os.path.join(workdir, f"chosen_s{si}.wav")
            os.replace(winner["take"], dest)
            chosen.append((si, dest))
        qc["sentences"].append(entry)

    qc["timings"] = {"wall_s": round(time.time() - wall0, 1),
                     "generation_calls": gen_calls}
    failed = [e for e in qc["sentences"] if not e["passed"]]
    qc_path = os.path.splitext(args.out)[0] + ".qc.json"
    if not chosen:
        qc["verdict"] = ("FAIL — no sentence passed the full "
                         "escalation ladder; NO final mp3 written")
        with open(qc_path, "w") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)
        print("FAIL: no sentence passed the ship checks — see "
              f"QC report: {qc_path}", file=sys.stderr)
        return 2
    info = assemble([t for _, t in chosen], args.out, settings, args.bed)
    import verify
    vrep = verify.verify_file(
        args.out, [sentences[si - 1] for si, _ in chosen], args.lang,
        settings, sentence_spans=info["spans"],
        expected_duration_s=info["duration_s"])
    qc["final"] = {"out": args.out, "backend": backend, **info,
                   "verification": vrep}
    if failed:
        names = "; ".join(f"[{e['index']}] {e['text'][:60]}"
                          for e in failed)
        qc["verdict"] = (f"PARTIAL — {len(failed)} sentence(s) failed "
                         f"the full escalation ladder and are NOT in "
                         f"the file: {names}. Everything else shipped.")
    else:
        qc["verdict"] = ("PASS — every sentence passed the gates "
                         "(best-of-N repair loop)")
    if not vrep["pass"]:
        qc["verdict"] = ("FAIL — final assembled-file verification "
                         "failed; the mp3 was removed. " + qc["verdict"])
    with open(qc_path, "w") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    if not vrep["pass"]:
        os.unlink(args.out)
        print("FAIL: final verification failed — mp3 removed, see "
              f"QC report: {qc_path}", file=sys.stderr)
        return 2
    if args.keep_takes:
        keep = os.path.splitext(args.out)[0] + "_takes"
        os.makedirs(keep, exist_ok=True)
        for f in os.listdir(workdir):
            os.replace(os.path.join(workdir, f), os.path.join(keep, f))
    print(f"{'OK' if not failed else 'PARTIAL'} {args.out} "
          f"({info['duration_s']}s) — {len(chosen)}/{len(sentences)} "
          f"sentences — QC: {qc_path}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
