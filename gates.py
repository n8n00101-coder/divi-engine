"""The quality gates of Divi Engine.

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

Added 2026-11-17 (strict audit of the gate-2 ear-check samples):
  8. HEAD BLEED — the IndicF5 route sometimes opens a take with
     ~1–1.5 s of garbled speech that is not the script at all: a
     phrase from the REFERENCE passage itself (the natspan2 ref ends
     "...జూలై 2024 లో కొత్త క్రిమినల్ చట్టాలు వచ్చాయి" — bled takes open
     with that "kotta kriminil chattalu"), leaking into the
     generation before the first script word. No earlier
     gate measures the head: gate 6 covers only a ~0.08–0.4 s grunt
     island, and gates 1–3 judge the whole take, where a strong body
     can carry a bled head through alignment. The bleed also inflates
     the take's duration and drags the measured pace down. This gate
     decodes the head window alone (from speech onset, forced
     language, thresholds disabled) and fails the take when the head
     legibly carries the DEFAULT reference passage's closing phrase,
     when pre-script speech cannot be rendered phonetically at all,
     or when nothing of the script's opening is recognizable. Other
     head mush is recorded as evidence, not failed: fw-base garbles
     this voice's genuine openings too, and the ear-approved fixed13
     takes carry a non-default reference's tail echo -- the hard
     signature is the convicted one.

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
from phonetics import (LANG_SIMPLE, LANG_SYLLABLES, any_simple, en_simple,  # noqa: E402
                       simplify, te_phon, te_simple)

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


# ------------------------------------------- gate 2 loanword awareness -----
# Recalibration (2026-11-16, owner's GPU+gate-fix decision, after turbo
# proof run 43881089750): gate 2 failed 522 of 865 gated takes in that run,
# and the dominant false-positive class was the channel's OWN English
# loanwords. The script writes them in Telugu script (క్రిమినల్, థియరీ,
# సేఫ్); unhinted whisper renders them in Latin or Arabic script, and the
# cross-script phonetic distance (e.g. థియరీ 'tiyari' vs "theory" 'teory',
# sim ~0.40) made correct takes read as foreign bleed. These borrowings
# are not bleed — the channel's narration code-mixes exactly these word
# types (docs/ENGLISH_MIX_POLICY.md; 304 attested lexemes in
# voice/english_mix_classes.json).
#
# Behind the settings flag gates.gate2_loanword_aware (default False —
# the locked bar, byte for byte, until the owner's ear approves the
# samples built under the new gate). When ON, the scan stays STRICTLY
# SUBTRACTIVE: the alignment and the candidate set are unchanged, and a
# candidate is cleared only when it can be attributed to a loanword that
# is actually present in THIS sentence's script, through one of:
#   (i)   exact English form — the token IS the attested lexeme (or its
#         regular -s/-es plural) of a script loanword. Exact only, on
#         purpose: the comparative 'safer' must not be excused by the
#         script's సేఫ్ (safe), or the 2026-11-14 'feel safer' bleed
#         would be whitewashed by the fix that cites it.
#   (ii)  dual-form phonetic match — the token's phon reaches
#         EN_MATCH_BAR (0.62) against the ENGLISH phonetic form of a
#         script loanword. The English bar is higher than the 0.45
#         Telugu-form bar: mid-range similarity between two different
#         English words is common ('money' vs 'model' = 0.60), and a
#         bled word that merely resembles a legit loanword must not
#         clear. (Short English forms <= 3 phon chars are held to the
#         same 0.62 inside _en_match.)
#   (iii) consonant-skeleton match against an English loanword form
#         (skeleton sim >= 0.80, both skeletons >= 3/4 chars) — whisper's
#         Arabic-script renderings drop short vowels, so a loanword can
#         arrive as a bare consonant frame ('krimnl' for criminal).
# Telugu only: the lexicon is the Telugu channel's attested mix. Hindi
# keeps its romanized-Hindi handling; English its script-match rule.

_MIX_CLASSES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "voice", "english_mix_classes.json")
_loan_lexicon_cache = None


def _loan_lexicon():
    """Attested English-mix lexicon entries: {english, en_phon, stem,
    stem_phon, stem_rx}. Stems are Telugu-script forms as attested in the
    channel corpus; a few are stored as 're:<regex>' for boundary-
    sensitive forms (their literal head is used for the phon form)."""
    global _loan_lexicon_cache
    if _loan_lexicon_cache is not None:
        return _loan_lexicon_cache
    entries = []
    try:
        with open(_MIX_CLASSES_PATH, encoding="utf-8") as fh:
            mix = json.load(fh)
        for cls in mix.get("classes", {}).values():
            for w in cls.get("words", []):
                eng = (w.get("english") or "").strip().lower()
                stem = (w.get("telugu_form_stem") or "").strip()
                if not eng or not stem:
                    continue
                rx = None
                if stem.startswith("re:"):
                    pat = stem[3:]
                    try:
                        rx = re.compile(pat)
                    except re.error:
                        rx = None
                    stem = pat.split("(?")[0].split("(")[0]
                entries.append({"english": eng, "en_phon": en_simple(eng),
                                "stem": stem, "stem_phon": te_simple(stem),
                                "stem_tephon": te_phon(stem),
                                "stem_rx": rx})
    except Exception:
        entries = []
    _loan_lexicon_cache = entries
    return entries


def _sentence_loans(script_words, lang):
    """script-word index -> lexicon entries the word carries. Telugu
    agglutinates case/plural suffixes onto the END of the stem
    (కాలేజీని from కాలేజీ, కేసులు from కేస), so the stem is a PREFIX of
    the word. Three prefix channels, in order:
    - the lexicon's own boundary regex, where one is stored;
    - raw-script prefix (exact, suffixation-proof);
    - phonetic prefix on the LENGTH-PRESERVING te_phon forms, for
      spelling variants.
    The collapsed te_simple forms are NOT used for attribution at any
    length: simplify() erases vowel length, so the 'model' stem మోడల
    ('modala' simple) falsely matched the native word మొదలవుతుంది
    (begins) in the proof-pool audit (2026-11-16). Mid-word containment
    and short prefixes likewise falsely attributed native words (కథ
    'kata' -> 'cut' via 'kat', మూడు 'mudu' -> 'mood' via 'mud',
    కారణం -> 'car' via 'kar', యూనివర్సిటీ -> 'city' via a mid-word
    సిటీ) and are not used."""
    loans = {}
    if lang != "te":
        return loans
    for idx, w in enumerate(script_words):
        wpf = te_phon(w)
        for e in _loan_lexicon():
            hit = False
            if e["stem_rx"] is not None and e["stem_rx"].search(w):
                hit = True
            if not hit and e["stem"] and w.startswith(e["stem"]):
                hit = True
            if not hit and len(e["stem_tephon"]) >= 3 \
                    and wpf.startswith(e["stem_tephon"]):
                hit = True
            if hit:
                loans.setdefault(idx, []).append(e)
    return loans


def _lexeme_hit(tok_text, loans):
    """True when a Latin-script token IS an attested loanword of this
    sentence's script in its English form (or regular -s/-es plural).
    Exact-form only — see the design note above."""
    t = re.sub(r"[^a-z]", "", tok_text.lower())
    if len(t) < 3:
        return False
    for es in loans.values():
        for e in es:
            eng = e["english"]
            if " " in eng:
                continue
            if t == eng or t == eng + "s" or t == eng + "es":
                return True
    return False


# A token clears against a loanword's ENGLISH form only at this bar —
# higher than the 0.45 Telugu-form bar, because mid-range similarity
# between two DIFFERENT English words is common ('money' vs 'model'
# scores 0.60) and a bled wrong word that merely resembles a legit
# loanword must not clear. The skeleton channel (0.80) is separate:
# whisper's Arabic-script renderings drop short vowels systematically.
EN_MATCH_BAR = 0.62


def _en_match(p, en_targets):
    """Best effective match of a token phon against the ENGLISH phonetic
    forms of the sentence's loanwords (channels ii + iii above)."""
    best = 0.0
    sk = _skel(p)
    for ep in en_targets:
        s = sim(p, ep)
        if len(ep) <= 3 and s < 0.62:
            s = 0.0  # short forms need the stronger bar (channel ii)
        if s > best:
            best = s
        if len(sk) >= 3 and len(_skel(ep)) >= 4:
            if sim(sk, _skel(ep)) >= 0.80 and best < 0.80:
                best = 0.80  # vowel-unreliable rendering (channel iii)
    return best


