# Admissions validation iteration - 2026-05-16

本輪目標是比較兩條資料產生路徑：

1. 爬蟲程式：延續既有 v0.2 pipeline，針對人工驗證發現的錯誤補上保守規則並重跑。
2. LLM 原生閱讀：讓 LLM 直接閱讀官方網站，產出一份可和爬蟲輸出比較的 NIT draft。

## NIT 結論

人工驗證與 LLM 原生閱讀都顯示，NIT 的官方資訊不應被解讀成 GRE/GMAT 要求。原先爬蟲的 `GRE keyword found` 是 substring false positive，主要來自 `degree` 等一般字串片段。

NIT 較合理的 program family 是：

- `Technology Management`，degree outcome 為 `MBA / M.A.`，Single Degree 與 Double Degree 是 study mode，不應無條件拆成互不相關的 program family。
- `Business Analytics & AI`，degree 為 `Master of Science`。

LLM 原生閱讀輸出已保存於 `outputs/nit_llm_native_admissions.json`。該檔包含本輪可見的 agent/model metadata、來源 URL、以及 token/cost 是否可取得的紀錄。

## 已修的爬蟲規則

- GRE/GMAT 等 keyword extraction 改成完整 token matching，避免 `degree` 觸發 `GRE`。
- 德語 language score 只接受 CEFR/TestDaF/DSH 類型，不再把 `German-language course September 1` 這種日期或月份附近數字當成德語成績。
- NIT `business-analytics-and-ai` 加入 program path allowlist，避免漏抓 Business Analytics & AI。
- NIT marketing/navigation 標題增加清理，避免 `Show submenu` 這類導覽文字成為 program name。

## 仍待修的爬蟲問題

Subagent 重新核對 12 份 output 後，結論是目前批次產物仍只能當 candidate extraction，不可直接當 admissions database。最高優先順序如下：

- Program classifier：FAQ、tuition、overview、listing、general application page 不應產生 program record，只能作 shared evidence 或 discovery。
- Degree extraction：degree 不可從全頁 nav/global text fallback，例如 master pages 被全頁 `PhD` 或 `MBA` 污染。
- Language requirements：需支援 CEFR B2/C1、TOEIC、PTE、Cambridge、Duolingo，以及同一段多測驗清單；若只知道有語言要求但沒有最低分數，應標人工審核。
- Conditional tests：GMAT/GRE 需區分 required、conditional、not required / need not submit，不能只因 keyword 出現就放入 `test_requirements`。
- Zero-program outputs：若 seed pages 成功抓取但 programs=0，manifest 應標 broken 或需要人工審核，不應看起來像成功。
- School-specific shared requirements merge：NIT admissions、IGC central requirements、KLU FAQ 等中央頁面有重要條件，但目前沒有可靠合併回各 program record。

## 驗證紀錄

- `python -m unittest tests.test_scrape_admissions`
- `python -m json.tool outputs\nit_llm_native_admissions.json`
- `python scripts\crawl_partner_schools.py --max-pages 8 --delay 0.2 --timeout 15`
- `python scripts\render_admissions_html.py outputs --out-dir outputs\html`
- `python scripts\compare_admissions_outputs.py --crawler-json outputs\nit_northern_institute_of_technology_management_admissions.json --llm-json outputs\nit_llm_native_admissions.json --out outputs\html\nit_llm_vs_crawler_comparison.html`

全校批次在 360 秒限制下曾於第 11 所學校附近 timeout；改用 600 秒限制完成 12 校 manifest。這再次確認跨校全量 crawl 應視為長任務，或改成 per-school/resumable validation workflow。

## 重要澄清

2026-05-16 的 12 校 batch 不是一次完整的「迭代到 LLM 品質」流程。它只是在修掉部分保守規則後重跑既有 crawler outputs，目的是讓新的 JSON 與 LLM-native NIT draft 可被比較。真正要把 crawler 迭代到接近 LLM 閱讀品質，還需要按學校逐一修 program discovery、central requirements merge、degree extraction、language/test conditional semantics，並重複官方頁驗證。

NIT 的 HTML 比較頁位於 `outputs/html/nit_llm_vs_crawler_comparison.html`。這個頁面明確顯示 crawler 與 LLM-native 的差距：crawler 仍有 3 筆 NIT records 且缺語言分數；LLM-native 版本整理成 2 個 program family，並保留 TOEFL/IELTS/C1 與 GRE/GMAT not required 的語意。
