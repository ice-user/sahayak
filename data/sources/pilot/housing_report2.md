# Scheme research batch report

Generated 2026-11-28T07:32:21+00:00; 2 source(s).
Nothing is added to the database by this run: approve each thread with `python -m research review <thread> --approve`, then `python -m research merge`.

Wall time 92s (46.0s per source); sum of per-source times 153s; extractor attempts 6; LLM calls 11 (5.5 per source, extractor + auditor); tokens 114119.

## Ready for review (all automatic checks passed): 0

## Needs human fix (checks still failing after retries): 2

| Source | Scheme | Thread | Secs / tries | Notes |
|---|---|---|---|---|
| https://www.myscheme.gov.in/schemes/pmay-g | Pradhan Mantri Awaas Yojana - Gramin `pmay_g` | `r-c989648db3` | 92s / 3 | auditor: candidate: No eligibility rules were extracted; the document contains explicit exclusion criteria (e.g., pucca house ownership, government employee, income above Rs.10,000/month, paying incom |
| https://www.myscheme.gov.in/schemes/pmay-u | Pradhan Mantri Awas Yojana - Urban `pradhan_mantri_awas_yojana_urban` | `r-5f7b25ccbd` | 61s / 3 | auditor: rules[0] (annual_income lte 300000): The rule restricts eligibility to EWS only (annual_income lte 300000), but the document defines four income categories (EWS up to 3,00,000; LIG 3,00,001 t |

## Failed (fetch / LLM / unexpected error): 0

## Already decided: 0