def ghost_scan(unhinted_res, lang, script_words, settings=None):
    """Foreign ghost words in the UNHINTED transcript.

    (a) Latin tokens that are blacklisted English or (for hi) not plausible
    romanized Hindi; for en, Latin tokens matching no script word.
    (b) Phonetic hunt: every unhinted token is normalized and aligned against
    the script; junk tokens and tokens under weakly-matched words are checked
    against the English blacklist in phonetic space, and substantial tokens
    matching NO script word at all are ghosts too (this is the check that
    catches Urdu-script renderings of 'fees safer').

    Loanword awareness (settings flag gates.gate2_loanword_aware, default
    off): with the flag on, tokens attributable to an attested English
    loanword of THIS sentence's script are not ghosts — see the design
    note at _loan_lexicon. With the flag off, loans == {} and every new
    branch below is inert: the locked behaviour, byte for byte."""
    text = unhinted_res["text"]
    ghosts = []
    if settings is None:
        settings = load_settings()
    aware = bool(settings.get("gates", {}).get("gate2_loanword_aware", False))
    loans = _sentence_loans(script_words, lang) if aware else {}
    en_targets = [e["en_phon"] for es in loans.values() for e in es]
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
            # Loanword exemption (flag-gated): a blacklisted form that IS
            # this sentence's own attested loanword in its English form
            # ("safe" for సేఫ్, "fees" for ఫీజు) is a script word, not
            # bleed — the same principle as the script-match exemption
            # below. Exact form only: 'safer' is not excused by సేఫ్.
            if loans and _lexeme_hit(t, loans):
                continue
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
        # Loanword exemption (flag-gated): the token is this sentence's
        # own attested loanword in its English form (e.g. whisper wrote
        # "Safe" where the script says సేఫ్) — a rendering, not bleed.
        # Exact form only, so 'safer'/'fees' without the corresponding
        # loanword in the script still fail below.
        if loans and _lexeme_hit(toks[t]["tok"], loans):
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
            if best < 0.45 and loans:
                # Dual-form match: the token may render a script loanword
                # in its English form rather than its Telugu form. The
                # English form has its own, higher bar (EN_MATCH_BAR).
                if _en_match(p, en_targets) >= EN_MATCH_BAR:
                    best = EN_MATCH_BAR
            if best < 0.45:
                why = f"phon '{p}' matches no script word (best sim {best:.2f})"
        if why:
            ghosts.append(f"{toks[t]['tok']} :: {why}")
    return ghosts


