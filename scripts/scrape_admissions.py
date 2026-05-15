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
import xml.etree.ElementTree as ET
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
ACADEMIC_PROGRAM_PATHS = (
    "/program/",
    "/programs/",
    "/programme/",
    "/programmes/",
    "/degree-programs/",
    "/study-programs/",
    "/en/bachelor/",
    "/en/master/",
    "/en/mba",
    "/en/dba",
    "/en/l/study-finder/",
)
NON_PROGRAM_PATHS = (
    "/events/",
    "/event-detail/",
    "/faqs",
    "/university/",
    "/services/",
    "/international/",
    "/en/bachelor/mbs-school",
    "/en/l/bachelor-in-english",
    "/en/l/english-taught",
    "/en/l/master-program-in-english",
)


@dataclasses.dataclass
class Page:
    url: str
    title: str
    text_blocks: list[str]
    links: list[str]


@dataclasses.dataclass
class RobotPolicy:
    parser: urllib.robotparser.RobotFileParser
    robots_url: str
    status: str
    error: str | None = None
    sitemaps: list[str] = dataclasses.field(default_factory=list)

    def can_fetch(self, user_agent: str, url: str) -> bool:
        if self.status != "available":
            return False
        return self.parser.can_fetch(user_agent, url)


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


def looks_like_program_page(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    if any(blocked in path for blocked in NON_PROGRAM_PATHS):
        return False
    return any(allowed in path for allowed in ACADEMIC_PROGRAM_PATHS)


def build_robot_policy(root_url: str, user_agent: str, timeout: float) -> RobotPolicy:
    parsed = urllib.parse.urlsplit(root_url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    robot_parser = urllib.robotparser.RobotFileParser()
    try:
        request = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        robot_parser.parse([])
        return RobotPolicy(
            parser=robot_parser,
            robots_url=robots_url,
            status="unavailable",
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
    lines = content.splitlines()
    robot_parser.parse(lines)
    sitemaps = [
        normalize_space(line.split(":", 1)[1])
        for line in lines
        if line.lower().startswith("sitemap:") and ":" in line
    ]
    return RobotPolicy(parser=robot_parser, robots_url=robots_url, status="available", sitemaps=sitemaps)


def fetch_page(url: str, user_agent: str, timeout: float) -> Page:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            raise ValueError(f"Skipping non-HTML content: {content_type}")
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")
        final_url = canonicalize_url(response.geturl())
    parser = TextLinkParser(final_url)
    parser.feed(html)
    parser.close()
    title = normalize_space(" ".join(parser.title_parts))
    return Page(url=final_url, title=title, text_blocks=parser.blocks, links=parser.links)


def crawl(
    root_url: str,
    seed_urls: list[str],
    max_pages: int,
    delay: float,
    user_agent: str,
    timeout: float,
) -> tuple[list[Page], list[dict], RobotPolicy]:
    root_url = canonicalize_url(root_url)
    robot_policy = build_robot_policy(root_url, user_agent, timeout=timeout)
    initial_urls = [root_url] + [canonicalize_url(url) for url in seed_urls]
    queue: deque[str] = deque(initial_urls)
    seen: set[str] = set()
    fetched_final_urls: set[str] = set()
    pages: list[Page] = []
    skipped: list[dict] = []

    for sitemap_url in robot_policy.sitemaps:
        for sitemap_page in discover_sitemap_urls(sitemap_url, root_url, robot_policy, user_agent, timeout):
            if looks_relevant(sitemap_page) and looks_like_program_page(sitemap_page):
                queue.append(canonicalize_url(sitemap_page))

    while queue and len(pages) < max_pages:
        url = canonicalize_url(queue.popleft())
        if url in seen:
            continue
        seen.add(url)
        if not same_host(url, root_url):
            skipped.append({"url": url, "reason": "different_host"})
            continue
        if not robot_policy.can_fetch(user_agent, url):
            reason = "blocked_by_robots" if robot_policy.status == "available" else "robots_unavailable"
            detail = None if robot_policy.status == "available" else robot_policy.error
            skipped.append({"url": url, "reason": reason, "detail": detail})
            continue
        if pages:
            time.sleep(delay)
        try:
            page = fetch_page(url, user_agent=user_agent, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
            skipped.append({"url": url, "reason": type(exc).__name__, "detail": str(exc)[:200]})
            continue
        if page.url in fetched_final_urls:
            skipped.append({"url": url, "reason": "duplicate_after_redirect", "detail": page.url})
            continue
        fetched_final_urls.add(page.url)
        pages.append(page)

        for link in page.links:
            normalized = canonicalize_url(link)
            if normalized in seen or not same_host(normalized, root_url):
                continue
            if looks_relevant(normalized) and looks_like_program_page(normalized):
                queue.append(normalized)

    return pages, skipped, robot_policy


def discover_sitemap_urls(
    sitemap_url: str,
    root_url: str,
    robot_policy: RobotPolicy,
    user_agent: str,
    timeout: float,
) -> list[str]:
    sitemap_url = canonicalize_url(sitemap_url)
    if not same_host(sitemap_url, root_url) or not robot_policy.can_fetch(user_agent, sitemap_url):
        return []
    try:
        request = urllib.request.Request(sitemap_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    urls: list[str] = []
    for loc in root.iter():
        if loc.tag.endswith("loc") and loc.text:
            value = normalize_space(loc.text)
            if same_host(value, root_url):
                urls.append(value)
    return urls


def page_to_program(page: Page) -> dict | None:
    if not looks_like_program_page(page.url):
        return None
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


def build_output(
    root_url: str,
    pages: list[Page],
    skipped: list[dict],
    robot_policy: RobotPolicy,
    args: argparse.Namespace,
) -> dict:
    programs = dedupe_programs([program for page in pages if (program := page_to_program(page))])
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
            "robots_url": robot_policy.robots_url,
            "robots_status": robot_policy.status,
            "robots_error": robot_policy.error,
            "sitemaps_discovered": robot_policy.sitemaps,
        },
        "crawl_summary": {
            "pages_fetched": len(pages),
            "pages_skipped": len(skipped),
            "programs_extracted": len(programs),
        },
        "programs": programs,
        "skipped": skipped[:50],
    }


def dedupe_programs(programs: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for program in programs:
        url = program["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(program)
    return deduped


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract school program admission requirements to JSON.")
    parser.add_argument("school_url", help="Official school URL or program listing URL to crawl.")
    parser.add_argument(
        "--seed-url",
        action="append",
        default=[],
        help="Additional same-host page to crawl first, such as a manually reviewed program listing URL.",
    )
    parser.add_argument("--out", default="-", help="Output JSON path. Use '-' for stdout.")
    parser.add_argument("--max-pages", type=int, default=25, help="Hard crawl limit.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between successful requests.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout per request.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Crawler User-Agent.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    pages, skipped, robot_policy = crawl(
        root_url=args.school_url,
        seed_urls=args.seed_url,
        max_pages=args.max_pages,
        delay=args.delay,
        user_agent=args.user_agent,
        timeout=args.timeout,
    )
    output = build_output(args.school_url, pages, skipped, robot_policy, args)
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
