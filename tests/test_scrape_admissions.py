import unittest
import urllib.robotparser

from scripts.scrape_admissions import Page, RobotPolicy, page_to_program


class AdmissionExtractionTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
