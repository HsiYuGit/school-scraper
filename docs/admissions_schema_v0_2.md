# Admissions JSON schema v0.2

v0.2 的目標是把學校網站上的入學資訊整理成可以和學生資料比對的資料庫雛形，而不是只保存爬蟲文字片段。每個結構化欄位都必須能追溯到官方頁面的 evidence；無法確定時保留欄位但標記低信心或人工待確認。

## Top-level fields

- `schema_version`: 固定為 `0.2`。
- `school`: 學校層級 metadata，包含 `name`, `url`, `country`, `partner_status`, `school_type`。
- `retrieved_at`: 本次抓取時間，UTC ISO 8601。
- `crawler_policy`: robots、同 host、request limit、User-Agent 等合規設定。
- `crawl_summary`: 抓取頁數、略過頁數、抽出的 program 數、需要人工確認的 program 數。
- `programs`: program records。
- `skipped`: 略過 URL 與原因，最多保留前 50 筆。

## Program record

每個 program record 固定包含：

- `school`: 複製 top-level school metadata，方便單筆匯入資料庫。
- `program`: `name`, `degree`, `level`, `url`, `campus`, `language_of_instruction`, `parent_program`, `specialization`。
- `requirements`: 固定 taxonomy；缺資料用 `null` 或空陣列，不省略欄位。
- `application`: deadlines, intakes, application channel, uni-assist/VPD, fees。
- `evidence`: 依欄位保存 evidence item。
- `raw_evidence_sections`: 原本的 requirement heading/text 區塊，只作追溯用。
- `needs_human_review`: 只要核心 requirements 幾乎抽不到或 evidence 信心不足，即為 `true`。

## Requirements taxonomy

- `academic_background`: 學位層級、最低 ECTS、認可學校/學歷、成績/GPA 門檻。
- `subject_prerequisites`: economics, accounting, mathematics, statistics, business studies 等先修科目與 ECTS。
- `language_requirements`: IELTS, TOEFL, Cambridge, Duolingo, German 等最低分數、有效期限、waiver 條件。
- `test_requirements`: GMAT, GRE, TM-WISO, aptitude test, interview, case study。
- `work_experience`: 工作年限、相關性、MBA 或專業學程要求。
- `documents`: CV, motivation letter, transcript, passport, reference, portfolio 等。
- `conditional_paths`: pre-master, bridge course, transfer/lateral entry, non-consecutive admission。
- `international_requirements`: visa-sensitive deadline, Uni-assist/VPD, APS, China/India/Vietnam 等特殊提醒。

## Evidence item

每個 evidence item 至少包含：

- `source_url`
- `source_text`
- `retrieved_at`
- `confidence`: `high`, `medium`, `low`
- `review_note`

## Confidence defaults

- `high`: 正規表達式直接命中明確數值或文件名稱，例如 `180 ECTS`, `IELTS 6.5`, `CV`。
- `medium`: 命中類別但需要人工判斷條件範圍，例如 `business-related degree`。
- `low`: 只知道頁面提到類別，尚不能判斷是否為硬性門檻。
