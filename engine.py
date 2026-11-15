#!/usr/bin/env python3
"""Julie AI Voice Engine — gated voice-clone generation.

    python3 engine.py --text "…" --lang te --out line.mp3
    python3 engine.py --text-file script.txt --lang en --out out.mp3 --bed
    python3 engine.py --batch lines.txt --lang en --outdir out/ --jobs 4

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

Generation routes (locked, see voice/settings.json):
  en  Chatterbox TTS zero-shot clone, exaggeration 0.35, phrase chunking,
      pace guard (regen once, then atempo clamped to 1.12x, logged).
  te  IndicF5 (ai4bharat HF Space) from the Telugu reference. No atempo —
      pace is fixed by take selection.
  hi  IndicF5 cross-lingual from the Telugu reference, with the owner's
      approved +20% pace calibration: ONE atempo 1.20 per take, logged.

Pluggable backends (backends.py): env JULIE_TTS_BACKEND overrides the
route above for any language — "elevenlabs" (your ElevenLabs voice,
key from env ELEVENLABS_API_KEY) or "http" (any model server you run,
env JULIE_TTS_URL). The gates, re-roll loop and QC report are unchanged
on top of every backend; each take's backend is recorded in the QC
report. See README, "Connect your own model (fast path)".

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


def _squash_gaps_np(y, sr, max_gap=0.35, keep=0.12, thr_db=-45.0):
    """Cut silences longer than max_gap INSIDE a phrase down to `keep`.
    (The clone invents mid-phrase pauses; her delivery flows through.)"""
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


def _atempo_file(path, factor):
    tmp = path + ".atempo.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", f"atempo={factor}",
                    tmp, "-y"], check=True)
    os.replace(tmp, path)


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

    def generate(self, text, out_wav):
        """English clone take: phrase chunking + pace guard (locked recipe)."""
        import numpy as np
        import soundfile as sf

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
                y = _squash_gaps_np(y, SR)
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
        if ref_rate > 0 and abs(rate - ref_rate) / ref_rate > band:
            y = synth_all()  # ONE regeneration
            rate = _onset_rate(y, SR)
            pace["action"] = "regen"
            pace["rate_after_regen"] = round(rate, 2)
            if abs(rate - ref_rate) / ref_rate > band:
                factor = min(1.12, max(1 / 1.12, ref_rate / rate)) if rate > 0 else 1.0
                sf.write(out_wav, y, SR, subtype="PCM_16")
                _atempo_file(out_wav, round(factor, 3))
                pace["action"] = "regen+atempo"
                pace["atempo"] = round(factor, 3)
                return pace
        sf.write(out_wav, y, SR, subtype="PCM_16")
        return pace


def _chatterbox_take(text, ref_wav, out_wav, settings):
    """One-off English clone take (single-take subprocess path): builds a
    throwaway session, exactly the old behaviour."""
    return _ChatterboxSession(ref_wav, settings).generate(text, out_wav)


def _bytes_to_take(audio, lang, out_wav, settings, info):
    """Shared downstream path for every service backend: audio bytes in
    (mp3/wav), normalised 24 kHz mono wav out. Hindi keeps its locked
    +20% pace calibration (ONE atempo, logged) on every route."""
    raw = out_wav + ".raw"
    with open(raw, "wb") as f:
        f.write(audio)
    subprocess.run(["ffmpeg", "-v", "error", "-i", raw, "-ar", str(SR),
                    "-ac", "1", out_wav, "-y"], check=True)
    os.unlink(raw)
    if lang == "hi":
        atempo = settings["hindi_indicf5"]["pace_calibration"]["atempo"]
        _atempo_file(out_wav, atempo)
        info["atempo"] = atempo  # approved +20% pace calibration, logged


def _gen_take_core(backend, lang, text, out_wav, settings, session=None):
    """Synthesize ONE raw take via an already-resolved backend; returns
    the GEN_INFO dict. `session` is a reusable _ChatterboxSession —
    batch mode loads the model once and passes it in for every line;
    without one, the Chatterbox route builds a throwaway session, as
    the old per-take subprocess path always did."""
    info = {"lang": lang, "backend": backend}
    if backend == "chatterbox":
        if lang != "en":
            raise RuntimeError(
                "[chatterbox] the Chatterbox route is the English clone; "
                "for te/hi use indicf5-space, elevenlabs or http")
        sess = session or _ChatterboxSession(EN_REF, settings)
        info["pace"] = sess.generate(text, out_wav)
    elif backend == "indicf5-space":
        if lang == "en":
            raise RuntimeError(
                "[indicf5-space] the IndicF5 route serves te/hi; "
                "for en use chatterbox, elevenlabs or http")
        ref_text = open(TE_REF_TEXT).read().strip()
        audio = _indicf5_synthesize(text, TE_REF, ref_text)
        _bytes_to_take(audio, lang, out_wav, settings, info)
    elif backend in ("elevenlabs", "http", "github"):
        audio = backends.synthesize(backend, text, lang, settings)
        _bytes_to_take(audio, lang, out_wav, settings, info)
    else:  # resolve_backend already rejects unknown values
        raise RuntimeError(f"[backends] unhandled backend {backend!r}")
    return info


def gen_take(lang, text, out_wav):
    """--gen-take mode: synthesize ONE raw take via the selected backend
    (env JULIE_TTS_BACKEND, default per language). Prints a JSON info
    line that names the backend; the parent records it in the QC report."""
    settings = load_settings()
    backend = backends.resolve_backend(lang, settings)
    info = _gen_take_core(backend, lang, text, out_wav, settings)
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
    in the output manifest, never fatal to the rest of the chunk."""
    with open(in_path) as fh:
        manifest = json.load(fh)
    lang = manifest["lang"]
    settings = load_settings()
    backend = backends.resolve_backend(lang, settings)
    session = None
    if backend == "chatterbox":
        session = _ChatterboxSession(EN_REF, settings)  # load + condition ONCE
    results = []
    for item in manifest["items"]:
        t0 = time.time()
        rec = {"index": item["index"], "roll": item["roll"]}
        try:
            rec["gen"] = _gen_take_core(backend, lang, item["text"],
                                        item["out"], settings, session=session)
            rec["ok"] = os.path.exists(item["out"])
            if not rec["ok"]:
                rec["gen_error"] = "generation wrote no output file"
        except Exception as e:  # one bad line must not kill the chunk
            rec["ok"] = False
            rec["gen_error"] = str(e)[-400:]
        rec["gen_s"] = round(time.time() - t0, 1)
        results.append(rec)
    with open(out_path, "w") as fh:
        json.dump({"backend": backend, "results": results}, fh,
                  ensure_ascii=False)
    print(f"BATCH_GEN {len(results)} takes, backend={backend}")
    return 0