# ------------------------------------------------- gate 8 (head bleed) ---
HEAD_BLEED_LANGS = ("te", "hi")
_HEAD_WINDOW_S = 2.4        # head decode window from speech onset
_HEAD_TAIL_WORDS = 4        # ref passage tail length used as the signature
_HEAD_TAIL2_MIN = 0.69      # 2-word ref-tail sub-phrase match bar
                            # (measured class gap on the 2026-11-17
                            # calibration corpus: convicted bleed
                            # heads score 0.70-0.92, clean/approved
                            # heads <= 0.48)
_HEAD_TAIL3_MIN = 0.68      # 3-word ref-tail sub-phrase match bar
_HEAD_ANCHOR_MIN = 0.60     # script-word recognition bar for the anchor
_HEAD_FLOOR_MIN = 0.50      # below this nothing of the opening is readable

_mix_lexicon = None
_ref_tails = None


def _loanword_forms():
    """Telugu stem -> [English forms] from voice/english_mix_classes.json
    (the corpus-attested English-mix classes; the same lexicon the
    gate-2 loanword recalibration consults). Loaded once; a missing or
    unreadable file yields an empty lexicon, never an error."""
    global _mix_lexicon
    if _mix_lexicon is None:
        _mix_lexicon = {}
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "voice", "english_mix_classes.json")
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for cls in (data.get("classes") or {}).values():
                for w in cls.get("words") or []:
                    stem = (w.get("telugu_form_stem") or "").strip()
                    eng = (w.get("english") or "").strip()
                    if not stem or not eng or stem.startswith("re:"):
                        continue
                    forms = []
                    for f in eng.split("/"):
                        f = re.sub(r"\(.*?\)", "", f).strip()
                        if f:
                            forms.append(f)
                    if forms:
                        _mix_lexicon.setdefault(stem, []).extend(forms)
        except Exception:
            _mix_lexicon = {}
    return _mix_lexicon


