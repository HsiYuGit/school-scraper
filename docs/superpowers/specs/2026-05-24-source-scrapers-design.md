# Source Scrapers Design

Date: 2026-05-24

## Goal

Build two source-specific admissions scrapers for the Gut-Haode 12 partner schools:

- My German University
- DAAD

The new scrapers must be independent from the existing official-school-site crawler and from each other. They must output contract-compatible admissions JSON, preserve source-specific fields that do not fit the current shared contract, and feed a dashboard area that compares four strategies:

- official-site crawler (`outputs/v0_4`)
- official-site LLM (`outputs/v0_3/llm_native_v0_2`)
- DAAD (`outputs/source_daad`)
- My German University (`outputs/source_mgu`)

## Scope

The source scrapers collect all programmes exposed by each source platform for the 12 partner schools. Degree level, language of instruction, study mode, and application availability are metadata and dashboard filters only. They must not be used as hidden extraction filters unless the user later asks for a narrower view.

The scrapers must not fall back to school official websites. Missing or partial source coverage is valid output and must be visible in JSON, manifests, and the dashboard.

## Architecture

Use a source-reconnaissance-first workflow.

1. Research My German University and DAAD public source mechanics:
   - search entry points
   - pagination
   - listing/detail page URL patterns
   - record identifiers
   - available public JSON endpoints
   - robots and access boundaries
   - fields exposed on listing pages versus detail pages
   - JavaScript-gated or otherwise missing fields
2. Convert stable findings into a source target configuration, tentatively `data/source_scraper_targets.json`.
3. Implement separate source entrypoints:
   - `scripts/scrape_mgu_admissions.py`
   - `scripts/scrape_daad_admissions.py`
4. Share only low-level output and manifest helpers in `scripts/source_scraper_common.py`.

Source-specific modules own source discovery, parsing, source-specific fields, and platform quirks. Shared helpers own partner-list loading, slugs, contract-compatible skeletons, evidence item construction, manifest writing, coverage statuses, and conservative fetch settings.

## Output Contract

Each source output should remain compatible with the existing program-level admissions contract:

- `school`
- `program`
- `requirements`
- `application`
- `evidence`
- `raw_evidence_sections`
- `needs_human_review`

Each source output may also include source metadata:

- `source_platform`
- `source_record_id`
- `source_listing_url`
- `source_detail_url`
- `source_coverage_status`
- `source_specific`

`source_specific` preserves source fields that do not fit the current contract. These fields must retain source URL and evidence context so they can later be promoted into the shared contract if useful.

## Coverage And Limitations

The first implementation should be conservative and transparent. It should respect robots rules, use public HTML or public observable endpoints, apply timeouts and delays, avoid login/CAPTCHA bypass, avoid aggressive scanning, and stay within the source platform.

When the source cannot be fully covered, the output must record explicit statuses such as:

- `complete_within_configured_targets`
- `source_partial_match`
- `bounded_search_limit_reached`
- `source_no_match`
- `source_limited`
- `js_gated`
- `robots_blocked`
- `endpoint_candidate_found`

Any status that could mean missed programmes must be surfaced in the dashboard, not only in raw JSON.

Each manifest should also collect `future_deepening_candidates`, including candidate endpoints, missing fields, browser-rendering clues, query parameters, and expected payoff for later versions.

## Data Flow

```text
source reconnaissance
  -> data/source_scraper_targets.json
  -> scrape_mgu_admissions.py / scrape_daad_admissions.py
  -> outputs/source_mgu/*.json + manifest
  -> outputs/source_daad/*.json + manifest
  -> HTML review pages
  -> cross-strategy dashboard
```

Recommended output layout:

```text
outputs/
  source_mgu/
    <school>_admissions.json
    source_mgu_manifest.json
  source_daad/
    <school>_admissions.json
    source_daad_manifest.json
  html/
    source_mgu/
    source_daad/
    comparisons/
      strategy_matrix/
      source_mgu_vs_source_daad/
      v0_4_vs_source_mgu/
      v0_4_vs_source_daad/
```

## Dashboard And Comparison

The dashboard should include a dedicated cross-strategy comparison surface. The comparison starts from the 12 partner schools and shows:

- school coverage per strategy
- programme counts and coverage statuses
- programme matches and unmatched records
- requirement/application differences
- evidence URLs for each strategy
- warnings for possible missed source coverage

Programme matching should use source detail URLs, official course URLs when available, normalized title, degree, level, and source record IDs. Unmatched records should be labeled by strategy, such as:

- `only_in_official_crawler`
- `only_in_official_llm`
- `only_in_daad`
- `only_in_mgu`

Requirement/application comparison should cover language requirements, academic background/ECTS, GRE/GMAT/interview/tests, work experience, documents, deadlines, application channel, and fees. Differences default to `needs_review`; the comparison should not automatically declare which strategy is correct.

## Verification Gates

The implementation is acceptable only when:

1. Source reconnaissance is recorded and target config is based on known MGU/DAAD mechanics.
2. MGU and DAAD outputs parse as valid JSON.
3. Source outputs remain compatible with the admissions review renderer or its deliberate extension.
4. All-program scope is preserved; degree/language/study mode are not hidden extraction filters.
5. Dashboard pages visibly surface possible missed coverage and source limitations.
6. Cross-strategy comparison covers official crawler, official LLM, DAAD, and MGU.
7. Unit tests cover shared contract builder behavior, source coverage statuses, source-specific extension preservation, and strategy matching/comparison.
8. Existing `tests.test_scrape_admissions` continues to pass.
9. Documentation is updated before each implementation commit.

## Commit Strategy

Keep commits atomic:

1. Source reconnaissance and target config.
2. Shared source-scraper helpers and tests.
3. DAAD scraper and DAAD outputs.
4. My German University scraper and MGU outputs.
5. Dashboard and cross-strategy comparison.

If implementation discoveries change these boundaries, preserve the rule: one feature or behavior change per commit, with docs updated before the commit.
