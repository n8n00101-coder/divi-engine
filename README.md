# Julie AI Voice Engine

A gated voice-clone engine for one finalized house voice — **Julie AI** — in
three languages: **English, Telugu, Hindi**.

You give it text. It generates the voice-over, then **proves** the take is
clean before it lets you have it: every take must pass five quality gates,
and the engine re-rolls automatically (up to 6 attempts per sentence) until
one does. If no take passes, the engine exits non-zero, writes the gate
table, and **refuses to write a final mp3**. Defective audio is not a
deliverable this tool can produce.

```
python3 engine.py --text "…" --lang te --out line.mp3
python3 engine.py --text-file script.txt --lang en --out out.mp3 --bed
python3 engine.py --text-file script.txt --lang hi --out out.mp3 --rolls 8
```

Next to every mp3 the engine writes `<name>.qc.json` — the full QC report:
per sentence, per roll, every gate's measurements, and which take was
chosen and why.

## The voice

One female Indian narration voice, measured and locked on 2026-11-14:

- **English** — zero-shot clone via [Chatterbox TTS](https://github.com/resemble-ai/chatterbox)
  (MIT), exaggeration **0.35**, phrase-by-phrase generation (pauses only
  where her phrases break: 0.66 s after a sentence, 0.06 s at commas), and
  a pace guard against her measured onset rate (5.24/s). Her profile:
  F0 median 221 Hz, controlled range 168–311 Hz, emphasis by *stretching*
  hinge words rather than pitch drama. **Status: LOCKED / owner-approved.**
- **Telugu** — [IndicF5](https://huggingface.co/spaces/ai4bharat/IndicF5)
  zero-shot clone from her Telugu reference. Pace is set by take
  *selection* (the owner's ear calibration: −30% vs the raw first take);
  time-stretching Telugu is banned — it stretched silences and broke the
  channel rhythm.
- **Hindi** — IndicF5 cross-lingual from the same Telugu reference, with
  the owner's approved +20% pace calibration (one atempo 1.20 per take,
  always logged). No Hindi reference sample exists yet, so Hindi is marked
  UNVERIFIED against the channel until one is supplied.

Full measurements: [`PRONUNCIATION-PROFILE.md`](PRONUNCIATION-PROFILE.md).
References and locked values: [`voice/`](voice/) (`settings.json` is the
single source of truth — the gates read their thresholds from it).

## The five gates — and the defect each one exists to kill

Every defect below was shipped by hand once, and caught by a human ear.
The gates are the permanent fix: they run **inside** the engine, on every
take, before anything is assembled.

| # | Gate | The defect it kills |
|---|------|---------------------|
| 1 | **No-hint language identity** — the take is transcribed with *no* language hint; the detected language must be the target (prob ≥ 0.80, Hindi ≥ 0.90) | A "Telugu" sample that detected as **Punjabi (0.486)** unhinted. Forcing the language into the checker masks between-language diction; detecting blind does not. |
| 2 | **Ghost-word scan** — the unhinted transcript is searched, in Latin *and* phonetic space, for foreign words that match no script word | The same sample's unhinted transcript literally contained **"feel safer"** four times — hallucinated English at phrase joints, invisible to any forced-language check. |
| 3 | **Pronunciation** — forced-language ASR word probabilities (every word ≥ 0.50) plus phonetic similarity per word, with missing/merged/smeared words rejected | Conjunct-heavy and long words (క్షణం, తాత్కాలికంగా) smeared or merged while a sentence-level "all words present" check passed them. |
| 4 | **PHYS — swallowed words** — per word: duration vs syllable count (absolute floor + 60% of take pace), mid-word energy collapse to the noise floor, abrupt-cut tails | Words **eaten mid-word** — ASR-readable, but audibly truncated. A sentence-level check cannot see this; acoustics can. (Validated: the owner-approved clean sample scores zero hard flags.) |
| 5 | **Pitch band** — F0 median must sit in **185–220 Hz** | Take-to-take pitch-centre wander (163–251 Hz across splices) making one voice sound like several. Out-of-band takes are re-rolled, **never pitch-shifted**. |

Assembly is gated too: sentence takes are level-matched with plain gain
only (stacked processing measurably eats voice identity), joined with one
0.6 s gap, every pause is gated to **true digital silence** (the IndicF5
route leaves a ~91 Hz hum in gaps), and exactly **one** loudnorm pass
(≈ −15 LUFS) finishes the file. `--bed` adds the channel's quiet piano bed
≈ 11 dB under the voice.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ffmpeg -version   # ffmpeg must be on PATH (assembly + loudnorm)
```

Notes:

- The English route downloads the Chatterbox model once (CPU is fine, it
  is just slow — a few minutes per take on a small machine).
- The gates use faster-whisper `base` locally; set `JULIE_WHISPER_MODEL`
  to a model name or a local model directory to override.
- Telugu/Hindi generation calls the free ai4bharat/IndicF5 Hugging Face
  Space — no API key needed. Keep your proxy env as-is for that call; the
  engine isolates it in a subprocess so it never contaminates the local
  ASR gates.

## Connect your own model (fast path)

The built-in routes are free, and you pay in time instead: the IndicF5
Space has a public queue and outage streaks, and Chatterbox on a local
CPU takes minutes per take. If you run a faster model yourself — or
have an ElevenLabs voice — connect it and generation stops being the
bottleneck:

1. `git pull` to get the pluggable-backend build.
2. Pick ONE backend (environment variables only — keys never go in a
   file, and never appear in QC reports):
   - **ElevenLabs:** `export JULIE_TTS_BACKEND=elevenlabs`,
     `export ELEVENLABS_API_KEY=…`, `export JULIE_EL_VOICE_ID=…`
     (optional `JULIE_EL_MODEL`, default `eleven_multilingual_v2`; the
     voice id can instead live in `voice/settings.json` under
     `backends.elevenlabs.voice_id`). The voice then comes from that
     ElevenLabs voice id — the reference wavs are not used.
   - **Your own model server:** `export JULIE_TTS_BACKEND=http` and
     `export JULIE_TTS_URL=http://your-server/tts` (optional
     `JULIE_TTS_KEY`, sent as `Authorization: Bearer …`). Server
     contract: accept a POST with JSON `{"text", "lang", "voice"}` and
     return audio bytes (mp3 or wav) as the response body.
3. Run the engine exactly as before — same CLI, same languages.

Nothing about quality control changes: the five gates, the re-roll loop
and the QC report apply on top of **any** backend, each take's backend
is recorded in `<name>.qc.json`, and a take that fails the gates is
rejected no matter how fast it was generated. HTTP backends time out at
120 s per take and fail loudly, naming the backend — no silent hangs.
Leave `JULIE_TTS_BACKEND` unset to return to the default free routes.

## Honest limits

- **IndicF5 diction varies per take.** Some takes will always smear a hard
  word or sprout a ghost word. The engine's answer is not to fix them in
  post — it is to *reject and re-roll*. Expect several rolls on hard
  sentences; expect the occasional honest failure (exit 2 + gate table)
  rather than a defective file.
- **The IndicF5 Space has outage streaks** (ZeroGPU). Generation retries
  with backoff, but a bad hour is a bad hour.
- ASR probabilities are a proxy for diction, calibrated against the human
  ear that caught these defects. The ear outranks the numbers — if a
  passing take sounds wrong to you, open an issue with the QC report.
- Hindi is cross-lingual and UNVERIFIED against its channel (see above).

## Layout

```
engine.py                 CLI: generate -> gate -> re-roll -> assemble
backends.py               pluggable TTS backends (defaults, elevenlabs, http)
gates.py                  the five gates, importable
phonetics.py              Telugu / Devanagari / ASR-script phonetic normalizers
voice/
  settings.json           ALL locked settings (single source of truth)
  english-reference.wav   canonical 25 s English reference (+ .m4a original)
  telugu-reference.wav    Telugu reference (+ its transcript .txt)
  samples/                owner-approved samples per language
  VOICE.md                voice provenance
PRONUNCIATION-PROFILE.md  the measured delivery profile the settings encode
```

## License

MIT — see `LICENSE`. The reference voice is a real person's voice, supplied
by its owner for this project; use the engine and the voice accordingly.