# fw-base frequently latches onto TAMIL script for this voice's line
# openings (genuine narration included); phonetics.any_simple has no
# Tamil branch, so Tamil tokens reduce to empty phons and every
# phonetic check goes blind. Tamil is an abugida parallel to Telugu,
# so a compact transliteration restores them -- used ONLY by gate 8.
_TA_CONS = {"க": "k", "ங": "ng", "ச": "c", "ஞ": "ny", "ட": "T", "ண": "N",
            "த": "t", "ந": "n", "ன": "n", "ப": "p", "ம": "m", "ய": "y",
            "ர": "r", "ற": "R", "ல": "l", "ள": "L", "ழ": "zh", "வ": "v",
            "ஜ": "j", "ஷ": "Sh", "ஸ": "s", "ஹ": "h"}
_TA_INDEP = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu",
             "எ": "e", "ஏ": "ee", "ஐ": "ai", "ஒ": "o", "ஓ": "oo", "ஔ": "au",
             "ஃ": "h"}
_TA_SIGN = {"ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu", "ெ": "e",
            "ே": "ee", "ை": "ai", "ொ": "o", "ோ": "oo", "ௌ": "au", "்": ""}


def _ta_simple(tok):
    out = []
    i = 0
    while i < len(tok):
        ch = tok[i]
        if ch in _TA_CONS:
            base = _TA_CONS[ch]
            nxt = tok[i + 1] if i + 1 < len(tok) else ""
            if nxt == "்":
                out.append(base)
                i += 2
            elif nxt in _TA_SIGN:
                out.append(base + _TA_SIGN[nxt])
                i += 2
            else:
                out.append(base + "a")
                i += 1
        elif ch in _TA_INDEP:
            out.append(_TA_INDEP[ch])
            i += 1
        elif ch in _TA_SIGN:
            out.append(_TA_SIGN[ch])
            i += 1
        else:
            i += 1
    from phonetics import simplify as _simplify
    return _simplify("".join(out))


def _head_phon(tok):
    """Token -> simplified phonetics for gate 8 (adds the Tamil branch
    any_simple lacks; every other script defers to any_simple). Mixed
    Tamil+other tokens occur (fw-base script salad): keep whichever
    rendering carries more phonetic content."""
    base = any_simple(tok)
    if any("\u0b80" <= ch <= "\u0bff" for ch in tok):
        ta = _ta_simple(tok)
        if len(ta) > len(base):
            return ta
    return base


def _simple(word, lang):
    """Script word -> simplified phonetics in its own language."""
    return LANG_SIMPLE.get(lang, any_simple)(word)


