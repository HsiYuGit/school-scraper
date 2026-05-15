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
ECTS_RE = re.compile(
    r"\b(?P<credits>\d{1,3})\s*ECTS(?:\s+credits?)?"
    r"(?:\s+(?:in|of|from)\s+(?P<subject>[A-Za-z][A-Za-z &/\-]{1,60}))?",
    re.IGNORECASE,
)
GRADE_RE = re.compile(r"\b(?:grade|gpa|average)[^.\n]{0,50}?(?:at least|minimum|min\.?|of)?\s*(?P<grade>\d+(?:[.,]\d+)?)", re.IGNORECASE)
LANGUAGE_TEST_PATTERNS = {
    "IELTS": re.compile(r"\bIELTS\b[^\n]{0,80}?(?P<score>\d+(?:[.,]\d+)?)", re.IGNORECASE),
    "TOEFL iBT": re.compile(r"\bTOEFL(?:\s+iBT|\s+IBT)?(?:\s*&\s*Home Edition)?\b[^\n]{0,80}?(?P<score>\d{2,3})", re.IGNORECASE),
    "Duolingo": re.compile(r"\bDuolingo\b[^\n]{0,80}?(?P<score>\d{2,3})", re.IGNORECASE),
    "Cambridge": re.compile(r"\bCambridge\b[^\n]{0,80}?(?P<score>[A-C][12]?|\d{2,3})", re.IGNORECASE),
    "ELS": re.compile(r"\bELS\b[^\n]{0,80}?(?P<score>\d{2,3})", re.IGNORECASE),
    "German": re.compile(r"\b(?:German|Deutsch)\b[^\n]{0,80}?(?P<score>A1|A2|B1|B2|C1|C2|TestDaF|DSH)", re.IGNORECASE),
}
SUBJECT_KEYWORDS = {
    "economics": ("economics", "economy"),
    "accounting": ("accounting",),
    "mathematics": ("mathematics", "maths", "math"),
    "statistics": ("statistics", "statistical"),
    "business studies": ("business studies", "business administration", "management"),
    "finance": ("finance",),
    "business law": ("business law", "law"),
}
DOCUMENT_KEYWORDS = {
    "CV": ("cv", "curriculum vitae", "resume", "résumé"),
    "Motivation letter": ("motivation letter", "letter of motivation", "personal statement"),
    "Transcript": ("transcript", "academic record"),
    "Degree certificate": ("degree certificate", "graduation certificate", "diploma"),
    "Passport": ("passport",),
    "Reference letter": ("reference", "recommendation"),
    "Proof of English proficiency": ("proof of english", "english proficiency"),
    "Photo": ("photo",),
    "Application form": ("application form",),
    "Portfolio": ("portfolio",),
}
TEST_KEYWORDS = {
    "GMAT": ("gmat",),
    "GRE": ("gre",),
    "TM-WISO": ("tm-wiso", "tm wiso"),
    "Aptitude test": ("aptitude test",),
    "Personal interview": ("personal interview", "admission interview", "online interview"),
    "Case study": ("case study",),
}
CONDITIONAL_PATH_KEYWORDS = {
    "Pre-master": ("pre-master", "premaster"),
    "Bridge course": ("bridge course", "preparatory course"),
    "Transfer/lateral entry": ("transfer", "lateral entry"),
    "Non-consecutive admission": ("non-consecutive",),
}
INTERNATIONAL_KEYWORDS = {
    "Uni-assist/VPD": ("uni-assist", "vpd"),
    "Visa-sensitive deadline": ("visa", "non-european", "non-eu"),
    "APS": ("aps",),
    "Country-specific reminder": ("china", "india", "vietnam"),
}
ACADEMIC_PROGRAM_PATHS = (
    "/program/",
    "/programs/",
    "/programme/",
    "/programmes/",
    "/degree-programs/",
    "/degree-programme/",
    "/study-programs/",
    "/study-programmes/",
    "/graduate-studies/",
    "/full-degree-students/",
    "/mba-master/",
    "/master-programs/",
    "/mba-programs/",
    "/study-technology-management",
    "/your-double-degree",
    "/your-single-degree",
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


@dataclasses.dataclass(frozen=True)
class SchoolMetadata:
    name: str | None
    url: str
    country: str | None
    partner_status: str | None
    school_type: str | None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "country": self.country,
            "partner_status": self.partner_status,
            "school_type": self.school_type,
        }


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


