#!/usr/bin/env python3
"""Divi Turbo — the fast path.  One voice, three languages, one command.

    python3 turbo.py --te script_te.txt --hi script_hi.txt --en script_en.txt --outdir out/
    python3 turbo.py --te script_te.txt --outdir out/            # one language

What makes it fast
------------------
* ONE local model (OmniVoice, k2-fsa) for all three languages, loaded
  ONCE per device. No free-Space queues, no quota errors, no network
  after the first download.
* The voice prompt (reference audio -> tokens) is encoded ONCE per
  language and reused for every sentence.
* Sentences are generated in BATCHES (length-sorted, padded together),
  which is where GPU speed comes from. With two GPUs (Kaggle T4 x2) the
  sentences are split across both.
* One take first. Only a sentence that FAILS a check is re-made (new
  seed), and only that sentence. Nothing restarts the job.
* Cheap checks run on every take (duration vs. text length catches
  dropped / repeated / swallowed words; head-grunt mute + cut-word gate
  from acoustic_gates.py). The Whisper word check runs on GPU by
  default and is optional on CPU (--asr / --no-asr).

What stays the same (owner's law)
---------------------------------
* Same voice: Telugu + Hindi clone from the canonical natural-pace
  Telugu reference (voice/refs/natspan2.wav, the ear-approved one);
  English clones from voice/english-reference.wav. Override with
  --ref-te/--ref-hi/--ref-en (e.g. a Hindi clip from the Hindi channel).
* Same speed: speed 1.0, NO time-stretch, NO atempo on any language.
  Pace comes from the reference, as approved. The pace check REJECTS a
  take that drifts, it never stretches it.
* Same assembly recipe: plain gain level-match, 0.6 s sentence gaps
  (0.66 s English), true-silence gaps, ONE loudnorm pass (~-15 LUFS).

Outputs per language: <lang>.mp3, <lang>.srt (subtitles with real
timings), <lang>.qc.json (every sentence, every take, every check,
every text normalization, timings and the speed-vs-realtime figure).
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import textnorm  # noqa: E402

SR = 24000
LANG_NAME = {"te": "Telugu", "hi": "Hindi", "en": "English"}
GAP_S = {"te": 0.6, "hi": 0.6, "en": 0.66}
REF_DEFAULT = {
    "te": ("voice/refs/natspan2.wav", "voice/telugu-reference-text.txt"),
    "hi": ("voice/refs/natspan2.wav", "voice/telugu-reference-text.txt"),
    "en": ("voice/english-reference.wav", "voice/english-reference-text.txt"),
}
# Allowed seconds-per-character band, relative to the job's own median
# take. Outside it the take most likely dropped, repeated or swallowed
# words -> re-made. (Relative, so it follows the reference's pace.)
PACE_BAND = (0.72, 1.40)
MAX_CHARS = {"te": 170, "hi": 190, "en": 230}


# ------------------------------------------------------------ text prep --
def split_sentences(text, lang):
    text = re.sub(r"\s+", " ", text.replace("\r", " ")).strip()
    parts = re.split(r"(?<=[.!?।॥])\s+|\n+", text)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # over-long sentence -> split at clause boundaries only
        while len(p) > MAX_CHARS[lang]:
            cut = -1
            for m in re.finditer(r"[,;:]\s", p[:MAX_CHARS[lang]]):
                cut = m.end()
            if cut < 40:
                break
            out.append(p[:cut].strip().rstrip(",;:") + ",")
            p = p[cut:].strip()
        out.append(p)
    return out


def prep_script(raw, lang):
    log = []
    try:
        import preflight
        pf = preflight.preflight_text(raw, lang)
        text, corr, flags = pf["text"], pf["corrections"], pf["flags"]
    except Exception as e:  # pre-flight is an aid, never a blocker
        text, corr, flags = raw, [], [{"preflight_error": repr(e)}]
    sents = split_sentences(text, lang)
    spoken = [textnorm.normalize(s, lang, log) for s in sents]
    return sents, spoken, {"script_corrections": corr, "flags": flags,
                           "spoken_form": log}


# ------------------------------------------------------------- devices --
def pick_devices(want):
    import torch
    if want == "cpu" or not torch.cuda.is_available():
        return ["cpu"]
    n = torch.cuda.device_count()
    return [f"cuda:{i}" for i in range(n)] if want == "auto" else [want]


def load_model(device):
    import torch
    from omnivoice import OmniVoice
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    if device == "cpu":
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    return OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=device,
                                     dtype=dtype)


# ------------------------------------------------------------ checks ----
def _speech_bounds(y, thr_db=-45.0):
    if len(y) == 0:
        return 0, 0
    hop = 240
    n = len(y) // hop
    if n == 0:
        return 0, len(y)
    fr = y[: n * hop].reshape(n, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    peak = db.max()
    act = np.where(db > max(thr_db, peak - 40))[0]
    if len(act) == 0:
        return 0, 0
    return max(0, act[0] * hop - 1200), min(len(y), (act[-1] + 1) * hop + 2400)


def trim(y):
    a, b = _speech_bounds(y)
    y = y[a:b].astype(np.float32)
    f = min(len(y) // 4, int(0.012 * SR))
    if f > 0:
        ramp = np.linspace(0, 1, f, dtype=np.float32)
        y[:f] *= ramp
        y[-f:] *= ramp[::-1]
    return y


def acoustic_checks(y):
    """Gates 6 (head grunt, auto-muted) + 7 (cut word) from the engine."""
    import soundfile as sf
    try:
        import acoustic_gates as ag
    except Exception as e:
        return y, {"skipped": repr(e)}
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        sf.write(path, y, SR)
        g6 = ag.head_grunt_gate(path, apply=True)
        y2, _ = sf.read(path, dtype="float32")
        g7 = ag.cut_word_gate(path)
        return y2, {"gate6_head_grunt": {"muted": bool(g6.get("action")),
                                         "pass": g6["pass"]},
                    "gate7_cut_word": {"pass": g7["pass"],
                                       "fails": g7["fails"]}}
    except Exception as e:
        return y, {"error": repr(e)}
    finally:
        os.unlink(path)


_ASR = {}


def asr_model(device):
    if device not in _ASR:
        from faster_whisper import WhisperModel
        if device.startswith("cuda"):
            name = os.environ.get("TURBO_ASR_MODEL", "large-v3-turbo")
            _ASR[device] = WhisperModel(name, device="cuda",
                                        device_index=int(device.split(":")[1]),
                                        compute_type="float16")
        else:
            name = os.environ.get("TURBO_ASR_MODEL", "small")
            _ASR[device] = WhisperModel(name, device="cpu", compute_type="int8")
    return _ASR[device]


def _norm_chars(s):
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _cer(ref, hyp):
    r, h = _norm_chars(ref).replace(" ", ""), _norm_chars(hyp).replace(" ", "")
    if not r:
        return 0.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i] + [0] * len(h)
        for j, hc in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / len(r)


def asr_check(y, text, lang, device):
    m = asr_model(device)
    segs, info = m.transcribe(y, language=lang, beam_size=1,
                              vad_filter=False, without_timestamps=True)
    hyp = " ".join(s.text for s in segs)
    return {"hyp": hyp, "cer": round(_cer(text, hyp), 3)}


# ---------------------------------------------------------- generation --
def gen_batch(model, prompt, texts, lang, seed, steps):
    import torch
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    out = model.generate(text=texts, language=[LANG_NAME[lang]] * len(texts),
                         voice_clone_prompt=[prompt] * len(texts),
                         speed=1.0, num_step=steps)
    return [np.asarray(a, dtype=np.float32) for a in out]


def worker(device, jobs, args, q=None):
    """jobs: list of (lang, idx, spoken_text). Returns {(lang, idx): take}."""
    model = load_model(device)
    prompts = {}
    for lang in sorted({j[0] for j in jobs}):
        wav, txt = args.refs[lang]
        rt = open(txt, encoding="utf-8").read().strip() if txt and os.path.exists(txt) else None
        prompts[lang] = model.create_voice_clone_prompt(wav, rt)
    use_asr = args.asr if args.asr is not None else device.startswith("cuda")
    results = {}
    pending = list(jobs)
    for rnd in range(args.max_rolls):
        if not pending:
            break
        seed = args.seed + 1000 * rnd
        # length-sorted batches: similar lengths pad together -> faster
        pending.sort(key=lambda j: (j[0], len(j[2])))
        new = []
        for lang in sorted({j[0] for j in pending}):
            L = [j for j in pending if j[0] == lang]
            for b in range(0, len(L), args.batch):
                chunk = L[b:b + args.batch]
                t0 = time.time()
                audios = gen_batch(model, prompts[lang], [c[2] for c in chunk],
                                   lang, seed + b, args.steps)
                dt = time.time() - t0
                for (lg, idx, txt), y in zip(chunk, audios):
                    y = trim(y)
                    y, ac = acoustic_checks(y)
                    rec = {"round": rnd + 1, "seed": seed + b, "device": device,
                           "dur_s": round(len(y) / SR, 2),
                           "spc": len(y) / SR / max(1, len(txt)),
                           "batch_gen_s": round(dt, 2), "acoustic": ac}
                    if use_asr:
                        rec["asr"] = asr_check(y, txt, lg, device)
                    new.append(((lg, idx, txt), y, rec))
        # decide
        still = []
        for key, y, rec in new:
            lg, idx, txt = key
            prev = results.get((lg, idx))
            rec["fails"] = []
            if not rec["acoustic"].get("gate7_cut_word", {}).get("pass", True):
                rec["fails"].append("cut_word")
            if "asr" in rec and rec["asr"]["cer"] > args.max_cer[lg]:
                rec["fails"].append(f"words (CER {rec['asr']['cer']})")
            entry = prev or {"takes": []}
            entry["takes"].append({k: v for k, v in rec.items()})
            entry["text"] = txt
            # keep the best take so far (fewest fails, then lowest CER)
            score = (len(rec["fails"]), rec.get("asr", {}).get("cer", 0))
            if "best" not in entry or score < entry["best_score"]:
                entry["best"], entry["best_score"] = y, score
            results[(lg, idx)] = entry
            if rec["fails"]:
                still.append(key)
        pending = still
        # pace check across the whole job (relative to the job median)
        if rnd + 1 < args.max_rolls:
            for lang in {k[0] for k in results}:
                spcs = [len(e["best"]) / SR / max(1, len(e["text"]))
                        for k, e in results.items() if k[0] == lang]
                med = float(np.median(spcs))
                for k, e in results.items():
                    if k[0] != lang:
                        continue
                    r = len(e["best"]) / SR / max(1, len(e["text"])) / med
                    if not (PACE_BAND[0] <= r <= PACE_BAND[1]) and len(e["text"]) > 25:
                        e["takes"][-1].setdefault("fails", []).append(
                            f"pace x{r:.2f} of median")
                        e["best_score"] = (9, 9)
                        if (k[0], k[1], e["text"]) not in pending:
                            pending.append((k[0], k[1], e["text"]))
    out = {k: {"audio": v["best"], "takes": v["takes"],
               "pass": v["best_score"][0] == 0} for k, v in results.items()}
    if q is not None:
        q.put((device, out))
    return out


# ------------------------------------------------------------ assembly --
def assemble(takes, lang, out_mp3, sentences):
    gap = np.zeros(int(GAP_S[lang] * SR), dtype=np.float32)
    rms = [float(np.sqrt(np.mean(t ** 2)) + 1e-9) for t in takes]
    target = float(np.median(rms))
    pieces, srt, t = [], [], 0.0
    for i, (y, s) in enumerate(zip(takes, sentences)):
        y = y * min(4.0, target / (np.sqrt(np.mean(y ** 2)) + 1e-9))
        start = t
        pieces.append(y)
        t += len(y) / SR
        srt.append((start, t, s))
        if i < len(takes) - 1:
            pieces.append(gap)
            t += len(gap) / SR
    full = np.concatenate(pieces) if pieces else np.zeros(SR, np.float32)
    import soundfile as sf
    raw = out_mp3[:-4] + ".raw.wav"
    sf.write(raw, full, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
                    "loudnorm=I=-15:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1",
                    "-b:a", "192k", out_mp3], check=True)
    os.unlink(raw)

    def ts(x):
        h, r = divmod(x, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
    with open(out_mp3[:-4] + ".srt", "w", encoding="utf-8") as f:
        for i, (a, b, s) in enumerate(srt, 1):
            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{s}\n\n")
    return t


# ---------------------------------------------------------------- main --
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for l in ("te", "hi", "en"):
        ap.add_argument(f"--{l}", help=f"{LANG_NAME[l]} script (.txt)")
        ap.add_argument(f"--ref-{l}", help=f"{LANG_NAME[l]} reference wav")
        ap.add_argument(f"--ref-text-{l}", help="its exact transcript (.txt)")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--device", default="auto", help="auto | cpu | cuda:0")
    ap.add_argument("--batch", type=int, default=0, help="sentences per batch (0 = auto)")
    ap.add_argument("--steps", type=int, default=32,
                    help="diffusion steps (32 = approved quality; 16 = ~2x faster)")
    ap.add_argument("--max-rolls", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1234)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--asr", dest="asr", action="store_true", default=None,
                   help="force the Whisper word check on")
    g.add_argument("--no-asr", dest="asr", action="store_false")
    args = ap.parse_args()

    langs = [l for l in ("te", "hi", "en") if getattr(args, l)]
    if not langs:
        ap.error("give at least one of --te / --hi / --en")
    os.makedirs(args.outdir, exist_ok=True)
    args.refs = {}
    for l in langs:
        wav = getattr(args, f"ref_{l}") or os.path.join(HERE, REF_DEFAULT[l][0])
        txt = getattr(args, f"ref_text_{l}") or os.path.join(HERE, REF_DEFAULT[l][1])
        args.refs[l] = (wav, txt)
    args.max_cer = {"te": 0.45, "hi": 0.35, "en": 0.25}

    T0 = time.time()
    devices = pick_devices(args.device)
    if not args.batch:
        args.batch = 16 if devices[0].startswith("cuda") else 4
    scripts, jobs = {}, []
    for l in langs:
        raw = open(getattr(args, l), encoding="utf-8").read()
        sents, spoken, meta = prep_script(raw, l)
        scripts[l] = (sents, spoken, meta)
        jobs += [(l, i, s) for i, s in enumerate(spoken)]
    print(f"[turbo] {len(jobs)} sentences, {len(langs)} language(s), "
          f"devices={devices}, batch={args.batch}, steps={args.steps}", flush=True)

    # spread work over devices (round-robin by length so each gets a fair share)
    jobs_sorted = sorted(jobs, key=lambda j: -len(j[2]))
    shards = [jobs_sorted[i::len(devices)] for i in range(len(devices))]
    results = {}
    if len(devices) == 1:
        results.update(worker(devices[0], shards[0], args))
    else:
        import torch.multiprocessing as mp
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        ps = [ctx.Process(target=worker, args=(d, s, args, q))
              for d, s in zip(devices, shards)]
        for p in ps:
            p.start()
        for _ in ps:
            _, r = q.get()
            results.update(r)
        for p in ps:
            p.join()
    gen_wall = time.time() - T0

    summary = {}
    for l in langs:
        sents, spoken, meta = scripts[l]
        takes = [results[(l, i)]["audio"] for i in range(len(sents))]
        out = os.path.join(args.outdir, f"{l}.mp3")
        dur = assemble(takes, l, out, sents)
        failed = [i + 1 for i in range(len(sents)) if not results[(l, i)]["pass"]]
        qc = {"language": l, "reference": args.refs[l][0], "speed": "LOCKED 1.0 (no stretch)",
              "audio_minutes": round(dur / 60, 2), "sentences": len(sents),
              "needs_ear_check": failed, **meta,
              "per_sentence": [{"n": i + 1, "text": sents[i], "spoken": spoken[i],
                                "pass": results[(l, i)]["pass"],
                                "takes": [{k: v for k, v in t.items() if k != "spc"}
                                          for t in results[(l, i)]["takes"]]}
                               for i in range(len(sents))]}
        json.dump(qc, open(out[:-4] + ".qc.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, default=str)
        summary[l] = {"minutes": round(dur / 60, 2), "needs_ear_check": failed}
    wall = time.time() - T0
    total_audio = sum(v["minutes"] for v in summary.values()) * 60
    summary["_timing"] = {"wall_s": round(wall, 1), "generation_s": round(gen_wall, 1),
                          "audio_s": round(total_audio, 1),
                          "x_realtime": round(total_audio / wall, 2) if wall else None,
                          "devices": devices}
    json.dump(summary, open(os.path.join(args.outdir, "summary.json"), "w"),
              indent=1)
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
