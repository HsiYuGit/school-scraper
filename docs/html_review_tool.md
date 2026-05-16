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
