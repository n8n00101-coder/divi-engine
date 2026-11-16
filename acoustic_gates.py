"""Acoustic take-shape gates 6 + 7 for Divi Engine
(Ajju's orders, 2026-11-16). Self-contained (numpy / librosa /
soundfile only, NO environment side effects) so engine.py can call it
inside the generation subprocess — gates.py strips proxy vars at
import, which would break later Space calls in the same process.

GATE 6 — HEAD GRUNT. The OmniVoice route prepends a short, quiet,
flat low-pitched voiced grunt to (nearly) every generated sentence
file: it starts ~0.10 s in, runs 0.16–0.25 s at a flat F0 of
~139–168 Hz (~55 Hz below this speaker's ~209 Hz median), sits
~10 dB under the speech body, and is separated from the first real
word by silence. Heard at every sentence join, it is the stray
"rey / ey orey" the owner caught on 2026-11-16. The segment is
non-word phonation sitting in silence, so the fix is to MUTE it in
place (8 ms cosine fades, file length unchanged) — never a splice,
never a regeneration of real speech. Detection is conservative: an
isolated, quiet, flat, low first island before the first real word.
A genuine first word is essentially never all of those at once.

GATE 7 — CUT WORD. A take whose FINAL word is truncated must never
ship (owner's ear, 2026-11-16: Sample B sentence 6, whose ending
"mana varaku vasthayi" never landed). This gate judges the SHAPE of
the ending acoustically; it cannot know WHICH word was said — that
is what gates 1–3 are for. It fails a take when:
  (a) abrupt cut — the final island is still loud at its end and the
      level then falls off a cliff (the PHYS per-word rule, applied
      to the take's ending);
  (b) detached weak tail — a short (<= 0.35 s), quiet (>= 4 dB under
      the speech body), flat, low island stranded AFTER the main
      final island by a dip: the ending did not land as one word
      with the sentence (Sample B v1 sentence 6 exactly: main island
      ends 3.30 s, then a lone 0.21 s flat ~150 Hz segment);
  (c) file-edge chop — speech is still active in the last frames of
      the file (the take was cut by its own file boundary);
  (d) pinched ending — the final island is anomalously short
      (< 0.10 s) against the take's own island profile.
Natural sentence endings — energy and pitch decaying together into
the final word — pass all four checks.
"""
import numpy as np

HOP, WIN = 240, 480            # 10 ms hop, 20 ms window @ 24 kHz
ACT_FLOOR_DB = -90.0


def _load24(path):
    import librosa
    y, sr = librosa.load(path, sr=24000, mono=True)
    return y.astype(np.float64), sr


def _frame_db(y):
    n = max(1, (len(y) - WIN) // HOP + 1)
    idx = np.minimum(np.arange(n)[:, None] * HOP + np.arange(WIN)[None, :],
                     len(y) - 1)
    rms = np.sqrt(np.mean(y[idx] ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), HOP / 24000.0


def _islands(db, dt, thr, bridge=0.060, min_len=0.080):
    """Speech islands: frames above thr, gaps <= bridge joined."""
    above = db > thr
    out, i, n = [], 0, len(db)
    while i < n:
        if above[i]:
            j, gap, last = i, 0.0, i
            while j < n:
                if above[j]:
                    last, gap = j, 0.0
                else:
                    gap += dt
                    if gap > bridge:
                        break
                j += 1
            if (last - i + 1) * dt >= min_len:
                out.append((i * dt, (last + 1) * dt))
            i = max(j, i + 1)
        else:
            i += 1
    return out


def _floor_ref(db):
    g = db[db > ACT_FLOOR_DB]
    return float(np.percentile(g, 5)) if len(g) else -50.0


def _seg_rms_db(y, sr, a, b):
    seg = y[int(a * sr):int(b * sr)]
    if len(seg) == 0:
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))


def _ac_f0(y, sr, a, b, wins=4):
    """Autocorrelation F0 (median, IQR) over sub-windows of a segment —
    the fallback estimator for very quiet short segments where YIN
    locks onto the subharmonic."""
    seg = y[int(a * sr):int(b * sr)].astype(np.float64)
    if len(seg) < int(0.05 * sr):
        return None, None
    edges = np.linspace(0, len(seg), wins + 1).astype(int)
    ests = []
    for i in range(wins):
        s = seg[edges[i]:edges[i + 1]]
        if len(s) < int(0.04 * sr):
            continue
        s = s - s.mean()
        if np.sqrt(np.mean(s ** 2)) < 1e-4:
            continue
        ac = np.correlate(s, s, "full")[len(s) - 1:]
        ac = ac / (ac[0] + 1e-12)
        lo, hi = int(sr / 450), int(sr / 60)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] < 0.25:  # no real periodicity peak in this window
            continue
        ests.append(sr / lag)
    if not ests:
        return None, None
    ests = np.array(ests)
    return (float(np.median(ests)),
            float(np.percentile(ests, 75) - np.percentile(ests, 25)))


