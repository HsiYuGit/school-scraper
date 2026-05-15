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