def _acceptable_phons(word, lang):
    """Phonetic forms a script word may legitimately be HEARD as: its
    own simplified form plus, for te, the English form of an attested
    loanword (she may say the English word itself -- gate 2's finding).
    A stem matches when the word starts with it and the remainder is a
    short inflection (<= 4 chars)."""
    own = _simple(word, lang)
    forms = {own}
    if lang in HEAD_BLEED_LANGS:
        for stem, engs in _loanword_forms().items():
            s = _simple(stem, lang)
            if s and own.startswith(s) and len(own) - len(s) <= 4:
                for e in engs:
                    forms.add(en_simple(e))
    return sorted(f for f in forms if f)


def _ref_tail_subphons():
    """(default_ref, {ref_name: [sub-phons]}) built from
    voice/refs/refs.json: for each canonical reference passage, the
    phonetic sub-phrases of its last _HEAD_TAIL_WORDS significant
    words (2-word and 3-word windows). The DEFAULT reference (the
    production conditioning source, refs.json "default") is the
    fail-active signature; every other ref's best score is recorded
    as advisory evidence only -- the owner's ear-approved fixed13
    takes carry the natspan3 tail's echo, so a hard gate on every
    ref's tail would refuse the owner's own approved takes (the same
    reason gates 3/4/5 are advisory for te/hi)."""
    global _ref_tails
    if _ref_tails is None:
        _ref_tails = (None, {})
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "voice", "refs", "refs.json")
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            tails = {}
            for name, ref in (data.get("refs") or {}).items():
                words = [w for w in re.split(r"\s+", (ref.get("text")
                         or "").strip()) if w]
                ph = []
                for w in words:
                    p = _simple(w, "te")
                    if len(p) >= 3:
                        ph.append(p)
                tail = ph[-_HEAD_TAIL_WORDS:]
                subs = set()
                for n in (2, 3):
                    for i in range(len(tail) - n + 1):
                        subs.add(("".join(tail[i:i + n]), n))
                if subs:
                    tails[name] = sorted(subs)
            _ref_tails = (data.get("default"), tails)
        except Exception:
            _ref_tails = (None, {})
    return _ref_tails


def _best_concat_sim(forms, phons, pos, kmax=4):
    """Best similarity of any acceptable form against the concatenation
    of up to kmax token phons starting at pos; returns (sim, k)."""
    best, bestk = 0.0, 1
    cat = ""
    for k in range(1, kmax + 1):
        if pos + k - 1 >= len(phons):
            break
        cat += phons[pos + k - 1]
        if not cat:
            continue
        for f in forms:
            v = sim(f, cat)
            if v > best:
                best, bestk = v, k
    return best, bestk


