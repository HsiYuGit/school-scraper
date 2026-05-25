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
        build_strategy_matrix,
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
        build_strategy_matrix,
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
    for version in ("v0_2", "v0_3", "v0_4"):
        source_dir = outputs_dir / version
        if source_dir.exists():
            target_dir = html_dir / version
            for path in sorted(source_dir.glob("*.json")):
                rendered.append(render_file(path, target_dir))
    for llm_name in ("llm_native", "llm_native_v0_2"):
        llm_dir = outputs_dir / "v0_3" / llm_name
        if llm_dir.exists():
            target_dir = html_dir / "v0_3" / llm_name
            for path in sorted(llm_dir.glob("*.json")):
                rendered.append(render_file(path, target_dir))
    for source_name in ("source_daad", "source_mgu"):
        source_dir = outputs_dir / source_name
        if source_dir.exists():
            target_dir = html_dir / source_name
            for path in sorted(source_dir.glob("*.json")):
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


def version_comparison_row(
    name: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    before_status: str,
    after_status: str,
) -> str:
    before_programs = len(before.get("programs", [])) if before else 0
    after_programs = len(after.get("programs", [])) if after else 0
    before_lang = count_language_tests(before or {})
    after_lang = count_language_tests(after or {})
    before_tests = count_test_requirements(before or {})
    after_tests = count_test_requirements(after or {})
    before_review = (before or {}).get("crawl_summary", {}).get("programs_needing_human_review")
    after_review = (after or {}).get("crawl_summary", {}).get("programs_needing_human_review")
    observations: list[str] = []
    if before_programs > after_programs:
        observations.append("Fewer final program records; likely reduced non-program false positives.")
    if before_programs == 0 and after_programs > 0:
        observations.append("Recovered programs from previous zero-program output.")
    if after_lang > before_lang:
        observations.append("More language requirements extracted.")
    if after_status == "broken_or_needs_review":
        observations.append("Zero or weak extraction is now explicitly flagged.")
    if not observations:
        observations.append("No clear summary-level improvement; inspect detail pages.")
    return (
        "<tr>"
        f"<td>{escape(name)}</td>"
        f"<td>{before_programs}</td><td>{after_programs}</td>"
        f"<td>{before_lang}</td><td>{after_lang}</td>"
        f"<td>{before_tests}</td><td>{after_tests}</td>"
        f"<td>{escape(before_review)}</td><td>{escape(after_review)}</td>"
        f"<td>{escape(before_status)}</td><td>{escape(after_status)}</td>"
        f"<td>{format_value(observations)}</td>"
        "</tr>"
    )


def render_version_comparison(
    outputs_dir: Path,
    html_dir: Path,
    before_version: str = "v0_2",
    after_version: str = "v0_3",
) -> Path:
    before_paths = index_by_school(outputs_dir / before_version)
    after_paths = index_by_school(outputs_dir / after_version)
    before_status = manifest_status(outputs_dir / before_version / "partner_school_crawl_manifest.json")
    after_status = manifest_status(outputs_dir / after_version / "partner_school_crawl_manifest.json")
    names = sorted(set(before_paths) | set(after_paths))
    rows = []
    totals = {
        f"{before_version} programs": 0,
        f"{after_version} programs": 0,
        f"{before_version} language tests": 0,
        f"{after_version} language tests": 0,
        f"{after_version} broken/review schools": sum(1 for value in after_status.values() if value == "broken_or_needs_review"),
    }
    for name in names:
        before = load_json(before_paths[name]) if name in before_paths else None
        after = load_json(after_paths[name]) if name in after_paths else None
        totals[f"{before_version} programs"] += len((before or {}).get("programs", []))
        totals[f"{after_version} programs"] += len((after or {}).get("programs", []))
        totals[f"{before_version} language tests"] += count_language_tests(before or {})
        totals[f"{after_version} language tests"] += count_language_tests(after or {})
        rows.append(
            version_comparison_row(
                name,
                before,
                after,
                before_status.get(name, "not_recorded"),
                after_status.get(name, "not_recorded"),
            )
        )
    before_label = before_version.replace("_", ".")
    after_label = after_version.replace("_", ".")
    body = "".join(
        [
            f"<header><h1>{escape(before_label)} vs {escape(after_label)} admissions crawler comparison</h1>",
            f"<p>Summary-level comparison of the preserved {escape(before_label)} snapshot and the {escape(after_label)} crawler rerun.</p></header>",
            "<main><section>",
            render_meta_grid(totals),
            "</section><section><h2>Schools</h2>",
            f"<table><thead><tr><th>School</th><th>{escape(before_label)} Programs</th><th>{escape(after_label)} Programs</th>",
            f"<th>{escape(before_label)} Language</th><th>{escape(after_label)} Language</th><th>{escape(before_label)} Tests</th><th>{escape(after_label)} Tests</th>",
            f"<th>{escape(before_label)} Review</th><th>{escape(after_label)} Review</th><th>{escape(before_label)} Status</th><th>{escape(after_label)} Status</th><th>Assessment</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody></table></section></main>",
        ]
    )
    output = html_dir / "comparisons" / f"{before_version}_vs_{after_version}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page(f"{before_label} vs {after_label} comparison", body) + "\n", encoding="utf-8")
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
            "v0.3 crawler output",
            "LLM v0.1 output",
        )
        output_path.write_text(content + "\n", encoding="utf-8")
        rendered.append(output_path)
    return rendered


