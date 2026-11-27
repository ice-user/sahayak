# Bullet-to-rules fine-tuning dataset

One task: map a single eligibility bullet from a scheme page to structured rules (`research/fields.py` fields, canonical state names) plus `unmapped` conditions that no field can express.

## How it was built

1. `scripts/collect_myscheme.py snapshot` rendered myscheme.gov.in scheme pages (730 schemes with at least one eligibility bullet; a seeded random sample, about 40% central / 60% state, spread over states, throttled to one page per 2 s).
2. `research/bullets.py` takes the second `Eligibility` heading's section (the first is the nav menu) up to the next section heading and splits it into bullets/sentences, dropping empty and boilerplate lines.
3. Teacher `nvidia/nemotron-3.5-super-vl-120b-a12b` (NVIDIA API, thinking off, temperature 0) labelled every bullet with a compact few-shot prompt (`research/bullet_prompt.py`), 4 threads, one retry on API/parse errors.
4. `research/bullet_check.py` keeps a label only if: the JSON shape is exact; each rule's field/op/value is valid per `research/fields.py` and `research/validate.py` (types, ranges, canonical state names, no contradictions); each quote is a verbatim substring of the bullet; each number in a rule appears in its quote; and every number in the bullet is covered by some quote.
5. Splits are by scheme (no scheme appears in two splits), 80/10/10, stratified by central/state (seed 20261127). Bullets identical to a test bullet were removed from train/val (183 dropped).

## Files

Each line: `{scheme_id, url, level, bullet, target}`; target = `{"rules": [{field, op, value, quote}], "unmapped": [{quote, reason}]}`.

- `train.jsonl`, `val.jsonl`, `test.jsonl`: checked labels only.
- `test_all.jsonl`: every test-scheme bullet; `target` is null where the teacher label failed the check, so the test set is not biased toward easy bullets.
- `labels.jsonl`: every teacher output with its check result and first problems (provenance).

## Counts

- Schemes: 730 (train 584, val 73, test 73); central 298, state 432
- Bullets labelled: 5163; passed the checker: 4831
- **Teacher pass rate: 93.6%**
- train 3731, val 433, test 484, test_all 518 (484 with a target, 34 null)
- Among passed labels: 986 bullets have at least one rule, 550 have no rules and no unmapped entries (no condition), 1154 rules and 4925 unmapped items in total

## Rule field distribution (passed labels)

| field | rules |
|---|---|
| age | 368 |
| state | 359 |
| annual_income | 114 |
| gender | 79 |
| bpl | 63 |
| in_regular_govt_employment | 44 |
| marital_status | 38 |
| children | 25 |
| has_bank_account | 18 |
| ever_income_tax_payer | 12 |
| is_govt_employee | 11 |
| owns_cultivable_land | 11 |
| pregnant_or_lactating | 9 |
| household_has_lpg | 3 |

Ops: eq 640, lte 279, gte 199, any_child 25, in 8, ne 3

## Most common reasons a teacher label failed

- #: 183
- number # for annual_income does not appear in its quote: 36
- #, #: 21
- quote must be one contiguous span of the bullet (no ellipsis: 20
- number # for age does not appear in its quote: 14
- state # is not named in its quote: 11
- number # for monthly_pension does not appear in its quote: 10
- quote is not a verbatim substring of the bullet (too_short):: 9

## Teacher usage

- Calls: 5163, total tokens: 6807822 (prompt + completion, as reported by the API)

## Known limitations

- **Labels are silver, not human gold**: they come from the teacher model and were only checked by code (shape, validity, verbatim quotes, number grounding). A label can pass and still be semantically wrong (for example a missed condition without numbers, or a field choice a human would disagree with).
- The field set is small (`sahayak.models.Profile`), so most real conditions (caste, occupation, disability, education) are `unmapped`.
- Bullets come from one site's English text; labels were not reviewed per state. Pages differ in style.
- Sentence splitting is heuristic; some bullets are fragments or run-ons.
