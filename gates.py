"""The quality gates of the Julie AI Voice Engine.

These gates exist because every one of them maps to a real defect that was
once shipped by hand and caught by a human ear (2026-11-14):

  1. NO-HINT language identity — a "Telugu" sample once detected as Punjabi
     (0.486) when the recognizer was NOT told the language first. Forcing the
     language into the checker masks between-language diction; detecting
     WITHOUT a hint does not.
  2. GHOST-WORD scan — the same sample's unhinted transcript literally
     contained the English phrase "feel safer" four times. Foreign words the
     engine hallucinated at phrase joints, invisible to a forced-language
     check, visible in the unhinted transcript.
  3. PRONUNCIATION (forced-language word probabilities + phonetic similarity)
     — conjunct-heavy and long words smeared or merged while a sentence-level
     "all words present" check passed them.
  4. PHYS (swallowed words) — words eaten mid-word: too short for their
     syllable count, or with a mid-word energy collapse / abrupt cut tail.
     A word can be ASR-readable and still be audibly swallowed.
  5. PITCH band — take-to-take pitch-centre wander (163–251 Hz across
     splices) made one voice sound like several. A take outside the band is
     re-rolled, never pitch-shifted.

Added 2026-11-16 (owner's ear, OmniVoice route — acoustic_gates.py):
  6. HEAD GRUNT — the OmniVoice route prepends a short, quiet, flat
     low-pitched voiced grunt to nearly every generated sentence; heard
     at joins as a stray "rey / ey orey". engine.py auto-mutes it at
     generation time and records the action in the QC report; this gate
     verifies no grunt survives into a gated take.
  7. CUT WORD — a take whose final word is truncated, chopped at the
     file edge, or stranded as a detached weak tail after the main
     final island fails and is re-rolled; a sentence with no whole
     ending ships nothing. Acoustic shape only — gates 1–3 judge
     which words were said.

Local ASR only: proxy env vars are stripped in this process (a proxy breaks
local model loads). Nothing in here needs the network.
"""
import os

for _k in list(os.environ.keys()):
    if "proxy" in _k.lower():
        del os.environ[_k]

import difflib
import json
import re
import sys

import numpy as np
import librosa
from faster_whisper import WhisperModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phonetics import LANG_SIMPLE, LANG_SYLLABLES, any_simple, simplify  # noqa: E402

# Whisper model: env override, else the local cache used in production,
# else the hub name "base" (downloaded once by faster-whisper).
def _model_path():
    env = os.environ.get("JULIE_WHISPER_MODEL")
    if env:
        return env
    local = os.path.expanduser("~/workspace/voice-lib/fw-base")
    if os.path.isdir(local):
        return local
    return "base"


_model = None


def get_model():
    global _model
    if _model is None:
        _model = WhisperModel(_model_path(), device="cpu", compute_type="int8")
    return _model


SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "voice", "settings.json")


def load_settings():
    with open(SETTINGS_PATH) as fh:
        return json.load(fh)


# ------------------------------------------------------------- ASR helpers -
def asr_tokens(path, lang):
    """Forced-language transcription with word timestamps (16 kHz feed, so
    timestamps are true seconds on the file's own acoustic timeline)."""
    y, sr = librosa.load(path, sr=16000, mono=True)
    segs, info = get_model().transcribe(
        y.astype(np.float32), language=lang, beam_size=5, word_timestamps=True)
    simple = LANG_SIMPLE[lang]
    toks = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                toks.append({"tok": t, "phon": simple(t),
                             "prob": round(float(w.probability), 3),
                             "start": round(float(w.start), 2),
                             "end": round(float(w.end), 2)})
    return toks, float(info.language_probability)


def nohint_detect(path):
    """Gate 1's raw material: transcribe with NO language hint."""
    y, sr = librosa.load(path, sr=16000, mono=True)
    segs, info = get_model().transcribe(
        y.astype(np.float32), language=None, beam_size=5, word_timestamps=True)
    segs = list(segs)
    text = " ".join(s.text.strip() for s in segs).strip()
    words = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                words.append({"tok": t, "prob": round(float(w.probability), 3)})
    return {"lang": info.language,
            "prob": round(float(info.language_probability), 3),
            "text": text, "words": words}


