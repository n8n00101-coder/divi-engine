"""turbo.py — ONE command for a full Telugu/Hindi voice-over.

    python3 turbo.py script.txt --lang te --out voiceover.mp3

This is the DEFAULT route for long te/hi scripts (Ajju's design,
2026-11-16): the parallel split is built in, not a special mode. The
one command does everything:

  1. sentence-splits the script (or takes it as-is with --lines),
  2. commits the lines file under jobs/ and pushes,
  3. dispatches the turbo workflow — the tool itself fans the script
     out over many parallel GitHub Actions runners (auto-sized,
     ~4 sentences per runner, capped at 40), each runner loading
     IndicF5 once, generating whole takes of its chunk and gating
     them with the locked ship bar,
  4. a failures-only wave 2 re-rolls whatever wave 1 missed,
  5. the workflow assembles ONE mp3 under the locked settings
     (engine.assemble: gated gaps, piano bed, one loudnorm pass),
  6. this command waits, downloads the `turbo-final` artifact, and
     leaves exactly one voice-over file (+ its QC json) behind.

Exit codes: 0 = voice-over written; 2 = failed loudly (no partial
file is ever presented as the voice-over). Stdlib only — needs git
and the gh CLI, authenticated for this repo.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = "turbo.yml"
LINES_PER_RUNNER = 4
MAX_CHUNKS = 40
MIN_CHUNKS = 8


def split_sentences(text):
    parts = re.split(r"(?<=[.!?।॥\n])\s*", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def auto_chunks(n_lines):
    return max(MIN_CHUNKS, min(MAX_CHUNKS,
                               math.ceil(n_lines / LINES_PER_RUNNER)))


def _run(cmd, check=True):
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: "
                           f"{(p.stderr or p.stdout)[-400:]}")
    return p


def _latest_run_id():
    p = _run(["gh", "run", "list", "--workflow", WORKFLOW, "--limit", "1",
              "--json", "databaseId", "--jq", ".[0].databaseId"],
             check=False)
    s = p.stdout.strip()
    return int(s) if s.isdigit() else 0


def run_cli(script, lang="te", out="voiceover.mp3", branch="main",
            chunks=None, lines_mode=False, timeout_min=90):
    t0 = time.time()
    raw = open(script, encoding="utf-8").read()
    if lines_mode:
        sentences = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    else:
        sentences = split_sentences(raw)
    if not sentences:
        print("ERROR: no sentences in script", file=sys.stderr)
        return 2
    n_chunks = chunks or auto_chunks(len(sentences))
    slug = re.sub(r"[^A-Za-z0-9]+", "-",
                  os.path.splitext(os.path.basename(script))[0]).strip("-")
    lines_rel = f"jobs/turbo-{slug or 'script'}.txt"
    lines_abs = os.path.join(REPO, lines_rel)
    with open(lines_abs, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sentences) + "\n")
    print(f"turbo: {len(sentences)} sentences -> {n_chunks} parallel "
          f"runners (branch {branch})")
    _run(["git", "add", lines_rel])
    p = _run(["git", "commit", "-m",
              f"turbo lines: {slug} ({lang}, {len(sentences)} sentences)"],
             check=False)
    if p.returncode != 0 and "nothing to commit" not in (
            p.stdout + p.stderr):
        raise RuntimeError(f"git commit failed: {(p.stderr or p.stdout)[-300:]}")
    _run(["git", "push", "origin", branch])
    before = _latest_run_id()
    _run(["gh", "workflow", "run", WORKFLOW, "--ref", branch,
          "-f", f"lines_path={lines_rel}", "-f", f"chunks={n_chunks}",
          "-f", f"lang={lang}"])
    run_id = 0
    deadline = time.time() + 180
    while time.time() < deadline:
        cand = _latest_run_id()
        if cand and cand != before:
            run_id = cand
            break
        time.sleep(5)
    if not run_id:
        print("ERROR: dispatched but the run never appeared", file=sys.stderr)
        return 2
    print(f"turbo: run {run_id} "
          f"(https://github.com/n8n00101-coder/julie-ai-voice-engine"
          f"/actions/runs/{run_id}) — waiting…")
    watch = subprocess.run(["gh", "run", "watch", str(run_id),
                            "--exit-status"], cwd=REPO)
    dl = os.path.join(REPO, ".turbo-out")
    subprocess.run(["gh", "run", "download", str(run_id), "-n",
                    "turbo-final", "-D", dl], cwd=REPO,
                   capture_output=True, text=True)
    mp3 = os.path.join(dl, "voiceover.mp3")
    qc_path = os.path.join(dl, "turbo.qc.json")
    qc = {}
    if os.path.exists(qc_path):
        qc = json.load(open(qc_path, encoding="utf-8"))
    if watch.returncode != 0 or not os.path.exists(mp3):
        missing = qc.get("missing")
        print(f"ERROR: no voice-over produced."
              + (f" Unshipped sentences: {missing}" if missing else
                 " See the run's turbo.qc.json / logs."), file=sys.stderr)
        return 2
    out_abs = out if os.path.isabs(out) else os.path.join(os.getcwd(), out)
    with open(mp3, "rb") as src, open(out_abs, "wb") as dst:
        dst.write(src.read())
    qc_out = os.path.splitext(out_abs)[0] + ".qc.json"
    with open(qc_out, "w", encoding="utf-8") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    wall = time.time() - t0
    print(f"turbo: DONE in {wall / 60:.1f} min — {out_abs} "
          f"({qc.get('assembly', {}).get('duration_s', '?')}s of audio, "
          f"{qc.get('shipped', '?')}/{qc.get('sentences', '?')} sentences, "
          f"first-pass {qc.get('first_pass_shipped', '?')}, "
          f"wave2 {qc.get('wave2_shipped', '?')}; QC: {qc_out})")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Julie AI voice — turbo "
                                             "(one-command long voice-over)")
    ap.add_argument("script", help="script text file (or lines file "
                                   "with --lines)")
    ap.add_argument("--lang", default="te", choices=["te", "hi"])
    ap.add_argument("--out", default="voiceover.mp3")
    ap.add_argument("--branch", default="main",
                    help="branch the workflow runs on (default: main)")
    ap.add_argument("--chunks", type=int, default=None,
                    help="parallel runners (default: auto, ~4 "
                         "sentences per runner, 8..40)")
    ap.add_argument("--lines", action="store_true",
                    help="script is already one sentence per line")
    a = ap.parse_args()
    try:
        return run_cli(a.script, lang=a.lang, out=a.out, branch=a.branch,
                       chunks=a.chunks, lines_mode=a.lines)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
