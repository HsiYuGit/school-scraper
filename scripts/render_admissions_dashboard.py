"""Render the versioned admissions review dashboard and comparison pages."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Iterable

try:
    from compare_admissions_outputs import (
        count_language_tests,
        count_test_requirements,
        render_comparison,
    )
    from render_admissions_html import (
        escape,
        format_value,
        load_json,
        page,
        render_file,
        render_meta_grid,
    )
except ModuleNotFoundError:
    from scripts.compare_admissions_outputs import (
        count_language_tests,
        count_test_requirements,
        render_comparison,
    )
    from scripts.render_admissions_html import (
        escape,
        format_value,
        load_json,
        page,
        render_file,
        render_meta_grid,
    )


DEFAULT_OUTPUTS_DIR = Path("outputs")
DEFAULT_HTML_DIR = Path("outputs/html")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", errors="ignore").decode("ascii")
    slug = "".join(char.lower() if char.isalnum() else "_" for char in ascii_value)
    return "_".join(part for part in slug.split("_") if part) or "school"


def json_files(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*.json") if path.name != "partner_school_crawl_manifest.json")


def school_name(payload: dict[str, Any], path: Path) -> str:
    return payload.get("school", {}).get("name") or path.stem


def index_by_school(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in json_files(root):
        payload = load_json(path)
        if "programs" in payload:
            result[school_name(payload, path)] = path
    return result


def copy_nit_llm(outputs_dir: Path) -> None:
    source = outputs_dir / "v0_2" / "nit_llm_native_admissions.json"
    target_dir = outputs_dir / "v0_3" / "llm_native"
    target = target_dir / "nit_llm_native_admissions.json"
    if source.exists() and not target.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def render_reviews(outputs_dir: Path, html_dir: Path) -> list[Path]:
    rendered: list[Path] = []
    for version in ("v0_2", "v0_3"):
        source_dir = outputs_dir / version
        if source_dir.exists():
            target_dir = html_dir / version
            for path in sorted(source_dir.glob("*.json")):
                rendered.append(render_file(path, target_dir))
    llm_dir = outputs_dir / "v0_3" / "llm_native"
    if llm_dir.exists():
        target_dir = html_dir / "v0_3" / "llm_native"
        for path in sorted(llm_dir.glob("*.json")):
            rendered.append(render_file(path, target_dir))
    return rendered


def manifest_status(manifest_path: Path) -> dict[str, str]:
    if not manifest_path.exists():
        return {}
    manifest = load_json(manifest_path)
    return {
        item.get("school", ""): item.get("validation_status") or "not_recorded"
        for item in manifest.get("schools", [])
    }


def version_comparison_row(name: str, v2: dict[str, Any] | None, v3: dict[str, Any] | None, v2_status: str, v3_status: str) -> str:
    v2_programs = len(v2.get("programs", [])) if v2 else 0
    v3_programs = len(v3.get("programs", [])) if v3 else 0
    v2_lang = count_language_tests(v2 or {})
    v3_lang = count_language_tests(v3 or {})
    v2_tests = count_test_requirements(v2 or {})
    v3_tests = count_test_requirements(v3 or {})
    v2_review = (v2 or {}).get("crawl_summary", {}).get("programs_needing_human_review")
    v3_review = (v3 or {}).get("crawl_summary", {}).get("programs_needing_human_review")
    observations: list[str] = []
    if v2_programs > v3_programs:
        observations.append("Fewer final program records; likely reduced non-program false positives.")
    if v2_programs == 0 and v3_programs > 0:
        observations.append("Recovered programs from previous zero-program output.")
    if v3_lang > v2_lang:
        observations.append("More language requirements extracted.")
    if v3_status == "broken_or_needs_review":
        observations.append("Zero or weak extraction is now explicitly flagged.")
    if not observations:
        observations.append("No clear summary-level improvement; inspect detail pages.")
    return (
        "<tr>"
        f"<td>{escape(name)}</td>"
        f"<td>{v2_programs}</td><td>{v3_programs}</td>"
        f"<td>{v2_lang}</td><td>{v3_lang}</td>"
        f"<td>{v2_tests}</td><td>{v3_tests}</td>"
        f"<td>{escape(v2_review)}</td><td>{escape(v3_review)}</td>"
        f"<td>{escape(v2_status)}</td><td>{escape(v3_status)}</td>"
        f"<td>{format_value(observations)}</td>"
        "</tr>"
    )


def render_version_comparison(outputs_dir: Path, html_dir: Path) -> Path:
    v2_paths = index_by_school(outputs_dir / "v0_2")
    v3_paths = index_by_school(outputs_dir / "v0_3")
    v2_status = manifest_status(outputs_dir / "v0_2" / "partner_school_crawl_manifest.json")
    v3_status = manifest_status(outputs_dir / "v0_3" / "partner_school_crawl_manifest.json")
    names = sorted(set(v2_paths) | set(v3_paths))
    rows = []
    totals = {
        "v0.2 programs": 0,
        "v0.3 programs": 0,
        "v0.2 language tests": 0,
        "v0.3 language tests": 0,
        "v0.3 broken/review schools": sum(1 for value in v3_status.values() if value == "broken_or_needs_review"),
    }
    for name in names:
        v2 = load_json(v2_paths[name]) if name in v2_paths else None
        v3 = load_json(v3_paths[name]) if name in v3_paths else None
        totals["v0.2 programs"] += len((v2 or {}).get("programs", []))
        totals["v0.3 programs"] += len((v3 or {}).get("programs", []))
        totals["v0.2 language tests"] += count_language_tests(v2 or {})
        totals["v0.3 language tests"] += count_language_tests(v3 or {})
        rows.append(version_comparison_row(name, v2, v3, v2_status.get(name, "not_recorded"), v3_status.get(name, "not_recorded")))
    body = "".join(
        [
            "<header><h1>v0.2 vs v0.3 admissions crawler comparison</h1>",
            "<p>Summary-level comparison of the preserved v0.2 snapshot and the v0.3 crawler rerun.</p></header>",
            "<main><section>",
            render_meta_grid(totals),
            "</section><section><h2>Schools</h2>",
            "<table><thead><tr><th>School</th><th>v0.2 Programs</th><th>v0.3 Programs</th>",
            "<th>v0.2 Language</th><th>v0.3 Language</th><th>v0.2 Tests</th><th>v0.3 Tests</th>",
            "<th>v0.2 Review</th><th>v0.3 Review</th><th>v0.2 Status</th><th>v0.3 Status</th><th>Assessment</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody></table></section></main>",
        ]
    )
    output = html_dir / "comparisons" / "v0_2_vs_v0_3.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page("v0.2 vs v0.3 comparison", body) + "\n", encoding="utf-8")
    return output


def render_llm_comparisons(outputs_dir: Path, html_dir: Path) -> list[Path]:
    crawler_paths = index_by_school(outputs_dir / "v0_3")
    llm_paths = index_by_school(outputs_dir / "v0_3" / "llm_native")
    output_dir = html_dir / "comparisons" / "v0_3_vs_llm"
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for name, llm_path in sorted(llm_paths.items()):
        crawler_path = crawler_paths.get(name)
        if not crawler_path:
            continue
        output_path = output_dir / f"{slugify(name)}.html"
        content = render_comparison(
            load_json(crawler_path),
            load_json(llm_path),
            crawler_path,
            llm_path,
            f"{name}: v0.3 crawler vs LLM-native",
        )
        output_path.write_text(content + "\n", encoding="utf-8")
        rendered.append(output_path)
    return rendered


def link(path: Path, html_dir: Path, label: str) -> str:
    return f'<a href="{escape(path.relative_to(html_dir).as_posix())}">{escape(label)}</a>'


def render_dashboard_index(outputs_dir: Path, html_dir: Path, version_page: Path, llm_pages: list[Path]) -> Path:
    v2_paths = index_by_school(outputs_dir / "v0_2")
    v3_paths = index_by_school(outputs_dir / "v0_3")
    llm_paths = index_by_school(outputs_dir / "v0_3" / "llm_native")
    llm_page_by_slug = {path.stem: path for path in llm_pages}
    names = sorted(set(v2_paths) | set(v3_paths) | set(llm_paths))
    rows = []
    for name in names:
        slug = slugify(name)
        v2_link = link(html_dir / "v0_2" / f"{v2_paths[name].stem}.html", html_dir, "v0.2") if name in v2_paths else ""
        v3_link = link(html_dir / "v0_3" / f"{v3_paths[name].stem}.html", html_dir, "v0.3") if name in v3_paths else ""
        llm_link = link(html_dir / "v0_3" / "llm_native" / f"{llm_paths[name].stem}.html", html_dir, "LLM-native") if name in llm_paths else ""
        compare_link = link(llm_page_by_slug[slug], html_dir, "v0.3 vs LLM") if slug in llm_page_by_slug else ""
        rows.append(
            "<tr>"
            f"<td>{escape(name)}</td>"
            f"<td>{v2_link}</td><td>{v3_link}</td><td>{llm_link}</td><td>{compare_link}</td>"
            "</tr>"
        )
    body = "".join(
        [
            "<header><h1>Admissions Review Dashboard</h1>",
            "<p>Versioned crawler outputs, LLM-native readings, and comparison pages.</p></header>",
            "<main><section>",
            render_meta_grid(
                {
                    "generated_at": dt.datetime.now(dt.UTC).isoformat(),
                    "v0.2 schools": len(v2_paths),
                    "v0.3 schools": len(v3_paths),
                    "llm-native schools": len(llm_paths),
                }
            ),
            "</section><section><h2>Comparison Reports</h2><ul>",
            f"<li>{link(version_page, html_dir, 'v0.2 vs v0.3 crawler improvement')}</li>",
            "</ul></section><section><h2>Schools</h2>",
            "<table><thead><tr><th>School</th><th>v0.2 Review</th><th>v0.3 Review</th><th>LLM-native Review</th><th>Comparison</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody></table></section></main>",
        ]
    )
    output = html_dir / "index.html"
    output.write_text(page("Admissions Review Dashboard", body) + "\n", encoding="utf-8")
    return output


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render versioned admissions review dashboard.")
    parser.add_argument("--outputs-dir", default=str(DEFAULT_OUTPUTS_DIR))
    parser.add_argument("--html-dir", default=str(DEFAULT_HTML_DIR))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    outputs_dir = Path(args.outputs_dir)
    html_dir = Path(args.html_dir)
    html_dir.mkdir(parents=True, exist_ok=True)
    copy_nit_llm(outputs_dir)
    reviews = render_reviews(outputs_dir, html_dir)
    version_page = render_version_comparison(outputs_dir, html_dir)
    llm_pages = render_llm_comparisons(outputs_dir, html_dir)
    index = render_dashboard_index(outputs_dir, html_dir, version_page, llm_pages)
    result = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "index": str(index),
        "review_pages": len(reviews),
        "llm_comparison_pages": len(llm_pages),
        "version_comparison": str(version_page),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
