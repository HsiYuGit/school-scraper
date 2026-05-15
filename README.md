# 留學申請資料庫 POC

這個專案先驗證「學校條件資料庫」的第一段流程：

1. 整理好德合作學校清單與官方連結。
2. 以學校官方頁面為輸入，擷取各科系/學程的入學條件。
3. 輸出可重跑產生的結構化 JSON，作為後續資料庫 schema 的雛形。

目前範圍以 Gut! 好德網站公開列出的合作學校為準。好德首頁明確列出適用學校時，資料標記為 `confirmed_from_offer_text`；若只在合作夥伴 logo 區出現，標記為 `candidate_from_partner_logo`，後續需人工確認是否屬於本次「學校條件」範圍。

## 目前檔案

- `data/partner_schools.json`：合作學校清單、官方連結、來源註記。

## 後續 POC 目標

- 新增可輸入學校連結的 scraper。
- 產出 `outputs/` 下的學程入學條件 JSON。
