"""turbo_collect.py — merge wave-1 runner records, emit the wave-2 list.

Reads every s<idx>.json under --stage (the merged wave-1 artifacts),
compares against the full lines file, and writes:
  failed-lines.txt   "<orig_index>\\t<sentence>" for each unshipped line
  collect_summary.json  per-sentence status + counts
  n_failed.txt       the failure count (the workflow turns it into a
                     job output / wave-2 matrix)
  matrix2.json       {"idx": [0..min(n_failed, MAX_W2_CHUNKS)-1]}
Pure stdlib; runs on the runner's stock python.
"""
import argparse
import glob
import json
import os

MAX_W2_CHUNKS = 24


def load_lines(path):
    items = []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.rstrip("\n")
            if not ln.strip():
                continue
            if "\t" in ln:
                idx_s, text = ln.split("\t", 1)
                items.append((int(idx_s), text.strip()))
            else:
                items.append((len(items) + 1, ln.strip()))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    items = load_lines(a.lines)
    status = {}
    for p in glob.glob(os.path.join(a.stage, "s*.json")):
        try:
            rec = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        status[int(rec["sentence"])] = rec
    rows, failed = [], []
    for idx, text in items:
        rec = status.get(idx)
        shipped = bool(rec and rec.get("ship"))
        rows.append({"sentence": idx, "ship": shipped,
                     "wave": rec.get("wave") if rec else None,
                     "identity": rec.get("identity") if rec else None,
                     "wps": rec.get("wps") if rec else None})
        if not shipped:
            failed.append((idx, text))
    with open(os.path.join(a.outdir, "failed-lines.txt"), "w",
              encoding="utf-8") as fh:
        for idx, text in failed:
            fh.write(f"{idx}\t{text}\n")
    n2 = min(len(failed), MAX_W2_CHUNKS)
    with open(os.path.join(a.outdir, "matrix2.json"), "w") as fh:
        json.dump({"idx": list(range(n2))}, fh)
    with open(os.path.join(a.outdir, "n_failed.txt"), "w") as fh:
        fh.write(str(len(failed)))
    summary = {"sentences": len(items), "shipped": len(items) - len(failed),
               "failed": len(failed), "wave2_chunks": n2, "rows": rows}
    with open(os.path.join(a.outdir, "collect_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(f"COLLECT shipped {summary['shipped']}/{len(items)} "
          f"failed {len(failed)} wave2_chunks {n2}", flush=True)


if __name__ == "__main__":
    main()