# ------------------------------------------------------------- alignment ---
def sim(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def align(words_phon, toks):
    """DP alignment of script words to ASR tokens. Returns a per-word
    assignment list plus the indices of junk (unmatched) tokens."""
    W, T = len(words_phon), len(toks)
    INF = float('inf')
    dp = [[INF] * (T + 1) for _ in range(W + 1)]
    bk = [[None] * (T + 1) for _ in range(W + 1)]
    dp[0][0] = 0.0
    for i in range(W + 1):
        for j in range(T + 1):
            c = dp[i][j]
            if c == INF:
                continue
            if i < W:  # consume 1..4 tokens for word i
                cat = ""
                for k in range(1, 5):
                    if j + k - 1 >= T:
                        break
                    cat += toks[j + k - 1]["phon"]
                    nc = c + (1 - sim(words_phon[i], cat))
                    if nc < dp[i + 1][j + k]:
                        dp[i + 1][j + k] = nc
                        bk[i + 1][j + k] = ("word", i, j, k)
            if i + 1 < W and j < T:  # merged: 1 token for words i, i+1
                nc = c + (1 - sim(words_phon[i] + words_phon[i + 1],
                                  toks[j]["phon"])) + 0.15
                if nc < dp[i + 2][j + 1]:
                    dp[i + 2][j + 1] = nc
                    bk[i + 2][j + 1] = ("merged", i, j, 1)
            if j < T:  # junk token
                nc = c + 0.45
                if nc < dp[i][j + 1]:
                    dp[i][j + 1] = nc
                    bk[i][j + 1] = ("junk", i, j, 1)
            if i < W:  # missing word
                nc = c + 0.9
                if nc < dp[i + 1][j]:
                    dp[i + 1][j] = nc
                    bk[i + 1][j] = ("missing", i, j, 0)
    assign = [None] * W
    junk = []
    i, j = W, T
    while (i, j) != (0, 0):
        step = bk[i][j]
        if step is None:
            break
        kind, pi, pj, k = step
        if kind == "word":
            assign[pi] = {"toks": list(range(pj, pj + k)), "merged": False}
            i, j = pi, pj
        elif kind == "merged":
            assign[pi] = {"toks": [pj], "merged": True}
            assign[pi + 1] = {"toks": [pj], "merged": True}
            i, j = pi, pj
        elif kind == "junk":
            junk.append(pj)
            i, j = pi, pj
        elif kind == "missing":
            assign[pi] = {"toks": [], "merged": False, "missing": True}
            i, j = pi, pj
    return assign, sorted(junk)


# ------------------------------------------------------------- acoustics ---
def f0_rms(path, span=None):
    y, sr = librosa.load(path, sr=24000, mono=True)
    if span is not None:
        a = max(0, int(span[0] * sr))
        b = min(len(y), int(span[1] * sr))
        if b - a > sr:  # only restrict when the span is sane
            y = y[a:b]
    dur = len(y) / sr
    hop = 256
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-9)
    act = db > -45
    speech = y[np.repeat(act, hop)[:len(y)]] if act.any() else y
    rms_db = float(20 * np.log10(np.sqrt(np.mean(speech ** 2)) + 1e-9)) if len(speech) else -99.0
    f0, flag, _ = librosa.pyin(y, fmin=70, fmax=500, sr=sr)
    fv = f0[flag] if (f0 is not None and flag is not None) else np.array([])
    f0med = float(np.median(fv)) if len(fv) else -1.0
    return {"dur": round(dur, 2), "f0_med": round(f0med, 1), "rms_db": round(rms_db, 2)}


def pitch_gate(path, settings=None, span=None):
    """Gate 5: F0 median inside the locked band."""
    settings = settings or load_settings()
    lo, hi = settings["gates"]["pitch_band_hz"]
    r = f0_rms(path, span)
    return {"pass": bool(lo <= r["f0_med"] <= hi), **r, "band": [lo, hi]}


def frame_db(path):
    y, sr = librosa.load(path, sr=24000, mono=True)
    hop, win = 240, 480
    n = max(1, (len(y) - win) // hop)
    idx = np.arange(n)[:, None] * hop + np.arange(win)[None, :]
    fr = y[np.minimum(idx, len(y) - 1)]
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9), hop / sr