def run_batch(args, settings, gen_env):
    """--batch orchestration: rounds of parallel worker processes.

    Round 1 generates one take per line (each worker loads the model
    once for its whole chunk); the parent gates every take in-process;
    only lines that failed go into the next round, up to --rerolls
    extra rounds. Passing lines are assembled to <outdir>/<nnn>.mp3;
    lines that never pass get no mp3 and are named in batch.qc.json.
    Returns 0 when every line passed, 2 otherwise (same honesty rule
    as single mode)."""
    import gates  # already imported by main(); local ref for clarity

    lines = read_batch_lines(args.batch, args.first_index)
    if not lines:
        print("ERROR: no lines in batch file", file=sys.stderr)
        return 2
    os.makedirs(args.outdir, exist_ok=True)
    jobs = max(1, args.jobs or min(4, os.cpu_count() or 1))
    max_attempts = 1 + max(0, args.rerolls)
    try:
        backend = backends.resolve_backend(args.lang, settings)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    worker_env = dict(gen_env)
    if backend == "chatterbox":
        # Spread the machine's cores across workers unless the user
        # pinned JULIE_CLONE_THREADS themselves.
        threads = max(1, (os.cpu_count() or 1) // jobs)
        worker_env.setdefault("JULIE_CLONE_THREADS", str(threads))
    workdir = tempfile.mkdtemp(prefix="julie_batch_")
    engine_path = os.path.abspath(__file__)
    line_by_idx = {ln["index"]: ln for ln in lines}
    records = {ln["index"]: {"index": ln["index"], "text": ln["text"],
                             "rolls": [], "chosen_roll": None, "out": None}
               for ln in lines}
    chosen_takes = {}
    model_loads = 0
    wall0 = time.time()
    pending = list(lines)
    for attempt in range(1, max_attempts + 1):
        if not pending:
            break
        chunks = split_round_robin(pending, jobs)
        procs = []
        for ci, chunk in enumerate(chunks):
            items = [{"index": ln["index"], "roll": attempt,
                      "text": ln["text"],
                      "out": os.path.join(
                          workdir, f"line{ln['index']}_r{attempt}.wav")}
                     for ln in chunk]
            man_in = os.path.join(workdir, f"manifest_{attempt}_{ci}.in.json")
            man_out = os.path.join(workdir, f"manifest_{attempt}_{ci}.out.json")
            with open(man_in, "w") as fh:
                json.dump({"lang": args.lang, "items": items}, fh,
                          ensure_ascii=False)
            proc = subprocess.Popen(
                [sys.executable, engine_path, "--batch-gen", man_in, man_out],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=worker_env)
            procs.append((proc, man_out, items))
            model_loads += 1
        still = []
        for proc, man_out, items in procs:
            try:
                proc.communicate(timeout=1800 * len(items) + 1800)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            results = []
            if os.path.exists(man_out):
                with open(man_out) as fh:
                    results = json.load(fh).get("results", [])
            by_idx = {r["index"]: r for r in results}
            item_by_idx = {it["index"]: it for it in items}
            for idx, item in item_by_idx.items():
                rec = records[idx]
                res = by_idx.get(idx)
                if res is None:
                    rec["rolls"].append(
                        {"roll": attempt, "backend": backend,
                         "gen_error": "batch worker died before reporting"})
                    still.append(line_by_idx[idx])
                    continue
                entry = {"roll": attempt, "backend": backend,
                         "gen_s": res.get("gen_s")}
                if not res.get("ok"):
                    entry["gen_error"] = res.get("gen_error", "worker failed")
                    rec["rolls"].append(entry)
                    still.append(line_by_idx[idx])
                    continue
                entry["gen"] = res.get("gen")
                g0 = time.time()
                rep = gates.run_all_gates(item["out"], args.lang,
                                          rec["text"], settings)
                entry["gate_s"] = round(time.time() - g0, 1)
                entry.update(rep)
                rec["rolls"].append(entry)
                if rep["pass"]:
                    rec["chosen_roll"] = attempt
                    chosen_takes[idx] = item["out"]
                else:
                    still.append(line_by_idx[idx])
        pending = still

    for idx in sorted(records):
        rec = records[idx]
        if rec["chosen_roll"] is not None:
            out_mp3 = os.path.join(args.outdir, batch_line_name(idx))
            info = assemble([chosen_takes[idx]], out_mp3, settings, args.bed)
            rec["out"] = out_mp3
            rec["duration_s"] = info["duration_s"]
    failed = [r for r in records.values() if r["chosen_roll"] is None]
    qc = {"engine": "julie-ai-voice-engine 1.0", "mode": "batch",
          "voice": settings["voice_name"], "lang": args.lang,
          "backend": backend, "jobs": jobs, "rerolls": args.rerolls,
          "lines": [records[i] for i in sorted(records)],
          "timings": {"wall_s": round(time.time() - wall0, 1),
                      "model_loads": model_loads,
                      "gen_s_total": round(sum(
                          e.get("gen_s") or 0
                          for r in records.values() for e in r["rolls"]), 1)},
          "verdict": ("PASS — every line passed all five gates"
                      if not failed else
                      f"PARTIAL — {len(failed)} of {len(records)} lines "
                      "never passed the gates; no mp3 written for them")}
    qc_path = os.path.join(args.outdir, "batch.qc.json")
    with open(qc_path, "w") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    print(f"BATCH {'OK' if not failed else 'PARTIAL'}: "
          f"{len(records) - len(failed)}/{len(records)} lines -> {args.outdir} "
          f"({qc['timings']['wall_s']}s wall, {model_loads} model loads) "
          f"— QC: {qc_path}")
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
    for i, t in enumerate(takes):
        g = target / rmss[i]
        parts.append((t * g).astype(np.float32))
        if i < len(takes) - 1:
            parts.append(gap)
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
            "level_match_target_rms": target}


