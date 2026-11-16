"""Divi Engine — FINAL ASSEMBLED-FILE VERIFICATION tests
(verify.py; owner's order 4, 2026-11-16): the last self-fix layer
re-checks the ASSEMBLED file, not just the takes — every script
sentence present exactly once, no grunt/cut endings, sane gaps and
levels, honest duration.

Fixtures are built from the canonical Telugu reference take (her
genuine narration + its exact transcript), so a correct file must
PASS and each sabotage must FAIL for the stated reason.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

import engine  # noqa: E402
import verify  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name +
          ((" — " + detail) if (detail and not cond) else ""))
    if not cond:
        FAILS.append(name)


REF_WAV = os.path.join(HERE, "voice", "telugu-reference.wav")
REF_TEXT = open(os.path.join(HERE, "voice",
                             "telugu-reference-text.txt")).read().strip()
SETTINGS = engine.load_settings()
SR = 24000


def _write(y, name):
    path = os.path.join(tempfile.mkdtemp(prefix="divi_selffix_"), name)
    sf.write(path, y.astype("f4"), SR, format="WAV")
    return path


def _slice_fixture():
    """(sentence, audio): the first 26 words of the reference
    transcript (decimals flattened) and the matching audio prefix
    cut at the natural pause nearest the proportional point. The
    full reference is a span CUT from longer narration — its own
    ending is abrupt, so it cannot be the PASS fixture; this slice
    ends at a real pause and passes gate 7 (validated)."""
    words = [w.replace("128.6", "128").replace("64.6", "64")
             for w in REF_TEXT.split()[:26]]
    sent = " ".join(words) + "."
    y, sr = sf.read(REF_WAV, dtype="float32")
    fr = int(0.02 * sr)
    n = len(y) // fr
    rms = np.array([np.sqrt(np.mean(y[i * fr:(i + 1) * fr] ** 2))
                    for i in range(n)])
    thr = 0.15 * np.median(rms[rms > 0])
    target = 26 / 32 * len(y) / sr
    gaps, i = [], 0
    while i < n:
        if rms[i] <= thr:
            j = i
            while j < n and rms[j] <= thr:
                j += 1
            if (j - i) * 0.02 >= 0.25:
                gaps.append((i + j) / 2 * 0.02)
            i = j
        else:
            i += 1
    cut = min(gaps, key=lambda g: abs(g - target))
    return sent, y[:int(cut * sr)]


def run():
    y, _ = sf.read(REF_WAV, dtype="float32")
    dur = len(y) / SR

    # PASS: a genuine take with a whole ending, its own transcript,
    # honest spans
    sent, ys = _slice_fixture()
    p = _write(ys, "good.wav")
    rep = verify.verify_file(p, [sent], "te", SETTINGS,
                             sentence_spans=[[0.0, round(len(ys) / SR, 3)]],
                             expected_duration_s=round(len(ys) / SR, 2))
    check("genuine assembled file PASSES verification",
          rep["pass"] is True,
          str({k: v for k, v in rep["checks"].items()
               if isinstance(v, dict) and not v.get("pass", True)}))

    # dropped sentence: a second script sentence has no audio
    p = _write(y, "dropped.wav")
    rep = verify.verify_file(
        p, [REF_TEXT, "మరొక ముఖ్యమైన వాక్యం ఇక్కడ ఉంది."], "te",
        SETTINGS,
        sentence_spans=[[0.0, round(dur, 3)], [round(dur + 0.6, 3), 4.0]],
        expected_duration_s=round(dur, 2))
    check("dropped sentence FAILS completeness",
          rep["pass"] is False
          and rep["checks"]["completeness"]["pass"] is False,
          str(rep["checks"].get("completeness"))[:200])

    # duplicated sentence: the same take twice, claimed as two
    # different sentences -> cross-match must catch it
    gap = np.zeros(int(0.6 * SR), dtype="f4")
    y2 = np.concatenate([y, gap, y])
    p = _write(y2, "dup.wav")
    rep = verify.verify_file(
        p, [REF_TEXT, "పూర్తిగా వేరే రెండో వాక్యం ఇది."], "te",
        SETTINGS,
        sentence_spans=[[0.0, round(dur, 3)],
                        [round(dur + 0.6, 3), round(dur, 3)]],
        expected_duration_s=round(len(y2) / SR, 2))
    check("duplicated sentence FAILS (cross-match / completeness)",
          rep["pass"] is False, str(rep["checks"])[:200])

    # head grunt on the assembled file -> gate-6 check fails it
    t = np.arange(int(0.22 * SR)) / SR
    grunt = (0.05 * np.sin(2 * np.pi * 150 * t)).astype("f4")
    yg = np.concatenate([grunt, y])
    p = _write(yg, "grunt.wav")
    rep = verify.verify_file(p, [REF_TEXT], "te", SETTINGS,
                             sentence_spans=[[0.0, round(len(yg) / SR, 3)]],
                             expected_duration_s=round(len(yg) / SR, 2))
    check("grunt-headed file FAILS the head-grunt check",
          rep["pass"] is False
          and rep["checks"]["head_grunt"]["pass"] is False,
          str(rep["checks"].get("head_grunt"))[:200])

    # truncated ending: last words missing -> completeness fails
    yt = y[:int(len(y) * 0.55)]
    p = _write(yt, "trunc.wav")
    rep = verify.verify_file(p, [REF_TEXT], "te", SETTINGS,
                             sentence_spans=[[0.0, round(len(yt) / SR, 3)]],
                             expected_duration_s=round(len(yt) / SR, 2))
    check("truncated ending FAILS completeness",
          rep["pass"] is False
          and rep["checks"]["completeness"]["pass"] is False,
          str(rep["checks"].get("completeness"))[:200])

    # padded silence: a 3 s hole inside the file -> gap sanity fails
    hole = np.zeros(int(3.0 * SR), dtype="f4")
    yh = np.concatenate([y[:len(y) // 2], hole, y[len(y) // 2:]])
    p = _write(yh, "hole.wav")
    rep = verify.verify_file(p, [REF_TEXT], "te", SETTINGS,
                             sentence_spans=[[0.0, round(len(yh) / SR, 3)]],
                             expected_duration_s=round(len(yh) / SR, 2))
    check("padded silence FAILS interior-silence sanity",
          rep["pass"] is False
          and rep["checks"]["interior_silence"]["pass"] is False,
          str(rep["checks"].get("interior_silence"))[:200])


if __name__ == "__main__":
    run()
    print("\n" + ("ALL PASS" if not FAILS
                  else f"{len(FAILS)} FAILURES: {FAILS}"))
    sys.exit(1 if FAILS else 0)