def page_to_program(
    page: Page,
    school: SchoolMetadata | None = None,
    retrieved_at: str | None = None,
) -> dict | None:
    if not looks_like_program_page(page.url):
        return None
    full_text = "\n".join(page.text_blocks)
    if not REQUIREMENT_HEADINGS.search(full_text) and not looks_relevant(page.url, page.title):
        return None

    requirements = extract_requirement_sections(page.text_blocks)
    if not requirements:
        return None

    title = clean_program_title(page.title, page.text_blocks)
    retrieved_at = retrieved_at or dt.datetime.now(dt.UTC).isoformat()
    school = school or SchoolMetadata(name=None, url="", country=None, partner_status=None, school_type=None)
    raw_sections = [{"heading": item["heading"], "text": item["text"]} for item in requirements]
    evidence_text = "\n".join(f"{item['heading']} {item['text']}" for item in requirements)
    structured_requirements, evidence = normalize_requirements(evidence_text, page.url, retrieved_at)
    application, application_evidence = normalize_application(full_text, page.url, retrieved_at)
    evidence.update(application_evidence)
    languages = unique_matches(LANGUAGE_RE, full_text)
    needs_human_review = needs_review(structured_requirements, application, raw_sections)

    return {
        "school": school.as_dict(),
        "program": {
            "name": title,
            "degree": first_match(DEGREE_RE, f"{title}\n{full_text}"),
            "level": infer_program_level(title, page.url),
            "url": page.url,
            "campus": infer_campus(full_text),
            "language_of_instruction": languages,
            "parent_program": infer_parent_program(title, page.url),
            "specialization": infer_specialization(title, page.url),
        },
        "requirements": structured_requirements,
        "application": application,
        "evidence": evidence,
        "raw_evidence_sections": raw_sections,
        "needs_human_review": needs_human_review,
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


def normalize_requirements(text: str, source_url: str, retrieved_at: str) -> tuple[dict, dict]:
    requirements = empty_requirements()
    evidence: dict[str, list[dict]] = {}

    ects_matches = list(ECTS_RE.finditer(text))
    if ects_matches:
        first_ects = int(ects_matches[0].group("credits"))
        requirements["academic_background"]["minimum_ects"] = first_ects
        requirements["academic_background"]["notes"].append(f"Found {first_ects} ECTS requirement.")
        add_evidence(evidence, "academic_background", source_url, ects_matches[0].group(0), retrieved_at, "high", "Direct ECTS extraction.")
    if re.search(r"\b(bachelor'?s?|undergraduate|first academic degree|recognized degree)\b", text, re.IGNORECASE):
        requirements["academic_background"]["degree_level"] = "bachelor or recognized first degree"
        add_evidence(evidence, "academic_background", source_url, sentence_around(text, "degree"), retrieved_at, "medium", "Degree-level requirement inferred from admissions text.")
    if re.search(r"\bstate-recognized|recognized university|accredited\b", text, re.IGNORECASE):
        requirements["academic_background"]["recognized_institution"] = "recognized or accredited institution"
    if grade := first_named_match(GRADE_RE, text, "grade"):
        requirements["academic_background"]["minimum_grade"] = grade.replace(",", ".")

    requirements["subject_prerequisites"] = extract_subject_prerequisites(text, source_url, retrieved_at, evidence)
    requirements["language_requirements"] = extract_language_requirements(text, source_url, retrieved_at, evidence)
    requirements["test_requirements"] = extract_keyword_list(text, TEST_KEYWORDS, "test_requirements", source_url, retrieved_at, evidence)
    requirements["work_experience"] = extract_work_experience(text, source_url, retrieved_at, evidence)
    requirements["documents"] = extract_keyword_list(text, DOCUMENT_KEYWORDS, "documents", source_url, retrieved_at, evidence)
    requirements["conditional_paths"] = extract_keyword_list(text, CONDITIONAL_PATH_KEYWORDS, "conditional_paths", source_url, retrieved_at, evidence)
    requirements["international_requirements"] = extract_keyword_list(text, INTERNATIONAL_KEYWORDS, "international_requirements", source_url, retrieved_at, evidence)

    return requirements, evidence


def empty_requirements() -> dict:
    return {
        "academic_background": {
            "degree_level": None,
            "minimum_ects": None,
            "recognized_institution": None,
            "minimum_grade": None,
            "notes": [],
        },
        "subject_prerequisites": [],
        "language_requirements": [],
        "test_requirements": [],
        "work_experience": {
            "minimum_years": None,
            "relevance": None,
            "notes": [],
        },
        "documents": [],
        "conditional_paths": [],
        "international_requirements": [],
    }


def extract_subject_prerequisites(text: str, source_url: str, retrieved_at: str, evidence: dict) -> list[dict]:
    prerequisites: list[dict] = []
    lower = text.lower()
    for subject, keywords in SUBJECT_KEYWORDS.items():
        if not any(keyword in lower for keyword in keywords):
            continue
        ects = None
        for match in ECTS_RE.finditer(text):
            subject_text = (match.group("subject") or "").lower()
            if subject_text and any(keyword in subject_text for keyword in keywords):
                ects = int(match.group("credits"))
                break
        prerequisites.append({"subject": subject, "minimum_ects": ects, "notes": []})
        add_evidence(evidence, "subject_prerequisites", source_url, sentence_around(text, keywords[0]), retrieved_at, "medium", "Subject prerequisite keyword found.")
    return prerequisites


def extract_language_requirements(text: str, source_url: str, retrieved_at: str, evidence: dict) -> list[dict]:
    requirements: list[dict] = []
    seen: set[str] = set()
    validity = "2 years" if re.search(r"\b(two|2)\s+years?\b", text, re.IGNORECASE) else None
    waiver = extract_waivers(text)
    for test_name, pattern in LANGUAGE_TEST_PATTERNS.items():
        for match in pattern.finditer(text):
            score = match.group("score").replace(",", ".")
            key = f"{test_name}:{score}"
            if key in seen:
                continue
            seen.add(key)
            requirements.append(
                {
                    "test": test_name,
                    "minimum_score": score,
                    "component_scores": extract_component_scores(match.group(0)),
                    "validity": validity,
                    "waiver": waiver,
                }
            )
            add_evidence(evidence, "language_requirements", source_url, match.group(0), retrieved_at, "high", "Direct language-test score extraction.")
    return requirements


def extract_work_experience(text: str, source_url: str, retrieved_at: str, evidence: dict) -> dict:
    result = {"minimum_years": None, "relevance": None, "notes": []}
    pattern = re.compile(
        r"\b(?:at least|minimum|min\.?)?\s*(?P<years>\d+|one|two|three|four|five)\s+years?\b[^.\n]{0,100}?(?:work|professional|experience)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        match = re.search(r"\bwork experience\b[^.\n]{0,140}", text, re.IGNORECASE)
    if match:
        years = number_from_word(match.groupdict().get("years"))
        result["minimum_years"] = years
        result["relevance"] = normalize_space(match.group(0))
        add_evidence(evidence, "work_experience", source_url, match.group(0), retrieved_at, "high" if years else "medium", "Work-experience requirement found.")
    return result


def normalize_application(text: str, source_url: str, retrieved_at: str) -> tuple[dict, dict]:
    evidence: dict[str, list[dict]] = {}
    deadlines = unique_matches(DEADLINE_RE, text, limit=8)
    fees = unique_matches(TUITION_RE, text, limit=5)
    intakes = unique_list(re.findall(r"\b(?:spring|summer|fall|winter)\s+(?:semester|intake|term)\b", text, flags=re.IGNORECASE))
    channel = None
    if re.search(r"\bonline application\b", text, re.IGNORECASE):
        channel = "Online application"
        add_evidence(evidence, "application_channel", source_url, sentence_around(text, "online application"), retrieved_at, "medium", "Application channel keyword found.")
    uni_assist = None
    if re.search(r"\buni-assist|VPD\b", text, re.IGNORECASE):
        uni_assist = sentence_around(text, "uni-assist") if "uni-assist" in text.lower() else sentence_around(text, "VPD")
        add_evidence(evidence, "uni_assist_or_vpd", source_url, uni_assist, retrieved_at, "medium", "Uni-assist or VPD keyword found.")
    for deadline in deadlines:
        add_evidence(evidence, "deadlines", source_url, deadline, retrieved_at, "medium", "Deadline keyword extraction.")
    return (
        {
            "deadlines": deadlines,
            "intakes": intakes,
            "application_channel": channel,
            "uni_assist_or_vpd": uni_assist,
            "fees": fees,
        },
        evidence,
    )


def extract_keyword_list(
    text: str,
    keyword_map: dict[str, tuple[str, ...]],
    evidence_key: str,
    source_url: str,
    retrieved_at: str,
    evidence: dict,
) -> list[str]:
    values: list[str] = []
    lower = text.lower()
    for label, keywords in keyword_map.items():
        if not any(keyword in lower for keyword in keywords):
            continue
        values.append(label)
        add_evidence(evidence, evidence_key, source_url, sentence_around(text, keywords[0]), retrieved_at, "medium", f"{label} keyword found.")
    return values


def extract_waivers(text: str) -> list[str]:
    waivers: list[str] = []
    lower = text.lower()
    if "schooling in english" in lower:
        waivers.append("Schooling completed in English")
    if "degree in english" in lower or "academic degree in english" in lower:
        waivers.append("Academic degree completed in English")
    if "daily business communication" in lower:
        waivers.append("English used in daily business communication")
    return waivers


def extract_component_scores(text: str) -> list[str]:
    scores: list[str] = []
    for match in re.finditer(r"\b(?:min\.?|minimum)?\s*(?:of\s*)?(?P<score>\d{1,3})\s+(?P<component>writing|reading|listening|speaking|all other bands)\b", text, re.IGNORECASE):
        scores.append(f"{match.group('score')} {match.group('component').lower()}")
    return scores


def needs_review(requirements: dict, application: dict, raw_sections: list[dict]) -> bool:
    structured_hits = 0
    if requirements["academic_background"]["degree_level"] or requirements["academic_background"]["minimum_ects"]:
        structured_hits += 1
    if requirements["subject_prerequisites"]:
        structured_hits += 1
    if requirements["language_requirements"]:
        structured_hits += 1
    if requirements["documents"]:
        structured_hits += 1
    if requirements["work_experience"]["minimum_years"] is not None:
        structured_hits += 1
    if application["deadlines"] or application["application_channel"]:
        structured_hits += 1
    return not raw_sections or structured_hits < 2


def add_evidence(
    evidence: dict[str, list[dict]],
    key: str,
    source_url: str,
    source_text: str,
    retrieved_at: str,
    confidence: str,
    review_note: str,
) -> None:
    source_text = normalize_space(source_text)
    if not source_text:
        return
    evidence.setdefault(key, [])
    item = {
        "source_url": source_url,
        "source_text": source_text[:500],
        "retrieved_at": retrieved_at,
        "confidence": confidence,
        "review_note": review_note,
    }
    if item not in evidence[key]:
        evidence[key].append(item)


def sentence_around(text: str, keyword: str) -> str:
    if not keyword:
        return ""
    match = re.search(re.escape(keyword), text, re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - 120)
    end = min(len(text), match.end() + 180)
    return normalize_space(text[start:end])


def first_named_match(pattern: re.Pattern[str], text: str, group_name: str) -> str | None:
    match = pattern.search(text)
    return match.group(group_name) if match else None


def number_from_word(value: str | None) -> int | None:
    if not value:
        return None
    mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    value = value.lower()
    if value.isdigit():
        return int(value)
    return mapping.get(value)


def infer_program_level(title: str, url: str) -> str | None:
    haystack = f"{title} {url}".lower()
    if any(value in haystack for value in ("master", "msc", "m.sc", "mba", "ma", "m.a")):
        return "master"
    if any(value in haystack for value in ("bachelor", "bsc", "b.sc", "ba", "b.a")):
        return "bachelor"
    if "phd" in haystack or "doctor" in haystack:
        return "doctoral"
    return None


def infer_campus(text: str) -> str | None:
    match = re.search(r"\b(?:campus|location)\b[^.\n]{0,80}", text, re.IGNORECASE)
    return normalize_space(match.group(0)) if match else None


def infer_parent_program(title: str, url: str) -> str | None:
    if "|" in title:
        return normalize_space(title.split("|", 1)[0])
    path_parts = [part for part in urllib.parse.urlsplit(url).path.split("/") if part]
    if len(path_parts) >= 3 and path_parts[-2] in {"international-business", "master-international-business"}:
        return path_parts[-2].replace("-", " ").title()
    return None


def infer_specialization(title: str, url: str) -> str | None:
    if "|" in title:
        return normalize_space(title.split("|", 1)[1])
    path_parts = [part for part in urllib.parse.urlsplit(url).path.split("/") if part]
    if len(path_parts) >= 4 and "master" in path_parts:
        return path_parts[-1].replace("-", " ").title()
    return None


def unique_list(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = normalize_space(value)
        if clean and clean not in result:
            result.append(clean)
    return result


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
    retrieved_at = dt.datetime.now(dt.UTC).isoformat()
    school = SchoolMetadata(
        name=args.school_name,
        url=root_url,
        country=args.country,
        partner_status=args.partner_status,
        school_type=args.school_type,
    )
    programs = dedupe_programs(
        [
            program
            for page in pages
            if (program := page_to_program(page, school=school, retrieved_at=retrieved_at))
        ]
    )
    return {
        "schema_version": "0.2",
        "school": school.as_dict(),
        "retrieved_at": retrieved_at,
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
            "programs_needing_human_review": sum(1 for program in programs if program["needs_human_review"]),
        },
        "programs": programs,
        "skipped": skipped[:50],
    }


def dedupe_programs(programs: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for program in programs:
        url = program["program"]["url"]
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
    parser.add_argument("--school-name", default=None, help="School name to include in v0.2 output metadata.")
    parser.add_argument("--country", default=None, help="School country to include in v0.2 output metadata.")
    parser.add_argument("--partner-status", default=None, help="Gut-Haode partner status for this school.")
    parser.add_argument("--school-type", default=None, help="School type from the partner-school list.")
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
