"""Render admissions JSON outputs into static HTML review pages."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_INPUT = Path("outputs")
DEFAULT_OUTPUT_DIR = Path("outputs/html")


STYLE = """
:root {
  color-scheme: light;
  --bg: #f7f8fb;
  --panel: #ffffff;
  --ink: #1d2433;
  --muted: #647084;
  --line: #d9dfeb;
  --accent: #0f766e;
  --warn: #b45309;
  --soft: #eef7f5;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Arial, "Noto Sans", sans-serif;
  line-height: 1.5;
}
a { color: var(--accent); overflow-wrap: anywhere; }
header {
  background: #0f172a;
  color: #fff;
  padding: 28px clamp(20px, 5vw, 56px);
}
header p { color: #cbd5e1; margin: 8px 0 0; }
main { max-width: 1180px; margin: 0 auto; padding: 24px; }
section, article {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  margin: 0 0 18px;
  padding: 18px;
}
h1, h2, h3 { line-height: 1.2; margin: 0 0 12px; }
h1 { font-size: 30px; }
h2 { font-size: 22px; }
h3 { font-size: 18px; }
.meta-grid, .stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.cell, .stat {
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
}
.label {
  color: var(--muted);
  display: block;
  font-size: 12px;
  text-transform: uppercase;
}
.value { font-weight: 600; overflow-wrap: anywhere; }
.badge {
  background: var(--soft);
  border: 1px solid #b7ddd5;
  border-radius: 999px;
  color: #115e59;
  display: inline-block;
  font-size: 12px;
  margin: 2px 4px 2px 0;
  padding: 2px 8px;
}
.badge.warn {
  background: #fff7ed;
  border-color: #fed7aa;
  color: var(--warn);
}
table {
  border-collapse: collapse;
  margin: 10px 0;
  width: 100%;
}
th, td {
  border: 1px solid var(--line);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
th { background: #f1f5f9; }
details {
  border-top: 1px solid var(--line);
  margin-top: 12px;
  padding-top: 12px;
}
summary { cursor: pointer; font-weight: 700; }
pre {
  background: #111827;
  border-radius: 6px;
  color: #e5e7eb;
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
}
.program-header {
  display: flex;
  gap: 10px;
  justify-content: space-between;
  align-items: flex-start;
}
.program-title { min-width: 0; }
.small { color: var(--muted); font-size: 13px; }
ul { margin: 8px 0 0; padding-left: 20px; }
""".strip()


def escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def json_pre(value: Any) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2))


def list_items(values: Iterable[Any]) -> str:
    items = [f"<li>{format_value(item)}</li>" for item in values]
    return f"<ul>{''.join(items)}</ul>" if items else ""


def format_value(value: Any) -> str:
    if value is None:
        return '<span class="small">Not found</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        if not value:
            return '<span class="small">None</span>'
        if all(not isinstance(item, (dict, list)) for item in value):
            return " ".join(f'<span class="badge">{escape(item)}</span>' for item in value)
        return list_items(value)
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            rows.append(f"<tr><th>{escape(key)}</th><td>{format_value(item)}</td></tr>")
        return f"<table>{''.join(rows)}</table>" if rows else '<span class="small">None</span>'
    return escape(value)


def page(title: str, body: str) -> str:
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)}</title>",
            f"<style>{STYLE}</style>",
            "</head>",
            "<body>",
            body,
            "</body>",
            "</html>",
        ]
    )


def render_meta_grid(items: dict[str, Any]) -> str:
    cells = []
    for label, value in items.items():
        cells.append(
            '<div class="cell">'
            f'<span class="label">{escape(label)}</span>'
            f'<span class="value">{format_value(value)}</span>'
            "</div>"
        )
    return f'<div class="meta-grid">{"".join(cells)}</div>'


def render_summary(payload: dict[str, Any]) -> str:
    school = payload.get("school", {})
    crawl_summary = payload.get("crawl_summary", {})
    crawler_policy = payload.get("crawler_policy", {})
    body = [
        "<section>",
        "<h2>School</h2>",
        render_meta_grid(
            {
                "name": school.get("name"),
                "country": school.get("country"),
                "partner_status": school.get("partner_status"),
                "school_type": school.get("school_type"),
                "school_url": school.get("url"),
                "retrieved_at": payload.get("retrieved_at"),
                "schema_version": payload.get("schema_version"),
            }
        ),
        "</section>",
        "<section>",
        "<h2>Crawl Summary</h2>",
        render_meta_grid(crawl_summary),
        "<details><summary>Crawler policy</summary>",
        format_value(crawler_policy),
        "</details>",
        "</section>",
    ]
    if payload.get("review_seed_config"):
        body.extend(
            [
                "<section>",
                "<h2>Reviewed Seed Config</h2>",
                format_value(payload["review_seed_config"]),
                "</section>",
            ]
        )
    return "".join(body)


def render_application(application: dict[str, Any]) -> str:
    return (
        "<h3>Application</h3>"
        + render_meta_grid(
            {
                "deadlines": application.get("deadlines"),
                "intakes": application.get("intakes"),
                "application_channel": application.get("application_channel"),
                "uni_assist_or_vpd": application.get("uni_assist_or_vpd"),
                "fees": application.get("fees"),
            }
        )
    )


def render_evidence(evidence: dict[str, Any]) -> str:
    if isinstance(evidence, list):
        evidence = {"evidence": evidence}
    if not isinstance(evidence, dict):
        evidence = {}
    groups = []
    for group_name, items in evidence.items():
        rows = []
        for item in items or []:
            if isinstance(item, dict):
                source_url = item.get("source_url")
                rows.append(
                    "<tr>"
                    f"<td>{escape(item.get('confidence'))}</td>"
                    f"<td><a href=\"{escape(source_url)}\">{escape(source_url)}</a></td>"
                    f"<td>{escape(item.get('source_text'))}</td>"
                    f"<td>{escape(item.get('review_note'))}</td>"
                    "</tr>"
                )
            else:
                source_url = str(item)
                rows.append(
                    "<tr>"
                    "<td></td>"
                    f"<td><a href=\"{escape(source_url)}\">{escape(source_url)}</a></td>"
                    "<td></td>"
                    f"<td>{escape(group_name)}</td>"
                    "</tr>"
                )
        if rows:
            groups.append(
                f"<details><summary>{escape(group_name)} ({len(rows)})</summary>"
                "<table><thead><tr><th>Confidence</th><th>URL</th><th>Text</th><th>Review note</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table></details>"
            )
    return "<h3>Evidence</h3>" + ("".join(groups) if groups else '<p class="small">No evidence items.</p>')


def render_raw_sections(raw_sections: list[dict[str, Any]]) -> str:
    rows = []
    for item in raw_sections:
        rows.append(
            "<tr>"
            f"<td>{escape(item.get('heading'))}</td>"
            f"<td>{escape(item.get('source_url'))}</td>"
            f"<td>{escape(item.get('text'))}</td>"
            "</tr>"
        )
    if not rows:
        return '<h3>Raw Evidence Sections</h3><p class="small">No raw evidence sections.</p>'
    return (
        "<h3>Raw Evidence Sections</h3>"
        "<table><thead><tr><th>Heading</th><th>URL</th><th>Text</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_program(program_record: dict[str, Any], index: int) -> str:
    program = program_record.get("program", {})
    needs_review = program_record.get("needs_human_review")
    review_badge = '<span class="badge warn">Needs human review</span>' if needs_review else ""
    return "".join(
        [
            "<article>",
            '<div class="program-header">',
            '<div class="program-title">',
            f"<h2>{index}. {escape(program.get('name') or 'Unnamed program')}</h2>",
            f'<p class="small"><a href="{escape(program.get("url"))}">{escape(program.get("url"))}</a></p>',
            "</div>",
            review_badge,
            "</div>",
            render_meta_grid(
                {
                    "degree": program.get("degree"),
                    "level": program.get("level"),
                    "campus": program.get("campus"),
                    "language": program.get("language_of_instruction"),
                    "parent_program": program.get("parent_program"),
                    "specialization": program.get("specialization"),
                }
            ),
            "<h3>Requirements</h3>",
            format_value(program_record.get("requirements", {})),
            render_application(program_record.get("application", {})),
            render_evidence(program_record.get("evidence", {})),
            render_raw_sections(program_record.get("raw_evidence_sections", [])),
            "<details><summary>Full JSON for this program</summary>",
            f"<pre>{json_pre(program_record)}</pre>",
            "</details>",
            "</article>",
        ]
    )


def render_admissions(payload: dict[str, Any], source_path: Path) -> str:
    school_name = payload.get("school", {}).get("name") or source_path.stem
    programs = payload.get("programs", [])
    title = f"{school_name} admissions review"
    program_html = "".join(render_program(program, index) for index, program in enumerate(programs, start=1))
    body = "".join(
        [
            "<header>",
            f"<h1>{escape(school_name)}</h1>",
            f"<p>Admissions JSON review page generated from {escape(source_path.name)}.</p>",
            "</header>",
            "<main>",
            render_summary(payload),
            "<section>",
            f"<h2>Programs ({len(programs)})</h2>",
            "</section>",
            program_html or '<section><p class="small">No programs extracted.</p></section>',
            "<section><details><summary>Full source JSON</summary>",
            f"<pre>{json_pre(payload)}</pre>",
            "</details></section>",
            "</main>",
        ]
    )
    return page(title, body)


def render_manifest(payload: dict[str, Any], source_path: Path) -> str:
    rows = []
    for school in payload.get("schools", []):
        output_path = school.get("output_path")
        html_name = Path(output_path).with_suffix(".html").name if output_path else ""
        link = f'<a href="{escape(html_name)}">{escape(school.get("school"))}</a>' if html_name else escape(school.get("school"))
        summary = school.get("crawl_summary", {})
        rows.append(
            "<tr>"
            f"<td>{link}</td>"
            f"<td>{escape(school.get('partner_status'))}</td>"
            f"<td>{escape(school.get('robots_status'))}</td>"
            f"<td>{escape(summary.get('pages_fetched'))}</td>"
            f"<td>{escape(summary.get('programs_extracted'))}</td>"
            f"<td>{escape(summary.get('programs_needing_human_review'))}</td>"
            "</tr>"
        )
    body = "".join(
        [
            "<header>",
            "<h1>Partner School Crawl Manifest</h1>",
            f"<p>Generated from {escape(source_path.name)}.</p>",
            "</header>",
            "<main><section>",
            render_meta_grid(
                {
                    "generated_at": payload.get("generated_at"),
                    "school_count": payload.get("school_count"),
                    "max_pages": payload.get("max_pages"),
                    "delay_seconds": payload.get("delay_seconds"),
                    "timeout_seconds": payload.get("timeout_seconds"),
                }
            ),
            "</section><section>",
            "<h2>Schools</h2>",
            "<table><thead><tr><th>School</th><th>Partner</th><th>Robots</th><th>Pages</th><th>Programs</th><th>Review</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody></table>",
            "</section><section><details><summary>Full manifest JSON</summary>",
            f"<pre>{json_pre(payload)}</pre>",
            "</details></section></main>",
        ]
    )
    return page("Partner school crawl manifest", body)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def html_name_for(path: Path) -> str:
    if path.name == "partner_school_crawl_manifest.json":
        return "index.html"
    return path.with_suffix(".html").name


def render_file(path: Path, output_dir: Path) -> Path:
    payload = load_json(path)
    if "programs" in payload:
        content = render_admissions(payload, path)
    elif "schools" in payload:
        content = render_manifest(payload, path)
    else:
        content = page(
            f"{path.name} JSON review",
            f"<header><h1>{escape(path.name)}</h1></header><main><section><pre>{json_pre(payload)}</pre></section></main>",
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / html_name_for(path)
    output_path.write_text(content + "\n", encoding="utf-8")
    return output_path


def discover_json_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(path for path in input_path.glob("*.json") if path.is_file())


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render admissions JSON files as static HTML review pages.")
    parser.add_argument("input", nargs="?", default=str(DEFAULT_INPUT), help="JSON file or directory of JSON files.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated HTML files.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    input_path = Path(args.input)
    output_dir = Path(args.out_dir)
    rendered = [render_file(path, output_dir) for path in discover_json_files(input_path)]
    result = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "html_files": [str(path) for path in rendered],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