# =========================================================================
# Main loop: generate -> gate -> re-roll
# =========================================================================
def split_sentences(text):
    parts = re.split(r"(?<=[.!?।॥\n])\s*", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def main():
    ap = argparse.ArgumentParser(description="Julie AI Voice Engine")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--lang", choices=["en", "te", "hi"])
    ap.add_argument("--out")
    ap.add_argument("--rolls", type=int, default=None,
                    help="max generation attempts per sentence (default: settings)")
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
                    help="batch mode: gate re-rolls per failing line "
                         "(default: 2)")
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
    workdir = tempfile.mkdtemp(prefix="julie_takes_")
    try:
        backend = backends.resolve_backend(args.lang, settings)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    qc = {"engine": "julie-ai-voice-engine 1.0", "voice": settings["voice_name"],
          "lang": args.lang, "backend": backend, "text": text,
          "max_rolls": max_rolls, "sentences": []}
    chosen = []
    if backend in ("elevenlabs", "http"):
        gen_timeout = 300  # 120 s HTTP cap per take + conversion margin
    else:
        gen_timeout = 1800 if args.lang == "en" else 1200
    for si, sent in enumerate(sentences, start=1):
        entry = {"index": si, "text": sent, "rolls": [], "chosen_roll": None}
        passed_path = None
        for roll in range(1, max_rolls + 1):
            take = os.path.join(workdir, f"s{si}_r{roll}.wav")
            t0 = time.time()
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--gen-take",
                 args.lang, sent, take],
                capture_output=True, text=True, timeout=gen_timeout,
                env=gen_env)
            gen_info = {}
            for line in (proc.stdout or "").splitlines():
                if line.startswith("GEN_INFO "):
                    gen_info = json.loads(line[len("GEN_INFO "):])
            if proc.returncode != 0 or not os.path.exists(take):
                entry["rolls"].append({"roll": roll, "backend": backend,
                                       "gen_error":
                                       (proc.stderr or "")[-400:],
                                       "gen_s": round(time.time() - t0, 1)})
                continue
            rep = gates.run_all_gates(take, args.lang, sent, settings)
            entry["rolls"].append({"roll": roll, "backend": backend,
                                   "gen": gen_info,
                                   "gen_s": round(time.time() - t0, 1), **rep})
            if rep["pass"]:
                entry["chosen_roll"] = roll
                passed_path = take
                break
        qc["sentences"].append(entry)
        if passed_path is None:
            qc["verdict"] = "FAIL — no take passed all gates; NO final mp3 written"
            qc_path = os.path.splitext(args.out)[0] + ".qc.json"
            with open(qc_path, "w") as fh:
                json.dump(qc, fh, ensure_ascii=False, indent=1)
            print(f"FAIL: sentence {si} never passed the gates in "
                  f"{max_rolls} rolls. Gate table: {qc_path}", file=sys.stderr)
            return 2
        dest = os.path.join(workdir, f"chosen_s{si}.wav")
        os.replace(passed_path, dest)
        chosen.append(dest)

    info = assemble(chosen, args.out, settings, args.bed)
    qc["verdict"] = "PASS — every sentence passed all five gates"
    qc["final"] = {"out": args.out, "backend": backend, **info}
    qc_path = os.path.splitext(args.out)[0] + ".qc.json"
    with open(qc_path, "w") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    if args.keep_takes:
        keep = os.path.splitext(args.out)[0] + "_takes"
        os.makedirs(keep, exist_ok=True)
        for f in os.listdir(workdir):
            os.replace(os.path.join(workdir, f), os.path.join(keep, f))
    print(f"OK {args.out} ({info['duration_s']}s) — QC: {qc_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
