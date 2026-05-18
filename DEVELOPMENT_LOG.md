# 開發日誌

## 2026-05-15

### 工作規劃

1. 建立好德合作學校清單與官方連結。
2. 建立保守合規的學校入學條件爬蟲：輸入學校連結，輸出學程條件 JSON。
3. 用爬蟲產出概念驗證 JSON，確認產物可由同一支程式重跑產生。

### 已完成

- 建立專案 README，記錄 POC 目標、資料範圍與後續產物。
- 建立 `data/partner_schools.json`，收錄好德首頁明確列出的合作學校與官方連結。
- 將只在好德合作夥伴 logo 區出現的教育機構標成候選，避免把非學校服務夥伴混入學校條件資料。
- 已完成第一個原子提交：`808a225 Add partner school source list`。
- 已完成第二部分爬蟲程式提交：`30aa0be Add admissions scraper POC`、`1ca0031 Improve admissions crawler discovery`、`87c7a6e Filter admissions extraction to program pages`、`5017221 Deduplicate redirected program pages`。
- 已產出 MBS POC JSON：`outputs/munich_business_school_admissions.json`。
- 定義 v0.2 admissions schema，將輸出目標改為可比對學生條件的 structured requirements taxonomy。
- 新增 `docs/admissions_schema_v0_2.md` 與 `tests/fixtures/mbs_v0_2_sample.json`，作為後續爬蟲重構的固定靶心。
- 重構 `scripts/scrape_admissions.py` 的 program 輸出：新增 `SchoolMetadata`、v0.2 `program`/`requirements`/`application`/`evidence`/`raw_evidence_sections` 結構，並加入 `needs_human_review` 以支援跨校 iteration。
- 新增 normalization 規則，先抽 ECTS、先修科目、語言測驗分數、文件、工作經驗、面試/case study、Uni-assist/VPD 與簽證相關提醒。
- 新增 `data/partner_school_crawl_seeds.json`，用 subagent 人工 review 的結果為 12 所學校建立 per-school root URL、seed URLs、review notes 與 crawl cautions。
- 新增 `scripts/crawl_partner_schools.py`，可批次讀取 partner list 與 seed config，輸出每校 v0.2 JSON 與 manifest。
- 修正批次 workflow 的 Windows console UTF-8 輸出，避免 manifest 已寫入後因 CP950 無法列印德文/中文字元而失敗。
- 將 chunked HTTP `IncompleteRead` 視為單頁 skipped reason，避免單一學校頁面傳輸不完整時中斷整批 12 校抓取。
- 批次 manifest 改為每跑完一所學校就更新，避免全量抓取 timeout 時只留下過期 manifest。
- 修正語言分數 normalization 的 false positive：同一句中多個語言考試或 TOEFL institution code 不能互相污染，例如 IELTS 不應吃到 ELS 112 或 TOEFL code 5772。
- 新增語言考試量尺檢查：IELTS、TOEFL iBT、Duolingo、ELS、Cambridge、德文 CEFR 分數需落在合理範圍，避免 IELTS 850 或 TOEFL 7.0 這種跨欄位錯配進入輸出。

### 進行中

- 新增 `scripts/scrape_admissions.py`，作為輸入學校 URL、輸出入學條件 JSON 的 POC 爬蟲。
- 新增離線單元測試，先驗證入學條件區塊抽取邏輯。
- 加入爬蟲合規原則：遵守 `robots.txt`、同網域限制、低頻率請求、不繞過登入/CAPTCHA/付費牆、輸出來源追溯 metadata。
- 強化 crawler robustness：區分 `robots_unavailable` 與 `blocked_by_robots`，讀取 robots 內 sitemap，並支援 `--seed-url` 餵入人工 review 找到的學程列表頁。
- 人工 review MBS master 頁後，發現 sitemap 會混入 events 與 SEO landing pages；已新增 program URL filter，避免非科系頁進入 POC JSON。
- 重跑 MBS 後發現 redirect 造成 MBA 重複、`MBS at School` 服務頁誤入；已加入 redirect 後 URL 去重與服務頁排除。

### 驗證紀錄

