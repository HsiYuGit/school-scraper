# Source Scraper Reconnaissance

Date: 2026-05-24

## DAAD

- Base URL: https://www2.daad.de/deutschland/studienangebote/international-programmes/en/
- Robots URL: https://www.daad.de/robots.txt; https://www2.daad.de/robots.txt returned 404 during reconnaissance. The main DAAD robots file sets `Crawl-delay: 2`, disallows several internal/application paths, and disallows query URLs containing `hec-fetch-offset`.
- Search entry points:
  - https://www2.daad.de/deutschland/studienangebote/international-programmes/en/result/
  - https://www.daad.de/en/studying-in-germany/universities/all-degree-programmes/
  - Observable JSON candidate: https://www2.daad.de/deutschland/studienangebote/international-programmes/api/solr/en/search.json
- Pagination behavior: The public result page exposes page, result-count, sorting, grid/list, and map controls. The observed JSON endpoint accepts `limit` and `offset`; a bounded `limit=3000&offset=0&display=list` request returned 2,524 courses. Future implementation should use small paged `limit`/`offset` requests with DAAD's crawl-delay rather than one large pull.
- Detail page pattern: `/deutschland/studienangebote/international-programmes/en/detail/<numeric_id>/`, for example `https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/5259/`.
- Record ID fields: Search JSON records include numeric `id` and relative `link` fields. The detail URL repeats the same numeric ID. The search JSON also includes an `academy` string but no confirmed institution ID/name mapping was captured in Task 1.
- Public endpoint candidates:
  - Confirmed candidate: `/deutschland/studienangebote/international-programmes/api/solr/en/search.json`
  - Candidate parameters observed or reported by the public page/API: `q`, `limit`, `offset`, `display`, `sort`, `degree[]`, `lang[]`, `fos`, `subjects[]`, `cit[]`, `tyi[]`, `ins[]`, `fee`, `bgn[]`, `dur[]`, `lvlEn[]`, `lvlDe[]`, `langDeAvailable`, `langEnAvailable`, `admReq`, `cert`, `scholarshipLC`, `scholarshipSC`, `isSep`.
  - Future candidate: inspect browser network for detail-page JSON or tab payloads before implementing detail extraction.
- Listing fields: Search JSON exposes `id`, `image`, `courseName`, `courseNameShort`, `academy`, `city`, `languages`, `languageLevelGerman`, `languageLevelEnglish`, `beginning`, `programmeDuration`, `date`, `costString`, `tuitionFees`, `courseType`, `isElearning`, `preparationForDegree`, `preparationForSubjectGroups`, `applicationDeadline`, `isCompleteOnlinePossible`, `badgeLabel`, `financialSupport`, `structuredResearch`, `supportInternationalStudents`, `subject`, `typeOfElearning`, `link`, and `requestLanguage`.
- Detail-only fields: Detail pages expose richer sections such as degree, course location, teaching-language prose, full-time/part-time mode, programme duration, beginning, application deadlines, course details, costs/funding, requirements/registration, and services. Example DAAD detail record `5259` shows degree, location, teaching language, duration, beginning, and visa-sensitive deadlines in the HTML detail page.
- JavaScript/browser clues: The search page renders a usable filter shell and page controls in HTML. The detail page was readable without executing JavaScript, though tabs/previous-next controls are present. The result list appears backed by the JSON endpoint rather than only static HTML.
- Access limits: Respect DAAD robots and crawl-delay; do not use disallowed `hec-fetch-offset` URLs, internal app paths, login-only areas, PDFs, or aggressive full-site scans. Treat `www2.daad.de` robots ambiguity conservatively by following the stricter main `www.daad.de` policy and using bounded API/page requests.
- Task 3 implementation mechanics:
  - `scripts/scrape_daad_admissions.py` uses the DAAD search JSON path with bounded `limit=100&offset=0&display=list` requests, then fetches same-source `/detail/<numeric_id>/` pages.
  - Detail pages remained readable as HTML and did not require JavaScript execution for the first-pass contract fields.
  - Detail record IDs can be extracted from `/detail/<numeric_id>/` URLs when the listing record ID is unavailable.
  - The 2026-05-24 live run produced 104 programme records: TUM Asia 8, ISM 10, EBS 9, SRH 59, Hochschule Fresenius 9, NIT 3, Hochschule Bremen 4, and IGC Bremen 2.
  - Munich Business School, CBS International Business School, Kuehne Logistics University, and ESMT Berlin produced `source_limited` outputs under the configured DAAD query/detail targets; no school-official fallback was attempted.
  - All DAAD outputs remain warning-marked because the configured targets are `source_partial_match` or `target_needs_recon`, so the manifest cannot claim exhaustive source coverage.
  - Parser hardening after review removes DAAD page chrome such as `DAADREMOVE_JS` and skip links from programme names, rejects navigation/tab headings such as `Requirements / Registration` as structured fees or deadlines, and cleans the promoted requirements notes before writing them into the normalized contract.
  - Certificate-like and short-course-like records, including summer/camp/training records, are retained for all-program source visibility but marked with `needs_human_review = true` and `source_specific.quality_flags`.
  - The scraper now records the bounded listing window (`limit=100 offset=0`) in per-school limitation notes and defaults to DAAD's documented two-second crawl delay unless a caller explicitly overrides it. A shared DAAD fetch session applies that delay before every fetch after the first, including listing-to-detail and cross-target transitions.
