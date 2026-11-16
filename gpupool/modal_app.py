"""The Modal-side half of the gpupool Modal adapter.

Deploy ONCE (by the account owner, after `modal setup`):

    pip install modal
    modal deploy gpupool/modal_app.py

That creates the Modal app "julie-voice-gpu" with one function,
run_batch(lines, lang, first_index) -> zip bytes, which the client
adapter (gpupool/adapters.py ModalAdapter) calls via
modal.Function.from_name. The function runs the engine's own batch
mode on a T4 — same repo, same locked voice, same ship gates — and
returns the batch output folder zipped (<nnn>.mp3 + batch.qc.json),
exactly the contract every other pool provider speaks.

Starter-plan math: T4 is billed per second (~$0.59/h), so the
$30/month recurring credit is ~50 T4-hours/month. Cold start pays a
repo clone + pip install inside the function (a few minutes); that
time is billed, so the scheduler gives Modal mid-size chunks, not
single lines.
"""

import io
import os
import subprocess
import sys
import zipfile

import modal

REPO_URL = "https://github.com/n8n00101-coder/julie-ai-voice-engine.git"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1", "zip")
)

app = modal.App("julie-voice-gpu", image=image)


def _flip(path, old, new):
    src = open(path).read()
    if src.count(old) >= 1:
        open(path, "w").write(src.replace(old, new, 1))


@app.function(gpu="T4", timeout=3600)
def run_batch(lines: list, lang: str, first_index: int) -> bytes:
    work = "/tmp/julie-voice"
    subprocess.run(["git", "clone", "--depth", "1", REPO_URL, work],
                   check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "torch==2.6.0", "torchaudio==2.6.0",
                    "--index-url", "https://download.pytorch.org/whl/cu124"],
                   check=True)
    reqs = [os.path.join(work, "requirements.txt")]
    if lang in ("te", "hi"):
        reqs.append(os.path.join(work, "requirements-indicf5.txt"))
    for req in reqs:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                        "-r", req], check=True)
    _flip(os.path.join(work, "engine.py"),
          'ChatterboxTTS.from_pretrained(device="cpu")',
          'ChatterboxTTS.from_pretrained(device="cuda")')
    _flip(os.path.join(work, "gates.py"),
          'WhisperModel(_model_path(), device="cpu", compute_type="int8")',
          'WhisperModel(_model_path(), device="cuda", compute_type="float16")')
    lines_path = os.path.join(work, "lines.txt")
    with open(lines_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    outdir = os.path.join(work, "out")
    # Exit 2 = some lines failed the gates after re-rolls; those lines
    # are named in batch.qc.json and the passing lines still ship.
    subprocess.run([sys.executable, "engine.py", "--batch", lines_path,
                    "--lang", lang, "--outdir", outdir, "--jobs", "1",
                    "--rerolls", "2", "--first-index", str(first_index)],
                   cwd=work)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(outdir)):
            zf.write(os.path.join(outdir, name), name)
    return buf.getvalue()