def head_bleed_check(toks, script_words, lang):
    """Pure matcher for gate 8 (no ASR): toks are the head decode's
    word tokens [{tok, phon, prob, start, end}]; script_words is the
    sentence split on whitespace. Decides from the token stream alone.

    FAILS when:
      (1) the head carries the DEFAULT reference passage's closing
          phrase, legibly -- a token window up to the script anchor
          matching a 2-word tail sub-phrase at >= _HEAD_TAIL2_MIN or a
          3-word one at >= _HEAD_TAIL3_MIN (the convicted bleed: the
          conditioning visibly re-speaking the reference's last words
          instead of the script). Sub-phrases that are part of the
          script's own opening are excluded.
      (2) significant pre-script speech the phonetics cannot render
          at all (empty phons over a >= 0.5 s lead span), or
      (3) nothing of the script's opening is recognizable anywhere in
          the head decode (no anchor and no near miss).
    Everything else passes; mush that resembles neither the reference
    tail nor nothing-at-all is RECORDED (lead_junk, tail_echo) as
    evidence, mirroring the advisory treatment gates 3/4/5 get for
    te/hi: fw-base garbles this voice's genuine openings too, and the
    owner's approved takes carry non-default-ref tail echo -- a hard
    fail on raw mush would refuse her own narration.

    Anchor and phrase scans run over the AUDIBLE subsequence (tokens
    with non-empty phons): an unrenderable token must not act as free
    glue that lets a later script word "anchor" across it."""
    words = [w for w in script_words if w]
    res = {"pass": True, "fails": [], "head_text": "", "word1_sim": None,
           "anchor_word": None, "lead_junk": [], "tail_match": None,
           "tail_echo": None, "window_s": None}
    if not toks:
        res["fails"].append("head decode is empty")
        res["pass"] = False
        return res
    res["head_text"] = " ".join(t["tok"] for t in toks)
    phons = [t.get("phon") or "" for t in toks]
    sig = [i for i, t in enumerate(toks)
           if len(phons[i]) >= 3 or (t.get("prob") or 0) >= 0.5]
    aud = [i for i in range(len(toks)) if phons[i]]
    aph = [phons[i] for i in aud]
    # anchor: earliest audible position where any of the first 3
    # script words is recognizably heard (tolerant concat scan,
    # loanword forms included)
    anchor = None          # (aud_pos, k, word_index, sim)
    for apos in range(len(aud)):
        for wi in range(min(3, len(words))):
            v, k = _best_concat_sim(_acceptable_phons(words[wi], lang),
                                    aph, apos)
            if v >= _HEAD_ANCHOR_MIN and (anchor is None
                                          or wi < anchor[2]):
                anchor = (apos, k, wi, v)
        if anchor is not None:
            break
    w1, _ = _best_concat_sim(_acceptable_phons(words[0], lang), aph, 0) \
        if words else (0.0, 1)
    res["word1_sim"] = round(w1, 3)
    anchor_orig = aud[anchor[0]] if anchor is not None else None
    if anchor is not None:
        res["anchor_word"] = words[anchor[2]]
        res["lead_junk"] = [toks[i]["tok"] for i in sig if i < anchor_orig]
    # (1) default-ref tail signature; windows may start up to and
    # including the anchor position (the phrase can share a word with
    # the script, e.g. its own kriminal token inside the bleed)
    default_ref, tails = _ref_tail_subphons()
    script_open = "".join(_simple(w, lang) for w in words[:4])
    limit = (anchor[0] + 1) if anchor is not None else len(aud)
    best = {}              # ref -> (margin, score, n_words, window_text)
    for name, subs in tails.items():
        subs = [(s, n) for s, n in subs if s not in script_open]
        if not subs:
            continue
        for apos in range(0, max(0, limit)):
            cat = ""
            for k in range(1, 6):
                if apos + k - 1 >= len(aph):
                    break
                cat += aph[apos + k - 1]
                if not cat:
                    continue
                for s, n in subs:
                    bar = _HEAD_TAIL2_MIN if n == 2 else _HEAD_TAIL3_MIN
                    margin = sim(s, cat) - bar
                    cur = best.get(name)
                    if cur is None or margin > cur[0]:
                        best[name] = (margin, sim(s, cat), n, " ".join(
                            toks[aud[j]]["tok"]
                            for j in range(apos, apos + k)))
    for name, (margin, v, n, wtext) in best.items():
        entry = {"ref": name, "score": round(v, 3), "sub_words": n,
                 "window": wtext}
        if name == default_ref:
            res["tail_match"] = entry
            if margin >= 0:
                res["fails"].append(
                    "reference bleed: head opens with the %s passage "
                    "tail (%r, match %.2f)" % (name, wtext, v))
        elif res["tail_echo"] is None or v > res["tail_echo"]["score"]:
            res["tail_echo"] = entry
    # (2) unrenderable pre-script speech
    lead = [i for i in sig if anchor_orig is None or i < anchor_orig]
    if lead:
        span = toks[lead[-1]]["end"] - toks[lead[0]]["start"]
        phon_len = sum(len(phons[i]) for i in lead)
        if span >= 0.5 and phon_len < 3:
            res["fails"].append(
                "head unrecognizable: %.1fs of pre-script speech cannot "
                "be rendered phonetically" % span)
    # (3) nothing of the opening recognizable
    if anchor is None:
        near = 0.0
        for wi in range(min(4, len(words))):
            forms = _acceptable_phons(words[wi], lang)
            for apos in range(len(aph)):
                v, _k = _best_concat_sim(forms, aph, apos)
                near = max(near, v)
        if near < _HEAD_FLOOR_MIN:
            res["fails"].append(
                "head unrecognizable: none of the script's first words "
                "found in the head decode (best %.2f)" % near)
    res["pass"] = not res["fails"]
    return res