- `python -m json.tool data\partner_schools.json`：通過。
- `python -m unittest tests.test_scrape_admissions`：通過。
- `python -m py_compile scripts\scrape_admissions.py tests\test_scrape_admissions.py`：通過。
- `python -m unittest tests.test_scrape_admissions`：v0.2 schema fixture 與 structured normalization 測試通過。
- `$env:PYTHONDONTWRITEBYTECODE='1'; python -m py_compile scripts\scrape_admissions.py tests\test_scrape_admissions.py`：通過；使用 `PYTHONDONTWRITEBYTECODE` 避免 Windows 上既有 `__pycache__` lock 造成誤報。
- reviewed seed config 測試確認 12 所 partner schools 都有對應 seed 設定，並驗證 output slug 產生規則。
- 首次 sandbox 批次抓取因本機連線限制全部回傳 `robots_unavailable`；授權網路後發現部分頁面會出現 `IncompleteRead`，已改成可追溯 skipped reason。
- 全量 12 校、每校 20 頁的批次在本機超過 7 分鐘 timeout；後續不要只依賴一次性全量命令，應以每校或小批次重跑，並靠 incrementally written manifest 判斷完成狀態。
- 抽查 MBS/ESMT 輸出時發現 regex 若跨過下一個考試名稱，會產生看似完整但錯誤的語言分數；之後新增 normalization 規則時要優先做 false-positive 測試，不只測 happy path。
- 語言分數不能只靠鄰近文字判斷，還要檢查各考試自己的分數量尺；這種 domain constraint 比單純加長/縮短 regex window 更可靠。

### v0.2 12 校批次產出

實際產出命令：

```powershell
python scripts\crawl_partner_schools.py --max-pages 8 --delay 0.2 --timeout 12
```

本次 bounded batch 已產出 12 份 `outputs/*_admissions.json` 與 `outputs/partner_school_crawl_manifest.json`。摘要如下：

- TUM Asia：抓 8 頁，抽出 7 個 records，其中 6 個需人工 review。
- Munich Business School：抓 8 頁，抽出 4 個 records，0 個需人工 review。
- International School of Management (ISM)：抓 8 頁，抽出 6 個 records，其中 1 個需人工 review。
- CBS International Business School：抓 8 頁，抽出 2 個 records，0 個需人工 review。
- EBS Universität：抓 8 頁，抽出 5 個 records，其中 2 個需人工 review。
- SRH Universities：抓 5 頁，抽出 0 個 records；需下一輪針對 program finder 或 seed pattern 迭代。
- Kühne Logistics University (KLU)：抓 8 頁，抽出 4 個 records，其中 1 個需人工 review。
- Hochschule Fresenius：抓 8 頁，抽出 3 個 records，0 個需人工 review。
- NIT Northern Institute of Technology Management：抓 6 頁，抽出 2 個 records，0 個需人工 review。
- Hochschule Bremen：抓 4 頁，抽出 0 個 records，另有 1 個 reviewed seed URL 回 404；需下一輪找實際 degree-programme slug 或改用 sitemap/頁面結構。
- ESMT Berlin：抓 8 頁，抽出 4 個 records，0 個需人工 review。
- International Graduate Center, Hochschule Bremen：抓 8 頁，抽出 5 個 records，其中 1 個需人工 review。

人工抽查：

- MBS 與 ESMT 的語言分數曾出現 false positive，已用 test-specific score scale 修正並重跑。
- SRH 與 Hochschule Bremen 目前不是 robots 問題，而是 discovery/extraction 規則尚未抓到可轉成 program record 的頁面；下一輪應針對這兩校開小批次調整，不要全量重跑所有學校。
- 本機 sandbox 對多個官方站的 HTTPS 連線回傳 connection refused；已修正程式避免將環境問題誤判為 robots 封鎖。
- 人工 review `https://www.munich-business-school.de/en/master`：頁面公開列出 Master International Business、Master Innovation & Entrepreneurship、Master International Marketing and Brand Management、Master Sports Management and Media、Master in Finance、Pre-Master；爬蟲輸出包含上述頁面。
- MBS sitemap 另帶出 Master International Business 底下 7 個 specialization 頁；目前保留為獨立 program record，後續 schema 可再決定要當 program 或 specialization。
- 實際產出命令：

```powershell
python scripts\scrape_admissions.py "https://www.munich-business-school.de/en/" --seed-url "https://www.munich-business-school.de/en/master" --seed-url "https://www.munich-business-school.de/en/l/study-finder/master-of-business-administration" --out outputs\munich_business_school_admissions.json --max-pages 40 --delay 1 --timeout 15
```

