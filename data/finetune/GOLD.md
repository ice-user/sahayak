# Gold test set (reviewed)

`test_gold.jsonl` is `test_all.jsonl` (518 bullets, 73 held-out schemes) with every target read and corrected one by one by a reviewer. Line format: `{scheme_id, url, level, bullet, target, teacher_target, changed, note}` (`note` only when changed). Every gold target passes `research/bullet_check.py`.

**Caveat: this gold set was reviewed by an LLM (Claude Sonnet, a different model family from the Nemotron teacher), not by a human. Spot-check a sample before trusting the numbers; `spotcheck_30.jsonl` has 30 items for that (seed 20261127; 12 changed, 18 unchanged).**

## Counts

- Bullets: 518 (484 had a teacher label, 34 had `target: null` because the teacher label failed the checks)
- Gold targets with at least one rule: 87 (104 rules in total); 61 gold bullets are empty/no-condition or have only unmapped items, the rest are unmapped-only
- Changed vs teacher: 77 of 518 (14.9%) = 34 teacher failures filled in + 43 corrections of passing teacher labels
- Unchanged: 441

## Teacher label changes (the 484 labels that had passed the code check)

- Changed: 43 / 484 = 8.9%
  - rules changed: 32 (6.6%)
  - unmapped-only changed (rules identical): 11 (2.3%)
- Unchanged: 441 (91.1%)

## Five most common teacher error types (the 43 corrections)

1. Spurious state rule (16): a state name taken from an institution, issuing authority, board or scheme name instead of the applicant's residence. Example: "beneficiary of the Delhi Scheduled Castes ... Finance and Development Corporation" gave `state eq Delhi`; "Government of NCT of Delhi" issuing an income certificate also gave Delhi.
2. Missed condition (12): a criterion left out entirely (empty lists) or a mappable fact missed. Example: "Unemployed son below 28 years of age" had the age rule but no `gender eq male`; list items such as "Urban Local Bodies" got empty targets.
3. Wrong field (6): a condition forced into a field that means something narrower. Example: "Persons already in regular service" became `in_regular_govt_employment eq false` although the service need not be government.
4. Conditional or alternative condition turned into a hard rule (4): Example: "self-cultivates their land or cultivates leased land" became `owns_cultivable_land eq true`, which would wrongly exclude lessee farmers; "age limit 37 for SC/ST/Women" and "42 for persons with disabilities" became unconditional `age lte` rules.
5. Wrong subject (3) and bad age bound (2): rule about someone other than the applicant (mentor's regular faculty post became govt employment) and wrong inclusive bounds (bridegroom "above 21" labelled `gte 21`; "between 18 and over 80" labelled `gte 18` and `gte 81`).

The 34 `teacher_failed` items had no teacher label; many are "Note 02: ..." or numbered list lines where the number prefix has to be inside some quote for the checker. For those administrative lines the gold uses one unmapped item quoting the whole bullet with the reason "administrative note, not an eligibility condition" (not a real condition, just needed to satisfy the number-coverage check).

## Review policy applied

- Rules only when the condition is the applicant's own, unconditional, and expressible by a profile field; category-specific limits (SC/ST, disability, women, "if girl") go to unmapped.
- A state rule needs residence or domicile of the applicant (or the applicant entity being located there); institution, bank, school, issuer or scheme names containing a state do not count.
- "above N" is gte N+1, "below N" is lte N-1, "N and above"/"up to N" are inclusive; income "less than X" is lte X-1; monthly limits are multiplied by 12.
- Where the source is ambiguous or contradictory, the span goes to unmapped rather than guessing a bound.
- Known unavoidable gap: bullet 250 spells the state "Madhya Pradeah", so it is unmapped to keep the quote verbatim.