def render_pairwise_comparisons(
    left_paths: dict[str, Path],
    right_paths: dict[str, Path],
    html_dir: Path,
    output_subdir: str,
    title_template: str,
    left_label: str,
    right_label: str,
) -> list[Path]:
    output_dir = html_dir / "comparisons" / output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for name in sorted(set(left_paths) & set(right_paths)):
        left_path = left_paths[name]
        right_path = right_paths[name]
        output_path = output_dir / f"{slugify(name)}.html"
        content = render_comparison(
            load_json(left_path),
            load_json(right_path),
            left_path,
            right_path,
            title_template.format(name=name),
            left_label,
            right_label,
        )
        output_path.write_text(content + "\n", encoding="utf-8")
        rendered.append(output_path)
    return rendered


def warning_badges(warnings: list[str]) -> str:
    return "".join(f'<span class="badge warn">{escape(warning)}</span>' for warning in warnings)


def render_strategy_matrix_page(name: str, strategies: dict[str, dict[str, Any]]) -> str:
    matrix = build_strategy_matrix(strategies)
    warnings = matrix["coverage_warnings"]
    warning_items = "".join(f"<li>{escape(warning)}</li>" for warning in warnings) or '<li><span class="small">None</span></li>'
    rows = []
    for row in matrix["programmes"]:
        rows.append(
            "<tr>"
            f"<td>{escape(row['status'])}</td>"
            f"<td>{format_value(row['present_in'])}</td>"
            f"<td>{escape(row['key'])}</td>"
            f"<td>{format_value(row.get('record_counts'))}</td>"
            "</tr>"
        )
    strategy_json = {
        "strategies": strategies,
        "matrix": matrix,
    }
    body = "".join(
        [
            "<header>",
            f"<h1>{escape(name)}: strategy comparison</h1>",
            "<p>Official crawler, official LLM, DAAD, and My German University outputs where available.</p>",
            "</header>",
            "<main>",
            "<section><h2>Coverage Warnings</h2>",
            f"<ul>{warning_items}</ul>",
            "</section>",
            "<section><h2>Programme Matching</h2>",
            "<table><thead><tr><th>Status</th><th>Present In</th><th>Programme Key</th><th>Record Counts</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody></table>",
            "</section>",
            "<section><h2>Full Strategy JSON</h2>",
            "<details><summary>Payloads</summary>",
            f"<pre>{escape(json.dumps(strategy_json, ensure_ascii=False, indent=2))}</pre>",
            "</details></section>",
            "</main>",
        ]
    )
    return page(f"{name}: strategy comparison", body)


