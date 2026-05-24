"""Scrape My German University admissions records into the source contract."""

from __future__ import annotations

import argparse
import html.parser
import json
import re
import time
import urllib.error
import urllib.parse
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


DEFAULT_OUTPUT_DIR = Path("outputs/source_mgu")
ALLOWED_HOSTS = {"www.mygermanuniversity.com", "mygermanuniversity.com"}
DETAIL_LEVELS = {"bachelor", "master", "mba", "phd", "doctorate", "certificate"}
MGU_CHALLENGE_MARKERS = (
    "cf-chl",
    "cloudflare",
    "Just a moment",
    "managed challenge",
    "challenge-platform",
    "noindex,nofollow",
    "Enable JavaScript and cookies",
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
        if tag_name in {"h1", "h2", "h3", "h4", "p", "dt", "dd", "li", "td", "th", "span"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag_name in {"h1", "h2", "h3", "h4", "p", "dt", "dd", "li", "td", "th", "span"}:
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


def infer_level(name: str, degree: str | None) -> str | None:
    haystack = f"{name} {degree or ''}".lower()
    if "pre-bachelor" in haystack:
        return "pre-bachelor"
    if "bachelor" in haystack or re.search(r"\bb\.a\.|\bb\.sc\.", haystack):
        return "bachelor"
    if "master" in haystack or "mba" in haystack or re.search(r"\bm\.a\.|\bm\.sc\.", haystack):
        return "master"
    if "phd" in haystack or "doctor" in haystack:
        return "doctoral"
    return None


def is_challenge_html(html: str) -> bool:
    return any(marker.lower() in html.lower() for marker in MGU_CHALLENGE_MARKERS)


def mgu_record_id(detail_url: str, fallback: str | None = None) -> str | None:
    match = re.search(r"/(\d+)(?:[/?#]|$)", detail_url)
    if match:
        return match.group(1)
    return fallback


def first_matching_block(blocks: list[str], pattern: str) -> str | None:
    regex = re.compile(pattern, re.IGNORECASE)
    return next((block for block in blocks if regex.search(block)), None)


def inline_value(blocks: list[str], labels: tuple[str, ...]) -> str | None:
    for block in blocks:
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*:\s*(.+)$", block, re.IGNORECASE)
            if match:
                return normalize_space(match.group(1).strip(" .;"))
    return None


def values_from_text(text: str, labels: tuple[str, ...]) -> str | None:
    stop_labels = (
        "Teaching language",
        "Language",
        "Duration",
        "Tuition fees",
        "Fees",
        "Application deadline",
        "Admission Requirements",
        "Overview",
    )
    for label in labels:
        pattern = rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:{'|'.join(re.escape(item) for item in stop_labels)})\s*:|\s+[A-Z][A-Za-z ]+ Requirements|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return normalize_space(match.group(1).strip(" .;"))
    return None


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


def programme_name_from_blocks(blocks: list[str]) -> str:
    for block in blocks:
        if re.search(r"\b(overview|admission requirements|duration|tuition fees|teaching language)\b", block, re.IGNORECASE):
            continue
        if len(block) > 2:
            return block
    return "Unnamed MGU programme"


def degree_from_blocks(blocks: list[str]) -> str | None:
    return first_matching_block(
        blocks[:12],
        r"\b(Bachelor|Master|MBA|M\.A\.|M\.Sc\.|B\.A\.|B\.Sc\.|PhD|Doctor)\b",
    )


def admission_text_from_blocks(blocks: list[str]) -> str:
    accepted = [
        block
        for block in blocks
        if re.search(r"admission|requirement|ielts|toefl|ects|bachelor|master|degree", block, re.IGNORECASE)
    ]
    return normalize_space(" ".join(accepted))


def parse_mgu_detail(
    html: str,
    detail_url: str,
    listing_url: str | None,
    record_id: str | None,
) -> SourceProgram:
    blocks = blocks_from_html(html)
    joined = normalize_space(" ".join(blocks))
    name = programme_name_from_blocks(blocks)
    degree = degree_from_blocks(blocks)
    language = inline_value(blocks, ("Teaching language", "Language")) or values_from_text(
        joined,
        ("Teaching language", "Language"),
    )
    duration = inline_value(blocks, ("Duration",)) or values_from_text(joined, ("Duration",))
    fees = inline_value(blocks, ("Tuition fees", "Fees")) or values_from_text(joined, ("Tuition fees", "Fees"))
    deadline = inline_value(blocks, ("Application deadline", "Application deadlines"))
    admission_text = admission_text_from_blocks(blocks)
    ielts = parse_ielts(admission_text or joined)
    ects = parse_ects(admission_text or joined)
    requirements = {
        "language_requirements": [{"test": "IELTS", "minimum_score": ielts}] if ielts else [],
        "academic_background": {
            "minimum_ects": ects,
            "notes": [admission_text] if admission_text else [],
        },
    }
    application = {
        "deadlines": [deadline] if deadline else [],
        "intakes": [],
        "fees": [fees] if fees else [],
    }
    return SourceProgram(
        source_record_id=mgu_record_id(detail_url, record_id),
        source_listing_url=listing_url,
        source_detail_url=detail_url,
        name=name,
        degree=degree,
        level=infer_level(name, degree),
        language_of_instruction=language_values(language),
        requirements=requirements,
        application=application,
        evidence_key="mgu_detail",
        evidence_text=admission_text or joined[:500],
        source_specific={
            "source_platform": "my_german_university",
            "duration": duration,
            "raw_blocks": blocks[:60],
        },
        needs_human_review=not bool(admission_text),
    )


class MguFetchSession:
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


def load_source_targets(path: Path) -> list[dict[str, Any]]:
    targets = load_json(path)
    return targets["sources"]["my_german_university"]["schools"]


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
    candidates.append(
        {
            "strategy": "inspect_allowed_browser_network",
            "reason": "MGU direct HTML access can be Cloudflare/JavaScript-gated; later work may confirm a public endpoint without bypassing access controls.",
        }
    )
    return candidates


def is_allowed_mgu_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc not in ALLOWED_HOSTS:
        return False
    if parsed.path.lower().endswith((".pdf", ".zip")):
        return False
    return True


def extract_detail_links(html: str, base_url: str) -> list[str]:
    links: dict[str, None] = {}
    for raw in re.findall(r"""href=["']([^"']+)["']""", html, flags=re.IGNORECASE):
        absolute = urllib.parse.urljoin(base_url, raw)
        parsed = urllib.parse.urlparse(absolute)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 3 and parts[0].lower() in DETAIL_LEVELS and parts[-1].isdigit() and is_allowed_mgu_url(absolute):
            cleaned = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            links[cleaned] = None
    return list(links)


def build_empty_output(
    target: dict[str, Any],
    partner: dict[str, Any],
    status: str,
    limitation_notes: list[str],
) -> dict[str, Any]:
    return build_source_output(
        source_platform="my_german_university",
        source_label="My German University",
        school=school_contract(partner),
        programmes=[],
        coverage_status=status,
        limitation_notes=limitation_notes,
        future_deepening_candidates=target_future_candidates(target),
    )


def coverage_status_for_target(
    target: dict[str, Any],
    programmes: list[SourceProgram],
    attempted_count: int,
    fetch_failures: int,
    challenge_seen: bool,
    limitation_notes: list[str],
) -> str:
    target_status = target.get("coverage_status")
    if challenge_seen:
        return "js_gated"
    if not programmes:
        if target_status == "source_no_match" and not attempted_count:
            return "source_no_match"
        return "source_limited" if limitation_notes or attempted_count or fetch_failures else "source_no_match"
    if fetch_failures or target_status in {"source_partial_match", "target_needs_recon", "target_seeded"}:
        return "source_partial_match"
    return "complete_within_configured_targets"


def collect_detail_candidates(
    target: dict[str, Any],
    fetcher: MguFetchSession,
    limitation_notes: list[str],
) -> tuple[list[tuple[str, str | None, str | None]], bool, int]:
    candidates: dict[str, tuple[str, str | None, str | None]] = {}
    fetch_failures = 0
    challenge_seen = False

    for detail_url in target.get("detail_urls", []):
        if is_allowed_mgu_url(detail_url):
            candidates[detail_url] = (detail_url, None, mgu_record_id(detail_url))
        else:
            limitation_notes.append(f"Skipped non-MGU or disallowed configured detail URL: {detail_url}")

    for listing_url in target.get("listing_urls", []):
        if not is_allowed_mgu_url(listing_url):
            limitation_notes.append(f"Skipped non-MGU or disallowed configured listing URL: {listing_url}")
            continue
        try:
            html = fetcher.fetch(listing_url)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            fetch_failures += 1
            limitation_notes.append(f"Could not fetch MGU listing {listing_url}: {exc.__class__.__name__}: {exc}")
            continue
        if is_challenge_html(html):
            challenge_seen = True
            limitation_notes.append(
                f"MGU listing {listing_url} returned Cloudflare/JavaScript-gated challenge HTML; not bypassed."
            )
            continue
        links = extract_detail_links(html, listing_url)
        if not links:
            limitation_notes.append(f"MGU listing {listing_url} returned no usable same-source programme detail links.")
        for detail_url in links:
            candidates.setdefault(detail_url, (detail_url, listing_url, mgu_record_id(detail_url)))

    return list(candidates.values()), challenge_seen, fetch_failures


def scrape_target(
    target: dict[str, Any],
    partner: dict[str, Any],
    args: argparse.Namespace,
    fetcher: MguFetchSession | None = None,
) -> dict[str, Any]:
    programmes: list[SourceProgram] = []
    limitation_notes: list[str] = []
    fetcher = fetcher or MguFetchSession(user_agent=args.user_agent, timeout=args.timeout, delay=args.delay)

    target_status = target.get("coverage_status")
    if target_status in {"source_partial_match", "target_needs_recon", "target_seeded"}:
        limitation_notes.append(
            f"Configured MGU target is {target_status}; configured source URLs may not cover every programme exposed by MGU."
        )
    if target_status == "source_no_match" and not target.get("listing_urls") and not target.get("detail_urls"):
        return build_empty_output(
            target,
            partner,
            "source_no_match",
            [f"No MGU source target was confirmed for {target['school_name']}; no school-official fallback attempted."],
        )

    detail_candidates, challenge_seen, fetch_failures = collect_detail_candidates(target, fetcher, limitation_notes)
    if not detail_candidates:
        status = coverage_status_for_target(
            target,
            programmes,
            attempted_count=0,
            fetch_failures=fetch_failures,
            challenge_seen=challenge_seen,
            limitation_notes=limitation_notes,
        )
        return build_empty_output(target, partner, status, limitation_notes)

    for detail_url, listing_url, record_id in detail_candidates:
        try:
            html = fetcher.fetch(detail_url)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            fetch_failures += 1
            limitation_notes.append(f"Could not fetch MGU detail {detail_url}: {exc.__class__.__name__}: {exc}")
            continue
        if is_challenge_html(html):
            challenge_seen = True
            limitation_notes.append(
                f"MGU detail {detail_url} returned Cloudflare/JavaScript-gated challenge HTML; not bypassed."
            )
            continue
        try:
            programmes.append(parse_mgu_detail(html, detail_url, listing_url, record_id))
        except Exception as exc:  # noqa: BLE001 - preserve batch output for later review.
            fetch_failures += 1
            limitation_notes.append(f"Could not parse MGU detail {detail_url}: {exc.__class__.__name__}: {exc}")

    status = coverage_status_for_target(
        target,
        programmes,
        attempted_count=len(detail_candidates),
        fetch_failures=fetch_failures,
        challenge_seen=challenge_seen,
        limitation_notes=limitation_notes,
    )
    if not programmes:
        return build_empty_output(target, partner, status, limitation_notes)
    return build_source_output(
        source_platform="my_german_university",
        source_label="My German University",
        school=school_contract(partner),
        programmes=programmes,
        coverage_status=status,
        limitation_notes=limitation_notes,
        future_deepening_candidates=target_future_candidates(target),
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape My German University source admissions records.")
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
    status_counts: dict[str, int] = {}
    programme_count = 0
    fetcher = MguFetchSession(user_agent=args.user_agent, timeout=args.timeout, delay=args.delay)

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
                "source_platform": "my_german_university",
                "output_path": str(output_path),
                "coverage_status": status,
                "warning": output["source_coverage"]["warning"],
                "programs_extracted": len(output["programs"]),
                "limitation_notes": output["source_coverage"]["limitation_notes"],
            }
        )

    manifest = {
        "schema_version": "0.1",
        "source_platform": "my_german_university",
        "school_count": len(manifest_entries),
        "programs_extracted": programme_count,
        "status_counts": status_counts,
        "warning_statuses": sorted(
            {entry["coverage_status"] for entry in manifest_entries if entry["warning"]}
        ),
        "schools": manifest_entries,
    }
    write_json(output_dir / "source_mgu_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
