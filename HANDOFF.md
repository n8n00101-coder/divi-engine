# HANDOFF — Divi Engine voice-over tool (read this first, then continue from NEXT STEPS)

You are continuing an existing project. Everything below is verified state, not a plan.

## What this is
Paste a script → get a finished voice-over in Telugu, Hindi and English, in the channel voice of
WHO TAUGHT US (youtube.com/@who_taught_us-telugu, @who_taught_us--hindi, @who_taught_us).
100% free, open-source only. The owner has NO money — never suggest paid APIs.

## Where everything lives
- GitHub repo (source of truth, always pull latest): https://github.com/n8n00101-coder/julie-ai-voice-engine
- Backup zip of the same code: Kaggle dataset `arjunchotuchotu/divi-engine-turbo` (private).
- Kaggle account for GPU runs: username `arjunchotuchotu` (phone-verified, GPU T4 x2, 30 h/week).
  The owner pastes the Kaggle API key into your vault when you ask. Never print key values.

## Key files
- `turbo.py` — the tool: batched OmniVoice generation + faster-whisper check + assembly (mp3 + srt + QC report).
- `textnorm.py` — numbers/years/% → spoken words per language.
- `DiviTurbo.ipynb`, `kaggle_run.py` — Kaggle runners.
- `voice/settings.json` — SOURCE OF TRUTH for voice/speed/gates. Never change locked values without a new ear approval from the owner.
- `voice/refs/` — Telugu refs natspan1/2/3 (natspan2 = default). `voice/english-reference.wav` — English ref.

## Rules (owner's, non-negotiable)
- Same voice in all 3 languages; same speed; same words — never change, add or skip a word.
- Speed locked at 1.0. No time-stretch (atempo) on Telugu or Hindi.
- Tone fits the topic (serious = serious, light = lively), same tone in all 3 languages.
- Numbers/years/% spoken as words in THAT language.
- Zero mistakes: no cut words, no head grunts, no extra 'ay'/'eh'/breath sound after the last word of a sentence.
- Sentence gaps: 0.35 s Telugu/Hindi, 0.40 s English. 45 ms soft fade on sentence tails.
- Whisper check on every sentence; re-generate only REAL failures. English loanwords in Latin script and digits are NOT errors.
- Samples first, always: the owner approves by ear before any full run or delivery claim. His ear outranks every automated check.

## Kaggle setup that works
- Notebook/batch: Accelerator = GPU T4 x2, Internet = ON. Keep Kaggle's own torch.
- `pip install --no-deps omnivoice webdataset tensorboardx pydub num2words faster-whisper ctranslate2 onnxruntime av tokenizers`
- GPU Whisper also needs: `pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` + their lib folders on LD_LIBRARY_PATH; CPU Whisper fallback if that fails.
- Use BOTH GPUs (--device auto). Model load ~5 min once per session — generate all 3 languages in one session.
- Max 2 GPU batch sessions at a time; never leave old runs queued. Batch runs sometimes sit in QUEUED ~1 h — say so honestly.

## State (2026-11-17)
- Engine main includes: full gate stack (language/identity/pitch/ghost-word/head-bleed), self-healing re-roll,
  OmniVoice route with head-grunt mute + tail-trim fixes, turbo.py + textnorm.py (merged from Hark's build).
- Measured: 86 s of audio in 217 s on ONE T4 + ~5 min one-time model load. Speed target 20-min VO in ~10 min is
  NOT proven; honest free-T4 estimate so far 25–40 min. Never claim the target until measured.
- Owner feedback on first Kaggle samples: extra 'ay' after a question word, gaps too long, some words felt cut —
  fixes are in turbo.py but NOT yet ear-verified.
- OPEN: no clean Hindi reference (Hindi clones cross-lingually from the Telugu ref — owner's ear rejected a
  mixed-sounding Hindi take before). English ref is 25 s — trim to 8–10 s with exact transcript before use.
- OmniVoice weights are CC-BY-NC (non-commercial) — known caveat for monetized channels.

## NEXT STEPS
1. Run the tool on Kaggle → new 20–30 s samples in Telugu, Hindi, English → owner ear approval.
2. After approval: 2-minute timing test, both GPUs, 16 vs 32 steps — report real numbers.
3. Build the owner's self-run Kaggle notebook (paste 3 scripts → Run All → download mp3 + srt + QC report).
4. Final code to the GitHub repo above.

## How to talk to the owner
Telugu-English mix (Romanized Telugu), short, honest. Report failures plainly with the reason.
Never claim a sample is good on automated checks alone — his ear decides.
