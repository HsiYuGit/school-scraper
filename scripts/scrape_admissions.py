"""Crawl public school pages and extract admission requirement snippets.

This is a conservative proof-of-concept scraper:
- respects robots.txt through urllib.robotparser;
- crawls only the same host as the input URL;
- uses a low default request rate and a hard max-page limit;
- does not bypass logins, CAPTCHAs, paywalls, or blocked robots rules.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html.parser
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import deque
from typing import Iterable


DEFAULT_USER_AGENT = "study-admissions-poc/0.1 (+https://www.gut-haode.com/ partner-school research)"
PROGRAM_HINTS = (
    "program",
    "programme",
    "programs",
    "programmes",
    "degree",
    "master",
    "msc",
    "mba",
    "bachelor",
    "admission",
    "application",
    "requirements",
)
REQUIREMENT_HEADINGS = re.compile(
    r"\b(admission requirements?|entry requirements?|application requirements?|"
    r"requirements?|eligibility|documents?|language requirements?|"
    r"academic requirements?|application documents?)\b",
    re.IGNORECASE,
)
STOP_HEADINGS = re.compile(
    r"\b(curriculum|modules?|fees?|tuition|career|contact|apply now|"
    r"overview|downloads?|faq|financing|scholarships?)\b",
    re.IGNORECASE,
)
DEGREE_RE = re.compile(r"\b(M\.?Sc\.?|MSc|MBA|M\.?A\.?|MA|B\.?Sc\.?|BSc|B\.?A\.?|BA|LL\.?M\.?|PhD)\b")
LANGUAGE_RE = re.compile(r"\b(English|German|Deutsch)\b", re.IGNORECASE)
DEADLINE_RE = re.compile(r"\b(deadline|application period|apply by|intake)\b[^.\n]{0,140}", re.IGNORECASE)
TUITION_RE = re.compile(r"\b(tuition|fees?)\b[^.\n]{0,140}", re.IGNORECASE)


@dataclasses.dataclass
class Page:
    url: str
    title: str
    text_blocks: list[str]
    links: list[str]


class TextLinkParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.links: list[str] = []
        self.blocks: list[str] = []
        self._tag_stack: list[str] = []
        self._current: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urllib.parse.urljoin(self.base_url, href))
        if tag in {"h1", "h2", "h3", "h4", "p", "li", "td", "th"}:
            self._flush_current()
            self._tag_stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if self._tag_stack and tag == self._tag_stack[-1]:
            self._flush_current()
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        clean = normalize_space(data)
        if not clean:
            return
        if self._in_title:
            self.title_parts.append(clean)
        if self._tag_stack:
            self._current.append(clean)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        if not self._current:
            return
        text = normalize_space(" ".join(self._current))
        if len(text) > 1:
            self.blocks.append(text)
        self._current = []


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    cleaned = parsed._replace(fragment="", query="")
    return urllib.parse.urlunsplit(cleaned)


def same_host(url: str, root: str) -> bool:
    return urllib.parse.urlsplit(url).netloc.lower() == urllib.parse.urlsplit(root).netloc.lower()


def looks_relevant(url: str, text: str = "") -> bool:
    haystack = f"{url} {text}".lower()
    return any(hint in haystack for hint in PROGRAM_HINTS)


def build_robot_parser(root_url: str, user_agent: str) -> urllib.robotparser.RobotFileParser:
    parsed = urllib.parse.urlsplit(root_url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    robot_parser = urllib.robotparser.RobotFileParser()
    robot_parser.set_url(robots_url)
    try:
        robot_parser.read()
    except Exception:
        # If robots.txt cannot be fetched, urllib's parser treats rules as empty.
        # We keep the crawl narrow through same-host and max-page controls.
        pass
    return robot_parser


def fetch_page(url: str, user_agent: str, timeout: float) -> Page:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            raise ValueError(f"Skipping non-HTML content: {content_type}")
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")
    parser = TextLinkParser(url)
    parser.feed(html)
    parser.close()
    title = normalize_space(" ".join(parser.title_parts))
    return Page(url=url, title=title, text_blocks=parser.blocks, links=parser.links)


def crawl(root_url: str, max_pages: int, delay: float, user_agent: str, timeout: float) -> tuple[list[Page], list[dict]]:
    root_url = canonicalize_url(root_url)
    robot_parser = build_robot_parser(root_url, user_agent)
    queue: deque[str] = deque([root_url])
    seen: set[str] = set()
    pages: list[Page] = []
    skipped: list[dict] = []

    while queue and len(pages) < max_pages:
        url = canonicalize_url(queue.popleft())
        if url in seen:
            continue
        seen.add(url)
        if not same_host(url, root_url):
            skipped.append({"url": url, "reason": "different_host"})
            continue
        if not robot_parser.can_fetch(user_agent, url):
            skipped.append({"url": url, "reason": "blocked_by_robots"})
            continue
        if pages:
            time.sleep(delay)
        try:
            page = fetch_page(url, user_agent=user_agent, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
            skipped.append({"url": url, "reason": type(exc).__name__, "detail": str(exc)[:200]})
            continue
        pages.append(page)

        for link in page.links:
            normalized = canonicalize_url(link)
            if normalized in seen or not same_host(normalized, root_url):
                continue
            if looks_relevant(normalized):
                queue.append(normalized)

    return pages, skipped


def page_to_program(page: Page) -> dict | None:
    full_text = "\n".join(page.text_blocks)
    if not REQUIREMENT_HEADINGS.search(full_text) and not looks_relevant(page.url, page.title):
        return None

    requirements = extract_requirement_sections(page.text_blocks)
    if not requirements:
        return None

    title = clean_program_title(page.title, page.text_blocks)
    return {
        "program_name": title,
        "url": page.url,
        "degree": first_match(DEGREE_RE, f"{title}\n{full_text}"),
        "language": unique_matches(LANGUAGE_RE, full_text),
        "application_deadline_evidence": unique_matches(DEADLINE_RE, full_text, limit=3),
        "tuition_evidence": unique_matches(TUITION_RE, full_text, limit=3),
        "admission_requirements": requirements,
    }


def clean_program_title(title: str, blocks: list[str]) -> str:
    candidates = [title] + blocks[:6]
    for candidate in candidates:
        candidate = normalize_space(candidate)
        if 5 <= len(candidate) <= 140 and looks_relevant("", candidate):
            return candidate
    return normalize_space(title or blocks[0] if blocks else "Unknown program")


def extract_requirement_sections(blocks: list[str]) -> list[dict]:
    sections: list[dict] = []
    active_heading: str | None = None
    active_lines: list[str] = []

    for block in blocks:
        if REQUIREMENT_HEADINGS.search(block):
            if active_heading and active_lines:
                sections.append({"heading": active_heading, "text": " ".join(active_lines)})
            active_heading = block[:160]
            active_lines = []
            continue
        if active_heading:
            if STOP_HEADINGS.search(block) and len(active_lines) >= 2:
                sections.append({"heading": active_heading, "text": " ".join(active_lines)})
                active_heading = None
                active_lines = []
                continue
            if len(block) > 2:
                active_lines.append(block)
            if len(" ".join(active_lines)) > 1800:
                sections.append({"heading": active_heading, "text": " ".join(active_lines)[:1800]})
                active_heading = None
                active_lines = []

    if active_heading and active_lines:
        sections.append({"heading": active_heading, "text": " ".join(active_lines)})
    return sections


def first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def unique_matches(pattern: re.Pattern[str], text: str, limit: int = 10) -> list[str]:
    values: list[str] = []
    for match in pattern.finditer(text):
        value = normalize_space(match.group(0))
        if value and value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def build_output(root_url: str, pages: list[Page], skipped: list[dict], args: argparse.Namespace) -> dict:
    programs = [program for page in pages if (program := page_to_program(page))]
    return {
        "schema_version": "0.1",
        "school_url": root_url,
        "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
        "crawler_policy": {
            "respects_robots_txt": True,
            "same_host_only": True,
            "max_pages": args.max_pages,
            "delay_seconds": args.delay,
            "timeout_seconds": args.timeout,
            "user_agent": args.user_agent,
            "no_login_captcha_paywall_bypass": True,
        },
        "crawl_summary": {
            "pages_fetched": len(pages),
            "pages_skipped": len(skipped),
            "programs_extracted": len(programs),
        },
        "programs": programs,
        "skipped": skipped[:50],
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract school program admission requirements to JSON.")
    parser.add_argument("school_url", help="Official school URL or program listing URL to crawl.")
    parser.add_argument("--out", default="-", help="Output JSON path. Use '-' for stdout.")
    parser.add_argument("--max-pages", type=int, default=25, help="Hard crawl limit.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between successful requests.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout per request.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Crawler User-Agent.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    pages, skipped = crawl(
        root_url=args.school_url,
        max_pages=args.max_pages,
        delay=args.delay,
        user_agent=args.user_agent,
        timeout=args.timeout,
    )
    output = build_output(args.school_url, pages, skipped, args)
    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(payload)
    else:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
