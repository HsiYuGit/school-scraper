# 留學申請資料庫 POC

這個專案先驗證「學校條件資料庫」的第一段流程：

1. 整理好德合作學校清單與官方連結。
2. 以學校官方頁面為輸入，擷取各科系/學程的入學條件。
3. 輸出可重跑產生的結構化 JSON，作為後續資料庫 schema 的雛形。

目前範圍以 Gut! 好德網站公開列出的合作學校為準。好德首頁明確列出適用學校時，資料標記為 `confirmed_from_offer_text`；若只在合作夥伴 logo 區出現，標記為 `candidate_from_partner_logo`，後續需人工確認是否屬於本次「學校條件」範圍。

## 目前檔案

- `data/partner_schools.json`：合作學校清單、官方連結、來源註記。
- `DEVELOPMENT_LOG.md`：開發規劃、已完成工作、驗證紀錄與待辦。
- `scripts/scrape_admissions.py`：輸入學校官方連結或學程列表頁，保守爬取同網域公開頁面，輸出各學程入學條件 JSON。
- `tests/test_scrape_admissions.py`：入學條件區塊抽取的最小單元測試。
- `outputs/munich_business_school_admissions.json`：用同一支 scraper 產出的 Munich Business School POC 入學條件 JSON。

## 爬蟲合規原則

本 POC 預設採取保守做法，避免違反德國/歐洲網站規範或一般網路爬取禮儀：

- 先讀取並遵守目標網域的 `robots.txt`。
- 只抓取輸入網址同一 host 下的公開 HTML 頁面。
- 不繞過登入、CAPTCHA、付費牆、封鎖規則或技術性限制。
- 預設每次成功請求間隔 1 秒，且用 `--max-pages` 設定硬上限。
- 輸出 JSON 保留來源 URL、抓取時間、User-Agent、robots 設定與 skipped reason，方便後續追溯。
- 若本機環境抓不到 `robots.txt`，輸出會標記 `robots_unavailable`，不會把它誤記成學校明確封鎖。
- 若人工 review 發現學程列表頁不在首頁導覽，可用 `--seed-url` 加入同網域起始頁；程式仍會套用 robots 與同網域限制。

若要進入正式產品，建議再做一次法律/合規確認，尤其是各校網站 terms of use、資料庫權利、個資與商業用途限制。

## 使用方式

```powershell
python scripts\scrape_admissions.py "https://www.klu.org/" --seed-url "https://www.klu.org/degree-programs/choose-your-program/master-management/" --out outputs\klu_admissions.json --max-pages 30 --delay 1
```

可用 metadata 參數把好德合作狀態寫進輸出：

```powershell
python scripts\scrape_admissions.py "https://www.munich-business-school.de/en/" --school-name "Munich Business School" --country Germany --partner-status confirmed_from_offer_text --school-type university --seed-url "https://www.munich-business-school.de/en/master" --out outputs\munich_business_school_admissions.json --max-pages 40 --delay 1 --timeout 15
```

批次跑好德清單內 12 所學校時，使用 reviewed seed config：

```powershell
python scripts\crawl_partner_schools.py --max-pages 30 --delay 1 --timeout 15
```

批次腳本會讀取 `data/partner_schools.json` 與 `data/partner_school_crawl_seeds.json`，為每所學校輸出 `outputs/<school_slug>_admissions.json`，並產生 `outputs/partner_school_crawl_manifest.json`。每校 seed config 可獨立調整，因為不同學校的 program list、admissions page、application portal 與 robots 規則都不相同。

輸出 schema 目前升級目標為 v0.2，主體不再只是 admission requirement 原文區塊，而是固定 taxonomy：

- `school`：學校名稱、官方 URL、國家、好德合作狀態。
- `program`：學程名稱、degree、level、URL、campus、授課語言、parent/specialization。
- `requirements`：academic background、subject prerequisites、language、tests、work experience、documents、conditional paths、international requirements。
- `application`：deadline、intake、application channel、Uni-assist/VPD、fees。
- `evidence`：每個結構化欄位的官方頁面來源、原文、信心與人工備註。
- `raw_evidence_sections`：保留爬蟲原始區塊以利追溯，但不作為主要資料模型。

詳細欄位定義見 `docs/admissions_schema_v0_2.md`；固定範例見 `tests/fixtures/mbs_v0_2_sample.json`。

因為各校網站版面差異很大，v0.2 採 evidence-first 策略：能明確抽出的 ECTS、語言分數、文件、工作經驗等會進入 structured fields；抽不出或信心不足時會保留 raw evidence 並標記 `needs_human_review`，避免把某一所學校的模板硬套到其他學校。

## 後續 POC 目標

- 擴充更多合作學校的人工 reviewed seed URL。
- 將 `program` 與 `specialization` 的資料層級拆得更清楚。
- 將 admission requirement 文字再拆成學歷、語言、文件、期限、費用等欄位。
- 為好德清單內 12 所學校建立可重跑 seed config 與批次輸出 manifest。
