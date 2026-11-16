"""indicf5-batch runner: WHOLE-SENTENCE IndicF5 takes + full gates per take.

Runs on a GitHub Actions runner (matrix of 10). Each runner loads IndicF5
once, generates ROLLS whole takes of each demo sentence with ONE assigned
reference (rotated by runner index over voice/refs/refs.json:
span1/span2/span3/te3), and gates EVERY take with the full suite:

  - gates.run_all_gates (no-hint language detect, ghost scan, forced word
    probs + phonetic sim, PHYS swallowed-word, F0 pitch band)
  - Resemblyzer identity vs voice/english-reference.wav (the 25 s sample),
    pass >= 0.85
  - pace: script words / effective speech span, pass 1.9-2.5 words/s
    (her channel band is ~2.2 wps)

A take is a FULL PASS only if every gate passes on that same take.
All takes + per-take gate JSON are written to OUTDIR for harvest; nothing
is assembled here.

Env: RUNNER_INDEX (0..9), ROLLS (per sentence, default 6), OUTDIR (out),
LINES_PATH (optional lines file in this repo — one sentence per line;
written by engine.py's dispatch_mass_rolls for arbitrary te/hi scripts.
Default: the built-in demo pair.)
"""
import json
import os
import sys
import traceback

import numpy as np
import soundfile as sf
import torch

torch.set_num_threads(4)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
OUT = os.environ.get("OUTDIR", "out")
os.makedirs(OUT, exist_ok=True)
IDX = int(os.environ.get("RUNNER_INDEX", "0"))
ROLLS = int(os.environ.get("ROLLS", "6"))
# fixed10 (2026-11-16): generation-side SPEED control. This IndicF5 build
# takes speed as a CONFIG parameter; forward() reads config.speed per call
# and infer_process scales the generated duration by 1/speed
# (f5_tts/infer/utils_infer.py: duration = ref_len + ref_len/ref_text_len
# * gen_text_len / speed). speed<1 = slower/longer. Default 1.0 = the
# behaviour of every previous wave.
SPEED = float(os.environ.get("SPEED", "1.0"))

DEMO_SENTS = {
    1: "మీరు నిద్రలోకి జారుకున్న క్షణం నుంచి, మీ మెదడు పని ఆపదు. నిజానికి, దాని అసలు పని అప్పుడే మొదలవుతుంది.",
    2: "రోజంతా మీరు చూసినవి, విన్నవి, నేర్చుకున్నవి అన్నీ మెదడులో తాత్కాలికంగా దాచుకుంటాయి. కానీ అవి అక్కడే ఉంటే, మరుసటి రోజు కల్లా కలిసిపోతాయి.",
}


def load_sentences():
    """Sentences to voice: the LINES_PATH file when set and present
    (one sentence per line, numbered from 1 in file order), else the
    built-in demo pair."""
    lp = os.environ.get("LINES_PATH", "")
    if lp:
        p = lp if os.path.isabs(lp) else os.path.join(ROOT, lp)
        if os.path.exists(p):
            lines = [ln.strip() for ln in open(p, encoding="utf-8")
                     if ln.strip()]
            if lines:
                return {i + 1: t for i, t in enumerate(lines)}
    return DEMO_SENTS


SENTS = load_sentences()
# Ref rotation: REF_ORDER env (comma-separated refs.json keys) overrides the
# fixed6 default — fixed7 (2026-11-16) uses it to run natural-pace refs only.
REF_ORDER = [x.strip() for x in
             os.environ.get("REF_ORDER", "").split(",") if x.strip()] \
    or ["span1", "span2", "span3", "te3"]
IDENTITY_MIN = 0.85
WPS_MIN, WPS_MAX = 1.9, 2.5

# ------------------------------------------------------------ gates setup --
import gates  # noqa: E402  (import strips proxy env — harmless on a runner)

# fixed4 calibration (2026-11-15): faster-whisper's DEFAULT log-prob /
# no-speech thresholds silently drop ALL segments on this material. Disable
# both on the shared model instance before any gate runs.
_m = gates.get_model()
_orig_transcribe = _m.transcribe


def _transcribe_no_thresholds(*a, **kw):
    kw.setdefault("log_prob_threshold", None)
    kw.setdefault("no_speech_threshold", None)
    return _orig_transcribe(*a, **kw)


_m.transcribe = _transcribe_no_thresholds

# --------------------------------------------------------------- identity --
from resemblyzer import VoiceEncoder, preprocess_wav  # noqa: E402

