# LLM-native admissions JSON contract v0.3

LLM-native outputs are comparison artifacts for testing whether an LLM can read official school websites directly. They must keep the same program-level shape as crawler outputs so comparisons measure content differences, not format drift.

## Top-level fields

Every LLM-native file in `outputs/v0_3/llm_native/` must use these top-level keys:

- `schema_version`: fixed `0.3-llm-native-draft`.
- `method`: run metadata.
- `school`: same school metadata object used by crawler outputs.
- `retrieved_at`: UTC ISO 8601 timestamp.
- `programs`: list of program records.
- `llm_review_summary`: compact summary with `program_count`, `key_findings`, and `known_gaps`.

## Method metadata

`method` must include:

- `type`: fixed `llm_native_official_site_reading`.
- `created_at`: UTC ISO 8601 timestamp.
- `school`: school name.
- `agent`: visible agent metadata, including `agent_id`, `nickname`, `role`, `model`, and `reasoning_effort`; use `not exposed` when unavailable.
- `cost_tracking`: `token_usage`, `estimated_usd_cost`, and `note`; do not estimate unavailable token or dollar cost.
- `source_urls`: official school URLs read for the result.
- `elapsed_time_seconds`: measured value if available, otherwise `not exposed`.
- `format_note`: fixed note that the file matches the repo v0.3 LLM-native contract.

## Program records

Each program record must keep the crawler-compatible keys:

- `school`
- `program`
- `requirements`
- `application`
- `evidence`
- `raw_evidence_sections`
- `needs_human_review`

`requirements` must keep the v0.2 taxonomy:

- `academic_background`
- `subject_prerequisites`
- `language_requirements`
- `test_requirements`
- `work_experience`
- `documents`
- `conditional_paths`
- `international_requirements`

If an official page does not expose a requirement, leave the field `null` or empty and record the gap in `llm_review_summary.known_gaps`; do not invent values.
