# Admissions crawler v0.4 review

Date: 2026-05-19

Scope: review every v0.3 crawler output and produce `outputs/v0_4/` with higher coverage while avoiding the v0.3 false-positive patterns. These files remain candidate admissions data and still require human review before being treated as authoritative.

## Summary

- v0.3 total: 30 program records, 69 language requirement records, 75 test requirement records.
- v0.4 total: 126 program records, 251 language requirement records, 199 test requirement records.
- Zero-output recovery: CBS, ISM, and SRH moved from 0 programs to non-zero outputs.
- Precision fixes: generic titles such as `Bachelor`, `Master Programs`, and `MBA programs` are no longer final records; cross-host redirects are skipped; NIT study-mode pages are no longer separate programs; `RemoteDisconnected` is recorded as a skipped URL instead of aborting the run.
- Known limitation: output volume is higher because sitemap and reviewed seed coverage are broader. v0.4 is better for recall and removes the clearest regressions, but fields such as shared language/test requirements still need manual review before production ingestion.

## Per-school review

| School | v0.3 issue | v0.4 action and result |
| --- | --- | --- |
| TUM Asia | v0.3 had 5 programs and missed some crawler/LLM-identified MSc pages; language requirements were absent. | Added reviewed seeds for central graduate requirements plus Aerospace Engineering and Industrial Chemistry. v0.4 has 7 programs and language evidence. |
| Munich Business School | v0.3 captured only 4 high-level programs and missed many master variants and preparatory routes. | Added reviewed master, MBA, DBA, Pre-Bachelor, and application seeds. v0.4 has 16 records, including `pre-bachelor` and `pre-master` levels. |
| International School of Management (ISM) | v0.3 was zero-output because concrete overview/application URLs were filtered with listing pages. | Allowed concrete `/overview` program paths while keeping top-level listings blocked. v0.4 has 14 records. |
| CBS International Business School | v0.3 was zero-output because CBS master/MBA URL patterns were not accepted. | Added `/masters-degree-germany/` and reviewed MBA/admissions seeds. v0.4 has 13 records. Language extraction remains sparse and should be reviewed manually. |
| EBS Universität | v0.3 was partial and could treat curriculum case studies as admissions tests. | Added individual bachelor/master/MBA seeds and required admissions context for case-study tests. v0.4 has 7 records. |
| SRH Universities | v0.3 was zero-output because concrete program paths were not seeded and later discovery produced generic titles. | Added concrete program/admission seeds, URL-first degree inference, and generic-title filtering. v0.4 has 12 records and no bare `Bachelor` final records. |
| Kühne Logistics University (KLU) | v0.3 over-tightened to one program and leaked graduate FAQ evidence across levels. | Added direct bachelor/master/MBA/foundation seeds, fixed level inference, and scoped shared FAQ evidence by level/language. v0.4 has 8 records. |
| Hochschule Fresenius | v0.3 was partial and missed many direct master pages; redirects could move to another host. | Added direct study-program seeds, skipped cross-host redirects, and kept central requirements as shared evidence. v0.4 has 21 same-host records. |
| NIT Northern Institute of Technology Management | v0.3 had the Business Analytics title/degree wrong and treated Technology Management study modes as programs. | URL-title rules now produce `Master in Business Analytics & AI` with `Master of Science`; single/double degree mode URLs are excluded as final programs. v0.4 has 2 program-family records. |
| Hochschule Bremen | v0.3 had only 2 records and missed the Computer Science MSc seed. | Replaced the bare degree-programme seed with a concrete Computer Science MSc seed and allowed discovered degree programme slugs. v0.4 has 12 records. |
| ESMT Berlin | v0.3 had admissions pages but mislabeled some MSc pages as MBA and admitted a summer-school false positive during v0.4 iteration. | Added URL-specific titles/degrees, expanded MBA seeds, and blocked summer-school/generic program titles. v0.4 has 7 records. |
| International Graduate Center, Hochschule Bremen | v0.3 included broad or generic pages and could admit focus/event/partner subpages. | Added reviewed IGC program seeds and blocked focus/event/dual-degree partner subpages. v0.4 has 7 records. |

## Harness notes

- Run schools as bounded single-school jobs when full batch stability is poor; then merge manifests by school name.
- Treat crawler output as candidate data. Improvement means both higher recall and fewer obvious non-program records, not just higher counts.
- Keep a suspect query for every iteration: generic titles, cross-host redirects, event/summer-school pages, focus pages, and known mode pages.
- Add a failing unit test before each new precision rule, then rerun the affected school only.
