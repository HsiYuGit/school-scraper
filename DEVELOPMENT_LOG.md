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
- 本機 sandbox 對多個官方站的 HTTPS 連線回傳 connection refused；已修正程式避免將環境問題誤判為 robots 封鎖。

### 待做

- 對至少一所合作學校執行實際抓取，產出 `outputs/*.json`。
- 檢查實際 JSON 內容是否可讀、可追溯，並記錄命令。
- 若正式化，需進一步確認各學校網站 terms of use、資料庫權利、商業用途與個資風險。
