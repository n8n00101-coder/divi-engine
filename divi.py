"""Divi Engine — the front door.

    python3 divi.py --text-file script.txt --lang te --out out.mp3
    python3 divi.py --text-file script.txt --lang hi --out out.mp3 --cloud
    python3 divi.py --text-file script.txt --lang en --out out.mp3 --cloud --chunks 40

One command in, one finished voice-over out:

  1. SCRIPT PRE-FLIGHT heals the script (preflight.py) — the
     generation stages only ever see the corrected text; the
     corrected script lands beside the output and every correction
     is in the QC report.
  2. GENERATION + SELF-HEALING run in the engine's batch mode
     (best-of-N waves, per-sentence escalation ladder). Local mode
     runs it on this machine; --cloud dispatches the divi-voice-batch
     GitHub Actions matrix (up to 40 free runners, one model load
     per runner) and downloads the per-line mp3s.
  3. ASSEMBLY + FINAL VERIFICATION: the shipped lines are assembled
     with the locked recipe (median gain match, 0.6 s gaps, gaps
     gated to true silence, ONE loudnorm) and the assembled file is
     verified end-to-end (verify.py). A file that fails verification
     is removed, never shipped.

The SPEED LAW (a 20-minute voice-over ready within 10 minutes
wall-clock) is what --cloud is for: per-sentence generation and
gates run in parallel across the runner matrix. --speed is the
user's explicit per-job tempo option; without it the locked recipe
speed runs exactly (the QC report prints LOCKED / USER-REQUESTED).

Exit codes: 0 = every sentence shipped + verified; 2 = partial
(failed sentences named in the QC report, everything else
delivered) or verification failed (mp3 removed); 3 = dispatched
(nothing local to deliver).
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine  # noqa: E402
import preflight  # noqa: E402
import verify  # noqa: E402


def _sentences(text, lang):
    pf = preflight.preflight_text(text, lang)
    return pf, engine.split_sentences(pf["text"])


def _assemble_and_verify(take_wavs, out_mp3, shipped_texts, settings,
                         lang, bed, qc_extra):
    info = engine.assemble(take_wavs, out_mp3, settings, bed)
    rep = verify.verify_file(out_mp3, shipped_texts, lang, settings,
                             sentence_spans=info["spans"],
                             expected_duration_s=info["duration_s"])
    qc = {"engine": "Divi Engine 2.0", "mode": "divi",
          "out": out_mp3, **info, "verification": rep, **qc_extra}
    if not rep["pass"]:
        qc["verdict"] = ("FAIL — final assembled-file verification "
                         "failed; the mp3 was removed")
    qc_path = os.path.splitext(out_mp3)[0] + ".qc.json"
    with open(qc_path, "w", encoding="utf-8") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    if not rep["pass"]:
        os.unlink(out_mp3)
    return qc, qc_path


def run_local(args, text):
    """Local path: engine batch mode with --assemble-out does
    generation, healing, assembly and verification in one go."""
    pf, sentences = _sentences(text, args.lang)
    if not sentences:
        print("ERROR: no sentences after pre-flight", file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="divi_local_")
    lines_file = os.path.join(tmp, "lines.txt")
    with open(lines_file, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sentences) + "\n")
    outdir = os.path.join(tmp, "batch_out")
    cmd = [sys.executable, os.path.join(HERE, "engine.py"),
           "--batch", lines_file, "--lang", args.lang,
           "--outdir", outdir, "--assemble-out",
           os.path.abspath(args.out),
           "--candidates", str(args.candidates),
           "--rerolls", str(args.rerolls)]
    if args.jobs:
        cmd += ["--jobs", str(args.jobs)]
    if args.speed is not None:
        cmd += ["--speed", str(args.speed)]
    if args.bed:
        cmd += ["--bed"]
    env = dict(os.environ)
    if args.backend:
        env["JULIE_TTS_BACKEND"] = args.backend
    t0 = time.time()
    p = subprocess.run(cmd, env=env)
    wall = round(time.time() - t0, 1)
    final_qc = os.path.splitext(os.path.abspath(args.out))[0] + ".qc.json"
    print(f"divi (local): {wall}s wall — QC: {final_qc}")
    return p.returncode


def run_cloud(args, text):
    pf, sentences = _sentences(text, args.lang)
    if not sentences:
        print("ERROR: no sentences after pre-flight", file=sys.stderr)
        return 2
    settings = engine.load_settings()
    branch = subprocess.run(["git", "-C", HERE, "rev-parse",
                             "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    lines_path = os.path.join(HERE, "divi-lines.txt")
    with open(lines_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sentences) + "\n")
    subprocess.run(["git", "-C", HERE, "add", "divi-lines.txt"],
                   check=True)
    subprocess.run(["git", "-C", HERE, "commit", "-q", "-m",
                    f"divi: lines for cloud run ({args.lang}, "
                    f"{len(sentences)} sentences)"], check=True)
    subprocess.run(["git", "-C", HERE, "push", "-q", "origin", branch],
                   check=True)
    chunks = max(1, min(args.chunks, 40, len(sentences)))
    t0 = time.time()
    cmd = ["gh", "workflow", "run", "voice-batch.yml", "--ref", branch,
           "-f", f"lines_path=divi-lines.txt", "-f", f"lang={args.lang}",
           "-f", f"chunks={chunks}", "-f",
           f"candidates={args.candidates}", "-f",
           f"rerolls={args.rerolls}"]
    if args.backend:
        cmd += ["-f", f"backend={args.backend}"]
    if args.speed is not None:
        cmd += ["-f", f"speed={args.speed}"]
    subprocess.run(cmd, cwd=HERE, check=True)
    # find the run we just dispatched (newest voice-batch run)
    time.sleep(5)
    runs = json.loads(subprocess.run(
        ["gh", "run", "list", "--workflow", "voice-batch.yml",
         "--limit", "1", "--json", "databaseId"],
        cwd=HERE, capture_output=True, text=True).stdout)
    run_id = str(runs[0]["databaseId"])
    print(f"divi (cloud): run {run_id} dispatched on {chunks} runners "
          f"for {len(sentences)} sentences — watching…")
    subprocess.run(["gh", "run", "watch", run_id], cwd=HERE)
    tmp = tempfile.mkdtemp(prefix="divi_cloud_")
    subprocess.run(["gh", "run", "download", run_id, "-n",
                    "divi-voice-batch-all", "-D", tmp], cwd=HERE,
                   check=True)
    # per-line verdicts from the chunk QC reports
    line_status = {}
    for qc_path in glob.glob(os.path.join(tmp, "batch.qc.chunk-*.json")):
        qc = json.load(open(qc_path))
        for ln in qc.get("lines", []):
            line_status[ln["index"]] = ln.get("chosen_roll") is not None
    shipped_idx = [i for i in range(1, len(sentences) + 1)
                   if line_status.get(i)]
    failed_idx = [i for i in range(1, len(sentences) + 1)
                  if not line_status.get(i)]
    if not shipped_idx:
        print("divi (cloud): NO line passed — nothing to assemble",
              file=sys.stderr)
        return 2
    # decode the shipped line mp3s to wavs for the locked assembly
    take_wavs = []
    for i in shipped_idx:
        mp3 = os.path.join(tmp, engine.batch_line_name(i))
        wav = os.path.join(tmp, f"line{i:03d}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-ar",
                        "24000", "-ac", "1", wav, "-y"], check=True)
        take_wavs.append(wav)
    out_abs = os.path.abspath(args.out)
    qc_extra = {"cloud_run_id": run_id, "chunks": chunks,
                "script_corrections": pf["corrections"],
                "script_flags": pf["flags"],
                "lines_total": len(sentences),
                "lines_shipped": shipped_idx,
                "lines_failed": failed_idx,
                "wall_s": round(time.time() - t0, 1)}
    qc, qc_path = _assemble_and_verify(
        take_wavs, out_abs, [sentences[i - 1] for i in shipped_idx],
        settings, args.lang, args.bed, qc_extra)
    if failed_idx:
        qc["verdict"] = (f"PARTIAL — {len(failed_idx)} of "
                         f"{len(sentences)} lines failed the full "
                         f"escalation ladder and are NOT in the "
                         f"file: {failed_idx}. Everything else "
                         f"shipped and verified.")
        with open(qc_path, "w", encoding="utf-8") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)
    elif qc["verification"]["pass"]:
        qc["verdict"] = "PASS — every line shipped and verified"
        with open(qc_path, "w", encoding="utf-8") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)
    print(f"divi (cloud): {qc_extra['wall_s']}s wall, "
          f"{len(shipped_idx)}/{len(sentences)} lines — QC: {qc_path}")
    if not qc["verification"]["pass"]:
        return 2
    return 0 if not failed_idx else 2


def main():
    ap = argparse.ArgumentParser(
        description="Divi Engine — one command, one finished "
                    "voice-over (pre-flight -> healing generation "
                    "-> assembly -> final verification)")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--lang", choices=["en", "te", "hi"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cloud", action="store_true",
                    help="dispatch to the GitHub Actions runner "
                         "matrix (the speed-law path)")
    ap.add_argument("--chunks", type=int, default=40,
                    help="cloud runners (1-40, default 40)")
    ap.add_argument("--backend",
                    help="backend override (e.g. omnivoice, "
                         "indicf5-space); default: the locked route "
                         "per language")
    ap.add_argument("--speed", type=float, default=None,
                    help="USER-REQUESTED tempo factor for this job "
                         "only; default: locked recipe speed")
    ap.add_argument("--candidates", type=int, default=3)
    ap.add_argument("--rerolls", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=None,
                    help="local mode: parallel workers")
    ap.add_argument("--bed", action="store_true")
    args = ap.parse_args()
    if not args.text and not args.text_file:
        ap.error("--text or --text-file is required")
    text = args.text if args.text else open(
        args.text_file, encoding="utf-8").read()
    # the corrected script always lands beside the output
    pf = preflight.preflight_text(text, args.lang)
    corrected_path = os.path.join(
        os.path.dirname(os.path.abspath(args.out)),
        "script.corrected.txt")
    with open(corrected_path, "w", encoding="utf-8") as fh:
        fh.write(pf["text"] + "\n")
    for fl in pf["flags"]:
        print(f"SCRIPT FLAG [{fl['class']}] {fl['word']}: "
              f"{fl['reason']}", file=sys.stderr)
    if args.cloud:
        return run_cloud(args, text)
    return run_local(args, text)


if __name__ == "__main__":
    sys.exit(main())
