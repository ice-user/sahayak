# Scheme research batch report

Generated 2026-11-27T13:38:39+00:00; 14 source(s).
Nothing is added to the database by this run: approve each thread with `python -m research review <thread> --approve`, then `python -m research merge`.

Wall time 455s (32.5s per source); sum of per-source times 875s; extractor attempts 40; LLM calls 85 (6.1 per source, extractor + auditor); tokens 534127.

## Ready for review (all automatic checks passed): 1

| Source | Scheme | Thread | Secs / tries | Notes |
|---|---|---|---|---|
| https://www.myscheme.gov.in/schemes/post-st | Post Matric Scholarship Scheme For The Students Belonging To Scheduled Tribe For Studies In India `post_matric_scholarship_st` | `r-e2a863b6c8` | 108s / 1 |  |

## Needs human fix (checks still failing after retries): 13

| Source | Scheme | Thread | Secs / tries | Notes |
|---|---|---|---|---|
| https://www.myscheme.gov.in/schemes/pmuy2 | Pradhan Mantri Ujjwala Yojana 2.0 `pradhan_mantri_ujjwala_yojana_2_0` | `r-1fce6044d1` | 66s / 3 | auditor: rules[0] (gender eq "female"): The document restricts eligibility to adult women belonging to specified categories, but the rule only checks gender and omits the category requirement entirely |
| https://www.myscheme.gov.in/schemes/fesmwpnie | Free Education For Sports Medal Winners / Participants Of National/ International Events `free_education_for_sports_medal_winners_participants` | `r-d7562fec7d` | 59s / 3 | auditor: criterion in the source is covered by no rule or caveat: Applicant must be a medal winner of National games or participant in recognized international sporting events recognized by the World  |
| https://www.myscheme.gov.in/schemes/pm-svanidhi | PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi) `pm_svanidhi` | `r-69af5e9e8e` | 43s / 3 | auditor: candidate: The document states the loan is provided at a low-interest rate of 7% with a 7% interest subsidy, but the candidate's benefits field does not clearly state that the 7% is an intere |
| https://www.myscheme.gov.in/schemes/rkvp | Rashtriya Krishi Vigyan Puraskar `rashtriya_krishi_vigyan_puraskar` | `r-8a6dc203f6` | 139s / 3 | auditor: candidate: No age rules were extracted even though every category has an age limit; missing upper bounds mean citizens could be wrongly told they qualify or do not qualify -- source says: "mu |
| https://www.myscheme.gov.in/schemes/nsrdard | National Savings Recurring Deposit Account(RD) `national_savings_recurring_deposit_account` | `r-e0f98aa0d4` | 53s / 3 | auditor: rules[0] (age gte 10): The document allows minors aged 10 and above, single adults, guardians, and joint accounts up to three adults with no upper age limit; the rule only captures age >= 10  |
| https://www.myscheme.gov.in/schemes/prism-c2-fwmpkhttptt | PRISM (Promoting Innovations in Individuals, Start-ups and MSMEs): Category-2: Fabrication of Working Model/Process Know-how/Testing & Trial/Patenting/Technology Transfer `prism_category_2_fabrication_working_model` | `r-93f1a0549c` | 55s / 3 | auditor: criterion in the source is covered by no rule or caveat: Applicant must be an Indian Citizen -- source says: "The applicant must be an Indian Citizen.". Add a rule if a Profile field can expr |
| https://www.myscheme.gov.in/schemes/nccsra | National Centre for Communication Security (NCCS) Research Associates Scheme `nccs_research_associates_scheme` | `r-37d5b9e91e` | 50s / 3 | auditor: criterion in the source is covered by no rule or caveat: Applicant must be an Indian National -- source says: "Only Indian Nationals may apply.". Add a rule if a Profile field can express it, |
| https://www.myscheme.gov.in/schemes/sga | Shilp Guru Award `shilp_guru_award` | `r-a579934394` | 58s / 3 | auditor: rules[0] (age gte 55): Rule only captures lower bound of age; document states applicant should be at least 55 years old with no upper bound, so rule is faithful on age but the engine cannot v |
| https://www.myscheme.gov.in/schemes/cssrbl | Central Sector Scheme for Rehabilitation of Bonded Labourer `central_sector_scheme_for_rehabilitation_of_bonded_labourer` | `r-35e7da5a02` | 46s / 3 | auditor: candidate: No eligibility rules were extracted; the only eligibility condition in the document is that the beneficiary must be a rescued bonded labourer, which cannot be checked by the engine |
| https://www.myscheme.gov.in/schemes/ads | Ashadeepa Scheme `ashadeepa_scheme` | `r-441b7c6d5b` | 50s / 3 | auditor: rules[0] (state eq "Karnataka"): The only mapped rule is state Karnataka; all other eligibility criteria from the document are missing from the rules engine, so citizens could be wrongly told |
| https://www.myscheme.gov.in/schemes/aas | Ashraya Adhar Scheme `ashraya_adhar_scheme` | `r-f3ed6057b9` | 61s / 3 | auditor: rules[0] (age lte 55): Rule only captures the standard upper age limit of 55 and omits the relaxation to 58 for government/corporation/board/aided institute employees, so eligible older appli |
| https://www.myscheme.gov.in/schemes/akckvy | Aaloo Ke Kufri Chipsona-1 Prabhed Ke Kshetra Vistaar Yojana `aaloo_ke_kufri_chipsona_1_prabhed_ke_kshetra_vistaar_yojana` | `r-929c589c7f` | 50s / 3 | auditor: rules[1] (owns_cultivable_land eq true): Rule only checks that the applicant owns cultivable land, but the document requires agricultural land between a minimum of 0.25 acres (0.1 ha) and a m |
| https://www.myscheme.gov.in/schemes/aavy | Atal Awasiya Vidyala Yojana `atal_awasiya_vidyalaya_yojana` | `r-9dfc4a9035` | 38s / 3 | auditor: rules[0] (state eq "Uttar Pradesh"): The document states the scheme is implemented in only 18 districts of Uttar Pradesh, but the rule only checks state eq Uttar Pradesh, missing the district |

## Failed (fetch / LLM / unexpected error): 0

## Already decided: 0
