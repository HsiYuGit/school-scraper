# Admissions source scraper grill

Date: 2026-05-23

Scope: design two independent source-specific admissions scrapers for My German University and DAAD, separate from the existing official-school-site crawler, covering the same 12 Gut-Haode partner schools and preserving the repo admissions JSON contract.

## Round 1

Question: If My German University or DAAD cannot find one of the 12 partner schools or some programmes, how should the output handle the gap?

User answer: Accepted the recommendation.

Recommendation / tradeoff note: Keep the scope strict: each source scraper should output one result per partner school, but must not fall back to official school websites. Missing or partial source coverage should be represented explicitly as `source_no_match` or `source_partial_match`, with source queries, URLs checked, and limitations recorded. This preserves the single-source promise and makes source coverage itself auditable.

Decision: Generate 12-school outputs for each source. Do not use official-school-site fallback inside the My German University or DAAD scrapers. Missing source coverage is valid output and should be visible in the JSON and manifest.

Unresolved follow-up: Decide whether the per-source JSON should be normalized directly into the repo admissions contract, or preserve more source-specific raw fields with a mapping layer.

## Round 2

Question: Should the My German University and DAAD outputs directly follow the existing admissions JSON contract, or preserve source-specific raw fields first and map them later?

User answer: Accepted the recommendation, with an added requirement to preserve extensibility. If My German University or DAAD exposes information that the current JSON contract cannot represent cleanly, the design should provide a way to keep it rather than dropping it.

Recommendation / tradeoff note: Use the existing program-level admissions contract as the primary output so renderers, comparisons, and tests can continue to work. Add source metadata such as `source_platform`, `source_record_id`, source listing/detail URLs, and coverage status. Preserve fields that do not fit the current contract in a source-specific extension object instead of forcing them into the wrong normalized field.

Decision: Primary output remains contract-compatible. Each source scraper may include a bounded source-specific extension area, tentatively `source_specific`, for fields that do not fit the existing normalized contract. Any source-specific field must retain evidence and source URL context so it can later be promoted into the shared contract if useful.

Unresolved follow-up: Decide whether source records are discovered live from search/listing pages, or whether the repo should maintain curated per-school source URLs for each platform.

## Round 3

Question: Why does the design need source pages for each school?

User answer: The user agrees with maintaining stable My German University / DAAD source targets for each school or programme.

Recommendation / tradeoff note: "Source pages" means platform-internal pages on My German University or DAAD, not school official websites. Stable source targets make the scrapers reproducible, let programme-level detail pages supply requirements/deadlines/fees, and preserve `source_url` / source record IDs for evidence tracing.

Decision: Add or maintain a curated per-platform target map for the 12 schools. Live discovery may fill gaps, but confirmed source targets should be written into configuration and reused by default.

Unresolved follow-up: Decide the versioned output layout for My German University and DAAD artifacts, and whether the HTML dashboard should surface them immediately.

## Round 4

Question: Should My German University and DAAD outputs be added to the existing HTML dashboard immediately?

User answer: Accepted the recommendation, and added that there should be a place to compare every strategy: official-site LLM, official-site crawler, DAAD, and My German University.

Recommendation / tradeoff note: Put source outputs in separate directories such as `outputs/source_mgu/` and `outputs/source_daad/`, then render separate dashboard sections for those sources. Do not mix them into `v0_4` or `llm_native_v0_2`, because those are different extraction strategies. Add a strategy comparison area that can compare official-site crawler, official-site LLM, DAAD, and My German University at school and programme level.

Decision: Source scrapers should produce standalone source directories and manifests. The review dashboard should expose each source and include a dedicated cross-strategy comparison surface covering official-site LLM, official-site crawler, DAAD, and My German University.

Unresolved follow-up: Decide the comparison dimensions and matching rules across strategies.

## Round 5

Question: What should the four-strategy comparison page compare?

User answer: Accepted the recommendation.

Recommendation / tradeoff note: Use a three-layer comparison: school coverage, programme matching, and requirement/application gaps. Match programmes by source detail URL, official course URL when available, normalized title, degree, and level. Treat unmatched records as strategy-only records such as `only_in_official_crawler`, `only_in_official_llm`, `only_in_daad`, or `only_in_mgu`. Compare admissions fields without automatically declaring one strategy correct.

Decision: Build a cross-strategy comparison surface that shows source coverage, programme-level matches/unmatched records, and requirement/application differences for language requirements, academic background/ECTS, GRE/GMAT/interview/tests, work experience, documents, deadlines, application channel, and fees. Differences should carry evidence URLs and default to `needs_review` rather than automatic truth claims.

Unresolved follow-up: Decide programme scope for MGU and DAAD extraction.

## Round 6

Question: Should the first source-scraper pass prioritize English-taught, Master, or otherwise "most relevant" programmes?

User answer: The user clarified that the intended scope is all programmes for each school, not a Master- or English-focused subset, and accepted the correction.

Recommendation / tradeoff note: Prior mentions of English, Master, or full-degree emphasis came from earlier seed examples, extractor capabilities, and DAAD's common International Programmes framing, not from a user scope decision. Those should not become hidden filters.

Decision: My German University and DAAD scrapers should collect all programmes for the 12 partner schools that the source platform exposes. Degree level, language, study mode, and application availability are metadata and dashboard filters only. They must not be used as extraction-priority rules or exclusion rules unless the user later asks for a narrower view.

Unresolved follow-up: Decide crawling boundaries for robots, JavaScript-rendered pages, and source-site search/detail access.

## Round 7

