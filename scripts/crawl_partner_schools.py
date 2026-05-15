"""Batch crawl Gut-Haode partner-school admissions pages.

The batch workflow is deliberately config-driven because each school exposes
programmes and admissions evidence differently. The script does not bypass the
same robots/same-host constraints used by the single-school scraper.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

try:
    from scrape_admissions import DEFAULT_USER_AGENT, build_output, crawl
except ModuleNotFoundError:
    from scripts.scrape_admissions import DEFAULT_USER_AGENT, build_output, crawl


DEFAULT_PARTNERS_PATH = Path("data/partner_schools.json")
DEFAULT_SEEDS_PATH = Path("data/partner_school_crawl_seeds.json")
DEFAULT_OUTPUT_DIR = Path("outputs")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_value).strip("_").lower()
    return slug or "school"


def index_by_name(items: Iterable[dict]) -> dict[str, dict]:
    return {item["name"]: item for item in items}


def build_scrape_args(batch_args: argparse.Namespace, school: dict) -> SimpleNamespace:
    return SimpleNamespace(
        max_pages=batch_args.max_pages,
        delay=batch_args.delay,
        timeout=batch_args.timeout,
        user_agent=batch_args.user_agent,
        school_name=school["name"],
        country=school.get("country"),
        partner_status=school.get("partner_status"),
        school_type=school.get("school_type"),
    )


def crawl_school(batch_args: argparse.Namespace, school: dict, seed_config: dict) -> dict:
    output_dir = Path(batch_args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    root_url = seed_config.get("crawl_root_url") or school["official_url"]
    seed_urls = seed_config.get("seed_urls", [])
    pages, skipped, robot_policy = crawl(
        root_url=root_url,
        seed_urls=seed_urls,
        max_pages=batch_args.max_pages,
        delay=batch_args.delay,
        user_agent=batch_args.user_agent,
        timeout=batch_args.timeout,
    )
    scrape_args = build_scrape_args(batch_args, school)
    output = build_output(root_url, pages, skipped, robot_policy, scrape_args)
    output["school"]["source_official_url"] = school["official_url"]
    output["review_seed_config"] = {
        "seed_urls": seed_urls,
        "review_notes": seed_config.get("review_notes", []),
        "crawl_cautions": seed_config.get("crawl_cautions", []),
    }
    output_path = output_dir / f"{slugify(school['name'])}_admissions.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "school": school["name"],
        "partner_status": school.get("partner_status"),
        "crawl_root_url": root_url,
        "output_path": str(output_path),
        "robots_status": robot_policy.status,
        "robots_error": robot_policy.error,
        "crawl_summary": output["crawl_summary"],
        "review_notes": seed_config.get("review_notes", []),
        "crawl_cautions": seed_config.get("crawl_cautions", []),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch crawl all configured Gut-Haode partner schools.")
    parser.add_argument("--partners", default=str(DEFAULT_PARTNERS_PATH), help="Path to partner_schools.json.")
    parser.add_argument("--seeds", default=str(DEFAULT_SEEDS_PATH), help="Path to reviewed seed config JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for per-school output JSON.")
    parser.add_argument("--manifest", default=str(DEFAULT_OUTPUT_DIR / "partner_school_crawl_manifest.json"))
    parser.add_argument("--school", action="append", default=[], help="Limit run to one or more exact school names.")
    parser.add_argument("--max-pages", type=int, default=30, help="Hard crawl limit per school.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between successful requests.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout per request.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Crawler User-Agent.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    partners = load_json(Path(args.partners))["schools"]
    seeds = index_by_name(load_json(Path(args.seeds))["schools"])
    selected = set(args.school)
    manifest_entries = []
    for school in partners:
        if selected and school["name"] not in selected:
            continue
        seed_config = seeds.get(school["name"], {"crawl_root_url": school["official_url"], "seed_urls": []})
        manifest_entries.append(crawl_school(args, school, seed_config))

    manifest = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "school_count": len(manifest_entries),
        "max_pages": args.max_pages,
        "delay_seconds": args.delay,
        "timeout_seconds": args.timeout,
        "schools": manifest_entries,
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