def find_islands(db, dt, thr, bridge=0.060, min_len=0.080):
    """Speech islands: frames above thr, gaps <= bridge joined."""
    above = db > thr
    isl = []
    i = 0
    n = len(db)
    while i < n:
        if above[i]:
            j = i
            gap = 0
            last = i
            while j < n:
                if above[j]:
                    last = j
                    gap = 0
                else:
                    gap += dt
                    if gap > bridge:
                        break
                j += 1
            if (last - i + 1) * dt >= min_len:
                isl.append((i * dt, (last + 1) * dt))
            i = max(j, i + 1)
        else:
            i += 1
    return isl


# ------------------------------------------------------- PHYS (gate 4) -----
def _phys_for_unit(db, dt, floor_ref, islands, words, probs, start, end, lang):
    """Swallowed-word physics for one ASR unit (one word, or a merged pair).
    The ASR span locates the word; the acoustic island clips it; the loud
    core (contiguous run above peak-18 dB containing the peak) defines the
    interior. Returns (hard_flags, notes)."""
    syllables = LANG_SYLLABLES[lang]
    simple = LANG_SIMPLE[lang]
    hard, notes = [], []
    chosen = [iv for iv in islands if iv[1] > start - 0.05 and iv[0] < end + 0.05]
    if not chosen:
        return [f"no acoustic island found near ASR span {start:.2f}-{end:.2f}s"], notes
    a0 = max(min(iv[0] for iv in chosen), start - 0.05)
    a1 = min(max(iv[1] for iv in chosen), end + 0.05)
    if a1 <= a0:
        a0, a1 = min(iv[0] for iv in chosen), max(iv[1] for iv in chosen)
    speech_dur = sum(max(0.0, min(iv[1], a1) - max(iv[0], a0)) for iv in chosen)
    syll = sum(syllables(w) for w in words)
    if speech_dur < 0.6 * syll * 0.16:
        hard.append(f"duration {speech_dur:.2f}s speech < 60% of min "
                    f"syllable-expected {syll * 0.16:.2f}s ({syll} syll)")
    i0, i1 = int(a0 / dt), max(int(a0 / dt) + 1, int(a1 / dt))
    seg = db[i0:i1]
    peak = float(np.max(seg))
    pk = int(np.argmax(seg))
    thr = peak - 18.0
    lo = pk
    while lo > 0 and seg[lo - 1] > thr:
        lo -= 1
    hi = pk
    while hi < len(seg) - 1 and seg[hi + 1] > thr:
        hi += 1
    core = seg[lo:hi + 1]
    gem = any(re.search(r"([bcdfghjklmnpqrstvyz])\1", simple(w)) for w in words)
    single = len(words) == 1
    if len(core):
        below = core < thr
        run = 0
        for k, b in enumerate(below):
            run = run + 1 if b else 0
            if run * dt > 0.040:
                dip_min = float(np.min(core[k - run + 1:k + 1]))
                dip_dur = run * dt
                near_floor = dip_min < floor_ref + 8.0
                weak = (probs is not None and min(probs) < 0.65)
                msg = (f"mid-word dip {peak - dip_min:.0f} dB deep, "
                       f"{dip_dur * 1000:.0f} ms, at {a0 + (lo + k - run + 1) * dt:.2f}s "
                       f"(dip {dip_min:.0f} dB, hum floor ~{floor_ref:.0f} dB)")
                is_hard = near_floor and ((dip_dur > 0.090 and not gem) or weak) and single
                if is_hard:
                    hard.append("swallowed middle: " + msg)
                else:
                    notes.append("dip noted (closure/uncorroborated): " + msg)
                break

    def seg_db(a, b):
        x = db[int(a / dt):max(int(a / dt) + 1, int(b / dt))]
        return float(np.mean(x)) if len(x) else -120.0

    fin = seg_db(a1 - 0.030, a1)
    post = seg_db(a1, a1 + 0.030) if a1 + 0.030 < len(db) * dt else -120.0
    if fin > peak - 12.0 and post < fin - 15.0:
        hard.append(f"abrupt cut: island-final-30ms {fin:.0f} dB vs peak "
                    f"{peak:.0f} dB, post {post:.0f} dB")
    return hard, notes