def head_bleed_gate(path, lang, text, settings=None):
    """Gate 8: reference-bleed / garbled head. Decodes the take's head
    (onset-anchored _HEAD_WINDOW_S window, thresholds disabled like
    gates 3/4) and runs head_bleed_check. Active only when
    settings.gates.head_bleed_gate is on AND the language is te/hi --
    the bleed was proven on Telugu IndicF5 takes conditioned on the
    Telugu references. The flag ships ON: the calibration controls
    hold (the two convicted gate-2 takes fail; the ear-approved
    fixed13 takes and her genuine reference spans pass)."""
    active = bool(settings and (settings.get("gates") or {}).get(
        "head_bleed_gate")) and lang in HEAD_BLEED_LANGS
    rep = {"pass": True, "active": active}
    if not active:
        return rep
    try:
        db, dt = frame_db(path)
        gap = db[db > -90.0]
        floor = float(np.percentile(gap, 5)) if len(gap) else -50.0
        islands = find_islands(db, dt, floor + 8.0)
        onset = islands[0][0] if islands else 0.0
        y, sr = librosa.load(path, sr=16000, mono=True)
        a = max(0.0, onset - 0.05)
        b = min(len(y) / sr, onset + _HEAD_WINDOW_S)
        seg = y[int(a * sr):int(b * sr)]
        segs, _info = get_model().transcribe(
            seg.astype(np.float32), language=lang, beam_size=5,
            word_timestamps=True, condition_on_previous_text=False,
            log_prob_threshold=None, no_speech_threshold=None)
        toks = []
        for s in segs:
            for w in (s.words or []):
                t = w.word.strip()
                if t:
                    toks.append({"tok": t, "phon": _head_phon(t),
                                 "prob": round(float(w.probability), 3),
                                 "start": round(float(w.start) + a, 2),
                                 "end": round(float(w.end) + a, 2)})
        chk = head_bleed_check(toks, (text or "").split(), lang)
        rep.update(chk)
        rep["window_s"] = [round(a, 2), round(b, 2)]
    except Exception as exc:  # a gate must never crash the pipeline
        rep["pass"] = False
        rep["fails"] = ["head-bleed gate error: %s" % exc]
    return rep


# ------------------------------------------------- gate 9 (tail grunt) ---
TAIL_GRUNT_LANGS = ("te", "hi")
_TAIL_WINDOW_S = 2.4        # tail decode window ending at the file end


