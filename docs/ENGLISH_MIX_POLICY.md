# ENGLISH-MIX POLICY — @who_taught_us-telugu narration

**Ajju's order (2026-11-16 19:45 IST):** Telugu narration does NOT have to be
100% Telugu. English words are fine — but ONLY the types of words the channel
itself keeps in English, in the same places and the same way. This document is
that system, written as executable script-writing rules for the voice tool.
Machine-readable version: `english_mix_classes.json`.

## Corpus — exactly what this rests on

| Source | Kind | Words | English-origin tokens |
|---|---|---|---|
| Male Gaze Part 2 (video `20nHsFoqK3s`, 13:47) | YouTube auto-caption transcript of genuine channel narration, retrieved 2026-11-15 (`voice-lib/tripti/longform/telugu-part2-transcript.txt`) | 1,545 | 412 (26.7%) |
| The Silent Habit (~15.5 min) | The channel's **official voice-over script** (`tab-reels/silent-habit/Script_Telugu.txt`) | 2,081 | 357 (17.2%) |
| Narration excerpt (Silent Habit) | Genuine narration text (`voice-lib/wtu-telugu-voice/ref-voice-telugu.txt`) | 13 | 4 |
| **Total** | **2 distinct videos** | **3,639** | **773 tokens, 304 attested lexemes** |

Method: every English-origin token was extracted — Latin-script tokens by
regex; Telugu-script transliterations by attested stem matching (Telugu
agglutinates case suffixes, so stems are counted inside suffixed forms).
Every lexeme in the appendix has ≥1 real attestation, with counts per source
and example sentences (full data: `extraction.json`).

**Caveats, honestly:**
- **2 videos, not more.** Expansion was attempted on 2026-11-16 via the
  GitHub Actions clean-network route: the channel listing succeeded (the
  channel has exactly 3 long-form videos: Male Gaze Part 1 `2Qz5EGcsK6A`,
  Male Gaze Part 2, and one notebook/children story `i28FG-K1ZYE`), but
  per-video caption downloads were refused by YouTube's bot check on the
  runner, and the repo's audio-fetch workflow shows the same failures today.
  The wall was **not** evaded (no cookies/bypass). Re-run the fetch when it
  clears to widen the corpus; the class system below is unlikely to change —
  both videos, on different topics, show the same system.
- Part 2 counts rest on auto-captions (ASR spellings vary, e.g. స్టెప్ఫోర్ for
  "step four"). The Silent Habit **official script is the authority** for the
  script-writing convention.
- Our own dub scripts (e.g. the Diwali script) were **excluded** — they are
  not channel evidence. (Words like *decibel* / *ton* appear only there and
  are therefore NOT in this policy.)

## The system in one paragraph

Telugu carries the grammar, the argument and the emotion. English supplies
**labels**: the concept being named, the field's working terms, the research
vocabulary, the structure announcements, and the everyday loanwords modern
Telugu already speaks with. English never carries a clause: there are no
English function words, no English connectives (beyond a tiny closed set),
no English tense, and no whole English sentences inside the narration.
Measured density: roughly **1 in 5 words** is English-origin (17–27% by
video) — but they are almost all nouns and labels sitting inside Telugu
sentences.

## The rules

**R1 — Concept labels stay English.** When a concept is *named*, the English
term is used and then explained in Telugu — never replaced by a coined
Telugu equivalent. Attested class (72 tokens): objectification, theory,
psychologist, dopamine, system, habit, cue, trigger, loop, trap, addiction,
aggression, stress, crave, satisfaction, system, anxiety, depression…
Evidence: "సైకాలజిస్ట్లు ఈ చూపుని **ఆబ్జెక్టిఫికేషన్** అంటారు" (Part 2);
"సైకాలజిస్ట్స్ దీన్ని **objectification** అంటారు, అంటే ఒక మనిషిని …
వస్తువులా చూడటం" (Silent Habit).

**R2 — Research & evidence vocabulary stays English** (78 tokens): study
(×19), report (×11), research/researcher, review, survey, experiment,
effect, evidence, finding, result, prove/proof, link, analysis, scan.
Statistics attach to these words. Evidence: "2018 లో 50 **స్టడీస్
అనాలసిస్**"; "ఢిల్లీ **రీసెర్చర్స్** చూశారు"; "కోర్లేషన్ **ప్రూఫ్** కాదు".

**R3 — The topic's craft vocabulary stays English** (80 tokens). For film:
camera (×11), angle, close-up, slow motion, slow pan, tilt, shot, scene,
character, director, hero, heroine, industry, producer, actor, artist,
reveal, film guides. Generalised: whatever field a video is about, its
working terms are English; the explanation around them is Telugu.

**R4 — Commerce & product terms stay English** (41 tokens): ad, product,
marketing, marketing tool, marketing asset, rights, label, bill, ledger,
logic, item, car, washing machine, fridge, TV, AC, tyre, headlight, bonnet,
door, luxury. Evidence: "**కార్, వాషింగ్ మెషిన్, ఫ్రిడ్జ్, టీవీ** ఎలా
అమ్ముతారో ఆలోచించండి"; "ఈ లెక్క … **బిజినెస్ లాజిక్**, **ఎగజాక్ట్ బిల్**
కాదు".

**R5 — Tech & platform vocabulary stays English** (75 tokens): screen,
video, phone, internet, online, website, site, app, click, tab, thumbnail,
endless, views, reels, clips, platform, subscribe, comment, scroll, pop up,
delete, host, session, autopilot, manual. Evidence: "**ఎండ్‌లెస్ ట్యాబ్స్.
ఎండ్‌లెస్ థంబ్‌నెయిల్స్.**"; CTA: "**సబ్స్క్రైబ్** చేయండి", "**కామెంట్**
చేయండి".

**R6 — Established everyday loanwords are used as-is** (114 tokens — the
largest class): college, fee, safety, safe, road, bus, bus stop, travel,
job, office, city, university, student, lab, test, marks, doctor, room,
toilet, bed, walk, call, shower, workout, skill, time, committee, notice,
ban, association, high court, judge, case, criminal, police, team, special,
official, career, book, group, plastic, surgeon, patient, streak. Do NOT
substitute formal Telugu equivalents (విశ్వవిద్యాలయం-style) where the
channel says యూనివర్సిటీ. Evidence: "రోడ్డు **సేఫ్** గా ఉందని ఒక అమ్మాయి
తక్కువ **కాలేజీ**ని ఎందుకు ఎంచుకుంటుంది?"; "**బస్ స్టాప్**".

**R7 — Structure is announced in English** (95 tokens): chapter / step /
card / stage / part + **one, two, three…**, first, last, next, list, short
list. Evidence: "**చాప్టర్ వన్.** ఇది ఎలా మొదలైంది"; "**స్టెప్ టూ** మన
కళ్ళు ఫాలో అవుతాయి"; "**కార్డ్ త్రీ** ఫ్రెండ్స్ చప్పట్లు కొడతారు";
"**కారణం వన్** మార్కెటింగ్". Cardinal numbers for actual counting stay
Telugu — one/two/three occur ONLY in these ordinal slots.

**R8 — Numbers: Telugu words for counts, English for scale, % as a
symbol** (18 tokens): million, billion, number, point, rate, double, top,
average stay English. BUT counts are Telugu words (ఐదు, వంద, లక్ష, కోట్లు),
percentages are the **% symbol** after Telugu number words, and the word
"percent" is **never spelled out (0 attestations)**. Years are digits;
month names are English (June ×4, July, September, December — 7 tokens).
Evidence: "73% మంది"; "520 **మిలియన్ వ్యూస్**"; "**టాప్** 20% కాలేజ్";
"**జూన్** 2025 లో".

**R9 — English verb stems ride Telugu light verbs** (67 tokens). The stem
is English; the grammar is Telugu: follow అవుతుంది, check చేసుకుంటుంది,
decide అవుతాడు, cut చేసేశాయి, list చేసింది, report చేసింది, track
చేసింది, face చేశారు, surf చేయ్, replace చేయ్, build చేసుకున్నావ్,
design చేశారు, plan చేసుకోలేదు, open చేద్దాం, close చేసామని, kidnap
చేసిన, work అవుతుంది, match అయ్యింది, fire అవుతూనే ఉంటాయి. English
tense/auxiliaries are banned (see Banned).

**R10 — Stance adjectives: attested set only** (79 tokens): powerful,
normal, serious, clear, exact, simple, perfect, free, weak, solid, real,
practical, silent, strong, extreme, exciting, boring, focus, damage,
restless, energy, confidence, memory, mood, guilt, distress, values,
environment, respect, crime, warning, defence, investigation, unverified,
mafia, minor, adult, sex/sexual, love, choice, progress, consistency,
superpower, magnetic, charm, confidential. They sit inside Telugu adverb
frames: "**క్లియర్** గా చెప్పుకుందాం", "**పవర్ఫుల్** గా చూపిస్తుంది",
"**సీరియస్** క్రైమ్". A new evaluative adjective that is not in this set
defaults to Telugu.

**R11 — Body words: Telugu core, thin English loan layer** (18 tokens).
Specific body parts stay Telugu (కళ్ళు, చెయ్యి, నడుము, చాతి, పెదవులు,
కాళ్ళు, హిప్స్ is the exception). Only the attested general layer is
English: body (×11), face, skin, hips, body shame. Evidence: "ఆమె **బాడీ**
మీదే"; "**బాడీ షేమ్** ఎక్కువయింది" — beside "ఆమె నడుము", "ఆమె చాతి,
పెదవులు" in the same passage.

**R12 — Proper nouns keep their English identity** (17 Telugu-script
tokens + all Latin-script names in the official script): researchers and
public figures (Martha Nussbaum, Barbara Fredrickson, L. Monique Ward,
Samantha, Hitler), organisations and brands (World Bank, Oxfam, BBC,
T-Series, Bollywood, YouTube, Instagram), international places (America,
Cambridge, Berlin, London, Ohio). Never translated.

## Placement patterns (measured)

1. **Inside Telugu word order.** English nouns sit exactly where a Telugu
   noun would sit; the Telugu verb closes the clause. Nothing is fronted
   or reordered for an English word.
2. **Telugu suffixes attach directly** — case, plural, emphasis: brain**లో**,
   screen **మీద**, studies**లో**, ICD-11**లో**, habit **నుంచే**, colleges
   కాలేజీ**ని**, cases కేసు**లు**. No English prepositions or articles
   ever appear.
3. **Concept-label position:** at first naming, in the frame
   "…దీన్ని **X** అంటారు" or as the object of a Telugu verb; the Telugu
   explanation follows immediately.
