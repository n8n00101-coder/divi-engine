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

GATE 9 — TAIL GRUNT. The mirror of gate 6 at the END of the take:
voiced phonation continuing past the script's last word (owner's ear,
2026-11-17, on the turbo TE/HI samples: "rey / eyh" sounds at sentence
ends). It is glued to the last word — no silence gap — so tail trims
and island checks missed it. Detection lives in tail_grunt_detect:
with an aligner's last-word end it convicts voiced phonation more
than 60 ms past that end; without one it falls back to a
conservative dip-split signature on the final island.
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


# ------------------------------------------------------------ gate 9 -----
# Natural release allowance: calibrated on the shipped samples
# (2026-11-17) — clean sentence finals measure residual <= 0.03 s
# (acoustic phonation end vs the aligner's last-word end); the
# convicted grunt measures 0.08 s. 60 ms sits between the classes
# with ~2x margin on the clean side.
TAIL_GRUNT_ALLOWANCE_S = 0.060
TAIL_GRUNT_LANGS = ("te", "hi")


def _voiced_frac(y, sr, a, b, win=0.040):
    """Fraction of 40 ms sub-windows in [a, b] carrying a real
    periodicity peak (normalised autocorrelation >= 0.3 at a
    60–400 Hz lag) — the voicing test that separates a grunt (voiced
    phonation) from a breath / noise tail (no stable period)."""
    seg = y[int(a * sr):int(b * sr)].astype(np.float64)
    w = int(win * sr)
    if len(seg) < w:
        return None
    lo, hi = int(sr / 400), int(sr / 60)
    hits, total = 0, 0
    for i in range(0, len(seg) - w + 1, max(1, w // 2)):
        s = seg[i:i + w]
        s = s - s.mean()
        if np.sqrt(np.mean(s ** 2)) < 1e-4:
            continue
        ac = np.correlate(s, s, "full")[len(s) - 1:]
        ac = ac / (ac[0] + 1e-12)
        total += 1
        if len(ac) > lo and float(np.max(ac[lo:hi])) >= 0.3:
            hits += 1
    return (hits / total) if total else None


def tail_grunt_detect(path, last_word_end=None):
    """Detect the TAIL GRUNT: voiced phonation that continues past the
    script's last word (the mirror of gate 6's head grunt — the same
    stray "rey / eyh" the owner caught at sentence HEADS on 2026-11-16,
    caught at sentence ENDS on 2026-11-17 in the turbo TE/HI samples).

    Measurement on the shipped samples (2026-11-17): the grunt is
    GLUED to the last word — no silence gap separates it (sub-threshold
    dips < 40 ms), so island-based tail trims missed it, and Whisper
    folds it into the last word or just past it. One shipped Telugu
    sentence carries phonation 80 ms past the aligner's last-word end
    at a dead-flat 140 Hz (IQR 5) — the head grunt's own signature
    (139–168 Hz, flat, ~8–10 dB under the body) at the tail.

    Two modes:
      ASR mode (last_word_end given): residual = acoustic phonation
      end (last island end, floor + 8 dB, 30 ms bridge) minus the
      aligner's last-word end. residual <= 0.060 s is the natural
      release allowance (calibration above). Beyond it, the residual
      segment is convicted when it is VOICED (periodicity-tested over
      its body, past the word's own release edge) — breath/noise
      tails are recorded, not convicted.
      Acoustic-only mode (no aligner): a conservative dip-split
      signature on the final island — a shallow dip (phonation never
      reaches the floor: a glued grunt keeps voicing through it,
      unlike a stop closure) followed by a short, flat, low segment.
      Heuristic; the ASR mode is the convicting instrument wherever
      an aligner is available.
    Returns the evidence either way; 'present' is the verdict."""
    y, sr, db, dt, floor, isl = _profile(path, bridge=0.030)
    dur = len(y) / sr
    ev = {"present": False, "mode": "asr" if last_word_end is not None
          else "acoustic", "duration_s": round(dur, 2),
          "islands": len(isl)}
    if not isl:
        ev["reason"] = "no speech islands found"
        return ev
    body_rms, body_f0 = _body_stats(y, sr, isl)
    phon_end = isl[-1][1]
    ev.update({"phon_end_s": round(phon_end, 2),
               "body_rms_db": round(body_rms, 1),
               "body_f0_hz": round(body_f0, 0) if body_f0 else None})
    if last_word_end is not None:
        residual = phon_end - float(last_word_end)
        ev.update({"last_word_end_s": round(float(last_word_end), 2),
                   "residual_s": round(residual, 3)})
        if residual <= TAIL_GRUNT_ALLOWANCE_S:
            ev["reason"] = ("phonation ends within the %.0f ms release "
                            "allowance" % (TAIL_GRUNT_ALLOWANCE_S * 1000))
            return ev
        # Judge the grunt BODY, skipping the word's own release edge
        # (the first <= 60 ms past the aligner end is partly the last
        # word decaying — voiced by definition, proves nothing).
        zb = float(last_word_end) + min(0.06, residual * 0.25)
        seg_rms = _seg_rms_db(y, sr, float(last_word_end), phon_end)
        f0, iqr = _seg_f0(y, sr, zb, phon_end)
        vf = _voiced_frac(y, sr, zb, phon_end)
        ev.update({"segment_s": [round(float(last_word_end), 2),
                                 round(phon_end, 2)],
                   "segment_rms_db": round(seg_rms, 1),
                   "segment_f0_hz": round(f0, 0) if f0 else None,
                   "segment_f0_iqr_hz": round(iqr, 0) if iqr is not None
                   else None,
                   "segment_voiced_frac": (round(vf, 2) if vf is not None
                                           else None)})
        voiced = vf is not None and vf >= 0.5
        audible = seg_rms >= body_rms - 40.0
        ev["checks"] = {"residual_beyond_allowance": True,
                        "voiced": bool(voiced), "audible": bool(audible)}
        ev["present"] = bool(voiced and audible)
        if ev["present"]:
            ev["reason"] = ("voiced phonation %.2f s past the last word "
                            "(F0 %s Hz) — tail grunt"
                            % (residual, ev["segment_f0_hz"]))
        else:
            ev["reason"] = "post-word tail is not voiced phonation"
        return ev
    # ---- acoustic-only fallback: dip-split signature on the final island
    a, b = isl[-1]
    ev["last_island_s"] = [round(a, 2), round(b, 2)]
    if b - a < 0.25:
        ev["reason"] = "final island too short to split acoustically"
        return ev
    i0 = max(int(a / dt), int((b - 0.60) / dt))
    i1 = int(b / dt)
    seg_db = db[i0:i1]
    if len(seg_db) < 10:
        ev["reason"] = "final island tail too short to scan"
        return ev
    # last local minimum at least 8 dB under both neighbours' maxima,
    # with >= 0.08 s of segment after it
    dip_at, dip_val = None, None
    for k in range(3, len(seg_db) - 3):
        t_k = i0 * dt + k * dt
        if b - t_k < 0.08:
            break
        pre = float(np.max(seg_db[max(0, k - 20):k])) if k else -120.0
        post = float(np.max(seg_db[k + 1:]))
        v = float(seg_db[k])
        if v <= pre - 8.0 and v <= post - 8.0:
            dip_at, dip_val = t_k, v   # keep scanning: the LAST such dip
    if dip_at is None:
        ev["reason"] = "no dip-split signature in the final island"
        return ev
    seg_dur = b - dip_at
    seg_rms = _seg_rms_db(y, sr, dip_at, b)
    f0, iqr = _seg_f0(y, sr, dip_at, b)
    ev.update({"dip_s": round(dip_at, 2), "dip_db": round(dip_val, 1),
               "floor_db": round(floor, 1),
               "segment_s": [round(dip_at, 2), round(b, 2)],
               "segment_rms_db": round(seg_rms, 1),
               "segment_f0_hz": round(f0, 0) if f0 else None,
               "segment_f0_iqr_hz": round(iqr, 0) if iqr is not None
               else None})
    checks = {
        "shallow_dip": dip_val >= floor + 14.0,
        "short_segment": 0.08 <= seg_dur <= 0.40,
        "flat_low_f0": (f0 is not None and 100.0 <= f0 <= 175.0
                        and body_f0 is not None and f0 <= body_f0 - 30.0
                        and (iqr is None or iqr <= 45.0)),
        "under_body": seg_rms <= body_rms - 4.0,
    }
    ev["checks"] = checks
    ev["present"] = all(checks.values())
    if ev["present"]:
        ev["reason"] = ("dip-split flat low segment %.2f s at the tail "
                        "(F0 %s Hz) — tail grunt (acoustic mode)"
                        % (seg_dur, ev["segment_f0_hz"]))
    return ev


def tail_grunt_gate(path, last_word_end=None):
    """Gate 9 report (verification only — this module never edits a
    take for gate 9; the turbo finishing path may CUT a cleanly
    separable grunt at the last-word end, and the engine path simply
    fails the take for a re-roll)."""
    det = tail_grunt_detect(path, last_word_end)
    return {"pass": not det["present"], "present": det["present"],
            "detection": det}


# ------------------------------------------------------- gate 9b --------
def _fine_rms(y, sr, a, b, win_s=0.010, hop_s=0.005):
    """Fine RMS trace (10 ms windows, 5 ms hop) — the resolution at
    which a word's release (energy collapse) and a following grunt
    (energy return) separate."""
    out = []
    w = int(win_s * sr)
    t = a
    while t < b:
        seg = y[int(t * sr):int(t * sr) + w]
        out.append((t, float(20 * np.log10(np.sqrt(np.mean(seg ** 2))
                                           + 1e-9)) if len(seg)
                    else -120.0))
        t += hop_s
    return out


def _spectral_flatness(y, sr, a, b, fmin=100.0, fmax=2000.0):
    """Spectral flatness (geometric/arithmetic PSD mean) in a band.
    Phonation — even creaky, irregular phonation — concentrates
    energy in harmonics (measured 0.27 on the convicted creak tail,
    0.01-0.04 on modal voice); breath / noise is flat (0.58 on a
    synthetic noise control)."""
    seg = y[int(a * sr):int(b * sr)]
    if len(seg) < 1024:
        return None
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2 + 1e-12
    fr = np.fft.rfftfreq(len(seg), 1.0 / sr)
    band = spec[(fr >= fmin) & (fr <= fmax)]
    if not len(band):
        return None
    return float(np.exp(np.mean(np.log(band))) / np.mean(band))


def _win_f0s(y, sr, a, b, win=0.050, hop=0.025):
    """Windowed F0 medians over a span (the _seg_f0 estimator)."""
    out = []
    t = a
    while t + 0.04 <= b:
        f0, _ = _seg_f0(y, sr, t, t + win)
        if f0:
            out.append((t, f0))
        t += hop
    return out


def absorbed_tail_detect(path, last_word_start=None,
                         last_word_end=None):
    """Gate 9b — the ABSORBED tail grunt: phonation folded INSIDE the
    aligner's last-word span, the class gate 9's own report flagged
    as invisible to it (residual vs the aligner end is zero because
    the aligner stretches the word over the grunt). Caught by Ajju's
    ear on the v2 Hindi sample (2026-11-18) after gate 9 passed it.

    Conviction shape (calibrated 2026-11-18, test_absorbed_tail.py):
    inside the final word's span the energy first COLLAPSES to near
    the floor (>= 40 ms at >= 25 dB under the span body, after the
    span's energy peak — the word has ended), then a NEW phonation
    segment >= 60 ms sustains to the phonation end at body level in
    a GRUNT REGIME:
      * creak — F0 median <= 120 Hz (the convicted v2 HI S1 tail:
        73 Hz against a 171 Hz word core) with phonation-grade
        spectral flatness (< 0.45); creak defeats the standard
        autocorrelation voicing test, which is one reason the class
        stayed invisible; or
      * flat plateau — F0 IQR <= 12 Hz and |slope| <= 60 Hz/s at
        >= 20 Hz below the final word's core F0 (the v1 HI tails:
        IQR 0.6-3.8, slope -5..-16 Hz/s).
    A legitimate final syllable after a stop closure (the false-
    positive shape: TE ఆపదు / కలిసిపోతాయి) rides the declination
    down at -160..-210 Hz/s and is NOT convicted; a natural release
    never returns after a floor collapse. Detection only ever FAILS
    the take for a re-roll — nothing is ever cut inside a word."""
    ev = {"present": False, "method": "absorbed-collapse-return"}
    y, sr, db, dt, floor, isl = _profile(path, bridge=0.030)
    if not isl:
        ev["reason"] = "no speech islands"
        return ev
    body_rms, body_f0 = _body_stats(y, sr, isl)
    a0, phon_end = isl[-1]
    # The collapse itself can split the final island (a deep dip
    # under the island threshold): the analysis window covers the
    # trailing island COMPLEX — islands separated by collapse-grade
    # gaps (<= 0.12 s) — while the phonation end stays the last
    # island's end.
    j = len(isl) - 1
    while j > 0 and isl[j][0] - isl[j - 1][1] <= 0.12:
        j -= 1
    a0 = isl[j][0]
    start = max(a0, phon_end - 0.45)
    if last_word_start is not None:
        start = max(a0, min(last_word_start - 0.05, phon_end - 0.10))
    rows = _fine_rms(y, sr, start, phon_end + 0.01)
    ev.update({"phon_end_s": round(phon_end, 3),
               "span_s": [round(start, 3), round(phon_end, 3)],
               "body_rms_db": round(body_rms, 1)})
    if len(rows) < 10:
        ev["reason"] = "span too short to judge"
        return ev
    span_body = float(np.percentile([r for _, r in rows], 75))
    thr = span_body - 25.0
    ev["span_body_db"] = round(span_body, 1)
    ev["collapse_thr_db"] = round(thr, 1)
    peak_i = int(np.argmax([r for _, r in rows]))
    collapse = None
    run = []
    for i in range(peak_i, len(rows)):
        if rows[i][1] <= thr:
            run.append(i)
        else:
            if len(run) >= 8:      # >= 40 ms at 5 ms hop
                collapse = (run[0], run[-1])
                break
            run = []
    if collapse is None and len(run) >= 8:
        collapse = (run[0], run[-1])
    if collapse is None:
        ev["reason"] = "no floor collapse after the word peak"
        return ev
    c_end = rows[collapse[1]][0]
    ev["collapse_s"] = [round(rows[collapse[0]][0], 3), round(c_end, 3)]
    if c_end < phon_end - 0.35:
        ev["reason"] = "collapse too early in the span (syllable gap)"
        return ev
    ret_dur = phon_end - c_end
    ret = [r for (t, r) in rows if t > c_end]
    if not ret:
        ev["reason"] = "collapse runs to the phonation end (release)"
        return ev
    ret_med = float(np.median(ret[:-4])) if len(ret) > 4 \
        else float(np.median(ret))
    ev["return_s"] = round(ret_dur, 3)
    ev["return_med_db"] = round(ret_med, 1)
    if ret_dur < 0.060:
        ev["reason"] = "post-collapse return too short (< 60 ms)"
        return ev
    if ret_med < body_rms - 20.0:
        ev["reason"] = "post-collapse return too quiet to be the grunt"
        return ev
    # grunt-regime test on the return segment
    f0w = _win_f0s(y, sr, c_end + 0.005, phon_end)
    f0s = [f for _, f in f0w]
    ev["return_f0s"] = [round(f, 0) for f in f0s]
    core_f0 = None
    if last_word_start is not None and last_word_end is not None \
            and last_word_end > last_word_start:
        mid = last_word_start + (last_word_end - last_word_start) * 0.5
        cf = [f for _, f in _win_f0s(y, sr, last_word_start, mid)]
        core_f0 = float(np.median(cf)) if cf else None
    ev["word_core_f0_hz"] = (round(core_f0, 0) if core_f0 else None)
    regime = None
    if f0s:
        med = float(np.median(f0s))
        ev["return_f0_med_hz"] = round(med, 0)
        if med <= 120.0:
            flat = _spectral_flatness(y, sr, c_end + 0.005,
                                      phon_end - 0.005)
            ev["return_flatness"] = (round(flat, 3)
                                     if flat is not None else None)
            if flat is not None and flat < 0.45:
                regime = "creak"
        if regime is None and len(f0s) >= 3:
            iqr = float(np.percentile(f0s, 75) - np.percentile(f0s, 25))
            tt = np.array([t for t, _ in f0w])
            ff = np.array(f0s)
            slope = float(np.polyfit(tt - tt[0], ff, 1)[0])
            ev["return_f0_iqr_hz"] = round(iqr, 1)
            ev["return_f0_slope_hz_s"] = round(slope, 0)
            below = (core_f0 is not None and med <= core_f0 - 20.0) \
                or (core_f0 is None and 120.0 < med <= 185.0)
            if iqr <= 12.0 and abs(slope) <= 60.0 and below:
                regime = "flat_plateau"
    ev["regime"] = regime
    if regime:
        ev["present"] = True
        ev["reason"] = ("absorbed tail grunt: voiced %s segment %.2f s "
                        "returns after a floor collapse inside the "
                        "final word (F0 med %s Hz, word core %s Hz)"
                        % (regime, ret_dur, ev.get("return_f0_med_hz"),
                           ev.get("word_core_f0_hz")))
    else:
        ev["reason"] = ("post-collapse return is not in a grunt regime "
                        "(declining syllable / release)")
    return ev


def absorbed_tail_gate(path, last_word_start=None, last_word_end=None):
    """Gate 9b report (verification only — never edits the take;
    a conviction fails the take for a re-roll)."""
    det = absorbed_tail_detect(path, last_word_start, last_word_end)
    return {"pass": not det["present"], "present": det["present"],
            "detection": det}