- Future deepening candidates:
  - Build and verify the `ins[]` institution ID map from the public filter UI or network requests.
  - Confirm DAAD course-type mapping and whether all source-visible partner records require `International Programmes` or also the broader `all-degree-programmes` database.
  - Inspect detail-page network requests for structured requirement/application payloads.
  - Confirm ambiguous partner mappings such as TUM Asia versus Technical University of Munich/Singapore records and International Graduate Center versus Bremen University of Applied Sciences.

## My German University

- Base URL: https://www.mygermanuniversity.com/
- Robots URL: https://www.mygermanuniversity.com/robots.txt. Direct `curl` access returned a Cloudflare managed-challenge page with `noindex,nofollow`; no usable robots directives were obtained in Task 1.
- Search entry points:
  - https://www.mygermanuniversity.com/
  - https://www.mygermanuniversity.com/universities
  - University profile pages, for example `https://www.mygermanuniversity.com/universities/Munich-Business-School`
  - University study-program listing pages, for example `https://www.mygermanuniversity.com/universities/International-School-of-Management-ISM/study-programs`
  - Subject and degree scoped pages, for example `/universities/<slug>/master`, `/subject/<subject-slug>`, and `/nc-free`
- Pagination behavior: Search-indexed university listing pages use `page=<n>` query parameters for multi-page listings, for example `https://www.mygermanuniversity.com/universities/Hochschule-Fresenius-University-of-Applied-Sciences/study-programs?page=2` and `https://www.mygermanuniversity.com/universities/HSB-Hochschule-Bremen-%E2%80%93-City-University-of-Applied-Sciences?page=8`. Public pages also expose "Browse Study Programs" counts and "All Study Programs" sections.
- Detail page pattern: Programme detail pages use a degree-level path plus slug and numeric record ID, for example `https://www.mygermanuniversity.com/master/international-business/1691`. Likely variants include `/bachelor/<programme-slug>/<numeric_id>`, `/master/<programme-slug>/<numeric_id>`, `/mba/<programme-slug>/<numeric_id>`, and similar degree-level prefixes, but only the master example was confirmed in Task 1.
- Record ID fields: Programme detail URLs include a trailing numeric ID such as `1691`. University targets use stable slugs such as `Munich-Business-School`, `International-School-of-Management-ISM`, and `HSB-Hochschule-Bremen-%E2%80%93-City-University-of-Applied-Sciences`. No public JSON school ID was confirmed.
- Public endpoint candidates:
  - Source pages reference public static programme/detail pages under `www.mygermanuniversity.com`.
  - `https://api.mygermanuniversity.com/files/study_program_information_package/...pdf` appears in indexed results as a file host for programme information packages, but no stable JSON search/detail endpoint was confirmed.
  - Future candidate: browser network inspection of StudyFinder filters and programme detail pages if allowed by robots/access boundaries.
- Listing fields: University/profile/listing pages expose school overview, location, status/type, student counts, degree tabs, number of study programmes, top subjects, top study programmes, fee ranges, common application deadlines, study-program counts, and filter metadata such as language, intake, numerus clausus, tuition, study mode, and teaching degree.
- Detail-only fields: Detail pages expose programme name, degree, language, application deadlines, duration/start, tuition fees, mode of admission, application channel, study mode, registration/tuition details, and potentially admission requirements and downloadable information packages.
- JavaScript/browser clues: Direct `curl` access to robots and pages returned Cloudflare managed-challenge HTML. The public pages are visible through search-index snapshots, but a first scraper must treat direct HTML collection as Cloudflare/JS-gated unless browser/network access proves otherwise. Map widgets are gated by user interaction and should not be loaded.
- Access limits: Do not bypass Cloudflare, login, cookies, CAPTCHA, or JavaScript challenges. Do not use school official-site fallback. If robots cannot be read because of Cloudflare, scraper outputs must surface `js_gated` or `source_limited` rather than silently treating coverage as complete.
- Task 4 implementation mechanics:
  - `scripts/scrape_mgu_admissions.py` only fetches configured My German University listing/detail URLs from `data/source_scraper_targets.json`; it does not fall back to school official websites.
  - The parser keeps MGU-specific fields in `source_specific`, including `duration` and `raw_blocks`, while mapping programme name, degree/level, language, IELTS, deadlines, and fees into the shared source admissions contract where present.
  - The scraper detects Cloudflare/JavaScript challenge markers in returned HTML and writes `js_gated` warning outputs instead of attempting bypass.
  - The completed local run on 2026-05-24 could not connect to MGU source URLs (`WinError 10061`) and therefore produced 12 warning-visible outputs: one `source_no_match` for TUM Asia and 11 `source_limited` files for configured MGU targets.
  - A network-approved retry reached some pages but timed out before a complete 12-school manifest could be written; final outputs were regenerated from the completed bounded run so the manifest and per-school files remain consistent.
- Future deepening candidates:
  - Use an allowed browser session to inspect StudyFinder network calls and confirm whether a public JSON endpoint exists.
  - Confirm pagination exhaustiveness for `/study-programs?page=<n>` pages and the page size per university.
  - Extract all programme detail IDs from confirmed university pages once access is allowed.
  - Decide whether to include source-hosted information-package PDFs; Task 1 records them only as future candidates.