def _seg_f0(y, sr, a, b):
    """(median, IQR) F0 over a segment, or (None, None). YIN first,
    with octave folding of outlier frames; if YIN locks onto the
    subharmonic (median < 100 Hz while autocorrelation finds a strong
    fundamental an octave up — measured on Sample B8's head grunt:
    YIN 73 Hz vs autocorrelation 156 Hz), the autocorrelation
    estimate wins."""
    import librosa
    seg = y[int(a * sr):int(b * sr)].astype(np.float32)
    if len(seg) < int(0.04 * sr):
        return None, None
    try:
        f0 = librosa.yin(seg, fmin=60, fmax=450, sr=sr,
                         frame_length=1024, hop_length=256)
    except Exception:
        return None, None
    f0 = f0[(f0 > 60) & (f0 < 450)]
    if not len(f0):
        return _ac_f0(y, sr, a, b)
    if len(f0) >= 6:  # YIN edge frames bleed into the surrounding
        # silence on short segments; judge the central body of the span
        k = max(1, int(0.15 * len(f0)))
        f0 = f0[k:-k] if len(f0) - 2 * k >= 3 else f0
    med = float(np.median(f0))
    if med > 0:  # fold outlier frames toward the median by an octave
        f0 = np.where(f0 < med * 0.65, f0 * 2.0, f0)
        f0 = np.where(f0 > med * 1.50, f0 / 2.0, f0)
    med = float(np.median(f0))
    iqr = float(np.percentile(f0, 75) - np.percentile(f0, 25))
    if med < 100.0 or iqr > 45.0:
        ac_med, ac_iqr = _ac_f0(y, sr, a, b)
        if ac_med is not None and ((med < 100.0 and ac_med > 1.6 * med)
                                   or (ac_iqr is not None
                                       and ac_iqr < iqr)):
            return ac_med, ac_iqr
    return med, iqr


def _profile(path, bridge=0.060):
    y, sr = _load24(path)
    db, dt = _frame_db(y)
    floor = _floor_ref(db)
    isl = _islands(db, dt, floor + 8.0, bridge=bridge)
    return y, sr, db, dt, floor, isl


def _body_stats(y, sr, isl):
    """Energy-weighted RMS (dB) and F0 median of the speech body
    (the longest island — the sentence's main span)."""
    if not isl:
        return -120.0, None
    main = max(isl, key=lambda iv: iv[1] - iv[0])
    f0, _ = _seg_f0(y, sr, main[0], main[1])
    return _seg_rms_db(y, sr, main[0], main[1]), f0


# ------------------------------------------------------------ gate 6 -----
def head_grunt_detect(path):
    """Detect the OmniVoice head-grunt signature at a take's head.
    Returns a dict: present + the measured evidence either way."""
    y, sr, db, dt, floor, isl = _profile(path)
    ev = {"present": False, "islands": len(isl)}
    if len(isl) < 2:
        ev["reason"] = "fewer than two speech islands"
        return ev
    (a, b), (c, _d) = isl[0], isl[1]
    dur = b - a
    gap = c - b
    rms = _seg_rms_db(y, sr, a, b)
    body_rms, body_f0 = _body_stats(y, sr, isl[1:])
    f0, iqr = _seg_f0(y, sr, a, b)
    ev.update({"span_s": [round(a, 2), round(b, 2)],
               "dur_s": round(dur, 2), "gap_after_s": round(gap, 2),
               "rms_db": round(rms, 1), "body_rms_db": round(body_rms, 1),
               "f0_hz": round(f0, 0) if f0 else None,
               "f0_iqr_hz": round(iqr, 0) if iqr is not None else None,
               "body_f0_hz": round(body_f0, 0) if body_f0 else None})
    checks = {
        "starts_at_head": a <= 0.20,
        "short": 0.08 <= dur <= 0.40,
        "isolated_by_silence": gap >= 0.12,
        "quiet_vs_body": rms <= body_rms - 4.0,
        "low_flat_f0": (f0 is not None and 100.0 <= f0 <= 190.0
                        and body_f0 is not None and f0 <= body_f0 - 30.0
                        and (iqr is None or iqr <= 60.0)),
    }
    ev["checks"] = checks
    ev["present"] = all(checks.values())
    return ev


def mute_head_grunt(path):
    """Mute a detected head grunt in place (8 ms cosine edge fades,
    file length unchanged). Returns the action record for the QC
    report: {"muted": bool, ...evidence}."""
    det = head_grunt_detect(path)
    if not det["present"]:
        return {"muted": False, "detection": det}
    import soundfile as sf
    y, sr = sf.read(path)
    mono = y.ndim == 1
    col = y if mono else y[:, 0]
    a, b = det["span_s"]
    i0, i1 = int(a * sr), int(b * sr)
    f = int(0.008 * sr)
    col = col.copy()
    if i0 > 0:
        n = min(f, i0)
        col[i0 - n:i0] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, n)))
    col[i0:i1] = 0.0
    if i1 < len(col):
        n = min(f, len(col) - i1)
        col[i1:i1 + n] *= 0.5 * (1 - np.cos(np.linspace(0, np.pi, n)))
    if mono:
        sf.write(path, col, sr)
    else:
        y = y.copy()
        y[:, 0] = col
        sf.write(path, y, sr)
    return {"muted": True, "span_s": det["span_s"],
            "f0_hz": det["f0_hz"], "rms_db": det["rms_db"],
            "note": "head grunt muted in place (non-word phonation in "
                    "silence; no speech sample altered)"}


