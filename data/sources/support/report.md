# Scheme research batch report

Generated 2026-11-27T22:35:53+00:00; 15 source(s).
Nothing is added to the database by this run: approve each thread with `python -m research review <thread> --approve`, then `python -m research merge`.

Wall time 348s (23.2s per source); sum of per-source times 676s; extractor attempts 45; LLM calls 85 (5.7 per source, extractor + auditor); tokens 528503.

## Ready for review (all automatic checks passed): 0

## Needs human fix (checks still failing after retries): 15

| Source | Scheme | Thread | Secs / tries | Notes |
|---|---|---|---|---|
| https://www.myscheme.gov.in/schemes/nfbs | National Family Benefit Scheme `national_family_benefit_scheme` | `r-1b0f635fac` | 40s / 3 | auditor: rules[0] (bpl eq true): The only encoded rule is BPL status; all other eligibility criteria from the document are missing as rules, so citizens could be wrongly told they qualify or do not qu |
| https://www.myscheme.gov.in/schemes/igndps | Indira Gandhi National Disability Pension Scheme `indira_gandhi_national_disability_pension_scheme` | `r-f97cb28ebe` | 33s / 3 | auditor: rules[0] (age gte 18): Document states pension of Rs.300 per month for Divyangjan between 18-79 years and Rs.500 per month for those aged 80 years and above, but the rule only captures a lowe |
| https://www.myscheme.gov.in/schemes/pm-sym | Pradhan Mantri Shram Yogi Maan-dhan `pm_shram_yogi_maan_dhan` | `r-493195266b` | 32s / 3 | auditor: rules[2] (annual_income lte 180000): Document specifies monthly income of ₹15,000 or less; rule converts to annual income of ₹180,000 but the engine only has annual_income field, so a citizen |
| https://www.myscheme.gov.in/schemes/pmkmdy | Pradhan Mantri Kisan Maandhan Yojana `pm_kisan_maandhan_yojana` | `r-44b6ea78e4` | 71s / 3 | auditor: rules[0] (age gte 18): Age lower bound is captured, but the candidate's rules array contains only age conditions and omits all other eligibility criteria, meaning citizens could be wrongly to |
| https://www.myscheme.gov.in/schemes/pmfby | Pradhan Mantri Fasal Bima Yojna (PMFBY) `pmfby` | `r-04a0dd3cfc` | 60s / 3 | auditor: candidate: No eligibility rules were extracted; the engine will evaluate an empty rule set and cannot enforce any of the document's eligibility conditions (e.g., insurable interest, land owne |
| https://www.myscheme.gov.in/schemes/pmjdy | Pradhan Mantri Jan Dhan Yojana `pmjdy` | `r-bbdf52a78f` | 29s / 3 | auditor: criterion in the source is covered by no rule or caveat: Applicant must be an Indian National -- source says: "The applicant should be an Indian National.". Add a rule if a Profile field can  |
| https://www.myscheme.gov.in/schemes/pmv | PM Vishwakarma `pm_vishwakarma` | `r-378966517a` | 37s / 3 | auditor: rules[1] (in_regular_govt_employment eq false): The exclusion covers both a person in government service AND their family members, but the rule only checks the applicant's own government empl |
| https://www.myscheme.gov.in/schemes/sui | Stand-Up India `stand_up_india` | `r-d741137669` | 43s / 3 | auditor: rules[0] (age gte 18): The document sets an age condition only for male applicants (at least 18 years), but the rule applies it to all applicants regardless of gender, making it stricter for  |
| https://www.myscheme.gov.in/schemes/pm-svanidhi | PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi) `pm_svanidhi` | `r-69af5e9e8e` | 29s / 3 | evidence for benefits[7]: quote not found in the source (best match 94/100); copy it verbatim or drop the claim: "The scheme encourages entrepreneurship and helps them to create employment opportuniti |
| https://www.myscheme.gov.in/schemes/pm-gkay | Pradhan Mantri Garib Kalyan Anna Yojana `pm_gkay` | `r-1426813393` | 60s / 3 | auditor: criterion in the source is covered by no rule or caveat: Families must belong to Antyodaya Anna Yojana (AAY) or Priority Households (PHH) categories -- source says: "Families belonging to Ant |
| https://www.myscheme.gov.in/schemes/nps-tsep | National Pension Scheme for Traders And Self Employed Persons `nps_tsep` | `r-9a28e5a827` | 40s / 3 | auditor: rules[3] (income_tax_payer_last_year eq false): Document says applicant must not be an income-tax payer or income-tax assessee (general status), but rule only checks last year's status; a per |
| https://www.myscheme.gov.in/schemes/sadppfaa | Scheme Of Assistance To Disabled Persons For Purchase/Fitting Of Aids/Appliances `adip_scheme` | `r-ca690db38c` | 85s / 3 | auditor: rules[0] (annual_income lte 360000): Document specifies monthly income not exceeding Rs. 30,000 per month, but rule uses annual_income with value 360000. The engine only supports annual_incom |
| https://www.myscheme.gov.in/schemes/gpaiscw | Group Personal Accident Insurance Scheme For Coir Workers `group_personal_accident_insurance_scheme_for_coir_workers` | `r-460a69ccde` | 27s / 3 | auditor: candidate: The document requires the applicant to be EITHER a disabled coir worker OR nominee of the disabled/deceased coir worker, but no rule captures this alternative; the rules array is e |
| https://www.myscheme.gov.in/schemes/nswf | National Scheme Of Welfare Of Fishermen `national_scheme_of_welfare_of_fishermen` | `r-ee02b1e95e` | 57s / 3 | auditor: candidate: No eligibility rules were provided; the engine cannot check any criteria, so citizens may be wrongly told they qualify or do not qualify. -- source says: "Eligibility Criteria for  |
| https://www.myscheme.gov.in/schemes/cssrbl | Central Sector Scheme for Rehabilitation of Bonded Labourer `central_sector_scheme_for_rehabilitation_of_bonded_labourer` | `r-35e7da5a02` | 33s / 3 | auditor: criterion in the source is covered by no rule or caveat: The beneficiary should be a rescued bonded labour -- source says: "The beneficiary should be a rescued bonded labour.". Add a rule if  |

## Failed (fetch / LLM / unexpected error): 0

## Already decided: 0
