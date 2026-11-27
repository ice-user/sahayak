# Support-scheme candidates: review (2026-11-28)

Run: 15 central myscheme pages, model nvidia/nemotron-3.5-super-vl-120b-a12b, separate state DB (research/.state/support.sqlite).
Result: 0 ready for review, 15 needs fix, 0 failed. Nothing approved or merged. Tokens: 528,503 (85 LLM calls).
Not snapshotted: Ayushman Bharat PM-JAY (ab-pmjay): myscheme page render timed out 3 times, no snapshot, not researched.
Not found on myscheme (central list): Annapurna Scheme (NSAP), e-Shram, other NSAP central pages beyond NFBS / IGNDPS (IGNOAPS, IGNWPS already in schemes.json).
Already in schemes.json (skipped): IGNOAPS, IGNWPS, APY, PMJJBY, PMSBY, PM-KISAN, PMUY, SSY, PMMVY, PM-JAY senior.
Left to other agent: PMAY-G, PMAY-U, DAY-NULM shelters.

Current Profile fields: age, gender, state, marital_status, bpl, annual_income, ever_income_tax_payer, income_tax_payer_last_year, has_bank_account, owns_cultivable_land, is_govt_employee, monthly_pension, household_has_lpg, pregnant_or_lactating, in_regular_govt_employment, children.

## Ready for review
None.

## Needs fix (blocking reasons; judgement = reject as-is / fix by hand)

| Scheme (slug) | Blocking reasons | Missing profile field the cause? | Judgement |
|---|---|---|---|
| NFBS (nfbs) | Only rule is bpl=true. Dropped: breadwinner death, deceased aged 18-60, applicant is household head (all stayed as unmapped caveats). | Yes: household_breadwinner_deceased / deceased_age. | Fix: keep bpl rule + caveats; the scheme is a one-time benefit, state needs checking. Not approvable as an engine-checked scheme today. |
| IGNDPS (igndps) | Rules age>=18 + bpl. Missing: disability, >80% disability threshold (source), pension tier at 80+. | Yes: disability_percentage. | Reject until disability_percentage exists; then fix (age 18+, bpl, disability>=80). |
| PM-SYM (pm-sym) | Rules age 18-40, income <=180000 (source is Rs 15,000/month), ever_income_tax_payer=false (wrong: source says current payer), has_bank_account. Missing: unorganised worker, not in EPFO/ESIC/NPS. | Yes: is_unorganised_worker (+ monthly_income, epfo_member). | Fix: use income_tax_payer_last_year, monthly income as 15000*12 is acceptable only if the engine documents it; needs unorganised-worker field. |
| PM Kisan Maan-dhan (pmkmdy) | Rules age 18-40 only. Missing: cultivable land up to 2 ha, land in records at 1 Aug 2019, not in other pension/EPFO/NPS. | Yes: land_holding_hectares (owns_cultivable_land is too coarse), is_farmer. | Reject until land_holding_hectares; then fix. |
| PMFBY (pmfby) | No rules; 16 blockers. Needs farmer/cultivator/sharecropper, land record or tenure agreement, notified crop/area, apply before cut-off. | Yes: is_farmer / cultivator_type, crop_notified (seasonal, not profile-friendly). | Reject; keep as info-only caveats, or add owns_cultivable_land rule by hand. |
| PMJDY (pmjdy) | No rules. Only uncovered: Indian national and minors >10 need guardian. | No (citizenship assumed). Benefit is for people without a bank account: has_bank_account=false rule is expressible. | Fix easily: add has_bank_account eq false (source says bank account for the unbanked) + age>=10 caveat. Likely approvable after a 1-minute edit; verify quote. |
| PM Vishwakarma (pmv) | Rules age>=18, in_regular_govt_employment=false (source also excludes family members). Missing: artisan in one of 18 trades, unorganised, self-employed. | Yes: occupation / trade, is_unorganised_worker. | Fix: add caveat for family-member exclusion; needs occupation field. |
| Stand-Up India (sui) | Rule age>=18 applied to everyone (source: age only for men; women of any... also needs SC/ST or woman). Missing: SC/ST or woman, greenfield enterprise, non-defaulter. | Yes: caste_category / social_category (gender exists), business_type. | Reject until category field; then fix (gender=female OR category in SC/ST). |
| PM SVANidhi (pm-svanidhi) | Single blocker: benefits[7] quote not verbatim (94/100 match). Rules empty. | Yes for rules: is_street_vendor, vending certificate. | Fix: drop/fix the benefits[7] quote (trivial); add a street-vendor field. Closest to ready of all 15 on mechanics. |
| PM-GKAY (pm-gkay) | No rules. Needs AAY or PHH ration-card category (state-identified). | Yes: ration_card_type (AAY/PHH/none). | Reject as-is; fix once ration_card_type exists (or bpl as a proxy, but that is a loose approximation). |
| NPS-Traders (nps-tsep) | Rules age 18-40, bank account, income_tax_payer_last_year=false (source: not an income-tax payer at all). Uncovered: turnover <= Rs 1.5 crore, not EPFO/NPS/ESIC member. | Yes: is_self_employed/trader, annual_turnover, epfo_member. | Fix: use current-tax-payer wording; needs occupation + turnover. |
| ADIP (sadppfaa) | Rule annual_income<=360000 from Rs 30,000/month; source has full-cost to 22,500 and part-cost to 30,000 tiers; missing 40% disability certificate and no assistance in last 3 years. | Yes: disability_percentage. | Reject until disability_percentage; then fix with income note. |
| Coir workers accident insurance (gpaiscw) | No rules. Needs coir worker (or nominee), age>=14, disability >=40% for disablement claim. | Yes: occupation (coir worker), disability_percentage. | Reject; niche, low value. |
| Fishermen welfare (nswf) | No rules; 19 blockers. Inland fishermen under 60, BPL, full-time fishing. | Yes: occupation (fisherman). | Reject; fix with occupation=fisherman + age<60 + bpl. |
| Bonded labour rehabilitation (cssrbl) | No rules; only blocker: rescued bonded labourer. | Yes: occupation/special status. | Reject; state-run rescue process, not self-assessed. |

## Approve recommendations
None right now. Closest to approvable after a trivial hand edit (no new profile field): PMJDY (add has_bank_account eq false), PM SVANidhi (fix one quote, but rule-less without a street-vendor field).

## Ranked profile fields that would unlock the most schemes
1. disability_percentage (or disability status): IGNDPS, ADIP, coir workers (3)
2. occupation (trade/worker/fisherman/artisan/street vendor/self-employed): PM Vishwakarma, PM SVANidhi, NPS-Traders, NSWF, coir, PM-SYM, bonded labour (7)
3. is_unorganised_worker (+ epfo/esic/nps_member flag): PM-SYM, PM Vishwakarma, NPS-Traders, PMKMDY (4)
4. land_holding_hectares / is_farmer: PM Kisan Maan-dhan, PMFBY (2)
5. social_category (SC/ST/OBC): Stand-Up India (and many scholarship schemes)
6. ration_card_type (AAY/PHH): PM-GKAY
7. monthly_income (engine lacks monthly unit): PM-SYM, ADIP
8. household_breadwinner_deceased: NFBS
