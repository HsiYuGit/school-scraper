# Admissions extraction harness

This document captures the v0.2 gap-repair workflow so crawler and LLM extraction can become a repeatable harness.

## Exact prompt

The exact reusable prompt is stored at:

`docs/prompts/admissions_llm_native_v0_2_prompt.md`

In this run, the prompt was applied manually by Codex against repo files and available official URLs. No standalone paid LLM/API extraction run was made, so token usage, elapsed time, and dollar cost are unavailable and must not be estimated.

## Workflow

1. Read project docs first:
   - `README.md`
   - `DEVELOPMENT_LOG.md`
   - `docs/admissions_schema_v0_2.md`
   - `docs/admissions_output_versions.md`
   - `docs/admissions_llm_native_schema_v0_3.md`
   - `docs/html_review_tool.md`
2. Pair each crawler v0.3 file in `outputs/v0_3/*.json` with its LLM-native v0.1 file in `outputs/v0_3/llm_native/*.json`.
3. Compare program names, URLs, requirements, application fields, evidence groups, and raw evidence sections.
4. Choose schools only when the crawler has a concrete program/fact/requirement that v0.1 lacks.
5. For each crawler-only item, classify it as:
   - `crawler_false_positive`
   - `genuine_llm_omission`
   - `naming_or_grouping_mismatch`
   - `schema_granularity_difference`
   - `unverifiable_from_available_evidence`
6. Generate v0.2 JSON only for selected schools.
7. Keep v0.1 strengths unless stronger official evidence contradicts them.
8. Do not import crawler false positives.
9. Run JSON validation and a focused static comparison.

## JSON contract notes

LLM v0.2 should keep the broad v0.3 LLM-native shape:

- Top-level:
  - `schema_version`
  - `method`
  - `school`
  - `retrieved_at`
  - `programs`
  - `llm_review_summary`
- Program record:
  - `school`
  - `program`
  - `requirements`
  - `application`
  - `evidence`
  - `raw_evidence_sections`
  - `needs_human_review`
- Requirement taxonomy:
  - `academic_background`
  - `subject_prerequisites`
  - `language_requirements`
  - `test_requirements`
  - `work_experience`
  - `documents`
  - `conditional_paths`
  - `international_requirements`

v0.2 method metadata should add:

- `version: llm_native_v0_2`
- `source_files`
- `prompt_file`
- `workflow`
- `limitations`
- truthful `cost_tracking` values, with unavailable token/cost marked as unavailable rather than estimated

## Acceptance gates

A v0.2 artifact passes only if:

- It is valid JSON.
- It includes method metadata identifying `llm_native_v0_2`.
- It keeps crawler-compatible program records.
- It recovers confirmed crawler-only true facts.
- It does not import identified crawler false positives.
- It preserves stronger v0.1 facts.
- It marks low-confidence or JavaScript-gated source reads with `needs_human_review` or medium/low confidence evidence.
- It lists source files and official source URLs used.
- It treats admissions JSON as candidate data, not truth.

Focused local verification:

```powershell
python -m json.tool outputs\v0_3\llm_native_v0_2\tum_asia_llm_native_v0_2_admissions.json
python -m json.tool outputs\v0_3\llm_native_v0_2\munich_business_school_llm_native_v0_2_admissions.json
python -m json.tool outputs\v0_3\llm_native_v0_2\cbs_international_business_school_llm_native_v0_2_admissions.json
python -m json.tool outputs\v0_3\llm_native_v0_2\ebs_universitat_llm_native_v0_2_admissions.json
```

Suggested static comparison:

```powershell
python - <<'PY'
import json
from pathlib import Path
for path in Path("outputs/v0_3/llm_native_v0_2").glob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["method"]["version"] == "llm_native_v0_2"
    assert data["programs"]
    print(path.name, len(data["programs"]), [p["program"]["name"] for p in data["programs"]])
PY
```

## Reusable crawler/LLM harness shape

The next durable harness can be a script that:

1. Normalizes crawler and LLM program names by URL, title, and parent/specialization.
2. Computes crawler-only and LLM-only items for program records, requirements, application fields, and evidence.
3. Produces a machine-readable gap list with suggested root-cause labels.
4. Requires a human/LLM reviewer to accept, reject, or mark each gap as unverifiable.
5. Writes a v0.2 LLM-native file only after acceptance gates pass.
6. Emits a report table and validation commands with exit status.

This keeps the crawler useful as a recall engine and the LLM useful as a precision/evidence reviewer without pretending either output is final truth.

## Lessons from CBS and EBS extension

- CBS showed that a zero-program crawler v0.3 output can hide real LLM recall gaps once v0.4 finds concrete programme URLs. Use the crawler as a recall surface, but reject template records such as broad programme-family or marketing pages before writing LLM v0.2.
- EBS showed the opposite pattern: crawler v0.4 mostly confirmed or renamed records that LLM v0.1 already handled better. In that case, v0.2 should preserve the stronger LLM extraction and record the crawler differences as naming, grouping, or granularity notes instead of adding duplicate programmes.
- Keep console encoding separate from file encoding. On Windows, UTF-8 names such as `EBS Universität` may display as mojibake in terminal output even when the JSON file itself is valid UTF-8.

## Lessons from the remaining-school clean-room extension

- Future v0.2/v0.3 extraction workers must be clean-room workers: do not let them read `outputs/v0_3/llm_native/`, root LLM-native drafts, or any v0.1 answer before writing their own result. The controller should compare v0.1 vs v0.2 only after the v0.2 artifact exists.
- For clean-room runs, `method.source_files` should list docs plus crawler/official evidence files only. If the output needs to state that v0.1 was not used, keep that as a limitation note rather than a source file.
- v0.4 crawler output is useful as a recall surface, not as truth. SRH, ISM, Hochschule Bremen, CBS, and similar schools can recover real programme URLs after weak v0.3 output, but each recovered record still needs official-page confirmation or `needs_human_review`.
- Shared admissions pages need explicit scope labels such as programme, route, level, or campus. Otherwise language, VPD, document, deadline, interview, and test snippets get over-attached to every programme.
- Repeated application interview text should stay in application-workflow evidence unless the official page frames it as a standalone entrance exam.
- When a worker reports malformed candidate JSON, verify with `python -m json.tool` before recording it as a crawler failure. In the 2026-05-20 integration pass, the Hochschule Bremen v0.4 file parsed cleanly even though one worker treated it as line-level evidence.
- The 2026-05-20 clean-room pass produced the remaining eight LLM v0.2 files and regenerated the local dashboard. Static verification found 117 HTML files, 134 internal links, and 0 missing links.
