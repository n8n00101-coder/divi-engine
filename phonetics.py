"""Phonetic normalization shared by the gates.

Every script word and every ASR token is pushed through the SAME converter,
so systematic spelling conventions cancel out and what remains is a real
diction difference. Three script families are covered:

- Telugu script  -> Latin phonetics (te_phon)
- Devanagari     -> Latin phonetics (hi_phon)
- ASR output     -> whisper renders unhinted Indic speech in Arabic script,
  Latin script, or the native script depending on the take; asr_simple /
  any_simple normalize all of them onto the same simplified scale.
"""
import re

# ---------------------------------------------------------------- Telugu ---
VOW = {'అ': 'a', 'ఆ': 'aa', 'ఇ': 'i', 'ఈ': 'ii', 'ఉ': 'u', 'ఊ': 'uu', 'ఋ': 'ru',
       'ఎ': 'e', 'ఏ': 'ee', 'ఐ': 'ai', 'ఒ': 'o', 'ఓ': 'oo', 'ఔ': 'au'}
VSIGN = {'ా': 'aa', 'ి': 'i', 'ీ': 'ii', 'ు': 'u', 'ూ': 'uu', 'ృ': 'ru', 'ె': 'e',
         'ే': 'ee', 'ై': 'ai', 'ొ': 'o', 'ో': 'oo', 'ౌ': 'au'}
CONS = {'క': 'k', 'ఖ': 'kh', 'గ': 'g', 'ఘ': 'gh', 'ఙ': 'ng', 'చ': 'ch', 'ఛ': 'ch',
        'జ': 'j', 'ఝ': 'jh', 'ఞ': 'ny', 'ట': 'T', 'ఠ': 'Th', 'డ': 'D', 'ఢ': 'Dh',
        'ణ': 'N', 'త': 't', 'థ': 'th', 'ద': 'd', 'ధ': 'dh', 'న': 'n', 'ప': 'p',
        'ఫ': 'f', 'బ': 'b', 'భ': 'bh', 'మ': 'm', 'య': 'y', 'ర': 'r', 'ల': 'l',
        'వ': 'v', 'శ': 'sh', 'ష': 'Sh', 'స': 's', 'హ': 'h', 'ళ': 'L', 'ఱ': 'r'}
VIRAMA = '్'
ANUS = 'ం'
VIS = 'ః'


def te_phon(word):
    out = []
    i = 0
    s = word
    while i < len(s):
        c = s[i]
        if c in VOW:
            out.append(VOW[c]); i += 1
        elif c in CONS:
            base = CONS[c]
            nxt = s[i + 1] if i + 1 < len(s) else ''
            if nxt == VIRAMA:
                out.append(base); i += 2
            elif nxt in VSIGN:
                out.append(base + VSIGN[nxt]); i += 2
            elif nxt == ANUS:
                out.append(base + 'a'); i += 1  # anusvara handled below
            else:
                out.append(base + 'a'); i += 1
        elif c == ANUS:
            out.append('m'); i += 1
        elif c == VIS:
            out.append('h'); i += 1
        elif c in VSIGN:
            out.append(VSIGN[c]); i += 1
        elif c == VIRAMA:
            i += 1
        else:
            i += 1
    return ''.join(out)