def render_strategy_matrix_pages(outputs_dir: Path, html_dir: Path) -> list[dict[str, Any]]:
    strategy_roots = {
        "official_crawler": outputs_dir / "v0_4",
        "official_llm": outputs_dir / "v0_3" / "llm_native_v0_2",
        "daad": outputs_dir / "source_daad",
        "mgu": outputs_dir / "source_mgu",
    }
    indexes = {strategy: index_by_school(root) for strategy, root in strategy_roots.items()}
    names = sorted({name for paths in indexes.values() for name in paths})
    output_dir = html_dir / "comparisons" / "strategy_matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[dict[str, Any]] = []
    for name in names:
        strategies = {
            strategy: load_json(paths[name])
            for strategy, paths in indexes.items()
            if name in paths
        }
        matrix = build_strategy_matrix(strategies)
        output_path = output_dir / f"{slugify(name)}.html"
        output_path.write_text(render_strategy_matrix_page(name, strategies) + "\n", encoding="utf-8")
        rendered.append(
            {
                "school": name,
                "path": output_path,
                "coverage_warnings": matrix["coverage_warnings"],
                "strategy_count": len(strategies),
            }
        )
    return rendered


def link(path: Path, html_dir: Path, label: str) -> str:
    return f'<a href="{escape(path.relative_to(html_dir).as_posix())}">{escape(label)}</a>'


