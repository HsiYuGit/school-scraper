# Admissions LLM-native v0.2 gap report

Date: 2026-05-18, extended 2026-05-19

Scope: clean-room comparison of `outputs/v0_3/*.json` crawler outputs against `outputs/v0_3/llm_native/*.json`, treating the current LLM-native files as LLM v0.1. The 2026-05-19 extension also used `outputs/v0_4/*.json` as a candidate recall surface for CBS International Business School and EBS Universität. Admissions JSON is candidate data, not truth.

Generated v0.2 files:

- `outputs/v0_3/llm_native_v0_2/tum_asia_llm_native_v0_2_admissions.json`
- `outputs/v0_3/llm_native_v0_2/munich_business_school_llm_native_v0_2_admissions.json`
- `outputs/v0_3/llm_native_v0_2/cbs_international_business_school_llm_native_v0_2_admissions.json`
- `outputs/v0_3/llm_native_v0_2/ebs_universitat_llm_native_v0_2_admissions.json`

## Chosen schools

I selected exactly two schools where crawler v0.3 captured meaningful items that LLM v0.1 did not:

| School | Why selected |
| --- | --- |
| TUM Asia | Crawler found Aerospace Engineering and Industrial Chemistry program records and current application-period/fee facts missing from LLM v0.1. Live official navigation also lists both programs under Graduate Studies. |
| Munich Business School | Crawler found Pre-Bachelor International Business as an official program page. LLM v0.1 only mentioned Pre-Bachelor as a conditional/preparation route and listed it as a known gap. |
| CBS International Business School | Crawler v0.4 recovered concrete CBS master/MBA programme URLs after v0.3 had zero program records. Official CBS pages confirmed several v0.1 omissions. |
| EBS Universität | v0.4 did not reveal genuine v0.1 program omissions, but it was useful for classifying crawler naming, grouping, fee, and language-noise differences. |

## Comparison table

| School | Crawler v0.3 | LLM v0.1 | LLM v0.2 |
| --- | ---: | ---: | ---: |
| TUM Asia | 5 programs | 3 programs | 5 programs |
| Munich Business School | 4 programs | 8 programs | 9 programs |
| CBS International Business School | 0 programs in v0.3; 13 programs in v0.4 | 4 programs | 12 programs |
| EBS Universität | 4 programs in v0.3; 7 programs in v0.4 | 8 programs | 8 programs |

## Root-cause classification

### TUM Asia

| Crawler-only item | Classification | Judgment and evidence |
| --- | --- | --- |
| Aerospace Engineering program | genuine_llm_omission | Crawler has a program record at `https://tum-asia.edu.sg/graduate-studies/master-aerospace-engineering/` with official-page application period `1 Oct 2025 - 10 Jun 2026 * Extended *`, August 2026 intake, and fee `S$40,657*`. Live official navigation lists Aerospace Engineering under Graduate Studies. The individual page was JavaScript-gated during live reading, so v0.2 keeps `needs_human_review: true`. |
| Industrial Chemistry program | genuine_llm_omission | Crawler has a program record at `https://tum-asia.edu.sg/graduate-studies/master-industrial-chemistry/` with application period `1 Oct 2025 - 15 Apr 2026 * Extended *`, August 2026 intake, and fee `S$49,050*`. Live official navigation lists Industrial Chemistry under Graduate Studies. The individual page was JavaScript-gated during live reading, so v0.2 keeps `needs_human_review: true`. |
| Rail and Urban Transport extended deadline | genuine_llm_omission | LLM v0.1 used `1 Oct 2025 to 31 Mar 2026`; crawler and live official page show `1 Oct 2025 - 10 Jun 2026 * Extended *`. v0.2 updates the date and preserves the richer v0.1 requirement fields. |
| Integrated Circuit Design and Green Electronics crawler-specific deadlines/fees | genuine_llm_omission with caveat | Crawler evidence includes official-page application periods and fees. Live text was not available in this audit because the pages were JavaScript-gated, so v0.2 adds them as candidate evidence with medium confidence rather than high-confidence truth. |
| Industrial Chemistry "Case study" test requirement | crawler_false_positive | Crawler source text is curriculum/module text about a case study on Aquaculture 4.0, not an admissions test. v0.2 does not import it. |
| Crawler language_of_instruction includes German | crawler_false_positive | LLM v0.1 and official program framing support English instruction; crawler likely picked up German-language/course/global text. v0.2 uses English only on new TUM records. |

### Munich Business School

| Crawler-only item | Classification | Judgment and evidence |
| --- | --- | --- |
| Pre-Bachelor International Business program | genuine_llm_omission | Crawler raw evidence from `https://www.munich-business-school.de/en/bachelor/pre-bachelor` states that the Pre-Bachelor study program requires a university entrance qualification and B2 English, and that applicants apply in combination with Bachelor International Business. Live official page also confirms this page exists. LLM v0.1 explicitly left Pre-Bachelor as a known gap rather than a program record. |
| Pre-Bachelor as standalone degree | schema_granularity_difference | Official evidence frames it as a preparation/pre-bachelor study program combined with Bachelor International Business, not as a standalone bachelor degree. v0.2 uses `level: pre-bachelor`, `degree: Pre-Bachelor certificate / preparation program`, and `parent_program: Bachelor International Business`. |
| MBS Pre-Bachelor 30/60 ECTS and grade 2.5 | crawler_false_positive for normal Pre-Bachelor admission | Those facts come from Bachelor transfer/lateral-entry sections in the same page raw evidence. v0.2 does not put them in normal Pre-Bachelor academic requirements. |
| MBS Pre-Bachelor monthly application rounds and interview | genuine_llm_omission | Crawler raw evidence and the page text show monthly application rounds and a two-step written application plus online interview. v0.2 records this. |

