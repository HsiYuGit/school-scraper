import unittest
import urllib.robotparser
import json
from pathlib import Path

from scripts.scrape_admissions import Page, RobotPolicy, looks_like_program_page, page_to_program


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

    def test_extracts_requirement_section_from_program_page(self):
        page = Page(
            url="https://example.edu/programs/msc-management",
            title="MSc Management | Example University",
            links=[],
            text_blocks=[
                "MSc Management",
                "Admission requirements",
                "Bachelor degree with at least 180 ECTS credits.",
                "Proof of English proficiency: TOEFL or IELTS.",
                "Curriculum",
                "Core modules and electives.",
            ],
        )

        program = page_to_program(page)

        self.assertIsNotNone(program)
        self.assertEqual(program["degree"], "MSc")
        self.assertIn("English", program["language"])
        self.assertEqual(program["admission_requirements"][0]["heading"], "Admission requirements")
        self.assertIn("180 ECTS", program["admission_requirements"][0]["text"])

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


if __name__ == "__main__":
    unittest.main()
