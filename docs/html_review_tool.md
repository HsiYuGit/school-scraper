# Admissions HTML review tool

Use `scripts/render_admissions_html.py` when admissions JSON is hard to review by hand.
The script converts crawler JSON outputs into static HTML pages, without making
network requests or changing the source JSON.

## Render all current outputs

```powershell
python scripts\render_admissions_html.py outputs --out-dir outputs\html
```

This creates:

- `outputs/html/index.html`: manifest summary with links to school pages.
- `outputs/html/<school>_admissions.html`: one review page per admissions JSON.
- `outputs/html/nit_llm_native_admissions.html`: the LLM-native NIT draft, when `outputs/nit_llm_native_admissions.json` exists.

## Compare crawler output with LLM-native output

```powershell
python scripts\compare_admissions_outputs.py --crawler-json outputs\nit_northern_institute_of_technology_management_admissions.json --llm-json outputs\nit_llm_native_admissions.json --out outputs\html\nit_llm_vs_crawler_comparison.html
```

The comparison page highlights differences that matter for validation:

- program count and program names;
- language-test minimum scores;
- GRE/GMAT or other test interpretation;
- work-experience fields;
- method metadata for the LLM-native run, including visible model information and whether token/cost data was available.

The current NIT comparison is an experiment artifact. It shows that the crawler
rerun removed the false GRE requirement and discovered Business Analytics & AI,
but still does not match the LLM-native result because it cannot yet merge
central admissions requirements back into program records or group Technology
Management study modes into one program family.

## Render one file

```powershell
python scripts\render_admissions_html.py outputs\munich_business_school_admissions.json --out-dir outputs\html
```

## Source platform review pages

Source platform outputs render under `outputs/html/source_daad/` and `outputs/html/source_mgu/`. Pages include a Source Coverage section. Any warning status such as `bounded_search_limit_reached`, `source_partial_match`, `source_no_match`, `js_gated`, or `robots_blocked` must be treated as possible missed coverage during dashboard review.

## Cross-strategy comparison

The dashboard includes strategy comparison pages under `outputs/html/comparisons/strategy_matrix/`. Each page compares official crawler, official LLM, DAAD, and My German University where available. The index labels source review columns as `DAAD (source_daad)` and `My German University (source_mgu)` so client-facing names and route identifiers are both visible. The comparison labels programmes as matched, partially matched, or only-in-strategy and surfaces source coverage warnings before programme details.
Source record IDs are treated as strategy-local identifiers in the matrix, so ID keys include the strategy namespace. When one strategy contributes multiple records to the same programme key, the page preserves the full record list and shows per-strategy record counts.

## What to review in HTML

- School metadata, crawl limits, robots status, and crawl summary.
- Program name, URL, degree, level, campus, language, parent program, and specialization.
- Requirement taxonomy, including academic background, language tests, documents, conditional paths, and international requirements.
- Application deadlines, intakes, channels, Uni-assist/VPD notes, and fees.
- Evidence groups and raw evidence sections, including confidence and source text.
- The `Needs human review` badge on records where extraction confidence is insufficient.

The generated HTML is an output artifact for manual review. Do not edit it as
source of truth; update the scraper or JSON generation flow when the displayed
content reveals an extraction issue.

## Client dashboard

Use the dashboard renderer when preparing a self-contained folder for review:

```powershell
python scripts\render_admissions_dashboard.py --outputs-dir outputs --html-dir outputs\html
```

This keeps existing files in `outputs/html/` and adds or updates:

- `outputs/html/index.html`
- `outputs/html/comparisons/v0_3_vs_v0_4.html`
- `outputs/html/comparisons/llm_v0_1_vs_v0_2/*.html`
- `outputs/html/comparisons/v0_4_vs_llm_v0_2/*.html`
- versioned review pages for `v0_2`, `v0_3`, `v0_4`, `llm_native`, and `llm_native_v0_2`

For the current client review, open or copy the whole `outputs/html/` folder
and start from `outputs/html/index.html`.
