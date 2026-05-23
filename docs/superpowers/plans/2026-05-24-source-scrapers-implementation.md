# Source Scrapers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build source-specific DAAD and My German University admissions scrapers, output contract-compatible JSON for the 12 Gut-Haode partner schools, and add a dashboard comparison across official crawler, official LLM, DAAD, and MGU.

**Architecture:** Start with source reconnaissance and stable target configuration before writing parsers. Implement separate DAAD and MGU CLI entrypoints with a small shared `source_scraper_common.py` module for contract, evidence, manifest, status, and bounded fetch helpers. Extend the existing static HTML review/dashboard tools to render source outputs and a cross-strategy comparison matrix.

**Tech Stack:** Python standard library (`argparse`, `dataclasses`, `datetime`, `html.parser`, `json`, `pathlib`, `re`, `time`, `urllib`), existing repo renderers/tests, static HTML output, `unittest`.

---

## File Map

- Create: `docs/source_scraper_reconnaissance.md`
  - Records DAAD and My German University source mechanics, robots/access boundaries, endpoints, pagination, record IDs, and limitations.
- Create: `data/source_scraper_targets.json`
  - Stable per-source target/query config for all 12 schools.
- Create: `scripts/source_scraper_common.py`
  - Shared source-scraper dataclasses and helpers for partner loading, slugging, fetch policy, contract skeletons, evidence, manifests, coverage statuses, and JSON writing.
- Create: `scripts/scrape_daad_admissions.py`
  - DAAD-specific discovery/parsing/extraction CLI.
- Create: `scripts/scrape_mgu_admissions.py`
  - My German University-specific discovery/parsing/extraction CLI.
- Modify: `scripts/render_admissions_html.py`
  - Render source metadata, source coverage warnings, and `source_specific` sections.
- Modify: `scripts/render_admissions_dashboard.py`
  - Render `outputs/source_daad`, `outputs/source_mgu`, source manifests, and cross-strategy comparison links.
- Modify: `scripts/compare_admissions_outputs.py`
  - Add reusable programme matching and strategy comparison helpers.
- Modify: `tests/test_scrape_admissions.py`
  - Add focused tests for source targets, common helpers, renderer support, source coverage visibility, and strategy comparison.
- Modify: `docs/admissions_output_versions.md`
  - Document source output folders and strategy comparison dashboard.
- Modify: `docs/html_review_tool.md`
  - Document source review pages and warning visibility.
- Modify: `DEVELOPMENT_LOG.md`
  - Record source scraper reconnaissance and implementation notes as work progresses.

---

### Task 1: Source Reconnaissance And Target Config

**Files:**
- Create: `docs/source_scraper_reconnaissance.md`
- Create: `data/source_scraper_targets.json`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write the failing target-config test**

Add this test to `tests/test_scrape_admissions.py`:

```python
    def test_source_scraper_targets_cover_all_partner_schools(self):
        root = Path(__file__).parents[1]
        partners = json.loads((root / "data" / "partner_schools.json").read_text(encoding="utf-8"))["schools"]
        targets_path = root / "data" / "source_scraper_targets.json"
        self.assertTrue(targets_path.exists())
        targets = json.loads(targets_path.read_text(encoding="utf-8"))

        self.assertEqual(targets["schema_version"], "0.1")
        self.assertEqual({"daad", "my_german_university"}, set(targets["sources"]))
        for source_name, source in targets["sources"].items():
            self.assertIn("base_url", source)
            self.assertIn("access_policy", source)
            self.assertEqual({item["name"] for item in partners}, {item["school_name"] for item in source["schools"]}, source_name)
            for school in source["schools"]:
                self.assertIn(school["coverage_status"], {
                    "target_seeded",
                    "target_needs_recon",
                    "source_no_match",
                    "source_partial_match",
                })
                self.assertTrue(school.get("queries") or school.get("listing_urls") or school.get("detail_urls") or school["coverage_status"] == "source_no_match")
```

- [ ] **Step 2: Run the target-config test and verify it fails**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_source_scraper_targets_cover_all_partner_schools
```

Expected: `FAIL` because `data/source_scraper_targets.json` does not exist.

- [ ] **Step 3: Research DAAD and MGU source mechanics**

Use public pages and browser/network inspection where allowed. Record:

```markdown
# Source Scraper Reconnaissance

Date: 2026-05-24

## DAAD

- Base URL:
- Robots URL:
- Search entry points:
- Pagination behavior:
- Detail page pattern:
- Record ID fields:
- Public endpoint candidates:
- Listing fields:
- Detail-only fields:
- JavaScript/browser clues:
- Access limits:
- Future deepening candidates:

## My German University

- Base URL:
- Robots URL:
- Search entry points:
- Pagination behavior:
- Detail page pattern:
- Record ID fields:
- Public endpoint candidates:
- Listing fields:
- Detail-only fields:
- JavaScript/browser clues:
- Access limits:
- Future deepening candidates:
```

Save the filled version to `docs/source_scraper_reconnaissance.md`. Keep exact URLs and query parameters for any target or endpoint considered reusable.

- [ ] **Step 4: Create the target config**

Create `data/source_scraper_targets.json` with this shape. Fill every `schools` array with the 12 partner school names from `data/partner_schools.json`; use discovered target URLs where known, and `target_needs_recon` with queries where a stable URL is not yet confirmed.

```json
{
  "schema_version": "0.1",
  "generated_from": "docs/source_scraper_reconnaissance.md",
  "scope": {
    "partner_schools_path": "data/partner_schools.json",
    "programme_scope": "all programmes exposed by each source for the partner school",
    "no_hidden_filters": [
      "degree_level",
      "language_of_instruction",
      "study_mode",
      "application_availability"
    ],
    "no_official_school_fallback": true
  },
  "sources": {
    "daad": {
      "label": "DAAD",
      "base_url": "https://www.daad.de/",
      "access_policy": {
        "respect_robots_txt": true,
        "same_source_only": true,
        "no_login_captcha_bypass": true,
        "default_timeout_seconds": 15,
        "default_delay_seconds": 1.0
      },
      "schools": []
    },
    "my_german_university": {
      "label": "My German University",
      "base_url": "https://www.mygermanuniversity.com/",
      "access_policy": {
        "respect_robots_txt": true,
        "same_source_only": true,
        "no_login_captcha_bypass": true,
        "default_timeout_seconds": 15,
        "default_delay_seconds": 1.0
      },
      "schools": []
    }
  }
}
```

Each school entry should use:

```json
{
  "school_name": "Munich Business School",
  "school_aliases": ["Munich Business School", "MBS"],
  "coverage_status": "target_seeded",
  "queries": ["Munich Business School"],
  "listing_urls": [],
  "detail_urls": [],
  "source_school_ids": [],
  "notes": [],
  "future_deepening_candidates": []
}
```

- [ ] **Step 5: Run the target-config test and verify it passes**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_source_scraper_targets_cover_all_partner_schools
```

