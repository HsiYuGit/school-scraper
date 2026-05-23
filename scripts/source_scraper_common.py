"""Shared helpers for source-specific admissions scrapers."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import copy
import re
import unicodedata
import urllib.request
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


def json_clone(value: Any) -> Any:
    return copy.deepcopy(value)


def empty_requirements() -> dict[str, Any]:
    return {
        "academic_background": {
            "degree_level": None,
            "minimum_ects": None,
            "recognized_institution": None,
            "minimum_grade": None,
            "notes": [],
        },
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
    merged = json_clone(defaults)
    for key, item in (value or {}).items():
        if isinstance(item, dict) and isinstance(merged.get(key), dict):
            merged[key].update(json_clone(item))
        else:
            merged[key] = json_clone(item)
    return merged


def evidence_item(
    source_url: str | None,
    source_text: str,
    retrieved_at: str,
    confidence: str = "medium",
    review_note: str = "Source-platform extraction.",
) -> dict[str, Any]:
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
        "school": json_clone(school),
        "program": {
            "name": programme.name,
            "degree": programme.degree,
            "level": programme.level,
            "url": detail_url,
            "campus": programme.campus,
            "language_of_instruction": json_clone(programme.language_of_instruction),
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
        "source_specific": json_clone(programme.source_specific),
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
        "school": json_clone(school),
        "retrieved_at": retrieved_at,
        "source_coverage": {
            "status": coverage_status,
            "warning": coverage_warning(coverage_status),
            "programs_extracted": len(programme_records),
            "limitation_notes": json_clone(limitation_notes),
            "future_deepening_candidates": json_clone(future_deepening_candidates),
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