# ------------------------------------------------- gates 3 + 4 (forced) ----
def forced_check(path, lang, script_words, settings=None):
    """Pronunciation (word probs + phonetic similarity + junk tokens) and
    PHYS swallowed-word checks on one take, from a forced-language ASR."""
    settings = settings or load_settings()
    min_prob = settings["gates"]["word_prob_min"]
    simple = LANG_SIMPLE[lang]
    syllables = LANG_SYLLABLES[lang]
    toks, langp = asr_tokens(path, lang)
    wphon = [simple(w) for w in script_words]
    assign, junk = align(wphon, toks)
    rows = []
    pron_fails = []
    for idx, w in enumerate(script_words):
        a = assign[idx]
        if a is None or a.get("missing") or not a["toks"]:
            rows.append({"word": w, "prob": None, "sim": 0.0, "status": "MISSING"})
            pron_fails.append(f"{w}: missing")
            continue
        probs = [toks[t]["prob"] for t in a["toks"]]
        cat = "".join(toks[t]["phon"] for t in a["toks"])
        s = sim(wphon[idx], cat)
        wp = min(probs)
        status = "OK"
        if a["merged"]:
            if s >= 0.75:
                status = "MERGED-CLEAN"  # tokenisation merged the pair; phonetics present
            else:
                status = "MERGED"
                pron_fails.append(f"{w}: merged into one ASR token with loss (sim {s:.2f})")
        if s < 0.62:
            status = "SMEARED"
            pron_fails.append(f"{w}: smeared (sim {s:.2f})")
        if wp < min_prob:
            status = (status + "+LOWPROB") if status != "OK" else "LOWPROB"
            pron_fails.append(f"{w}: prob {wp:.2f} < {min_prob:.2f}")
        rows.append({"word": w, "prob": wp, "sim": round(s, 2), "status": status,
                     "toks": [toks[t]["tok"] for t in a["toks"]],
                     "start": toks[a["toks"][0]]["start"],
                     "end": toks[a["toks"][-1]]["end"]})
    junk_rows = [{"tok": toks[t]["tok"], "prob": toks[t]["prob"], "start": toks[t]["start"]}
                 for t in junk
                 if toks[t]["prob"] >= 0.30 or len(toks[t]["phon"]) >= 3]
    if junk_rows:
        pron_fails.append(f"junk tokens: {[j['tok'] for j in junk_rows]}")

    # PHYS gate on acoustic islands
    phys_fail_words = []
    phys_fails = []
    timed = [r for r in rows if r.get("start") is not None]
    if timed:
        db, dt = frame_db(path)
        gap_frames = db[db > -90.0]
        floor_ref = float(np.percentile(gap_frames, 5)) if len(gap_frames) else -50.0
        islands = find_islands(db, dt, floor_ref + 8.0)
        total_speech = sum(iv[1] - iv[0] for iv in islands)
        units = []
        for r in timed:
            if units and abs(units[-1]["start"] - r["start"]) < 1e-6 and \
                    abs(units[-1]["end"] - r["end"]) < 1e-6:
                units[-1]["rows"].append(r)
            else:
                units.append({"start": r["start"], "end": r["end"], "rows": [r]})
        total_syll = sum(syllables(r["word"]) for r in timed)
        take_sps = (total_speech / total_syll) if total_syll else 0.0
        for u in units:
            probs = [r["prob"] for r in u["rows"] if r["prob"] is not None]
            hard, notes = _phys_for_unit(db, dt, floor_ref, islands,
                                         [r["word"] for r in u["rows"]],
                                         probs or None, u["start"], u["end"], lang)
            chosen = [iv for iv in islands
                      if iv[1] > u["start"] - 0.05 and iv[0] < u["end"] + 0.05]
            sdur = sum(iv[1] - iv[0] for iv in chosen)
            syll = sum(syllables(r["word"]) for r in u["rows"])
            if take_sps > 0 and syll > 0 and sdur > 0 and (sdur / syll) < 0.6 * take_sps:
                hard.append(f"duration: {sdur / syll:.3f}s/syll < 60% of take pace "
                            f"{take_sps:.3f}s/syll (word {sdur:.2f}s, {syll} syll)")
            for r in u["rows"]:
                r["phys"] = hard
                r["phys_notes"] = notes
            if hard:
                phys_fail_words += [r["word"] for r in u["rows"]]
                for r in u["rows"]:
                    for f in hard:
                        phys_fails.append(f"{r['word']}: PHYS {f}")
    f0r = f0_rms(path)
    if timed:
        span = (max(0.0, timed[0]["start"] - 0.1), timed[-1]["end"] + 0.1)
        f0r = f0_rms(path, span)
        f0r["f0_span"] = [round(span[0], 2), round(span[1], 2)]
    mp = min([r["prob"] for r in rows if r["prob"] is not None], default=0.0)
    return {"pron_pass": len(pron_fails) == 0,
            "phys_pass": len(phys_fails) == 0,
            "fails": pron_fails + phys_fails,
            "pron_fails": pron_fails, "phys_fails": phys_fails,
            "min_prob": mp, "rows": rows, "junk": junk_rows,
            "lang_p_forced": round(langp, 2),
            "phys_fail_words": phys_fail_words, **f0r}


