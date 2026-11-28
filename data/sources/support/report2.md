# Scheme research batch report

Generated 2026-11-28T07:30:45+00:00; 15 source(s).
Nothing is added to the database by this run: approve each thread with `python -m research review <thread> --approve`, then `python -m research merge`.

Wall time 402s (26.8s per source); sum of per-source times 765s; extractor attempts 45; LLM calls 96 (6.4 per source, extractor + auditor); tokens 710601.

## Ready for review (all automatic checks passed): 0

## Needs human fix (checks still failing after retries): 15

| Source | Scheme | Thread | Secs / tries | Notes |
|---|---|---|---|---|
| https://www.myscheme.gov.in/schemes/nfbs | National Family Benefit Scheme `national_family_benefit_scheme` | `r-1b0f635fac` | 18s / 3 | behavioural test 'breadwinner_deceased differs from required True' crashed: 1 validation error for Profile   Value error, breadwinner_age_at_death given but breadwinner_deceased=false [type=value_erro |
| https://www.myscheme.gov.in/schemes/igndps | Indira Gandhi National Disability Pension Scheme `igndps` | `r-f97cb28ebe` | 49s / 3 | auditor: rules[1] (disability_percentage gte 80): Document says disability should be more than 80% (strictly greater than 80), but rule uses gte 80 which admits exactly 80% -- source says: "The applic |
| https://www.myscheme.gov.in/schemes/pm-sym | Pradhan Mantri Shram Yogi Maan-dhan `pm_shram_yogi_maan_dhan` | `r-493195266b` | 51s / 3 | auditor: rules[0] (is_unorganised_worker eq true): The document lists specific categories of eligible workers (unorganized worker, construction workers, domestic workers, cobbler etc.) but the rule on |
| https://www.myscheme.gov.in/schemes/pmkmdy | Pradhan Mantri Kisan Maandhan Yojana `pm_kisan_maandhan_yojana` | `r-44b6ea78e4` | 76s / 3 | auditor: rules[2] (age gte 18): The rule captures age gte 18 but the document says 'between 18 and 40 years of age at the time of entry'; the upper bound lte 40 is present in rule 3, so both bounds ar |
| https://www.myscheme.gov.in/schemes/pmfby | Pradhan Mantri Fasal Bima Yojna (PMFBY) `pmfby` | `r-04a0dd3cfc` | 45s / 3 | auditor: candidate: No eligibility rules were extracted; the document lists eligibility conditions (e.g., all farmers including tenant farmers and sharecroppers growing notified crops in notified area |
| https://www.myscheme.gov.in/schemes/pmjdy | Pradhan Mantri Jan Dhan Yojana `pmjdy` | `r-bbdf52a78f` | 26s / 3 | auditor: candidate: The document states eligibility requires the applicant to be an Indian National, but no rule enforces citizenship; the rules engine has no citizenship field, so this criterion is e |
| https://www.myscheme.gov.in/schemes/pmv | PM Vishwakarma `pm_vishwakarma` | `r-378966517a` | 50s / 3 | auditor: rules[0] (occupation eq "artisan_craftsperson"): The document requires the applicant to be an artisan or craftsperson working with hands and tools AND engaged in one of 18 specific family-bas |
| https://www.myscheme.gov.in/schemes/sui | Stand-Up India `stand_up_india` | `r-d741137669` | 44s / 3 | auditor: rules[0] (social_category in ["sc", "st"]): Rule requires SC/ST for all applicants, but the document only requires SC/ST for male applicants; women applicants are eligible regardless of categ |
| https://www.myscheme.gov.in/schemes/pm-svanidhi | PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi) `pm_svanidhi` | `r-69af5e9e8e` | 38s / 3 | auditor: candidate: No eligibility rules were extracted; the document lists four categories of eligible street vendors (Certificate of Vending/Identity Card holders, surveyed-but-unissued vendors, ven |
| https://www.myscheme.gov.in/schemes/pm-gkay | Pradhan Mantri Garib Kalyan Anna Yojana `pm_gkay` | `r-1426813393` | 51s / 3 | auditor: candidate: No eligibility rules were extracted; the document lists specific eligibility categories (AAY and PHH families, AAY sub-criteria such as households headed by widows/terminally ill/d |
| https://www.myscheme.gov.in/schemes/nps-tsep | National Pension Scheme for Traders And Self Employed Persons `nps_tsep` | `r-9a28e5a827` | 35s / 3 | auditor: rules[3] (is_epfo_esic_nps_member eq false): The rule combines EPFO, ESIC and NPS into one field, but the document lists them as separate exclusions and also excludes PM-SYM members; the engi |
| https://www.myscheme.gov.in/schemes/sadppfaa | Scheme Of Assistance To Disabled Persons For Purchase/Fitting Of Aids/Appliances `adip_scheme` | `r-ca690db38c` | 128s / 3 | auditor: rules[0] (disability_percentage gte 40): The document requires a 40% Disability Certificate (benchmark disability) for beneficiaries, but certain aids require higher disability percentages (8 |
| https://www.myscheme.gov.in/schemes/gpaiscw | Group Personal Accident Insurance Scheme For Coir Workers `group_personal_accident_insurance_scheme_for_coir_workers` | `r-460a69ccde` | 41s / 3 | auditor: rules[0] (occupation eq "coir_worker"): The document says the applicant must be EITHER a disabled coir worker OR nominee of the disabled/deceased coir worker. The rule restricts eligibility t |
| https://www.myscheme.gov.in/schemes/nswf | National Scheme Of Welfare Of Fishermen `national_scheme_of_welfare_of_fishermen` | `r-ee02b1e95e` | 65s / 3 | auditor: candidate: No eligibility rules were extracted; the engine will evaluate an empty rule set and cannot enforce any eligibility condition from the document. -- source says: "Eligibility Criteri |
| https://www.myscheme.gov.in/schemes/cssrbl | Central Sector Scheme for Rehabilitation of Bonded Labourer `central_sector_scheme_for_rehabilitation_of_bonded_labourer` | `r-35e7da5a02` | 48s / 3 | auditor: candidate: No eligibility rules were extracted; the only eligibility condition in the document (being a rescued bonded labourer) is missing, so the engine cannot evaluate anyone -- source say |

## Failed (fetch / LLM / unexpected error): 0

## Already decided: 0
