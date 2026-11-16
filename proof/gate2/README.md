# Gate-2 loanword recalibration — ear-check samples

**What Ajju is being asked to judge:** gate 2 used to kill correct
takes because the channel's own English loanwords — written in Telugu
script in the script — come back from unhinted whisper in Latin or
Arabic script and read as foreign bleed. The recalibration (settings
flag `gates.gate2_loanword_aware`, **still OFF in the shipped
settings** — these samples were produced with the flag on) excuses a
token only when it is an attested channel loanword (304 lexemes,
`voice/english_mix_classes.json`) present in *that sentence's own
script*, in its exact English form (`safe` for సేఫ్, `fees` for
ఫీజు — never `safer`), or matching the English phonetic form at a
raised bar.

## The samples

Both are whole takes in the locked voice (IndicF5, natspan2
reference, speed 1.0; indicf5-batch run 43944853511, the production
mass-roll route), gated locally under both bars with identical
detections (`finalize_samples.py`, per-sample `.qc.json` alongside).

### sample-5-short-criminal-case.mp3
Script: పోలీసులు క్రిమినల్ కేసులో థియరీని రివ్యూ చేశారు.
Unhinted whisper: "…criminal **case** lo **theory** ni **review**
chaisaru"
- **Old gate killed it on:** `case` (phon matches no script word,
  sim 0.40) and `review` (phon 'reuiew', sim 0.36) — two of the
  sentence's own loanwords.
- **New gate:** 0 ghosts. Gate 1 ✓, gate 7 ✓, identity 0.861 ✓.
- Honest status: **not a full-bar ship** — pace measures 1.705 wps
  vs the 1.9–2.5 band. That is a generation-side property of the
  local-model route (its takes land at 1.6–1.83 wps), not a gate-2
  question; gate 2 was the only *gate* this take failed, and it
  failed it only under the old matcher.

### sample-7-short-safety-report.mp3
Script: స్టూడెంట్స్ సేఫ్టీ గురించి కమిటీ రిపోర్ట్ విడుదల చేశారు.
Unhinted whisper: "…**Students Safety** … **Committee Report**…"
- **Old gate killed it on:** `Safety` (phon 'sapety' ~ blacklist
  phon 'sape') — the sentence's own సేఫ్టీ, in its exact English
  form.
- **New gate:** 0 ghosts. Gate 7 ✓.
- Honest status: **not a full-bar ship** — gate 1 (no-hint language
  probability) failed on this detection, so identity/pace were never
  reached. Gate 2 was again the only *content* gate at issue, and it
  flipped.

## Why no full-bar ship-flip sample

47 Space-route rolls were hunted first (`rolls-log.json`): gate 2's
ghost count dropped on 15 of them ('case' alone cleared in five
takes), and three takes reached gate-2-clean under the new bar —
each was then stopped by a *different* bar element (gate 1 language
probability, gate 7 cut-word, pace). The Space then entered a
ZeroGPU error streak that ended the hunt. The Actions local-model
route paces systematically below the band (above), so its takes
cannot supply the missing conjunction either. The two samples above
are the strongest gate-2 evidence captured: in both, the **only**
words the old gate objected to are the channel's own loanwords, and
the new gate passes them. Deciding the flag is exactly the question
of whether those words should pass.

## Audit trail
- `rolls-log.json` — every Space-hunt roll, both bars, per take.
- `finalize-log.json` — the five harvested candidates re-gated
  locally (two flips, one both-clean, two correctly unrepaired:
  garble-class ghosts like 'Zoola'/'sisturn' stay ghosts under the
  new matcher too).
- `driver3.py`, `finalize_samples.py`, `harvest.py` — the drivers.
