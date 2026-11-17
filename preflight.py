"""Divi Engine — SCRIPT PRE-FLIGHT (owner's order, 2026-11-16 20:28
IST): heal the INPUT before any generation. A flawed script cannot
produce a clean voice-over, so the whole script is analysed and
auto-corrected first; the generation stages consume ONLY the
corrected script.

Deterministic-first: every correction below is a rule with a stated
reason — no model, no key, no network. (An LLM pass may assist later
where a key exists; the core never depends on one.) Nothing is ever
silently rewritten: every change is returned in the corrections log
(original -> corrected -> class -> reason), the corrected script is
saved beside the output as script.corrected.txt, and anything whose
fix could change MEANING is applied only at high confidence —
otherwise the word is left untouched and the item is FLAGGED at the
top of the QC report for the owner's eye.

Correction classes:
  format        markdown/emoji/stray characters stripped, whitespace
                normalised, spelled-out percent -> the % symbol
                (channel policy: % is ALWAYS the symbol), missing
                sentence terminators supplied. Digits stay digits —
                years are spoken from digits by convention.
  duplicate     an identical sentence/line appearing twice is kept
                once (a duplicated line in the script would voice
                the same sentence twice).
  typo          known misspellings (a curated map of forms that are
                never correct) are fixed outright. Beyond the map, a
                word is corrected only when it is absent from a FULL
                system dictionary with exactly ONE dictionary
                neighbour at edit distance 1 (2 for long words) —
                never against a small corpus lexicon, which would
                'correct' real words; two or more neighbours = the
                fix is ambiguous -> flagged, never guessed. Indic
                words are FLAG-ONLY: the channel corpus lexicon is
                too small to rewrite against safely (measured: it
                'corrected' the legitimate లేస్తుంది to చేస్తుంది),
                so a possible Indic typo is flagged, never touched.
  english_mix   (Telugu scripts) the english-mix policy
                (voice/english_mix_classes.json): banned English
                connectives are replaced by their standard Telugu
                equivalents; attested English label words stay;
                an unattested English content word with a clear
                Telugu equivalent is converted; banned function
                words / pronouns and unattested words without a
                clear equivalent are FLAGGED (register and meaning
                are the owner's call).
  purity        a word from a third language/script inside the
                script: corrected where a clear equivalent exists
                (e.g. a Devanagari connective inside Telugu ->
                Telugu), otherwise flagged.
  sentence_shape  a sentence too long for one breath/take is split
                ONLY at a natural clause boundary (comma/semicolon
                or a connective), both halves whole; a fragment
                without a terminator is joined to its neighbour.
                No boundary -> flagged, never chopped mid-clause.

Pre-flight never touches tempo or any locked recipe value — the
speed law (speedpolicy.py) is a separate, sealed concern.
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# One-breath caps (words per sentence) — a whole take must stay
# speakable in one breath; longer sentences split at clause bounds.
MAX_WORDS = {"en": 28, "te": 26, "hi": 26}
MIN_HALF = 5          # both halves of a split need at least this many
FRAGMENT_MAX = 2      # <= this many words + no terminator = fragment

# ---------------------------------------------------------------- lexicon --
_COMMON_EN = set("""
the of and a an in is are was were will would can could should may might
to for with by from at on as it its this that these those there here
what when where which who whom whose why how all any both each few more
most other some such no nor not only own same so than too very just
about above after again against below between into through during
before under around among within without across behind beyond plus
except until per via receive separate occurred definitely necessary
believe achieve piece field friend change people through thought
important different children question example while world life hand
part place case week company system program problem government number
night point water room mother area money story young fact month lot
right study book eye job word business issue side kind head house
service power hour game often there under story history parent self
board search quick quickly result strong voice video audio channel
percent million billion hundred thousand first second third study
studies research evidence effect result analysis review survey report
experiment finding prove proof link screen phone internet online
website click views platform subscribe comment scroll delete session
manual chapter step card stage list short body camera director cut
design angle face hero case build check close decide follow gap asset
after before bill car caveat concept english explain fridge build
""".split())

_EN_TO_TE = {
    "water": "నీరు", "food": "ఆహారం", "house": "ఇల్లు",
    "money": "డబ్బు", "time": "సమయం", "people": "ప్రజలు",
    "man": "మనిషి", "day": "రోజు", "night": "రాత్రి",
    "year": "సంవత్సరం", "world": "ప్రపంచం", "life": "జీవితం",
    "hand": "చేయి", "eye": "కన్ను", "book": "పుస్తకం",
    "school": "పాఠశాల", "village": "గ్రామం", "city": "నగరం",
    "work": "పని", "love": "ప్రేమ", "family": "కుటుంబం",
    "story": "కథ", "question": "ప్రశ్న", "answer": "సమాధానం",
    "truth": "నిజం", "power": "శక్తి", "mind": "మనసు",
    "heart": "గుండె", "rain": "వర్షం", "sun": "సూర్యుడు",
}
_TE_CONNECTIVES = {"and": "మరియు", "but": "కానీ",
                   "because": "ఎందుకంటే", "then": "తర్వాత",
                   "however": "అయితే", "so": "అందుకే"}
_HI_CONNECTIVES = {"and": "और", "but": "लेकिन",
                   "because": "क्योंकि", "then": "फिर",
                   "however": "हालांकि", "so": "इसलिए"}
# A Devanagari connective stranded inside a Telugu script has one
# clear Telugu equivalent (purity class).
_HI_TO_TE = {"और": "మరియు", "लेकिन": "కానీ",
             "क्योंकि": "ఎందుకంటే", "फिर": "తర్వాత"}
_SPELLED_CARDINALS = {"one", "two", "three", "four", "five", "six",
                      "seven", "eight", "nine", "ten"}
_ORDINAL_HEADS = {"part", "chapter", "step", "card", "stage"}

# Curated KNOWN misspellings -> correction. This map is the typo
# pass's always-on core: it fires only on forms that are never
# correct English, so a clean script can never be corrupted by it.
_KNOWN_TYPOS = {
    "recieve": "receive", "seperate": "separate",
    "definately": "definitely", "occured": "occurred",
    "teh": "the", "adress": "address", "enviroment": "environment",
    "goverment": "government", "independant": "independent",
    "neccessary": "necessary", "accomodate": "accommodate",
    "existance": "existence", "experiance": "experience",
    "finaly": "finally", "generaly": "generally",
    "immediatly": "immediately", "knowlege": "knowledge",
    "libary": "library", "noticable": "noticeable",
    "ocassionally": "occasionally", "posession": "possession",
    "preferance": "preference", "refering": "referring",
    "rember": "remember", "similiar": "similar",
    "sucess": "success", "tendancy": "tendency",
    "tommorow": "tomorrow", "transfered": "transferred",
    "truely": "truly", "wierd": "weird", "writen": "written",
    "accross": "across", "apparantly": "apparently",
    "begining": "beginning", "beleive": "believe",
    "calender": "calendar", "cemetary": "cemetery",
    "changable": "changeable", "collegue": "colleague",
    "comming": "coming", "commited": "committed",
    "concious": "conscious",
    "grammer": "grammar", "harrass": "harass",
    "independant": "independent", "liason": "liaison",
    "millenium": "millennium", "noticably": "noticeably",
    "occassion": "occasion", "pavillion": "pavilion",
    "publically": "publicly", "refered": "referred",
    "seige": "siege", "supercede": "supersede",
    "tommorrow": "tomorrow", "vaccum": "vacuum",
    "withing": "within", "writting": "writing",
}
_DICT_PATHS = ("/usr/share/dict/american-english",
               "/usr/share/dict/words",
               "/usr/share/hunspell/en_US.dic",
               "/usr/share/myspell/en_US.dic",
               "/usr/share/dict/british-english")


def _system_dictionary():
    """A real English wordlist when the machine has one (the
    unique-neighbour typo rule is only safe against a full
    dictionary — against a small corpus lexicon it 'corrects' real
    words, which pre-flight must never do)."""
    for path in _DICT_PATHS:
        try:
            words = set()
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    w = line.strip().split("/")[0].lower()
                    if w.isalpha() and len(w) > 1:
                        words.add(w)
            if len(words) > 10000:
                return words
        except OSError:
            continue
    return set()


_LEXICONS = None


def _repo_tokens(patterns, scripts):
    toks = set()
    import glob
    for pat in patterns:
        for path in glob.glob(os.path.join(HERE, pat)):
            try:
                text = open(path, encoding="utf-8").read()
            except OSError:
                continue
            for tok in _word_tokens(text):
                if _script_of(tok) in scripts:
                    toks.add(tok)
    return toks


def _mix_policy():
    """(attested English lexemes, banned sets) from the english-mix
    policy JSON vendored from the english-mix-policy branch."""
    path = os.path.join(HERE, "voice", "english_mix_classes.json")
    attested, banned = set(), {}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return attested, banned
    for cls in (data.get("classes") or {}).values():
        for entry in cls.get("words") or []:
            form = (entry.get("english") or "").split("(")[0]
            for part in form.split("/"):
                w = part.strip().lower()
                if w and all(ch.isalpha() or ch in "- " for ch in w):
                    for single in w.split():
                        attested.add(single)
                        attested.add(single + "s")
                        if single.endswith("y"):
                            attested.add(single[:-1] + "ies")
    for b in data.get("banned") or []:
        items = set()
        for it in b.get("items") or []:
            w = it.split("(")[0].strip().lower()
            if w and " " not in w and w.isalpha():
                items.add(w)
        banned[b.get("type")] = items
    return attested, banned


def _lexicons():
    global _LEXICONS
    if _LEXICONS is not None:
        return _LEXICONS
    latin = set(_COMMON_EN)
    latin |= _repo_tokens(["*.md", "docs/*.md", "jobs/*.txt",
                           "voice/*.md"], {"latin"})
    te = _repo_tokens(["jobs/fixed*.txt", "voice/refs/*.txt",
                       "voice/telugu-reference.txt"], {"telugu"})
    hi = _repo_tokens(["jobs/fixed14-lines-hi.txt"], {"devanagari"})
    attested, banned = _mix_policy()
    latin |= attested
    try:
        refs = json.load(open(os.path.join(
            HERE, "voice", "refs", "refs.json"), encoding="utf-8"))
        for ref in (refs.get("refs") or {}).values():
            for tok in _word_tokens(ref.get("text") or ""):
                if _script_of(tok) == "telugu":
                    te.add(tok)
    except (OSError, ValueError):
        pass
    _LEXICONS = {"latin": {w.lower() for w in latin if len(w) > 1},
                 "en_dict": _system_dictionary(),
                 "te": te, "hi": hi, "attested": attested,
                 "banned": banned}
    return _LEXICONS


# ---------------------------------------------------------------- helpers --
_WORD_RE = re.compile(
    r"[A-Za-z][A-Za-z'’\-]*"
    r"|[\u0C00-\u0C7F]+(?:[\u200C\u200D][\u0C00-\u0C7F]+)*"
    r"|[\u0900-\u097F]+(?:[\u200C\u200D][\u0900-\u097F]+)*"
    r"|[^\sA-Za-z\u0C00-\u0C7F\u0900-\u097F]+")


def _word_tokens(text):
    return [t for t in _WORD_RE.findall(text)
            if any(ch.isalpha() for ch in t)]


def _script_of(token):
    for ch in token:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "TELUGU" in name:
            return "telugu"
        if "DEVANAGARI" in name:
            return "devanagari"
        if "LATIN" in name:
            return "latin"
        return name.split()[0].lower()
    return "other"


def _dl(a, b, cap):
    """Damerau-Levenshtein distance with early exit above cap."""
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    prev2, prev = None, list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and j > 1 and a[i - 1] == b[j - 2] \
                    and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[lb]


def _unique_correction(word, lexicon):
    """(fix, n_candidates): fix only when EXACTLY ONE neighbour."""
    cap = 2 if len(word) >= 8 else 1
    cands = [w for w in lexicon
             if w and w[0] == word[0] and abs(len(w) - len(word)) <= cap
             and _dl(word, w, cap) <= cap]
    if len(cands) == 1:
        return cands[0], 1
    return None, len(cands)


def _split_sentences(text):
    parts = re.split(r"(?<=[.!?…।])\s+", text.replace("\n", " "))
    return [p.strip() for p in parts if p.strip()]


def _terminator(sentence):
    return sentence.rstrip()[-1:] in ".!?…।"


# ------------------------------------------------------------- token pass --
def _token_pass(sentence, lang, lex, where, corr, flags):
    """All word-level classes on ONE sentence; returns the new text."""
    banned = lex["banned"]

    def sub_word(m):
        tok = m.group(0)
        script = _script_of(tok)
        low = tok.lower()
        # --- purity: a word in a foreign script -------------------
        if lang == "te" and script == "devanagari":
            if tok in _HI_TO_TE:
                corr.append({"original": tok, "corrected": _HI_TO_TE[tok],
                             "class": "purity", "where": where,
                             "reason": "Hindi connective inside a Telugu "
                                       "script -> its Telugu equivalent"})
                return _HI_TO_TE[tok]
            flags.append({"word": tok, "class": "purity", "where": where,
                          "reason": "Hindi (Devanagari) word inside a "
                                    "Telugu script; no clear Telugu "
                                    "equivalent on file — left as-is"})
            return tok
        if lang == "hi" and script == "telugu":
            flags.append({"word": tok, "class": "purity", "where": where,
                          "reason": "Telugu word inside a Hindi script; "
                                    "no confident equivalent — left as-is"})
            return tok
        if script not in ("latin", "telugu", "devanagari"):
            flags.append({"word": tok, "class": "purity", "where": where,
                          "reason": f"word in a third script "
                                    f"({script}) — left as-is"})
            return tok
        if lang == "en" and script != "latin":
            flags.append({"word": tok, "class": "purity", "where": where,
                          "reason": "non-English word inside an English "
                                    "script — left as-is (may be a name)"})
            return tok
        # --- Latin tokens inside te / hi scripts -------------------
        if script == "latin" and lang in ("te", "hi"):
            conns = _TE_CONNECTIVES if lang == "te" else _HI_CONNECTIVES
            if low in conns:
                corr.append({"original": tok, "corrected": conns[low],
                             "class": "english_mix" if lang == "te"
                             else "purity", "where": where,
                             "reason": "banned English connective — the "
                                       "script language carries "
                                       "connectives (english-mix policy)"})
                return conns[low]
            if lang == "te":
                if low in banned.get("english_function_words", set()) \
                        or low in banned.get(
                            "english_pronouns_auxiliaries_tense", set()):
                    flags.append({"word": tok, "class": "english_mix",
                                  "where": where,
                                  "reason": "banned English function "
                                            "word / pronoun in a Telugu "
                                            "script (policy: 0 corpus "
                                            "attestations); rewriting it "
                                            "is a meaning/register call "
                                            "— left as-is"})
                    return tok
                if low in _SPELLED_CARDINALS:
                    prev = sentence[:m.start()].strip().split()
                    head = prev[-1].lower() if prev else ""
                    if head not in _ORDINAL_HEADS:
                        flags.append({"word": tok, "class": "english_mix",
                                      "where": where,
                                      "reason": "spelled-out English "
                                                "cardinal used for "
                                                "counting (policy: "
                                                "counting numbers are "
                                                "Telugu/digits) — left "
                                                "as-is"})
                    return tok
                if low in lex["attested"]:
                    return tok          # attested label: stays English
                if tok[0].isupper():
                    return tok          # proper noun: stays
                if low in _EN_TO_TE:
                    corr.append({"original": tok,
                                 "corrected": _EN_TO_TE[low],
                                 "class": "english_mix", "where": where,
                                 "reason": "English word outside the "
                                           "attested mix classes with a "
                                           "clear Telugu equivalent"})
                    return _EN_TO_TE[low]
                flags.append({"word": tok, "class": "english_mix",
                              "where": where,
                              "reason": "English word outside the "
                                        "attested mix classes; no clear "
                                        "Telugu equivalent on file — "
                                        "left as-is"})
                return tok
            return tok                  # hi: Latin code-mix is normal
        # --- typo pass ---------------------------------------------
        # Latin: the curated known-misspelling map always applies;
        # the unique-neighbour rule applies ONLY against a full
        # system dictionary (never against the small repo lexicon —
        # it would 'correct' real words the corpus happens to lack).
        if script == "latin":
            if low in _KNOWN_TYPOS:
                out = _KNOWN_TYPOS[low]
                if tok[0].isupper():
                    out = out.capitalize()
                corr.append({"original": tok, "corrected": out,
                             "class": "typo", "where": where,
                             "reason": "known misspelling (curated "
                                       "map); the script form is "
                                       "never correct English"})
                return out
            en_dict = lex.get("en_dict") or set()
            if en_dict and len(low) >= 4 and low not in en_dict \
                    and low not in lex["latin"]:
                fix, n = _unique_correction(low, en_dict)
                if fix is not None:
                    out = fix.capitalize() if tok[0].isupper() else fix
                    corr.append({"original": tok, "corrected": out,
                                 "class": "typo", "where": where,
                                 "reason": "absent from the system "
                                           "dictionary; exactly one "
                                           "dictionary neighbour at "
                                           "edit distance <= "
                                           f"{2 if len(low) >= 8 else 1}"})
                    return out
                if n >= 2:
                    flags.append({"word": tok, "class": "typo",
                                  "where": where,
                                  "reason": f"{n} plausible dictionary "
                                            "corrections — ambiguous, "
                                            "left as-is"})
            return tok
        # Indic scripts: FLAG-ONLY. The channel corpus lexicon is
        # far too small to correct against safely — measured on real
        # Telugu narration, a unique-neighbour rule 'corrected' the
        # legitimate లేస్తుంది to చేస్తుంది. Until a full Indic
        # dictionary exists on the machine, an unknown long word
        # with several near neighbours is flagged as a possible
        # typo and NEVER rewritten.
        lexset = {"telugu": lex["te"],
                  "devanagari": lex["hi"]}.get(script)
        if lexset and len(tok) >= 7 and tok not in lexset:
            cands = [w for w in lexset
                     if w and abs(len(w) - len(tok)) <= 1
                     and _dl(tok, w, 1) <= 1]
            if len(cands) >= 2:
                flags.append({"word": tok, "class": "typo",
                              "where": where,
                              "reason": f"possible typo: {len(cands)} "
                                        "near lexicon neighbours — "
                                        "Indic correction is flag-only "
                                        "(corpus lexicon too small to "
                                        "rewrite safely), left as-is"})
        return tok

    out = _WORD_RE.sub(
        lambda m: sub_word(m) if any(ch.isalpha() for ch in m.group(0))
        else m.group(0), sentence)
    # --- spelled-out percent -> the % symbol (all languages) -------
    def pct(m):
        corr.append({"original": m.group(0),
                     "corrected": m.group(1) + "%",
                     "class": "format", "where": where,
                     "reason": "channel policy: % is always the "
                               "symbol, never spelled out"})
        return m.group(1) + "%"
    out = re.sub(r"(\d+(?:\.\d+)?)\s*(?:percent|per\s+cent)\b",
                 pct, out, flags=re.IGNORECASE)
    out = re.sub(r"(\d+(?:\.\d+)?)\s*శాతం", pct, out)
    out = re.sub(r"(\d+(?:\.\d+)?)\s*प्रतिशत", pct, out)
    return out


# ------------------------------------------------------------ shape pass --
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:])\s+")
_CONNECTIVE_SPLIT = {
    "en": re.compile(r"\s+(?=(?:and|but|because|so)\s)"),
    "te": re.compile(r"\s+(?=(?:మరియు|కానీ|అయితే|అందుకే)\s)"),
    "hi": re.compile(r"\s+(?=(?:और|लेकिन|क्योंकि|फिर)\s)"),
}


def _shape_pass(sentences, lang, corr, flags):
    cap = MAX_WORDS[lang]
    out = []
    for si, s in enumerate(sentences):
        words = s.split()
        if len(words) <= cap:
            out.append(s)
            continue
        # Clause boundaries, best kind first (connective > ; : > ,),
        # then closest to the middle — never a bare list comma when
        # a real clause joint exists.
        bounds = []
        for m in _CONNECTIVE_SPLIT[lang].finditer(s):
            bounds.append((0, m.start()))
        for m in re.finditer(r"(?<=[;:])\s+", s):
            bounds.append((1, m.end()))
        for m in re.finditer(r"(?<=,)\s+", s):
            bounds.append((2, m.end()))
        def _dist(p):
            return abs(len(s[:p].split()) - len(words) // 2)
        # First pass per boundary kind, in text order: the earliest
        # joint that leaves BOTH halves within the cap (a later list
        # comma can be nearer the middle yet dangle a fragment).
        # Fallback: closest to the middle.
        ordered = []
        for rank in (0, 1, 2):
            group = [p for r, p in bounds if r == rank]
            ordered.extend(sorted(
                group,
                key=lambda p: (0 if len(s[p:].split()) <= cap else 1,
                               p)))
            ordered.extend(sorted(group, key=_dist))
        seen_p, uniq = set(), []
        for p in ordered:
            if p not in seen_p:
                seen_p.add(p)
                uniq.append(p)
        done = False
        for p in uniq:
            left = s[:p].strip().rstrip(",;:").strip()
            right = s[p:].strip()
            if len(left.split()) >= MIN_HALF \
                    and len(right.split()) >= MIN_HALF:
                if not _terminator(left):
                    left += "."
                if not _terminator(right):
                    right += "."
                corr.append({"original": s, "corrected": left + " ⏎ "
                             + right, "class": "sentence_shape",
                             "where": si + 1,
                             "reason": f"{len(words)} words exceeds the "
                                       f"one-breath cap ({cap}); split "
                                       "at a natural clause boundary"})
                out.extend([left, right])
                done = True
                break
        if not done:
            flags.append({"word": s[:60] + "…", "class": "sentence_shape",
                          "where": si + 1,
                          "reason": f"{len(words)} words exceeds the "
                                    f"one-breath cap ({cap}) and has "
                                    "no natural clause boundary — left "
                                    "whole, flagged for the owner"})
            out.append(s)
    # join fragments (no terminator, <= FRAGMENT_MAX words) forward
    joined = []
    for s in out:
        if joined and len(joined[-1].split()) <= FRAGMENT_MAX \
                and not _terminator(joined[-1]):
            corr.append({"original": joined[-1], "corrected": s,
                         "class": "sentence_shape", "where": None,
                         "reason": "fragment without a terminator "
                                   "joined to its neighbour sentence"})
            joined[-1] = joined[-1] + " " + s
        else:
            joined.append(s)
    return joined


# -------------------------------------------------------------- cleaning --
def _clean(text, corr):
    raw = unicodedata.normalize("NFC", text).replace("\r\n", "\n")
    lines = []
    for ln in raw.split("\n"):
        new = ln
        new = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", new)   # md links
        new = re.sub(r"(\*\*|__|\*|_|`{1,3})", "", new)     # md emphasis
        new = re.sub(r"^\s{0,3}#{1,6}\s*", "", new)          # md headings
        new = re.sub(r"^\s*>\s?", "", new)                   # md quotes
        # Strip emoji/control/format junk — but NEVER ZWNJ/ZWJ:
        # in Indic scripts they are orthography (కోచ్‌లో), not junk.
        new = "".join(ch for ch in new
                      if unicodedata.category(ch) not in ("So", "Cs")
                      and ch not in "​﻿")
        new = re.sub(r"[ \t]{2,}", " ", new).strip()
        if new != ln.strip() and ln.strip():
            corr.append({"original": ln.strip(), "corrected": new,
                         "class": "format", "where": None,
                         "reason": "markdown/emoji/stray characters "
                                   "or doubled whitespace stripped "
                                   "for TTS"})
        if new:
            lines.append(new)
    return "\n".join(lines)


# ------------------------------------------------------------------ API --
def preflight_text(text, lang):
    """Heal a whole script. Returns {"text", "corrections", "flags"}.
    The generation stages must consume ONLY the returned text."""
    lex = _lexicons()
    corr, flags = [], []
    cleaned = _clean(text, corr)
    sentences = _split_sentences(cleaned)
    # duplicate sentences: keep the first occurrence only
    seen, unique = set(), []
    for s in sentences:
        key = re.sub(r"\s+", " ", s.strip().lower())
        if key in seen:
            corr.append({"original": s, "corrected": "",
                         "class": "duplicate", "where": None,
                         "reason": "identical sentence appears twice "
                                   "in the script; kept once"})
            continue
        seen.add(key)
        unique.append(s)
    sentences = [_token_pass(s, lang, lex, i + 1, corr, flags)
                 for i, s in enumerate(unique)]
    sentences = _shape_pass(sentences, lang, corr, flags)
    fixed = []
    for s in sentences:
        if not _terminator(s):
            corr.append({"original": s, "corrected": s + ".",
                         "class": "format", "where": None,
                         "reason": "missing sentence terminator "
                                   "supplied (TTS phrasing needs the "
                                   "full stop)"})
            s += "."
        fixed.append(s)
    return {"text": " ".join(fixed), "corrections": corr,
            "flags": flags}


def preflight_lines(lines, lang):
    """Batch mode: heal a lines file (one sentence per line).
    Returns {"lines", "corrections", "flags"}; duplicates removed,
    over-long lines split at clause boundaries (indices renumber —
    the QC log says exactly what moved)."""
    lex = _lexicons()
    corr, flags = [], []
    seen, unique = set(), []
    for ln in lines:
        one = _clean(ln, corr)
        if not one:
            continue
        key = re.sub(r"\s+", " ", one.lower())
        if key in seen:
            corr.append({"original": ln, "corrected": "",
                         "class": "duplicate", "where": None,
                         "reason": "identical line appears twice in "
                                   "the lines file; kept once"})
            continue
        seen.add(key)
        unique.append(one)
    out = []
    for i, ln in enumerate(unique):
        sents = _split_sentences(ln) or [ln]
        sents = [_token_pass(s, lang, lex, i + 1, corr, flags)
                 for s in sents]
        sents = _shape_pass(sents, lang, corr, flags)
        for s in sents:
            if not _terminator(s):
                corr.append({"original": s, "corrected": s + ".",
                             "class": "format", "where": i + 1,
                             "reason": "missing sentence terminator "
                                       "supplied"})
                s += "."
            out.append(s)
    return {"lines": out, "corrections": corr, "flags": flags}
