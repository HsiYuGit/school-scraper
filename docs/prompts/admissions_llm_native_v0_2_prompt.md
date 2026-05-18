# Admissions LLM-native v0.2 gap-repair prompt

Use this prompt for a repo-grounded LLM-native repair pass after a crawler-vs-LLM comparison.

```text
You are performing an admissions extraction gap-repair pass for one school.

Inputs:
- The crawler v0.3 JSON for the school.
- The current LLM-native JSON for the school, treated as LLM v0.1.
- The repo admissions LLM-native contract document.
- Any official source URLs already present in the JSON evidence.

Rules:
- Treat admissions JSON as candidate data, not truth.
- Preserve the LLM v0.1 strengths unless contradicted by stronger official evidence.
- Identify crawler-only programs, facts, and requirements.
- Classify each crawler-only item as one of:
  - crawler_false_positive
  - genuine_llm_omission
  - naming_or_grouping_mismatch
  - schema_granularity_difference
  - unverifiable_from_available_evidence
- Ground every decision in source_url, source_text, raw_evidence_sections, and official URLs when available.
- Add only confirmed or explicitly candidate crawler-only omissions to LLM v0.2.
- Do not import crawler false positives.
- If local evidence is insufficient, keep the item out of structured fields or mark it needs_human_review.
- Keep the v0.3 LLM-native program-level shape:
  school, program, requirements, application, evidence, raw_evidence_sections, needs_human_review.
- Add method metadata identifying version llm_native_v0_2, source files, prompt/workflow limitations, and unavailable token/cost truthfully.

Output:
- One improved LLM-native v0.2 JSON file for the school.
- A short note explaining why v0.2 improves over v0.1 and what remains uncertain.
```

This pass was not a paid standalone LLM API extraction run. Token usage, elapsed time, and dollar cost were not measured and must not be estimated.
