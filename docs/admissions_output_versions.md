# Admissions output versions

本專案從 2026-05-17 起保留 admissions crawler 的版本化輸出，避免後續重跑覆蓋掉可比較的舊結果。

## v0.2 snapshot

`outputs/v0_2/` 保存 2026-05-16 產出的既有 12 校 crawler JSON、`partner_school_crawl_manifest.json`，以及既有的 `nit_llm_native_admissions.json`。

這批檔案代表修過部分 v0.2 規則後的 candidate extraction。根據 `docs/admissions_validation_iteration_2026_05_16.md` 與 `data/admissions_validation_findings_2026_05_16.json`，它仍有明確限制：

- FAQ、tuition、overview、listing、general application page 仍可能被當作 program record。
- degree 可能被全頁導覽或全站文字污染。
- GRE/GMAT/GATE 尚未完整區分 required、conditional、not required。
- language requirements 缺 TOEIC、PTE、Cambridge、CEFR 與多測驗清單支援。
- zero-program outputs 看起來像成功，但實際應標示為 broken 或需要人工確認。

## v0.3 target

`outputs/v0_3/` 會保存本輪重新產生的 crawler output 與 LLM-native official-site reading。v0.3 不覆蓋 v0.2，並會另外產出 HTML 比較頁：

- v0.2 crawler vs v0.3 crawler improvement。
- v0.3 crawler vs LLM-native official-site reading。
- 每校 review page，全部從 `outputs/html/index.html` 連結。

## v0.3 crawler changes

v0.3 根據 `data/admissions_validation_findings_2026_05_16.json` 收斂 crawler，目標是降低假陽性，而不是把每所學校的所有 program 都硬抓出來：

- FAQ、tuition、overview、listing、general application page 只作 discovery 或 shared evidence，不直接產生 final program record。
- degree 只從 title、頁面前段與 URL pattern 推斷，不再用全頁文字 fallback。
- language extraction 補 TOEIC、PTE Academic、Cambridge、CEFR English，並保留既有 IELTS、TOEFL、Duolingo、ELS、German。
- GMAT、GRE、GATE 改為 structured test requirement，包含 `required`、`conditional`、`not_required`、`mentioned_unclear`。
- central/shared requirement pages 可保守合併到 program record 的空白欄位，但 shared page 本身不再當 program。
- seed 成功抓到頁面但 `programs_extracted=0` 時，manifest 標為 `broken_or_needs_review`。
