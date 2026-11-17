#!/usr/bin/env python3
"""Tests for the gate-2 loanword-aware recalibration (2026-11-16).

The recalibration (settings flag gates.gate2_loanword_aware, default
OFF) lets gate 2 attribute an ASR token to an attested English loanword
that is actually present in THIS sentence's Telugu script, instead of
calling the channel's own code-mixing foreign bleed. It must stay
strictly subtractive and must NOT whitewash real bleed.

Tier 1 (always runs, no ASR): synthetic detections.
  - flag OFF reproduces the locked behaviour on every case;
  - 'safe' clears only when the script carries సేఫ్; 'safer' is NOT
    excused by సేఫ్టీ (exact-form discipline — the 2026-11-14
    'feel safer' bleed class);
  - 'fees' fails without ఫీజు in the script (turbo sentence 47
    pattern) and clears with it (regular plural of 'fee');
  - 'theory' clears via the dual-form English match (the natspan1
    genuine-narration ghost: థియరీ 'tiyari' vs 'teory', sim 0.44);
  - an Arabic-script rendering (phon 'kriminl') of క్రిమినల్ clears
    when the script carries the loanword inside a long compound (the
    configuration the real pool flags came from), and the consonant-
    skeleton channel inside _en_match is unit-probed directly;
  - 'money' never clears: not against a script with no loanword, and
    not against మోడల (model) either — 'money' vs 'model' sim 0.60 is
    below EN_MATCH_BAR, and the native word మొదలవుతుంది (begins) must
    not attribute 'model' at all (vowel-length discipline);
  - Hindi and English scans are byte-identical with the flag on/off.

Tier 2 (opt-in, JULIE_RUN_ASR_TESTS=1; loads faster-whisper, slow):
the fixed13-way controls on real audio — her genuine narration spans
(natspan1/2/3) and the ear-approved fixed13 takes pass gate 2 under
the new scan; a pure-English take gated as Telugu still fails.

Run: python3 test_gate2_loanword.py   (exit 0 = all pass)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gates  # noqa: E402

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        FAIL.append(name)


def det(text, toks):
    return {"lang": "te", "prob": 0.99, "text": text,
            "words": [{"tok": t, "prob": 0.95} for t in toks]}


def scans(script, d):
    words = [w for w in script.split() if w]
    off = gates.load_settings()
    on = gates.load_settings()
    on["gates"]["gate2_loanword_aware"] = True
    return (gates.ghost_scan(d, "te", words, off),
            gates.ghost_scan(d, "te", words, on))


def has(ghosts, needle):
    # part (a) ghost entries preserve the ASR token's case ("Safe");
    # part (b) entries embed it in a "tok :: why" string. Match loosely.
    return any(needle.lower() in g.lower() for g in ghosts)


# --- 1. 'safe' attributable to the script's own సేఫ్ -------------------
off, on = scans("ఇది సేఫ్ కాదు", det("Safe", ["Safe"]))
check("safe: locked scan flags it", has(off, "safe"))
check("safe: new scan clears it (script carries సేఫ్)", on == [], str(on))

# --- 2. 'safer' is NOT excused by సేఫ్టీ -------------------------------
off, on = scans("ఇది సేఫ్టీ విషయం", det("safer", ["safer"]))
check("safer: locked scan flags it", has(off, "safer"))
check("safer: new scan STILL flags it (exact-form discipline)",
      has(on, "safer"))

# --- 3. 'fees' without ఫీజు in the script still fails ------------------
off, on = scans("కేసులు పెరిగాయి", det("fees", ["fees"]))
check("fees/no-loan: locked scan flags it", has(off, "fees"))
check("fees/no-loan: new scan STILL flags it", has(on, "fees"))

# --- 4. 'fees' with ఫీజు clears (plural of the attested 'fee') --------
off, on = scans("కాలేజీ ఫీజు ఎక్కువ", det("fees", ["fees"]))
check("fees/with-loan: locked scan flags it", has(off, "fees"))
check("fees/with-loan: new scan clears it", on == [], str(on))

# --- 5. 'theory' dual-form match (the genuine-narration ghost) --------
off, on = scans("థియరీ ప్రకారం", det("Theory.", ["Theory."]))
check("theory: locked scan flags it", len(off) >= 1)
check("theory: new scan clears it", on == [], str(on))

# --- 6. Arabic-script rendering of a script loanword -------------------
# The bare-token version of this case (det token 'krmnl' against a script
# carrying plain క్రిమినల్) is flagged by NEITHER scan: the token aligns
# cleanly to its script word (sim 0.77 >= 0.75) and never becomes a ghost
# candidate. The real pool flags happened when the loanword sat inside a
# long agglutinated compound, so its Telugu-form phon is far from the
# rendering's phon — the stored turbo ghost for this class reads
# "phon 'kriminl' matches no script word (best sim 0.40)". Reproduce
# that configuration: script word = criminal-compound (te_simple len 27,
# sim('kriminl', compound) = 0.41), det renders the loanword in Arabic
# script (any_simple -> 'kriminl'), exactly as unhinted whisper did.
_script6 = "క్రిమినల్‌కేసులవిషయంలోకూడా అందరూ మాట్లాడారు"
_det6 = det("کریمینل అందరూ మాట్లాడారు", ["کریمینل", "అందరూ", "మాట్లాడారు"])
_words6 = _script6.split()
off = gates.ghost_scan(_det6, "te", _words6, gates.load_settings())
_on_settings = gates.load_settings()
_on_settings["gates"]["gate2_loanword_aware"] = True
on = gates.ghost_scan(_det6, "te", _words6, _on_settings)
check("kriminl/compound: locked scan flags it", has(off, "kriminl"),
      str(off))
check("kriminl/compound: new scan clears it (English-form match)",
      on == [], str(on))
# The consonant-skeleton channel (iii) inside _en_match, unit-probed:
# 'cules' is a stored pool phon whose full-form sim to the attested
# lexeme 'closeup' is 0.33 (< EN_MATCH_BAR) while its consonant
# skeleton matches at 0.86 — only the skeleton channel can clear it.
check("skeleton channel: _en_match('cules', ['closeup']) >= 0.80 "
      "while raw sim < EN_MATCH_BAR",
      gates.sim("cules", "closeup") < gates.EN_MATCH_BAR
      and gates._en_match("cules", ["closeup"]) >= 0.80)

# --- 7. 'money' discipline ---------------------------------------------
off, on = scans("మీరు మొదలవుతుంది పని", det("money", ["money"]))
check("money/no-loan: new scan STILL flags it", has(on, "money"))
loans = gates._sentence_loans(["మొదలవుతుంది"], "te")
check("money/no-loan: మొదలవుతుంది attributes NO loanword", loans == {},
      str(loans))
off, on = scans("ఒక మోడల లాగా", det("money", ["money"]))
check("money/vs-model: new scan STILL flags it (0.60 < EN bar)",
      has(on, "money"))
off, on = scans("ఒక మోడల లాగా", det("model", ["model"]))
check("model/exact: new scan clears the true loanword rendering",
      not has(on, "model"))

# --- 8. hi / en unchanged by the flag ----------------------------------
for lang, script, d in (
    ("hi", "यह एक टेस्ट है", det("kuchh aur", ["kuchh", "aur"])),
    ("en", "Hello this is Julie", det("Hello this is Julie",
                                       ["Hello", "this", "is", "Julie"])),
):
    words = [w for w in script.split() if w]
    soff = gates.load_settings()
    son = gates.load_settings()
    son["gates"]["gate2_loanword_aware"] = True
    d2 = dict(d)
    d2["lang"] = lang
    a = gates.ghost_scan(d2, lang, words, soff)
    b = gates.ghost_scan(d2, lang, words, son)
    check(f"{lang}: flag on/off identical", a == b, f"{a} vs {b}")

# --- tier 2: real-audio controls (opt-in) -------------------------------
if os.environ.get("JULIE_RUN_ASR_TESTS") == "1":
    on = gates.load_settings()
    on["gates"]["gate2_loanword_aware"] = True
    refs = json.load(open(os.path.join(HERE, "voice", "refs", "refs.json"),
                          encoding="utf-8"))["refs"]

    def g2(path, text, lang="te"):
        d = gates.nohint_detect(path)
        words = [w for w in text.split() if w]
        return gates.ghost_scan(d, lang, words, on)

    for span in ("natspan1", "natspan2", "natspan3"):
        info = refs[span]
        p = os.path.join(HERE, info["wav"])
        gh = g2(p, info["text"])
        # natspan2 carries one known native-word ASR garble ('yenimiti')
        # that no loanword rule may clear; the bar is <= 1 there, 0 else.
        bar = 1 if span == "natspan2" else 0
        check(f"ASR genuine {span}: gate2 ghosts <= {bar}", len(gh) <= bar,
              str(gh))
    s1 = open(os.path.join(HERE, "jobs", "fixed13-s1.txt"),
              encoding="utf-8").read().strip()
    s2 = open(os.path.join(HERE, "jobs", "fixed13-s2.txt"),
              encoding="utf-8").read().strip()
    for name, text in (("s1", s1), ("s2", s2)):
        p = os.path.join(HERE, "voice", "samples",
                         f"telugu-approved-{name}-fixed13.mp3")
        gh = g2(p, text)
        check(f"ASR ear-approved {name}: gate2 clean", gh == [], str(gh))
    en = os.path.join(HERE, "voice", "samples", "english-approved.mp3")
    gh = g2(en, s1)
    check("ASR english-as-te: STILL fails gate 2 (>= 3 ghosts)",
          len(gh) >= 3, str(gh))
else:
    print("SKIP tier-2 ASR controls (set JULIE_RUN_ASR_TESTS=1 to run)")

print()
if FAIL:
    print(f"{len(FAIL)} FAILURES: {FAIL}")
    sys.exit(1)
print("ALL PASS")