Expected: `OK`.

- [ ] **Step 6: Update docs and commit Task 1**

Append a short entry to `DEVELOPMENT_LOG.md` under `## 2026-05-24`:

```markdown
### Source scraper reconnaissance planning

- Recorded DAAD and My German University source mechanics in `docs/source_scraper_reconnaissance.md`.
- Added `data/source_scraper_targets.json` as the stable 12-school source target map for later DAAD/MGU scrapers.
- Preserved all-program scope: degree, language, study mode, and application availability are metadata only, not extraction filters.
```

Run:

```powershell
python -m json.tool data\source_scraper_targets.json
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_source_scraper_targets_cover_all_partner_schools
```

Expected: both commands exit `0`.

Commit:

```powershell
git add docs\source_scraper_reconnaissance.md data\source_scraper_targets.json tests\test_scrape_admissions.py DEVELOPMENT_LOG.md
git commit -m "Add source scraper reconnaissance targets" -m "Record DAAD and My German University source mechanics and add a stable 12-school target map before implementing source-specific parsers."
```

---

### Task 2: Shared Source Scraper Common Module

**Files:**
- Create: `scripts/source_scraper_common.py`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `docs/admissions_output_versions.md`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write failing tests for shared helpers**

Add imports near the top of `tests/test_scrape_admissions.py`:

```python
from scripts.source_scraper_common import (
    COVERAGE_STATUSES,
    SourceProgram,
    build_source_output,
    coverage_warning,
    source_slug,
)
```

Add tests:

```python
    def test_source_common_preserves_contract_and_source_specific(self):
        program = SourceProgram(
            source_record_id="daad-w7513",
            source_listing_url="https://www.daad.de/example-list",
            source_detail_url="https://www.daad.de/example-detail",
            name="Master International Business",
            degree="MA",
            level="master",
            language_of_instruction=["English"],
            requirements={"language_requirements": [{"test": "IELTS", "minimum_score": "6.5"}]},
            application={"deadlines": ["15 July"], "fees": ["EUR 50 application fee"]},
            evidence_key="language_requirements",
            evidence_text="IELTS 6.5",
            source_specific={"daad_subject_group": "Business"},
            needs_human_review=False,
        )
        output = build_source_output(
            source_platform="daad",
            source_label="DAAD",
            school={"name": "Munich Business School", "url": "https://www.munich-business-school.de/en/"},
            programmes=[program],
            coverage_status="complete_within_configured_targets",
            limitation_notes=[],
            future_deepening_candidates=[],
        )

        self.assertEqual(output["schema_version"], "0.4-source")
        self.assertEqual(output["source_platform"], "daad")
        self.assertEqual(output["source_coverage"]["status"], "complete_within_configured_targets")
        self.assertEqual(output["programs"][0]["program"]["name"], "Master International Business")
        self.assertIn("requirements", output["programs"][0])
        self.assertEqual(output["programs"][0]["source_specific"]["daad_subject_group"], "Business")
        self.assertEqual(output["programs"][0]["source_record_id"], "daad-w7513")

    def test_source_coverage_warning_marks_possible_missed_programmes(self):
        self.assertTrue(coverage_warning("bounded_search_limit_reached"))
        self.assertTrue(coverage_warning("source_partial_match"))
        self.assertFalse(coverage_warning("complete_within_configured_targets"))
        self.assertIn("robots_blocked", COVERAGE_STATUSES)
        self.assertEqual(source_slug("My German University"), "my_german_university")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_source_common_preserves_contract_and_source_specific tests.test_scrape_admissions.AdmissionExtractionTest.test_source_coverage_warning_marks_possible_missed_programmes
```

Expected: `ERROR` because `scripts.source_scraper_common` is missing.

- [ ] **Step 3: Implement the shared module**

Create `scripts/source_scraper_common.py`:

