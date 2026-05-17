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
