"""turbo_gen.py — production-shaped IndicF5 runner for the 20-in-10 path.

One runner voices ONE chunk of a full script (round-robin slice of the
lines file), loading IndicF5 exactly once. Per sentence it generates
whole takes ONE AT A TIME and stops at the first take that meets the
ear-approved ship bar (Ajju, fixed13 — the same bar indicf5_gen.py and
engine.ship_decision implement):

    gate1 (no-hint language) + gate2 (ghost scan) + Resemblyzer
    identity >= 0.85 + pace within 1.9-2.5 wps, all on the SAME take.

Cheap pre-selection keeps the expensive ASR gate suite off hopeless
takes: a take is only gated if (a) its total-duration words/sec is in
the generous band [1.5, 2.9] (the real pace gate runs on the ASR span,
which is <= total duration, so outside this band a pace pass is
impossible or implausible) and (b) its identity already clears 0.85.
A take that fails the ship bar never ships; a sentence with no
shipping take after MAX_TAKES rolls is recorded as failed and is the
wave-2 workflow's problem. Non-shipping take audio is deleted — only
the shipped take (s<idx>.wav) and the per-sentence record (s<idx>.json)
leave the runner.

Env:
  LINES_PATH  lines file (repo-relative or absolute). Plain format: one
              sentence per line, original index = 1-based position.
              Indexed format (wave 2): "<orig_index>\\t<sentence>".
  CHUNK_IDX   this runner's chunk index (0-based)
  NCHUNKS     total chunks in this wave
  WAVE        1 or 2 (recorded in the output JSON)
  MAX_TAKES   whole takes per sentence before giving up (default 2)
  REF_NAME    refs.json key (default natspan2 — the fixed13 default;
              its settings speed anchor is 1.0 = no correction)
  SPEED       generation speed override; empty = settings anchor
  LANG        gate language (default te)
  OUTDIR      output dir (default out)
"""
import json
import os
import sys
import time
import traceback

import numpy as np
import soundfile as sf
import torch

torch.set_num_threads(4)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
T0 = time.time()


def log(msg):
    print(f"[T+{time.time() - T0:7.1f}s] {msg}", flush=True)


OUT = os.environ.get("OUTDIR", "out")
os.makedirs(OUT, exist_ok=True)
CHUNK_IDX = int(os.environ.get("CHUNK_IDX", "0"))
NCHUNKS = int(os.environ.get("NCHUNKS", "1"))
WAVE = int(os.environ.get("WAVE", "1"))
MAX_TAKES = int(os.environ.get("MAX_TAKES", "2"))
LANG = os.environ.get("LANG", "te").strip().lower()
REF_NAME = os.environ.get("REF_NAME", "natspan2")
IDENTITY_MIN = 0.85
WPS_MIN, WPS_MAX = 1.9, 2.5
CHEAP_MIN, CHEAP_MAX = 1.5, 2.9  # total-duration wps pre-band (see docstring)