```python
"""Shared helpers for source-specific admissions scrapers."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import Any, Iterable


DEFAULT_USER_AGENT = "study-admissions-source-scraper/0.1 (+https://www.gut-haode.com/ partner-school research)"
PARTNER_SCHOOLS_PATH = Path("data/partner_schools.json")
SOURCE_TARGETS_PATH = Path("data/source_scraper_targets.json")

COVERAGE_STATUSES = {
    "complete_within_configured_targets",
    "target_seeded",
    "target_needs_recon",
    "source_partial_match",
    "bounded_search_limit_reached",
    "source_no_match",
    "source_limited",
    "js_gated",
    "robots_blocked",
    "endpoint_candidate_found",
}

WARNING_STATUSES = {
    "target_needs_recon",
    "source_partial_match",
    "bounded_search_limit_reached",
    "source_no_match",
    "source_limited",
    "js_gated",
    "robots_blocked",
    "endpoint_candidate_found",
}


@dataclasses.dataclass(frozen=True)
class SourceProgram:
    source_record_id: str | None
    source_listing_url: str | None
    source_detail_url: str | None
    name: str
    degree: str | None = None
    level: str | None = None
    campus: str | None = None
    language_of_instruction: list[str] = dataclasses.field(default_factory=list)
    requirements: dict[str, Any] = dataclasses.field(default_factory=dict)
    application: dict[str, Any] = dataclasses.field(default_factory=dict)
    evidence_key: str = "source_record"
    evidence_text: str = ""
    source_specific: dict[str, Any] = dataclasses.field(default_factory=dict)
    needs_human_review: bool = True


def source_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
    return slug or "source"


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_partner_schools(path: Path = PARTNER_SCHOOLS_PATH) -> list[dict[str, Any]]:
    return load_json(path)["schools"]


def empty_requirements() -> dict[str, Any]:
    return {
        "academic_background": {"degree_level": None, "minimum_ects": None, "recognized_institution": None, "minimum_grade": None, "notes": []},
        "subject_prerequisites": [],
        "language_requirements": [],
        "test_requirements": [],
        "work_experience": {"minimum_years": None, "relevance": None, "notes": []},
        "documents": [],
        "conditional_paths": [],
        "international_requirements": [],
    }


def empty_application() -> dict[str, Any]:
    return {
        "deadlines": [],
        "intakes": [],
        "application_channel": None,
        "uni_assist_or_vpd": None,
        "fees": [],
    }


def merge_contract_defaults(value: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(defaults, ensure_ascii=False))
    for key, item in (value or {}).items():
        if isinstance(item, dict) and isinstance(merged.get(key), dict):
            merged[key].update(item)
        else:
            merged[key] = item
    return merged


def evidence_item(source_url: str | None, source_text: str, retrieved_at: str, confidence: str = "medium", review_note: str = "Source-platform extraction.") -> dict[str, Any]:
    return {
        "source_url": source_url,
        "source_text": normalize_space(source_text)[:500],
        "retrieved_at": retrieved_at,
        "confidence": confidence,
        "review_note": review_note,
    }


def program_to_record(programme: SourceProgram, school: dict[str, Any], retrieved_at: str) -> dict[str, Any]:
    detail_url = programme.source_detail_url or programme.source_listing_url
    return {
        "school": school,
        "program": {
            "name": programme.name,
            "degree": programme.degree,
            "level": programme.level,
            "url": detail_url,
            "campus": programme.campus,
            "language_of_instruction": programme.language_of_instruction,
            "parent_program": None,
            "specialization": None,
        },
        "requirements": merge_contract_defaults(programme.requirements, empty_requirements()),
        "application": merge_contract_defaults(programme.application, empty_application()),
        "evidence": {
            programme.evidence_key: [
                evidence_item(detail_url, programme.evidence_text or programme.name, retrieved_at)
            ]
        },
        "raw_evidence_sections": [
            {
                "heading": "Source platform record",
                "source_url": detail_url,
                "text": programme.evidence_text or programme.name,
            }
        ],
        "needs_human_review": programme.needs_human_review,
        "source_record_id": programme.source_record_id,
        "source_listing_url": programme.source_listing_url,
        "source_detail_url": programme.source_detail_url,
        "source_specific": programme.source_specific,
    }


def coverage_warning(status: str) -> bool:
    return status in WARNING_STATUSES


def build_source_output(
    source_platform: str,
    source_label: str,
    school: dict[str, Any],
    programmes: Iterable[SourceProgram],
    coverage_status: str,
    limitation_notes: list[str],
    future_deepening_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if coverage_status not in COVERAGE_STATUSES:
        raise ValueError(f"Unknown source coverage status: {coverage_status}")
    retrieved_at = utc_now()
    programme_records = [program_to_record(programme, school, retrieved_at) for programme in programmes]
    return {
        "schema_version": "0.4-source",
        "source_platform": source_platform,
        "source_label": source_label,
        "school": school,
        "retrieved_at": retrieved_at,
        "source_coverage": {
            "status": coverage_status,
            "warning": coverage_warning(coverage_status),
            "programs_extracted": len(programme_records),
            "limitation_notes": limitation_notes,
            "future_deepening_candidates": future_deepening_candidates,
        },
        "programs": programme_records,
        "skipped": [],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_text(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: float = 15.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")
```

- [ ] **Step 4: Run shared-helper tests and verify they pass**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_source_common_preserves_contract_and_source_specific tests.test_scrape_admissions.AdmissionExtractionTest.test_source_coverage_warning_marks_possible_missed_programmes
```

Expected: `OK`.

- [ ] **Step 5: Update docs and commit Task 2**

Add a `## Source platform outputs` section to `docs/admissions_output_versions.md`:

```markdown
## Source platform outputs

`outputs/source_daad/` and `outputs/source_mgu/` are reserved for source-specific admissions outputs. These files use `schema_version = 0.4-source`, keep the shared programme contract, and add source metadata such as `source_platform`, `source_record_id`, `source_listing_url`, `source_detail_url`, `source_coverage`, and per-programme `source_specific`.

Coverage statuses with `source_coverage.warning = true` must be surfaced in the dashboard because they can mean missed programmes.
```

Append to `DEVELOPMENT_LOG.md`:

```markdown
### Shared source-scraper contract helpers

- Added `scripts/source_scraper_common.py` for source-specific scraper contract output, evidence, coverage statuses, and source-specific extension fields.
- Added tests to protect source output compatibility with the existing admissions review model.
```

Run:

```powershell
python -m unittest tests.test_scrape_admissions
python -m py_compile scripts\source_scraper_common.py tests\test_scrape_admissions.py
```

Expected: all tests pass; py_compile exits `0`.

Commit:

```powershell
git add scripts\source_scraper_common.py tests\test_scrape_admissions.py docs\admissions_output_versions.md DEVELOPMENT_LOG.md
git commit -m "Add source scraper contract helpers" -m "Introduce shared helpers for source-specific admissions outputs so DAAD and MGU scrapers can preserve the existing contract while recording source metadata and coverage warnings."
```

---

### Task 3: DAAD Scraper And Outputs

**Files:**
- Create: `scripts/scrape_daad_admissions.py`
- Create/update: `outputs/source_daad/*.json`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `docs/source_scraper_reconnaissance.md`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write failing DAAD parser tests with fixture HTML**

