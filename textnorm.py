"""Spoken-form text normalization for Divi Turbo (te / hi / en).

Runs BEFORE the voice reads a sentence, so numbers, years, %, ₹,
decimals and short forms (BBC, NCRB) come out as words in the target
language instead of being guessed (or skipped) by the TTS model.

Deterministic, no model, no network. Every change is logged so the QC
report can show exactly what the voice was asked to say.
"""
import re

# ---------------------------------------------------------------- Telugu
TE_1_19 = ["సున్నా", "ఒకటి", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు",
           "ఎనిమిది", "తొమ్మిది", "పది", "పదకొండు", "పన్నెండు", "పదమూడు",
           "పద్నాలుగు", "పదిహేను", "పదహారు", "పదిహేడు", "పద్దెనిమిది",
           "పందొమ్మిది"]
TE_TENS = ["", "", "ఇరవై", "ముప్పై", "నలభై", "యాభై", "అరవై", "డెబ్బై",
           "ఎనభై", "తొంభై"]
# attributive forms used before a multiplier ("రెండు వేల", "మూడు లక్షల")
TE_HUNDREDS = {1: "వంద", 2: "రెండు వందల", 3: "మూడు వందల", 4: "నాలుగు వందల",
               5: "ఐదు వందల", 6: "ఆరు వందల", 7: "ఏడు వందల", 8: "ఎనిమిది వందల",
               9: "తొమ్మిది వందల"}


def _te_below100(n):
    if n < 20:
        return TE_1_19[n]
    t, u = divmod(n, 10)
    return TE_TENS[t] + ("" if u == 0 else " " + TE_1_19[u])


def _te_below1000(n, final=True):
    if n < 100:
        return _te_below100(n)
    h, r = divmod(n, 100)
    if r == 0:
        if h == 1:
            return "వంద"
        return TE_HUNDREDS[h][:-1] + "లు" if final else TE_HUNDREDS[h]
    head = "నూట" if h == 1 else TE_HUNDREDS[h]
    return head + " " + _te_below100(r)


def te_number(n):
    if n == 0:
        return TE_1_19[0]
    parts = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thou, n = divmod(n, 1000)
    if crore:
        parts.append("ఒక కోటి" if crore == 1 and (lakh or thou or n) == 0
                     else ("కోటి" if crore == 1 else te_number(crore) + " కోట్ల"))
    if lakh:
        parts.append("లక్ష" if lakh == 1 else _te_below100(lakh) + " లక్షల")
    if thou:
        parts.append("వెయ్యి" if thou == 1 and n == 0 else
                     ("వెయ్యి" if thou == 1 else _te_below100(thou) + " వేల"))
        if thou > 1 and n == 0:
            parts[-1] = _te_below100(thou) + " వేలు"
    if n:
        parts.append(_te_below1000(n))
    return " ".join(parts)


# ----------------------------------------------------------------- Hindi
HI_1_99 = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह "
           "पंद्रह सोलह सत्रह अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस "
           "छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस "
           "छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस "
           "पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन "
           "चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ "
           "पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर "
           "चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी "
           "बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे "
           "इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे "
           "निन्यानवे").split()
assert len(HI_1_99) == 100


def hi_number(n):
    if n < 100:
        return HI_1_99[n]
    parts = []
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thou, n = divmod(n, 1000)
    hund, n = divmod(n, 100)
    if crore:
        parts.append(hi_number(crore) + " करोड़")
    if lakh:
        parts.append(HI_1_99[lakh] + " लाख")
    if thou:
        parts.append(HI_1_99[thou] + " हज़ार")
    if hund:
        parts.append(HI_1_99[hund] + " सौ")
    if n:
        parts.append(HI_1_99[n])
    return " ".join(parts)


# --------------------------------------------------------------- English
EN_1_19 = ("zero one two three four five six seven eight nine ten eleven "
           "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
           "nineteen").split()
EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
           "eighty", "ninety"]


def _en_below1000(n):
    out = []
    h, r = divmod(n, 100)
    if h:
        out.append(EN_1_19[h] + " hundred")
    if r:
        if r < 20:
            out.append(EN_1_19[r])
        else:
            t, u = divmod(r, 10)
            out.append(EN_TENS[t] + ("" if not u else "-" + EN_1_19[u]))
    return " ".join(out)