def render_dashboard_index(
    outputs_dir: Path,
    html_dir: Path,
    version_pages: dict[str, Path],
    llm_pages: list[Path],
    llm_v0_2_pages: list[Path],
    crawler_llm_v0_2_pages: list[Path],
    strategy_pages: list[dict[str, Any]],
) -> Path:
    v2_paths = index_by_school(outputs_dir / "v0_2")
    v3_paths = index_by_school(outputs_dir / "v0_3")
    v4_paths = index_by_school(outputs_dir / "v0_4")
    llm_paths = index_by_school(outputs_dir / "v0_3" / "llm_native")
    llm_v0_2_paths = index_by_school(outputs_dir / "v0_3" / "llm_native_v0_2")
    source_daad_paths = index_by_school(outputs_dir / "source_daad")
    source_mgu_paths = index_by_school(outputs_dir / "source_mgu")
    llm_page_by_slug = {path.stem: path for path in llm_pages}
    llm_v0_2_page_by_slug = {path.stem: path for path in llm_v0_2_pages}
    crawler_llm_v0_2_page_by_slug = {path.stem: path for path in crawler_llm_v0_2_pages}
    strategy_page_by_slug = {path_info["path"].stem: path_info for path_info in strategy_pages}
    names = sorted(
        set(v2_paths)
        | set(v3_paths)
        | set(v4_paths)
        | set(llm_paths)
        | set(llm_v0_2_paths)
        | set(source_daad_paths)
        | set(source_mgu_paths)
    )
    rows = []
    for name in names:
        slug = slugify(name)
        v2_link = link(html_dir / "v0_2" / f"{v2_paths[name].stem}.html", html_dir, "v0.2") if name in v2_paths else ""
        v3_link = link(html_dir / "v0_3" / f"{v3_paths[name].stem}.html", html_dir, "v0.3") if name in v3_paths else ""
        v4_link = link(html_dir / "v0_4" / f"{v4_paths[name].stem}.html", html_dir, "v0.4") if name in v4_paths else ""
        llm_link = link(html_dir / "v0_3" / "llm_native" / f"{llm_paths[name].stem}.html", html_dir, "LLM v0.1") if name in llm_paths else ""
        llm_v0_2_link = link(html_dir / "v0_3" / "llm_native_v0_2" / f"{llm_v0_2_paths[name].stem}.html", html_dir, "LLM v0.2") if name in llm_v0_2_paths else ""
        source_daad_link = link(html_dir / "source_daad" / f"{source_daad_paths[name].stem}.html", html_dir, "DAAD (source_daad)") if name in source_daad_paths else ""
        source_mgu_link = link(html_dir / "source_mgu" / f"{source_mgu_paths[name].stem}.html", html_dir, "My German University (source_mgu)") if name in source_mgu_paths else ""
        compare_link = link(llm_page_by_slug[slug], html_dir, "v0.3 vs LLM v0.1") if slug in llm_page_by_slug else ""
        llm_v0_2_compare = link(llm_v0_2_page_by_slug[slug], html_dir, "LLM v0.1 vs v0.2") if slug in llm_v0_2_page_by_slug else ""
        crawler_llm_v0_2_compare = link(crawler_llm_v0_2_page_by_slug[slug], html_dir, "v0.4 vs LLM v0.2") if slug in crawler_llm_v0_2_page_by_slug else ""
        strategy_info = strategy_page_by_slug.get(slug)
        strategy_link = link(strategy_info["path"], html_dir, "Strategy comparison") if strategy_info else ""
        warnings = warning_badges(strategy_info["coverage_warnings"]) if strategy_info else ""
        rows.append(
            "<tr>"
            f"<td>{escape(name)}</td>"
            f"<td>{v2_link}</td><td>{v3_link}</td><td>{v4_link}</td>"
            f"<td>{llm_link}</td><td>{llm_v0_2_link}</td><td>{source_daad_link}</td><td>{source_mgu_link}</td>"
            f"<td>{compare_link}</td><td>{llm_v0_2_compare}</td><td>{crawler_llm_v0_2_compare}</td><td>{strategy_link}</td><td>{warnings}</td>"
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
                    "v0.4 schools": len(v4_paths),
                    "LLM v0.1 schools": len(llm_paths),
                    "LLM v0.2 schools": len(llm_v0_2_paths),
                    "source_daad schools": len(source_daad_paths),
                    "source_mgu schools": len(source_mgu_paths),
                    "strategy comparison pages": len(strategy_pages),
                }
            ),
            "</section><section><h2>Comparison Reports</h2><ul>",
            f"<li>{link(version_pages['v0_2_vs_v0_3'], html_dir, 'v0.2 vs v0.3 crawler improvement')}</li>",
            f"<li>{link(version_pages['v0_3_vs_v0_4'], html_dir, 'v0.3 vs v0.4 crawler improvement')}</li>",
            f"<li>{link(strategy_pages[0]['path'], html_dir, 'Strategy comparison pages') if strategy_pages else 'Strategy comparison pages'}</li>",
            "</ul></section><section><h2>Schools</h2>",
            "<table><thead><tr><th>School</th><th>v0.2 Review</th><th>v0.3 Review</th><th>v0.4 Review</th>"
            "<th>LLM v0.1 Review</th><th>LLM v0.2 Review</th><th>DAAD (source_daad)</th><th>My German University (source_mgu)</th><th>v0.3 vs LLM v0.1</th>"
            "<th>LLM v0.1 vs v0.2</th><th>v0.4 vs LLM v0.2</th><th>Strategy comparison</th><th>Warnings</th></tr></thead>",
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
    version_pages = {
        "v0_2_vs_v0_3": render_version_comparison(outputs_dir, html_dir, "v0_2", "v0_3"),
        "v0_3_vs_v0_4": render_version_comparison(outputs_dir, html_dir, "v0_3", "v0_4"),
    }
    llm_pages = render_llm_comparisons(outputs_dir, html_dir)
    llm_v0_2_pages = render_pairwise_comparisons(
        index_by_school(outputs_dir / "v0_3" / "llm_native"),
        index_by_school(outputs_dir / "v0_3" / "llm_native_v0_2"),
        html_dir,
        "llm_v0_1_vs_v0_2",
        "{name}: LLM v0.1 vs v0.2",
        "LLM v0.1 output",
        "LLM v0.2 output",
    )
    crawler_llm_v0_2_pages = render_pairwise_comparisons(
        index_by_school(outputs_dir / "v0_4"),
        index_by_school(outputs_dir / "v0_3" / "llm_native_v0_2"),
        html_dir,
        "v0_4_vs_llm_v0_2",
        "{name}: v0.4 crawler vs LLM v0.2",
        "v0.4 crawler output",
        "LLM v0.2 output",
    )
    strategy_pages = render_strategy_matrix_pages(outputs_dir, html_dir)
    index = render_dashboard_index(
        outputs_dir,
        html_dir,
        version_pages,
        llm_pages,
        llm_v0_2_pages,
        crawler_llm_v0_2_pages,
        strategy_pages,
    )
    result = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "index": str(index),
        "review_pages": len(reviews),
        "llm_comparison_pages": len(llm_pages),
        "llm_v0_2_comparison_pages": len(llm_v0_2_pages),
        "v0_4_vs_llm_v0_2_pages": len(crawler_llm_v0_2_pages),
        "strategy_matrix_pages": len(strategy_pages),
        "version_comparisons": {key: str(path) for key, path in version_pages.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