def head_grunt_gate(path, apply=False):
    """Gate 6 report. With apply=True the grunt is muted first and the
    gate re-checks the result (this is the engine's generation path);
    with apply=False it is a pure verification (gates.run_all_gates)."""
    action = mute_head_grunt(path) if apply else None
    det = head_grunt_detect(path)
    out = {"pass": not det["present"], "present": det["present"],
           "detection": det}
    if action is not None:
        out["action"] = action
    return out


# ------------------------------------------------------------ gate 7 -----
def cut_word_gate(path):
    """Gate 7 report: is the take's ending whole? See module docstring
    for the four failure shapes and the honest scope of the check.
    Tail analysis uses a 30 ms island bridge (a >= 40 ms dip separates
    islands) so a stranded tail segment is not bridged into the main
    island and hidden."""
    y, sr, db, dt, floor, isl = _profile(path, bridge=0.030)
    dur = len(y) / sr
    rep = {"pass": True, "fails": [], "islands": len(isl),
           "duration_s": round(dur, 2)}
    if not isl:
        rep.update({"pass": False, "fails": ["no speech islands found"]})
        return rep
    body_rms, body_f0 = _body_stats(y, sr, isl)
    a, b = isl[-1]
    last_rms = _seg_rms_db(y, sr, a, b)
    last_f0, last_iqr = _seg_f0(y, sr, a, b)
    rep.update({"last_island_s": [round(a, 2), round(b, 2)],
                "last_island_dur_s": round(b - a, 2),
                "last_rms_db": round(last_rms, 1),
                "body_rms_db": round(body_rms, 1),
                "last_f0_hz": round(last_f0, 0) if last_f0 else None,
                "body_f0_hz": round(body_f0, 0) if body_f0 else None})

    def seg_db(t0, t1):
        x = db[int(t0 / dt):max(int(t0 / dt) + 1, int(t1 / dt))]
        return float(np.mean(x)) if len(x) else -120.0

    # (c) file-edge chop: the final island runs into the file boundary
    # while still clearly active.
    if b >= dur - 0.03 and seg_db(max(0.0, dur - 0.03), dur) > floor + 8.0:
        rep["fails"].append(
            "file-edge chop: speech still active in the final 30 ms "
            f"({seg_db(max(0.0, dur - 0.03), dur):.0f} dB) at {dur:.2f}s")
    # (a) abrupt cut: final island still near its own peak at its end,
    # then a >15 dB cliff within 30 ms.
    i0, i1 = int(a / dt), max(int(a / dt) + 1, int(b / dt))
    seg = db[i0:i1]
    if len(seg):
        peak = float(np.max(seg))
        fin = seg_db(b - 0.030, b)
        post = seg_db(b, b + 0.030) if b + 0.030 < len(db) * dt else -120.0
        rep["final_peak_db"] = round(peak, 1)
        if fin > peak - 12.0 and post < fin - 15.0:
            rep["fails"].append(
                f"abrupt cut: island-final-30ms {fin:.0f} dB vs peak "
                f"{peak:.0f} dB, post {post:.0f} dB")
    # (b) detached weak tail: a short, quiet, flat, low island stranded
    # after the main final island by a dip.
    if len(isl) >= 2:
        pa, pb = isl[-2]
        gap = a - pb
        main_dur = pb - pa
        if (0.04 <= gap and (b - a) <= 0.35 and main_dur >= 0.50
                and last_rms <= body_rms - 4.0
                and last_f0 is not None and body_f0 is not None
                and last_f0 <= body_f0 - 30.0
                and (last_iqr is None or last_iqr <= 60.0)):
            rep["fails"].append(
                f"detached weak tail: final island {a:.2f}-{b:.2f}s "
                f"({b - a:.2f}s, {last_rms:.0f} dB vs body "
                f"{body_rms:.0f} dB, F0 {last_f0:.0f} vs {body_f0:.0f} Hz) "
                f"stranded {gap * 1000:.0f} ms after the main island — "
                "the ending did not land as one word")
    # (d) pinched ending: final island anomalously short vs the take's
    # own island profile.
    durs = sorted(iv[1] - iv[0] for iv in isl)
    med = float(np.median(durs)) if durs else 0.0
    if (b - a) < 0.10 and med >= 0.30:
        rep["fails"].append(
            f"pinched ending: final island {b - a:.2f}s vs take median "
            f"island {med:.2f}s")
    rep["pass"] = not rep["fails"]
    return rep