def load_items():
    lp = os.environ.get("LINES_PATH", "")
    p = lp if os.path.isabs(lp) else os.path.join(ROOT, lp)
    items = []
    with open(p, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            if "\t" in ln:
                idx_s, text = ln.split("\t", 1)
                items.append((int(idx_s), text.strip()))
            else:
                items.append((len(items) + 1, ln.strip()))
    items.sort(key=lambda x: x[0])
    return items


ITEMS = load_items()
MINE = [it for pos, it in enumerate(ITEMS) if pos % NCHUNKS == CHUNK_IDX]
log(f"runner chunk {CHUNK_IDX}/{NCHUNKS} wave {WAVE}: "
    f"{len(MINE)} of {len(ITEMS)} sentences, ref={REF_NAME}")

# ------------------------------------------------------------ gates setup --
import gates  # noqa: E402

_m = gates.get_model()
_orig_transcribe = _m.transcribe


def _transcribe_no_thresholds(*a, **kw):
    kw.setdefault("log_prob_threshold", None)
    kw.setdefault("no_speech_threshold", None)
    return _orig_transcribe(*a, **kw)


_m.transcribe = _transcribe_no_thresholds
log("whisper gate model loaded")

# --------------------------------------------------------------- identity --
from resemblyzer import VoiceEncoder, preprocess_wav  # noqa: E402

_enc = VoiceEncoder()
_ref_emb = _enc.embed_utterance(
    preprocess_wav(os.path.join(ROOT, "voice", "english-reference.wav")))
log("resemblyzer encoder loaded")


def identity(path):
    emb = _enc.embed_utterance(preprocess_wav(path))
    return round(float(np.dot(_ref_emb, emb)), 3)


def pace_of(rep, n_words):
    rows = [r for r in rep["gate3_pronunciation"]["rows"]
            if r.get("start") is not None]
    if not rows:
        return None
    span = rows[-1]["end"] - rows[0]["start"]
    durs = [r["end"] - r["start"] for r in rows]
    med = float(np.median(durs)) if durs else 0.0
    eff = span + med
    return round(n_words / eff, 3) if eff > 0 else None


def main():
    settings = gates.load_settings()
    speed_env = os.environ.get("SPEED", "").strip()
    if speed_env:
        speed = float(speed_env)
    else:
        anchor = (settings.get("telugu_indicf5", {})
                  .get("speed_anchors", {}).get(REF_NAME, {}))
        speed = float(anchor.get("speed", 1.0))
    refs = json.load(open(os.path.join(ROOT, "voice", "refs", "refs.json"),
                          encoding="utf-8"))["refs"]
    ref = refs[REF_NAME]
    ref_wav = os.path.join(ROOT, ref["wav"])
    ref_text = ref["text"]

    t_load = time.time()
    from transformers import AutoModel
    model = AutoModel.from_pretrained("Aditya02/IndicF5",
                                      trust_remote_code=True, speed=speed)
    model.config.speed = speed
    log(f"IndicF5 loaded in {time.time() - t_load:.1f}s, speed={speed}")

    summary = {"chunk": CHUNK_IDX, "nchunks": NCHUNKS, "wave": WAVE,
               "ref": REF_NAME, "speed": speed, "lang": LANG,
               "model_load_s": round(time.time() - t_load, 1),
               "sentences": []}
    for si, text in MINE:
        words = text.replace(",", " ").replace(".", " ").split()
        rec = {"sentence": si, "wave": WAVE, "chunk": CHUNK_IDX,
               "ref": REF_NAME, "speed": speed, "ship": False,
               "takes": []}
        t_sent = time.time()
        for k in range(1, MAX_TAKES + 1):
            tk = {"roll": k}
            tmp = os.path.join(OUT, f".tmp_s{si}_t{k}.wav")
            try:
                t_g = time.time()
                audio = model(text, ref_audio_path=ref_wav,
                              ref_text=ref_text)
                tk["gen_s"] = round(time.time() - t_g, 1)
                if audio.dtype == np.int16:
                    audio = audio.astype(np.float32) / 32768.0
                audio = np.array(audio, dtype=np.float32)
                sf.write(tmp, audio, 24000)
                dur = len(audio) / 24000.0
                tk["duration_s"] = round(dur, 2)
                twps = len(words) / dur if dur > 0 else 0.0
                tk["total_wps"] = round(twps, 3)
                if not (CHEAP_MIN <= twps <= CHEAP_MAX):
                    tk["skip"] = "duration pre-band"
                    rec["takes"].append(tk)
                    os.unlink(tmp)
                    log(f"s{si} t{k}: dur={dur:.2f}s total_wps={twps:.2f} "
                        f"-> cheap reject (gen {tk['gen_s']}s)")
                    continue
                t_i = time.time()
                ident = identity(tmp)
                tk["identity"] = ident
                tk["identity_s"] = round(time.time() - t_i, 1)
                if ident < IDENTITY_MIN:
                    tk["skip"] = "identity pre-check"
                    rec["takes"].append(tk)
                    os.unlink(tmp)
                    log(f"s{si} t{k}: id={ident} -> identity reject")
                    continue
                t_a = time.time()
                rep = gates.run_all_gates(tmp, LANG, text)
                tk["gates_s"] = round(time.time() - t_a, 1)
                wps = pace_of(rep, len(words))
                tk["wps"] = wps
                tk["pace_pass"] = bool(wps is not None
                                       and WPS_MIN <= wps <= WPS_MAX)
                tk["gate1_pass"] = bool(
                    rep["gate1_nohint_language"]["pass"])
                tk["gate2_pass"] = bool(rep["gate2_ghost_words"]["pass"])
                tk["gate_pass_all5"] = bool(rep["pass"])
                ship = bool(tk["gate1_pass"] and tk["gate2_pass"]
                            and tk["pace_pass"])
                tk["ship"] = ship
                rec["takes"].append(tk)
                if ship:
                    final = os.path.join(OUT, f"s{si}.wav")
                    os.replace(tmp, final)
                    rec["ship"] = True
                    rec["shipped_take"] = k
                    rec["identity"] = ident
                    rec["wps"] = wps
                    rec["duration_s"] = tk["duration_s"]
                    log(f"s{si} t{k}: SHIP id={ident} wps={wps} "
                        f"gen={tk['gen_s']}s gates={tk['gates_s']}s")
                    break
                os.unlink(tmp)
                log(f"s{si} t{k}: gates fail g1={tk['gate1_pass']} "
                    f"g2={tk['gate2_pass']} pace={wps} "
                    f"(gates {tk['gates_s']}s)")
            except Exception as e:
                tk["error"] = f"{type(e).__name__}: {e}"
                rec["takes"].append(tk)
                if os.path.exists(tmp):
                    os.unlink(tmp)
                traceback.print_exc()
                log(f"s{si} t{k}: ERROR {tk['error']}")
        rec["sentence_s"] = round(time.time() - t_sent, 1)
        with open(os.path.join(OUT, f"s{si}.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1)
        summary["sentences"].append(
            {k2: rec.get(k2) for k2 in
             ("sentence", "ship", "shipped_take", "identity", "wps",
              "duration_s", "sentence_s")})
        log(f"s{si}: done ship={rec['ship']} in {rec['sentence_s']}s")
    summary["total_s"] = round(time.time() - T0, 1)
    summary["shipped"] = sum(1 for s in summary["sentences"] if s["ship"])
    with open(os.path.join(OUT, f"turbo_summary_chunk{CHUNK_IDX}.json"),
              "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    log(f"CHUNK DONE shipped {summary['shipped']}/{len(MINE)} "
        f"total {summary['total_s']}s")
    print("TURBO_GEN_DONE", flush=True)


if __name__ == "__main__":
    main()