Add a fixture-style test to `tests/test_scrape_admissions.py`:

```python
    def test_daad_detail_parser_extracts_contract_programme(self):
        from scripts.scrape_daad_admissions import parse_daad_detail

        html = """
        <html><body>
          <h1>Master International Business</h1>
          <dl>
            <dt>Degree</dt><dd>Master of Arts</dd>
            <dt>Course language</dt><dd>English</dd>
            <dt>Beginning</dt><dd>Winter semester</dd>
            <dt>Application deadline</dt><dd>15 July</dd>
            <dt>Tuition fees</dt><dd>6,000 EUR per semester</dd>
          </dl>
          <section><h2>Admission requirements</h2>
            <p>Bachelor degree with 180 ECTS and proof of English language proficiency IELTS 6.5.</p>
          </section>
        </body></html>
        """

        programme = parse_daad_detail(
            html,
            detail_url="https://www.daad.de/example?w=w7513",
            listing_url="https://www.daad.de/search",
            record_id="w7513",
        )

        self.assertEqual(programme.source_record_id, "w7513")
        self.assertEqual(programme.name, "Master International Business")
        self.assertEqual(programme.degree, "Master of Arts")
        self.assertEqual(programme.level, "master")
        self.assertIn("English", programme.language_of_instruction)
        self.assertIn("15 July", programme.application["deadlines"])
        self.assertIn("6,000 EUR per semester", programme.application["fees"])
        self.assertEqual(programme.source_specific["source_platform"], "daad")
```

- [ ] **Step 2: Run DAAD parser test and verify it fails**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_daad_detail_parser_extracts_contract_programme
```

Expected: `ERROR` because `scripts.scrape_daad_admissions` is missing.

- [ ] **Step 3: Implement DAAD parser and CLI skeleton**

Create `scripts/scrape_daad_admissions.py` with:

```python
"""Scrape DAAD admissions records into the source admissions contract."""

from __future__ import annotations

import argparse
import html.parser
import json
import re
from pathlib import Path
from typing import Any, Iterable

try:
    from source_scraper_common import (
        DEFAULT_USER_AGENT,
        SOURCE_TARGETS_PATH,
        SourceProgram,
        build_source_output,
        load_json,
        load_partner_schools,
        normalize_space,
        source_slug,
        write_json,
    )
except ModuleNotFoundError:
    from scripts.source_scraper_common import (
        DEFAULT_USER_AGENT,
        SOURCE_TARGETS_PATH,
        SourceProgram,
        build_source_output,
        load_json,
        load_partner_schools,
        normalize_space,
        source_slug,
        write_json,
    )


DEFAULT_OUTPUT_DIR = Path("outputs/source_daad")


class SimpleTextParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag.lower() in {"h1", "h2", "h3", "p", "dt", "dd", "li"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag.lower() in {"h1", "h2", "h3", "p", "dt", "dd", "li"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = normalize_space(data)
        if text:
            self._current.append(text)

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        if self._current:
            value = normalize_space(" ".join(self._current))
            if value:
                self.blocks.append(value)
        self._current = []


def blocks_from_html(html: str) -> list[str]:
    parser = SimpleTextParser()
    parser.feed(html)
    parser.close()
    return parser.blocks


def first_after(blocks: list[str], labels: tuple[str, ...]) -> str | None:
    lower_labels = {label.lower() for label in labels}
    for index, block in enumerate(blocks[:-1]):
        if block.lower().strip(":") in lower_labels:
            return blocks[index + 1]
    return None


def infer_level(name: str, degree: str | None) -> str | None:
    haystack = f"{name} {degree or ''}".lower()
    if "bachelor" in haystack:
        return "bachelor"
    if "master" in haystack or "mba" in haystack or "m.sc" in haystack or "m.a" in haystack:
        return "master"
    if "phd" in haystack or "doctor" in haystack:
        return "doctoral"
    return None


def parse_daad_detail(html: str, detail_url: str, listing_url: str | None, record_id: str | None) -> SourceProgram:
    blocks = blocks_from_html(html)
    name = blocks[0] if blocks else "Unnamed DAAD programme"
    degree = first_after(blocks, ("Degree", "Final degree"))
    language = first_after(blocks, ("Course language", "Languages"))
    deadline = first_after(blocks, ("Application deadline", "Application deadlines"))
    fees = first_after(blocks, ("Tuition fees", "Fees"))
    beginning = first_after(blocks, ("Beginning", "Start"))
    admission_text = " ".join(block for block in blocks if re.search(r"admission|requirement|ielts|toefl|ects", block, re.IGNORECASE))
    application = {
        "deadlines": [deadline] if deadline else [],
        "intakes": [beginning] if beginning else [],
        "fees": [fees] if fees else [],
    }
    requirements = {
        "language_requirements": [{"test": "IELTS", "minimum_score": "6.5"}] if re.search(r"IELTS\s*6\.5", admission_text, re.IGNORECASE) else [],
        "academic_background": {"notes": [admission_text] if admission_text else []},
    }
    return SourceProgram(
        source_record_id=record_id,
        source_listing_url=listing_url,
        source_detail_url=detail_url,
        name=name,
        degree=degree,
        level=infer_level(name, degree),
        language_of_instruction=[language] if language else [],
        requirements=requirements,
        application=application,
        evidence_key="daad_detail",
        evidence_text=admission_text or " ".join(blocks[:8]),
        source_specific={
            "source_platform": "daad",
            "raw_blocks": blocks[:40],
        },
        needs_human_review=not admission_text,
    )
```

Add these CLI helpers below `parse_daad_detail`:

```python
def load_source_targets(path: Path) -> list[dict[str, Any]]:
    targets = load_json(path)
    return targets["sources"]["daad"]["schools"]


def partner_by_name() -> dict[str, dict[str, Any]]:
    return {school["name"]: school for school in load_partner_schools()}


def build_no_match_output(target: dict[str, Any], partner: dict[str, Any]) -> dict[str, Any]:
    return build_source_output(
        source_platform="daad",
        source_label="DAAD",
        school={
            "name": partner["name"],
            "url": partner["official_url"],
            "country": partner.get("country"),
            "partner_status": partner.get("partner_status"),
            "school_type": partner.get("school_type"),
        },
        programmes=[],
        coverage_status="source_no_match",
        limitation_notes=[f"No DAAD detail URLs configured for {target['school_name']}."],
        future_deepening_candidates=target.get("future_deepening_candidates", []),
    )


def scrape_target(target: dict[str, Any], partner: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    programmes: list[SourceProgram] = []
    limitation_notes: list[str] = []
    for detail_url in target.get("detail_urls", []):
        html = Path(detail_url).read_text(encoding="utf-8") if detail_url.startswith("fixture://") else ""
        if not html:
            limitation_notes.append(f"Network fetch for {detail_url} is implemented after reconnaissance confirms the stable endpoint.")
            continue
        programmes.append(parse_daad_detail(html, detail_url, target.get("listing_urls", [None])[0], None))
    if not programmes:
        return build_no_match_output(target, partner)
    return build_source_output(
        source_platform="daad",
        source_label="DAAD",
        school={
            "name": partner["name"],
            "url": partner["official_url"],
            "country": partner.get("country"),
            "partner_status": partner.get("partner_status"),
            "school_type": partner.get("school_type"),
        },
        programmes=programmes,
        coverage_status="complete_within_configured_targets" if not limitation_notes else "source_partial_match",
        limitation_notes=limitation_notes,
        future_deepening_candidates=target.get("future_deepening_candidates", []),
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape DAAD source admissions records.")
    parser.add_argument("--targets", default=str(SOURCE_TARGETS_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    partners = partner_by_name()
    output_dir = Path(args.output_dir)
    manifest_entries = []
    for target in load_source_targets(Path(args.targets)):
        partner = partners[target["school_name"]]
        output = scrape_target(target, partner, args)
        output_path = output_dir / f"{source_slug(partner['name'])}_admissions.json"
        write_json(output_path, output)
        manifest_entries.append({
            "school": partner["name"],
            "source_platform": "daad",
            "output_path": str(output_path),
            "coverage_status": output["source_coverage"]["status"],
            "warning": output["source_coverage"]["warning"],
            "programs_extracted": len(output["programs"]),
            "limitation_notes": output["source_coverage"]["limitation_notes"],
        })
    manifest = {
        "schema_version": "0.1",
        "source_platform": "daad",
        "school_count": len(manifest_entries),
        "schools": manifest_entries,
    }
    write_json(output_dir / "source_daad_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

During implementation, replace the temporary `fixture://` branch with the confirmed DAAD public fetch/search path from `docs/source_scraper_reconnaissance.md`; keep the same function boundaries and tests.

- [ ] **Step 4: Run DAAD parser test and verify it passes**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_daad_detail_parser_extracts_contract_programme
```

Expected: `OK`.

- [ ] **Step 5: Run DAAD scraper for all 12 configured schools**

Run with bounded settings derived from reconnaissance:

```powershell
python scripts\scrape_daad_admissions.py --targets data\source_scraper_targets.json --output-dir outputs\source_daad --timeout 15 --delay 1
```

Expected:

- `outputs/source_daad/source_daad_manifest.json` exists.
- 12 per-school JSON files exist, even if some have `programs: []`.
- Any partial/no-match/limited result has `source_coverage.warning = true`.

- [ ] **Step 6: Validate DAAD outputs**

Run:

```powershell
python -m json.tool outputs\source_daad\source_daad_manifest.json
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_daad_detail_parser_extracts_contract_programme
python -m py_compile scripts\scrape_daad_admissions.py
```

Also run a JSON sweep:

```powershell
Get-ChildItem outputs\source_daad -Filter *.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
```

Expected: all commands exit `0`.

- [ ] **Step 7: Update docs and commit Task 3**

Append DAAD implementation notes to `DEVELOPMENT_LOG.md` and add any new DAAD source mechanics discovered during implementation to `docs/source_scraper_reconnaissance.md`.

Commit:

```powershell
git add scripts\scrape_daad_admissions.py outputs\source_daad docs\source_scraper_reconnaissance.md DEVELOPMENT_LOG.md tests\test_scrape_admissions.py
git commit -m "Add DAAD source admissions scraper" -m "Implement the DAAD-specific admissions source scraper, generate 12-school source outputs, and record coverage limitations for dashboard review."
```

---

### Task 4: My German University Scraper And Outputs

**Files:**
- Create: `scripts/scrape_mgu_admissions.py`
- Create/update: `outputs/source_mgu/*.json`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `docs/source_scraper_reconnaissance.md`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write failing MGU parser test with fixture HTML**

Add to `tests/test_scrape_admissions.py`:

```python
    def test_mgu_detail_parser_preserves_source_specific_fields(self):
        from scripts.scrape_mgu_admissions import parse_mgu_detail

        html = """
        <html><body>
          <h1>Innovation and Entrepreneurship</h1>
          <span>Master of Arts</span>
          <section><h2>Overview</h2>
            <p>Teaching language: English</p>
            <p>Duration: 4 semesters</p>
            <p>Tuition fees: 5,000 EUR per semester</p>
          </section>
          <section><h2>Admission Requirements</h2>
            <p>Applicants need a Bachelor's degree and proof of English, e.g. IELTS 6.5.</p>
          </section>
        </body></html>
        """

        programme = parse_mgu_detail(
            html,
            detail_url="https://www.mygermanuniversity.com/master/innovation-and-entrepreneurship/1692",
            listing_url="https://www.mygermanuniversity.com/universities/Munich-Business-School",
            record_id="1692",
        )

        self.assertEqual(programme.source_record_id, "1692")
        self.assertEqual(programme.name, "Innovation and Entrepreneurship")
        self.assertEqual(programme.level, "master")
        self.assertIn("English", programme.language_of_instruction)
        self.assertIn("duration", programme.source_specific)
        self.assertIn("5,000 EUR per semester", programme.application["fees"])
```

- [ ] **Step 2: Run MGU parser test and verify it fails**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_mgu_detail_parser_preserves_source_specific_fields
```

Expected: `ERROR` because `scripts.scrape_mgu_admissions` is missing.

- [ ] **Step 3: Implement MGU parser and CLI skeleton**

Create `scripts/scrape_mgu_admissions.py` with source-specific parser names and the same CLI boundary names used by the DAAD script (`load_source_targets`, `partner_by_name`, `scrape_target`, `parse_args`, `main`). Include this parser function:

```python
def parse_mgu_detail(html: str, detail_url: str, listing_url: str | None, record_id: str | None) -> SourceProgram:
    blocks = blocks_from_html(html)
    name = blocks[0] if blocks else "Unnamed MGU programme"
    joined = " ".join(blocks)
    degree = next((block for block in blocks[:8] if re.search(r"\b(Bachelor|Master|MBA|M\.A\.|M\.Sc\.)\b", block, re.IGNORECASE)), None)
    language = "English" if re.search(r"Teaching language:\s*English|Language:\s*English", joined, re.IGNORECASE) else None
    duration_match = re.search(r"Duration:\s*([^.;]+)", joined, re.IGNORECASE)
    fee_match = re.search(r"Tuition fees:\s*([^.;]+)", joined, re.IGNORECASE)
    ielts_match = re.search(r"IELTS\s*(\d+(?:\.\d+)?)", joined, re.IGNORECASE)
    requirements = {
        "language_requirements": [{"test": "IELTS", "minimum_score": ielts_match.group(1)}] if ielts_match else [],
        "academic_background": {"notes": [block for block in blocks if re.search(r"degree|admission requirement", block, re.IGNORECASE)][:5]},
    }
    application = {
        "deadlines": [],
        "intakes": [],
        "fees": [fee_match.group(1)] if fee_match else [],
    }
    return SourceProgram(
        source_record_id=record_id,
        source_listing_url=listing_url,
        source_detail_url=detail_url,
        name=name,
        degree=degree,
        level=infer_level(name, degree),
        language_of_instruction=[language] if language else [],
        requirements=requirements,
        application=application,
        evidence_key="mgu_detail",
        evidence_text=joined[:500],
        source_specific={
            "source_platform": "my_german_university",
            "duration": duration_match.group(1) if duration_match else None,
            "raw_blocks": blocks[:40],
        },
        needs_human_review=not bool(blocks),
    )
```

Reuse `SimpleTextParser`, `blocks_from_html`, and `infer_level` from the DAAD file only by copying minimal source-specific equivalents or moving proven generic text parsing to `source_scraper_common.py` in the same commit with tests. Do not import DAAD parser code from the MGU script.

- [ ] **Step 4: Run MGU parser test and verify it passes**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_mgu_detail_parser_preserves_source_specific_fields
```

Expected: `OK`.

- [ ] **Step 5: Run MGU scraper for all 12 configured schools**

Run:

```powershell
python scripts\scrape_mgu_admissions.py --targets data\source_scraper_targets.json --output-dir outputs\source_mgu --timeout 15 --delay 1
```

Expected:

- `outputs/source_mgu/source_mgu_manifest.json` exists.
- 12 per-school JSON files exist.
- Any partial/no-match/limited result has `source_coverage.warning = true`.

- [ ] **Step 6: Validate MGU outputs**

Run:

```powershell
python -m json.tool outputs\source_mgu\source_mgu_manifest.json
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_mgu_detail_parser_preserves_source_specific_fields
python -m py_compile scripts\scrape_mgu_admissions.py
Get-ChildItem outputs\source_mgu -Filter *.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
```

Expected: all commands exit `0`.

- [ ] **Step 7: Update docs and commit Task 4**

Append MGU implementation notes to `DEVELOPMENT_LOG.md` and add new MGU mechanics discovered during implementation to `docs/source_scraper_reconnaissance.md`.

Commit:

```powershell
git add scripts\scrape_mgu_admissions.py outputs\source_mgu docs\source_scraper_reconnaissance.md DEVELOPMENT_LOG.md tests\test_scrape_admissions.py
git commit -m "Add MGU source admissions scraper" -m "Implement the My German University source scraper, generate 12-school source outputs, and preserve source-specific fields for later contract expansion."
```

---

### Task 5: Source HTML Review Rendering

**Files:**
- Modify: `scripts/render_admissions_html.py`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `docs/html_review_tool.md`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write failing renderer test for source coverage warnings**

Add to `tests/test_scrape_admissions.py`:

```python
    def test_renders_source_coverage_warning_to_html(self):
        from scripts.source_scraper_common import SourceProgram, build_source_output

        root = Path(__file__).parents[1]
        output_dir = root / "outputs" / "_test_html_source"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        payload = build_source_output(
            source_platform="daad",
            source_label="DAAD",
            school={"name": "Example School", "url": "https://example.edu/"},
            programmes=[
                SourceProgram(
                    source_record_id="x1",
                    source_listing_url="https://daad.example/list",
                    source_detail_url="https://daad.example/detail",
                    name="Example Programme",
                    evidence_text="IELTS 6.5",
                    source_specific={"raw_duration": "4 semesters"},
                )
            ],
            coverage_status="bounded_search_limit_reached",
            limitation_notes=["Only first 20 search records inspected."],
            future_deepening_candidates=[{"strategy": "inspect_public_endpoint", "reason": "Load-more request observed."}],
        )
        source_path = output_dir / "example_source.json"
        output_dir.mkdir(parents=True)
        source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        html_path = render_file(source_path, output_dir)
        html = html_path.read_text(encoding="utf-8")

        self.assertIn("Source Coverage", html)
        self.assertIn("bounded_search_limit_reached", html)
        self.assertIn("Only first 20 search records inspected.", html)
        self.assertIn("source_specific", html)

        shutil.rmtree(output_dir)
```

- [ ] **Step 2: Run renderer test and verify it fails**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_renders_source_coverage_warning_to_html
```

Expected: `FAIL` because the renderer does not display source coverage.

- [ ] **Step 3: Extend renderer summary**

In `scripts/render_admissions_html.py`, update `render_summary` to include:

```python
    if payload.get("source_coverage") or payload.get("source_platform"):
        coverage = payload.get("source_coverage", {})
        body.extend(
            [
                "<section>",
                "<h2>Source Coverage</h2>",
                render_meta_grid(
                    {
                        "source_platform": payload.get("source_platform"),
                        "source_label": payload.get("source_label"),
                        "status": coverage.get("status"),
                        "warning": coverage.get("warning"),
                        "programs_extracted": coverage.get("programs_extracted"),
                        "limitations": coverage.get("limitation_notes"),
                        "future_deepening_candidates": coverage.get("future_deepening_candidates"),
                    }
                ),
                "</section>",
            ]
        )
```

In `render_program`, add source metadata after the normal program meta grid:

```python
            render_meta_grid(
                {
                    "source_record_id": program_record.get("source_record_id"),
                    "source_listing_url": program_record.get("source_listing_url"),
                    "source_detail_url": program_record.get("source_detail_url"),
                    "source_specific": program_record.get("source_specific"),
                }
            ) if program_record.get("source_record_id") or program_record.get("source_specific") else "",
```

- [ ] **Step 4: Run renderer test and verify it passes**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_renders_source_coverage_warning_to_html
```

Expected: `OK`.

- [ ] **Step 5: Render source HTML pages**

Run:

```powershell
python scripts\render_admissions_html.py outputs\source_daad --out-dir outputs\html\source_daad
python scripts\render_admissions_html.py outputs\source_mgu --out-dir outputs\html\source_mgu
```

Expected: source review HTML files are created and include source coverage sections.

- [ ] **Step 6: Update docs and commit Task 5**

Add to `docs/html_review_tool.md`:

```markdown
## Source platform review pages

Source platform outputs render under `outputs/html/source_daad/` and `outputs/html/source_mgu/`. Pages include a Source Coverage section. Any warning status such as `bounded_search_limit_reached`, `source_partial_match`, `source_no_match`, `js_gated`, or `robots_blocked` must be treated as possible missed coverage during dashboard review.
```

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_renders_source_coverage_warning_to_html
python -m py_compile scripts\render_admissions_html.py
```

Commit:

```powershell
git add scripts\render_admissions_html.py tests\test_scrape_admissions.py docs\html_review_tool.md DEVELOPMENT_LOG.md outputs\html\source_daad outputs\html\source_mgu
git commit -m "Render source scraper coverage warnings" -m "Extend the admissions HTML review pages so DAAD and MGU source outputs expose coverage limits, source metadata, and source-specific fields during dashboard review."
```

---

### Task 6: Cross-Strategy Comparison Dashboard

**Files:**
- Modify: `scripts/compare_admissions_outputs.py`
- Modify: `scripts/render_admissions_dashboard.py`
- Modify: `tests/test_scrape_admissions.py`
- Modify: `docs/html_review_tool.md`
- Modify: `DEVELOPMENT_LOG.md`

- [ ] **Step 1: Write failing strategy matching test**

Add to `tests/test_scrape_admissions.py`:

```python
    def test_strategy_comparison_labels_only_in_sources(self):
        from scripts.compare_admissions_outputs import build_strategy_matrix

        official = {
            "school": {"name": "Example School"},
            "programs": [
                {"program": {"name": "Shared Programme", "degree": "MSc", "level": "master", "url": "https://official/shared"}, "requirements": {}, "application": {}, "needs_human_review": False}
            ],
        }
        daad = {
            "school": {"name": "Example School"},
            "source_coverage": {"status": "bounded_search_limit_reached", "warning": True},
            "programs": [
                {"program": {"name": "Shared Programme", "degree": "MSc", "level": "master", "url": "https://daad/shared"}, "source_record_id": "d1", "requirements": {}, "application": {}, "needs_human_review": False},
                {"program": {"name": "DAAD Only", "degree": "BA", "level": "bachelor", "url": "https://daad/only"}, "source_record_id": "d2", "requirements": {}, "application": {}, "needs_human_review": True},
            ],
        }

        matrix = build_strategy_matrix({"official_crawler": official, "daad": daad})

        statuses = {row["status"] for row in matrix["programmes"]}
        self.assertIn("matched", statuses)
        self.assertIn("only_in_daad", statuses)
        self.assertIn("bounded_search_limit_reached", matrix["coverage_warnings"])
```

- [ ] **Step 2: Run strategy matching test and verify it fails**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_strategy_comparison_labels_only_in_sources
```

Expected: `ERROR` because `build_strategy_matrix` is missing.

- [ ] **Step 3: Implement strategy matrix helpers**

Add to `scripts/compare_admissions_outputs.py`:

```python
def normalize_program_key(record: dict[str, Any]) -> str:
    program = record.get("program", {})
    name = (program.get("name") or "").lower()
    degree = (program.get("degree") or "").lower()
    level = (program.get("level") or "").lower()
    source_id = (record.get("source_record_id") or "").lower()
    if source_id:
        return f"id:{source_id}"
    return "name:" + " ".join(f"{name} {degree} {level}".split())


def build_strategy_matrix(strategies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    coverage_warnings: list[str] = []
    grouped: dict[str, dict[str, Any]] = {}
    for strategy_name, payload in strategies.items():
        coverage = payload.get("source_coverage", {})
        if coverage.get("warning") and coverage.get("status"):
            coverage_warnings.append(coverage["status"])
        for record in payload.get("programs", []):
            key = normalize_program_key(record)
            grouped.setdefault(key, {"records": {}})
            grouped[key]["records"][strategy_name] = record

    programmes: list[dict[str, Any]] = []
    strategy_names = set(strategies)
    for key, item in sorted(grouped.items()):
        present = set(item["records"])
        if len(present) == 1:
            only = next(iter(present))
            status = f"only_in_{only}"
        elif present == strategy_names:
            status = "matched"
        else:
            status = "partially_matched"
        programmes.append({"key": key, "status": status, "present_in": sorted(present), "records": item["records"]})
    return {"coverage_warnings": sorted(set(coverage_warnings)), "programmes": programmes}
```

- [ ] **Step 4: Run strategy matching test and verify it passes**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_strategy_comparison_labels_only_in_sources
```

Expected: `OK`.

- [ ] **Step 5: Add dashboard source directories and strategy pages**

In `scripts/render_admissions_dashboard.py`:

1. Update `render_reviews` to include `source_daad` and `source_mgu`.
2. Add `index_by_school(outputs_dir / "source_daad")` and `index_by_school(outputs_dir / "source_mgu")`.
3. Add a `render_strategy_matrix_pages(outputs_dir, html_dir)` function that loads available school payloads from:
   - `outputs/v0_4`
   - `outputs/v0_3/llm_native_v0_2`
   - `outputs/source_daad`
   - `outputs/source_mgu`
4. Write per-school pages under `outputs/html/comparisons/strategy_matrix/<school>.html`.
5. Add strategy matrix links and warning badges to `index.html`.

The per-school page should include this concrete structure:

```html
<h1>{school}: strategy comparison</h1>
<section><h2>Coverage Warnings</h2><ul><li>{warning_status}</li></ul></section>
<section><h2>Programme Matching</h2><table><thead><tr><th>Status</th><th>Present In</th><th>Programme Key</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Full Strategy JSON</h2><details><summary>Payloads</summary><pre>{json}</pre></details></section>
```

- [ ] **Step 6: Extend dashboard test**

Modify `test_dashboard_includes_client_comparison_routes` to assert:

```python
            self.assertIn("Strategy comparison", html)
            self.assertIn("source_daad", html)
            self.assertIn("source_mgu", html)
            self.assertTrue((output_dir / "comparisons" / "strategy_matrix").exists())
```

- [ ] **Step 7: Run dashboard tests**

Run:

```powershell
python -m unittest tests.test_scrape_admissions.AdmissionExtractionTest.test_strategy_comparison_labels_only_in_sources tests.test_scrape_admissions.AdmissionExtractionTest.test_dashboard_includes_client_comparison_routes
```

Expected: `OK`.

- [ ] **Step 8: Regenerate dashboard**

Run:

```powershell
python scripts\render_admissions_dashboard.py --outputs-dir outputs --html-dir outputs\html
```

Expected JSON output includes a count for strategy matrix pages and `outputs/html/index.html` links to strategy comparisons.

- [ ] **Step 9: Run link/content verification**

Run:

```powershell
python -m unittest tests.test_scrape_admissions
python -m py_compile scripts\compare_admissions_outputs.py scripts\render_admissions_dashboard.py scripts\render_admissions_html.py
```

Then run a static link sweep over `outputs/html` using a short script or existing project pattern:

```powershell
@'
from pathlib import Path
from html.parser import HTMLParser

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("http://", "https://", "mailto:")):
                self.links.append(href.split("#", 1)[0])

root = Path("outputs/html")
missing = []
checked = 0
html_files = list(root.rglob("*.html"))
for path in html_files:
    parser = LinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    for href in parser.links:
        if not href:
            continue
        checked += 1
        target = (path.parent / href).resolve()
        if not target.exists():
            missing.append((str(path), href))
print({"html_files": len(html_files), "links_checked": checked, "missing_links": len(missing)})
if missing:
    raise SystemExit(missing[:10])
'@ | python -
```

Expected: `missing_links` is `0`.

- [ ] **Step 10: Update docs and commit Task 6**

Update `docs/html_review_tool.md` with:

```markdown
## Cross-strategy comparison

The dashboard includes strategy comparison pages under `outputs/html/comparisons/strategy_matrix/`. Each page compares official crawler, official LLM, DAAD, and My German University where available. The comparison labels programmes as matched, partially matched, or only-in-strategy and surfaces source coverage warnings before programme details.
```

Append to `DEVELOPMENT_LOG.md`:

```markdown
### Source strategy dashboard

- Added cross-strategy comparison pages for official crawler, official LLM, DAAD, and My German University.
- Dashboard warning badges now surface source statuses that can indicate missed programme coverage.
```

Commit:

```powershell
git add scripts\compare_admissions_outputs.py scripts\render_admissions_dashboard.py scripts\render_admissions_html.py tests\test_scrape_admissions.py docs\html_review_tool.md DEVELOPMENT_LOG.md outputs\html
git commit -m "Add source strategy comparison dashboard" -m "Render DAAD and MGU source outputs alongside official crawler and LLM outputs, with dashboard-visible coverage warnings and programme matching."
```

---

### Task 7: Final Verification And Review

**Files:**
- No new source files unless verification reveals a defect.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m unittest tests.test_scrape_admissions
```

Expected: all tests pass.

- [ ] **Step 2: Compile changed scripts**

Run:

```powershell
python -m py_compile scripts\source_scraper_common.py scripts\scrape_daad_admissions.py scripts\scrape_mgu_admissions.py scripts\render_admissions_html.py scripts\render_admissions_dashboard.py scripts\compare_admissions_outputs.py
```

Expected: exit code `0`.

- [ ] **Step 3: Validate source JSON outputs**

Run:

```powershell
Get-ChildItem outputs\source_daad,outputs\source_mgu -Filter *.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
```

Expected: exit code `0`.

- [ ] **Step 4: Regenerate dashboard and sweep links**

Run:

```powershell
python scripts\render_admissions_dashboard.py --outputs-dir outputs --html-dir outputs\html
```

Then rerun the static link sweep from Task 6 Step 9.

Expected:

- dashboard command exits `0`
- link sweep reports `missing_links: 0`
- `outputs/html/index.html` contains `Strategy comparison`, `DAAD`, and `My German University`

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: only intentional generated dashboard changes or no changes remain. Do not stage unrelated local files such as `好德專案.docx`.

- [ ] **Step 6: Report verification evidence**

Final report should include:

- commit hashes created for each task
- source output counts for DAAD and MGU
- dashboard strategy comparison page count
- warning statuses found in DAAD/MGU manifests
- test and link-sweep results
