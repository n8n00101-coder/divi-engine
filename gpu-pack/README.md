# GPU pack — voice a whole script on a free Kaggle T4 GPU

> **Status: prepared, not yet run.** This pack was written and checked
> against the engine's code, but it has **not** been executed on Kaggle
> yet. The first run is the test — if a step fails, note which one and
> tell us the error message. Nothing here needs a paid account, and it
> never asks for anyone's password: you sign in to your own Kaggle
> account yourself.

## Why this exists

The engine's voice model runs on CPU by default, which is slow. A
Kaggle notebook gives you a free **T4 GPU** (30 hours/week at the time
of writing). On the GPU, the same engine, same voice and same quality
gates run line generation many times faster than a small CPU — and the
model still loads only **once** for the whole script (batch mode).

## What you need

- A free Kaggle account (kaggle.com) — you create/sign in yourself.
- Your script as a plain text file: **one line per row** (`lines.txt`).
- ~15 minutes of clicking for the first setup; after that, one cell run
  per script.

## Steps

1. **Sign in** to kaggle.com with your own account.
2. *(One time only — API token, optional but makes re-runs easier)*
   Kaggle → your avatar → **Settings** → **API** → **Create New
   Token**. Your browser downloads `kaggle.json`. Keep it private —
   it is a key to your account. (You only need it if you later want to
   run notebooks from the command line; for the click-through route
   below you can skip this.)
3. Click **Create → New Notebook**.
4. On the right-hand panel: **Settings → Accelerator → GPU T4 x1**.
   (If it asks for phone verification, that is Kaggle's own step —
   complete it in your browser.)
5. Also on the right panel: **Internet → On** (the notebook must reach
   GitHub and PyPI to fetch the engine and its dependencies).
6. **Add your script:** right panel → **Input → Upload** → upload your
   `lines.txt`. It lands under `/kaggle/input/...`; either copy it to
   `/kaggle/working/lines.txt` with a small cell
   (`!cp /kaggle/input/*/lines.txt /kaggle/working/lines.txt`) or edit
   the `LINES =` path at the top of `gpu_batch.py`.
7. **Paste the runner:** open
   [`gpu_batch.py`](gpu_batch.py) from this folder, copy the whole
   file into one code cell of the notebook, and **Run** it.
   - First it checks a GPU is visible.
   - It clones this repo, installs dependencies (CUDA torch — this is
     the slow part, a few minutes), and flips the engine's device
     switches to the GPU in the notebook's copy only: synthesis on
     CUDA, the gate ASR in fp16. Voice settings and gate thresholds
     are not touched.
   - Then it voices your whole script in batch mode — one model load,
     every line through all five gates, failures re-rolled on their
     own.
8. **Download the result:** when the cell finishes, open the
   notebook's **Output** panel and download **`out.zip`** — it contains
   one mp3 per passing line (`001.mp3`, `002.mp3`, … in your script's
   order) plus `batch.qc.json`, which names any line that never passed
   the gates (those lines get no mp3 — re-run just those lines later).

## Honest limits

- Kaggle's free GPU is a shared gift: sessions are time-limited
  (up to ~12 hours) and the 30 h/week quota is Kaggle's, not ours.
- A 209-line script should fit comfortably in one session, but the
  very first run also pays the dependency install and model download.
- The Telugu/Hindi route uses the IndicF5 backend; this pack's GPU
  patch targets the English Chatterbox path and the gate ASR. For
  te/hi, prefer the GitHub Actions route in the main README.
- If `gpu_batch.py` stops with "engine.py device line not found", the
  engine's code has changed since this pack was written — tell us; the
  patch needs a one-line update, not a rewrite.