### CBS International Business School

| Crawler-only item | Classification | Judgment and evidence |
| --- | --- | --- |
| v0.3 zero-program output | crawler recall gap | v0.3 was not a reliable negative result. v0.4 found concrete CBS programme pages that official `cbs.de` pages confirm. |
| International Business & Management M.Sc. | naming_or_grouping_mismatch | v0.1 already had this core programme. v0.2 preserves it and updates intake coverage rather than duplicating a crawler title variant. |
| International Business M.A. | genuine_llm_omission with caveat | Official CBS page exists, but it frames the offering as last available in Summer 2026. v0.2 adds the record and marks it for human review. |
| Business Psychology and Management, Digital Marketing, Global Finance, Strategy & Consulting, Supply Chain & Logistics | genuine_llm_omission | Official CBS programme pages confirm these as real programme records. v0.2 adds them. |
| Global Finance winter/summer URLs | schema_granularity_difference | v0.2 models the winter/summer URL variants as one programme with two intake windows. |
| Business Technology Part-Time | schema_granularity_difference | Official CBS page exists, but catalogue grouping is specialization-like. v0.2 keeps it as a human-review record. |
| NXT GEN Programmes and template snippets | crawler_false_positive | These are broad marketing/template surfaces, not final programme records. v0.2 does not import them. |

### EBS Universität

| Crawler-only item | Classification | Judgment and evidence |
| --- | --- | --- |
| Master in Business Analytics crawler title as "AI master's degree" | naming_or_grouping_mismatch | v0.1 already had the correct programme family. v0.2 keeps `Master in Business Analytics`. |
| Full-time MBA crawler title | naming_or_grouping_mismatch | v0.1 correctly groups full-time and part-time MBA variants. v0.2 preserves the grouped record. |
| Executive MBA early-bonus dates | schema_granularity_difference | v0.2 records March/May 2026 dates as fee/bonus notes, not admissions deadlines. |
| Master in Management / Finance test extraction | crawler_under_specified | v0.1 contains stronger admissions-test interpretation, including Finance CFA Level 1 nuance. v0.2 preserves it. |
| Bachelor in Law, Politics and Economics missing from v0.4 | crawler recall gap | Absence from v0.4 is not an LLM error. v0.2 preserves the v0.1 record. |
| English/German/Deutsch language extraction | crawler_false_positive | v0.2 does not import crawler language pollution where official English pages support English-only programme language. |

## v0.1 to v0.2 changes

TUM Asia:

- Added `method.version = llm_native_v0_2`, `source_files`, `prompt_file`, workflow notes, limitations, and truthful unavailable cost/token metadata.
- Added Aerospace Engineering and Industrial Chemistry as candidate program records with official URLs, crawler-backed application periods, fees, central graduate requirements, and human-review flags.
- Corrected Rail and Urban Transport application period to the extended June 10, 2026 date.
- Added crawler-backed dates/fees to Integrated Circuit Design and Green Electronics with medium confidence.
- Preserved v0.1 strengths: central TOEFL/IELTS requirements, APS note, GRE/GATE negation, richer documents and academic-background notes.
- Excluded false positives: Industrial Chemistry curriculum "case study" as an admissions test, and crawler-inferred German instruction.

Munich Business School:

- Added `method.version = llm_native_v0_2`, `source_files`, `prompt_file`, workflow notes, limitations, and truthful unavailable cost/token metadata.
- Added Pre-Bachelor International Business as a preparation/pre-bachelor program linked to Bachelor International Business.
- Preserved all eight v0.1 records, including DBA, MBA, master, and bachelor coverage.
- Removed the v0.1 known-gap statement that Pre-Bachelor is only a pathway.
- Excluded false positives from the crawler: transfer-entry ECTS/grade facts as normal Pre-Bachelor admission requirements.

CBS International Business School:

- Added `method.version = llm_native_v0_2`, `source_files`, `prompt_file`, workflow notes, limitations, and truthful unavailable cost/token metadata.
- Expanded from 4 to 12 records by adding official-confirmed CBS programme pages while preserving v0.1 shared requirements and MBA cautions.
- Rejected crawler/template noise, including `NXT GEN Programmes`, navigation-derived campus fragments, and generic deadline snippets.
- Marked International Business M.A., Business Psychology and Management, Business Technology Part-Time, and MBA records for human review where availability, catalogue grouping, or public-page detail remains uncertain.

EBS Universität:

- Added `method.version = llm_native_v0_2`, `source_files`, `prompt_file`, workflow notes, limitations, and truthful unavailable cost/token metadata.
- Kept all 8 v0.1 programme records because v0.4 did not show genuine programme omissions.
- Refreshed confirmed fee/timing facts where useful and classified v0.4 differences as naming, grouping, schema granularity, or crawler false positives.
- Recorded the Windows console encoding lesson: terminal mojibake is not the same as invalid UTF-8 JSON.

## Why v0.2 is better

v0.2 improves recall for confirmed crawler-only facts while keeping precision controls:

- It recovers true missed program coverage for TUM Asia and MBS.
- It recovers true missed program coverage for CBS where v0.4 found official programme URLs after a v0.3 zero-output result.
- It avoids adding duplicates for EBS where the crawler mostly surfaced naming/granularity differences rather than true omissions.
- It keeps the LLM v0.1 richer requirement extraction instead of replacing it with crawler-normalized fragments.
- It marks JavaScript-gated or crawler-only evidence as candidate data needing human review.
- It explicitly rejects crawler false positives rather than merging every crawler-only field.

Remaining concerns:

- Some TUM program pages were JavaScript-gated during live reading; v0.2 relies on local crawler evidence plus official navigation for those records.
- The generated files are improved audit artifacts, not a final admissions database.