Question: How far should the My German University and DAAD scrapers go when source pages involve robots rules, JavaScript rendering, search APIs, or pages that need browser interaction?

User answer: The user agrees with a conservative first version, but wants the system to observe and record deeper strategies that could be attempted in later versions.

Recommendation / tradeoff note: First version should only use public, reproducible, low-risk access: robots-respecting HTML, stable detail pages, and observable public JSON endpoints where appropriate. It should not use login, CAPTCHA bypass, aggressive interactions, or large site scans. When a deeper strategy appears possible, record it as a future candidate rather than implementing it implicitly.

Decision: v1 source scrapers must stay conservative and transparent. They should emit explicit limitation statuses such as `source_limited`, `js_gated`, `robots_blocked`, or `endpoint_candidate_found`. They should also collect `future_deepening_candidates` in manifests or per-school notes, including candidate API endpoints, missing fields, query parameters, browser-rendering clues, and expected payoff for a later version.

Unresolved follow-up: Decide whether to build MGU and DAAD as fully separate scripts with shared helpers, or duplicate all logic for maximum independence.

## Round 8

Question: How independent should the My German University and DAAD scrapers be in code?

User answer: Accepted the recommendation.

Recommendation / tradeoff note: Use separate CLI scripts for each source so their discovery and parsing logic cannot blur together, while sharing only low-level contract and manifest helpers. This preserves source separation without duplicating evidence, output-path, manifest, and contract boilerplate.

Decision: Implement `scripts/scrape_mgu_admissions.py` and `scripts/scrape_daad_admissions.py` as separate entrypoints, backed by a small shared module tentatively named `scripts/source_scraper_common.py`. Shared code should cover partner-list loading, slugs/output paths, contract-compatible skeletons, evidence items, manifest writing, limitation statuses, and conservative HTTP fetch settings. Source-specific modules own all MGU/DAAD discovery, parsing, and `source_specific` fields.

Unresolved follow-up: Decide first implementation/run deliverable: code-only with tests, or code plus generated 12-school source outputs and dashboard comparison pages.

## Round 9

Question: Should the first implementation deliver code only, or code plus generated source outputs and dashboard comparison pages?

User answer: The user accepts producing first-version outputs with conservative crawl limits, but wants any possible missed coverage caused by those limits to be especially visible in the dashboard because dashboard review is the main validation workflow.

Recommendation / tradeoff note: Conservative limits mean bounded pages/records/search results, request timeouts, delays, same-source-only crawling, no login/CAPTCHA bypass, no PDF scraping by default, and no unbounded exploration. These limits make the run reproducible and low-risk, but they can cause source coverage gaps if the source site has more records beyond the bounded search.

Decision: First implementation should produce source outputs and dashboard artifacts, not just scripts. Every bounded run must emit coverage metadata and limitation warnings. The dashboard must surface per-source/per-school statuses such as `complete_within_configured_targets`, `source_partial_match`, `bounded_search_limit_reached`, `source_no_match`, `js_gated`, `robots_blocked`, and `source_limited`. Any status that could mean missed programmes must be visible in the dashboard, not buried only in JSON.

Unresolved follow-up: Propose approaches and present the implementation design for approval.

## Round 10

Question: Which source-scraper implementation approach should be used?

User answer: The user chose approach B: research the My German University and DAAD source-site mechanisms thoroughly first, then implement the scrapers.

Recommendation / tradeoff note: Approach A would have produced bounded v1 outputs quickly with explicit dashboard warnings. Approach B takes longer but should reduce avoidable misses by understanding search, pagination, detail pages, JavaScript-loaded data, and stable identifiers before coding extraction.

Decision: Use a source-reconnaissance-first workflow. Before implementing the MGU and DAAD scrapers, inspect each platform's public search/detail mechanics, pagination, available public endpoints, record identifiers, robots boundaries, and missing-field behavior. The final scraper should still remain conservative and transparent, but its conservative limits should be based on known source mechanics rather than guesses.

Unresolved follow-up: Present the revised design for approval.

## Round 11

Question: Does the revised architecture fit: source reconnaissance first, target config second, then separate MGU and DAAD CLI scrapers with shared contract helpers?

User answer: OK.

Recommendation / tradeoff note: This separates source understanding from extraction implementation. It should make crawler limits and target URLs deliberate rather than guessed during parser work.

Decision: Approved architecture: research My German University and DAAD source mechanics first, convert findings into target/config data, then implement independent source scrapers with shared low-level output helpers.

Unresolved follow-up: Confirm data flow and cross-strategy comparison design.

## Round 12

Question: Does the data flow fit: source reconnaissance -> target config -> MGU/DAAD outputs -> HTML review pages -> cross-strategy dashboard?

User answer: OK.

Recommendation / tradeoff note: Keeping DAAD and MGU outputs in separate source folders preserves strategy identity while allowing the dashboard to compare official crawler, official LLM, DAAD, and MGU.

Decision: Approved data flow and comparison design. Dashboard comparison should use 12 schools as the entry point and surface coverage, only-in-source records, matched-but-different records, and review-needed differences without automatically declaring truth.

Unresolved follow-up: Confirm verification and delivery gates.

## Round 13

Question: Do the verification and delivery gates fit?

User answer: OK.

Recommendation / tradeoff note: Acceptance should require source reconnaissance evidence, contract-compatible outputs, all-program scope, dashboard-visible coverage limitations, strategy comparison, tests, docs sync, and atomic commits.

Decision: Approved verification and delivery gates. The first committed artifact should be the design spec plus this grill record, followed by implementation work in later atomic commits.

Unresolved follow-up: None for design. Write the approved spec.
