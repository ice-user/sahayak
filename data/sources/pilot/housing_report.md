# Housing schemes: research pipeline report (2026-11-28)

Model: nvidia/nemotron-3.5-super-vl-120b-a12b (extractor and auditor). Sources: rendered myscheme.gov.in snapshots
(data/sources/myscheme/pmay-g.txt and pmay-u.txt), run with
`python -m research batch data/sources/pilot/housing_urls.txt --snapshots data/sources/myscheme`.
Nothing was approved or merged. data/schemes.json is unchanged.

## Summary

| Source | Scheme | Thread | Result |
|---|---|---|---|
| https://www.myscheme.gov.in/schemes/pmay-g | Pradhan Mantri Awaas Yojana - Gramin (`pradhan_mantri_awaas_yojana_gramin`) | `r-c989648db3` | needs human fix: 3 rules extracted (govt employee, income, income tax), 27 blocking auditor findings, 3 attempts |
| https://www.myscheme.gov.in/schemes/pmay-u | Pradhan Mantri Awas Yojana - Urban (`pradhan_mantri_awas_yojana_urban`) | `r-5f7b25ccbd` | needs human fix: 0 rules extracted (all conditions kept as caveats), 16 blocking auditor findings, 3 attempts |
| DAY-NULM Shelter for Urban Homeless (central) | not run | none | no central page exists in data/sources/myscheme_urls.txt (see below) |

Batch: 2 sources, wall time 120 s, 10 LLM calls (extractor plus auditor), 102,553 tokens. Every quote was found in the source text (PMAY-U: 34/34).

Why neither is ready: both schemes depend on facts the Profile cannot express (kutcha or pucca house, number of rooms, SECC listing,
family structure, prior housing benefit, urban area coverage). The auditor correctly flags those as missing rules; a human has to decide
whether to model them (new Profile fields) or accept them as caveats. PMAY-G's three extracted rules are also doubtful:
`annual_income lte 120000` rewrites "any member earning more than Rs.10,000 per month" (a per-member, per-month test) as a household
annual figure, and `ever_income_tax_payer` is "ever" while the source says "paying". PMAY-U extracted no rules because its criteria are
income bands (EWS/LIG/MIG), which are benefit tiers rather than eligibility cut-offs.

## DAY-NULM Shelter for Urban Homeless

data/sources/myscheme_urls.txt has only state variants, all tagged state:Uttarakhand: `daynulmsuh` (shelter for urban homeless),
`daynulmshguk` and `daynulsepuk`. There is no central page, so nothing was run. Shelters are covered in the app by the verified
help resource `urban_shelter_suh` in data/help_resources.json (official MoHUA pages) instead.

## Review panel: PMAY-G (thread r-c989648db3)

