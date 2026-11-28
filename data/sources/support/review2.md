# Support + housing schemes, second run with the new profile fields (2026-11-28)

Run: model nvidia/nemotron-3.5-super-vl-120b-a12b, fresh state DBs research/.state/support2.sqlite and housing2.sqlite, candidates in data/candidates_support2 and data/candidates_housing2. Reports: data/sources/support/report2.md, data/sources/pilot/housing_report2.md.
Tokens: support batch 710,601 (96 LLM calls); housing batch 114,119 (11 calls); one extra NFBS re-run after fixing a validator bug found by the batch (not measured, roughly 30k). Nothing approved or merged, data/schemes.json unchanged.
Status before -> after: all 15 support schemes `needs fix` -> `needs_human_fix`; PMAY-G / PMAY-U `needs fix` -> `needs_human_fix`. Zero schemes passed the auditor, but the reasons changed: every earlier 'profile cannot express it' blocker is gone; what remains is auditor strictness (every non-rule criterion must be a caveat), exclusive-bound slips (NFBS, IGNDPS), conditional/OR criteria, and extractor mistakes (Stand-Up India).
Edits: data/sources/support/edits/<thread>.json (each re-validated offline with validate_candidate: 0 errors, 0 warnings, every quote found in the source). Review with `python -m research review <thread> --edit data/sources/support/edits/<thread>.json` (an edited candidate skips the auditor, so it is your read of the quotes that counts). Nothing was run with --approve or --edit.
Pipeline fixes made during this run: Profile no longer rejects breadwinner_age_at_death with breadwinner_deceased=false (it crashed NFBS's behavioural tests).

## National Family Benefit Scheme (`nfbs`, thread `r-1b0f635fac`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `bpl eq true` quote: "The family of the applicant must be living Below Poverty Line (BPL)."
  - `breadwinner_deceased eq true` quote: "The primary breadwinner of the applicant's family must have been deceased."
  - `breadwinner_age_at_death gte 18` quote: "The age of the deceased breadwinner must have been more than 18 years and less than 60 years."
  - `breadwinner_age_at_death lte 60` quote: "The age of the deceased breadwinner must have been more than 18 years and less than 60 years."
- Auditor / validator notes:
  - auditor: rules[2] (breadwinner_age_at_death gte 18): Document says 'more than 18 years' (strictly greater than 18), but rule uses gte 18, which wrongly includes age exactly 18 -- source says: "The age of the deceased breadwinner must have been more than 18 yea
  - auditor: rules[3] (breadwinner_age_at_death lte 60): Document says 'less than 60 years' (strictly less than 60), but rule uses lte 60, which wrongly includes age exactly 60 -- source says: "The age of the deceased breadwinner must have been more than 18 years 
  - auditor: criterion in the source is covered by no rule or caveat: The applicant must be a citizen of India -- source says: "The applicant must be a citizen of India.". Add a rule if a Profile field can express it, otherwise add it to unmapped_criteria with thi
  - auditor: criterion in the source is covered by no rule or caveat: The applicant must be the succeeding primary breadwinner of the family -- source says: "The applicant must be the succeeding primary breadwinner of the family.". Add a rule if a Profile field ca
  - auditor: criterion in the source is covered by no rule or caveat: The family benefit will be paid to such surviving member of the household of the deceased poor, who after local inquiry, is found to be the head of the household -- source says: "The family bene
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Auditor is right: 'more than 18 and less than 60' is exclusive, the extractor wrote gte 18 / lte 60. Edit: breadwinner_age_at_death gte 19 and lte 59 (quote unchanged; the validator accepts the exclusive readings). bpl and breadwinner_deceased rules are faithful. Citizenship, 'succeeding breadwinner' and 'head of household' stay as caveats (not askable). Newly expressible thanks to breadwinner_deceased / breadwinner_age_at_death.

- Edit file: data/sources/support/edits/r-1b0f635fac.json

## Indira Gandhi National Disability Pension Scheme (`igndps`, thread `r-f97cb28ebe`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `age gte 18` quote: "The age of the applicant should be 18 years and above."
  - `disability_percentage gte 80` quote: "The applicant’s disability should be more than 80%."
  - `bpl eq true` quote: "The applicant should belong to the Below Poverty Line."
- Auditor / validator notes:
  - auditor: rules[1] (disability_percentage gte 80): Document says disability should be more than 80% (strictly greater than 80), but rule uses gte 80 which admits exactly 80% -- source says: "The applicant’s disability should be more than 80%."
  - auditor: rules[0] (age gte 18): Document states benefits are for Divyangjan between 18-79 years (Rs.300) and aged 80 years and above (Rs.500); rules capture only a lower bound of 18 and omit the upper age limit of 79 for the Rs.300 pension tier -- source says:
  - auditor: rules[2] (bpl eq true): No rule captures the pension amount tiers (Rs.300 for 18-79, Rs.500 for 80+) which are part of benefit determination -- source says: "A pension of Rs.300/- per month is provided to Divyangjan between 18-79 years. A pension of R
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be 79 years or younger for the Rs.300 per month pension tier -- source says: "A pension of Rs.300/- per month is provided to Divyangjan between 18-79 years.". Add a rule if a Prof
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be 80 years or older for the Rs.500 per month pension tier -- source says: "A pension of Rs.500/- per month will be provided to Divyangjan aged 80 years and above.". Add a rule if
  - auditor: criterion in the source is covered by no rule or caveat: Disability must be more than 80% (strictly greater than 80, not equal to 80) -- source says: "The applicant’s disability should be more than 80%.". Add a rule if a Profile field can express it, 
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Source says 'more than 80%' (strict), extractor wrote gte 80. Edit: disability_percentage gte 81. age gte 18 and bpl are faithful (the Rs300 vs Rs500 age tiers are benefit amounts, not eligibility, kept as caveats). Note: the official scheme text elsewhere says 80% or more; we follow this source verbatim, so a person at exactly 80% is told not eligible, which the caveat should mention.

- Edit file: data/sources/support/edits/r-f97cb28ebe.json

## Pradhan Mantri Shram Yogi Maan-dhan (`pm-sym`, thread `r-493195266b`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `is_unorganised_worker eq true` quote: "The applicant must be an unorganized worker, construction workers, domestic workers, cobbler etc."
  - `age gte 18` quote: "The applicant must have an entry age between 18 and 40 years."
  - `age lte 40` quote: "The applicant must have an entry age between 18 and 40 years."
  - `monthly_income lte 15000` quote: "The applicant must have a monthly income of ₹15,000/- or less."
  - `has_bank_account eq true` quote: "The applicant must possess a Savings Bank Account or Jan Dhan account number with an Indian Financial System Code."
  - `is_current_income_tax_payer eq false` quote: "An income tax payer."
  - `is_epfo_esic_nps_member eq false` quote: "Holding membership in the Employees' Provident Fund Organization scheme. Holding membership in the National Pension Scheme. Holding membership in the Employees' State Insurance Corporation scheme."
- Auditor / validator notes:
  - auditor: rules[0] (is_unorganised_worker eq true): The document lists specific categories of eligible workers (unorganized worker, construction workers, domestic workers, cobbler etc.) but the rule only checks a generic is_unorganised_worker flag, which may no
  - auditor: rules[5] (is_current_income_tax_payer eq false): The document's exclusion is 'An income tax payer' (present tense, no year given), which matches is_current_income_tax_payer; however the document also lists separate exclusions for EPFO, NPS and ESIC me
  - auditor: rules[6] (is_epfo_esic_nps_member eq false): The document lists EPFO, NPS and ESIC membership as separate exclusions, but the rule combines them into a single field is_epfo_esic_nps_member, which may not match the document's distinct conditions. -- so
  - auditor: rules[6] (is_epfo_esic_nps_member eq false): The document's exclusion 'Not a member of NPS-Traders scheme' is not captured by any rule. -- source says: "Not a member of NPS-Traders scheme."
  - auditor: rules[6] (is_epfo_esic_nps_member eq false): The document's exclusion 'Engaged in the organized sector' is not captured by any rule; the available field in_regular_govt_employment does not cover organized sector employment generally. -- source says: "
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must not be engaged in the organized sector -- source says: "Engaged in the organized sector.". Add a rule if a Profile field can express it, otherwise add it to unmapped_criteria with
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must not be a member of NPS-Traders scheme -- source says: "Not a member of NPS-Traders scheme.". Add a rule if a Profile field can express it, otherwise add it to unmapped_criteria wi
  - ... plus 1 more of the same kind (uncovered criteria)
- Judgement: **APPROVE (rules faithful); needs edit only to clear auditor flags**
- Reason / exact edit: All 7 rules match their quotes: monthly_income lte 15000 (period now correct, previously 180000 on annual_income), age 18-40, bank account, is_current_income_tax_payer false ('An income tax payer' = present tense), EPFO/ESIC/NPS false, is_unorganised_worker true. The auditor's blockers are about the three exclusions sharing one field (they are ANDed, so 'not a member of any' is exactly right) and about uncovered organised-sector / NPS-Traders / IFSC exclusions, which are already unmapped caveats. The edit file only adds the missing unmapped quotes so the review passes (edited candidates skip the auditor).

- Edit file: data/sources/support/edits/r-493195266b.json

## Pradhan Mantri Kisan Maandhan Yojana (`pmkmdy`, thread `r-44b6ea78e4`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `owns_cultivable_land eq true` quote: "The applicant should be a Small or Marginal Farmer."
  - `land_holding_hectares lte 2` quote: "The applicant should have cultivable landholding up to 2 hectares as per State or Union Territory land records."
  - `age gte 18` quote: "The applicant should be between 18 and 40 years of age at the time of entry."
  - `age lte 40` quote: "The applicant should be between 18 and 40 years of age at the time of entry."
- Auditor / validator notes:
  - auditor: rules[2] (age gte 18): The rule captures age gte 18 but the document says 'between 18 and 40 years of age at the time of entry'; the upper bound lte 40 is present in rule 3, so both bounds are captured -- source says: "The applicant should be between 
  - auditor: rules[3] (age lte 40): The rule captures age lte 40 but the document says 'between 18 and 40 years of age at the time of entry'; both bounds are present across rules 2 and 3 -- source says: "The applicant should be between 18 and 40 years of age at th
  - auditor: candidate: The document lists multiple exclusion categories (e.g., covered under NPS/ESIC/EPFO, opted for PM-SYM/PM-VM, institutional landholders, constitutional post holders, ministers/MPs/MLAs/mayors/chairpersons, serving/retired government employee
  - auditor: candidate: The document requires the applicant to possess an Aadhaar card and have a savings bank account or PM-KISAN account; these are not encoded as rules -- source says: "The applicant should possess an Aadhaar card. The applicant should have a sa
  - auditor: criterion in the source is covered by no rule or caveat: Applicant's name must appear in land records as on 01.08.2019 -- source says: "The applicant's name should appear in land records as on 01.08.2019.". Add a rule if a Profile field can express it
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must possess an Aadhaar card -- source says: "The applicant should possess an Aadhaar card.". Add a rule if a Profile field can express it, otherwise add it to unmapped_criteria with t
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must have a savings bank account or PM-KISAN account -- source says: "The applicant should have a savings bank account or PM-KISAN account.". Add a rule if a Profile field can express 
  - ... plus 8 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Original 4 rules (small/marginal farmer = owns_cultivable_land, land_holding_hectares lte 2 'up to 2 hectares', age 18-40) are faithful. Edit adds three exclusions that the source states and a field now expresses: income_tax_payer_last_year false ('paid Income Tax in the last assessment year'), is_govt_employee false (quote excludes MTS/Class IV/Group D, matching the field), is_epfo_esic_nps_member false; and all other exclusions (constitutional posts, MPs, professionals, institutional landholders, PM-SYM opt-ins, land record on 01.08.2019, Aadhaar, bank or PM-KISAN account) as unmapped caveats.

- Edit file: data/sources/support/edits/r-44b6ea78e4.json

## Pradhan Mantri Fasal Bima Yojna (PMFBY) (`pmfby`, thread `r-04a0dd3cfc`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the document lists eligibility conditions (e.g., all farmers including tenant farmers and sharecroppers growing notified crops in notified areas, insurable interest, valid land ownership certificate or l
  - auditor: candidate: The document states PMFBY applies to notified areas and crop losses in non-notified areas are generally not covered; this geographic/area condition is missing from the rules and caveats. -- source says: "PMFBY applies to notified areas, and
  - auditor: candidate: The document requires farmers to apply within the prescribed time frame, usually within 2 weeks of the start of the sowing season; this time condition is missing from the rules. -- source says: "The farmer must apply for insurance coverage 
  - auditor: candidate: The document excludes farmers who fail to pay their premium contributions; this premium-payment condition is missing from the rules. -- source says: "Farmers who fail to pay their premium contributions as required may not be eligible for co
  - auditor: candidate: The document excludes losses resulting from farmer negligence or non-compliance with recommended agricultural practices; this condition is missing from the rules. -- source says: "Losses resulting from farmer negligence, non-compliance with
  - auditor: candidate: The document requires farmers to possess a valid and authenticated land ownership certificate or a valid land tenure agreement; this document/land condition is missing from the rules. -- source says: "Farmers must possess a valid and authen
  - auditor: candidate: The document requires the farmer to be a cultivator or sharecropper on the insured land; this condition is missing from the rules. -- source says: "The farmer must be a cultivator or sharecropper on the insured land."
  - ... plus 11 more of the same kind (uncovered criteria)
- Judgement: **FIX (low value) -> approve only if you accept a one-rule scheme**
- Reason / exact edit: Still no rules from the extractor. Edit adds occupation eq farmer ('All farmers, including tenant farmers and sharecroppers...'). Crop notification, area, sowing-window, land record/tenancy, premium and negligence conditions are unmapped caveats; a farmer will get 'eligible' with those caveats shown. Reject instead if you do not want eligible verdicts without crop/area checks.

- Edit file: data/sources/support/edits/r-04a0dd3cfc.json

## Pradhan Mantri Jan Dhan Yojana (`pmjdy`, thread `r-bbdf52a78f`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: The document states eligibility requires the applicant to be an Indian National, but no rule enforces citizenship; the rules engine has no citizenship field, so this criterion is entirely unchecked. -- source says: "The applicant should be 
  - auditor: candidate: The document states minors above ten years require support from legal guardians, but no rule enforces this; the rules engine has no guardian field, so this criterion is entirely unchecked. -- source says: "If minors above ten years apply, t
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be an Indian National -- source says: "The applicant should be an Indian National.". Add a rule if a Profile field can express it, otherwise add it to unmapped_criteria with this 
  - auditor: criterion in the source is covered by no rule or caveat: Minors above ten years require support from their legal guardians for administering their PMJDY account -- source says: "If minors above ten years apply, they will require support from their leg
- Judgement: **FIX -> approve (zero rules, caveats only)**
- Reason / exact edit: The source states no bank-account condition (I did NOT add has_bank_account=false: 'unbanked' appears only in the intro, not as an eligibility criterion). The only criteria are Indian national and guardian support for minors over ten, both unmapped. Edit = candidate plus those two caveats; a rule-less scheme is shown as eligible for everyone, which matches 'any Indian citizen'. Check that you are happy with a rule-less record.

- Edit file: data/sources/support/edits/r-bbdf52a78f.json

## PM Vishwakarma (`pmv`, thread `r-378966517a`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `occupation eq "artisan_craftsperson"` quote: "The applicant should be an artisan or craftsperson working with hands and tools."
  - `is_unorganised_worker eq true` quote: "The applicant should be engaged in an unorganized sector on a self-employment basis."
  - `age gte 18` quote: "On the date of registration for the scheme, the minimum age of the applicant should be 18 years."
  - `is_govt_employee eq false` quote: "A person in government service and their family members shall not be eligible."
- Auditor / validator notes:
  - auditor: rules[0] (occupation eq "artisan_craftsperson"): The document requires the applicant to be an artisan or craftsperson working with hands and tools AND engaged in one of 18 specific family-based traditional trades. The rule only checks occupation eq ar
  - auditor: rules[0] (occupation eq "artisan_craftsperson"): The document requires engagement in one of 18 family-based traditional trades, but no rule captures this trade-specific condition. -- source says: "The applicant should be engaged in one of the 18 famil
  - auditor: rules[1] (is_unorganised_worker eq true): The document requires engagement in the unorganized sector on a self-employment basis. The rule only checks is_unorganised_worker eq true, omitting the self-employment basis condition. -- source says: "The app
  - auditor: rules[2] (age gte 18): The document states minimum age should be 18 years on the date of registration, which means age must be at least 18. The rule captures gte 18 correctly, but there is no upper age limit in the document, so no issue there; however
  - auditor: rules[3] (is_govt_employee eq false): The exclusion applies to a person in government service AND their family members. The rule only checks the applicant's is_govt_employee eq false, omitting the family-member exclusion entirely. -- source says: "A p
  - auditor: candidate: No rule captures the condition that the applicant should not have availed loans under similar credit-based schemes of the Central Government or State Government for self-employment/business development in the past 5 years. -- source says: "
  - auditor: candidate: No rule captures the condition that registration and benefits shall be restricted to one member of the family. -- source says: "The registration and benefits under the Scheme shall be restricted to one member of the family."
  - ... plus 6 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit (weak)**
- Reason / exact edit: Rules (occupation artisan_craftsperson, is_unorganised_worker, age gte 18, is_govt_employee false) are faithful but incomplete: the 18 trades are not enumerated in the source (so no sub-list was possible), family-member government-service exclusion, 5-year loan history, one member per family and engaged-in-trade are unmapped. The govt-employee rule is applicant-only; the family clause is kept as a caveat, so an applicant with a government-employee relative still sees 'eligible' plus the caveat. Edit adds those unmapped quotes.

- Edit file: data/sources/support/edits/r-378966517a.json

## Stand-Up India (`sui`, thread `r-d741137669`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `social_category in ["sc", "st"]` quote: "If the applicant is a male, he must be from SC / ST category."
  - `age gte 18` quote: "The age of the applicant must be at least 18 years."
  - `is_current_income_tax_payer eq false` quote: "The applicant must not be in default to any bank/financial institution."
- Auditor / validator notes:
  - auditor: rules[0] (social_category in ["sc", "st"]): Rule requires SC/ST for all applicants, but the document only requires SC/ST for male applicants; women applicants are eligible regardless of category. The rule wrongly excludes women from general/OBC/EWS ca
  - auditor: rules[2] (is_current_income_tax_payer eq false): The rule substitutes 'income tax payer' for 'default to any bank/financial institution'. These are entirely different conditions; the rule wrongly excludes income tax payers and wrongly includes default
  - auditor: rules[0] (social_category in ["sc", "st"]): The rule omits the document's alternative eligibility path for women entrepreneurs (any category) and the 51% shareholding condition for non-individual enterprises. -- source says: "facilitating bank loans f
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must not be in default to any bank/financial institution -- source says: "The applicant must not be in default to any bank/financial institution.". Add a rule if a Profile field can ex
  - auditor: criterion in the source is covered by no rule or caveat: Finance is provided for Greenfield Enterprises only -- source says: "Finance is provided for Greenfield Enterprises.". Add a rule if a Profile field can express it, otherwise add it to unmapped_
  - auditor: criterion in the source is covered by no rule or caveat: Women entrepreneurs (any social category) are eligible -- source says: "at least one woman borrower per bank branch for setting up a greenfield enterprise.". Add a rule if a Profile field can ex
  - auditor: criterion in the source is covered by no rule or caveat: For non-individual enterprises, at least 51% shareholding and controlling stake must be held by SC/ST or Woman entrepreneur -- source says: "In case of non-individual enterprises, at least 51% o
- Judgement: **FIX -> approve after edit (extractor wrong twice)**
- Reason / exact edit: Extractor faked the men-only condition as 'social_category in sc/st' for everyone (auditor correct: women are eligible in any category) and mapped 'not in default to any bank' to is_current_income_tax_payer (a hallucinated mapping). The rule format has no conditional rules and no OR, so the men-only SC/ST condition cannot be a rule. Edit: keep only age gte 18 ('The age of the applicant must be at least 18 years.', applies to everyone), move the male SC/ST condition and the bank-default condition to unmapped.

- Edit file: data/sources/support/edits/r-d741137669.json

## PM Street Vendor’s AtmaNirbhar Nidhi (PM SVANidhi) (`pm-svanidhi`, thread `r-69af5e9e8e`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the document lists four categories of eligible street vendors (Certificate of Vending/Identity Card holders, surveyed-but-unissued vendors, vendors left out of survey or started vending after survey with
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be a street vendor in possession of Certificate of Vending / Identity Card issued by ULBs -- source says: "Street vendors in possession of Certificate of Vending / Identity Card i
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be a vendor identified in the survey but not issued Certificate of Vending / Identity Card -- source says: "The vendors, who have been identified in the survey but have not been i
  - auditor: criterion in the source is covered by no rule or caveat: Survey Reference Number (SRN) is mandatory for online application -- source says: "Enter "Survey Reference Number" (SRN) which is mandatory.". Add a rule if a Profile field can express it, other
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Extractor returned no rules (it kept the four vendor categories as one unmapped OR). All four categories are street vendors, so edit adds occupation eq street_vendor with the quote 'Street vendors in possession of Certificate of Vending / Identity Card issued by Urban Local Bodies (ULBs).' (necessary condition; certificate / LoR / SRN conditions stay unmapped, which is correct because a user cannot be expected to know them).

- Edit file: data/sources/support/edits/r-69af5e9e8e.json

## Pradhan Mantri Garib Kalyan Anna Yojana (`pm-gkay`, thread `r-1426813393`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the document lists specific eligibility categories (AAY and PHH families, AAY sub-criteria such as households headed by widows/terminally ill/disabled persons/persons aged 60+, primitive tribal household
  - auditor: candidate: The document states AAY families are identified by States/UTs as per Central Government criteria including households headed by widows or terminally ill persons or disabled persons or persons aged 60 years or more with no assured means of s
  - auditor: candidate: The document states AAY families include widows or terminally ill persons or disabled persons or persons aged 60 years or more or single women or single men with no family or societal support or assured means of subsistence; no rule capture
  - auditor: candidate: The document states all primitive tribal households are eligible; no rule captures social_category or tribal status. -- source says: "All primitive tribal households."
  - auditor: candidate: The document states landless agriculture labourers, marginal farmers, rural artisans/craftsmen, slum dwellers, and persons earning livelihood on daily basis in the informal sector are eligible; no rule captures occupation or these categorie
  - auditor: candidate: The document states all eligible Below Poverty Line families of HIV positive persons are eligible; no rule captures bpl or HIV status. -- source says: "All eligible Below Poverty Line families of HIV positive persons"
  - auditor: candidate: The document states PHH are identified by State Governments/UTs as per criteria evolved by them, meaning state-specific PHH criteria are not captured; no rule reflects this state-dependent eligibility. -- source says: "PHH are to be identif
  - ... plus 7 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: No rules extracted. Edit adds ration_card_type in [aay, phh] with the quote 'Families belonging to Antyodaya Anna Yojana (AAY) and Priority Households (PHH) categories will be eligible for the scheme.' Clean, exact; the AAY sub-criteria (widows, tribal households, ...) are state-identified and stay as unmapped caveats.

- Edit file: data/sources/support/edits/r-1426813393.json

## National Pension Scheme for Traders And Self Employed Persons (`nps-tsep`, thread `r-9a28e5a827`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `age gte 18` quote: "The applicant must be between 18 and 40 years of age."
  - `age lte 40` quote: "The applicant must be between 18 and 40 years of age."
  - `has_bank_account eq true` quote: "The applicant must possess a savings bank account in their name."
  - `is_epfo_esic_nps_member eq false` quote: "The applicant must not be covered under any National Pension Scheme contributed by the Central Government. The applicant must not be a member of the Employees’ Provident Fund Organisation (EPFO) under the Employees’ Provident Fund"
- Auditor / validator notes:
  - auditor: rules[3] (is_epfo_esic_nps_member eq false): The rule combines EPFO, ESIC and NPS into one field, but the document lists them as separate exclusions and also excludes PM-SYM members; the engine field cannot express 'not a member of EPFO/ESIC/NPS(Gover
  - auditor: rules[3] (is_epfo_esic_nps_member eq false): The document excludes income-tax payers/assessee, but no rule covers this exclusion; the candidate only lists it in unmapped_criteria/caveats, so the engine will not check it. -- source says: "The applicant
  - auditor: candidate: The document requires the applicant to be a Laghu Vyapari, self-employed person, shop owner, retail trader, rice mill owner, oil mill owner, workshop owner, commission agent, real estate broker, small hotel owner, or restaurant owner, but n
  - auditor: candidate: The document requires annual turnover not exceeding ₹1,50,00,000/-, but no rule checks turnover; the candidate only lists it in caveats. -- source says: "The applicant must have an annual turnover that does not exceed ₹1,50,00,000/-."
  - auditor: candidate: The document requires possession of an Aadhaar Card or Aadhaar Number, but no rule checks this; the candidate only lists it in caveats. -- source says: "The applicant must possess an Aadhaar Card or Aadhaar Number."
  - auditor: candidate: The document excludes applicants enrolled under the Pradhan Mantri Shram Yogi Maandhan Yojana, but no rule checks this; the candidate only lists it in caveats. -- source says: "The applicant must not be enrolled under the Pradhan Mantri Shr
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be a Laghu Vyapari, self-employed person, shop owner, retail trader, rice mill owner, oil mill owner, workshop owner, commission agent, real estate broker, small hotel owner, or r
  - ... plus 4 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Original rules (age 18-40, bank account, EPFO/ESIC/NPS false) are faithful. Edit adds is_current_income_tax_payer false ('not an income-tax payer or income-tax assessee') and occupation in [small_trader_shopkeeper, self_employed] (quote lists trader / self-employed / shop owner / mill owner ...). Turnover, Aadhaar, PM-SYM exclusion stay unmapped.

- Edit file: data/sources/support/edits/r-9a28e5a827.json

## Scheme Of Assistance To Disabled Persons For Purchase/Fitting Of Aids/Appliances (`sadppfaa`, thread `r-ca690db38c`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `disability_percentage gte 40` quote: "Holding a 40% Disability Certificate (Benchmark disability)."
  - `monthly_income lte 30000` quote: "Having monthly income from all sources not exceeding Rs.30,000/- per month."
- Auditor / validator notes:
  - auditor: rules[0] (disability_percentage gte 40): The document requires a 40% Disability Certificate (benchmark disability) for beneficiaries, but certain aids require higher disability percentages (80% and above for high-end prosthesis and motorized tricycles
  - auditor: rules[1] (monthly_income lte 30000): The document states monthly income from all sources must not exceed Rs. 30,000 per month, but for dependents, the income of parents/guardians must not exceed Rs. 30,000 per month. The rule does not distinguish betw
  - auditor: candidate: The document states beneficiaries must be an Indian citizen of any age, but no citizenship rule is captured. The engine has no citizenship field, so this is a missing criterion. -- source says: "An Indian citizen of any age."
  - auditor: candidate: The document states beneficiaries must not have received assistance during the last 3 years for the same purpose from any source (with an exception for children below 12 years where minimum time is one year). No rule captures this exclusion
  - auditor: candidate: The document specifies Cochlear Implant assistance ceilings of Rs. 7.00 lakh for children with pre-lingual hearing loss between 1 to 5 years and Rs. 6.00 lakh for children with acquired hearing loss between 5 to 18 years. No rule captures t
  - auditor: candidate: The document specifies Motorized tricycles and wheelchairs are provided to persons aged 16 years and above, once in five years, and persons with severe disabilities of 16 years and above having mental impairment shall not be eligible. No ru
  - auditor: candidate: The document specifies Accessible Mobile Phone for visually impaired students aged 18 years and above, once in five years, and Laptop, Braille Note Taker and Braille for school-going students with disability (class 10th and above), once in 
  - ... plus 17 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Rules disability_percentage gte 40 and monthly_income lte 30000 ('per month': period correct now, was 360000 annual) are faithful as eligibility ceilings. The 22,500 full-cost vs 30,000 half-cost tiers are benefit levels, kept as caveats with citizenship and 'no assistance in last 3 years'. Dependent income (parents/guardians) is not expressible. Edit adds those unmapped quotes.

- Edit file: data/sources/support/edits/r-ca690db38c.json

## Group Personal Accident Insurance Scheme For Coir Workers (`gpaiscw`, thread `r-460a69ccde`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `occupation eq "coir_worker"` quote: "Group Personal Accident Insurance Scheme For Coir Workers"
  - `age gte 14` quote: "If the applicant is a disabled coir worker, he/she should be at least 14 years in age."
  - `disability_percentage gte 40` quote: "If the applicant is a disabled coir worker, the percentage of disability should be at least 40%."
- Auditor / validator notes:
  - auditor: rules[0] (occupation eq "coir_worker"): The document says the applicant must be EITHER a disabled coir worker OR nominee of the disabled/deceased coir worker. The rule restricts eligibility to coir workers only, excluding nominees of disabled/deceased
  - auditor: rules[1] (age gte 14): The age condition applies only if the applicant is a disabled coir worker, not to nominees. The rule applies it unconditionally to all applicants. -- source says: "If the applicant is a disabled coir worker, he/she should be at 
  - auditor: rules[2] (disability_percentage gte 40): The disability percentage condition applies only if the applicant is a disabled coir worker, not to nominees. The rule applies it unconditionally to all applicants. -- source says: "If the applicant is a disabl
  - auditor: criterion in the source is covered by no rule or caveat: Applicant must be either a disabled coir worker OR nominee of the disabled/deceased coir worker -- source says: "The applicant must be EITHER a disabled coir worker OR nominee of the disabled/de
- Judgement: **REJECT**
- Reason / exact edit: The scheme is for EITHER a disabled coir worker OR a nominee of a disabled/deceased worker. The extractor's rules (coir_worker, age >= 14, disability >= 40) apply the worker-only conditions to nominees too, and no valid subset exists (a rule-less record would show 'eligible' to everyone). Not expressible without OR / conditional rules. No edit written.

## National Scheme Of Welfare Of Fishermen (`nswf`, thread `r-ee02b1e95e`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the engine will evaluate an empty rule set and cannot enforce any eligibility condition from the document. -- source says: "Eligibility Criteria for Inland Fishermen"
  - auditor: candidate: The document sets an age limit for inland fishermen (below 60 years) but no rule captures it. -- source says: "The age of fishermen must be below 60 years old."
  - auditor: candidate: The document requires inland fishermen to belong to the BPL category, but no rule captures it. -- source says: "Applicant fishermen must belong to the BPL (Below Poverty Line) category."
  - auditor: candidate: The document requires inland fishermen to be engaged in full-time activities inland, but no rule captures it. -- source says: "They must be engaged in full-time activities inland."
  - auditor: candidate: The document requires marine fishermen to be officially licensed by States/UTs, but no rule captures it. -- source says: "Their respective States and Union Territories must officially license marine fishermen."
  - auditor: candidate: The document requires marine fishermen to operate under State, Union Territories, and FISHCOPFED, but no rule captures it. -- source says: "All marine fishermen who operate under State, Union Territories, and FISHCOPFED are eligible for thi
  - auditor: candidate: The document requires marine fishermen to involve themselves in full-time activities at sea, but no rule captures it. -- source says: "They must involve themselves in full-time activities at sea."
  - ... plus 10 more of the same kind (uncovered criteria)
- Judgement: **FIX (weak) -> approve only as an info record**
- Reason / exact edit: No rules extracted. Edit adds occupation eq fisherman (coastal licensed fishermen quote). Age below 60, BPL and full-time fishing apply to INLAND fishermen only (conditional) so they stay unmapped. Eligible = any fisherman, with 26 caveats; acceptable only because caveats are shown with the verdict.

- Edit file: data/sources/support/edits/r-ee02b1e95e.json

## Central Sector Scheme for Rehabilitation of Bonded Labourer (`cssrbl`, thread `r-35e7da5a02`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the only eligibility condition in the document (being a rescued bonded labourer) is missing, so the engine cannot evaluate anyone -- source says: "The beneficiary should be a rescued bonded labour."
  - auditor: criterion in the source is covered by no rule or caveat: The beneficiary must be a rescued bonded labourer -- source says: "The beneficiary should be a rescued bonded labour.". Add a rule if a Profile field can express it, otherwise add it to unmapped
- Judgement: **REJECT**
- Reason / exact edit: Only criterion is being a rescued bonded labourer: no profile field, and not self-assessable (rescue is a state process). A rule-less record would tell every user they are eligible. No edit written.

## Pradhan Mantri Awaas Yojana - Gramin (`pmay-g`, thread `r-c989648db3`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - none
- Auditor / validator notes:
  - auditor: candidate: No eligibility rules were extracted; the document contains explicit exclusion criteria (e.g., pucca house ownership, government employee, income above Rs.10,000/month, paying income tax, land ownership thresholds) that would wrongly qualify
  - auditor: candidate: The automatic exclusion 'Any member of the family earning more than Rs.10,000 per month' is not captured as a rule -- source says: "Any member of the family earning more than Rs.10,000 per month"
  - auditor: candidate: The automatic exclusion 'Household with any member as a Government employee' is not captured as a rule -- source says: "Household with any member as a Government employee"
  - auditor: candidate: The automatic exclusion 'Paying income tax' is not captured as a rule -- source says: "Paying income tax"
  - auditor: candidate: The automatic exclusion 'Paying professional tax' is not captured as a rule -- source says: "Paying professional tax"
  - auditor: candidate: The automatic exclusion 'Own a refrigerator' is not captured as a rule -- source says: "Own a refrigerator"
  - auditor: candidate: The automatic exclusion 'Own a landline phone' is not captured as a rule -- source says: "Own a landline phone"
  - ... plus 27 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Extractor produced zero rules this time. Edit adds house_type in [kutcha, none_homeless] (universe quote: houseless households in kutcha houses), is_govt_employee false ('Household with any member as a Government employee') and is_current_income_tax_payer false ('Paying income tax') as necessary conditions. NOT mapped (correctly): 'any member earning more than Rs.10,000 per month' is per EARNING MEMBER, not household or per-capita, so neither annual_income nor per_capita_monthly_income may carry it (this was the old period error); SECC listing, number of rooms, acre/irrigation exclusions (acres, not hectares), refrigerator, landline, vehicles, KCC, professional tax. 35 unmapped caveats.

- Edit file: data/sources/support/edits/r-c989648db3.json

## Pradhan Mantri Awas Yojana - Urban (`pmay-u`, thread `r-5f7b25ccbd`)

- Status: before `needs fix` (old profile) -> after `needs_human_fix` (3 attempts)
- Rules (extractor output):
  - `annual_income lte 300000` quote: "EWS: households with annual income up to ₹ 3,00,000."
  - `has_pucca_house eq false` quote: "The applicant or his/her family members must not be owning a pucca house in any part of the country."
- Auditor / validator notes:
  - auditor: rules[0] (annual_income lte 300000): The rule restricts eligibility to EWS only (annual_income lte 300000), but the document defines four income categories (EWS up to 3,00,000; LIG 3,00,001 to 6,00,000; MIG-1 6,00,001 to 12,00,000; MIG-2 12,00,001 to 
  - auditor: rules[1] (has_pucca_house eq false): The rule checks only whether the applicant owns a pucca house, but the document requires that neither the applicant nor his/her family members own a pucca house in any part of the country. The profile field has_puc
  - auditor: candidate: The document requires the family to comprise of husband/wife and unmarried children, but no rule captures this family composition condition. -- source says: "The family must comprise of husband/wife and unmarried children."
  - auditor: candidate: The document requires that the town/city in which the family resides must be covered under the scheme, but no rule captures this geographic coverage condition. -- source says: "The town/city in which the family resides must be covered under
  - auditor: candidate: The document requires that the family MUST NOT have previously availed benefits of any housing-related schemes set up by the Government of India, but no rule captures this exclusion condition. -- source says: "The family MUST NOT have previ
  - auditor: candidate: The document states all eligible beneficiaries should have an Aadhaar/Aadhaar Virtual ID, but no rule captures this mandatory identity requirement. -- source says: "All eligible beneficiaries under all components of the scheme should have a
  - auditor: candidate: The document states the Mission covers the entire urban area consisting of Statutory Towns, Notified Planning Areas, Development Authorities, Special Area Development Authorities, Industrial Development Authorities or any such authority und
  - ... plus 9 more of the same kind (uncovered criteria)
- Judgement: **FIX -> approve after edit**
- Reason / exact edit: Extractor's annual_income lte 300000 is EWS only; source has four bands up to 18,00,000 (MIG-2), so the scheme-wide ceiling is annual_income lte 1800000 (quote: MIG-2 line, 'annual' matches the field). has_pucca_house false is faithful for the applicant (family clause stays caveat). Previously zero rules; band, family composition, town coverage, prior housing benefit and Aadhaar stay unmapped.

- Edit file: data/sources/support/edits/r-5f7b25ccbd.json

## Summary

- Approve (rules faithful): pm-sym (via edit to add caveats).
- Fix then approve: nfbs, igndps, pmkmdy, pmjdy, pmv, sui, pm-svanidhi, pm-gkay, nps-tsep, sadppfaa, pmay-g, pmay-u.
- Fix, weak/low value (your call): pmfby, nswf.
- Reject: gpaiscw (EITHER/OR with nominees), cssrbl (not self-assessable).
- Not run: ab-pmjay (render timeout, no snapshot), unchanged from the first run.