def en_number(n, year_ok=True):
    if n == 0:
        return "zero"
    if year_ok and 1100 <= n <= 2099 and n % 100 != 0 and not (2000 <= n <= 2009):
        return _en_below1000(n // 100) + " " + (
            "oh " + EN_1_19[n % 100] if n % 100 < 10 else _en_below1000(n % 100))
    out = []
    for div, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        q, n = divmod(n, div)
        if q:
            out.append(_en_below1000(q) + " " + name)
    if n:
        out.append(_en_below1000(n))
    return " ".join(out)


NUM = {"te": te_number, "hi": hi_number, "en": en_number}
DIGIT = {"te": TE_1_19[:10], "hi": HI_1_99[:10], "en": EN_1_19[:10]}
POINT = {"te": "పాయింట్", "hi": "दशमलव", "en": "point"}
PERCENT = {"te": "శాతం", "hi": "प्रतिशत", "en": "percent"}
RUPEES = {"te": "రూపాయలు", "hi": "रुपये", "en": "rupees"}
DOLLARS = {"te": "డాలర్లు", "hi": "डॉलर", "en": "dollars"}

# letter names for spelling short forms (BBC -> బీ బీ సీ)
LETTERS = {
    "te": dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   "ఏ బీ సీ డీ ఈ ఎఫ్ జీ హెచ్ ఐ జే కే ఎల్ ఎం ఎన్ ఓ పీ క్యూ ఆర్ ఎస్ టీ యూ వీ డబ్ల్యూ ఎక్స్ వై జెడ్".split())),
    "hi": dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                   "ए बी सी डी ई एफ़ जी एच आई जे के एल एम एन ओ पी क्यू आर एस टी यू वी डब्ल्यू एक्स वाई ज़ेड".split())),
}
# short forms said as words, not letters
SAY_AS_WORD = {"NASA", "UNESCO", "UNICEF", "NATO", "AIDS", "COVID", "ISRO",
               "OPEC", "SEBI", "NITI"}


def _attr(words, lang):
    """Telugu attributive before a unit: ఐదు వందలు రూపాయలు -> ఐదు వందల రూపాయలు."""
    return re.sub(r"(వంద|వే)లు$", r"\1ల", words) if lang == "te" else words


def _num_words(s, lang):
    s = s.replace(",", "")
    if "." in s:
        a, b = s.split(".", 1)
        return (NUM[lang](int(a or 0)) + " " + POINT[lang] + " " +
                " ".join(DIGIT[lang][int(d)] for d in b if d.isdigit()))
    return NUM[lang](int(s))


_NUM_RE = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"


def normalize(text, lang, log=None):
    """Return text with numbers / symbols / short forms in spoken words."""
    log = log if log is not None else []
    orig = text

    def sub(pattern, fn, t):
        return re.sub(pattern, fn, t)

    # currency first (₹500 / Rs. 500 / $20)
    text = sub(r"(?:₹|Rs\.?\s?|INR\s?)(" + _NUM_RE + ")",
               lambda m: _attr(_num_words(m.group(1), lang), lang) + " " + RUPEES[lang], text)
    text = sub(r"\$(" + _NUM_RE + ")",
               lambda m: _attr(_num_words(m.group(1), lang), lang) + " " + DOLLARS[lang], text)
    # percent
    text = sub(r"(" + _NUM_RE + r")\s?%",
               lambda m: _num_words(m.group(1), lang) + " " + PERCENT[lang], text)
    # remaining numbers
    text = sub(_NUM_RE, lambda m: _num_words(m.group(0), lang), text)
    # short forms (only te/hi need letter names in native script; English
    # TTS reads capitals as letters when spaced)
    def abbr(m):
        w = m.group(0)
        if w in SAY_AS_WORD:
            return w.capitalize() if lang == "en" else w
        if lang == "en":
            return " ".join(w)
        return " ".join(LETTERS[lang][c] for c in w)
    text = sub(r"\b[A-Z]{2,6}\b", abbr, text)
    text = re.sub(r"[*_#`~|<>\[\]{}]", " ", text)   # markdown/emoji-ish junk
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text != orig:
        log.append({"original": orig, "spoken": text})
    return text


if __name__ == "__main__":
    for lang, s in [("te", "జూలై 2024 లో 128.6 కేసులు, 45% పెరిగాయి. BBC రిపోర్ట్ ₹500."),
                    ("hi", "जुलाई 2024 में 128.6 केस, 45% बढ़े। BBC रिपोर्ट ₹1,50,000."),
                    ("en", "In July 2024, cases rose 45% to 128.6 per lakh, says the BBC, costing ₹500.")]:
        print(lang, "->", normalize(s, lang))
