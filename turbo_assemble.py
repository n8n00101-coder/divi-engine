"""turbo_assemble.py — final assembly for the 20-in-10 path.

Collects the shipped take for every sentence (wave-1 and wave-2 records
under --stage), verifies the script is COMPLETE, and assembles the
final mp3 with engine.assemble() under the locked settings (sentence
gaps gated to digital silence, 0.6 s sentence gap, piano bed 11 dB
under voice, one loudnorm pass to ~-15 LUFS, 1.5 s bed tail).

Honesty rule (locked): if any sentence has no shipped take, NO mp3 is
written — the QC json names the missing sentences and the exit code
is 2.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


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
    ap.add_argument("--out", required=True)
    ap.add_argument("--qc", required=True)
    a = ap.parse_args()
    items = load_lines(a.lines)
    best = {}
    # Recursive scan: the stage holds one subdir per artifact (wave-1
    # and wave-2 artifacts contain SAME-NAMED s<idx>.json files, so
    # they must never be merged into one flat directory — a merged
    # download overwrote 38 wave-2 ship records in the 2026-11-16
    # proof run). Each record's wav is resolved next to the record.
    for p in glob.glob(os.path.join(a.stage, "**", "s*.json"),
                       recursive=True):
        try:
            rec = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not rec.get("ship"):
            continue
        idx = int(rec["sentence"])
        wav = os.path.join(os.path.dirname(p), f"s{idx}.wav")
        if not os.path.exists(wav):
            continue
        prev = best.get(idx)
        if prev is None or (rec.get("wave") or 1) >= \
                (prev[0].get("wave") or 1):
            best[idx] = (rec, wav)
    missing = [idx for idx, _ in items if idx not in best]
    qc = {"sentences": len(items), "shipped": len(best),
          "missing": missing, "rows": []}
    for idx, _text in items:
        got = best.get(idx)
        if got:
            rec = got[0]
            qc["rows"].append(
                {"sentence": idx, "wave": rec.get("wave"),
                 "take": rec.get("shipped_take"),
                 "identity": rec.get("identity"), "wps": rec.get("wps"),
                 "duration_s": rec.get("duration_s")})
    if missing:
        os.makedirs(os.path.dirname(os.path.abspath(a.qc)), exist_ok=True)
        with open(a.qc, "w", encoding="utf-8") as fh:
            json.dump(qc, fh, ensure_ascii=False, indent=1)
        print(f"ASSEMBLE REFUSED: {len(missing)} sentences unshipped: "
              f"{missing}", flush=True)
        sys.exit(2)
    import engine
    settings = engine.load_settings()
    paths = [best[idx][1] for idx, _ in items]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    info = engine.assemble(paths, a.out, settings, use_bed=True)
    qc["assembly"] = info
    qc["first_pass_shipped"] = sum(
        1 for r in qc["rows"] if r["wave"] == 1 and r["take"] == 1)
    qc["wave1_shipped"] = sum(1 for r in qc["rows"] if r["wave"] == 1)
    qc["wave2_shipped"] = sum(1 for r in qc["rows"] if r["wave"] == 2)
    with open(a.qc, "w", encoding="utf-8") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=1)
    print(f"ASSEMBLE DONE {a.out} duration={info['duration_s']}s "
          f"sentences={len(items)} first-pass={qc['first_pass_shipped']} "
          f"wave1={qc['wave1_shipped']} wave2={qc['wave2_shipped']}",
          flush=True)


if __name__ == "__main__":
    main()