4. **Structure markers are sentence-initial** ("చాప్టర్ వన్.", "స్టెప్
   టూ, …", "కార్డ్ త్రీ, …") or follow కారణం ("కారణం వన్, …").
5. **హానెస్ట్ నోట్ (honest note)** is a fixed segment-initial marker,
   always followed by a comma and a caveat (×5, all in Silent Habit; the
   Part 2 narration performs the same caveat move in plain Telugu —
   "నిజం చెప్పాలంటే…", "కానీ జాగ్రత్త…").
6. **సో (so)** is sentence-initial and rare (×3 in 3,639 words).
7. **Lists:** English items appear in comma lists read in one breath —
   products ("కార్, వాషింగ్ మెషిన్, ఫ్రిడ్జ్, టీవీ"), possessions
   ("నీ టైమ్, నీ ఎనర్జీ, నీ కాన్ఫిడెన్స్"), places ("కాలేజీ, బస్ స్టాప్,
   ఆమె వీధి").
8. **Same pace, same accent:** English words are pronounced in her
   Indian-English at the same speed as the Telugu flow — never slowed,
   never paused for (PRONUNCIATION-PROFILE standing order).

## Banned — what she NEVER says in English (negative evidence)

| Banned type | Evidence |
|---|---|
| Function words: the, a, an, of, in, on, to, for, with, by | 0 attestations in 3,639 words; Telugu suffixes do this work |
| Connectives: but, and, then, because, however | 0 attestations; కానీ / అందుకే / తర్వాత / మరి do all connective work. (సో is the closed-set exception, R-discourse) |
| Pronouns / auxiliaries / tense: I, you, we, is, are, was, will, have | 0 attestations in narration; the official script's Latin tokens are content words + proper names only |
| Whole English clauses inside narration | Absent from both videos (English titles/headers excepted) |
| The word "percent"; English cardinals for counting | 0 attestations; % symbol + Telugu number words used instead |
| Coined Telugu replacements for attested English labels | Never happens; she explains the English label in Telugu instead |
| English adjectives outside the attested stance set | Evaluative English is a closed set in the corpus |
| Any OTHER language mid-flow | Standing house rule (Ajju, 2026-11-15) |

Discourse markers are a **closed set**: సో, హానెస్ట్ నోట్, స్టెప్ బై
స్టెప్, plus రూల్ / గ్యాప్ as nouns. Nothing else discourse-level is
English.

## Script-writing convention (how the tool feeds the TTS)

From the official Silent Habit script — the ground truth:

1. **Default: Telugu transliteration.** Most English-origin words are
   written in Telugu script: పోర్న్, మైండ్‌కి, స్టడీ, రీసెర్చ్, స్క్రీన్,
   వీడియో, ఫోన్, హ్యాబిట్ (title), డోపమైన్ (chapter title), క్లిక్స్,
   ట్యాబ్స్, థంబ్‌నెయిల్స్.
2. **Latin script ONLY for:**
   - Proper names of people / organisations / brands: Kent Berridge,
     Valerie Voon, Wendy Wood, Paul Wright, Ashley Tokunaga, Joshua
     Grubbs, Maxwell Maltz, Phillippa Lally, Common Sense Media, World
     Health Organization, New York Times, Visa, Mastercard, University
     College London, Ohio, Berlin, Cambridge.
   - A small concept set the script itself keeps in Latin: **brain**
     (×10 incl. "Brain"), **subconscious** (×7), dopamine (×3), striatum,
     grey matter, tolerance, escalation, neuroplasticity, continuity
     hypothesis, abstinence violation effect, objectification, sexual
     script, arousal, urge/urges, habit (×11 Latin vs title transliteration
     — the one genuinely mixed word), ICD-11, Tele-MANAS.
   - Note the honest variance: *dopamine* and *habit* appear in BOTH
     scripts (Telugu in titles, Latin in body text). The tool's rule:
     body-text concept terms from the Latin set above → Latin; everything
     else English-origin → Telugu transliteration.
3. **Numbers as digits** for years and statistics (2023లో, 73%, 43%,
   ICD-11); counting numbers as Telugu words.
4. Telugu suffixes are written attached to the English word, whichever
   script it is in: brain**లో**, brain**కి**, ICD-11**లో**, striatum**లో**,
   habit **నుంచే**, స్క్రీన్ **మీద**.

## Hypothesis verdicts (tested, not assumed)

| Hypothesis | Verdict |
|---|---|
| Scientific/technical terms stay English | **Supported** — the largest label classes (R1, R3) |
| Psychology concepts stay English | **Supported** — R1 is built on them |
| Proper nouns stay English | **Supported** — R12 |
| Units & measurements stay English | **Partly** — million/billion/rate/top/average yes; the word "percent" NO (% symbol instead); decibel/ton NOT attested in genuine channel corpus (only in our own dub script — excluded) |
| Established everyday loanwords stay English | **Supported** — largest single class (R6, 114 tokens) |
| Discourse/connective words stay English | **NOT supported** beyond the tiny closed set (సో ×3, హానెస్ట్ నోట్, స్టెప్ బై స్టెప్). All real connective work is Telugu. This was the brief's weakest hypothesis — the data rules against it |

## Appendix — every attested lexeme

Full machine-readable data (counts per source + example sentences for every
lexeme): `english_mix_classes.json` / `extraction.json`. The table below is
generated from the same extraction — nothing in it is unattested.

| English | Telugu stem | Class | P2 | SH | Ref | Total | Example |
|---|---|---|---:|---:|---:|---:|---|
| study / studies | స్టడీ | research_evidence | 14 | 5 | 0 | 19 | 2009 అమెరికన్ స్టడీలో అమ్మాయి |
| video | వీడియో | tech_platforms | 3 | 12 | 0 | 15 | కారణం 3 వ్యూస్ ఊ అంటావా అఫీషియల్ తెలుగు వీడియో కి YouTube |
| part / partner | పార్ట | structure_ordinals | 9 | 5 | 0 | 14 | పార్ట్ వన్ ఒక ప్రశ్నతో ముగిసింది. |
| step | స్టెప | structure_ordinals | 6 | 6 | 0 | 12 | ఇప్పుడు ఈ చైన్ ని స్టెప్ బై |
| body | బాడీ | body_loans | 7 | 4 | 0 | 11 | ఎపిసోడ్ పార్ట్ట మన మీద ప్రభావం ఒక అమ్మాయిని బాడీలా చూస్తే ఒక మనిషిగా |
| camera | కెమెరా | film_media_craft | 11 | 0 | 0 | 11 | వైపులా చూడండి సేమ్ కెమెరా సేమ్ ఐదు మూవ్స్ ఒకటి లో యాంగిల్ ఈ యాంగిల్ మనిషిని |
| report | రిపోర్ట | research_evidence | 10 | 1 | 0 | 11 | 6 6 కి దాదాపు డబుల్ కానీ జాగ్రత్త ఈ నెంబర్స్ రిపోర్ట్ అయిన కేసులే |
| case | కేస | everyday_loans | 9 | 1 | 0 | 10 | అతని మీద దాదాపు 30 పాత కేసులు హిట్లర్ బుక్ ఇన్స్పిరేషన్ కూడా ఉందని పోలీసులు చెప్పారు. |
| stage | స్టేజ | structure_ordinals | 0 | 10 | 0 | 10 | స్టేజెస్. |
| chapter | చాప్టర | structure_ordinals | 0 | 9 | 0 | 9 | చాప్టర్ వన్. |
| link | లింక | research_evidence | 4 | 5 | 0 | 9 | రిజల్ట్ ఈ కంటెంట్ కి ఎక్కువ సెక్సెస్ నమ్మకాలకి ఆడవాళ్ళపై లైంగిక హింసని సహించడానికి లింక్ ఉంది. |
| screen | స్క్రీన | tech_platforms | 3 | 6 | 0 | 9 | సేమ్ షార్ట్ లిస్ట్ ఒకటి ప్రొడక్ట్ ఇంకొకరు మనిషి ఈ పాయింట్ స్క్రీన్ మీద పాటర్న్ ఏ |
| follow | ఫాలో | verb_stems | 7 | 1 | 0 | 8 | ప్రతి యడ్ ఒకే షార్ట్ లిస్ట్ ఫాలో అవుతుంది. |
| hero | హీరో | film_media_craft | 8 | 0 | 0 | 8 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| psychologist(s) | సైకాలజిస్ట | science_psych_concepts | 2 | 6 | 0 | 8 | ఆమెని ఎలా చూస్తాం సైకాలజిస్ట్లు ఈ చూపుని ఆబ్జెక్టిఫికేషన్ అంటారు. |
| committee | కమిటీ | everyday_loans | 7 | 0 | 0 | 7 | ఇప్పుడు కెమెరా ముందు ఆడవాళ్ళు ఇలాంటి పాటలో హీరోయిన్ డాన్స్ నిజంగా ఆమె ఛాయిస్నానా ఇప్పుడు కేరళ హేమ కమిటీ |
| one (ordinal slot) | (pattern) | structure_ordinals | 4 | 3 | 0 | 7 | పార్ట్ వన్ ఒక ప్రశ్నతో ముగిసింది. |
| research / researcher(s) | రీసెర్చ | research_evidence | 3 | 4 | 0 | 7 | ఢిల్లీ రీసెర్చర్స్ చూశారు చాలా మంది అమ్మాయిలు |
| safe | సేఫ | everyday_loans | 7 | 0 | 0 | 7 | రోడ్డు సేఫ్ గా ఉందని ఒక అమ్మాయి తక్కువ కాలేజీ ని ఎందుకు ఎంచుకుంటుంది? |
| scene | సీన | film_media_craft | 4 | 3 | 0 | 7 | ఈ సీన్స్ చూసి పెరిగే అమ్మాయిలకి ఏమవుతుంది? |
| system | సిస్టమ | science_psych_concepts | 0 | 7 | 0 | 7 | న్యూరోసైంటిస్ట్ Kent Berridge ఏం చూపించాడంటే, brainలో రెండు వేర్వేరు సిస్టమ్స్ ఉంటాయి. |
| time | టైమ | everyday_loans | 0 | 7 | 0 | 7 | రన్‌టైమ్ సుమారు 15. |
| city | సిటీ | everyday_loans | 3 | 3 | 0 | 6 | సెప్టెంబర్ 2026 ఢిల్లీ బెంగళూర్లో 4వేలకి పైగా ఆడవాళ్ళపై సర్వే ఈ చార్ట్ ని సిటీవీగా చదవండి. |
| college | కాలేజీ | everyday_loans | 5 | 1 | 0 | 6 | రోడ్డు సేఫ్ గా ఉందని ఒక అమ్మాయి తక్కువ కాలేజీ ని ఎందుకు ఎంచుకుంటుంది? |
| cue | క్యూ | science_psych_concepts | 0 | 6 | 0 | 6 | ఏదో క్యూరియాసిటీతో చేసిన రెండు మూడు క్లిక్స్, ఆ ఒక్క పర్ఫెక్ట్ వీడియో కోసం గంటల తరబడి వెతికే దాకా ఎలా వెళ్ళాయి |
| effect | ఎఫెక్ట | research_evidence | 3 | 3 | 0 | 6 | ఎఫెక్ట్ ఎంత 2018 |
| loop | లూప | science_psych_concepts | 2 | 4 | 0 | 6 | ఈ లూప్ ఫాలో అవ్వండి. |
| phone | ఫోన | tech_platforms | 0 | 6 | 0 | 6 | హైదరాబాద్‌లో ఉన్న ఫోన్ అయినా, Ohioలో ఉన్న ఫోన్ అయినా, ఓపెన్ చేసేది అవే వెబ్‌సైట్స్. |
| sex / sexual | (pattern) | stance_adjectives | 3 | 3 | 0 | 6 | రిజల్ట్ ఈ కంటెంట్ కి ఎక్కువ సెక్సెస్ నమ్మకాలకి ఆడవాళ్ళపై లైంగిక హింసని సహించడానికి లింక్ ఉంది. |
| three (ordinal slot) | (pattern) | structure_ordinals | 2 | 4 | 0 | 6 | కాలేజీ, బస్ స్టాప్ ఆమె వీధి కార్డ్ త్రీ ఫ్రెండ్స్ చప్పట్లు కొడతారు పాట వస్తుంది. |
| car | (pattern) | commerce_products | 5 | 0 | 0 | 5 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| first | ఫస్ట | structure_ordinals | 1 | 4 | 0 | 5 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| focus | ఫోకస | stance_adjectives | 2 | 3 | 0 | 5 | లుక్స్ మీద ఫోకస్ చేయమన్నారు. |
| four (ordinal slot) | (pattern) | structure_ordinals | 2 | 3 | 0 | 5 | స్టెప్ఫోర్ చాలా స్టడీస్ లో ఈ చూపుతో పాటు ఆడవాళ్ళ మీద హింసని ఎక్కువగా సహించడం కూడా కనిపిస్తుంది. |
| heroine | హీరోయిన | film_media_craft | 5 | 0 | 0 | 5 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| honest note (segment marker) | హానెస్ట్ నోట | discourse_markers | 0 | 5 | 0 | 5 | హానెస్ట్ నోట్, అది US సర్వే. |
| judge | జడ్జ | everyday_loans | 5 | 0 | 0 | 5 | కానీ ప్రాడక్ట్ లా చూస్తే ఆమెపై మన జడ్జ్మెంట్ మారుతుందా? |
| two (ordinal slot) | (pattern) | structure_ordinals | 2 | 3 | 0 | 5 | ఇప్పుడే చూసిన షార్ట్ లిస్ట్ లాగా స్టెప్ టూ మన కళ్ళు |
| America(n) | అమెరిక | proper_nouns | 3 | 1 | 0 | 4 | 2009 అమెరికన్ స్టడీలో అమ్మాయి |
| June | జూన | calendar | 4 | 0 | 0 | 4 | ఒప్పుకోవాలి లేదా ఏళ్ల కల వదులుకుని నో చెప్పాలి చాలా సెట్స్ లో జూనియర్ ఆర్టిస్టులకి టాయిలెట్ |
| ad | యాడ | commerce_products | 2 | 2 | 0 | 4 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| card | కార్డ | structure_ordinals | 4 | 0 | 0 | 4 | చేసే ఫార్ములా చూడండి కార్డ్ వన్ హీరో ఆమెని చూస్తాడు ఆమె తనదే అని డిసైడ్ అవుతాడు. |
| choice | ఛాయిస | stance_adjectives | 4 | 0 | 0 | 4 | ఇప్పుడు కెమెరా ముందు ఆడవాళ్ళు ఇలాంటి పాటలో హీరోయిన్ డాన్స్ నిజంగా ఆమె ఛాయిస్నానా ఇప్పుడు కేరళ హేమ కమిటీ |
| control | కంట్రోల | science_psych_concepts | 1 | 3 | 0 | 4 | 290 పేజీల రిపోర్ట్ ప్రకారం ఇండస్ట్రీని పవర్ఫుల్ మగవాళ్ళ మాఫియా కంట్రోల్ చేస్తోంది. |
| endless | ఎండ్‌లెస | tech_platforms | 0 | 2 | 2 | 4 | ఎండ్‌లెస్ ట్యాబ్స్. |
| face | ఫేస | body_loans | 3 | 1 | 0 | 4 | ఫంజిబిలిటీ ఆమె ఫేస్ |
| filter | ఫిల్టర | tech_platforms | 0 | 4 | 0 | 4 | స్టెప్ త్రీ, ఫిల్టర్. |
| industry | ఇండస్ట్రీ | film_media_craft | 4 | 0 | 0 | 4 | 290 పేజీల రిపోర్ట్ ప్రకారం ఇండస్ట్రీని పవర్ఫుల్ మగవాళ్ళ మాఫియా కంట్రోల్ చేస్తోంది. |
| list | లిస్ట | structure_ordinals | 3 | 1 | 0 | 4 | ప్రతి యడ్ ఒకే షార్ట్ లిస్ట్ ఫాలో అవుతుంది. |
| open | ఓపెన | verb_stems | 2 | 2 | 0 | 4 | రిపోర్ట్ ని సరిగ్గా ఓపెన్ చేద్దాం. |
| point | పాయింట | quantity_units | 2 | 2 | 0 | 4 | సేమ్ షార్ట్ లిస్ట్ ఒకటి ప్రొడక్ట్ ఇంకొకరు మనిషి ఈ పాయింట్ స్క్రీన్ మీద పాటర్న్ ఏ |
| producer | ప్రొడ్యూసర | film_media_craft | 4 | 0 | 0 | 4 | డబ్బుని ఫాలో అవుతామ అన్నాం కదా మరి కథకు అవసరం లేకపోయినా ప్రొడ్యూసర్లు ఈ పాటలు ఎందుకు పెడుతూనే ఉంటారు? |
| prove / proof | ప్రూవ | research_evidence | 3 | 1 | 0 | 4 | అని ప్రూవ్ కాలేదు. |
| release | రిలీజ | film_media_craft | 3 | 1 | 0 | 4 | 2024 లో రిపోర్ట్ రిలీజ్ చేయమని సమంత అడిగారు. |
| review | రివ్యూ | research_evidence | 2 | 2 | 0 | 4 | 2060 లో సైకాలజిస్ట్ ఎల్ మోనిక్ వార్డ్ 20 ఏళ్ల 135 స్టడీస్ రివ్యూ చేశారు. |
| rights | రైట్స | commerce_products | 4 | 0 | 0 | 4 | 2018 హ్యూమన్ రైట్స్ కమిషన్ తెలంగాణ ప్రభుత్వానికి నోటీసులు పంపింది. |
| site | సైట | tech_platforms | 0 | 4 | 0 | 4 | హైదరాబాద్‌లో ఉన్న ఫోన్ అయినా, Ohioలో ఉన్న ఫోన్ అయినా, ఓపెన్ చేసేది అవే వెబ్‌సైట్స్. |
| stress | స్ట్రెస | science_psych_concepts | 0 | 4 | 0 | 4 | తర్వాత స్ట్రెస్‌లో ఉన్నప్పుడు. |
| survey | సర్వే | research_evidence | 2 | 2 | 0 | 4 | సెప్టెంబర్ 2026 ఢిల్లీ బెంగళూర్లో 4వేలకి పైగా ఆడవాళ్ళపై సర్వే ఈ చార్ట్ ని సిటీవీగా చదవండి. |
| use | యూజ | verb_stems | 4 | 0 | 0 | 4 | కారణంట 2 మ్యూజిక్ రైట్స్ పుష్ప 2 మ్యూజిక్ రిజిక్ రైట్స్ కి టీ సిరీస్ 65 కోట్లు కట్టిందని బాలీవుడ్ హంగామా |
| views | వ్యూస | tech_platforms | 4 | 0 | 0 | 4 | కారణం 3 వ్యూస్ ఊ అంటావా అఫీషియల్ తెలుగు వీడియో కి YouTube |
| Samantha | సమంత | proper_nouns | 3 | 0 | 0 | 3 | 2024 లో రిపోర్ట్ రిలీజ్ చేయమని సమంత అడిగారు. |
| TV | టీవీ | commerce_products | 3 | 0 | 0 | 3 | కార్, వాషింగ్ మెషిన్, ఫ్రిడ్జ్, టీవీ ఎలా అమ్ముతారో ఆలోచించండి. |
| aggression | అగ్రెషన | science_psych_concepts | 0 | 3 | 0 | 3 | 2% సీన్స్‌లో ఫిజికల్ అగ్రెషన్ ఉంది, అంటే చెంపదెబ్బ కొట్టడం, గొంతు నొక్కడం లాంటివి. |
| audience | ఆడియన్స | film_media_craft | 3 | 0 | 0 | 3 | ఆడియన్స్ కి నేర్పే పాఠం [సంగీతం] వెంటపడితే వర్క్ అవుతుంది. |
| autopilot | ఆటోపైలట | tech_platforms | 0 | 3 | 0 | 3 | నీ subconscious మైండ్ ఆటోపైలట్ లాంటిది. |
| bore (in bore kottadam) | (pattern) | stance_adjectives | 0 | 3 | 0 | 3 | తర్వాత బోర్ కొట్టినప్పుడు. |
| break | బ్రేక | verb_stems | 0 | 3 | 0 | 3 | రెండు, ఒక్క విల్‌పవర్‌తో పని అవ్వదు, ఎందుకంటే నువ్వు ఆటోపైలట్‌తో మాన్యువల్ బ్రేక్ పెట్టి ఫైట్ చేస్తున్నావ్. |
| clear | క్లియర | stance_adjectives | 1 | 2 | 0 | 3 | సో ఈ కేసులు ఏం చూపిస్తాయో క్లియర్ గా చెప్పుకుందాం. |
| click | క్లిక | tech_platforms | 0 | 3 | 0 | 3 | ఏదో క్యూరియాసిటీతో చేసిన రెండు మూడు క్లిక్స్, ఆ ఒక్క పర్ఫెక్ట్ వీడియో కోసం గంటల తరబడి వెతికే దాకా ఎలా వెళ్ళాయి |
| curiosity | క్యూరియాసిటీ | science_psych_concepts | 0 | 3 | 0 | 3 | ఏదో క్యూరియాసిటీతో చేసిన రెండు మూడు క్లిక్స్, ఆ ఒక్క పర్ఫెక్ట్ వీడియో కోసం గంటల తరబడి వెతికే దాకా ఎలా వెళ్ళాయి |
| decide | డిసైడ | verb_stems | 1 | 2 | 0 | 3 | చేసే ఫార్ములా చూడండి కార్డ్ వన్ హీరో ఆమెని చూస్తాడు ఆమె తనదే అని డిసైడ్ అవుతాడు. |
| design | డిజైన | verb_stems | 0 | 3 | 0 | 3 | పోర్న్ నీకు ఏదో నేర్పించడానికి డిజైన్ చేయలేదు. |
| experiment | ఎక్స్పెరిమెంట | research_evidence | 3 | 0 | 0 | 3 | ఐదు స్లో మోషన్ 12 ఎక్స్పెరిమెంట్స్ లో ప్రొడక్ట్స్ లగ్జరీగా కనిపించాయి. |
| fight | ఫైట | verb_stems | 0 | 3 | 0 | 3 | రెండు, ఒక్క విల్‌పవర్‌తో పని అవ్వదు, ఎందుకంటే నువ్వు ఆటోపైలట్‌తో మాన్యువల్ బ్రేక్ పెట్టి ఫైట్ చేస్తున్నావ్. |
| film | ఫిలిం | film_media_craft | 3 | 0 | 0 | 3 | పొడుగ్గా పవర్ఫుల్ గా చూపిస్తుందని ఫిలిం గైడ్స్ చెప్తాయి. |
| finding | ఫైండింగ | research_evidence | 2 | 1 | 0 | 3 | మల్లం ఫైండింగ్ ఈ సీన్స్ |
| high court | హైకోర్ట | everyday_loans | 3 | 0 | 0 | 3 | 2016 లో మద్రాస్ హైకోర్ట్ జడ్జ్ రాశారు. |
| label | లేబుల | commerce_products | 2 | 1 | 0 | 3 | లేబుల్స్ కోట్ల రూపాయలు కడతాయి. |
| marketing | మార్కెటింగ | commerce_products | 3 | 0 | 0 | 3 | వన్ మార్కెటింగ్ ఈ పాటలు చాలాసార్లు రిలీజ్ కి ముందే సినిమాని ప్రమోట్ చేసే మార్కెటింగ్ టూల్ అని కంపోజర్స్ ప్రొడ్ |
| next | నెక్స్ట | structure_ordinals | 1 | 2 | 0 | 3 | నెక్స్ట్ టైం కెమెరా ఆమె నడుము మీదకు దిగి థియేటర్ విజిల్స్ వేసినప్పుడు మనం ఎందుకు విజిల్స్ వేస్తున్నాం మనం వేసి |
| number | నంబర | quantity_units | 1 | 2 | 0 | 3 | కానీ పార్ట్ వన్ లో స్టడీ చేసిన చూపు కూడా సేమ్ అఫీషియల్ నంబర్స్ 2024 లో ఇండియాలో |
| official | అఫీషియల | everyday_loans | 2 | 1 | 0 | 3 | కానీ పార్ట్ వన్ లో స్టడీ చేసిన చూపు కూడా సేమ్ అఫీషియల్ నంబర్స్ 2024 లో ఇండియాలో |
| plan | ప్లాన | verb_stems | 0 | 3 | 0 | 3 | నువ్వు ఇది ప్లాన్ చేసుకోలేదు. |
| police | పోలీస | everyday_loans | 3 | 0 | 0 | 3 | ఢిల్లీ దగ్గర ఒక అమ్మాయిని [సంగీతం] కిడ్నాప్ చేసిన వ్యక్తి దర్ సినిమాతో బాగా ఇన్స్పైర్ అయ్యాడని పోలీసులు చెప్పా |
| rate | రేట | quantity_units | 3 | 0 | 0 | 3 | లో 50 స్టడీస్ అనాలసిస్ నిజమే కానీ మోడరేట్ చాలా పెద్దది కాదు జీరో కాదు. |
| road | రోడ్డ | everyday_loans | 2 | 1 | 0 | 3 | రోడ్డు సేఫ్ గా ఉందని ఒక అమ్మాయి తక్కువ కాలేజీ ని ఎందుకు ఎంచుకుంటుంది? |
| room | రూమ | everyday_loans | 2 | 1 | 0 | 3 | లేవు బట్టలు మార్చుకునే రూమ్స్ లేవు. |
| safety | సేఫ్టీ | everyday_loans | 3 | 0 | 0 | 3 | సేఫ్టీ కోసం. |
| satisfy / satisfaction | (pattern) | science_psych_concepts | 0 | 3 | 0 | 3 | సాటిస్ఫై అయినట్టు అనిపించదు. |
| short list | షార్ట్ లిస్ట | structure_ordinals | 3 | 0 | 0 | 3 | ప్రతి యడ్ ఒకే షార్ట్ లిస్ట్ ఫాలో అవుతుంది. |
| silent | సైలెంట | stance_adjectives | 0 | 3 | 0 | 3 | ఇది ది సైలెంట్ హ్యాబిట్. |
| so (sentence opener) | సో  | discourse_markers | 2 | 1 | 0 | 3 | సో ఈ కేసులు ఏం చూపిస్తాయో క్లియర్ గా చెప్పుకుందాం. |
| student | స్టూడెంట | everyday_loans | 3 | 0 | 0 | 3 | స్టూడెంట్స్ స్విమ్ సూట్ కానీ స్వెటర్ గాని వేసుకున్నారు. |
| test | టెస్ట | everyday_loans | 3 | 0 | 0 | 3 | మనిషిని చూసే వస్తువుగా చూడడం ఒక సింపుల్ టెస్ట్ |
| toilet | టాయిలెట | everyday_loans | 3 | 0 | 0 | 3 | ఒప్పుకోవాలి లేదా ఏళ్ల కల వదులుకుని నో చెప్పాలి చాలా సెట్స్ లో జూనియర్ ఆర్టిస్టులకి టాయిలెట్ |
| top | టాప | quantity_units | 3 | 0 | 0 | 3 | కాలేజీ, బస్ స్టాప్ ఆమె వీధి కార్డ్ త్రీ ఫ్రెండ్స్ చప్పట్లు కొడతారు పాట వస్తుంది. |
| track | ట్రాక | verb_stems | 1 | 2 | 0 | 3 | 2025 హైదరాబాద్ స్టడీ కళ్ళని ట్రాక్ చేసింది. |
| trap | ట్రాప | science_psych_concepts | 0 | 3 | 0 | 3 | డోపమైన్ ట్రాప్. |
| trigger | ట్రిగ్గర | science_psych_concepts | 0 | 3 | 0 | 3 | మూడు, ఆ లూప్ రీవైర్ అయ్యేదాకా, అవే ట్రిగ్గర్స్ మళ్ళీ మళ్ళీ ఫైర్ అవుతూనే ఉంటాయి. |
| work (function) | వర్క | verb_stems | 2 | 1 | 0 | 3 | ఆడియన్స్ కి నేర్పే పాఠం [సంగీతం] వెంటపడితే వర్క్ అవుతుంది. |
| analysis | అనాలసిస్ | research_evidence | 2 | 0 | 0 | 2 | లో 50 స్టడీస్ అనాలసిస్ నిజమే కానీ మోడరేట్ చాలా పెద్దది కాదు జీరో కాదు. |
| angle | యాంగిల | film_media_craft | 2 | 0 | 0 | 2 | వైపులా చూడండి సేమ్ కెమెరా సేమ్ ఐదు మూవ్స్ ఒకటి లో యాంగిల్ ఈ యాంగిల్ మనిషిని |
| app | యాప | tech_platforms | 1 | 1 | 0 | 2 | నాలుగు [సంగీతం] సినిమాలకి ప్రవర్తనకి లింక్ చూపించే పెద్ద రీసెర్చ్ ఇండియాలో చాలా తక్కువ ఈ గ్యాప్ నిజం [సంగీతం]  |
| artist | ఆర్టిస్ట | film_media_craft | 2 | 0 | 0 | 2 | ఒప్పుకోవాలి లేదా ఏళ్ల కల వదులుకుని నో చెప్పాలి చాలా సెట్స్ లో జూనియర్ ఆర్టిస్టులకి టాయిలెట్ |
| ban | బ్యాన | everyday_loans | 2 | 0 | 0 | 2 | డోర్లు, కార్ సైడ్ బాడీ ఆమె నడుము హెడ్లైట్స్, బ్యానెట్ ఆమె చాతి పెదవులు |
| bed | బెడ | everyday_loans | 0 | 2 | 0 | 2 | ఒంటరిగా ఉండటం, బోర్ కొట్టడం, స్ట్రెస్, అర్ధరాత్రి, బెడ్ మీద చేతిలో ఫోన్. |
| book | బుక | everyday_loans | 1 | 1 | 0 | 2 | అతని మీద దాదాపు 30 పాత కేసులు హిట్లర్ బుక్ ఇన్స్పిరేషన్ కూడా ఉందని పోలీసులు చెప్పారు. |
| build | బిల్డ | verb_stems | 0 | 2 | 0 | 2 | 2009లో, University College Londonలో Phillippa Lally, కొత్త habits బిల్డ్ చేసుకుంటున్న 96 మందిని ఫాలో చేసింది. |
| business | బిజినెస | film_media_craft | 2 | 0 | 0 | 2 | ఎంటర్టైన్మెంటఆ బిజినెస్ ఈరోజు డబ్బు ఎటు వెళ్తుందో చూద్దాం. |
| character | క్యారెక్టర | film_media_craft | 2 | 0 | 0 | 2 | క్యారెక్టర్ ని రివీల్ చేసే పద్ధతి అని ఫిలిం గైడ్స్ చెప్తాయి. |
| check | చెక | verb_stems | 1 | 1 | 0 | 2 | కెమెరా లాగా మూడు తన బాడీని ఎప్పుడూ చెక్ చేసుకుంటుంది. |
| clip | క్లిప | tech_platforms | 1 | 1 | 0 | 2 | రెండు పాట క్లిప్స్ రీల్స్ గా మారుతుంది. |
| comment | కామెంట | tech_platforms | 1 | 1 | 0 | 2 | ఈ వీడియో హూ టాటస్ పార్ట్ట ఇక మీరు మర్చిపోలేని ఆ ఒక్క సీన్ ని కామెంట్ చేయండి. |
| consistency | కన్సిస్టెన్స | stance_adjectives | 0 | 2 | 0 | 2 | పని చేసేది కన్సిస్టెన్సీ. |
| count | కౌంట | verb_stems | 0 | 2 | 0 | 2 | డే కౌంట్స్ అందరికీ పని చేయవు. |
| criminal | క్రిమినల | everyday_loans | 2 | 0 | 0 | 2 | కేసులు ఎక్కువ అంటే రిపోర్టింగ్ ఎక్కువ కావచ్చు నేరాలు కాదు పైగా జూలై 2024 లో కొత్త క్రిమినల్ చట్టాలు వచ్చాయి. |
| director | డైరెక్టర | film_media_craft | 2 | 0 | 0 | 2 | డైరెక్టర్ మీద ఆరోపణ కాదు. |
| energy | ఎనర్జీ | stance_adjectives | 0 | 2 | 0 | 2 | ఒక్క వీడియో వల్ల కాదు, ఆ లూప్ నీ దగ్గర నుంచి ఏం తీసుకెళ్తుందో దాని వల్ల: నీ టైమ్, నీ ఎనర్జీ, నీ కాన్ఫిడెన్స్,  |
| enjoy | ఎంజాయ | verb_stems | 0 | 2 | 0 | 2 | ఒకటి లైకింగ్, అంటే ఏదైనా ఎంజాయ్ చేయడం. |
| evidence | ఎవిడెన్స | research_evidence | 1 | 1 | 0 | 2 | సెక్షువలైజ్డ్ వీడియో గేమ్స్ పై 2022 అనాలసిస్ ఎవిడెన్స్ వీక్ |
| extreme | (pattern) | stance_adjectives | 0 | 2 | 0 | 2 | ఇంకా ఎక్స్‌ట్రీమ్‌గా. |
| five (ordinal slot) | (pattern) | structure_ordinals | 0 | 2 | 0 | 2 | స్టేజ్ ఫైవ్, డ్యామేజ్. |
| fridge | ఫ్రిడ్జ | commerce_products | 2 | 0 | 0 | 2 | కార్, వాషింగ్ మెషిన్, ఫ్రిడ్జ్, టీవీ ఎలా అమ్ముతారో ఆలోచించండి. |
| guides (film guides) | గైడ్స | film_media_craft | 2 | 0 | 0 | 2 | పొడుగ్గా పవర్ఫుల్ గా చూపిస్తుందని ఫిలిం గైడ్స్ చెప్తాయి. |
| item | ఐటం | commerce_products | 2 | 0 | 0 | 2 | కంటే దాదాపు 18800 ఎక్కువ రోజు 40 నిమిషాలు ఎక్కువ ట్రావెల్ టాప్ ఐటం చూడండి ఇష్టం లేని గుచ్చి చూపులు |
| junior | జూనియర | film_media_craft | 2 | 0 | 0 | 2 | ఒప్పుకోవాలి లేదా ఏళ్ల కల వదులుకుని నో చెప్పాలి చాలా సెట్స్ లో జూనియర్ ఆర్టిస్టులకి టాయిలెట్ |
| lab | ల్యాబ | everyday_loans | 2 | 0 | 0 | 2 | నిజం చెప్పాలంటే ఈ స్టడీ ఒక చిన్న అమెరికన్ ల్యాబ్ స్టడీ. |
| last | లాస్ట | structure_ordinals | 0 | 2 | 0 | 2 | "ఇదే లాస్ట్ టైమ్" అని నీకు నువ్వే చెప్పుకుంటావ్. |
| lead | లీడ | verb_stems | 1 | 1 | 0 | 2 | జడ్జ్ లీడ్ చేశారు. |
| maths | మాథ్స | everyday_loans | 2 | 0 | 0 | 2 | తర్వాత మాథ్స్ టెస్ట్ రాశారు. |
| million | మిలియన | quantity_units | 1 | 1 | 0 | 2 | లో 520 మిలియన్ వ్యూస్ పైనే స్ట్రీట పాట ఆజ్కి రాత్వ బిలియన్ పైనే ఇండియా సినిమా ఆడియన్స్ లో ఎక్కువ శాతం మగవాళ్లే |
| minor | మైనర | stance_adjectives | 0 | 2 | 0 | 2 | డిసెంబర్ 2020లో, New York Times చేసిన ఒక ఇన్వెస్టిగేషన్ ఏం రిపోర్ట్ చేసిందంటే, ప్రపంచంలోనే అతిపెద్ద పోర్న్ సైట |
| normal | నార్మల | stance_adjectives | 2 | 0 | 0 | 2 | చెప్పగలం ఇండస్ట్రీ ఆడవాళ్ళని బాడీలుగా వెంటపడటాన్ని ప్రేమగా చూపిస్తూనే ఉంటే మనకేం నార్మల్ అనిపిస్తుందో మారుతుంద |
| objectification / objectify | ఆబ్జెక్టిఫి | science_psych_concepts | 2 | 0 | 0 | 2 | ఆమెని ఎలా చూస్తాం సైకాలజిస్ట్లు ఈ చూపుని ఆబ్జెక్టిఫికేషన్ అంటారు. |
| online | ఆన్‌లైన | tech_platforms | 0 | 2 | 0 | 2 | 13 నుంచి 17 ఏళ్ల వాళ్ళలో 73% మంది ఆన్‌లైన్‌లో పోర్న్ చూశారు. |
| pattern | ప్యాటర్న | science_psych_concepts | 0 | 2 | 0 | 2 | డ్రగ్స్ వాడేవాళ్ళకి వాళ్ళ డ్రగ్ కనిపించినప్పుడు ఎలా వెలుగుతుందో, దాదాపు అలాంటి ప్యాటర్న్‌లోనే. |
| perfect | పర్ఫెక్ట | stance_adjectives | 0 | 2 | 0 | 2 | ఏదో క్యూరియాసిటీతో చేసిన రెండు మూడు క్లిక్స్, ఆ ఒక్క పర్ఫెక్ట్ వీడియో కోసం గంటల తరబడి వెతికే దాకా ఎలా వెళ్ళాయి |
| powerful | పవర్ఫుల | stance_adjectives | 2 | 0 | 0 | 2 | పొడుగ్గా పవర్ఫుల్ గా చూపిస్తుందని ఫిలిం గైడ్స్ చెప్తాయి. |
| product | ప్రొడక్ట | commerce_products | 2 | 0 | 0 | 2 | ఐదు స్లో మోషన్ 12 ఎక్స్పెరిమెంట్స్ లో ప్రొడక్ట్స్ లగ్జరీగా కనిపించాయి. |
| repeat | రిపీట | verb_stems | 1 | 1 | 0 | 2 | ఈ సినిమాలో రిపీట్ |
| result | రిజల్ట | research_evidence | 2 | 0 | 0 | 2 | రిజల్ట్ ఆమె తక్కువ సమర్ధురాలిగా తక్కువ మనిషిగా కనిపించింది. |
| reward | రివార్డ | science_psych_concepts | 0 | 2 | 0 | 2 | వాళ్ళకి ఎక్స్‌ప్లిసిట్ క్లిప్స్ చూపించినప్పుడు, వాళ్ళ రివార్డ్ ఏరియాస్ వెలిగిపోయాయి. |
| rule | రూల | discourse_markers | 0 | 2 | 0 | 2 | ఎక్కడో దారిలో, అది ప్రతి habitకీ ఒక రూల్ అయిపోయింది. |
| serious | సీరియస | stance_adjectives | 0 | 2 | 0 | 2 | కానీ నీకు ఇది జరుగుతుంటే, సీరియస్‌గా తీసుకోవడం మంచిది, ఒక డాక్టర్ హెల్ప్ చేయగలరు. |
| sets (film sets) | సెట్స | film_media_craft | 2 | 0 | 0 | 2 | ఒప్పుకోవాలి లేదా ఏళ్ల కల వదులుకుని నో చెప్పాలి చాలా సెట్స్ లో జూనియర్ ఆర్టిస్టులకి టాయిలెట్ |
| shot | షాట | film_media_craft | 2 | 0 | 0 | 2 | హీరోయిన్ ఫస్ట్ షాట్ కార్ యాడ్ లాగే ఎందుకు ఉంటుంది? |
| sign | సైన | science_psych_concepts | 0 | 2 | 0 | 2 | అంటే ఆ habit చాలా లోతుకి వెళ్ళిపోయిందని సైన్. |
| swimsuit | స్విమ్ సూట | everyday_loans | 2 | 0 | 0 | 2 | స్టూడెంట్స్ స్విమ్ సూట్ కానీ స్వెటర్ గాని వేసుకున్నారు. |
| tab | ట్యాబ | tech_platforms | 0 | 1 | 1 | 2 | ఎండ్‌లెస్ ట్యాబ్స్. |
| theory | థియరీ | science_psych_concepts | 2 | 0 | 0 | 2 | 97 లో బార్బరా ఫ్రెడరిక్సన్ టామీ ఆన్ రాబర్ట్స్ పెట్టిన పేరు ఆబ్జెక్టిఫికేషన్ థియరీ ఎడమ నుంచి కుడికి చదవండి. |
| thumbnail | థంబ్‌నెయిల | tech_platforms | 0 | 1 | 1 | 2 | ఎండ్‌లెస్ థంబ్‌నెయిల్స్. |
| travel | ట్రావెల | everyday_loans | 2 | 0 | 0 | 2 | ట్రావెల్ లో వేదింపులు ఫేస్ చేశారు. |
| try | ట్రై | verb_stems | 0 | 2 | 0 | 2 | ఆపాలని ట్రై చేస్తావ్, కానీ ఆపలేవ్. |
| verbal | వెర్బల | science_psych_concepts | 0 | 2 | 0 | 2 | దాదాపు సగం సీన్స్‌లో వెర్బల్ అగ్రెషన్ ఉంది. |
| washing machine | వాషింగ్ మెషిన | commerce_products | 2 | 0 | 0 | 2 | కార్, వాషింగ్ మెషిన్, ఫ్రిడ్జ్, టీవీ ఎలా అమ్ముతారో ఆలోచించండి. |
| weak | వీక | stance_adjectives | 1 | 1 | 0 | 2 | సెక్షువలైజ్డ్ వీడియో గేమ్స్ పై 2022 అనాలసిస్ ఎవిడెన్స్ వీక్ |
| zero | జీరో | stance_adjectives | 2 | 0 | 0 | 2 | లో 50 స్టడీస్ అనాలసిస్ నిజమే కానీ మోడరేట్ చాలా పెద్దది కాదు జీరో కాదు. |
| AC | ఏసీ | commerce_products | 1 | 0 | 0 | 1 | సేమ్ కెమెరా సేమ్ పార్ట్స్ వాషింగ్ మెషిన్లు, ఫ్రిడ్జ్లు, టీవీలు, ఏసీలు సేమ్ ఐదు మూవ్స్ |
| BBC | బిబిసి | proper_nouns | 1 | 0 | 0 | 1 | బిబిసి రాసింది. |
| Barbara Fredrickson | బార్బరా ఫ్రెడరిక్సన | proper_nouns | 1 | 0 | 0 | 1 | 97 లో బార్బరా ఫ్రెడరిక్సన్ టామీ ఆన్ రాబర్ట్స్ పెట్టిన పేరు ఆబ్జెక్టిఫికేషన్ థియరీ ఎడమ నుంచి కుడికి చదవండి. |
| Bollywood | బాలీవుడ | proper_nouns | 1 | 0 | 0 | 1 | కారణంట 2 మ్యూజిక్ రైట్స్ పుష్ప 2 మ్యూజిక్ రిజిక్ రైట్స్ కి టీ సిరీస్ 65 కోట్లు కట్టిందని బాలీవుడ్ హంగామా |
| December | డిసెంబర | calendar | 0 | 1 | 0 | 1 | డిసెంబర్ 2020లో, New York Times చేసిన ఒక ఇన్వెస్టిగేషన్ ఏం రిపోర్ట్ చేసిందంటే, ప్రపంచంలోనే అతిపెద్ద పోర్న్ సైట |
| Hitler | హిట్లర | proper_nouns | 1 | 0 | 0 | 1 | అతని మీద దాదాపు 30 పాత కేసులు హిట్లర్ బుక్ ఇన్స్పిరేషన్ కూడా ఉందని పోలీసులు చెప్పారు. |
| July | జూలై | calendar | 1 | 0 | 0 | 1 | కేసులు ఎక్కువ అంటే రిపోర్టింగ్ ఎక్కువ కావచ్చు నేరాలు కాదు పైగా జూలై 2024 లో కొత్త క్రిమినల్ చట్టాలు వచ్చాయి. |
| L. Monique Ward | మోనిక్ వార్డ | proper_nouns | 1 | 0 | 0 | 1 | 2060 లో సైకాలజిస్ట్ ఎల్ మోనిక్ వార్డ్ 20 ఏళ్ల 135 స్టడీస్ రివ్యూ చేశారు. |
| Martha Nussbaum | మార్తా నస్బాం | proper_nouns | 1 | 0 | 0 | 1 | 1995 లో ఫిలాసఫర్ మార్తా నస్బాం మనిషిని వస్తువులా |
| Oxfam | ఆక్స్ఫామ | proper_nouns | 1 | 0 | 0 | 1 | ఆక్స్ఫామ్ ఇండియా ఐదు రాష్ట్రాల యువతని అడిగింది. |
| September | సెప్టెంబర | calendar | 1 | 0 | 0 | 1 | సెప్టెంబర్ 2026 ఢిల్లీ బెంగళూర్లో 4వేలకి పైగా ఆడవాళ్ళపై సర్వే ఈ చార్ట్ ని సిటీవీగా చదవండి. |
| T-Series | టీ సిరీస | proper_nouns | 1 | 0 | 0 | 1 | కారణంట 2 మ్యూజిక్ రైట్స్ పుష్ప 2 మ్యూజిక్ రిజిక్ రైట్స్ కి టీ సిరీస్ 65 కోట్లు కట్టిందని బాలీవుడ్ హంగామా |
| World Bank | వరల్డ్ బ్యాంక | proper_nouns | 1 | 0 | 0 | 1 | ఇప్పుడు మన మొదటి ప్రశ్న కాలేజీ వరల్డ్ బ్యాంక్ ఎకనామిస్ట్ ఢిల్లీ యూనివర్సిటీ స్టూడెంట్స్ ని స్టడీ చేశారు. |
| actor | యాక్టర | film_media_craft | 1 | 0 | 0 | 1 | సినిమా 2018 లో యాక్టర్ శ్రీరెడ్డి ఇండస్ట్రీలో లైంగిక దోపిడీకి వ్యతిరేకంగా హైదరాబాద్ ఫిలిం చాంబర్ బయట నిరసం చేశ |
| addiction | అడిక్షన | science_psych_concepts | 0 | 1 | 0 | 1 | హానెస్ట్ నోట్, దీన్ని అడిక్షన్ అనాలా వద్దా అని సైంటిస్ట్స్ ఇప్పటికీ ఆర్గ్యూ చేస్తూనే ఉన్నారు. |
| adult | అడల్ట | stance_adjectives | 0 | 1 | 0 | 1 | కొన్నేళ్ల పాటు, స్క్రీన్ మీద ఉన్న ఆ మనిషి ఒప్పుకున్నారో లేదో, అసలు అడల్ట్ అవునో కాదో కూడా తెలీకుండానే జనాలు చూ |
| anxiety | యంజైటీ | science_psych_concepts | 1 | 0 | 0 | 1 | థియరీ ఈ అలవాటుని సిగ్గు యంజైటీతో తర్వాత డిప్రెషన్ తిండి జబ్బులతో లింక్ చేస్తుంది. |
| asset | ఆసెట | commerce_products | 1 | 0 | 0 | 1 | 2025 లో ఇలాంటి మూడు పాటలు ఉన్న థమ్మా సినిమా డైరెక్టర్ ఈ పాటలు ఆడియన్స్ ని సినిమాలోకి తీసుకొచ్చే మార్కెటింగ్ ఆస |
| association | అసోసియేషన | everyday_loans | 1 | 0 | 0 | 1 | యక్టర్స్ అసోసియేషన్ |
| average | యావరేజ | quantity_units | 0 | 1 | 0 | 1 | ఫస్ట్ టైమ్ చూసే యావరేజ్ ఏజ్ ఎంతో తెలుసా? |
| bill | బిల్ల | commerce_products | 1 | 0 | 0 | 1 | కానీ ప్రతి బిల్లుకి రెండు వైపులు ఉంటాయి. |
| billion | బిలియన | quantity_units | 1 | 0 | 0 | 1 | లో 520 మిలియన్ వ్యూస్ పైనే స్ట్రీట పాట ఆజ్కి రాత్వ బిలియన్ పైనే ఇండియా సినిమా ఆడియన్స్ లో ఎక్కువ శాతం మగవాళ్లే |
| body shame | బాడీ షేమ | body_loans | 1 | 0 | 0 | 1 | స్విమ్ సూట్ లో ఉన్న అమ్మాయిలకి బాడీ షేమ్ ఎక్కువయింది. |
| bonnet | బ్యానెట | commerce_products | 1 | 0 | 0 | 1 | డోర్లు, కార్ సైడ్ బాడీ ఆమె నడుము హెడ్లైట్స్, బ్యానెట్ ఆమె చాతి పెదవులు |
| boring | బోరింగ | stance_adjectives | 0 | 1 | 0 | 1 | పాత కంటెంట్ బోరింగ్‌గా అనిపిస్తుంది. |
| bus | బస | everyday_loans | 1 | 0 | 0 | 1 | కాలేజీ, బస్ స్టాప్ ఆమె వీధి కార్డ్ త్రీ ఫ్రెండ్స్ చప్పట్లు కొడతారు పాట వస్తుంది. |
| call (phone call) | కాల్ | everyday_loans | 0 | 1 | 0 | 1 | ఒక వర్కౌట్, ఒక వాక్, ఫ్రెండ్‌తో ఒక కాల్, ఒక కోల్డ్ షవర్, నువ్వు నేర్చుకుంటున్న ఒక స్కిల్. |
| career | కెరియర | everyday_loans | 1 | 0 | 0 | 1 | మంది ఆడవాళ్ళకి హేమ రిపోర్ట్ చూపించినట్టు నో చెప్తే కెరియర్ పోవచ్చు. |
| charm | చార్మ | stance_adjectives | 0 | 1 | 0 | 1 | ఆన్‌లైన్ గ్రూప్స్ మెరిసిపోయే స్కిన్, మ్యాగ్నెటిక్ చార్మ్, భారీ ఎనర్జీ అని ప్రామిస్ చేస్తాయి. |
| chemical | కెమికల్ | science_psych_concepts | 0 | 1 | 0 | 1 | చాలా మంది దీన్ని ప్లెజర్ కెమికల్ అంటారు. |
| classification | క్లాసిఫికేషన | science_psych_concepts | 0 | 1 | 0 | 1 | World Health Organization ఇప్పుడు compulsive sexual behaviour disorderని తన అఫీషియల్ క్లాసిఫికేషన్ ICD-11లో లి |
| close | (pattern) | verb_stems | 1 | 0 | 0 | 1 | జూన్ 2025 లో 34 కేసులు క్లోజ్ చేసామని కేరళ హైకోర్టు కి చెప్పింది. |
| close-up | క్లోజఅప | film_media_craft | 1 | 0 | 0 | 1 | నాలుగు క్లోజఅప్స్ ఒక్కో పార్ట్ |
| composer | కంపోజర | film_media_craft | 1 | 0 | 0 | 1 | వన్ మార్కెటింగ్ ఈ పాటలు చాలాసార్లు రిలీజ్ కి ముందే సినిమాని ప్రమోట్ చేసే మార్కెటింగ్ టూల్ అని కంపోజర్స్ ప్రొడ్ |
| confidence | కాన్ఫిడెన్స | stance_adjectives | 0 | 1 | 0 | 1 | ఒక్క వీడియో వల్ల కాదు, ఆ లూప్ నీ దగ్గర నుంచి ఏం తీసుకెళ్తుందో దాని వల్ల: నీ టైమ్, నీ ఎనర్జీ, నీ కాన్ఫిడెన్స్,  |
| confidential | కాన్ఫిడెన్షియల | stance_adjectives | 0 | 1 | 0 | 1 | ఇండియాలో, Tele-MANAS 14416 లో ఫ్రీ, ఇంకా కాన్ఫిడెన్షియల్. |
| connect | కనెక్ట | verb_stems | 0 | 1 | 0 | 1 | ఒక్క వీడియో వల్ల కాదు, ఆ లూప్ నీ దగ్గర నుంచి ఏం తీసుకెళ్తుందో దాని వల్ల: నీ టైమ్, నీ ఎనర్జీ, నీ కాన్ఫిడెన్స్,  |
| copy | కాపీ | verb_stems | 1 | 0 | 0 | 1 | ఐదు తర్వాత సినిమా సేమ్ ఫార్ములా కాపీ లూప్ మళ్ళీ మొదలు. |
| correlation | కోర్లేషన | research_evidence | 1 | 0 | 0 | 1 | కోర్లేషన్ ప్రూఫ్ కాదు. |
| crave | క్రేవ | science_psych_concepts | 0 | 1 | 0 | 1 | ఇంకోటి వాంటింగ్, అంటే దాని కోసం తపించడం, క్రేవ్ చేయడం. |
| crime | క్రైమ | stance_adjectives | 0 | 1 | 0 | 1 | ఇండియాలో, మైనర్స్‌కి సంబంధించిన ఏదైనా సరే చాలా సీరియస్ క్రైమ్, ఇంకా "నాకు తెలీదు" అనేది డిఫెన్స్ కాదు. |
| cut | (pattern) | verb_stems | 0 | 1 | 0 | 1 | కొన్ని రోజుల్లోనే Visa, Mastercard దాన్ని కట్ చేసేశాయి. |
| damage | డ్యామేజ | stance_adjectives | 0 | 1 | 0 | 1 | స్టేజ్ ఫైవ్, డ్యామేజ్. |
| dance | డాన్స | film_media_craft | 1 | 0 | 0 | 1 | ఇప్పుడు కెమెరా ముందు ఆడవాళ్ళు ఇలాంటి పాటలో హీరోయిన్ డాన్స్ నిజంగా ఆమె ఛాయిస్నానా ఇప్పుడు కేరళ హేమ కమిటీ |
| defence | డిఫెన్స | stance_adjectives | 0 | 1 | 0 | 1 | ఇండియాలో, మైనర్స్‌కి సంబంధించిన ఏదైనా సరే చాలా సీరియస్ క్రైమ్, ఇంకా "నాకు తెలీదు" అనేది డిఫెన్స్ కాదు. |
| delete | డిలీట | tech_platforms | 0 | 1 | 0 | 1 | నిన్ను అక్కడికి తీసుకెళ్ళే యాప్స్ డిలీట్ చేయ్. |
| demand | డిమాండ | verb_stems | 1 | 0 | 0 | 1 | మగవాళ్ళు సెక్స్ కోసం ఓపెన్ గా డిమాండ్ చేస్తారు. |
| depression | డిప్రెషన్ | science_psych_concepts | 1 | 0 | 0 | 1 | థియరీ ఈ అలవాటుని సిగ్గు యంజైటీతో తర్వాత డిప్రెషన్ తిండి జబ్బులతో లింక్ చేస్తుంది. |
| distress | డిస్ట్రెస | stance_adjectives | 0 | 1 | 0 | 1 | సైకాలజిస్ట్ Joshua Grubbs ఏం కనిపెట్టాడంటే, తమ పోర్న్ వాడకం తమ వాల్యూస్‌కి వ్యతిరేకంగా ఉందని ఫీల్ అయ్యేవాళ్ళు, |
| doctor | డాక్టర | everyday_loans | 0 | 1 | 0 | 1 | కానీ నీకు ఇది జరుగుతుంటే, సీరియస్‌గా తీసుకోవడం మంచిది, ఒక డాక్టర్ హెల్ప్ చేయగలరు. |
| door | డోర | commerce_products | 1 | 0 | 0 | 1 | డోర్లు, కార్ సైడ్ బాడీ ఆమె నడుము హెడ్లైట్స్, బ్యానెట్ ఆమె చాతి పెదవులు |
| dopamine | డోపమైన్ | science_psych_concepts | 0 | 1 | 0 | 1 | డోపమైన్ ట్రాప్. |
| double | డబుల | quantity_units | 1 | 0 | 0 | 1 | 6 6 కి దాదాపు డబుల్ కానీ జాగ్రత్త ఈ నెంబర్స్ రిపోర్ట్ అయిన కేసులే |
| eight (ordinal slot) | (pattern) | structure_ordinals | 0 | 1 | 0 | 1 | చాప్టర్ ఎయిట్. |
| entertainment | ఎంటర్టైన్మెంట | film_media_craft | 1 | 0 | 0 | 1 | ఎంటర్టైన్మెంటఆ బిజినెస్ ఈరోజు డబ్బు ఎటు వెళ్తుందో చూద్దాం. |
| environment | ఎన్విరాన్‌మెంట | stance_adjectives | 0 | 1 | 0 | 1 | నీ ఎన్విరాన్‌మెంట్ మార్చు. |
| episode | ఎపిసోడ | film_media_craft | 1 | 0 | 0 | 1 | ఎపిసోడ్ పార్ట్ట మన మీద ప్రభావం ఒక అమ్మాయిని బాడీలా చూస్తే ఒక మనిషిగా |
| exact | ఎగజాక్ట | stance_adjectives | 1 | 0 | 0 | 1 | ఈ లెక్క ఇండస్ట్రీ వాళ్ళు చెప్పే బిజినెస్ లాజిక్ ఎగజాక్ట్ బిల్ కాదు. |
| exciting | ఎక్సైటింగ | stance_adjectives | 0 | 1 | 0 | 1 | ఏదైనా ఎక్సైటింగ్‌గా కనిపించినప్పుడు, నీ brain dopamine రిలీజ్ చేస్తుంది. |
| fee | ఫీజు | everyday_loans | 1 | 0 | 0 | 1 | తక్కువ కాలేజీ, ఎక్కువ ఫీజు, ఎక్కువ దూరం. |
| fire (trigger) | ఫైర | verb_stems | 0 | 1 | 0 | 1 | మూడు, ఆ లూప్ రీవైర్ అయ్యేదాకా, అవే ట్రిగ్గర్స్ మళ్ళీ మళ్ళీ ఫైర్ అవుతూనే ఉంటాయి. |
| free | ఫ్రీ | stance_adjectives | 0 | 1 | 0 | 1 | ఇండియాలో, Tele-MANAS 14416 లో ఫ్రీ, ఇంకా కాన్ఫిడెన్షియల్. |
| gap | గ్యాప | discourse_markers | 1 | 0 | 0 | 1 | నాలుగు [సంగీతం] సినిమాలకి ప్రవర్తనకి లింక్ చూపించే పెద్ద రీసెర్చ్ ఇండియాలో చాలా తక్కువ ఈ గ్యాప్ నిజం [సంగీతం]  |
| group | గ్రూప | everyday_loans | 0 | 1 | 0 | 1 | ఆన్‌లైన్ గ్రూప్స్ మెరిసిపోయే స్కిన్, మ్యాగ్నెటిక్ చార్మ్, భారీ ఎనర్జీ అని ప్రామిస్ చేస్తాయి. |
| guilt | గిల్ట | stance_adjectives | 0 | 1 | 0 | 1 | రహస్యం దాచడం, గిల్ట్, సిగ్గు. |
| habit | హ్యాబిట | science_psych_concepts | 0 | 1 | 0 | 1 | ఇది ది సైలెంట్ హ్యాబిట్. |
| headlight | హెడ్లైట | commerce_products | 1 | 0 | 0 | 1 | డోర్లు, కార్ సైడ్ బాడీ ఆమె నడుము హెడ్లైట్స్, బ్యానెట్ ఆమె చాతి పెదవులు |
| hips | హిప్స | body_loans | 1 | 0 | 0 | 1 | టైర్లు ఆమె కాళ్ళు కార్ వెనక భాగం ఆమె హిప్స్ |
| host | హోస్ట | tech_platforms | 0 | 1 | 0 | 1 | డిసెంబర్ 2020లో, New York Times చేసిన ఒక ఇన్వెస్టిగేషన్ ఏం రిపోర్ట్ చేసిందంటే, ప్రపంచంలోనే అతిపెద్ద పోర్న్ సైట |
| human rights (commission) | హ్యూమన్ రైట్స | proper_nouns | 1 | 0 | 0 | 1 | 2018 హ్యూమన్ రైట్స్ కమిషన్ తెలంగాణ ప్రభుత్వానికి నోటీసులు పంపింది. |
| inspire | ఇన్స్పైర | verb_stems | 1 | 0 | 0 | 1 | ఢిల్లీ దగ్గర ఒక అమ్మాయిని [సంగీతం] కిడ్నాప్ చేసిన వ్యక్తి దర్ సినిమాతో బాగా ఇన్స్పైర్ అయ్యాడని పోలీసులు చెప్పా |
| internet | ఇంటర్నెట | tech_platforms | 0 | 1 | 0 | 1 | కానీ ఇంటర్నెట్‌కి బార్డర్ ఉండదు. |
| investigation | ఇన్వెస్టిగేషన | stance_adjectives | 0 | 1 | 0 | 1 | డిసెంబర్ 2020లో, New York Times చేసిన ఒక ఇన్వెస్టిగేషన్ ఏం రిపోర్ట్ చేసిందంటే, ప్రపంచంలోనే అతిపెద్ద పోర్న్ సైట |
| job | జాబ | everyday_loans | 1 | 0 | 0 | 1 | బెంగళూరులో 14 రెండు సిటీల్లోనూ 10 మందిలో దాదాపు ఏడుగురు వేధింపుల భయం తమ జాబ్ నిర్ణయం మీద ప్రభావం చూపిస్తుందన్న |
| kick (thrill) | కిక | stance_adjectives | 0 | 1 | 0 | 1 | ప్రతిసారీ, అదే వీడియో కొంచెం తక్కువ కిక్ ఇస్తుంది. |
| kidnap | కిడ్నాప | verb_stems | 1 | 0 | 0 | 1 | ఢిల్లీ దగ్గర ఒక అమ్మాయిని [సంగీతం] కిడ్నాప్ చేసిన వ్యక్తి దర్ సినిమాతో బాగా ఇన్స్పైర్ అయ్యాడని పోలీసులు చెప్పా |
| ledger | లెడ్జర | commerce_products | 1 | 0 | 0 | 1 | సో లెడ్జర్ రెండు వైపులా చూద్దాం. |
| logic | లాజిక | commerce_products | 1 | 0 | 0 | 1 | ఈ లెక్క ఇండస్ట్రీ వాళ్ళు చెప్పే బిజినెస్ లాజిక్ ఎగజాక్ట్ బిల్ కాదు. |
| love | (pattern) | stance_adjectives | 0 | 1 | 0 | 1 | 12 ఏళ్లకి లవ్ అంటే ఏంటో నీకు తెలీదు. |
| luxury | లగ్జరీ | commerce_products | 1 | 0 | 0 | 1 | ఐదు స్లో మోషన్ 12 ఎక్స్పెరిమెంట్స్ లో ప్రొడక్ట్స్ లగ్జరీగా కనిపించాయి. |
| mafia | మాఫియా | stance_adjectives | 1 | 0 | 0 | 1 | 290 పేజీల రిపోర్ట్ ప్రకారం ఇండస్ట్రీని పవర్ఫుల్ మగవాళ్ళ మాఫియా కంట్రోల్ చేస్తోంది. |
| magnetic | మ్యాగ్నెటిక | stance_adjectives | 0 | 1 | 0 | 1 | ఆన్‌లైన్ గ్రూప్స్ మెరిసిపోయే స్కిన్, మ్యాగ్నెటిక్ చార్మ్, భారీ ఎనర్జీ అని ప్రామిస్ చేస్తాయి. |
| manual | మాన్యువల | tech_platforms | 0 | 1 | 0 | 1 | రెండు, ఒక్క విల్‌పవర్‌తో పని అవ్వదు, ఎందుకంటే నువ్వు ఆటోపైలట్‌తో మాన్యువల్ బ్రేక్ పెట్టి ఫైట్ చేస్తున్నావ్. |
| marks | మార్కుల | everyday_loans | 1 | 0 | 0 | 1 | లో మార్కులు తగ్గాయి. |
| match | మ్యాచ | verb_stems | 0 | 1 | 0 | 1 | కానీ చాలా మంది తమ ఎక్స్‌పీరియన్స్ గురించి చెప్పేదానితో ఇది మ్యాచ్ అయ్యింది. |
| memory | మెమరీ | stance_adjectives | 0 | 1 | 0 | 1 | నిద్ర తక్కువైతే, మరుసటి రోజు ఫోకస్, మూడ్, మెమరీ అన్నీ దెబ్బతింటాయి. |
| model | మోడల | film_media_craft | 1 | 0 | 0 | 1 | ఒక కార్ మోడల్ లాగా మార్చేయొచ్చు. |
| moderate | మోడరేట | stance_adjectives | 1 | 0 | 0 | 1 | లో 50 స్టడీస్ అనాలసిస్ నిజమే కానీ మోడరేట్ చాలా పెద్దది కాదు జీరో కాదు. |
| mood | మూడ్ | stance_adjectives | 0 | 1 | 0 | 1 | నిద్ర తక్కువైతే, మరుసటి రోజు ఫోకస్, మూడ్, మెమరీ అన్నీ దెబ్బతింటాయి. |
| neuroscientist | న్యూరోసైంటిస్ట | science_psych_concepts | 0 | 1 | 0 | 1 | న్యూరోసైంటిస్ట్ Kent Berridge ఏం చూపించాడంటే, brainలో రెండు వేర్వేరు సిస్టమ్స్ ఉంటాయి. |
| nine (ordinal slot) | (pattern) | structure_ordinals | 0 | 1 | 0 | 1 | చాప్టర్ నైన్. |
| notice | నోటీస | everyday_loans | 1 | 0 | 0 | 1 | 2018 హ్యూమన్ రైట్స్ కమిషన్ తెలంగాణ ప్రభుత్వానికి నోటీసులు పంపింది. |
| office | ఆఫీస | everyday_loans | 0 | 1 | 0 | 1 | రోడ్డు మీదో, కాలేజీలోనో, ఆఫీస్‌లోనో ఒక అమ్మాయిని చూసినప్పుడు, మైండ్ వెళ్ళకూడని చోటికి వెళ్తుంది. |
| patient | పేషెంట | everyday_loans | 0 | 1 | 0 | 1 | పేషెంట్స్ ఒక కొత్త ఫేస్‌కి అలవాటు పడటానికి సుమారు 21 రోజులు పడుతోందని ఆయన గమనించాడు. |
| physical | ఫిజికల | science_psych_concepts | 0 | 1 | 0 | 1 | 2% సీన్స్‌లో ఫిజికల్ అగ్రెషన్ ఉంది, అంటే చెంపదెబ్బ కొట్టడం, గొంతు నొక్కడం లాంటివి. |
| plastic | ప్లాస్టిక | everyday_loans | 0 | 1 | 0 | 1 | ఈ 21 రోజుల ఐడియా 1960లో ఒక ప్లాస్టిక్ సర్జన్, Maxwell Maltz రాసిన ఒక బుక్ నుంచి వచ్చింది. |
| platform | ప్లాట్ఫార్మ | tech_platforms | 1 | 0 | 0 | 1 | సంపాదిస్తారు ప్రొడ్యూసర్లు మ్యూజిక్ లేబుల్స్ ప్లాట్ఫార్మ్స్ ఎవరు కడతారు సెట్ లో టాయిలెట్ లేని జూనియర్ ఆర్టిస్ట |
| pop up | పాప్ అప | tech_platforms | 0 | 1 | 0 | 1 | ఒక లింక్ పాప్ అప్ అవుతుంది. |
| practical | ప్రాక్టికల | stance_adjectives | 0 | 1 | 0 | 1 | ప్రాక్టికల్, రియల్ విషయాలు. |
| progress | ప్రోగ్రెస | stance_adjectives | 0 | 1 | 0 | 1 | పర్ఫెక్షన్ కాదు, ప్రోగ్రెస్ ట్రాక్ చేయ్. |
| promote | ప్రమోట | verb_stems | 1 | 0 | 0 | 1 | వన్ మార్కెటింగ్ ఈ పాటలు చాలాసార్లు రిలీజ్ కి ముందే సినిమాని ప్రమోట్ చేసే మార్కెటింగ్ టూల్ అని కంపోజర్స్ ప్రొడ్ |
| publish | పబ్లిష | verb_stems | 1 | 0 | 0 | 1 | నిజం చెప్పాలంటే ఒక ఐటం సాంగ్ నుంచి ఎంత వస్తుందో ఎవరు పబ్లిష్ |
| rape | (pattern) | stance_adjectives | 0 | 1 | 0 | 1 | డిసెంబర్ 2020లో, New York Times చేసిన ఒక ఇన్వెస్టిగేషన్ ఏం రిపోర్ట్ చేసిందంటే, ప్రపంచంలోనే అతిపెద్ద పోర్న్ సైట |
| react | రియాక్ట | verb_stems | 0 | 1 | 0 | 1 | ఇంకా స్క్రీన్ మీద ఉన్న ఆ అమ్మాయిలు చాలా వరకు, వాళ్ళు అది ఎంజాయ్ చేస్తున్నట్టే రియాక్ట్ అయ్యారు. |
| real | రియల | stance_adjectives | 0 | 1 | 0 | 1 | ప్రాక్టికల్, రియల్ విషయాలు. |
| reels | రీల్స | tech_platforms | 1 | 0 | 0 | 1 | రెండు పాట క్లిప్స్ రీల్స్ గా మారుతుంది. |
| replace | రీప్లేస | verb_stems | 0 | 1 | 0 | 1 | జస్ట్ తీసేయడం కాదు, రీప్లేస్ చేయ్. |
| respect | రెస్పెక్ట | stance_adjectives | 0 | 1 | 0 | 1 | ఒక రిలేషన్‌షిప్‌లో రెస్పెక్ట్ ఎలా ఉంటుందో తెలీదు. |
| restless | రెస్ట్‌లెస | stance_adjectives | 0 | 1 | 0 | 1 | అది లేకపోతే రెస్ట్‌లెస్‌గా, చిరాకుగా ఉంటుంది. |
| reveal | రివీల | film_media_craft | 1 | 0 | 0 | 1 | క్యారెక్టర్ ని రివీల్ చేసే పద్ధతి అని ఫిలిం గైడ్స్ చెప్తాయి. |
| scan | స్కాన | research_evidence | 0 | 1 | 0 | 1 | 2014లో Cambridgeలో Valerie Voon లీడ్ చేసిన రీసెర్చర్స్, compulsive sexual behaviour ఉన్న మగవాళ్ళ brains స్కాన్ |
| scroll | స్క్రోల | tech_platforms | 0 | 1 | 0 | 1 | రాత్రిపూట ఏదో స్క్రోల్ చేస్తుంటే. |
| session | సెషన | tech_platforms | 0 | 1 | 0 | 1 | అర్ధరాత్రి సెషన్స్ నీ నిద్రని దొంగిలిస్తాయి. |
| seven (ordinal slot) | (pattern) | structure_ordinals | 0 | 1 | 0 | 1 | చాప్టర్ సెవెన్. |
| shower | షవర | everyday_loans | 0 | 1 | 0 | 1 | ఒక వర్కౌట్, ఒక వాక్, ఫ్రెండ్‌తో ఒక కాల్, ఒక కోల్డ్ షవర్, నువ్వు నేర్చుకుంటున్న ఒక స్కిల్. |
| simple | సింపుల | stance_adjectives | 1 | 0 | 0 | 1 | మనిషిని చూసే వస్తువుగా చూడడం ఒక సింపుల్ టెస్ట్ |
| six (ordinal slot) | (pattern) | structure_ordinals | 0 | 1 | 0 | 1 | చాప్టర్ సిక్స్. |
| skill | స్కిల | everyday_loans | 0 | 1 | 0 | 1 | ఒక వర్కౌట్, ఒక వాక్, ఫ్రెండ్‌తో ఒక కాల్, ఒక కోల్డ్ షవర్, నువ్వు నేర్చుకుంటున్న ఒక స్కిల్. |
| skin | స్కిన | body_loans | 0 | 1 | 0 | 1 | ఆన్‌లైన్ గ్రూప్స్ మెరిసిపోయే స్కిన్, మ్యాగ్నెటిక్ చార్మ్, భారీ ఎనర్జీ అని ప్రామిస్ చేస్తాయి. |
| slow motion | స్లో మోషన | film_media_craft | 1 | 0 | 0 | 1 | ఐదు స్లో మోషన్ 12 ఎక్స్పెరిమెంట్స్ లో ప్రొడక్ట్స్ లగ్జరీగా కనిపించాయి. |
| slow pan | స్లో పాన | film_media_craft | 1 | 0 | 0 | 1 | రెండు వెనక నుంచి పక్కకి స్లో పాన్ మూడు కింద నుంచి పైకి టిల్ట్ ఒక |
| solid | సాలిడ | stance_adjectives | 0 | 1 | 0 | 1 | దానికి సాలిడ్ ఎవిడెన్స్ ఏమీ లేదు. |
| song (in item song) | సాంగ | film_media_craft | 1 | 0 | 0 | 1 | నిజం చెప్పాలంటే ఒక ఐటం సాంగ్ నుంచి ఎంత వస్తుందో ఎవరు పబ్లిష్ |
| special | స్పెషల | everyday_loans | 1 | 0 | 0 | 1 | ఒక స్పెషల్ పోలీస్ టీం కేసులు తీసుకుంది. |
| step by step | స్టెప్ బై స్టెప | discourse_markers | 0 | 1 | 0 | 1 | ఇప్పుడు ఈ చెయిన్‌ని స్టెప్ బై స్టెప్ చూడు. |
| stop (bus stop) | స్టాప | everyday_loans | 1 | 0 | 0 | 1 | కాలేజీ, బస్ స్టాప్ ఆమె వీధి కార్డ్ త్రీ ఫ్రెండ్స్ చప్పట్లు కొడతారు పాట వస్తుంది. |
| streak | స్ట్రీక | everyday_loans | 0 | 1 | 0 | 1 | పర్ఫెక్ట్ స్ట్రీక్స్ కాదు, మంచి వారాలు కౌంట్ చేయ్. |
| strong | స్ట్రాంగ | stance_adjectives | 0 | 1 | 0 | 1 | ఇంకా స్ట్రాంగ్‌గా. |
| submit | సబ్మిట | verb_stems | 1 | 0 | 0 | 1 | 2019 లో సబ్మిట్ చేశారు. |
| subscribe | సబ్స్క్రైబ | tech_platforms | 1 | 0 | 0 | 1 | పార్ట్ త్రీ కోసం సబ్స్క్రైబ్ చేయండి. |
| superpower | సూపర్‌పవర | stance_adjectives | 0 | 1 | 0 | 1 | మిత్: మానేస్తే సూపర్‌పవర్స్ వస్తాయి. |
| support | సపోర్ట | verb_stems | 0 | 1 | 0 | 1 | ఇంకా ఆ వ్యూ, అమ్మాయిల మీద వయలెన్స్‌ని సపోర్ట్ చేసే ఆటిట్యూడ్స్‌తో కలిసే కనిపించింది. |
| surf (urge-surf) | సర్ఫ | verb_stems | 0 | 1 | 0 | 1 | Urgeని సర్ఫ్ చేయ్. |
| surgeon | సర్జన | everyday_loans | 0 | 1 | 0 | 1 | ఈ 21 రోజుల ఐడియా 1960లో ఒక ప్లాస్టిక్ సర్జన్, Maxwell Maltz రాసిన ఒక బుక్ నుంచి వచ్చింది. |
| sweater | స్వెటర | everyday_loans | 1 | 0 | 0 | 1 | స్టూడెంట్స్ స్విమ్ సూట్ కానీ స్వెటర్ గాని వేసుకున్నారు. |
| theatre | థియేటర | film_media_craft | 1 | 0 | 0 | 1 | నెక్స్ట్ టైం కెమెరా ఆమె నడుము మీదకు దిగి థియేటర్ విజిల్స్ వేసినప్పుడు మనం ఎందుకు విజిల్స్ వేస్తున్నాం మనం వేసి |
| tilt | టిల్ట | film_media_craft | 1 | 0 | 0 | 1 | రెండు వెనక నుంచి పక్కకి స్లో పాన్ మూడు కింద నుంచి పైకి టిల్ట్ ఒక |
| tool | టూల | commerce_products | 1 | 0 | 0 | 1 | వన్ మార్కెటింగ్ ఈ పాటలు చాలాసార్లు రిలీజ్ కి ముందే సినిమాని ప్రమోట్ చేసే మార్కెటింగ్ టూల్ అని కంపోజర్స్ ప్రొడ్ |
| tyre | టైర | commerce_products | 1 | 0 | 0 | 1 | టైర్లు ఆమె కాళ్ళు కార్ వెనక భాగం ఆమె హిప్స్ |
| university | యూనివర్సిటీ | everyday_loans | 1 | 0 | 0 | 1 | ఇప్పుడు మన మొదటి ప్రశ్న కాలేజీ వరల్డ్ బ్యాంక్ ఎకనామిస్ట్ ఢిల్లీ యూనివర్సిటీ స్టూడెంట్స్ ని స్టడీ చేశారు. |
| unverified | అన్‌వెరిఫైడ | stance_adjectives | 0 | 1 | 0 | 1 | ఆ తర్వాత ఆ సైట్ సుమారు 10 మిలియన్ అన్‌వెరిఫైడ్ వీడియోస్‌ని తీసేసింది. |
| values | వాల్యూస | stance_adjectives | 0 | 1 | 0 | 1 | సైకాలజిస్ట్ Joshua Grubbs ఏం కనిపెట్టాడంటే, తమ పోర్న్ వాడకం తమ వాల్యూస్‌కి వ్యతిరేకంగా ఉందని ఫీల్ అయ్యేవాళ్ళు, |
| walk | వాక | everyday_loans | 0 | 1 | 0 | 1 | ఒక వర్కౌట్, ఒక వాక్, ఫ్రెండ్‌తో ఒక కాల్, ఒక కోల్డ్ షవర్, నువ్వు నేర్చుకుంటున్న ఒక స్కిల్. |
| warning | వార్నింగ | stance_adjectives | 0 | 1 | 0 | 1 | ఇంకా ఇక్కడ నేను ఒక వార్నింగ్ ఇవ్వాల్సిందే. |
| website | వెబ్‌సైట | tech_platforms | 0 | 1 | 0 | 1 | హైదరాబాద్‌లో ఉన్న ఫోన్ అయినా, Ohioలో ఉన్న ఫోన్ అయినా, ఓపెన్ చేసేది అవే వెబ్‌సైట్స్. |
| workout | వర్కౌట | everyday_loans | 0 | 1 | 0 | 1 | ఒక వర్కౌట్, ఒక వాక్, ఫ్రెండ్‌తో ఒక కాల్, ఒక కోల్డ్ షవర్, నువ్వు నేర్చుకుంటున్న ఒక స్కిల్. |