# ------------------------------------------------------------ Devanagari ---
H_VOW = {'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ii', 'उ': 'u', 'ऊ': 'uu', 'ऋ': 'ru',
         'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'ऑ': 'o', 'ऍ': 'e', 'अं': 'am'}
H_VSIGN = {'ा': 'aa', 'ि': 'i', 'ी': 'ii', 'ु': 'u', 'ू': 'uu', 'ृ': 'ru', 'े': 'e',
           'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ॉ': 'o', 'ॆ': 'e'}
H_CONS = {'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng', 'च': 'ch', 'छ': 'ch',
          'ज': 'j', 'झ': 'jh', 'ञ': 'ny', 'ट': 'T', 'ठ': 'Th', 'ड': 'D', 'ढ': 'Dh',
          'ण': 'N', 'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n', 'प': 'p',
          'फ': 'f', 'ब': 'b', 'भ': 'bh', 'म': 'm', 'य': 'y', 'र': 'r', 'ल': 'l',
          'व': 'v', 'श': 'sh', 'ष': 'Sh', 'स': 's', 'ह': 'h', 'ळ': 'L'}
H_VIRAMA = '्'
H_ANUS = 'ं'
H_CHANDRA = 'ँ'
H_VIS = 'ः'
H_NUKTA = '़'


def hi_phon(word):
    out = []
    s = word
    n = len(s)

    def nxt_meaningful(i):
        j = i + 1
        while j < n and s[j] == H_NUKTA:
            j += 1
        return s[j] if j < n else ''

    i = 0
    while i < n:
        c = s[i]
        if c in H_VOW:
            out.append(H_VOW[c]); i += 1
        elif c in H_CONS:
            base = H_CONS[c]
            nx = nxt_meaningful(i)
            if nx == H_VIRAMA:
                out.append(base)
            elif nx in H_VSIGN:
                out.append(base + H_VSIGN[nx])
            else:
                out.append(base + 'a')
            i += 1
        elif c in H_VSIGN:
            out.append(H_VSIGN[c]); i += 1
        elif c == H_ANUS or c == H_CHANDRA:
            out.append('m'); i += 1
        elif c == H_VIS:
            out.append('h'); i += 1
        else:
            i += 1  # virama, nukta, digits, punctuation: skip
    return ''.join(out)


# ------------------------------------------------------- ASR Arabic script -
AR = {'ا': 'a', 'آ': 'aa', 'ب': 'b', 'پ': 'p', 'ت': 't', 'ٹ': 'T', 'ث': 's', 'ج': 'j',
      'چ': 'ch', 'ح': 'h', 'خ': 'kh', 'د': 'd', 'ڈ': 'D', 'ذ': 'z', 'ر': 'r', 'ڑ': 'R',
      'ز': 'z', 'ژ': 'zh', 'س': 's', 'ش': 'sh', 'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'z',
      'ع': '', 'غ': 'gh', 'ف': 'f', 'ق': 'k', 'ک': 'k', 'گ': 'g', 'ل': 'l', 'م': 'm',
      'ن': 'n', 'ں': 'n', 'و': 'u', 'ہ': 'h', 'ھ': 'h', 'ی': 'i', 'ے': 'e', 'ء': '',
      'ئ': 'i', 'ؤ': 'u', 'ة': 't', 'ى': 'a'}
for _cp, _v in {'\u064a': 'i', '\u06cc': 'i', '\u0643': 'k', '\u06a9': 'k',
                '\u0647': 'h', '\u06c1': 'h', '\u067e': 'p', '\u0679': 'T',
                '\u0688': 'D', '\u0691': 'R', '\u06af': 'g', '\u0686': 'ch',
                '\u0649': 'a', '\u0629': 't', '\u0626': 'i', '\u0624': 'u',
                '\u06d2': 'e', '\u06be': 'h', '\u0622': 'aa', '\u0627': 'a',
                '\u0670': 'a'}.items():
    AR[_cp] = _v

DIA = {'\u064b': 'an', '\u064c': 'un', '\u064d': 'in', '\u064e': 'a', '\u064f': 'u',
       '\u0650': 'i', '\u0652': '', '\u0651': '~'}


def ar_phon(tok):
    out = []
    for c in list(tok):
        if c in DIA:
            if DIA[c] == '~':  # shadda: geminate previous consonant
                if out:
                    out.append(out[-1][-1])
                continue
            out.append(DIA[c])
        elif c in AR:
            v = AR[c]
            if v:
                out.append(v)
    return ''.join(out)


# ------------------------------------------------------------- simplify ----
def simplify(p):
    p = p.lower()
    p = p.replace('aa', 'a').replace('ii', 'i').replace('uu', 'u').replace('ee', 'e').replace('oo', 'o')
    p = p.replace('kh', 'k').replace('gh', 'g').replace('jh', 'j').replace('bh', 'b').replace('dh', 'd')
    p = p.replace('th', 't').replace('Th', 't').replace('sh', 's').replace('Sh', 's').replace('ch', 'c')
    p = p.replace('T', 't').replace('D', 'd').replace('N', 'n').replace('L', 'l').replace('R', 'r')
    p = p.replace('f', 'p').replace('v', 'u').replace('z', 'j').replace('q', 'k')
    p = re.sub(r'(.)\1+', r'\1', p)  # collapse geminates
    p = p.replace('ng', 'n').replace('ny', 'n')
    p = p.replace('j', 'c').replace('ai', 'e')
    return p


def te_simple(word):
    return simplify(te_phon(word))


def hi_simple(tok):
    """Devanagari token -> simplified phonetics; other scripts via any_simple."""
    if any('\u0900' <= ch <= '\u097f' for ch in tok):
        return simplify(hi_phon(tok))
    return asr_simple(tok)


LAT = {'š': 's', 'ş': 's', 'ç': 'c', 'č': 'c', 'ğ': 'g', 'ı': 'i', 'ž': 'z', 'đ': 'd',
       'â': 'a', 'î': 'i', 'û': 'u', 'ê': 'e', 'ô': 'o', 'ä': 'a', 'ö': 'o', 'ü': 'u',
       'é': 'e', 'è': 'e', 'á': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n', 'ț': 't'}


def asr_simple(tok):
    """ASR token (Arabic-script phonetic OR Latin) -> simplified phonetics."""
    if any('\u0600' <= ch <= '\u06ff' for ch in tok):
        return simplify(ar_phon(tok))
    t = tok.lower()
    t = ''.join(LAT.get(ch, ch) for ch in t)
    t = re.sub(r'[^a-z]', '', t)
    return simplify(t)


def any_simple(tok):
    """Any token in any of the supported scripts -> simplified phonetics."""
    if any('\u0c00' <= ch <= '\u0c7f' for ch in tok):
        return te_simple(tok)
    if any('\u0900' <= ch <= '\u097f' for ch in tok):
        return hi_simple(tok)
    return asr_simple(tok)


def en_simple(tok):
    t = re.sub(r"[^a-z]", '', tok.lower())
    return simplify(t)


# ------------------------------------------------------------ syllables ----
def te_syllables(word):
    return max(1, len(re.findall(r"[aeiou]+", te_simple(word))))


_H_INDEP = set('अआइईउऊऋएऐओऔऑऍ')
_H_CONSSET = set(H_CONS.keys())


def hi_syllables(word):
    """Akshara count: independent vowels + consonant nuclei (a consonant
    counts unless a virama follows, i.e. it is cluster-internal)."""
    s = word
    n = len(s)
    cnt = 0
    for i, c in enumerate(s):
        if c in _H_INDEP:
            cnt += 1
        elif c in H_CONSSET:
            j = i + 1
            while j < n and s[j] == H_NUKTA:
                j += 1
            nx = s[j] if j < n else ''
            if nx != H_VIRAMA:
                cnt += 1
    return max(1, cnt)


def en_syllables(word):
    t = re.sub(r"[^a-z]", '', word.lower())
    if not t:
        return 1
    n = len(re.findall(r"[aeiouy]+", t))
    if t.endswith('e') and n > 1:
        n -= 1
    return max(1, n)


LANG_SIMPLE = {'en': en_simple, 'te': te_simple, 'hi': hi_simple}
LANG_SYLLABLES = {'en': en_syllables, 'te': te_syllables, 'hi': hi_syllables}
