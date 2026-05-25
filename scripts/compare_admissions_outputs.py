"""Render side-by-side HTML comparisons for admissions JSON outputs."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from render_admissions_html import STYLE, format_value, json_pre, page, render_meta_grid
except ModuleNotFoundError:
    from scripts.render_admissions_html import STYLE, format_value, json_pre, page, render_meta_grid


DEFAULT_CRAWLER_JSON = Path("outputs/nit_northern_institute_of_technology_management_admissions.json")
DEFAULT_LLM_JSON = Path("outputs/nit_llm_native_admissions.json")
DEFAULT_OUTPUT = Path("outputs/html/nit_llm_vs_crawler_comparison.html")


def escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def program_names(payload: dict[str, Any]) -> list[str]:
    return [program.get("program", {}).get("name") or "Unnamed program" for program in payload.get("programs", [])]


def normalized_program_names(payload: dict[str, Any]) -> set[str]:
    return {name.lower().strip() for name in program_names(payload)}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def semantic_program_key(record: dict[str, Any]) -> str:
    program = record.get("program", {})
    name = _normalized_text(program.get("name"))
    degree = _normalized_text(program.get("degree"))
    level = _normalized_text(program.get("level"))
    return "name:" + " ".join(f"{name} {degree} {level}".split())


def normalize_program_key(record: dict[str, Any], strategy_name: str | None = None) -> str:
    source_id = _normalized_text(record.get("source_record_id"))
    if source_id:
        source_specific = record.get("source_specific", {})
        source_platform = source_specific.get("source_platform") if isinstance(source_specific, dict) else None
        namespace = _normalized_text(strategy_name or record.get("source_platform") or source_platform)
        if namespace:
            return f"id:{namespace}:{source_id}"
        return f"id:{source_id}"
    return semantic_program_key(record)


def build_strategy_matrix(strategies: dict[str, dict[str, Any]]) -> dict[str, Any]:
    coverage_warnings: list[str] = []
    records: list[tuple[str, dict[str, Any], str, str]] = []
    semantic_counts: dict[str, set[str]] = {}
    for strategy_name, payload in strategies.items():
        coverage = payload.get("source_coverage", {})
        if coverage.get("warning") and coverage.get("status"):
            coverage_warnings.append(str(coverage["status"]))
        for record in payload.get("programs", []):
            semantic_key = semantic_program_key(record)
            record_key = normalize_program_key(record, strategy_name)
            semantic_counts.setdefault(semantic_key, set()).add(strategy_name)
            records.append((strategy_name, record, record_key, semantic_key))

    grouped: dict[str, dict[str, Any]] = {}
    for strategy_name, record, record_key, semantic_key in records:
        key = semantic_key if len(semantic_counts.get(semantic_key, set())) > 1 else record_key
        grouped.setdefault(key, {"records": {}})
        grouped[key]["records"].setdefault(strategy_name, []).append(record)

    programmes: list[dict[str, Any]] = []
    strategy_names = set(strategies)
    for key, item in sorted(grouped.items()):
        present = set(item["records"])
        if len(present) == 1:
            status = f"only_in_{next(iter(present))}"
        elif present == strategy_names:
            status = "matched"
        else:
            status = "partially_matched"
        programmes.append(
            {
                "key": key,
                "status": status,
                "present_in": sorted(present),
                "record_counts": {
                    strategy_name: len(records)
                    for strategy_name, records in sorted(item["records"].items())
                },
                "records": item["records"],
            }
        )
    return {"coverage_warnings": sorted(set(coverage_warnings)), "programmes": programmes}


def language_tests(program: dict[str, Any]) -> list[str]:
    values = []
    for item in program.get("requirements", {}).get("language_requirements", []) or []:
        if isinstance(item, dict):
            label = item.get("test")
            score = item.get("minimum_score")
            values.append(f"{label}: {score}" if score else str(label))
        else:
            values.append(str(item))
    return values


def test_requirements(program: dict[str, Any]) -> list[str]:
    values = []
    for item in program.get("requirements", {}).get("test_requirements", []) or []:
        if isinstance(item, dict):
            label = item.get("test")
            requirement = item.get("requirement")
            values.append(f"{label}: {requirement}" if requirement else str(label))
        else:
            values.append(str(item))
    return values


def count_language_tests(payload: dict[str, Any]) -> int:
    return sum(len(language_tests(program)) for program in payload.get("programs", []))


def count_test_requirements(payload: dict[str, Any]) -> int:
    return sum(len(test_requirements(program)) for program in payload.get("programs", []))


def program_summary_rows(payload: dict[str, Any]) -> str:
    rows = []
    for index, record in enumerate(payload.get("programs", []), start=1):
        program = record.get("program", {})
        requirements = record.get("requirements", {})
        work = requirements.get("work_experience", {}) if isinstance(requirements.get("work_experience"), dict) else {}
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(program.get('name'))}<div class=\"small\">{escape(program.get('url'))}</div></td>"
            f"<td>{escape(program.get('degree'))}</td>"
            f"<td>{format_value(program.get('language_of_instruction'))}</td>"
            f"<td>{format_value(language_tests(record))}</td>"
            f"<td>{format_value(test_requirements(record))}</td>"
            f"<td>{escape(work.get('minimum_years'))}</td>"
            f"<td>{'Yes' if record.get('needs_human_review') else 'No'}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_program_table(title: str, payload: dict[str, Any]) -> str:
    return (
        "<section>"
        f"<h2>{escape(title)}</h2>"
        "<table><thead><tr>"
        "<th>#</th><th>Program</th><th>Degree</th><th>Instruction language</th>"
        "<th>Language tests</th><th>Other tests</th><th>Work years</th><th>Review</th>"
        "</tr></thead>"
        f"<tbody>{program_summary_rows(payload)}</tbody></table>"
        "</section>"
    )


def render_difference_summary(
    crawler: dict[str, Any],
    llm: dict[str, Any],
    crawler_label: str = "crawler",
    llm_label: str = "LLM-native",
) -> str:
    crawler_names = program_names(crawler)
    llm_names = program_names(llm)
    crawler_tests = sorted({value for program in crawler.get("programs", []) for value in test_requirements(program)})
    llm_tests = sorted({value for program in llm.get("programs", []) for value in test_requirements(program)})
    crawler_languages = sorted({value for program in crawler.get("programs", []) for value in language_tests(program)})
    llm_languages = sorted({value for program in llm.get("programs", []) for value in language_tests(program)})
    only_crawler = sorted(set(crawler_names) - set(llm_names))
    only_llm = sorted(set(llm_names) - set(crawler_names))
    observations = []
    if len(crawler_names) != len(llm_names):
        observations.append("Program counts differ; review whether the difference is a true coverage gap or a non-program page.")
    if count_language_tests(llm) > count_language_tests(crawler):
        observations.append(f"{llm_label} found more language-test details than {crawler_label}.")
    if count_test_requirements(crawler) > count_test_requirements(llm):
        observations.append(f"{crawler_label} emitted more test requirements than {llm_label}; inspect for keyword false positives.")
    if only_crawler:
        observations.append(f"{crawler_label}-only program names may include false positives or naming differences.")
    if only_llm:
        observations.append(f"{llm_label}-only program names may indicate discovery gaps.")
    if not observations:
        observations.append(f"{crawler_label} and {llm_label} outputs are broadly aligned at the summary level.")
    return (
        "<section>"
        "<h2>Difference Summary</h2>"
        + render_meta_grid(
            {
                f"{crawler_label}_program_count": len(crawler_names),
                f"{llm_label}_program_count": len(llm_names),
                f"{crawler_label}_program_names": crawler_names,
                f"{llm_label}_program_names": llm_names,
                f"{crawler_label}_only_names": only_crawler,
                f"{llm_label}_only_names": only_llm,
                f"{crawler_label}_language_tests": crawler_languages,
                f"{llm_label}_language_tests": llm_languages,
                f"{crawler_label}_other_tests": crawler_tests,
                f"{llm_label}_other_tests": llm_tests,
            }
        )
        + "<h3>Assessment</h3>"
        + format_value(observations)
        + "</section>"
    )


def render_comparison(
    crawler: dict[str, Any],
    llm: dict[str, Any],
    crawler_path: Path,
    llm_path: Path,
    title: str | None = None,
    crawler_label: str = "Crawler output",
    llm_label: str = "LLM-native output",
) -> str:
    generated_at = dt.datetime.now(dt.UTC).isoformat()
    school_name = crawler.get("school", {}).get("name") or llm.get("school", {}).get("name") or "Admissions"
    page_title = title or f"{school_name}: crawler vs LLM-native reading"
    body = "".join(
        [
            "<header>",
            f"<h1>{escape(page_title)}</h1>",
            f"<p>Generated at {escape(generated_at)} from {escape(crawler_path.name)} and {escape(llm_path.name)}.</p>",
            "</header>",
            "<main>",
            render_difference_summary(crawler, llm, crawler_label, llm_label),
            render_program_table(crawler_label, crawler),
            render_program_table(llm_label, llm),
            "<section><h2>Method Metadata</h2>",
            render_meta_grid(
                {
                    "crawler_schema": crawler.get("schema_version"),
                    "crawler_retrieved_at": crawler.get("retrieved_at"),
                    "crawler_pages_fetched": crawler.get("crawl_summary", {}).get("pages_fetched"),
                    "llm_schema": llm.get("schema_version"),
                    "llm_created_at": llm.get("method", {}).get("created_at"),
                    "llm_model": llm.get("method", {}).get("agent", {}).get("model"),
                    "llm_reasoning_effort": llm.get("method", {}).get("agent", {}).get("reasoning_effort"),
                    "llm_token_usage": llm.get("method", {}).get("cost_tracking", {}).get("token_usage"),
                    "llm_estimated_cost": llm.get("method", {}).get("cost_tracking", {}).get("estimated_usd_cost"),
                }
            ),
            "</section>",
            "<section><details><summary>Full crawler JSON</summary>",
            f"<pre>{json_pre(crawler)}</pre>",
            "</details><details><summary>Full LLM-native JSON</summary>",
            f"<pre>{json_pre(llm)}</pre>",
            "</details></section>",
            "</main>",
        ]
    )
    return page(page_title, body)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two admissions JSON outputs as static HTML.")
    parser.add_argument("--crawler-json", default=str(DEFAULT_CRAWLER_JSON))
    parser.add_argument("--llm-json", default=str(DEFAULT_LLM_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--title", default=None)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    crawler_path = Path(args.crawler_json)
    llm_path = Path(args.llm_json)
    output_path = Path(args.out)
    content = render_comparison(load_json(crawler_path), load_json(llm_path), crawler_path, llm_path, args.title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content + "\n", encoding="utf-8")
    print(json.dumps({"generated_at": dt.datetime.now(dt.UTC).isoformat(), "html_file": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
