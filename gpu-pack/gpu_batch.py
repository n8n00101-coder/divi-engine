# Julie AI Voice Engine — Kaggle GPU batch runner
#
# STATUS: PREPARED, NOT YET RUN. This script was written for a Kaggle
# notebook with a T4 GPU attached. It has NOT been executed on Kaggle
# yet — the first run is the test. See gpu-pack/README.md for the
# step-by-step.
#
# What it does, in order:
#   1. Clones the julie-ai-voice-engine repo (fresh copy, in /kaggle/working).
#   2. Installs the engine's dependencies with a CUDA build of torch.
#   3. Applies a small, explicit device patch to the NOTEBOOK'S COPY ONLY
#      (the repo itself is untouched):
#        - engine.py: ChatterboxTTS device "cpu" -> "cuda"
#          (chatterbox-tts 0.1.7 exposes no fp16 switch, so the clone
#          model itself runs fp32 on the GPU.)
#        - gates.py: faster-whisper device "cpu"/int8 -> "cuda"/float16
#          (the gate ASR is the part that uses fp16.)
#      Voice settings and gate thresholds are NOT touched — accuracy is
#      the same five gates on every line.
#   4. Runs engine batch mode on your lines file (model loads once).
#   5. Zips every mp3 + batch.qc.json to /kaggle/working/out.zip.
#
# How to use: paste this whole file into ONE code cell of a Kaggle
# notebook (GPU T4 x1 enabled), edit LINES below if your script file
# has a different name, run the cell, then download out.zip from the
# notebook's Output panel.

import os
import subprocess
import sys

REPO_URL = "https://github.com/n8n00101-coder/julie-ai-voice-engine.git"
WORK = "/kaggle/working"
REPO_DIR = os.path.join(WORK, "julie-ai-voice-engine")

# --- Edit these three if needed -------------------------------------------
LINES = os.path.join(WORK, "lines.txt")   # put your script here, 1 line/row
LANG = "en"                               # en | te | hi
JOBS = 1                                  # one GPU = one worker is right
REROLLS = 2
# ---------------------------------------------------------------------------


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def main():
    import torch

    if not torch.cuda.is_available():
        raise SystemExit(
            "No GPU visible. In the Kaggle notebook: Settings -> "
            "Accelerator -> GPU T4 x1, then restart the session."
        )
    print("GPU:", torch.cuda.get_device_name(0))

    # 1. Fresh clone of the engine.
    if not os.path.isdir(REPO_DIR):
        run(["git", "clone", "--depth", "1", REPO_URL, REPO_DIR])

    # 2. Dependencies: CUDA torch first, then the engine requirements.
    run([sys.executable, "-m", "pip", "install", "-q",
         "torch==2.6.0", "torchaudio==2.6.0",
         "--index-url", "https://download.pytorch.org/whl/cu124"])
    run([sys.executable, "-m", "pip", "install", "-q", "httpx",
         "-r", os.path.join(REPO_DIR, "requirements.txt")])
    # ffmpeg ships with Kaggle images; if missing, uncomment:
    # run(["apt-get", "install", "-y", "-qq", "ffmpeg"])

    # 3. Device patch — notebook copy only, exactly two substitutions.
    eng = os.path.join(REPO_DIR, "engine.py")
    src = open(eng).read()
    old = 'ChatterboxTTS.from_pretrained(device="cpu")'
    assert src.count(old) == 1, "engine.py device line not found — repo changed?"
    open(eng, "w").write(src.replace(old, 'ChatterboxTTS.from_pretrained(device="cuda")'))

    gat = os.path.join(REPO_DIR, "gates.py")
    src = open(gat).read()
    old = 'WhisperModel(_model_path(), device="cpu", compute_type="int8")'
    assert src.count(old) == 1, "gates.py WhisperModel line not found — repo changed?"
    open(gat, "w").write(src.replace(
        old, 'WhisperModel(_model_path(), device="cuda", compute_type="float16")'))
    print("Device patch applied (cuda synth, fp16 gate ASR).")

    if not os.path.isfile(LINES):
        raise SystemExit(
            f"Lines file not found: {LINES}\n"
            "Upload your script (one line per row) in the notebook's "
            "Input panel, or edit LINES at the top of this script."
        )

    # 4. Batch mode on the GPU. Model loads once for the whole script.
    outdir = os.path.join(WORK, "out")
    run([sys.executable, "engine.py", "--batch", LINES, "--lang", LANG,
         "--outdir", outdir, "--jobs", str(JOBS), "--rerolls", str(REROLLS)],
        cwd=REPO_DIR)

    # 5. Zip the results for download.
    run(["bash", "-c", f"cd {WORK} && zip -r out.zip out"])
    print("Done. Download /kaggle/working/out.zip from the Output panel.")


if __name__ == "__main__":
    main()
