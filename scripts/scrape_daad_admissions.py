"""Scrape DAAD admissions records into the source admissions contract."""

from __future__ import annotations

import argparse
import html.parser
import json
import re
import time
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Iterable

try:
    from source_scraper_common import (
        DEFAULT_USER_AGENT,
        SOURCE_TARGETS_PATH,
        SourceProgram,
        build_source_output,
        fetch_text,
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
        fetch_text,
        load_json,
        load_partner_schools,
        normalize_space,
        source_slug,
        write_json,
    )


DEFAULT_OUTPUT_DIR = Path("outputs/source_daad")
DAAD_API_PATH = "/deutschland/studienangebote/international-programmes/api/solr/en/search.json"
DAAD_DETAIL_BASE = "https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/"
ALLOWED_HOSTS = {"www2.daad.de", "www.daad.de"}
SECTION_HEADINGS = {
    "Overview",
    "Course details",
    "Online learning",
    "Costs / Funding",
    "Requirements / Registration",
    "Services",
    "About the university",
    "Gallery",
    "Contact",
}
INVALID_STRUCTURED_VALUES = SECTION_HEADINGS | {
    "Yes",
    "No",
    "pagination",
    "Home Back Previous Next",
    "International Programmes 2025/2026",
}
CHROME_PATTERNS = (
    "DAADREMOVE_JS",
    "Skip to main content",
    "More information on daad.de",
    "CHE University Ranking",
    "DAAD database on admission requirements",
    "Home Back Previous Next",
    "International Programmes 2025/2026",
)


class SimpleTextParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag_name in {"h1", "h2", "h3", "h4", "p", "dt", "dd", "li", "td", "th"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag_name in {"h1", "h2", "h3", "h4", "p", "dt", "dd", "li", "td", "th"}:
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
    lower_labels = {normalize_label(label) for label in labels}
    for index, block in enumerate(blocks[:-1]):
        candidate = normalize_label(block)
        if candidate in lower_labels:
            value = clean_structured_value(blocks[index + 1])
            if value:
                return value
    return None


def normalize_label(value: str) -> str:
    return normalize_space(value).strip(":").lower()


def clean_daad_normalized_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = normalize_space(value)
    cleaned = re.sub(r"\s+-\s+International Programmes.*?(?=\s|$)", " ", cleaned)
    for pattern in CHROME_PATTERNS:
        cleaned = cleaned.replace(pattern, " ")
    for heading in SECTION_HEADINGS:
        cleaned = re.sub(rf"(?<!\w){re.escape(heading)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = normalize_space(cleaned.strip(" -:"))
    if not cleaned:
        return None
    if cleaned in INVALID_STRUCTURED_VALUES or cleaned in SECTION_HEADINGS:
        return None
    return cleaned


def clean_structured_value(value: str | None) -> str | None:
    cleaned = clean_daad_normalized_text(value)
    if not cleaned:
        return None
    if cleaned in INVALID_STRUCTURED_VALUES:
        return None
    return cleaned


def first_valid_after(blocks: list[str], labels: tuple[str, ...]) -> str | None:
    lower_labels = {normalize_label(label) for label in labels}
    for index, block in enumerate(blocks[:-1]):
        if normalize_label(block) not in lower_labels:
            continue
        value = clean_structured_value(blocks[index + 1])
        if value:
            return value
    return None


def clean_programme_name(value: str) -> str:
    cleaned = clean_daad_normalized_text(value) or ""
    return normalize_space(cleaned.strip(" -"))


def is_chrome_block(value: str) -> bool:
    cleaned = normalize_space(value)
    if not cleaned or cleaned in SECTION_HEADINGS or cleaned in INVALID_STRUCTURED_VALUES:
        return True
    if cleaned.isdigit():
        return True
    return any(pattern in cleaned for pattern in CHROME_PATTERNS)


def programme_name_from_blocks(blocks: list[str]) -> str:
    for block in blocks:
        candidate = clean_programme_name(block)
        if candidate and not is_chrome_block(candidate):
            return candidate
    return "Unnamed DAAD programme"


def is_non_degree_or_certificate_like(name: str, degree: str | None) -> bool:
    haystack = f"{name} {degree or ''}".lower()
    if re.search(r"\b(certificate|summer|camp|training|team-up|short course)\b", haystack):
        return True
    if degree and not re.search(
        r"\b(bachelor|master|mba|m\.a\.|m\.sc\.|b\.a\.|b\.sc\.|doctor|phd|engineering|science|arts)\b",
        degree,
        re.IGNORECASE,
    ):
        return True
    return False


def core_field_noise_flags(name: str, application: dict[str, list[str]]) -> list[str]:
    flags = []
    core_values = [name, *application.get("deadlines", []), *application.get("fees", [])]
    if any(any(pattern in value for pattern in CHROME_PATTERNS) for value in core_values):
        flags.append("page_chrome_in_core_field")
    if any(value in SECTION_HEADINGS for value in core_values):
        flags.append("section_heading_in_core_field")
    return flags


def cleaned_requirement_text(blocks: list[str], programme_name: str) -> str:
    accepted: list[str] = []
    admission_pattern = re.compile(r"admission|requirement|ielts|toefl|ects|bachelor|master", re.IGNORECASE)
    for block in blocks:
        cleaned = clean_daad_normalized_text(block)
        if not cleaned or not admission_pattern.search(cleaned):
            continue
        if clean_programme_name(cleaned) == programme_name:
            continue
        accepted.append(cleaned)
    return normalize_space(" ".join(accepted))


class DaadFetchSession:
    def __init__(self, user_agent: str, timeout: float, delay: float) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.delay = delay
        self._has_fetched = False

    def fetch(self, url: str) -> str:
        if self._has_fetched and self.delay > 0:
            time.sleep(self.delay)
        self._has_fetched = True
        return fetch_text(url, user_agent=self.user_agent, timeout=self.timeout)


def infer_level(name: str, degree: str | None) -> str | None:
    haystack = f"{name} {degree or ''}".lower()
    if "pre-bachelor" in haystack:
        return "pre-bachelor"
    if "bachelor" in haystack:
        return "bachelor"
    if "master" in haystack or "mba" in haystack or "m.sc" in haystack or "m.a" in haystack:
        return "master"
    if "phd" in haystack or "doctor" in haystack:
        return "doctoral"
    return None


def detail_record_id(detail_url: str, fallback: str | None = None) -> str | None:
    match = re.search(r"/detail/(\d+)/?", detail_url)
    if match:
        return match.group(1)
    return fallback


def language_values(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;/]|\band\b", value)
    values = [normalize_space(part) for part in parts if normalize_space(part)]
    return values or [value]


def parse_ielts(text: str) -> str | None:
    match = re.search(r"IELTS(?:\s+Academic)?\s*(?:score\s*)?(?:of\s*)?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    return match.group(1) if match else None


def parse_ects(text: str) -> int | None:
    match = re.search(r"(\d{2,3})\s*ECTS", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_daad_detail(
    html: str,
    detail_url: str,
    listing_url: str | None,
    record_id: str | None,
) -> SourceProgram:
    blocks = blocks_from_html(html)
    name = programme_name_from_blocks(blocks)
    degree = first_after(blocks, ("Degree", "Final degree", "Academic degree"))
    language = first_after(blocks, ("Course language", "Course languages", "Languages", "Teaching language"))
    deadline = first_after(blocks, ("Application deadline", "Application deadlines"))
    fees = first_valid_after(
        blocks,
        ("Tuition fees", "Tuition fees per semester in EUR", "Additional information on tuition fees", "Fees"),
    )
    beginning = first_after(blocks, ("Beginning", "Start"))
    duration = first_after(blocks, ("Programme duration", "Duration"))
    location = first_after(blocks, ("Course location", "Location"))
    study_mode = first_after(blocks, ("Mode of study", "Study mode"))
    admission_text = cleaned_requirement_text(blocks, name)
    ielts = parse_ielts(admission_text)
    ects = parse_ects(admission_text)
    language_requirements = [{"test": "IELTS", "minimum_score": ielts}] if ielts else []
    application = {
        "deadlines": [deadline] if deadline else [],
        "intakes": [beginning] if beginning else [],
        "fees": [fees] if fees else [],
    }
    quality_flags = core_field_noise_flags(name, application)
    if is_non_degree_or_certificate_like(name, degree):
        quality_flags.append("non_degree_or_certificate_like")
    requirements = {
        "language_requirements": language_requirements,
        "academic_background": {
            "minimum_ects": ects,
            "notes": [admission_text] if admission_text else [],
        },
    }
    return SourceProgram(
        source_record_id=detail_record_id(detail_url, record_id),
        source_listing_url=listing_url,
        source_detail_url=detail_url,
        name=name,
        degree=degree,
        level=infer_level(name, degree),
        campus=location,
        language_of_instruction=language_values(language),
        requirements=requirements,
        application=application,
        evidence_key="daad_detail",
        evidence_text=admission_text or " ".join(filter(None, (clean_daad_normalized_text(block) for block in blocks[:12]))),
        source_specific={
            "source_platform": "daad",
            "beginning": beginning,
            "programme_duration": duration,
            "study_mode": study_mode,
            "quality_flags": quality_flags,
            "raw_blocks": blocks[:60],
        },
        needs_human_review=bool(quality_flags) or not bool(admission_text),
    )


def load_source_targets(path: Path) -> list[dict[str, Any]]:
    targets = load_json(path)
    return targets["sources"]["daad"]["schools"]


def partner_by_name() -> dict[str, dict[str, Any]]:
    return {school["name"]: school for school in load_partner_schools()}


def school_contract(partner: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": partner["name"],
        "url": partner["official_url"],
        "country": partner.get("country"),
        "partner_status": partner.get("partner_status"),
        "school_type": partner.get("school_type"),
    }


def target_future_candidates(target: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for item in target.get("future_deepening_candidates", []):
        if isinstance(item, dict):
            candidates.append(item)
        else:
            candidates.append({"note": str(item)})
    return candidates


def is_allowed_daad_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in ALLOWED_HOSTS:
        return False
    return "hec-fetch-offset" not in parsed.query and not parsed.path.lower().endswith(".pdf")


def to_api_url(listing_url: str, limit: int = 100) -> str | None:
    parsed = urllib.parse.urlparse(listing_url)
    if not is_allowed_daad_url(listing_url):
        return None
    if parsed.path == DAAD_API_PATH:
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    elif "/international-programmes/en/result/" in parsed.path:
        query = urllib.parse.parse_qs(parsed.query)
        pairs = []
        if query.get("q"):
            pairs.append(("q", query["q"][0]))
    else:
        return None
    filtered = [(key, value) for key, value in pairs if key not in {"limit", "offset", "display"}]
    filtered.extend([("limit", str(limit)), ("offset", "0"), ("display", "list")])
    return urllib.parse.urlunparse(
        ("https", "www2.daad.de", DAAD_API_PATH, "", urllib.parse.urlencode(filtered), "")
    )


def iter_listing_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        if ("id" in payload or "link" in payload) and (
            "courseName" in payload or "courseNameShort" in payload or "academy" in payload
        ):
            yield payload
        for value in payload.values():
            yield from iter_listing_records(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from iter_listing_records(item)


def academy_matches(record: dict[str, Any], target: dict[str, Any]) -> bool:
    academy = normalize_space(str(record.get("academy") or ""))
    if not academy:
        return True
    haystack = academy.lower()
    for alias in [target["school_name"], *target.get("school_aliases", [])]:
        if alias and alias.lower() in haystack:
            return True
    return False


def detail_url_from_record(record: dict[str, Any]) -> str | None:
    link = record.get("link")
    if isinstance(link, str) and link:
        return urllib.parse.urljoin("https://www2.daad.de", link)
    record_id = record.get("id")
    if record_id is not None:
        return f"{DAAD_DETAIL_BASE}{record_id}/"
    return None


def listing_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("numFound", "total", "totalCount", "count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    for value in payload.values():
        found = listing_total(value)
        if found is not None:
            return found
    return None


def collect_detail_urls(
    target: dict[str, Any],
    args: argparse.Namespace,
    limitation_notes: list[str],
    fetcher: DaadFetchSession,
) -> tuple[list[tuple[str, str | None, str | None]], bool]:
    candidates: dict[str, tuple[str, str | None, str | None]] = {}
    listing_urls = target.get("listing_urls") or [None]
    for detail_url in target.get("detail_urls", []):
        if is_allowed_daad_url(detail_url):
            candidates[detail_url] = (detail_url, listing_urls[0], detail_record_id(detail_url))
        else:
            limitation_notes.append(f"Skipped non-DAAD or disallowed configured detail URL: {detail_url}")

    bounded = False
    for listing_url in target.get("listing_urls", []):
        api_url = to_api_url(listing_url)
        if not api_url:
            limitation_notes.append(f"Listing URL is not a supported bounded DAAD API/result URL: {listing_url}")
            continue
        try:
            text = fetcher.fetch(api_url)
            payload = json.loads(text)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
            limitation_notes.append(f"Could not fetch DAAD listing {api_url}: {exc.__class__.__name__}: {exc}")
            continue
        records = [record for record in iter_listing_records(payload) if academy_matches(record, target)]
        limitation_notes.append(f"Bounded DAAD listing window inspected for {api_url}: limit=100 offset=0.")
        total = listing_total(payload)
        if total is not None and total > len(records):
            bounded = True
            limitation_notes.append(
                f"DAAD listing {api_url} reported {total} records; bounded same-source fetch matched {len(records)} records in the first page."
            )
        for record in records:
            detail_url = detail_url_from_record(record)
            if detail_url and is_allowed_daad_url(detail_url):
                candidates.setdefault(detail_url, (detail_url, api_url, str(record.get("id") or "")))
    return list(candidates.values()), bounded


def build_no_match_output(
    target: dict[str, Any],
    partner: dict[str, Any],
    status: str = "source_no_match",
    limitation_notes: list[str] | None = None,
) -> dict[str, Any]:
    notes = limitation_notes or [f"No DAAD detail URLs configured for {target['school_name']}."]
    return build_source_output(
        source_platform="daad",
        source_label="DAAD",
        school=school_contract(partner),
        programmes=[],
        coverage_status=status,
        limitation_notes=notes,
        future_deepening_candidates=target_future_candidates(target),
    )


def coverage_status_for_target(
    target: dict[str, Any],
    programmes: list[SourceProgram],
    attempted_count: int,
    fetch_failures: int,
    bounded_listing: bool,
    limitation_notes: list[str],
) -> str:
    target_status = target.get("coverage_status")
    if not programmes:
        if attempted_count or fetch_failures or limitation_notes:
            return "source_limited"
        return "source_no_match"
    if fetch_failures or bounded_listing or target_status in {"source_partial_match", "target_needs_recon"}:
        return "source_partial_match"
    return "complete_within_configured_targets"


def scrape_target(
    target: dict[str, Any],
    partner: dict[str, Any],
    args: argparse.Namespace,
    fetcher: DaadFetchSession | None = None,
) -> dict[str, Any]:
    programmes: list[SourceProgram] = []
    limitation_notes: list[str] = []
    fetcher = fetcher or DaadFetchSession(user_agent=args.user_agent, timeout=args.timeout, delay=args.delay)
    detail_candidates, bounded_listing = collect_detail_urls(target, args, limitation_notes, fetcher)
    target_status = target.get("coverage_status")
    if target_status in {"source_partial_match", "target_needs_recon"}:
        limitation_notes.append(
            f"Configured DAAD target is {target_status}; configured queries and detail URLs may not cover every programme exposed by DAAD."
        )
    if not detail_candidates:
        status = "source_no_match" if target.get("coverage_status") == "source_no_match" and not limitation_notes else "source_limited"
        notes = limitation_notes or [f"No DAAD detail URLs were available or discovered for {target['school_name']}."]
        return build_no_match_output(target, partner, status=status, limitation_notes=notes)

    fetch_failures = 0
    for detail_url, listing_url, record_id in detail_candidates:
        try:
            html = fetcher.fetch(detail_url)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            fetch_failures += 1
            limitation_notes.append(f"Could not fetch DAAD detail {detail_url}: {exc.__class__.__name__}: {exc}")
            continue
        try:
            programmes.append(parse_daad_detail(html, detail_url, listing_url, record_id))
        except Exception as exc:  # noqa: BLE001 - preserve batch output for later review.
            fetch_failures += 1
            limitation_notes.append(f"Could not parse DAAD detail {detail_url}: {exc.__class__.__name__}: {exc}")

    status = coverage_status_for_target(
        target,
        programmes,
        attempted_count=len(detail_candidates),
        fetch_failures=fetch_failures,
        bounded_listing=bounded_listing,
        limitation_notes=limitation_notes,
    )
    if not programmes:
        return build_no_match_output(target, partner, status=status, limitation_notes=limitation_notes)
    return build_source_output(
        source_platform="daad",
        source_label="DAAD",
        school=school_contract(partner),
        programmes=programmes,
        coverage_status=status,
        limitation_notes=limitation_notes,
        future_deepening_candidates=target_future_candidates(target),
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape DAAD source admissions records.")
    parser.add_argument("--targets", default=str(SOURCE_TARGETS_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    partners = partner_by_name()
    output_dir = Path(args.output_dir)
    manifest_entries = []
    status_counts: dict[str, int] = {}
    programme_count = 0
    fetcher = DaadFetchSession(user_agent=args.user_agent, timeout=args.timeout, delay=args.delay)
    for target in load_source_targets(Path(args.targets)):
        partner = partners[target["school_name"]]
        output = scrape_target(target, partner, args, fetcher=fetcher)
        output_path = output_dir / f"{source_slug(partner['name'])}_admissions.json"
        write_json(output_path, output)
        status = output["source_coverage"]["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        programme_count += len(output["programs"])
        manifest_entries.append(
            {
                "school": partner["name"],
                "source_platform": "daad",
                "output_path": str(output_path),
                "coverage_status": status,
                "warning": output["source_coverage"]["warning"],
                "programs_extracted": len(output["programs"]),
                "limitation_notes": output["source_coverage"]["limitation_notes"],
            }
        )
    manifest = {
        "schema_version": "0.1",
        "source_platform": "daad",
        "school_count": len(manifest_entries),
        "programs_extracted": programme_count,
        "status_counts": status_counts,
        "warning_statuses": sorted(
            {entry["coverage_status"] for entry in manifest_entries if entry["warning"]}
        ),
        "schools": manifest_entries,
    }
    write_json(output_dir / "source_daad_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