```
┌──────────────────────── review: thread r-c989648db3 ────────────────────────┐
│ STATUS: needs_human_fix   source:                                           │
│ https://www.myscheme.gov.in/schemes/pmay-g   LLM attempts: 3                │
│                                                                             │
│ BLOCKING ERRORS (cannot approve until fixed; use --edit or --reject;        │
│ URL-only errors can also be approved with --allow-url):                     │
│   x auditor: rules[1] (annual_income lte 120000): Document says any member  │
│ earning more than Rs.10,000 per month is excluded; rule uses annual_income  │
│ lte 120000 which is mathematically equivalent but the field is              │
│ annual_income and the document states per month, so the unit mapping is     │
│ ambiguous and could misread the limit; also the rule only checks one income │
│ condition while the document lists 13 automatic exclusion parameters, any   │
│ one of which excludes. -- source says: "Any member of the family earning    │
│ more than Rs.10,000 per month"                                              │
│   x auditor: rules[2] (ever_income_tax_payer eq false): Document says       │
│ 'Paying income tax' is an automatic exclusion parameter; rule uses          │
│ ever_income_tax_payer which captures lifetime status rather than            │
│ current/paying status, potentially excluding people who paid in the past    │
│ but not now, or including people who pay now but never before. -- source    │
│ says: "Paying income tax"                                                   │
│   x auditor: candidate: The document lists 13 automatic exclusion           │
│ parameters; rules cover only 3 (government employee, income >               │
│ Rs.10,000/month, income tax). Missing exclusions include: mechanised        │
│ agricultural equipment, Kisan Credit Card >= Rs.50,000, non-agricultural    │
│ enterprises registered with Government, professional tax payer,             │
│ refrigerator owner, landline phone owner, and land ownership thresholds     │
│ (2.5 acres irrigated with equipment, 5 acres irrigated for two+ crop        │
│ seasons, 7.5 acres with equipment). -- source says: "From the remaining set │
│ of households, all households fulfilling any one of the 13 parameters       │
│ listed below are automatically excluded:- 1. Motorised two/three/four       │
│ wheeler/ fishing boat 2. Mechanised three/four-wheeler agricultural         │
│ equipment 3. Kisan Credit Card with a credit limit of Rs.50,000 or above 4. │
│ Household with any member as a Government employee 5. Households with       │
│ non-agricultural enterprises registered with the Government 6. Any member   │
│ of the family earning more than Rs.10,000 per month 7. Paying income tax 8. │
│ Paying professional tax 9. Own a refrigerator 10. Own a landline phone 11.  │
│ Own 2.5 acres or more of irrigated land with at least one irrigation        │
│ equipment 12. 5 acres or more of irrigated land for two or more crop        │
│ seasons 13. Owning at least 7.5 acres of land or more with at least one     │
│ irrigation equipment"                                                       │
│   x auditor: candidate: The document states the universe of eligible        │
│ beneficiaries includes houseless households living in zero, one, or         │
│ two-room houses with kutcha walls and kutcha roofs (per SECC data, subject  │
│ to exclusion). No rule captures housing type (kutcha walls/roofs), number   │
│ of rooms (zero/one/two), or houseless status. -- source says: "The universe │
│ of eligible beneficiaries under PMAY-G will include all the houseless       │
│ households living in zero, one, or two-room houses with kutcha walls and    │
│ kutcha roofs (as per SECC data, and subject to the exclusion process)."     │
│   x auditor: candidate: The document states all households living in houses │
│ with pucca roofs and/or pucca walls and households living in houses with    │
│ more than 2 rooms are filtered out. No rule captures pucca roof/wall or     │
│ room count exclusion. -- source says: "All households living in houses with │
│ pucca roofs and/or pucca walls and households living in houses with more    │
│ than 2 rooms are filtered out."                                             │
│   x auditor: candidate: The document states beneficiaries are identified    │
│ using SECC parameters and verified by Gram Sabhas. No rule captures         │
│ SECC-based identification or Gram Sabha verification. -- source says:       │
│ "Beneficiaries are identified using the Socio-Economic and Caste Census     │
│ (SECC) parameters and verified by the Gram Sabhas."                         │
│   x auditor: candidate: The document lists automatic/compulsory inclusion   │
│ criteria (households without shelter, destitute/living on alms, manual      │
│ scavengers, Primitive Tribal Groups, legally released bonded laborer) and   │
│ prioritisation criteria (no adult member 16-59, female-headed with no adult │
│ male 16-59, no literate adult above 25, disabled member with no able-bodied │
│ adult, landless manual casual labor, etc.). No rules capture these          │
│ inclusion/prioritisation conditions. -- source says: "Criteria for          │
│ Automatic/Compulsory Inclusion - 1. Households without shelter 2.           │
│ Destitute/ living on alms 3. Manual scavengers 4. Primitive Tribal Groups   │
│ 5. Legally released bonded laborer"                                         │
│   x auditor: candidate: The document lists tie-breaker parameters (widows   │
│ and next-of-kin of defence/paramilitary/police killed in action,            │
│ leprosy/cancer/HIV, single girl child, Forest Rights Act beneficiaries,     │
│ transgender persons). No rules capture these. -- source says: "i.           │
│ Households with widows and next-of-kin of members of                        │
│ defence/paramilitary/police forces killed in action. ii. Households where a │
│ member is suffering from leprosy or cancer and People living with HIV       │
│ (PLHIV). iii. Households with a single girl child. iv. Beneficiary families │
│ of the Scheduled Tribes and Other Traditional Forest Dwellers (Recognition  │
│ of Forest Rights) Act, 2006, commonly known as the Forest Rights Act. v.    │
│ Transgender persons."                                                       │
│   x auditor: candidate: The document lists earmarking targets for SC/ST     │
│ (60%), Minorities (15%), and PwDs (3%). No rules capture these              │
│ category-based earmarking conditions. -- source says: "60% of the target    │
│ allocated to each State/ UT should be earmarked for SC/STs, subject to the  │
│ availability of eligible beneficiaries. ... Further, as far as possible,    │
│ 15% of the total fund would be earmarked for Minorities at the National     │
│ Level for households. ... the States to the extent possible, may ensure     │
│ that 3% of beneficiaries at the State Level are from among persons with     │
│ disabilities."                                                              │
│   x auditor: candidate: The document states PMAY-G has been extended till   │
│ 31st March 2024. No rule captures this end date / duration condition. --    │
│ source says: "PMAY-G has been extended for another two years, i.e. till     │
│ 31st March 2024."                                                           │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Applicant household must be houseless or living in zero, one, or two-room   │
│ house with kutcha walls and kutcha roofs (per SECC data) -- source says:    │
│ "The universe of eligible beneficiaries under PMAY-G will include all the   │
│ houseless households living in zero, one, or two-room houses with kutcha    │
│ walls and kutcha roofs (as per SECC data, and subject to the exclusion      │
│ process).". Add a rule if a Profile field can express it, otherwise add it  │
│ to unmapped_criteria with this quote.                                       │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Households living in pucca roofs and/or pucca walls, or more than 2 rooms,  │
│ are excluded -- source says: "All households living in houses with pucca    │
│ roofs and/or pucca walls and households living in houses with more than 2   │
│ rooms are filtered out.". Add a rule if a Profile field can express it,     │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Household with any member as a Government employee is automatically         │
│ excluded -- source says: "Household with any member as a Government         │
│ employee". Add a rule if a Profile field can express it, otherwise add it   │
│ to unmapped_criteria with this quote.                                       │
│   x auditor: criterion in the source is covered by no rule or caveat: Any   │
│ member of the family earning more than Rs.10,000 per month is automatically │
│ excluded -- source says: "Any member of the family earning more than        │
│ Rs.10,000 per month". Add a rule if a Profile field can express it,         │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Paying income tax is an automatic exclusion -- source says: "Paying income  │
│ tax". Add a rule if a Profile field can express it, otherwise add it to     │
│ unmapped_criteria with this quote.                                          │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Paying professional tax is an automatic exclusion -- source says: "Paying   │
│ professional tax". Add a rule if a Profile field can express it, otherwise  │
│ add it to unmapped_criteria with this quote.                                │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning a refrigerator is an automatic exclusion -- source says: "Own a      │
│ refrigerator". Add a rule if a Profile field can express it, otherwise add  │
│ it to unmapped_criteria with this quote.                                    │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning a landline phone is an automatic exclusion -- source says: "Own a    │
│ landline phone". Add a rule if a Profile field can express it, otherwise    │
│ add it to unmapped_criteria with this quote.                                │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning motorised two/three/four wheeler or fishing boat is an automatic     │
│ exclusion -- source says: "Motorised two/three/four wheeler/ fishing boat". │
│ Add a rule if a Profile field can express it, otherwise add it to           │
│ unmapped_criteria with this quote.                                          │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning mechanised three/four-wheeler agricultural equipment is an automatic │
│ exclusion -- source says: "Mechanised three/four-wheeler agricultural       │
│ equipment". Add a rule if a Profile field can express it, otherwise add it  │
│ to unmapped_criteria with this quote.                                       │
│   x auditor: criterion in the source is covered by no rule or caveat: Kisan │
│ Credit Card with credit limit of Rs.50,000 or above is an automatic         │
│ exclusion -- source says: "Kisan Credit Card with a credit limit of         │
│ Rs.50,000 or above". Add a rule if a Profile field can express it,          │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Households with non-agricultural enterprises registered with the Government │
│ are automatically excluded -- source says: "Households with                 │
│ non-agricultural enterprises registered with the Government". Add a rule if │
│ a Profile field can express it, otherwise add it to unmapped_criteria with  │
│ this quote.                                                                 │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning 2.5 acres or more of irrigated land with at least one irrigation     │
│ equipment is an automatic exclusion -- source says: "Own 2.5 acres or more  │
│ of irrigated land with at least one irrigation equipment". Add a rule if a  │
│ Profile field can express it, otherwise add it to unmapped_criteria with    │
│ this quote.                                                                 │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning 5 acres or more of irrigated land for two or more crop seasons is an │
│ automatic exclusion -- source says: "5 acres or more of irrigated land for  │
│ two or more crop seasons". Add a rule if a Profile field can express it,    │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Owning at least 7.5 acres of land or more with at least one irrigation      │
│ equipment is an automatic exclusion -- source says: "Owning at least 7.5    │
│ acres of land or more with at least one irrigation equipment". Add a rule   │
│ if a Profile field can express it, otherwise add it to unmapped_criteria    │
│ with this quote.                                                            │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Beneficiaries identified using SECC parameters and verified by Gram Sabhas  │
│ -- source says: "Beneficiaries are identified using the Socio-Economic and  │
│ Caste Census (SECC) parameters and verified by the Gram Sabhas.". Add a     │
│ rule if a Profile field can express it, otherwise add it to                 │
│ unmapped_criteria with this quote.                                          │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Scheme valid only till 31st March 2024 -- source says: "PMAY-G has been     │
│ extended for another two years, i.e. till 31st March 2024.". Add a rule if  │
│ a Profile field can express it, otherwise add it to unmapped_criteria with  │
│ this quote.                                                                 │
│                                                                             │
│ Auditor (nvidia/nemotron-3.5-super-vl-120b-a12b): 27 blocking finding(s) on │
│ the latest attempt, 7 warning(s), 0 dropped (quote not in source).          │
│ Auditor notes (independent second reading of the source; judge each         │
│ yourself):                                                                  │
│   ? auditor: rules[0] (is_govt_employee eq false): Document says 'Household │
│ with any member as a Government employee' is excluded; rule uses            │
│ is_govt_employee which may refer to the applicant only, not any household   │
│ member. -- source says: "Household with any member as a Government          │
│ employee"                                                                   │
│   ? auditor: candidate: The benefit amount is stated as ₹1,20,000 for plain │
│ areas and ₹1,30,000 for hilly/difficult/IAP districts, but no rule or field │
│ captures the amount or the area-type distinction. -- source says:           │
│ "Financial Assistance of ₹ 1,20,000 per unit for plain areas; and ₹         │
│ 1,30,000 per unit for hilly areas, difficult areas, and IAP districts       │
│ (Himalayan states, North-Eastern states, and Union Territories of Jammu &   │
│ Kashmir)."                                                                  │
│   ? auditor: candidate: The document states loan of up to ₹70,000 at 3%     │
│ lower interest rate, with maximum principal for subsidy of ₹2,00,000. No    │
│ rule or field captures these loan/subsidy amounts. -- source says: "A       │
│ willing beneficiary can avail of institutional finance (loan) of up to ₹    │
│ 70,000 at 3% lower interest rate, to build a permanent house. The maximum   │
│ principal amount for which subsidy can be sought is ₹ 2,00,000."            │
│   ? auditor: candidate: The document states minimum house size of 25 sq m   │
│ including dedicated area for hygienic cooking. No rule or field captures    │
│ this. -- source says: "The minimum size of the house shall be is 25 sq m    │
│ including a dedicated area for hygienic cooking."                           │
│   ? auditor: candidate: The document states toilet construction assistance  │
│ of up to ₹12,000 in convergence with SBM-G. No rule or field captures this. │
│ -- source says: "In convergence with Swachh Bharat Mission-Gramin (SBM-G),  │
│ the beneficiaries get financial assistance of up to ₹ 12,000 for the        │
│ construction of toilets."                                                   │
│   ? auditor: candidate: The document states MGNREGA unskilled labor         │
│ employment at ₹90.95 per day for 95 days. No rule or field captures this.   │
│ -- source says: "In convergence with MGNREGA, the beneficiary is entitled   │
│ to employment as unskilled labor (Rural Mason Training) at ₹ 90.95 per day  │
│ for 95 days."                                                               │
│   ? auditor: candidate: The document states one LPG connection per house in │
│ convergence with Pradhan Mantri Ujjwala Yojana. No rule or field captures   │
│ this. -- source says: "In convergence with Pradhan Mantri Ujjwala Yojana,   │
│ one LPG connection per house is provided."                                  │
│                                                                             │
│ NEW scheme: Pradhan Mantri Awaas Yojana - Gramin                            │
│ [pradhan_mantri_awaas_yojana_gramin]                                        │
│   ministry: Ministry Of Rural Development   category: housing               │
│   summary:  PMAY-G aims at providing a pucca house, with basic amenities,   │
│ to all houseless households and those households living in kutcha and       │
│ dilapidated house in rural areas of India.                                  │
│   benefits: Financial Assistance of ₹ 1,20,000 per unit for plain areas;    │
│ and ₹ 1,30,000 per unit for hilly areas, difficult areas, and IAP districts │
│ (Himalayan states, North-Eastern states, and Union Territories of Jammu &   │
│ Kashmir). A willing beneficiary can avail of institutional finance (loan)   │
│ of up to ₹ 70,000 at 3% lower interest rate, to build a permanent house.    │
│ The maximum principal amount for which subsidy can be sought is ₹ 2,00,000. │
│ The minimum size of the house shall be is 25 sq m including a dedicated     │
│ area for hygienic cooking. In convergence with Swachh Bharat Mission-Gramin │
│ (SBM-G), the beneficiaries get financial assistance of up to ₹ 12,000 for   │
│ the construction of toilets. In convergence with MGNREGA, the beneficiary   │
│ is entitled to employment as unskilled labor (Rural Mason Training) at ₹    │
│ 90.95 per day for 95 days. In convergence with Pradhan Mantri Ujjwala       │
│ Yojana, one LPG connection per house is provided.                           │
│                                                                             │
│ Rules (checked by the engine) with evidence:                                │
│   * is_govt_employee eq false   -- Household with any member as a           │
│ Government employee is automatically excluded                               │
│       evidence: "Household with any member as a Government employee"        │
│   * annual_income lte 120000   -- Any member of the family earning more     │
│ than Rs.10,000 per month is automatically excluded                          │
│       evidence: "Any member of the family earning more than Rs.10,000 per   │
│ month"                                                                      │
│   * ever_income_tax_payer eq false   -- Paying income tax is an automatic   │
│ exclusion parameter                                                         │
│       evidence: "Paying income tax"                                         │
│                                                                             │
│ Unmapped criteria (kept as caveats, NOT checked by the engine):             │
│   * The universe of eligible beneficiaries under PMAY-G will include all    │
│ the houseless households living in zero, one, or two-room houses with       │
│ kutcha walls and kutcha roofs (as per SECC data, and subject to the         │
│ exclusion process).                                                         │
│       evidence: "The universe of eligible beneficiaries under PMAY-G will   │
│ include all the houseless households living in zero, one, or two-room       │
│ houses with kutcha walls and kutcha roofs (as per SECC data, and subject to │
│ the exclusion process)."                                                    │
│   * All households living in houses with pucca roofs and/or pucca walls and │
│ households living in houses with more than 2 rooms are filtered out.        │
│       evidence: "All households living in houses with pucca roofs and/or    │
│ pucca walls and households living in houses with more than 2 rooms are      │
│ filtered out."                                                              │
│   * Paying professional tax                                                 │
│       evidence: "Paying professional tax"                                   │
│   * Own a refrigerator                                                      │
│       evidence: "Own a refrigerator"                                        │
│   * Own a landline phone                                                    │
│       evidence: "Own a landline phone"                                      │
│   * Motorised two/three/four wheeler/ fishing boat                          │
│       evidence: "Motorised two/three/four wheeler/ fishing boat"            │
│   * Mechanised three/four-wheeler agricultural equipment                    │
│       evidence: "Mechanised three/four-wheeler agricultural equipment"      │
│   * Kisan Credit Card with a credit limit of Rs.50,000 or above             │
│       evidence: "Kisan Credit Card with a credit limit of Rs.50,000 or      │
│ above"                                                                      │
│   * Households with non-agricultural enterprises registered with the        │
│ Government                                                                  │
│       evidence: "Households with non-agricultural enterprises registered    │
│ with the Government"                                                        │
│   * Own 2.5 acres or more of irrigated land with at least one irrigation    │
│ equipment                                                                   │
│       evidence: "Own 2.5 acres or more of irrigated land with at least one  │
│ irrigation equipment"                                                       │
│   * 5 acres or more of irrigated land for two or more crop seasons          │
│       evidence: "5 acres or more of irrigated land for two or more crop     │
│ seasons"                                                                    │
│   * Owning at least 7.5 acres of land or more with at least one irrigation  │
│ equipment                                                                   │
│       evidence: "Owning at least 7.5 acres of land or more with at least    │
│ one irrigation equipment"                                                   │
│   * Beneficiaries are identified using the Socio-Economic and Caste Census  │
│ (SECC) parameters and verified by the Gram Sabhas.                          │
│       evidence: "Beneficiaries are identified using the Socio-Economic and  │
│ Caste Census (SECC) parameters and verified by the Gram Sabhas."            │
│   * Households without shelter                                              │
│       evidence: "Households without shelter"                                │
│   * Destitute/ living on alms                                               │
│       evidence: "Destitute/ living on alms"                                 │
│   * Manual scavengers                                                       │
│       evidence: "Manual scavengers"                                         │
│   * Primitive Tribal Groups                                                 │
│       evidence: "Primitive Tribal Groups"                                   │
│   * Legally released bonded laborer                                         │
│       evidence: "Legally released bonded laborer"                           │
│   * Households with no adult member between ages 16 to 59                   │
│       evidence: "Households with no adult member between ages 16 to 59"     │
│   * Female-headed households with no adult male member between ages 16 to   │
│ 59                                                                          │
│       evidence: "Female-headed households with no adult male member between │
│ ages 16 to 59"                                                              │
│   * Households with no literate adult above 25 years                        │
│       evidence: "Households with no literate adult above 25 years"          │
│   * Households with any disabled member and no able-bodied adult member     │
│       evidence: "Households with any disabled member and no able-bodied     │
│ adult member"                                                               │
│   * Landless Households deriving the major part of their income from manual │
│ casual labor                                                                │
│       evidence: "Landless Households deriving the major part of their       │
│ income from manual casual labor"                                            │
│   * Households with widows and next-of-kin of members of                    │
│ defence/paramilitary/police forces killed in action.                        │
│       evidence: "Households with widows and next-of-kin of members of       │
│ defence/paramilitary/police forces killed in action."                       │
│   * Households where a member is suffering from leprosy or cancer and       │
│ People living with HIV (PLHIV).                                             │
│       evidence: "Households where a member is suffering from leprosy or     │
│ cancer and People living with HIV (PLHIV)."                                 │
│   * Households with a single girl child.                                    │
│       evidence: "Households with a single girl child."                      │
│   * Beneficiary families of the Scheduled Tribes and Other Traditional      │
│ Forest Dwellers (Recognition of Forest Rights) Act, 2006, commonly known as │
│ the Forest Rights Act.                                                      │
│       evidence: "Beneficiary families of the Scheduled Tribes and Other     │
│ Traditional Forest Dwellers (Recognition of Forest Rights) Act, 2006,       │
│ commonly known as the Forest Rights Act."                                   │
│   * Transgender persons.                                                    │
│       evidence: "Transgender persons."                                      │
│   * 60% of the target allocated to each State/ UT should be earmarked for   │
│ SC/STs, subject to the availability of eligible beneficiaries.              │
│       evidence: "60% of the target allocated to each State/ UT should be    │
│ earmarked for SC/STs, subject to the availability of eligible               │
│ beneficiaries."                                                             │
│   * Further, as far as possible, 15% of the total fund would be earmarked   │
│ for Minorities at the National Level for households.                        │
│       evidence: "Further, as far as possible, 15% of the total fund would   │
│ be earmarked for Minorities at the National Level for households."          │
│   * the States to the extent possible, may ensure that 3% of beneficiaries  │
│ at the State Level are from among persons with disabilities.                │
│       evidence: "the States to the extent possible, may ensure that 3% of   │
│ beneficiaries at the State Level are from among persons with disabilities." │
│   * Financial Assistance of ₹ 1,20,000 per unit for plain areas; and ₹      │
│ 1,30,000 per unit for hilly areas, difficult areas, and IAP districts       │
│ (Himalayan states, North-Eastern states, and Union Territories of Jammu &   │
│ Kashmir).                                                                   │
│       evidence: "Financial Assistance of ₹ 1,20,000 per unit for plain      │
│ areas; and ₹ 1,30,000 per unit for hilly areas, difficult areas, and IAP    │
│ districts (Himalayan states, North-Eastern states, and Union Territories of │
│ Jammu & Kashmir)."                                                          │
│   * A willing beneficiary can avail of institutional finance (loan) of up   │
│ to ₹ 70,000 at 3% lower interest rate, to build a permanent house. The      │
│ maximum principal amount for which subsidy can be sought is ₹ 2,00,000.     │
│       evidence: "A willing beneficiary can avail of institutional finance   │
│ (loan) of up to ₹ 70,000 at 3% lower interest rate, to build a permanent    │
│ house. The maximum principal amount for which subsidy can be sought is ₹    │
│ 2,00,000."                                                                  │
│   * The minimum size of the house shall be is 25 sq m including a dedicated │
│ area for hygienic cooking.                                                  │
│       evidence: "The minimum size of the house shall be is 25 sq m          │
│ including a dedicated area for hygienic cooking."                           │
│   * In convergence with Swachh Bharat Mission-Gramin (SBM-G), the           │
│ beneficiaries get financial assistance of up to ₹ 12,000 for the            │
│ construction of toilets.                                                    │
│       evidence: "In convergence with Swachh Bharat Mission-Gramin (SBM-G),  │
│ the beneficiaries get financial assistance of up to ₹ 12,000 for the        │
│ construction of toilets."                                                   │
│   * In convergence with MGNREGA, the beneficiary is entitled to employment  │
│ as unskilled labor (Rural Mason Training) at ₹ 90.95 per day for 95 days.   │
│       evidence: "In convergence with MGNREGA, the beneficiary is entitled   │
│ to employment as unskilled labor (Rural Mason Training) at ₹ 90.95 per day  │
│ for 95 days."                                                               │
│   * In convergence with Pradhan Mantri Ujjwala Yojana, one LPG connection   │
│ per house is provided.                                                      │
│       evidence: "In convergence with Pradhan Mantri Ujjwala Yojana, one LPG │
│ connection per house is provided."                                          │
│   * PMAY-G has been extended for another two years, i.e. till 31st March    │
│ 2024.                                                                       │
│       evidence: "PMAY-G has been extended for another two years, i.e. till  │
│ 31st March 2024."                                                           │
│                                                                             │
│ Documents: Aadhaar number and a self-attested copy of the Aadhaar Card (If  │
│ the applicant is illiterate, then in such case a consent letter has to be   │
│ obtained along with the thumbprint of the applicant); Job Card (duly        │
│ registered with MGNREGA); Bank account details – both originals and         │
│ duplicates.; Swachh Bharat Mission (SBM) number.; Affidavit stating the     │
│ beneficiaries, or their family members do not own a pucca house.            │
│ How to apply: Visit the official website for login PMAY-G. Fill in the      │
│ details required in the personal details section (such as gender, mobile    │
│ number, Aadhaar number, etc.) Upload the consent form required to use the   │
│ Aadhaar number. Click on the search button to find the beneficiary name,    │
│ PMAY ID, and priority. Click on ‘Select to Register’. The beneficiary       │
│ details will be automatically generated and displayed. The remaining        │
│ beneficiary details can now be filled in, such as ownership type, relation, │
│ Aadhaar number, etc. Upload the consent form required to use the Aadhaar    │
│ number on behalf of the beneficiary. In the next section, add the           │
│ beneficiary account details in the required fields, such as beneficiary     │
│ name, bank account number, etc. If the beneficiary wants to avail a loan,   │
│ select ‘Yes’ and enter the required loan amount. In the next section, enter │
│ the MGNREGA job card number and Swachh Bharat Mission (SBM) number of the   │
│ beneficiary. The next section will be filled in by the concerned office.    │
│                                                                             │
│ Evidence check: 66/66 quotes found in the source text                       │
│                                                                             │
│ Actions: reject, edit                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
Decide with:  python -m research review r-c989648db3 --approve | --reject | 
--edit file.json
Edit template: python -m research show r-c989648db3 --json > edit.json

```