# ------------------------------------------------------- gate 2 (ghosts) ---
GHOST_BLACK = set("""safer safe saves saved say says said fee fees fail fails failed foe
feel feels felt just dose doze hello sorry please thank thanks okay yes yeah wow hey""".split())

# Romanized-Hindi words whisper legitimately produces when it renders Hindi in
# Latin script — these are NOT ghosts.
ROMAN_HI_OK = set("""yeh ye hai hain ki ka ke ko mein me aur jo woh wo bhi nahi nahin hota hoti hote tha thi the se par tak
jab tab kya ek do teen din bhar aap aapne aapka aapki ne suna dekha seekha sikha asli sach shuru jaye
jama asthayi roop agar wahin reh agli subah zyada zyadatar baatein baaten aapas ghulmil mil jis pal neend utarte
dimag dimaag kaam karna band karta uska tabhi pehle sab wah jaana jaata jaati hona honi chahiye lekin magar phir
kuch koi kisi is us iska uski mere mera meri tere tera apna apne khud bahut kam dheere roz raat kal aaj abhi kabhi
kaisa kaisi kyon kahan kidhar idhar udhar aisa aisi waisa waisi jitna jitni utna kitna kitni raha rahi rahe
gaya gayi gaye liya diya kiya hua hui hue wala wali wale kar karke bina diye liye log baat""".split())

GHOST_PHONS = {simplify(w) for w in GHOST_BLACK}


def _skel(p):
    return re.sub(r"[aeiou]", "", p)


def ghost_scan(unhinted_res, lang, script_words):
    """Foreign ghost words in the UNHINTED transcript.

    (a) Latin tokens that are blacklisted English or (for hi) not plausible
    romanized Hindi; for en, Latin tokens matching no script word.
    (b) Phonetic hunt: every unhinted token is normalized and aligned against
    the script; junk tokens and tokens under weakly-matched words are checked
    against the English blacklist in phonetic space, and substantial tokens
    matching NO script word at all are ghosts too (this is the check that
    catches Urdu-script renderings of 'fees safer')."""
    text = unhinted_res["text"]
    ghosts = []
    lat = re.findall(r"[A-Za-z]+", text)
    script_lat = {re.sub(r"[^a-z]", '', w.lower()) for w in script_words}
    for t in lat:
        tl = t.lower()
        # A token that IS a script word is never a ghost. The blacklist
        # exists to catch FOREIGN English bleed in te/hi takes; without
        # this exemption it also fired on an English take's own script
        # words ("hello" is in GHOST_BLACK, so "Hello, this is Julie."
        # failed gate 2 on every roll, deterministically — V4 diagnosis
        # 2026-11-15; the approved reference recording likewise tripped
        # it on its own words just/feels/safer). This matches the
        # docstring above: "for en, Latin tokens matching no script
        # word". te/hi behaviour is unchanged: their scripts strip to
        # non-Latin here, so a Latin blacklist token is still foreign
        # unless the script itself contains it (code-mixed lines).
        if tl in GHOST_BLACK and tl not in script_lat:
            ghosts.append(t)
        elif lang == "hi" and tl not in ROMAN_HI_OK:
            ghosts.append(t)
        elif lang == "en" and tl not in script_lat and len(tl) >= 3:
            if max((sim(simplify(tl), simplify(w)) for w in script_words),
                   default=0.0) < 0.75:
                ghosts.append(t)
    toks = [{"tok": w["tok"], "phon": any_simple(w["tok"]), "prob": w["prob"]}
            for w in unhinted_res["words"]]
    if not toks:
        return ghosts + ["<empty unhinted transcript>"]
    simple = LANG_SIMPLE[lang]
    wphon = [simple(w) for w in script_words]
    assign, junk = align(wphon, toks)
    cand = set(junk)
    for idx, a in enumerate(assign):
        if a is None or a.get("missing") or not a.get("toks"):
            continue
        cat = "".join(toks[t]["phon"] for t in a["toks"])
        if sim(wphon[idx], cat) < 0.75:
            cand.update(a["toks"])
    for t in sorted(cand):
        p = toks[t]["phon"]
        if not p:
            continue
        why = None
        if len(p) >= 3:
            for gp in GHOST_PHONS:
                r = difflib.SequenceMatcher(None, p, gp).ratio()
                if r >= 0.80 or (r >= 0.60 and len(_skel(p)) >= 2 and _skel(p) == _skel(gp)):
                    why = f"phon '{p}' ~ ghost '{gp}' (ratio {r:.2f})"
                    break
        if why is None and len(p) >= 4 and toks[t]["prob"] >= 0.30:
            best = max((sim(p, wp) for wp in wphon), default=0.0)
            if best < 0.45:
                why = f"phon '{p}' matches no script word (best sim {best:.2f})"
        if why:
            ghosts.append(f"{toks[t]['tok']} :: {why}")
    return ghosts


