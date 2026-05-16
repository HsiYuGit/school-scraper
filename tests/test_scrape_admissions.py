import unittest
import urllib.robotparser
import json
from pathlib import Path

from scripts.crawl_partner_schools import slugify
from scripts.render_admissions_html import render_file
from scripts.scrape_admissions import (
    Page,
    RobotPolicy,
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
        self.assertIn("Personal interview", requirements["test_requirements"])
        self.assertIn("Case study", requirements["test_requirements"])
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
        text = "IELTS 850 TOEFL 7.0 IELTS 7.0 TOEFL 95 Duolingo 170 Duolingo 120"

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
        self.assertNotIn(("Duolingo", "170"), scores)

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


if __name__ == "__main__":
    unittest.main()