- `python -m json.tool outputs\munich_business_school_admissions.json`：通過。
- `outputs/munich_business_school_admissions.json` 摘要：`pages_fetched=19`、`pages_skipped=1`、`programs_extracted=16`，skipped reason 為 `duplicate_after_redirect`。

### 待做

- 重構 scraper，使輸出符合 v0.2 schema，並保留 raw evidence sections 作追溯。
- 對好德清單 12 所學校執行實際抓取，產出 `outputs/*.json` 與 summary manifest。
- 檢查實際 JSON 內容是否可讀、可追溯，並記錄命令與人工 review 摘要。
- 若正式化，需進一步確認各學校網站 terms of use、資料庫權利、商業用途與個資風險。

## 2026-05-16

### NIT 人工驗證與雙路徑比較

- 人工驗證指出 NIT 輸出存在多個實質錯誤：官方 program family 應以 `Technology Management` 與 `Business Analytics & AI` 為主，原輸出把 study mode / info page 當成獨立校系，且把 `degree` 類字串誤判成 `GRE`。
- 用 subagent 直接閱讀 NIT 官方頁，產出 LLM 原生版本 `outputs/nit_llm_native_admissions.json`。此版本明確記錄可見的 agent/model metadata、來源 URL、token/cost 不可得狀態，以及 LLM 與爬蟲的差異。
- 爬蟲側新增保守規則：GRE/GMAT keyword 需完整 token 命中；德語 language score 不再接受一般數字；NIT `business-analytics-and-ai` 納入 program path；導覽/marketing 標題不再直接當 program name。
- 重新授權網路後重跑 NIT，爬蟲已能移除 false GRE 並抓到 Business Analytics & AI，但仍無法把中央 admissions 頁的語言分數可靠合併回 program record，也仍需要把 Technology Management 的 single/double degree mode 合併成同一 program family。

### 12 校重新核對發現

- 多個 subagent 重新核對 12 份 JSON output，結論是目前批次產物只能當 candidate extraction，不可直接進 admissions database。
- 高風險共通問題：FAQ/tuition/overview/listing pages 被當 program、degree 被全頁 nav/global text 污染、GRE/GMAT keyword 未區分 required/conditional/not required、language extractor 缺 CEFR/TOEIC/PTE/Cambridge/Duolingo 與多測驗清單支援。
- SRH Universities 與 Hochschule Bremen 仍是 zero-program output；這類情況未來 manifest 應標 broken 或 needs human review，而不是 `programs_needing_human_review=0`。
- 全校 batch 在 360 秒限制下跑到第 11 所附近 timeout；改用 600 秒限制完成 12 校 manifest。後續更適合改成 per-school validation workflow 或可續跑的 selected-school append manifest。

### 驗證紀錄

- `python -m unittest tests.test_scrape_admissions`：通過。
- `python -m json.tool outputs\nit_llm_native_admissions.json`：通過。
- `python scripts\crawl_partner_schools.py --max-pages 8 --delay 0.2 --timeout 15`：授權網路後完成 12 校 manifest；耗時約 412 秒。
- `python scripts\render_admissions_html.py outputs --out-dir outputs\html`：重新產出所有 JSON review HTML，包含 `nit_llm_native_admissions.html`。
- `python scripts\compare_admissions_outputs.py --crawler-json outputs\nit_northern_institute_of_technology_management_admissions.json --llm-json outputs\nit_llm_native_admissions.json --out outputs\html\nit_llm_vs_crawler_comparison.html`：產出 NIT 爬蟲 vs LLM 原生比較頁。
- 使用 in-app browser 開啟本機 `file://` 被安全策略阻擋，改用 localhost server 驗證時又被 `ERR_BLOCKED_BY_CLIENT` 阻擋；已停止本機 job，並用 bounded HTML content check 確認比較頁包含差異摘要、TOEFL 90 與 GRE/GMAT not required 等關鍵內容。

### 重要澄清

- 2026-05-16 的 12 校 batch 只是套用少數保守規則後重新產生 outputs，不是完整的「用 12 校驗證結果反覆迭代到 LLM 閱讀品質」。後續若要達到這個目標，應把 subagent 的 per-school findings 轉成逐校 failing tests 與 extraction fixes，而不是只重跑 batch。

## 2026-05-17

### v0.2 輸出凍結