# ------------------------------------------------------------- all gates ---
def run_all_gates(path, lang, text, settings=None):
    """Run every gate on one take. Returns a report dict; report['pass'] is
    True only if ALL gates pass (the original five plus gates 6/7)."""
    settings = settings or load_settings()
    g = settings["gates"]
    script_words = [w for w in re.split(r"\s+", text.strip()) if w]
    det = nohint_detect(path)
    need = g["nohint_prob_min"].get(lang, g["nohint_prob_min"]["default"])
    lang_pass = bool(det["lang"] == lang and det["prob"] >= need)
    ghosts = ghost_scan(det, lang, script_words)
    fc = forced_check(path, lang, script_words, settings)
    lo, hi = g["pitch_band_hz"]
    pitch_pass = bool(lo <= fc["f0_med"] <= hi)
    # Gates 6/7 (2026-11-16): acoustic take-shape checks. Gate 6 here is
    # verification only — engine.py auto-mutes the head grunt at
    # generation time (acoustic_gates.head_grunt_gate(apply=True)) and
    # records the action in the QC report's per-roll "gen" entry, so a
    # take reaching this point should already be grunt-free.
    import acoustic_gates
    hg = acoustic_gates.head_grunt_gate(path)
    cw = acoustic_gates.cut_word_gate(path)
    report = {
        "pass": bool(lang_pass and not ghosts and fc["pron_pass"]
                     and fc["phys_pass"] and pitch_pass
                     and hg["pass"] and cw["pass"]),
        "gate1_nohint_language": {"pass": lang_pass, "detected": det["lang"],
                                  "prob": det["prob"], "required": need,
                                  "unhinted_text": det["text"]},
        "gate2_ghost_words": {"pass": len(ghosts) == 0, "ghosts": ghosts},
        "gate3_pronunciation": {"pass": fc["pron_pass"], "min_prob": fc["min_prob"],
                                "fails": fc["pron_fails"], "rows": fc["rows"],
                                "junk": fc["junk"]},
        "gate4_phys_swallowed": {"pass": fc["phys_pass"], "fails": fc["phys_fails"],
                                 "fail_words": fc["phys_fail_words"]},
        "gate5_pitch": {"pass": pitch_pass, "f0_med": fc["f0_med"], "band": [lo, hi],
                        "rms_db": fc["rms_db"], "dur": fc["dur"]},
        "gate6_head_grunt": hg,
        "gate7_cut_word": cw,
    }
    return report


if __name__ == "__main__":
    # python3 gates.py <audio> <lang> <text>
    rep = run_all_gates(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    sys.exit(0 if rep["pass"] else 1)
