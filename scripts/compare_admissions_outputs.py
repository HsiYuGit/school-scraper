"""Render a side-by-side HTML comparison for two admissions JSON outputs."""

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


def render_difference_summary(crawler: dict[str, Any], llm: dict[str, Any]) -> str:
    crawler_names = program_names(crawler)
    llm_names = program_names(llm)
    crawler_tests = sorted({value for program in crawler.get("programs", []) for value in test_requirements(program)})
    llm_tests = sorted({value for program in llm.get("programs", []) for value in test_requirements(program)})
    crawler_languages = sorted({value for program in crawler.get("programs", []) for value in language_tests(program)})
    llm_languages = sorted({value for program in llm.get("programs", []) for value in language_tests(program)})
    observations = [
        "Crawler output still keeps Technology Management overview and Single Degree as separate records, while the LLM-native output groups Technology Management modes under one program family.",
        "Crawler output discovers Business Analytics & AI after the path fix, but still misses the admissions-page TOEFL/IELTS/C1 language thresholds.",
        "Crawler output no longer emits the previous false GRE requirement; LLM-native output explicitly records GRE/GMAT as not required or not stated.",
        "LLM-native output captures conditional degree outcomes and visa/ECTS study-mode logic that the crawler does not currently model."
    ]
    return (
        "<section>"
        "<h2>Difference Summary</h2>"
        + render_meta_grid(
            {
                "crawler_program_count": len(crawler_names),
                "llm_program_count": len(llm_names),
                "crawler_program_names": crawler_names,
                "llm_program_names": llm_names,
                "crawler_language_tests": crawler_languages,
                "llm_language_tests": llm_languages,
                "crawler_other_tests": crawler_tests,
                "llm_other_tests": llm_tests,
            }
        )
        + "<h3>Assessment</h3>"
        + format_value(observations)
        + "</section>"
    )


def render_comparison(crawler: dict[str, Any], llm: dict[str, Any], crawler_path: Path, llm_path: Path) -> str:
    generated_at = dt.datetime.now(dt.UTC).isoformat()
    body = "".join(
        [
            "<header>",
            "<h1>NIT admissions: crawler vs LLM-native reading</h1>",
            f"<p>Generated at {escape(generated_at)} from {escape(crawler_path.name)} and {escape(llm_path.name)}.</p>",
            "</header>",
            "<main>",
            render_difference_summary(crawler, llm),
            render_program_table("Crawler output", crawler),
            render_program_table("LLM-native output", llm),
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
    return page("NIT crawler vs LLM-native comparison", body)


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two admissions JSON outputs as static HTML.")
    parser.add_argument("--crawler-json", default=str(DEFAULT_CRAWLER_JSON))
    parser.add_argument("--llm-json", default=str(DEFAULT_LLM_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    crawler_path = Path(args.crawler_json)
    llm_path = Path(args.llm_json)
    output_path = Path(args.out)
    content = render_comparison(load_json(crawler_path), load_json(llm_path), crawler_path, llm_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content + "\n", encoding="utf-8")
    print(json.dumps({"generated_at": dt.datetime.now(dt.UTC).isoformat(), "html_file": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