_enc = VoiceEncoder()
_ref_emb = _enc.embed_utterance(
    preprocess_wav(os.path.join(ROOT, "voice", "english-reference.wav")))


def identity(path):
    emb = _enc.embed_utterance(preprocess_wav(path))
    return round(float(np.dot(_ref_emb, emb)), 3)


def pace_of(rep, n_words):
    """Words/sec over the ASR speech span (+ one median word duration)."""
    rows = [r for r in rep["gate3_pronunciation"]["rows"]
            if r.get("start") is not None]
    if not rows:
        return None, None
    span = rows[-1]["end"] - rows[0]["start"]
    durs = [r["end"] - r["start"] for r in rows]
    med = float(np.median(durs)) if durs else 0.0
    eff = span + med
    return (round(n_words / eff, 3) if eff > 0 else None), round(span, 2)


def main():
    refs = json.load(open(os.path.join(ROOT, "voice", "refs", "refs.json"),
                          encoding="utf-8"))["refs"]
    ref_name = REF_ORDER[IDX % len(REF_ORDER)]
    ref = refs[ref_name]
    ref_wav = os.path.join(ROOT, ref["wav"])
    ref_text = ref["text"]
    print(f"runner {IDX}: ref={ref_name} rolls={ROLLS}", flush=True)

    # f5_tts must resolve to the AI4Bharat/IndicF5 repo's fork (installed
    # by the workflow): the HF snapshot bundles an OLDER f5_tts whose
    # load_model() still requires ckpt_path, which this model.py does not
    # pass (wave-4 failure, 2026-11-15). Do NOT put the snapshot on
    # sys.path — it would shadow the correct fork with the bundled one.
    from transformers import AutoModel
    model = AutoModel.from_pretrained("Aditya02/IndicF5",
                                      trust_remote_code=True, speed=SPEED)
    model.config.speed = SPEED  # forward() reads config at call time
    print(f"IndicF5 loaded, config.speed={model.config.speed}", flush=True)

    summary = {"runner": IDX, "ref": ref_name, "rolls": ROLLS, "takes": []}
    for si, text in SENTS.items():
        words = text.replace(",", " ").replace(".", " ").split()
        for k in range(1, ROLLS + 1):
            name = f"s{si}_r{IDX}_t{k}"
            wp = os.path.join(OUT, name + ".wav")
            rec = {"take": name, "sentence": si, "roll": k, "ref": ref_name,
                   "speed": SPEED}
            try:
                audio = model(text, ref_audio_path=ref_wav,
                              ref_text=ref_text)
                if audio.dtype == np.int16:
                    audio = audio.astype(np.float32) / 32768.0
                audio = np.array(audio, dtype=np.float32)
                sf.write(wp, audio, 24000)
                rec["duration_s"] = round(len(audio) / 24000.0, 2)
                rep = gates.run_all_gates(wp, "te", text)
                ident = identity(wp)
                wps, span = pace_of(rep, len(words))
                rec["gate_pass"] = bool(rep["pass"])
                rec["identity"] = ident
                rec["identity_pass"] = bool(ident >= IDENTITY_MIN)
                rec["wps"] = wps
                rec["asr_span"] = span
                rec["pace_pass"] = bool(wps is not None
                                        and WPS_MIN <= wps <= WPS_MAX)
                rec["full_pass"] = bool(rep["pass"] and rec["identity_pass"]
                                        and rec["pace_pass"])
                rec["gates"] = rep
            except Exception as e:  # keep rolling; harvest sees the error
                rec["error"] = f"{type(e).__name__}: {e}"
                rec["full_pass"] = False
                traceback.print_exc()
            with open(os.path.join(OUT, name + ".json"), "w",
                      encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1)
            summary["takes"].append(
                {k2: rec.get(k2) for k2 in
                 ("take", "sentence", "roll", "ref", "speed", "duration_s",
                  "full_pass", "gate_pass", "identity", "wps", "error")})
            print(f"{name}: full_pass={rec.get('full_pass')} "
                  f"gates={rec.get('gate_pass')} id={rec.get('identity')} "
                  f"wps={rec.get('wps')} dur={rec.get('duration_s')} "
                  f"err={rec.get('error')}", flush=True)
    with open(os.path.join(OUT, f"runner{IDX}_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print("INDICF5_GEN_DONE", flush=True)


if __name__ == "__main__":
    main()
