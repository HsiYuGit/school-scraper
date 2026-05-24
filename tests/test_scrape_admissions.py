import http.client
import shutil
import unittest
import urllib.robotparser
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.crawl_partner_schools import classify_validation_status, slugify
from scripts.compare_admissions_outputs import render_comparison
from scripts.render_admissions_dashboard import main as render_dashboard_main
from scripts.render_admissions_html import render_file
from scripts.source_scraper_common import (
    COVERAGE_STATUSES,
    SourceProgram,
    build_source_output,
    coverage_warning,
    source_slug,
)
from scripts.scrape_admissions import (
    Page,
    RobotPolicy,
    build_output,
    crawl,
    looks_like_program_page,
    normalize_requirements,
    page_to_program,
)


class AdmissionExtractionTest(unittest.TestCase):
    def test_v0_2_fixture_has_fixed_requirement_taxonomy(self):
        fixture_path = Path(__file__).parent / "fixtures" / "mbs_v0_2_sample.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        program = payload["programs"][0]

        self.assertEqual(payload["schema_version"], "0.2")
        self.assertEqual(program["school"]["partner_status"], "confirmed_from_offer_text")
        self.assertIn("requirements", program)
        self.assertIn("raw_evidence_sections", program)
        self.assertIn("academic_background", program["requirements"])
        self.assertIn("subject_prerequisites", program["requirements"])
        self.assertIn("language_requirements", program["requirements"])
        self.assertIn("international_requirements", program["requirements"])

    def test_reviewed_seed_config_covers_all_partner_schools(self):
        root = Path(__file__).parents[1]
        partners = json.loads((root / "data" / "partner_schools.json").read_text(encoding="utf-8"))["schools"]
        seeds = json.loads((root / "data" / "partner_school_crawl_seeds.json").read_text(encoding="utf-8"))["schools"]

        self.assertEqual({item["name"] for item in partners}, {item["name"] for item in seeds})
        self.assertEqual(len(seeds), 12)
        self.assertEqual(slugify("Kühne Logistics University (KLU)"), "kuhne_logistics_university_klu")

    def test_source_scraper_targets_cover_all_partner_schools(self):
        root = Path(__file__).parents[1]
        partners = json.loads((root / "data" / "partner_schools.json").read_text(encoding="utf-8"))["schools"]
        targets_path = root / "data" / "source_scraper_targets.json"
        self.assertTrue(targets_path.exists())
        targets = json.loads(targets_path.read_text(encoding="utf-8"))

        self.assertEqual(targets["schema_version"], "0.1")
        self.assertEqual(targets["generated_from"], "docs/source_scraper_reconnaissance.md")
        self.assertEqual(targets["scope"]["partner_schools_path"], "data/partner_schools.json")
        self.assertTrue(targets["scope"]["no_official_school_fallback"])
        self.assertEqual(
            [
                "degree_level",
                "language_of_instruction",
                "study_mode",
                "application_availability",
            ],
            targets["scope"]["no_hidden_filters"],
        )
        self.assertEqual({"daad", "my_german_university"}, set(targets["sources"]))
        for source_name, source in targets["sources"].items():
            self.assertIn("base_url", source)
            self.assertIn("access_policy", source)
            self.assertEqual(len(source["schools"]), 12, source_name)
            for field in (
                "respect_robots_txt",
                "same_source_only",
                "no_login_captcha_bypass",
                "default_timeout_seconds",
                "default_delay_seconds",
            ):
                self.assertIn(field, source["access_policy"], source_name)
            self.assertEqual({item["name"] for item in partners}, {item["school_name"] for item in source["schools"]}, source_name)
            for school in source["schools"]:
                self.assertIn(school["coverage_status"], {
                    "target_seeded",
                    "target_needs_recon",
                    "source_no_match",
                    "source_partial_match",
                })
                self.assertTrue(school.get("queries") or school.get("listing_urls") or school.get("detail_urls") or school["coverage_status"] == "source_no_match")

    def test_source_common_preserves_contract_and_source_specific(self):
        program = SourceProgram(
            source_record_id="daad-w7513",
            source_listing_url="https://www.daad.de/example-list",
            source_detail_url="https://www.daad.de/example-detail",
            name="Master International Business",
            degree="MA",
            level="master",
            language_of_instruction=["English"],
            requirements={"language_requirements": [{"test": "IELTS", "minimum_score": "6.5"}]},
            application={"deadlines": ["15 July"], "fees": ["EUR 50 application fee"]},
            evidence_key="language_requirements",
            evidence_text="IELTS 6.5",
            source_specific={"daad_subject_group": "Business"},
            needs_human_review=False,
        )
        output = build_source_output(
            source_platform="daad",
            source_label="DAAD",
            school={"name": "Munich Business School", "url": "https://www.munich-business-school.de/en/"},
            programmes=[program],
            coverage_status="complete_within_configured_targets",
            limitation_notes=[],
            future_deepening_candidates=[],
        )

        self.assertEqual(output["schema_version"], "0.4-source")
        self.assertEqual(output["source_platform"], "daad")
        self.assertEqual(output["source_coverage"]["status"], "complete_within_configured_targets")
        self.assertEqual(output["programs"][0]["program"]["name"], "Master International Business")
        self.assertIn("requirements", output["programs"][0])
        self.assertEqual(output["programs"][0]["source_specific"]["daad_subject_group"], "Business")
        self.assertEqual(output["programs"][0]["source_record_id"], "daad-w7513")

    def test_source_output_does_not_reuse_mutable_input_objects(self):
        school = {
            "name": "Munich Business School",
            "url": "https://www.munich-business-school.de/en/",
            "aliases": ["MBS"],
        }
        limitation_notes = ["Only first page inspected"]
        future_deepening_candidates = [{"strategy": "inspect_endpoint", "params": {"limit": 20}}]
        program = SourceProgram(
            source_record_id="daad-w7513",
            source_listing_url="https://www.daad.de/example-list",
            source_detail_url="https://www.daad.de/example-detail",
            name="Master International Business",
            language_of_instruction=["English"],
            requirements={
                "language_requirements": [{"test": "IELTS", "scores": ["6.5"]}],
                "academic_background": {"notes": ["business degree"]},
            },
            application={
                "deadlines": ["15 July"],
                "fees": [{"amount": "EUR 50", "notes": ["application fee"]}],
            },
            source_specific={
                "daad_subject_group": "Business",
                "badges": [{"name": "international", "tags": ["daad"]}],
            },
        )

        output = build_source_output(
            source_platform="daad",
            source_label="DAAD",
            school=school,
            programmes=[program],
            coverage_status="source_partial_match",
            limitation_notes=limitation_notes,
            future_deepening_candidates=future_deepening_candidates,
        )
        record = output["programs"][0]

        output["school"]["aliases"].append("Top-level mutation")
        record["school"]["aliases"].append("Record mutation")
        record["program"]["language_of_instruction"].append("German")
        record["requirements"]["language_requirements"][0]["scores"].append("7.0")
        record["requirements"]["academic_background"]["notes"].append("mutated note")
        record["application"]["deadlines"].append("1 August")
        record["application"]["fees"][0]["notes"].append("mutated fee")
        record["source_specific"]["badges"][0]["tags"].append("mutated tag")
        output["source_coverage"]["limitation_notes"].append("mutated limitation")
        output["source_coverage"]["future_deepening_candidates"][0]["params"]["limit"] = 99

        self.assertEqual(school["aliases"], ["MBS"])
        self.assertEqual(program.language_of_instruction, ["English"])
        self.assertEqual(program.requirements["language_requirements"][0]["scores"], ["6.5"])
        self.assertEqual(program.requirements["academic_background"]["notes"], ["business degree"])
        self.assertEqual(program.application["deadlines"], ["15 July"])
        self.assertEqual(program.application["fees"][0]["notes"], ["application fee"])
        self.assertEqual(program.source_specific["badges"][0]["tags"], ["daad"])
        self.assertEqual(limitation_notes, ["Only first page inspected"])
        self.assertEqual(future_deepening_candidates[0]["params"]["limit"], 20)

    def test_source_output_rejects_unknown_coverage_status(self):
        with self.assertRaises(ValueError):
            build_source_output(
                source_platform="daad",
                source_label="DAAD",
                school={"name": "Example School"},
                programmes=[],
                coverage_status="not_a_real_status",
                limitation_notes=[],
                future_deepening_candidates=[],
            )

    def test_source_coverage_warning_marks_possible_missed_programmes(self):
        self.assertTrue(coverage_warning("bounded_search_limit_reached"))
        self.assertTrue(coverage_warning("source_partial_match"))
        self.assertFalse(coverage_warning("complete_within_configured_targets"))
        self.assertIn("robots_blocked", COVERAGE_STATUSES)
        self.assertEqual(source_slug("My German University"), "my_german_university")

    def test_daad_detail_parser_extracts_contract_programme(self):
        from scripts.scrape_daad_admissions import parse_daad_detail

        html = """
        <html><body>
          <h1>Master International Business</h1>
          <dl>
            <dt>Degree</dt><dd>Master of Arts</dd>
            <dt>Course language</dt><dd>English</dd>
            <dt>Beginning</dt><dd>Winter semester</dd>
            <dt>Application deadline</dt><dd>15 July</dd>
            <dt>Tuition fees</dt><dd>6,000 EUR per semester</dd>
          </dl>
          <section><h2>Admission requirements</h2>
            <p>Bachelor degree with 180 ECTS and proof of English language proficiency IELTS 6.5.</p>
          </section>
        </body></html>
        """

        programme = parse_daad_detail(
            html,
            detail_url="https://www.daad.de/example?w=w7513",
            listing_url="https://www.daad.de/search",
            record_id="w7513",
        )

        self.assertEqual(programme.source_record_id, "w7513")
        self.assertEqual(programme.name, "Master International Business")
        self.assertEqual(programme.degree, "Master of Arts")
        self.assertEqual(programme.level, "master")
        self.assertIn("English", programme.language_of_instruction)
        self.assertIn("15 July", programme.application["deadlines"])
        self.assertIn("6,000 EUR per semester", programme.application["fees"])
        self.assertEqual(programme.source_specific["source_platform"], "daad")

    def test_mgu_detail_parser_preserves_source_specific_fields(self):
        from scripts.scrape_mgu_admissions import parse_mgu_detail

        html = """
        <html><body>
          <h1>Innovation and Entrepreneurship</h1>
          <span>Master of Arts</span>
          <section><h2>Overview</h2>
            <p>Teaching language: English</p>
            <p>Duration: 4 semesters</p>
            <p>Tuition fees: 5,000 EUR per semester</p>
          </section>
          <section><h2>Admission Requirements</h2>
            <p>Applicants need a Bachelor's degree and proof of English, e.g. IELTS 6.5.</p>
          </section>
        </body></html>
        """

        programme = parse_mgu_detail(
            html,
            detail_url="https://www.mygermanuniversity.com/master/innovation-and-entrepreneurship/1692",
            listing_url="https://www.mygermanuniversity.com/universities/Munich-Business-School",
            record_id="1692",
        )

        self.assertEqual(programme.source_record_id, "1692")
        self.assertEqual(programme.name, "Innovation and Entrepreneurship")
        self.assertEqual(programme.level, "master")
        self.assertIn("English", programme.language_of_instruction)
        self.assertIn("duration", programme.source_specific)
        self.assertIn("5,000 EUR per semester", programme.application["fees"])

    def test_daad_detail_parser_ignores_page_chrome_and_section_tabs(self):
        from scripts.scrape_daad_admissions import parse_daad_detail

        html = """
        <html><body>
          <title>Bachelor's in Business Studies (BSc) - International Programmes - DAADREMOVE_JS Skip to main content</title>
          <a>Skip to main content</a>
          <nav><p>Services</p><p>International Programmes 2025/2026</p><p>Home Back Previous Next</p></nav>
          <h1>Bachelor's in Business Studies (BSc)</h1>
          <p>EBS University - Oestrich-Winkel</p>
          <ul>
            <li>Overview</li>
            <li>Course details</li>
            <li>Costs / Funding</li>
            <li>Requirements / Registration</li>
            <li>Services</li>
          </ul>
          <dl>
            <dt>Degree</dt><dd>Bachelor of Science in Business Studies</dd>
            <dt>Course location</dt><dd>Oestrich-Winkel</dd>
            <dt>Teaching language</dt><dd>English</dd>
            <dt>Beginning</dt><dd>Winter and summer semester</dd>
            <dt>Application deadline</dt>
            <dd>There are no application deadlines at EBS; early application is recommended.</dd>
            <dt>Tuition fees per semester in EUR</dt><dd>Yes</dd>
            <dt>Additional information on tuition fees</dt><dd>Total tuition fees: 54,480 EUR</dd>
          </dl>
          <section><h2>Requirements / Registration</h2>
            <p>Admission requirements include a recognised school-leaving certificate and proof of English.</p>
          </section>
        </body></html>
        """

        programme = parse_daad_detail(
            html,
            detail_url="https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/4080/",
            listing_url="https://www2.daad.de/search",
            record_id=None,
        )

        self.assertEqual(programme.source_record_id, "4080")
        self.assertEqual(programme.name, "Bachelor's in Business Studies (BSc)")
        self.assertNotIn("DAADREMOVE_JS", programme.name)
        self.assertNotIn("Skip to main content", programme.name)
        self.assertNotIn("Requirements / Registration", programme.application["deadlines"])
        self.assertNotIn("Requirements / Registration", programme.application["fees"])
        self.assertIn("Total tuition fees: 54,480 EUR", programme.application["fees"])
        requirement_notes = programme.requirements["academic_background"]["notes"]
        self.assertTrue(requirement_notes)
        for note in requirement_notes:
            self.assertNotIn("DAADREMOVE_JS", note)
            self.assertNotIn("Skip to main content", note)
            self.assertNotIn("Requirements / Registration", note)
        self.assertFalse(programme.needs_human_review)

    def test_daad_detail_parser_review_marks_certificate_like_records(self):
        from scripts.scrape_daad_admissions import parse_daad_detail

        html = """
        <html><body>
          <title>Solar Summer Team-up! - International Programmes - DAADREMOVE_JS Skip to main content</title>
          <h1>Solar Summer Team-up!</h1>
          <dl>
            <dt>Degree</dt><dd>Certificate of participation</dd>
            <dt>Teaching language</dt><dd>English</dd>
          </dl>
          <section><h2>Admission requirements</h2>
            <p>Admission is open to advanced students with relevant experience.</p>
          </section>
        </body></html>
        """

        programme = parse_daad_detail(
            html,
            detail_url="https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/10000/",
            listing_url="https://www2.daad.de/search",
            record_id=None,
        )

        self.assertEqual(programme.name, "Solar Summer Team-up!")
        self.assertTrue(programme.needs_human_review)
        self.assertIn("non_degree_or_certificate_like", programme.source_specific["quality_flags"])

    def test_daad_fetch_session_throttles_every_fetch_after_first(self):
        from scripts.scrape_daad_admissions import DaadFetchSession

        with (
            mock.patch("scripts.scrape_daad_admissions.fetch_text", return_value="ok") as fetch_mock,
            mock.patch("scripts.scrape_daad_admissions.time.sleep") as sleep_mock,
        ):
            session = DaadFetchSession(user_agent="test-agent", timeout=1, delay=2.0)
            self.assertEqual(session.fetch("https://www2.daad.de/first"), "ok")
            self.assertEqual(session.fetch("https://www2.daad.de/second"), "ok")
            self.assertEqual(session.fetch("https://www2.daad.de/third"), "ok")

        self.assertEqual(fetch_mock.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [2.0, 2.0])

    def test_daad_scraper_fetch_failure_stays_warning_visible(self):
        from scripts.scrape_daad_admissions import scrape_target

        target = {
            "school_name": "Example School",
            "coverage_status": "target_seeded",
            "listing_urls": [],
            "detail_urls": [
                "https://www2.daad.de/deutschland/studienangebote/international-programmes/en/detail/9999/"
            ],
            "future_deepening_candidates": [],
        }
        partner = {
            "name": "Example School",
            "official_url": "https://example.edu/",
            "country": "Germany",
            "partner_status": "test",
            "school_type": "university",
        }
        args = SimpleNamespace(user_agent="test-agent", timeout=1, delay=0)

        with mock.patch("scripts.scrape_daad_admissions.fetch_text", side_effect=TimeoutError("timed out")):
            output = scrape_target(target, partner, args)

        self.assertEqual(output["source_coverage"]["status"], "source_limited")
        self.assertTrue(output["source_coverage"]["warning"])
        self.assertEqual(output["programs"], [])
        self.assertIn("Could not fetch DAAD detail", output["source_coverage"]["limitation_notes"][0])

    def test_mgu_listing_cloudflare_challenge_stays_warning_visible(self):
        from scripts.scrape_mgu_admissions import scrape_target

        target = {
            "school_name": "Example School",
            "coverage_status": "target_seeded",
            "listing_urls": [
                "https://www.mygermanuniversity.com/universities/Example-School/study-programs"
            ],
            "detail_urls": [],
            "future_deepening_candidates": [],
        }
        partner = {
            "name": "Example School",
            "official_url": "https://example.edu/",
            "country": "Germany",
            "partner_status": "test",
            "school_type": "university",
        }
        args = SimpleNamespace(user_agent="test-agent", timeout=1, delay=0)
        challenge_html = "<html><head><meta name='robots' content='noindex,nofollow'></head><body>Cloudflare managed challenge</body></html>"

        with mock.patch("scripts.scrape_mgu_admissions.fetch_text", return_value=challenge_html):
            output = scrape_target(target, partner, args)

        self.assertEqual(output["source_coverage"]["status"], "js_gated")
        self.assertTrue(output["source_coverage"]["warning"])
        self.assertEqual(output["programs"], [])
        self.assertTrue(output["source_coverage"]["limitation_notes"])
        self.assertIn("Cloudflare/JavaScript-gated", output["source_coverage"]["limitation_notes"][-1])

    def test_mgu_configured_target_fetch_failure_stays_warning_visible(self):
        from scripts.scrape_mgu_admissions import scrape_target

        target = {
            "school_name": "Example School",
            "coverage_status": "target_seeded",
            "listing_urls": [],
            "detail_urls": [
                "https://www.mygermanuniversity.com/master/example-programme/9999"
            ],
            "future_deepening_candidates": [],
        }
        partner = {
            "name": "Example School",
            "official_url": "https://example.edu/",
            "country": "Germany",
            "partner_status": "test",
            "school_type": "university",
        }
        args = SimpleNamespace(user_agent="test-agent", timeout=1, delay=0)

        with mock.patch(
            "scripts.scrape_mgu_admissions.fetch_text",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            output = scrape_target(target, partner, args)

        self.assertEqual(output["source_coverage"]["status"], "source_limited")
        self.assertTrue(output["source_coverage"]["warning"])
        self.assertEqual(output["programs"], [])
        self.assertTrue(output["source_coverage"]["limitation_notes"])
        self.assertIn("Could not fetch MGU detail", output["source_coverage"]["limitation_notes"][-1])

    def test_mgu_source_no_match_without_urls_stays_warning_visible_without_fetch(self):
        from scripts.scrape_mgu_admissions import scrape_target

        target = {
            "school_name": "Example School",
            "coverage_status": "source_no_match",
            "listing_urls": [],
            "detail_urls": [],
            "future_deepening_candidates": [],
        }
        partner = {
            "name": "Example School",
            "official_url": "https://example.edu/",
            "country": "Germany",
            "partner_status": "test",
            "school_type": "university",
        }
        args = SimpleNamespace(user_agent="test-agent", timeout=1, delay=0)

        with mock.patch("scripts.scrape_mgu_admissions.fetch_text") as fetch_mock:
            output = scrape_target(target, partner, args)

        fetch_mock.assert_not_called()
        self.assertEqual(output["source_coverage"]["status"], "source_no_match")
        self.assertTrue(output["source_coverage"]["warning"])
        self.assertEqual(output["programs"], [])
        self.assertTrue(output["source_coverage"]["limitation_notes"])
        self.assertIn("No MGU source target was confirmed", output["source_coverage"]["limitation_notes"][0])

    def test_source_daad_outputs_have_no_chrome_in_core_fields(self):
        root = Path(__file__).parents[1]
        output_dir = root / "outputs" / "source_daad"
        if not output_dir.exists():
            self.skipTest("No DAAD source outputs available.")

        forbidden = (
            "DAADREMOVE_JS",
            "Skip to main content",
            "Requirements / Registration",
            "Course details",
            "Overview",
            "Costs / Funding",
            "Contact",
        )
        offenders = []
        for path in sorted(output_dir.glob("*_admissions.json")):
            if path.name == "source_daad_manifest.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for index, record in enumerate(payload.get("programs", [])):
                core_values = [
                    record.get("program", {}).get("name") or "",
                    *(record.get("application", {}).get("deadlines") or []),
                    *(record.get("application", {}).get("fees") or []),
                    *(record.get("requirements", {}).get("academic_background", {}).get("notes") or []),
                ]
                for value in core_values:
                    if any(token in value for token in forbidden):
                        offenders.append((path.name, index, value))

        self.assertEqual([], offenders[:5])

    def test_extracts_requirement_section_from_program_page(self):
        page = Page(
            url="https://example.edu/programs/msc-management",
            title="MSc Management | Example University",
            links=[],
            text_blocks=[
                "MSc Management",
                "Admission requirements",
                "Bachelor degree with at least 180 ECTS credits.",
                "Proof of English proficiency: TOEFL 85 or IELTS 6.5.",
                "Curriculum",
                "Core modules and electives.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["degree"], "MSc")
        self.assertEqual(program["program"]["level"], "master")
        self.assertIn("English", program["program"]["language_of_instruction"])
        self.assertEqual(program["requirements"]["academic_background"]["minimum_ects"], 180)
        self.assertIn("TOEFL iBT", [item["test"] for item in program["requirements"]["language_requirements"]])
        self.assertEqual(program["raw_evidence_sections"][0]["heading"], "Admission requirements")

    def test_normalizes_cross_school_requirement_taxonomy(self):
        text = (
            "Admission requirements Bachelor degree with at least 180 ECTS credits. "
            "Applicants need 30 ECTS in statistics and business studies up to 60 ECTS. "
            "English Proficiency TOEFL iBT & Home Edition: min. 85 (min. of 22 in writing band, "
            "min. of 20 in all other bands); IELTS 6.5; Duolingo 115. "
            "Test results are valid for two years. The English test can be waived for applicants "
            "having completed their first academic degree in English. "
            "Work experience: at least 2 years of relevant professional experience. "
            "Application documents: CV, letter of motivation, transcript, passport, reference letters. "
            "Qualified applicants will be invited for a personal interview and case study. "
            "Applicants from Vietnam, China and India should allow an extra month for visas. "
            "Uni-assist VPD may be required."
        )

        requirements, evidence = normalize_requirements(
            text,
            "https://example.edu/programs/msc-management",
            "2026-05-15T00:00:00+00:00",
        )

        self.assertEqual(requirements["academic_background"]["minimum_ects"], 180)
        self.assertIn("statistics", [item["subject"] for item in requirements["subject_prerequisites"]])
        self.assertIn("business studies", [item["subject"] for item in requirements["subject_prerequisites"]])
        self.assertEqual(
            {"TOEFL iBT", "IELTS", "Duolingo"},
            {item["test"] for item in requirements["language_requirements"]},
        )
        self.assertEqual(requirements["work_experience"]["minimum_years"], 2)
        self.assertIn("CV", requirements["documents"])
        self.assertIn("Personal interview", {item["test"] for item in requirements["test_requirements"]})
        self.assertIn("Case study", {item["test"] for item in requirements["test_requirements"]})
        self.assertIn("Uni-assist/VPD", requirements["international_requirements"])
        self.assertIn("language_requirements", evidence)

    def test_language_scores_do_not_cross_contaminate_between_tests(self):
        text = (
            "Proof of English proficiency (TOEFL 85, IELTS 6.5, ELS 112). "
            "TOEFL iBT & Home Edition: min. 85 (MBS TOEFL Institution Code: 5772). "
            "IELTS or ELS 112 is also mentioned in a compact list."
        )

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/programs/mba",
            "2026-05-15T00:00:00+00:00",
        )
        scores = {(item["test"], item["minimum_score"]) for item in requirements["language_requirements"]}

        self.assertIn(("TOEFL iBT", "85"), scores)
        self.assertIn(("IELTS", "6.5"), scores)
        self.assertIn(("ELS", "112"), scores)
        self.assertNotIn(("IELTS", "112"), scores)
        self.assertNotIn(("TOEFL iBT", "5772"), scores)

    def test_language_scores_must_match_test_scale(self):
        text = "IELTS 850 TOEFL 7.0 TOEFL 21 IELTS 7.0 TOEFL 95 Duolingo 170 Duolingo 120 German-language course September 2025"

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/programs/mba",
            "2026-05-15T00:00:00+00:00",
        )
        scores = {(item["test"], item["minimum_score"]) for item in requirements["language_requirements"]}

        self.assertIn(("IELTS", "7.0"), scores)
        self.assertIn(("TOEFL iBT", "95"), scores)
        self.assertIn(("Duolingo", "120"), scores)
        self.assertNotIn(("IELTS", "850"), scores)
        self.assertNotIn(("TOEFL iBT", "7.0"), scores)
        self.assertNotIn(("TOEFL iBT", "21"), scores)
        self.assertNotIn(("Duolingo", "170"), scores)
        self.assertNotIn(("German", "1"), scores)

    def test_toefl_component_scores_do_not_become_total_scores(self):
        text = "Proof of English: TOEFL iBT 90, with no less than 21 in each section; IELTS 6.5."

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/programs/msc-management",
            "2026-05-18T00:00:00+00:00",
        )
        scores = {(item["test"], item["minimum_score"]) for item in requirements["language_requirements"]}

        self.assertIn(("TOEFL iBT", "90"), scores)
        self.assertNotIn(("TOEFL iBT", "21"), scores)

    def test_degree_inference_prefers_program_url_over_navigation_text(self):
        page = Page(
            url="https://www.srh-university.de/en/bachelor/aim/applied-artificial-intelligence/",
            title="Bachelor Applied Artificial Intelligence",
            links=[],
            text_blocks=[
                "MBA",
                "Admission requirements",
                "Applicants need a university entrance qualification and proof of English.",
                "TOEFL 80 or IELTS 6.0.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["degree"], "Bachelor")
        self.assertEqual(program["program"]["level"], "bachelor")

    def test_gre_keyword_does_not_match_degree(self):
        text = "Bachelor's degree in engineering with good grades and high English proficiency."

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/programs/mba",
            "2026-05-15T00:00:00+00:00",
        )

        self.assertNotIn("GRE", requirements["test_requirements"])

    def test_gre_gate_negation_is_not_required(self):
        text = "Master applicants need not submit GRE or GATE scores. GMAT may be requested depending on profile."

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/admissions",
            "2026-05-17T00:00:00+00:00",
        )
        statuses = {(item["test"], item["requirement"]) for item in requirements["test_requirements"]}

        self.assertIn(("GRE", "not_required"), statuses)
        self.assertIn(("GATE", "not_required"), statuses)
        self.assertIn(("GMAT", "conditional"), statuses)

    def test_language_extractor_supports_v0_3_formats(self):
        text = (
            "Proof of English: TOEIC 850, PTE Academic 56, Cambridge 173 Grade B, "
            "Duolingo 115, English level B2 according to CEFR."
        )

        requirements, _ = normalize_requirements(
            text,
            "https://example.edu/programs/msc-management",
            "2026-05-17T00:00:00+00:00",
        )
        scores = {(item["test"], item["minimum_score"]) for item in requirements["language_requirements"]}

        self.assertIn(("TOEIC", "850"), scores)
        self.assertIn(("PTE Academic", "56"), scores)
        self.assertIn(("Cambridge", "173"), scores)
        self.assertIn(("Duolingo", "115"), scores)
        self.assertIn(("CEFR English", "B2"), scores)

    def test_nit_marketing_page_title_normalizes_to_program_name(self):
        page = Page(
            url="https://www.nithh.org/business-analytics-and-ai",
            title="Study Business Analytics & AI",
            links=[],
            text_blocks=[
                "Study Program Show submenu for Study Program",
                "Data-Driven Decision Making: Your Future Starts Here",
                "Master in Business Analytics & AI",
                "The requirements to study Business Analytics & AI",
                "A Bachelor's or equivalent degree from a recognized university.",
                "High level of proficiency in English.",
                "At least one year of professional experience.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["name"], "Master in Business Analytics & AI")

    def test_unavailable_robots_policy_does_not_look_like_block(self):
        parser = urllib.robotparser.RobotFileParser()
        parser.parse([])
        policy = RobotPolicy(
            parser=parser,
            robots_url="https://example.edu/robots.txt",
            status="unavailable",
            error="URLError: connection refused",
        )

        self.assertFalse(policy.can_fetch("study-admissions-poc/0.1", "https://example.edu/"))
        self.assertEqual(policy.status, "unavailable")

    def test_crawl_records_remote_disconnected_as_skipped(self):
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(["User-agent: *", "Allow: /"])
        policy = RobotPolicy(parser=parser, robots_url="https://example.edu/robots.txt", status="available")

        with (
            mock.patch("scripts.scrape_admissions.build_robot_policy", return_value=policy),
            mock.patch(
                "scripts.scrape_admissions.fetch_page",
                side_effect=http.client.RemoteDisconnected("Remote end closed connection without response"),
            ),
        ):
            pages, skipped, robot_policy = crawl(
                "https://example.edu/",
                ["https://example.edu/programs/msc-management"],
                max_pages=1,
                delay=0,
                user_agent="test-agent",
                timeout=1,
            )

        self.assertEqual(pages, [])
        self.assertEqual(robot_policy.status, "available")
        self.assertIn("RemoteDisconnected", {item["reason"] for item in skipped})

    def test_crawl_skips_redirects_to_different_host(self):
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(["User-agent: *", "Allow: /"])
        policy = RobotPolicy(parser=parser, robots_url="https://example.edu/robots.txt", status="available")
        redirected = Page(
            url="https://other.example.edu/programs/msc-management",
            title="MSc Management",
            links=[],
            text_blocks=["Admission requirements", "Bachelor degree and TOEFL 90."],
        )

        with (
            mock.patch("scripts.scrape_admissions.build_robot_policy", return_value=policy),
            mock.patch("scripts.scrape_admissions.fetch_page", return_value=redirected),
        ):
            pages, skipped, _ = crawl(
                "https://example.edu/",
                ["https://example.edu/programs/msc-management"],
                max_pages=1,
                delay=0,
                user_agent="test-agent",
                timeout=1,
            )

        self.assertEqual(pages, [])
        self.assertIn("redirected_to_different_host", {item["reason"] for item in skipped})

    def test_program_url_filter_excludes_events_and_marketing_pages(self):
        self.assertTrue(
            looks_like_program_page("https://www.munich-business-school.de/en/master/international-business")
        )
        self.assertTrue(
            looks_like_program_page("https://www.munich-business-school.de/en/mba/mba-full-time")
        )
        self.assertFalse(
            looks_like_program_page("https://www.munich-business-school.de/en/events/event-detail/event/mba-info-session")
        )
        self.assertFalse(
            looks_like_program_page("https://www.munich-business-school.de/en/bachelor/mbs-school")
        )
        self.assertFalse(
            looks_like_program_page("https://www.munich-business-school.de/en/l/english-taught-masters-in-germany")
        )
        self.assertFalse(
            looks_like_program_page("https://tum-asia.edu.sg/admissions/graduate-studies/application/")
        )
        self.assertFalse(
            looks_like_program_page("https://en.ism.de/full-degree-students/master-programs")
        )
        self.assertFalse(looks_like_program_page("https://www.nithh.org/your-single-degree-24m"))
        self.assertFalse(looks_like_program_page("https://www.nithh.org/your-double-degree"))
        self.assertFalse(looks_like_program_page("https://esmt.berlin/programs/summer-school"))
        self.assertFalse(
            looks_like_program_page("https://www.graduatecenter.org/en/mba-master/summer-semester-start.html")
        )
        self.assertFalse(
            looks_like_program_page(
                "https://www.graduatecenter.org/en/mba-master/international-mba-dual-degree/essca-school-of-managment.html"
            )
        )
        self.assertFalse(
            looks_like_program_page(
                "https://www.graduatecenter.org/en/mba-master/international-marketing-focus.html"
            )
        )
        self.assertFalse(
            looks_like_program_page(
                "https://www.graduatecenter.org/en/mba-master/info-event-application-for-full-time-studies-at-the-international-graduate-center.html"
            )
        )

    def test_program_url_filter_allows_concrete_school_patterns(self):
        self.assertTrue(
            looks_like_program_page(
                "https://en.ism.de/full-degree-students/master-programs/master-international-management/overview"
            )
        )
        self.assertFalse(looks_like_program_page("https://en.ism.de/full-degree-students/master-programs"))
        self.assertTrue(
            looks_like_program_page("https://www.cbs.de/en/masters-degree-germany/international-business")
        )
        self.assertTrue(
            looks_like_program_page("https://www.srh-university.de/en/master/supply-chain-management-english/g/")
        )
        self.assertTrue(
            looks_like_program_page(
                "https://www.klu.org/professionals-organizations/mba-leadership-scm"
            )
        )
        self.assertTrue(
            looks_like_program_page(
                "https://www.graduatecenter.org/en/mba-master/mba/mba-in-executive-management.html"
            )
        )
        self.assertFalse(looks_like_program_page("https://www.graduatecenter.org/en/mba-master/mba.html"))

    def test_case_study_in_curriculum_is_not_admissions_test(self):
        text = (
            "Admission requirements Bachelor degree with 180 ECTS. "
            "Curriculum Students work on a KUKA case study during the strategy module."
        )

        requirements, _ = normalize_requirements(
            text,
            "https://www.ebs.edu/en/ebs-business-school/study-programmes/master-in-management",
            "2026-05-18T00:00:00+00:00",
        )

        self.assertNotIn("Case study", {item["test"] for item in requirements["test_requirements"]})

    def test_generic_program_titles_are_not_final_records(self):
        for title in ("Bachelor", "Master Programs", "MBA programs"):
            with self.subTest(title=title):
                page = Page(
                    url="https://example.edu/programs/msc-management",
                    title=title,
                    links=[],
                    text_blocks=[
                        "Admission requirements",
                        "Applicants need a bachelor degree and proof of English.",
                    ],
                )

                self.assertIsNone(page_to_program(page))

    def test_known_program_url_title_wins_over_generic_page_text(self):
        page = Page(
            url="https://www.nithh.org/business-analytics-and-ai",
            title="Business Analytics & AI",
            links=[],
            text_blocks=[
                "• Master/MBA",
                "The requirements to study Business Analytics & AI",
                "A Bachelor's or equivalent degree from a recognized university.",
                "High level of proficiency in English.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["name"], "Master in Business Analytics & AI")
        self.assertEqual(program["program"]["degree"], "Master of Science")

    def test_program_level_does_not_match_ma_inside_words(self):
        page = Page(
            url="https://www.klu.org/programs/study-for-a-bachelor-in-business-administration-in-germany",
            title="Study for a Bachelor in Business Administration in Germany",
            links=[],
            text_blocks=[
                "Admission requirements",
                "A university entrance qualification and proof of English are required.",
                "TOEFL 80 or IELTS 6.0.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["level"], "bachelor")

    def test_pre_bachelor_level_is_not_promoted_to_bachelor(self):
        page = Page(
            url="https://www.munich-business-school.de/en/bachelor/pre-bachelor",
            title="Pre-Bachelor International Business",
            links=[],
            text_blocks=[
                "Admission requirements",
                "The Pre-Bachelor program prepares applicants for undergraduate studies.",
                "Applicants submit proof of English proficiency.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["program"]["level"], "pre-bachelor")

    def test_shared_requirements_merge_respects_level_and_language_scope(self):
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(["User-agent: *", "Allow: /"])
        policy = RobotPolicy(parser=parser, robots_url="https://www.klu.org/robots.txt", status="available")
        args = SimpleNamespace(
            school_name="Kühne Logistics University (KLU)",
            country="Germany",
            partner_status="confirmed_from_offer_text",
            school_type="university",
            max_pages=3,
            delay=0,
            timeout=15,
            user_agent="test-agent",
        )
        pages = [
            Page(
                url="https://www.klu.org/programs/study-for-a-bachelor-in-business-administration-in-germany",
                title="Study for a Bachelor in Business Administration in Germany",
                links=[],
                text_blocks=[
                    "Admission requirements",
                    "A university entrance qualification and proof of English are required.",
                    "TOEFL 80 or IELTS 6.0.",
                ],
            ),
            Page(
                url="https://www.klu.org/programs/faq/faq-graduate",
                title="FAQ Graduate",
                links=[],
                text_blocks=[
                    "Admission requirements",
                    "Applicants for graduate programs need a bachelor degree with 210 ECTS.",
                    "Proof of German C1 and TOEFL 90 may be required.",
                ],
            ),
            Page(
                url="https://www.klu.org/programs/faq/faq-undergraduate",
                title="FAQ Undergraduate",
                links=[],
                text_blocks=[
                    "Admission requirements",
                    "Bachelor applicants may submit TOEFL 80 or IELTS 6.0.",
                ],
            ),
        ]

        output = build_output("https://www.klu.org/", pages, [], policy, args)
        program = output["programs"][0]
        language_tests = {item["test"] for item in program["requirements"]["language_requirements"]}

        self.assertEqual(program["program"]["level"], "bachelor")
        self.assertNotEqual(program["requirements"]["academic_background"]["minimum_ects"], 210)
        self.assertNotIn("German", language_tests)

    def test_renders_admissions_fixture_to_html(self):
        root = Path(__file__).parents[1]
        fixture_path = root / "tests" / "fixtures" / "mbs_v0_2_sample.json"
        output_dir = root / "outputs" / "_test_html_admissions"

        output_path = render_file(fixture_path, output_dir)
        html = output_path.read_text(encoding="utf-8")

        self.assertEqual(output_path.name, "mbs_v0_2_sample.html")
        self.assertIn("Admissions JSON review page", html)
        self.assertIn("Requirements", html)
        self.assertIn("Evidence", html)
        self.assertIn("&amp;", html)

        output_path.unlink()
        output_dir.rmdir()

    def test_renders_manifest_as_index(self):
        root = Path(__file__).parents[1]
        manifest_path = root / "outputs" / "partner_school_crawl_manifest.json"
        output_dir = root / "outputs" / "_test_html_manifest"

        output_path = render_file(manifest_path, output_dir)
        html = output_path.read_text(encoding="utf-8")

        self.assertEqual(output_path.name, "index.html")
        self.assertIn("Partner School Crawl Manifest", html)
        self.assertIn("munich_business_school_admissions.html", html)

        output_path.unlink()
        output_dir.rmdir()

    def test_dashboard_includes_client_comparison_routes(self):
        root = Path(__file__).parents[1]
        output_dir = root / "outputs" / "_test_html_dashboard"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            result = render_dashboard_main(["--outputs-dir", str(root / "outputs"), "--html-dir", str(output_dir)])
            index_path = output_dir / "index.html"
            html = index_path.read_text(encoding="utf-8")

            self.assertEqual(result, 0)
            self.assertIn("v0.3 vs v0.4 crawler improvement", html)
            self.assertIn("LLM v0.1 vs v0.2", html)
            self.assertIn("v0.4 vs LLM v0.2", html)
            self.assertTrue((output_dir / "comparisons" / "v0_3_vs_v0_4.html").exists())
            expected_llm_v0_2 = len(list((root / "outputs" / "v0_3" / "llm_native_v0_2").glob("*.json")))
            self.assertEqual(expected_llm_v0_2, len(list((output_dir / "comparisons" / "llm_v0_1_vs_v0_2").glob("*.html"))))
            self.assertEqual(expected_llm_v0_2, len(list((output_dir / "comparisons" / "v0_4_vs_llm_v0_2").glob("*.html"))))
            self.assertIn("v0_3/llm_native_v0_2/cbs_international_business_school_llm_native_v0_2_admissions.html", html)
            self.assertIn("v0_3/llm_native_v0_2/ebs_universitat_llm_native_v0_2_admissions.html", html)
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)

    def test_zero_program_manifest_status_is_broken_or_review(self):
        status = classify_validation_status(
            {
                "pages_fetched": 4,
                "programs_extracted": 0,
                "programs_needing_human_review": 0,
            }
        )

        self.assertEqual(status, "broken_or_needs_review")

    def test_renders_nit_comparison_html(self):
        crawler = {
            "schema_version": "0.2",
            "retrieved_at": "2026-05-16T00:00:00+00:00",
            "crawl_summary": {"pages_fetched": 1},
            "programs": [
                {
                    "program": {
                        "name": "MBA in Technology Management",
                        "degree": "MBA",
                        "url": "https://example.edu/mba",
                        "language_of_instruction": ["English"],
                    },
                    "requirements": {"language_requirements": [], "test_requirements": []},
                    "needs_human_review": False,
                }
            ],
        }
        llm = {
            "schema_version": "0.2-llm-native-draft",
            "method": {
                "created_at": "2026-05-16T00:00:00+00:00",
                "agent": {"model": "Codex default inherited model", "reasoning_effort": "medium"},
                "cost_tracking": {"token_usage": "not exposed", "estimated_usd_cost": "not available"},
            },
            "programs": [
                {
                    "program": {
                        "name": "Technology Management",
                        "degree": "MBA / M.A.",
                        "url": "https://example.edu/tm",
                        "language_of_instruction": ["English"],
                    },
                    "requirements": {
                        "language_requirements": [{"test": "IELTS Academic", "minimum_score": "6.5"}],
                        "test_requirements": [{"test": "GRE/GMAT", "requirement": "not_required_or_not_stated"}],
                    },
                    "needs_human_review": False,
                }
            ],
        }

        html = render_comparison(
            crawler,
            llm,
            Path("crawler.json"),
            Path("llm.json"),
        )

        self.assertIn("crawler vs LLM-native reading", html)
        self.assertIn("Difference Summary", html)
        self.assertIn("IELTS Academic: 6.5", html)

    def test_llm_native_outputs_keep_v0_3_contract(self):
        root = Path(__file__).parents[1]
        llm_dir = root / "outputs" / "v0_3" / "llm_native"
        if not llm_dir.exists():
            self.skipTest("No v0.3 LLM-native outputs available.")

        top_level_keys = {"schema_version", "method", "school", "retrieved_at", "programs", "llm_review_summary"}
        program_keys = {"school", "program", "requirements", "application", "evidence", "raw_evidence_sections", "needs_human_review"}
        requirement_keys = {
            "academic_background",
            "subject_prerequisites",
            "language_requirements",
            "test_requirements",
            "work_experience",
            "documents",
            "conditional_paths",
            "international_requirements",
        }
        files = sorted(llm_dir.glob("*.json"))
        self.assertTrue(files)
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(payload), top_level_keys, path.name)
            self.assertEqual(payload["schema_version"], "0.3-llm-native-draft")
            self.assertEqual(payload["method"]["type"], "llm_native_official_site_reading")
            self.assertIn("cost_tracking", payload["method"])
            self.assertIn("source_urls", payload["method"])
            self.assertIn("format_note", payload["method"])
            self.assertEqual(payload["llm_review_summary"]["program_count"], len(payload["programs"]))
            for program in payload["programs"]:
                self.assertEqual(set(program), program_keys, path.name)
                self.assertIsInstance(program["evidence"], dict, path.name)
                self.assertIsInstance(program["raw_evidence_sections"], list, path.name)
                self.assertEqual(set(program["requirements"]), requirement_keys, path.name)


if __name__ == "__main__":
    unittest.main()