def tail_grunt_gate(path, lang, text, settings=None):
    """Gate 9: tail grunt — voiced phonation past the script's last
    word (the mirror of gate 8's head bleed, at the tail; owner's ear,
    2026-11-17, on the turbo TE/HI samples). Decodes the take's TAIL
    (the last _TAIL_WINDOW_S seconds, thresholds disabled like gate 8)
    for the aligner's last-word end, then runs the acoustic residual
    check (acoustic_gates.tail_grunt_detect). Active only when
    settings.gates.tail_grunt_gate is on AND the language is te/hi —
    the grunt is an OmniVoice-route artefact proven on those clones.
    The engine path never cuts: a convicted take FAILS and re-rolls
    (the turbo finishing path may cut a cleanly separable grunt at
    the last-word end instead; same detection, different remedy).
    If the tail window decodes to no words, the acoustic-only
    dip-split signature decides (documented heuristic)."""
    active = bool(settings and (settings.get("gates") or {}).get(
        "tail_grunt_gate")) and lang in TAIL_GRUNT_LANGS
    rep = {"pass": True, "active": active}
    if not active:
        return rep
    try:
        import acoustic_gates
        y, sr = librosa.load(path, sr=16000, mono=True)
        dur = len(y) / sr
        a = max(0.0, dur - _TAIL_WINDOW_S)
        seg = y[int(a * sr):]
        segs, _info = get_model().transcribe(
            seg.astype(np.float32), language=lang, beam_size=5,
            word_timestamps=True, condition_on_previous_text=False,
            log_prob_threshold=None, no_speech_threshold=None)
        words = [w for s in segs for w in (s.words or [])]
        lwe = (a + float(words[-1].end)) if words else None
        det = acoustic_gates.tail_grunt_detect(path, lwe)
        rep.update(det)
        rep["pass"] = not det["present"]
        rep["window_s"] = [round(a, 2), round(dur, 2)]
        if det["present"]:
            rep["fails"] = ["tail grunt: %s" % det.get("reason", "")]
    except Exception as exc:  # a gate must never crash the pipeline
        rep["pass"] = False
        rep["fails"] = ["tail-grunt gate error: %s" % exc]
    return rep



# ------------------------------------------------------------- all gates ---
def run_all_gates(path, lang, text, settings=None):
    """Run every gate on one take. Returns a report dict; report['pass'] is
    True only if ALL gates pass (the original five plus gates 6/7, and
    gates 8/9 wherever they are active)."""
    settings = settings or load_settings()
    g = settings["gates"]
    script_words = [w for w in re.split(r"\s+", text.strip()) if w]
    det = nohint_detect(path)
    need = g["nohint_prob_min"].get(lang, g["nohint_prob_min"]["default"])
    lang_pass = bool(det["lang"] == lang and det["prob"] >= need)
    ghosts = ghost_scan(det, lang, script_words, settings)
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
    hb = head_bleed_gate(path, lang, text, settings)
    tg = tail_grunt_gate(path, lang, text, settings)
    report = {
        "pass": bool(lang_pass and not ghosts and fc["pron_pass"]
                     and fc["phys_pass"] and pitch_pass
                     and hg["pass"] and cw["pass"]
                     and (hb["pass"] if hb["active"] else True)
                     and (tg["pass"] if tg["active"] else True)),
        "gate1_nohint_language": {"pass": lang_pass, "detected": det["lang"],
                                  "prob": det["prob"], "required": need,
                                  "unhinted_text": det["text"]},
        "gate2_ghost_words": {"pass": len(ghosts) == 0, "ghosts": ghosts,
                              "loanword_aware": bool(
                                  g.get("gate2_loanword_aware", False))},
        "gate3_pronunciation": {"pass": fc["pron_pass"], "min_prob": fc["min_prob"],
                                "fails": fc["pron_fails"], "rows": fc["rows"],
                                "junk": fc["junk"]},
        "gate4_phys_swallowed": {"pass": fc["phys_pass"], "fails": fc["phys_fails"],
                                 "fail_words": fc["phys_fail_words"]},
        "gate5_pitch": {"pass": pitch_pass, "f0_med": fc["f0_med"], "band": [lo, hi],
                        "rms_db": fc["rms_db"], "dur": fc["dur"]},
        "gate6_head_grunt": hg,
        "gate7_cut_word": cw,
        "gate8_head_bleed": hb,
        "gate9_tail_grunt": tg,
    }
    return report


if __name__ == "__main__":
    # python3 gates.py <audio> <lang> <text>
    rep = run_all_gates(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    sys.exit(0 if rep["pass"] else 1)
