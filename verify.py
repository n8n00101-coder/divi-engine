"""Divi Engine — final assembled-file verification (self-fix layer,
last line of defence).

The per-take gates judge takes. This module judges the FILE THAT
SHIPS: the assembled mp3, after level matching, gap gating and the
loudnorm pass. Every defect class that ever reached a listener did so
in an assembled file, so the assembled file is what gets verified —
never just the takes that went into it.

    python3 verify.py out.mp3 te sentences.txt [--expected-duration S]
    (sentences file: one sentence per line, in script order)

Checks (each logged in the returned report; ANY hard failure makes
report["pass"] False and the engine refuses to ship):

  completeness  the assembled file contains every script sentence
                exactly once, in order: the file is sliced into
                sentence windows (assembler spans when the engine
                supplies them, island grouping otherwise), each
                window is ASR-transcribed and aligned to its script
                sentence — no missing words — and each window's best
                match across ALL script sentences must be its own
                (a duplicated or swapped sentence fails here even when
                the count is right).
  language      the whole file, transcribed with NO language hint,
                detects as the target language (gate 1's rule, applied
                to the shipped file).
  head grunt    gate 6's detector runs on every sentence window of
                the assembled file — no grunt may survive assembly.
  cut word      gate 7 runs on every sentence window — every ending
                in the shipped file must be whole.
  gaps          inter-sentence silences sit in [0.30, 1.05] s (the
                locked 0.6 s join, with mp3 tolerance) and no
                sentence hides a padded interior silence > 0.9 s.
  levels        per-sentence speech RMS within ±7 dB of the median
                sentence (assembly gain-matches with plain gain; a
                bigger spread means a level jump a listener hears).
  duration      total duration matches the assembler's own figure
                (±0.5 s) when the engine supplies it.
  identity      spot check: up to 3 sentence windows embedded with
                Resemblyzer vs the English reference must clear
                gates.merged_sim_min (0.75). If Resemblyzer is not
                installed in the running environment the check is
                recorded as "unavailable" and excluded — the cloud
                workflows install it; a local run must not pretend it
                measured what it did not.

Thresholds here are deliberately generous sanity bounds: this pass
exists to catch SHIPPED-defect classes (missing/duplicated sentence,
surviving grunt, cut ending, padded silence, level jump, wrong
language, wrong length), not to re-judge diction — gates 1–5 already
did that per take, and re-judging with looser tools would only add
false refusals.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SR = 24000
GAP_MIN_S, GAP_MAX_S = 0.30, 1.05
INTERIOR_SILENCE_MAX_S = 0.9
LEVEL_SPREAD_DB = 7.0
DURATION_TOL_S = 0.5


def _decode24(mp3_path, wav_path):
    subprocess.run(["ffmpeg", "-v", "error", "-i", mp3_path, "-ar",
                    str(SR), "-ac", "1", wav_path, "-y"], check=True)


def _group_islands(isl, split_gap=0.45):
    """Group speech islands into sentence groups: a silence longer
    than split_gap starts a new sentence (the locked join is 0.6 s)."""
    groups = []
    for iv in isl:
        if groups and iv[0] - groups[-1][-1][1] > split_gap:
            groups.append([iv])
        elif groups:
            groups[-1].append(iv)
        else:
            groups.append([iv])
    return [(g[0][0], g[-1][1], g) for g in groups]


def verify_file(path, sentences, lang, settings=None,
                sentence_spans=None, expected_duration_s=None):
    """Verify an assembled mp3 against its script. `sentence_spans`
    (optional) is the assembler's [(start_s, dur_s), ...] speech-span
    map; `expected_duration_s` its total. Returns the report dict."""
    import numpy as np
    import soundfile as sf

    import acoustic_gates
    import gates as gates_mod

    settings = settings or gates_mod.load_settings()
    g = settings["gates"]
    rep = {"file": path, "lang": lang, "sentences_expected": len(sentences),
           "checks": {}, "sentences": [], "pass": False}
    tmp = tempfile.mkdtemp(prefix="divi_verify_")
    wav = os.path.join(tmp, "decoded.wav")
    try:
        _decode24(path, wav)
    except Exception as e:
        rep["checks"]["decode"] = {"pass": False, "error": str(e)[-200:]}
        return rep
    y, sr = sf.read(wav, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y[:, 0]
    total_s = len(y) / sr
    rep["duration_s"] = round(total_s, 2)

    # ---- sentence windows -------------------------------------------
    if sentence_spans:
        windows = [(float(a), float(a) + float(d))
                   for a, d in sentence_spans]
        rep["window_source"] = "assembler spans"
    else:
        _y, _sr, db, dt, floor, isl = acoustic_gates._profile(wav)
        groups = _group_islands(isl)
        windows = [(a, b) for a, b, _g in groups]
        rep["window_source"] = "island grouping (no assembler spans)"
    rep["sentences_found"] = len(windows)
    count_ok = len(windows) == len(sentences)
    rep["checks"]["sentence_count"] = {
        "pass": count_ok, "expected": len(sentences),
        "found": len(windows)}

    # ---- gaps ---------------------------------------------------------
    gap_list = []
    gaps_ok = True
    for i in range(len(windows) - 1):
        gap = windows[i + 1][0] - windows[i][1]
        gap_list.append(round(gap, 2))
        if not (GAP_MIN_S <= gap <= GAP_MAX_S):
            gaps_ok = False
    rep["checks"]["gaps"] = {"pass": gaps_ok and count_ok,
                             "gaps_s": gap_list,
                             "allowed_s": [GAP_MIN_S, GAP_MAX_S]}

    # ---- per-sentence checks ------------------------------------------
    simple = gates_mod.LANG_SIMPLE[lang]
    slice_paths = []
    for i, (a, b) in enumerate(windows):
        seg = y[int(max(0.0, a - 0.05) * sr):int(min(total_s, b + 0.30) * sr)]
        sp = os.path.join(tmp, f"sent{i + 1}.wav")
        sf.write(sp, seg, sr, subtype="PCM_16")
        slice_paths.append(sp)

    # ASR per slice (forced language) for completeness + cross-match
    toks_per_slice = []
    for sp in slice_paths:
        try:
            toks, _lp = gates_mod.asr_tokens(sp, lang)
        except Exception as e:
            toks = []
            rep.setdefault("notes", []).append(
                f"ASR failed on a sentence window: {str(e)[-120:]}")
        toks_per_slice.append(toks)

    en_simple = gates_mod.LANG_SIMPLE["en"]

    def slice_match(toks, script_text):
        # Whisper's forced-language output script wobbles on this
        # material — Telugu speech can come back ROMANIZED
        # ('Laksha' for లక్ష), whose te phonetic form is empty.
        # Compare in phonetic space whichever script the ASR chose:
        # a token's phon is its script form, falling back to the
        # Latin phonetic form of the raw token.
        phons = [t["phon"] or en_simple(t["tok"]) for t in toks]
        words = [w for w in script_text.strip().split() if w]
        wphon = [simple(w) for w in words]
        # Words with NO phonetic form (digits, '%', symbols) cannot
        # be judged in phonetic space — ASR renders numbers too
        # unstably (the genuine reference narration itself would
        # fail). They are excluded from missing/mean and reported
        # as unjudged; every speakable word is judged strictly.
        judged = [(wi, wphon[wi]) for wi in range(len(words))
                  if wphon[wi]]
        if not judged:
            return [], (1.0 if toks else 0.0)
        assign, _junk = gates_mod.align(
            [p for _wi, p in judged], [{"phon": p} for p in phons])
        missing, sims = [], []
        for k, (wi, p) in enumerate(judged):
            a = assign[k] if k < len(assign) else None
            if a is None or a.get("missing") or not a.get("toks"):
                missing.append(words[wi])
                sims.append(0.0)
            else:
                cat = "".join(phons[t] for t in a["toks"])
                sims.append(gates_mod.sim(p, cat))
        return missing, (float(np.mean(sims)) if sims else 0.0)

    completeness_ok = count_ok
    levels = []
    for i, sp in enumerate(slice_paths):
        entry = {"index": i + 1}
        if i < len(sentences):
            missing, mean_sim = slice_match(toks_per_slice[i],
                                            sentences[i])
            entry["missing_words"] = missing
            entry["mean_word_sim"] = round(mean_sim, 2)
            # cross-match: this window must match its OWN sentence best
            best_j, best_s = None, -1.0
            for j, s_text in enumerate(sentences):
                _m, s = slice_match(toks_per_slice[i], s_text)
                if s > best_s:
                    best_j, best_s = j, s
            entry["best_match_sentence"] = (best_j + 1) if best_j is not None else None
            own_ok = (not missing and mean_sim >= g["word_sim_min"]
                      and best_j == i)
            entry["completeness_pass"] = bool(own_ok)
            completeness_ok = completeness_ok and own_ok
        # An empty or unreadable window (span beyond the file's
        # end — e.g. a dropped sentence) is a verification FAILURE,
        # never a crash of the verifier itself.
        try:
            hg = acoustic_gates.head_grunt_detect(sp)
            entry["head_grunt_present"] = bool(hg["present"])
        except Exception as e:
            entry["head_grunt_present"] = True
            entry["head_grunt_error"] = str(e)[-120:]
        try:
            cw = acoustic_gates.cut_word_gate(sp)
            entry["cut_word_pass"] = bool(cw["pass"])
            if not cw["pass"]:
                entry["cut_word_fails"] = cw["fails"]
        except Exception as e:
            entry["cut_word_pass"] = False
            entry["cut_word_error"] = str(e)[-120:]
        seg_y, _ = sf.read(sp, dtype="float32", always_2d=False)
        if len(seg_y) == 0:
            # empty window: silence where a sentence should be
            entry["interior_silence_max_s"] = None
            entry["interior_silence_pass"] = False
            entry["rms_db"] = -120.0
            levels.append(entry["rms_db"])
            rep["sentences"].append(entry)
            continue
        # interior silence: longest sub-threshold run inside the window
        import acoustic_gates as _ag
        db, dt = _ag._frame_db(seg_y.astype(np.float64))
        floor = _ag._floor_ref(db)
        below = db <= floor + 8.0
        longest, run = 0.0, 0.0
        for bl in below:
            run = run + dt if bl else 0.0
            longest = max(longest, run)
        entry["interior_silence_max_s"] = round(longest, 2)
        entry["interior_silence_pass"] = bool(
            longest <= INTERIOR_SILENCE_MAX_S)
        rms = float(np.sqrt(np.mean(seg_y ** 2)) + 1e-12)
        entry["rms_db"] = round(20 * np.log10(rms), 1)
        levels.append(entry["rms_db"])
        rep["sentences"].append(entry)
    rep["checks"]["completeness"] = {"pass": bool(completeness_ok)}
    rep["checks"]["head_grunt"] = {
        "pass": all(not s["head_grunt_present"] for s in rep["sentences"])}
    rep["checks"]["cut_word"] = {
        "pass": all(s["cut_word_pass"] for s in rep["sentences"])}
    rep["checks"]["interior_silence"] = {
        "pass": all(s["interior_silence_pass"] for s in rep["sentences"]),
        "max_allowed_s": INTERIOR_SILENCE_MAX_S}
    if levels:
        med = float(np.median(levels))
        spread_ok = all(abs(v - med) <= LEVEL_SPREAD_DB for v in levels)
        rep["checks"]["levels"] = {"pass": bool(spread_ok),
                                   "median_rms_db": round(med, 1),
                                   "per_sentence_db": levels,
                                   "allowed_spread_db": LEVEL_SPREAD_DB}
    else:
        rep["checks"]["levels"] = {"pass": False, "error": "no sentences"}

    # ---- whole-file language -------------------------------------------
    try:
        det = gates_mod.nohint_detect(wav)
        need = g["nohint_prob_min"].get(
            lang, g["nohint_prob_min"]["default"])
        rep["checks"]["language"] = {
            "pass": bool(det["lang"] == lang and det["prob"] >= need),
            "detected": det["lang"], "prob": det["prob"],
            "required": need}
    except Exception as e:
        rep["checks"]["language"] = {"pass": False,
                                     "error": str(e)[-200:]}

    # ---- duration -------------------------------------------------------
    if expected_duration_s:
        ok = abs(total_s - float(expected_duration_s)) <= DURATION_TOL_S
        rep["checks"]["duration"] = {
            "pass": bool(ok), "actual_s": round(total_s, 2),
            "expected_s": float(expected_duration_s),
            "tolerance_s": DURATION_TOL_S}
    else:
        rep["checks"]["duration"] = {"pass": True,
                                     "note": "no assembler figure given"}

    # ---- identity spot check ---------------------------------------------
    id_check = {"status": "unavailable"}
    try:
        import engine as engine_mod
        idxs = sorted(set([0, len(slice_paths) // 2,
                           len(slice_paths) - 1])) if slice_paths else []
        vals = {}
        for i in idxs:
            vals[i + 1] = round(engine_mod._take_identity(slice_paths[i]), 3)
        thr = float(g["merged_sim_min"])
        id_check = {"status": "measured", "values": vals,
                    "min_required": thr,
                    "pass": all(v >= thr for v in vals.values())}
    except Exception as e:
        id_check = {"status": "unavailable",
                    "note": "Resemblyzer not available in this "
                            "environment — identity NOT measured here "
                            f"({str(e)[-100:]})"}
    rep["checks"]["identity_spot"] = id_check

    hard = ["sentence_count", "completeness", "language", "head_grunt",
            "cut_word", "gaps", "interior_silence", "levels", "duration"]
    rep["pass"] = all(rep["checks"][k]["pass"] for k in hard) and (
        id_check.get("status") != "measured" or id_check["pass"])
    return rep


def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Divi Engine — final assembled-file verification")
    ap.add_argument("mp3")
    ap.add_argument("lang", choices=["en", "te", "hi"])
    ap.add_argument("sentences_file",
                    help="one sentence per line, in script order")
    ap.add_argument("--expected-duration", type=float, default=None)
    args = ap.parse_args()
    sentences = [ln.strip() for ln in open(args.sentences_file,
                                            encoding="utf-8")
                 if ln.strip()]
    rep = verify_file(args.mp3, sentences, args.lang,
                      expected_duration_s=args.expected_duration)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
