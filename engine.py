#!/usr/bin/env python3
"""Julie AI Voice Engine — gated voice-clone generation.

    python3 engine.py --text "…" --lang te --out line.mp3
    python3 engine.py --text-file script.txt --lang en --out out.mp3 --bed

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
    raise RuntimeError(f"IndicF5 failed after retries: {last}")


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


def _chatterbox_take(text, ref_wav, out_wav, settings):
    """English clone take: phrase chunking + pace guard (locked recipe)."""
    import numpy as np
    import soundfile as sf
    import torch
    from chatterbox.tts import ChatterboxTTS

    cfg = settings["english_chatterbox"]
    torch.set_num_threads(max(1, int(os.environ.get("JULIE_CLONE_THREADS", "2"))))
    model = ChatterboxTTS.from_pretrained(device="cpu")
    has_prepare = hasattr(model, "prepare_conditionals")
    if has_prepare:
        model.prepare_conditionals(ref_wav)

    def gen_unit(unit):
        kw = {"exaggeration": cfg["exaggeration"], "cfg_weight": cfg["cfg_weight"]}
        if has_prepare:
            wav = model.generate(unit, **kw)
        else:
            wav = model.generate(unit, audio_prompt_path=ref_wav, **kw)
        data = wav.detach().cpu().float().numpy()
        return (data[0] if data.ndim == 2 else data).astype(np.float32)

    # phrase chunking: units end at commas/semicolons/colons (0.06 s joins)
    units = [u.strip() for u in re.split(r"(?<=[,;:])\s*", text) if u.strip()]
    if not units:
        units = [text]

    def synth_all():
        parts = []
        for ui, unit in enumerate(units):
            y = gen_unit(unit)
            y = _squash_gaps_np(y, SR)
            parts.append(y)
            if ui < len(units) - 1:
                parts.append(np.zeros(int(cfg_join * SR), dtype=np.float32))
        return np.concatenate(parts)

    cfg_join = settings["english_chatterbox"]["phrase_chunking"]["comma_gap_s"]
    ref_y, _ = sf.read(ref_wav, dtype="float32", always_2d=False)
    if ref_y.ndim > 1:
        ref_y = ref_y[:, 0]
    ref_rate = _onset_rate(ref_y.astype(np.float32), SR)
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


def gen_take(lang, text, out_wav):
    """--gen-take mode: synthesize ONE raw take. Prints a JSON info line."""
    settings = load_settings()
    info = {"lang": lang}
    if lang == "en":
        info["pace"] = _chatterbox_take(text, EN_REF, out_wav, settings)
    elif lang in ("te", "hi"):
        ref_text = open(TE_REF_TEXT).read().strip()
        audio = _indicf5_synthesize(text, TE_REF, ref_text)
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
    else:
        raise SystemExit(f"unknown lang {lang}")
    print("GEN_INFO " + json.dumps(info))


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
    ap.add_argument("--lang", choices=["en", "te", "hi"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rolls", type=int, default=None,
                    help="max generation attempts per sentence (default: settings)")
    ap.add_argument("--bed", action="store_true",
                    help="add the quiet piano bed under the voice")
    ap.add_argument("--keep-takes", action="store_true",
                    help="keep the per-roll take wavs next to the output")
    ap.add_argument("--gen-take", nargs=3, metavar=("LANG", "TEXT", "OUT"),
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.gen_take:
        gen_take(args.gen_take[0], args.gen_take[1], args.gen_take[2])
        return 0

    if not args.text and not args.text_file:
        ap.error("--text or --text-file is required")
    text = args.text if args.text else open(args.text_file).read()
    settings = load_settings()
    max_rolls = args.rolls or settings["gates"]["max_rolls"]
    import gates  # imported here: strips proxies in THIS process only

    sentences = split_sentences(text)
    if not sentences:
        ap.error("no sentences in text")
    workdir = tempfile.mkdtemp(prefix="julie_takes_")
    qc = {"engine": "julie-ai-voice-engine 1.0", "voice": settings["voice_name"],
          "lang": args.lang, "text": text, "max_rolls": max_rolls,
          "sentences": []}
    chosen = []
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
                capture_output=True, text=True, timeout=gen_timeout)
            gen_info = {}
            for line in (proc.stdout or "").splitlines():
                if line.startswith("GEN_INFO "):
                    gen_info = json.loads(line[len("GEN_INFO "):])
            if proc.returncode != 0 or not os.path.exists(take):
                entry["rolls"].append({"roll": roll, "gen_error":
                                       (proc.stderr or "")[-400:],
                                       "gen_s": round(time.time() - t0, 1)})
                continue
            rep = gates.run_all_gates(take, args.lang, sent, settings)
            entry["rolls"].append({"roll": roll, "gen": gen_info,
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
    qc["final"] = {"out": args.out, **info}
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
