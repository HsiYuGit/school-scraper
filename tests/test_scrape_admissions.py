import http.client
import unittest
import urllib.robotparser
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts.crawl_partner_schools import classify_validation_status, slugify
from scripts.compare_admissions_outputs import render_comparison
from scripts.render_admissions_html import render_file
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