- 建立 `outputs/v0_2/`，保存目前 12 校 crawler JSON、`partner_school_crawl_manifest.json` 與既有 `nit_llm_native_admissions.json`。
- 新增 `docs/admissions_output_versions.md`，明確區分 v0.2 snapshot 與後續 v0.3 重新產生結果，避免後續 comparison 因覆蓋舊檔而失去基準。

### v0.3 crawler 修正

- 根據 `data/admissions_validation_findings_2026_05_16.json` 修正 program classifier：FAQ、tuition、overview、listing、general application page 不再直接產生 program record。
- degree extraction 改為只看 title、頁面前段與 URL pattern，避免全頁 nav/global text 污染。
- 語言測驗 extraction 補 TOEIC、PTE Academic、Cambridge、CEFR English，並保留 IELTS、TOEFL、Duolingo、ELS、German 的量尺檢查。
- GMAT/GRE/GATE 改為 structured status，區分 `required`、`conditional`、`not_required`、`mentioned_unclear`，避免只因 keyword 出現就當作要求。
- shared requirement pages 可保守合併到 program record 空白欄位，但不直接成為 program。
- batch manifest 新增 `validation_status`，seed 有成功抓到頁面但沒有 program 時標 `broken_or_needs_review`。

驗證：

- `python -m unittest tests.test_scrape_admissions`：通過。
- `python scripts\crawl_partner_schools.py --output-dir outputs\v0_3 --manifest outputs\v0_3\partner_school_crawl_manifest.json --max-pages 8 --delay 0.2 --timeout 15`：授權網路後完成 12 校 v0.3 crawler manifest；本機 sandbox 未授權網路時會回 `robots_unavailable`/connection refused，不作為 crawler 結果。

### LLM-native 對照與 HTML dashboard

- 以 subagents 產出 11 校 LLM-native official-site reading JSON；NIT 使用既有 `nit_llm_native_admissions.json`，複製並補齊 v0.3 top-level contract。
- 新增 `docs/admissions_llm_native_schema_v0_3.md`，固定 LLM-native top-level、method metadata、program record 與 requirements taxonomy，避免不同 subagent 產生不同 JSON shape。
- 新增 dashboard renderer，會把 v0.2 review、v0.3 review、LLM-native review、v0.2 vs v0.3 improvement、v0.3 vs LLM-native comparison 全部接到 `outputs/html/index.html`。
- `python scripts\render_admissions_dashboard.py --outputs-dir outputs --html-dir outputs\html`：產出 dashboard，包含 39 個 review pages、12 個 LLM comparison pages 與 `outputs/html/comparisons/v0_2_vs_v0_3.html`。
- 本機 server/browser 驗證因 Windows process 啟動路線不穩且使用者指示跳過，已停止殘留 PID；改用 bounded HTML content/link checks 確認 index 連到 12 校 v0.2、v0.3、LLM-native 與 comparison pages。

## 2026-05-19

### LLM v0.2 clean-room gap review

- 依照主 agent 不直接補答案的限制，派出 fresh-context worker 針對 TUM Asia 與 Munich Business School 做兩校 gap analysis。
- 新增 `docs/admissions_llm_v0_2_gap_report.md`、`docs/prompts/admissions_llm_native_v0_2_prompt.md`、`docs/admissions_extraction_harness.md`。
- 產出 `outputs/v0_3/llm_native_v0_2/` 兩份 v0.2 LLM-native JSON，用於驗證 LLM 是否能吸收 crawler 已抓到但 v0.1 漏掉的 admissions facts。

### Crawler v0.4 review and rerun

- 逐校檢討 v0.3 crawler output，新增 `docs/admissions_crawler_v0_4_review.md`。
- 擴充 `data/partner_school_crawl_seeds.json`，把 reviewed seeds 從 listing/overview 擴到具體 programme/admissions URL。
- 改善 crawler 精度：允許 ISM/CBS/SRH 等具體 program URL；阻擋 event、summer-school、focus、study-mode、generic-title、cross-host redirect 等 non-program records；`RemoteDisconnected` 現在會被記錄為 skipped URL。
- 產出 `outputs/v0_4/` 12 校 crawler JSON 與 manifest。v0.4 summary: 126 program records、251 language requirement records、199 test requirement records；v0.3 summary: 30 program records、69 language requirement records、75 test requirement records。

### Verification

- `python -m unittest tests.test_scrape_admissions`
- `python -m json.tool outputs\v0_4\partner_school_crawl_manifest.json`
- 逐校 suspect query: generic title、cross-host redirect、event/focus/study-mode URL 均為 0。