## Review panel: PMAY-U (thread r-5f7b25ccbd)

```
┌──────────────────────── review: thread r-5f7b25ccbd ────────────────────────┐
│ STATUS: needs_human_fix   source:                                           │
│ https://www.myscheme.gov.in/schemes/pmay-u   LLM attempts: 3                │
│                                                                             │
│ BLOCKING ERRORS (cannot approve until fixed; use --edit or --reject;        │
│ URL-only errors can also be approved with --allow-url):                     │
│   x auditor: candidate: No eligibility rules were extracted; all            │
│ eligibility conditions from the document are missing from the rules array   │
│ and were only placed in caveats/unmapped_criteria, so the engine cannot     │
│ check any of them. -- source says: "1. The family identifies as one of the  │
│ following -                                                                 │
│ a) Economically Weaker Section (EWS): households with annual income up to ₹ │
│ 3,00,000.                                                                   │
│ b) Low Income Group (LIG): households with annual income between ₹ 3,00,001 │
│ and ₹ 6,00,000.                                                             │
│ c) Middle Income Group-1 (MIG-1): households with annual income between ₹   │
│ 6,00,001 and ₹ 12,00,000.                                                   │
│ d) Middle Income Group-2 (MIG-2): households with annual income between ₹   │
│ 12,00,001 and ₹ 18,00,000.                                                  │
│ 2. The applicant or his/her family members must not be owning a pucca house │
│ in any part of the country.                                                 │
│ 3. The family must comprise of husband/wife and unmarried children.         │
│ 4. The town/city in which the family resides must be covered under the      │
│ scheme.                                                                     │
│ 5. The family MUST NOT have previously availed the benefits of any          │
│ housing-related schemes set up by the Government of India."                 │
│   x auditor: candidate: The document states all eligible beneficiaries      │
│ should have an Aadhaar/Aadhaar Virtual ID, but no rule or caveat captures   │
│ this requirement. -- source says: "All eligible beneficiaries under all     │
│ components of the scheme should have an Aadhaar/ Aadhaar Virtual ID."       │
│   x auditor: candidate: The document restricts coverage to urban            │
│ areas/towns/cities covered under the scheme (Statutory Towns, Notified      │
│ Planning Areas, etc. as per Census 2011), but no rule or caveat captures    │
│ this geographic coverage condition. -- source says: "The Mission, as per    │
│ Census 2011, covers the entire urban area consisting of Statutory Towns,    │
│ Notified Planning Areas, Development Authorities, Special Area Development  │
│ Authorities, Industrial Development Authorities or any such authority under │
│ State legislation which is entrusted with the functions of urban planning & │
│ regulations."                                                               │
│   x auditor: candidate: The document requires the family to comprise of     │
│ husband/wife and unmarried children, but no rule or caveat captures this    │
│ family composition condition. -- source says: "The family must comprise of  │
│ husband/wife and unmarried children."                                       │
│   x auditor: candidate: The document requires that the family must not have │
│ previously availed benefits of any housing-related schemes set up by the    │
│ Government of India, but no rule or caveat captures this condition. --      │
│ source says: "The family MUST NOT have previously availed the benefits of   │
│ any housing-related schemes set up by the Government of India."             │
│   x auditor: candidate: The document requires that the applicant or family  │
│ members must not own a pucca house in any part of the country, but no rule  │
│ or caveat captures this condition. -- source says: "The applicant or        │
│ his/her family members must not be owning a pucca house in any part of the  │
│ country."                                                                   │
│   x auditor: candidate: The document defines EWS/LIG/MIG-1/MIG-2 by annual  │
│ household income ranges, but no rule captures these income limits; they are │
│ only listed as caveats/unmapped_criteria and are not machine-checked. --    │
│ source says: "a) Economically Weaker Section (EWS): households with annual  │
│ income up to ₹ 3,00,000.                                                    │
│ b) Low Income Group (LIG): households with annual income between ₹ 3,00,001 │
│ and ₹ 6,00,000.                                                             │
│ c) Middle Income Group-1 (MIG-1): households with annual income between ₹   │
│ 6,00,001 and ₹ 12,00,000.                                                   │
│ d) Middle Income Group-2 (MIG-2): households with annual income between ₹   │
│ 12,00,001 and ₹ 18,00,000."                                                 │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Applicant or family members must not own a pucca house in any part of the   │
│ country -- source says: "The applicant or his/her family members must not   │
│ be owning a pucca house in any part of the country.". Add a rule if a       │
│ Profile field can express it, otherwise add it to unmapped_criteria with    │
│ this quote.                                                                 │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Family must comprise of husband/wife and unmarried children -- source says: │
│ "The family must comprise of husband/wife and unmarried children.". Add a   │
│ rule if a Profile field can express it, otherwise add it to                 │
│ unmapped_criteria with this quote.                                          │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Town/city must be covered under the scheme (urban area as per Census 2011)  │
│ -- source says: "The town/city in which the family resides must be covered  │
│ under the scheme.". Add a rule if a Profile field can express it, otherwise │
│ add it to unmapped_criteria with this quote.                                │
│   x auditor: criterion in the source is covered by no rule or caveat:       │
│ Family must not have previously availed benefits of any housing-related     │
│ schemes set up by the Government of India -- source says: "The family MUST  │
│ NOT have previously availed the benefits of any housing-related schemes set │
│ up by the Government of India.". Add a rule if a Profile field can express  │
│ it, otherwise add it to unmapped_criteria with this quote.                  │
│   x auditor: criterion in the source is covered by no rule or caveat: All   │
│ eligible beneficiaries should have an Aadhaar/Aadhaar Virtual ID -- source  │
│ says: "All eligible beneficiaries under all components of the scheme should │
│ have an Aadhaar/ Aadhaar Virtual ID.". Add a rule if a Profile field can    │
│ express it, otherwise add it to unmapped_criteria with this quote.          │
│   x auditor: criterion in the source is covered by no rule or caveat: EWS   │
│ annual household income up to ₹ 3,00,000 -- source says: "a) Economically   │
│ Weaker Section (EWS): households with annual income up to ₹ 3,00,000.". Add │
│ a rule if a Profile field can express it, otherwise add it to               │
│ unmapped_criteria with this quote.                                          │
│   x auditor: criterion in the source is covered by no rule or caveat: LIG   │
│ annual household income between ₹ 3,00,001 and ₹ 6,00,000 -- source says:   │
│ "b) Low Income Group (LIG): households with annual income between ₹         │
│ 3,00,001 and ₹ 6,00,000.". Add a rule if a Profile field can express it,    │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat: MIG-1 │
│ annual household income between ₹ 6,00,001 and ₹ 12,00,000 -- source says:  │
│ "c) Middle Income Group-1 (MIG-1): households with annual income between ₹  │
│ 6,00,001 and ₹ 12,00,000.". Add a rule if a Profile field can express it,   │
│ otherwise add it to unmapped_criteria with this quote.                      │
│   x auditor: criterion in the source is covered by no rule or caveat: MIG-2 │
│ annual household income between ₹ 12,00,001 and ₹ 18,00,000 -- source says: │
│ "d) Middle Income Group-2 (MIG-2): households with annual income between ₹  │
│ 12,00,001 and ₹ 18,00,000.". Add a rule if a Profile field can express it,  │
│ otherwise add it to unmapped_criteria with this quote.                      │
│                                                                             │
│ Auditor (nvidia/nemotron-3.5-super-vl-120b-a12b): 16 blocking finding(s) on │
│ the latest attempt, 1 warning(s), 0 dropped (quote not in source).          │
│ Auditor notes (independent second reading of the source; judge each         │
│ yourself):                                                                  │
│   ? auditor: candidate: The benefits text states MIG II income as "from     │
│ Rs.12,00,001 and 18,00,000" which omits the word "to" and could be read as  │
│ ambiguous compared to the eligibility section which says "between ₹         │
│ 12,00,001 and ₹ 18,00,000". -- source says: "MIG II: Annual Household       │
│ Income from Rs.12,00,001 and 18,00,000; house sizes upto 200 sq.m"          │
│                                                                             │
│ NEW scheme: Pradhan Mantri Awas Yojana - Urban                              │
│ [pradhan_mantri_awas_yojana_urban]                                          │
│   ministry: Ministry Of Housing & Urban Affairs   category: housing         │
│   summary:  A flagship mission implemented by MoHUA, addressing urban       │
│ housing shortage. The beneficiaries include Economically Weaker Section     │
│ (EWS) / Low Income Group (LIG) and Middle Income Group (MIG) categories,    │
│ including slum dwellers, by ensuring a pucca house to all eligible urban    │
│ households by 2022.                                                         │
│   benefits: Slum rehabilitation of eligible Slum Dwellers with              │
│ participation of private developers using land as a resource. Promotion of  │
│ Affordable Housing through Credit Linked Subsidy Scheme (CLSS). EWS: Annual │
│ Household Income up to Rs.3,00,000; house sizes upto 30 sq.m; LIG: Annual   │
│ Household Income from Rs.3,00,001 to Rs.6,00,000; house sizes upto 60 sq.m; │
│ MIG I: Annual Household Income from Rs. 6,00,001 to Rs. 12,00,000; house    │
│ sizes upto 160 sq.m; MIG II: Annual Household Income from Rs.12,00,001 and  │
│ 18,00,000; house sizes upto 200 sq.m. Affordable Housing in Partnership     │
│ with Public & Private sectors: Central Assistance per EWS house in projects │
│ where 35% of houses are for EWSs. Subsidy for Beneficiary-Led individual    │
│ house construction /enhancement: For individuals of EWS category requiring  │
│ individual house (separate project for such beneficiaries).                 │
│                                                                             │
│ Rules (checked by the engine) with evidence:                                │
│   (none)                                                                    │
│                                                                             │
│ Unmapped criteria (kept as caveats, NOT checked by the engine):             │
│   * EWS: households with annual income up to ₹ 3,00,000.                    │
│       evidence: "Economically Weaker Section (EWS): households with annual  │
│ income up to ₹ 3,00,000."                                                   │
│   * LIG: households with annual income between ₹ 3,00,001 and ₹ 6,00,000.   │
│       evidence: "Low Income Group (LIG): households with annual income      │
│ between ₹ 3,00,001 and ₹ 6,00,000."                                         │
│   * MIG-1: households with annual income between ₹ 6,00,001 and ₹           │
│ 12,00,000.                                                                  │
│       evidence: "Middle Income Group-1 (MIG-1): households with annual      │
│ income between ₹ 6,00,001 and ₹ 12,00,000."                                 │
│   * MIG-2: households with annual income between ₹ 12,00,001 and ₹          │
│ 18,00,000.                                                                  │
│       evidence: "Middle Income Group-2 (MIG-2): households with annual      │
│ income between ₹ 12,00,001 and ₹ 18,00,000."                                │
│   * The applicant or his/her family members must not be owning a pucca      │
│ house in any part of the country.                                           │
│       evidence: "The applicant or his/her family members must not be owning │
│ a pucca house in any part of the country."                                  │
│   * The family must comprise of husband/wife and unmarried children.        │
│       evidence: "The family must comprise of husband/wife and unmarried     │
│ children."                                                                  │
│   * The town/city in which the family resides must be covered under the     │
│ scheme.                                                                     │
│       evidence: "The town/city in which the family resides must be covered  │
│ under the scheme."                                                          │
│   * The family MUST NOT have previously availed the benefits of any         │
│ housing-related schemes set up by the Government of India.                  │
│       evidence: "The family MUST NOT have previously availed the benefits   │
│ of any housing-related schemes set up by the Government of India."          │
│   * All eligible beneficiaries under all components of the scheme should    │
│ have an Aadhaar/ Aadhaar Virtual ID.                                        │
│       evidence: "All eligible beneficiaries under all components of the     │
│ scheme should have an Aadhaar/ Aadhaar Virtual ID."                         │
│   * The Mission, as per Census 2011, covers the entire urban area           │
│ consisting of Statutory Towns, Notified Planning Areas, Development         │
│ Authorities, Special Area Development Authorities, Industrial Development   │
│ Authorities or any such authority under State legislation which is          │
│ entrusted with the functions of urban planning & regulations.               │
│       evidence: "The Mission, as per Census 2011, covers the entire urban   │
│ area consisting of Statutory Towns, Notified Planning Areas, Development    │
│ Authorities, Special Area Development Authorities, Industrial Development   │
│ Authorities or any such authority under State legislation which is          │
│ entrusted with the functions of urban planning & regulations."              │
│                                                                             │
│ Documents: Aadhaar Number (or Aadhaar/ Aadhaar Enrolment ID);               │
│ Self-Certificate / Affidavit as Proof of Income.; Identity and Residential  │
│ Proof (PAN card, Voter ID, Driving License); Proof of Minority Community    │
│ (if the applicant belongs to a Minority Community); Proof of Nationality;   │
│ EWS Certificate / LIG Certificate / MIG Certificate (as applicable); Salary │
│ Slips; IT Return Statements; Property Valuation Certificate; Bank Details   │
│ and Account Statement; Affidavit / Proof that the applicant does not own a  │
│ ‘pucca’ house; Affidavit / Proof that the applicant is constructing a home  │
│ under the scheme                                                            │
│ How to apply: Online or Offline. Step 1: Visit the Official Website of      │
│ PMAY-Urban. Step 2: Select the ‘Citizen Assessment’ option and click on the │
│ applicable choice: “For Slum Dwellers” or “Benefits under other three       │
│ components”. Step 3: Enter your Aadhaar Card details. This will redirect    │
│ you to the online application form. In the form, fill in all the mandatory  │
│ details, and upload the required documents. The details to be filled        │
│ include name, contact number, other personal details, bank account and      │
│ income details, among others. Step 4: At the bottom of the form, click      │
│ ‘Save’ and enter the Captcha code. The application is now complete and a    │
│ print can be taken at this stage for future reference.                      │
│                                                                             │
│ Evidence check: 34/34 quotes found in the source text                       │
│                                                                             │
│ Actions: reject, edit                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
Decide with:  python -m research review r-5f7b25ccbd --approve | --reject | 
--edit file.json
Edit template: python -m research show r-5f7b25ccbd --json > edit.json

```
