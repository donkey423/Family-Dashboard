# 家庭收支記錄：Excel 優先實作流程

本文件供 Luna max 或其他接手模型逐步實作。2026-09-28 依目前程式重新收斂範圍；S4 已先完成不依賴銀行版型的正規化閘門，以下待辦仍不代表銀行解析、入帳或真實驗收已完成。

## 1. 交付目標與授權

唯一主流程：**信用卡 PDF → 本機解鎖 → 逐筆解析與核對 → SQLite → 每月支出 Excel**。先用本機樣本完成，再接既有 Gmail 同步自動處理。

使用者日常只需要開 Excel 看支出；Web 是連線設定、處理例外、首次確認及查看來源的輔助介面。完整 Dashboard 不是交付前置，不再以通用家庭資料平台的功能數量衡量進度。

- 產品名稱保持「家庭收支記錄」，內部識別沿用 `family_finance_hub`。
- 保留 FastAPI、React、SQLite/Alembic、Modular Monolith、Documents/Sources、SecretStore 及撤銷/恢復，不重建專案。
- Excel 是主要使用成果，但仍是 SQLite 的可重建輸出，不是另一份事實來源。
- 文件規格本身不授權執行程式變更；收到「開始實作」後，接手模型依本文件連續執行，不必每一步再問是否繼續。
- 實作授權不等於 Git 寫入、正式資料遷移、新外部服務授權、付費服務、啟用排程或修改防火牆的授權。
- 不從聊天回填身分資料；既有本機 SecretStore 由應用程式在已授權流程內使用，模型不把秘密讀出、貼回或寫進程式。

**第一個可用成果：** S6 結束，必須用一份授權真實帳單完成人工確認、Excel 明細與月支出、重跑不重複、撤銷及恢復。不能為了先做新首頁而延後它。
S7 提供不需呼叫 API 的最小介面；S8 才串接無人處理；S9 做固定 Windows 入口與正式交付。這三步不以新圖表或分類系統為前置。

## 2. 接手時的已知事實

這是本機檢查紀錄，不是重新連線 GitHub 的結果。接手時重新確認，不覆蓋後續修改。

| 項目 | 已觀察狀態 | 不可誤認為 |
| --- | --- | --- |
| Git | 2026-09-29 GitHub `main` 已包含 Groq provider 實作 `eeb6883`；使用者回報 push 後 `Everything up-to-date` 且 local working tree 乾淨 | 後續模型仍應在開始前重查 `git status` / HEAD，不可把歷史的 `001ca5d`/`4f9bfb5` 狀態當現在 |
| S1-S3 | Gmail 自訂查詢隔離、提示上下文/遮罩、共用 PDF 解鎖用例已有程式與合成測試 | 需要全部重寫 |
| S4 | `finance/statements/contracts.py` 與 `finance/statements/normalization.py` 已有純契約、月支出語意、穩定列 hash 及 pending 閘門；契約+正規化聚焦測試 26 passed | 已有任何一家銀行的交易解析器 |
| PDF | 來源讀取、本機解密、文字抽取/預覽，OCR 有介面及 adapter | 已建立 Finance 交易 |
| Gmail | 手動/排程共用同步；每 30 分鐘排程需 opt-in；PDF 收錄、CSV 可入帳 | PDF 可自動入帳 |
| SQLite | FinanceTransaction、來源、工作及撤銷已存在，尚無 Statement/StatementAccount | 可把 PDF 列塞入 CSV 流程就完成 |
| Excel | 已有快照、背景檢查、ownership marker、原子替換及佔用重試 | 已正確區分信用卡退款、繳款與收入 |
| 驗證 | Groq provider 實作後完整 backend 187 passed、frontend production build 成功；Groq/OpenAI dispatch 等以合成資料覆蓋 | 已完成真實 Groq runtime activation、真實 PDF 解鎖或銀行 parser 驗收 |

`ARCHITECTURE_REVIEW_BRIEF.md` 是背景，不是刪除授權；其原始分析基準較早，現在必須以最新 `main` 實作、TASKS/HANDOFF 與本文件為準。開始前先重查 Git，不自行 reset/force-push。

## 3. 保留與延後

| 保留 | 原因 |
| --- | --- |
| SQLite + Alembic | 保存處理狀態、可重跑/撤銷，Excel 遺失能重建 |
| Documents 1:N + SHA-256 | 相同附件不同信件不重複，來源可追溯，不用搬資料重設架構 |
| SecretStore + 受限 PasswordRule DSL | 身分/生日/密碼留本機，不執行 AI 程式、不暴力猜密碼 |
| 純 BankStatementParser + 核對 | 不把繳款算收入，不漏列仍宣稱成功 |
| 原子匯入 + 撤銷/恢復 | 誤匯入可排除，失敗不留半份帳單 |
| Excel ownership/hash/atomic replace/retry | 不覆寫別人的工作簿，Excel 開啟時保留舊檔 |

**本輪不做：** 新家庭 domain、股票 API、多銀行 plugin framework、通用 AI 交易解析、AI 分類、分類/備註 CRUD、完整 Dashboard、全站重排、OCR 擴充、PWA/原生 App、雙向 Excel 同步、保留任意手寫工作表、microservices、Redis/Kafka/Kubernetes/PostgreSQL。

**不重寫同步引擎：** 不把 Gmail History 改為新 90 天掃描/水位系統，不移除 History schema，不建另一套每日排程/退避平台，不把 Excel 改成事件驅動。現有輪詢是檢查，不是每次重建；先沿用。

已有功能不因降為次要就刪掉。最小改動只服務「解析正確、入帳不重複、Excel 正確、例外能處理」。

## 4. 執行方法與檔案地圖

順序：S0 → 核實 S1/S2/S3 → 核實 S3F-A → 完成/驗收 S3F-B（需要真實自動解鎖前）並優先補 S3F-C → S4 → S5 → S6A/S6B/S6C → S7 → S8 → S9。

1. 每包先讀程式/測試、列修改檔案、補失敗案例，再修改；不同時展開後面數包。
2. 每包完成 focused tests，更新 TASKS/HANDOFF，再接下一包。S0/S6/S7/S9 跑完整 backend suite 與 frontend build；schema 另跑隔離 migration tests。
3. 小而清楚的工作由單一模型完成。不可讓多模型同時改 models、migration、main、queries 或同一匯入流程。
4. 失敗先診斷修復，不刪測試/放寬核對取得綠燈。既有失敗記錄重現與影響，不把受影響關卡勾完成。
5. 不順手升級依賴、抽全專案 repository 層或格式化其他檔案。建議新檔若已有同責任實作，就沿用。
6. 缺外部資料先做真正不依賴它的授權工作；不能繞過樣本關卡猜格式、建推測 schema，或轉做凍結功能。
7. 每包交接：修改、實際命令/結果、真實/合成區別、未完成、下一步。不把規格寫成已完成事實。

以下 backend 落點除 tests/migration 外，前綴均為 `backend/src/family_finance_hub/`。

| 現有落點 | 本輪責任 |
| --- | --- |
| `application/pdf_processing.py` | 共用來源/profile/規則/解鎖/文字抽取，不另寫一套 |
| `finance/statements/contracts.py` | 已有純解析契約、金額/類型/核對及自然月語意 |
| `models.py`、backend/alembic/versions/ | 最小持久化與既有資料保留 |
| `application/use_cases.py` | 參考 CSV 原子匯入，不把信用卡當 CSV |
| `finance/queries.py` | 有效文件篩選、舊查詢金額語意 |
| `exports/ports.py`、`service.py`、`xlsx.py` | 最小擴充快照與正確 Excel 投影 |
| `integrations/gmail/client.py`、`sync.py`、`scheduler.py` | 沿用查詢/分頁/鎖/排程，接 PDF-only 及後續處理 |
| `main.py` | 薄 API 與依賴組裝，不塞銀行 regex/核對規則 |
| `frontend/src/App.tsx`、既有設定/詳情元件 | 最小帳戶設定、待處理、核對確認，不全面重寫 |
| backend/tests/ | 沿用 tmp SQLite、FakeGmail、MemorySecretStore、合成 PDF/Excel |

## 5. 共用資料規則

### 5.1 支出與時間

- 月支出以 transaction_date 的自然月計；帳單期起迄、入帳日另外保存。不拿郵件日/結帳日默默補消費日。
- 信用卡資料不含現金、轉帳或尚未出帳消費；收到一份帳單不等於本月全部支出到齊。
- purchase/fee/interest 為負數，refund/payment 為正數。繳款是清償，不是收入或第二次支出；退款不是收入。
- 分列消費、退款、淨消費、費用、利息。淨消費 = 消費 - 退款；含費用支出 = 淨消費 + 費用 + 利息；payment 只供核對。
- 按列帳幣別分組，不混幣別、不自造匯率。原幣欄位只有樣本需要才加，不與列帳額重複加總。
- 使用 Decimal；持久化沿用 Numeric(18,2) 範圍，超精度不靜默四捨五入。真實樣本需要其他精度，先記契約問題再決定，不悄悄改舊 CSV 語意。
- 分期只計本期列帳額，不同時計原始購買總額。unknown 或缺日期不可當普通消費入帳。
- 零消費帳單、未收到帳單、解析失敗是不同狀態。

### 5.2 安全與追溯

- 原始 PDF/抽取全文/秘密不進 Git、log、聊天或外部 AI。可存產品需要的結構化交易，不把全文塞入 raw_json。
- AI 只限既有 opt-in 的遮罩密碼說明分析；不加交易 AI fallback，不用模型產生金額補平核對。
- 寄件者只作 PDF 來源線索，不是銀行身分/帳戶所有權證明；個人解鎖不要求選 profile，成功解鎖也不是可入帳證明。
- 同日同店同金額可以是兩筆真交易，保留列序號/頁碼，不用描述+日期+金額去重。
- 撤銷沿用軟撤銷，保留來源；一般同步不得自動恢復已撤銷文件。

## 6. S0：確認目前基線

**輸入：** checkout、AGENTS/README/HANDOFF/TASKS、manifest、tests/config。
**輸出：** 可重現基線，不改業務行為。

1. 確認 repo 為 family-finance-hub，不是假設任務 cwd；記 branch/HEAD/status 與未追蹤檔。
2. 保留所有改動，唯讀比較本機 Git 參照；不自行 fetch/merge/reset/commit/push。
3. 檢查 fixtures 使用 tmp DB/storage 與 fake provider，不繼承正式資料位址；不開服務 UI 的 DB 當測試輸入。
4. 執行第 17 節完整基線、build、Alembic heads；不對正式 DB upgrade。

**完成：** 記錄實際命令、結果、既有失敗。TASKS 的 S0 勾選是前輪結果，接手仍確認新基線。

## 7. S1-S3：核實已有成果，不重新設計

| 步驟 | 查核行為 | 檔案/測試 |
| --- | --- | --- |
| S1 Gmail 範圍 | 自訂 q 走 message search；不借 history 抓範圍外郵件；自訂 A/B 不改預設 cursor；分頁改 q 有衝突；失敗頁不跳過 | `integrations/gmail/sync.py`、`test_gmail_sync.py` |
| S2 密碼上下文 | 關鍵行前後語意上下文；HTML row/cell/inline 空白及重疊行保序；先遮罩再截斷；不送全文/未確認安全資料 | `security/password_rules/extractor.py`、`test_password_rules.py`、`test_pdf_api.py` |
| S3 共用解鎖 | PdfPreviewUseCase 預設使用個人解鎖資料，不要求銀行/成員；舊 sender 精確匹配及手動 profile 保留相容；verified rule 安全重用；AI 關閉零呼叫 | `application/pdf_processing.py`、`test_pdf_processing.py`、`test_pdf_processor.py`、`test_pdf_api.py` |

保留 /content 原始 bytes、/preview no-store 與錯誤契約。自動化直接呼叫 application，不用 HTTP 呼叫自己。sender_pattern 不變任意 regex，密碼 DSL 不新增指令或暴力候選。

**完成：** 現有測試通過；發現缺口只補缺口，不把已完成步驟拆成新平台里程碑。

## 7.1 S3F：免費 AI 密碼規則 Provider

**目的：** 將目前 OpenAI-only 的密碼提示解析改成免費 API 優先；完整規格見 [FREE_AI_PASSWORD_RULE_PLAN.md](FREE_AI_PASSWORD_RULE_PLAN.md)。

**目前狀態（2026-09-29）：** provider-neutral 程式、Groq adapter、設定 API/UI 與安全邊界已由 `eeb6883` 完成並合併 `main`；完整 backend 187 passed、frontend build 成功。最後一次 runtime smoke check 仍使用已保存的 OpenAI profile，尚未完成 Groq runtime activation，因此真實 Groq request 與真實 PDF 解鎖仍未驗收。這次實際 Gmail PDF 已完成文件收錄及 SHA-256 重複收錄驗證，但 AI 預覽因現存 OpenAI 額度不足停止，沒有建立交易；不得把這次結果視為 parser 或 Excel 入帳完成。

- 第一階段接 Groq Free，預設 `openai/gpt-oss-20b`；實作前重新查 Groq 官方 Free Plan、model list 與 Structured Outputs 支援。
- 沿用 `PasswordRuleInterpreter`、`PasswordRuleService` verified cache、`SecretStore` 與 `PasswordComposer`；只把 provider config、adapter、UI 改成 provider-neutral，不新增 migration 或通用 AI 平台。
- Groq adapter 使用 Responses JSON Schema；因 Groq 不支援 `store`，不可送出該欄位。真實身分證、生日、組合密碼及帳單全文不得出站。
- Groq 401/403/429/timeout/5xx 或 schema failure 均 fail closed，留 pending/manual；禁止自動 fallback 到可能付費的 OpenAI。OpenAI 只有使用者明確選擇時使用。
- 驗收包含 synthetic prompt、payload 脫敏、provider dispatch、verified cache、不自動 fallback 及前端 production build。

**S3F 剩餘工作：**

- **S3F-B Runtime activation**：本機明確啟用 Groq，保存後確認 Active Provider/Model，先以 synthetic prompt 呼叫真實 Groq；第二次相同提示必須命中 cache，不再 remote call。
- **S3F-C Safe switch hardening**：新增 `/api/security/ai-provider/test` 或等價 preflight；新 provider 設定驗證失敗時，舊 active credential 必須完整保留。
- 將 provider 失敗轉成穩定 reason code；429/網路/schema/model 問題只留 pending/manual，不可偷偷改呼叫 OpenAI。
- Recommended/Default/Active Provider 必須分開：Groq 是建議與新設定預設，runtime 只認已保存 Active Provider。
- Groq Responses API 目前官方仍標示 beta；`openai/gpt-oss-20b` 支援 strict Structured Outputs，但實際相容性以 synthetic smoke test 為準。

S3F 是小型前置改善，不得擴張成 multi-provider 平台。S4 仍是產品主 blocker；若真實 S4 樣本需要自動密碼解鎖，先完成 S3F-B，再進行該樣本驗收。

## 8. S4：第一家銀行真實解析器

**前置：** 使用者指定一家銀行與至少兩期 PDF 的私有路徑，或明確授權的既有來源。密碼由既有本機設定供應，不要求貼入文件。
**已有：** `finance/statements/contracts.py`、`finance/statements/normalization.py`。後者只負責把已驗證的 Statement contract 轉成穩定列，未知列、缺日期、未核對或對帳不符會回 `pending`；不讀 PDF/Gmail/DB/秘密，也不取代銀行 parser。
**建議新增：** `finance/statements/<bank_id>.py`、`backend/tests/test_statement_parser.py`。

### S4A 樣本與核對規則

1. 樣本 A 開發，B 保留作未參與調整的驗證。原件留私有位置；提交 fixtures 重新製作合成內容，不是只刪姓名的全文。
2. 逐頁確認抽取完整、表頭/結尾、跨頁列及摘要；不是抽到字就成功。缺文字層才評估現有 OCR，不先擴建。
3. 列出該銀行欄位、跨年日期、借貸符號、分期呈現及核對公式。應繳/最低應繳不是消費總額；依實際前期餘額、借項、貸項、期末餘額核對。
4. 核對所需摘要可最小擴充既有 contract；差額精確呈現，不造平衡列。資訊不足回 not_checked，不假 matched。

### S4B 純解析器

1. 接收共用流程內容，沿用 `BankStatementParser.parse(extracted_text, page_count=...)` 與 `StatementParseResult`，不讀 DB/Gmail/SecretStore、不 commit。頁碼等現有欄位只能從可追溯內容取得，不依猜測填寫。
2. 先驗銀行/版型，按實際欄位解析；unknown、缺日期、缺核對欄位或跨頁截斷回待處理，不用寬鬆 regex 在任意文字找金額。
3. 沿用契約欄名 `bank_id`、`format_version`、`period_start`、`period_end`、`account_hint`；列使用 `page_number`、`line_index`、`transaction_date`、`posting_date`、`description`、`transaction_kind`、`amount`、`currency`。不要另建 page/date/kind 等重複欄名；解析器實作 ID 在持久化時另外記錄即可。
4. 不把末四碼當唯一帳戶，不存完整卡號。只做一個 parser，不建 registry/跨銀行猜測框架。

**必測：** 跨月/年、退款/繳款/費用/利息、分期、外幣、重複表頭、跨頁、合法相同列、零消費、漏列/未知列/未知版型/不平衡。
**完成：** A/B 均逐列核對日期、類型、金額、幣別、列數與核對式；只記去識別化樣本代號/結果。若 B 被拿來修規則，不再稱盲測，需另一份獨立驗證或明記限制。缺第二期可完成程式但 S4 仍待驗收，不開無人入帳。

## 9. S5：最小模型與隔離 migration

**前置：** S4 欄位/核對契約經真實樣本確認，不因等樣本先設計更多資料表。
**修改：** `models.py`、下一個 Alembic revision、`test_migrations.py`、必要 statement 持久化測試。

### S5A 必要資料

| 資料 | 最小內容/限制 |
| --- | --- |
| StatementAccount | 隨機 ID、由已驗證 parser 確認的 bank ID、別名、必要遮罩線索。代表帳單帳戶，不是一張實體卡，也不等同解鎖資料；不要求使用者建立銀行/成員解鎖 profile |
| Statement | 唯一 document_id、可空 account/period、parser ID/version、結構化草稿/核對摘要、review_version、狀態/reason_code、處理持有識別/時間 |
| FinanceTransaction 擴充 | nullable statement_id、posting_date、transaction_kind、statement_line_index；CSV 保持原樣，不回填臆測帳戶 |

狀態只有 pending（缺資料/不支援/衝突）、processing、ready（核對通過待確認）、imported、failed（可重試技術失敗）。撤銷仍看 Document，細節用 reason_code，不增加大量狀態。

### S5B 原子性與去重

1. (statement_id, statement_line_index) 唯一。既有 row_hash 非空且全域唯一，PDF 使用帶命名空間的穩定 statement_id + line_index 雜湊，不套 CSV 內容去重。
2. 同帳戶/期起迄最多一份 imported，以 SQLite 可驗證的條件唯一約束或等效原子防護實作，不只先查後寫；pending 草稿不受此 imported 約束排除。
3. 同期不同 bytes 列衝突，不自動替換/合併。已撤銷 imported 仍佔該期，防止新版繞過撤銷後雙重恢復；更正版替換明列不支援，不暗加版本機制。
4. processing 由條件更新取得唯一持有識別；寫回檢查識別/review version/文件狀態，失效持有者不得覆寫新結果。
5. 單一 backend 啟動可回收前次中斷 processing；不可每次 HTTP 請求清掉其他執行中的工作。不建 Redis/分散式 lease。
6. imported 完整不變，草稿不進 Finance。結構化 JSON 要 version/驗證，不放抽取全文/秘密。

**必測：** 空 DB 升級、當前 head 舊 CSV/source/revoked/export 設定保留、唯一/併發限制、非空 row_hash、中斷恢復、有新資料時拒絕破壞性 downgrade。
**完成：** 隔離 migration 全通過，revision 依當時 head，不寫死編號、不碰正式 DB。

## 10. S6：先交付正確的 Excel

**建議新增：** `application/statement_import.py`、`backend/tests/test_statement_import.py`；沿用 queries/lifecycle/exports。

### S6A 分析、帳戶與待確認 API

1. 沿用 S3 共用來源/解鎖及 S4 parser；短 transaction 取得處理權，transaction 外讀來源/解鎖/解析，再短 transaction 存草稿。新增的寫入 transaction 不包 HTTP/AI/PDF/OCR。保留來源讀取的內容 SHA-256 一致性檢查，不能把內容已變的 bytes 當成原 Document 入帳。
2. Document 已存在仍可重試 pending/failed，不需再上傳；ready 重解析增加 review_version，使舊確認失效。imported 不覆寫，已撤銷不處理。
3. 最小帳戶 API 提供列表/建立/修正綁定，不要求改 DB。以已驗證 parser 的銀行身分和遮罩線索核對，不以解鎖 profile 或末四碼單獨推定。
4. 有 imported 資料的 account 不得任意改 bank/身份綁定重寫歷史；別名可改，衝突綁定回明確錯誤，不做帳戶合併平台。

建議 route，新增前先確認沒有同責任入口：

| API | 責任 |
| --- | --- |
| `POST /api/documents/{id}/statement-analysis` | 分析/重試，回 statement id/狀態/原因，不回全文/密碼 |
| `GET /api/statements`、`GET /api/statements/{id}` | 分頁列表及結構化核對明細，明示尚未入帳 |
| `GET/POST /api/statement-accounts` | 帳戶列表/新增 |
| `PATCH /api/statement-accounts/{id}` | 受限修改別名/未使用綁定，已入帳身份不偷偷改 |
| `POST /api/statements/{id}/confirm` | 帶 review_version，過期/衝突回 409 |

### S6B 原子確認、查詢與撤銷

1. 同一寫入 transaction 再查 Document 有效、帳戶/期別/版本/核對及草稿完整。unknown、缺日期、核對不符不得靠確認繞過。
2. Finance rows、Statement imported、Job 一起提交；任意列失敗全 rollback。技術失敗另記安全原因碼，不含底層內容。
3. 重複成功確認回原結果/IDs，不新增交易/成功 Job。測併發確認及確認與撤銷競爭，用 DB 約束/條件更新，不只靠程序鎖。
4. 更新 `finance/queries.py` 及影響預覽共用計算：legacy CSV 不變；卡片收入 0，支出 = 消費+費用+利息-退款，繳款 0。只有退款時淨支出可負，不截為 0。
5. 搜尋/列表/總覽/撤銷影響沿用有效文件條件；恢復只納入舊交易，不重解析/建 IDs，Excel 從提交狀態重建。
6. 首次導入查同一期是否曾用 CSV 匯入；沒有帳戶/期別就不能宣稱跨 CSV/PDF 去重。使用者確認後撤銷錯誤舊來源，不自動刪相似交易。

### S6C Excel 正確性與相容性

**修改：** `exports/ports.py`、`service.py`、`xlsx.py`、`test_workbook_export.py`、`test_xlsx_writer.py`。

1. 快照最小新增 statement/account/source type/kind/period/posting_date/狀態；只由已提交有效資料產生，草稿不算正式交易。
2. 新增第一表「信用卡月支出」，只算確認的卡片交易，按自然月/帳戶/幣別列消費、退款、淨消費、費用、利息、含費用支出及已取得期別。繳款可列但不計收入/支出。
3. 保留「交易明細」及原核心欄，追加來源類型、帳戶、交易類型、入帳日、期別、來源/列 ID；含 CSV 與卡片，能篩選來源，不複製第二套明細表。
4. 保留「月份幣別摘要」名稱與 CSV 摘要用途，限定 legacy CSV，表頭清楚標示。PDF 不再與可能重複的舊 CSV 混算，卡片報表以新表為準。
5. 「文件狀態」讀 Statement/核對結果，零交易 imported 不標待處理；未完成 PDF、已撤銷來源可見但不加支出。
6. Excel/API 共用純計算規則，不在 writer 複製不同符號公式。第 14 節數值逐一驗收；用 openpyxl 讀回 cell values/types，不只查檔案存在。
7. fingerprint 納入輸出格式版本及影響輸出的別名/狀態，避免欄位或格式變更被 skip。PDF readiness 不再硬寫 False，也不能因 contract 存在就 True；顯示實際驗收的 bank/parser 範圍。
8. 保留 ownership marker、input/output hash、atomic replace、背景檢查/重試、不可信文字防公式/連結。新欄位也防公式注入，日期/金額維持可計算型別。
9. Excel 失敗不 rollback 已提交交易，不把 Statement 改回 pending；顯示「已入帳、Excel 待更新」，只重試輸出，不重匯 PDF。
10. 專用工作簿是系統產生檔，手寫修改會被重建覆蓋；個人筆記另放自己的工作簿。下載是當次副本，只有設定的本機輸出檔持續更新，不宣稱下載檔會同步。

**必測：** 多來源/同 SHA、同帳期不同文件、合法相同列、重複/過期/併發確認、與撤銷競爭、解析/寫入失敗、零交易、撤銷重掃、恢復 IDs、CSV 回歸、Excel 開啟/外部改檔/重建/公式注入。
**完成：** 全套 tests/build 通過；隔離且授權的真實 PDF 逐列核對後確認，Excel 相符，重跑新增 0 筆，撤銷消失/恢復原 IDs。真實測試產物不入 Git；缺真實關卡只寫合成流程完成，不勾整步。

## 11. S7：最小操作介面

**目標：** 不需終端呼叫 API，不重做 Dashboard。
**修改：** 既有設定、ExcelExportSettings、文件詳情/對話框及必要 API client/type。

1. 沿用 Gmail、個人解鎖、Excel 設定；新增最小帳單帳戶綁定，只顯示 parser 已確認的銀行/遮罩線索與可選別名，不要求使用者手填銀行、機構、家庭成員或解鎖 profile。
2. 一個「待處理帳單」入口，顯示來源/期別/原因/下一步，可選帳戶、補解鎖、分析重試、核對確認、看原件、撤銷。不建第二套文件匣/Jobs。
3. 確認畫面列筆數/期間/幣別/消費/退款/繳款/費用/利息/差額/來源；只有 ready 可確認。409 重載，不沿用舊確認。
4. Excel 區顯示上次成功更新、檔案狀態、待處理數、立即更新/下載；檔案佔用提示關閉 Excel 後重試，不把已入帳顯示成整批失敗。
5. 舊 overview/search/transactions/documents/activity URL 保留；只調必要入口，不做分類、商家管理、圖表、全站導覽重排。
6. 顯示收到哪些期別，不在缺少應到規則時宣稱全部到齊；自然月支出不等於帳單應繳，空月份不表示沒有支出。

**驗收：** 全套 tests/build；實際瀏覽器桌面/390px/320px 收錄→分析→確認→Excel→撤銷/恢復，有載入/空白/錯誤/重複點擊防護、焦點/返回路徑且不溢出。前端目前無獨立 test runner；需要時只加本流程最小互動測試配置，不換框架，不把 build 當操作測試。

## 12. S8：沿用 Gmail，受控自動入帳

**前置：** S4/S6 真實關卡通過、S7 可處理例外；使用者明確啟用指定帳戶自動入帳。同步、AI 密碼分析、自動入帳是不同選項。

### S8A 有限範圍，不重寫引擎

1. 沿用 GmailSyncUseCase、full/resume/message search、去重與 shared lock；新增明確帳單模式，不從自由文字 q 推測附件策略。
2. 帳單模式用確認過的銀行寄件者/主旨條件加 PDF，預設 in:anywhere、不限日期；重複查同一銀行全部可存取帳單信件，靠來源/內容去重。家用量先不建 90 天窗口/停機水位系統。
3. 查詢篩郵件不保證附件全為 PDF；附件層明確 pdf_only，同封 CSV 不自動匯入。一般手動 PDF/CSV 模式相容。
4. 宣稱包含垃圾郵件/垃圾桶時，list 呼叫要實際帶對應 includeSpamTrash；不是只在 q 寫 in:anywhere。FakeGmail/HTTP 參數測試需覆蓋。
5. 使用者限制日期時顯示真實範圍及範圍外未掃描，不把限定查詢成功當全信箱完成，不用 shared last_successful_at 推測已處理歷史。
6. full-sync query/page token 加上模式/附件策略相容檢查；中途改 q/policy 回衝突。可明確取消當輪續傳重跑，不清 Documents/transactions/預設 History cursor。
7. 沿用失敗頁重試/上限/分頁；token 失效可從同一查詢重跑靠冪等，不永久儲存任意搜尋語法分析結果。

設定與進度分開：既有 `GmailConnection` 最小擴充帳單模式/指定查詢等非秘密設定，`GmailSyncState` 只記當輪 query/policy/page token。手動與 scheduler 都讀相同已保存設定，不把 full-sync 的暫時 query 當成下次排程設定；舊連線升級維持原模式、不自動開啟新帳單模式。新增欄位沿用 S5 的隔離 migration 驗證，不加新設定檔或設定平台。

### S8B 發現後處理與安全開關

1. 同步提交 Documents 後呼叫 S6，不在現有 Gmail sync 外層寫入 transaction 裡解析 PDF/呼叫 AI。先接共用 orchestration，不大改全同步 transaction。
2. 包含已有且合格的 pending/failed，不只新增附件；限已設定銀行/帳戶範圍，跳過 imported/revoked。缺資料的 pending 等條件改變或人工重試，不每輪重打 AI。
3. 每份獨立處理，單份失敗不回滾其他帳單；同步成功/PDF 待處理/Excel 待更新分開，新附件 0 不代表全部完成。
4. 首份人工核對後使用者才可開該帳戶自動入帳；授權持久化綁 bank/account/parser version，新版本/綁定變更使資格失效。
5. 唯一帳戶、驗收格式/版本、解鎖條件、matched 核對、無 unknown/缺日期/同期衝突且 opt-in 才走同一 confirm；其餘待處理，不猜、不靜默略過。
6. 保留每 30 分鐘排程及背景到期檢查；關閉不跑，重啟按既有 due 邏輯補跑。不新增每日/退避平台、不刪 History，頻率優化等使用證據。
7. 不重設既有授權；首次 OAuth 由使用者操作。開發用 fake，真實驗收限授權銀行帳單範圍，不輸出全文/token。

**必測：** 混合附件、垃圾桶參數、範圍不借 History、分頁改 policy、多頁/上限/重啟、下載暫時失敗/失效 token、長停機重掃、授權失效、重複/撤銷、舊 pending、auto/AI 關閉、未知版型/版本變更。
**完成：** FakeGmail/scheduler focused tests 與一次授權真實重跑：範圍不漏頁、重跑 0 新增、待處理可見、Excel 更新。用注入時鐘測排程，不等待一天；沒跨日測試不宣稱長期穩定。

## 13. S9：固定 Windows 入口與正式驗收

**範圍：** README、`docs/operations.md`、最小啟動/停止腳本、必要 FastAPI 靜態入口。

1. 隔離環境 build React，FastAPI 提供正式靜態資源與同源 API；檢查 VITE_API_BASE_URL，不把開發埠寫死進 build。SPA fallback 不吞 /api/* 404。
2. 固定入口埠，同一 Windows 使用者啟動，Credential Manager 身份一致；不以 Vite 常駐，不做安裝器/service。
3. 重複啟動已屬本 app 的健康程序可開原入口；其他程式佔埠就報錯，不任意 kill/換埠。以 ownership/健康資訊識別，不只看埠有回應。
4. 啟動/停止支援空白路徑、健康檢查、清楚錯誤；背景程序隱藏視窗。登入啟動是 OS 持久設定，需明確同意，預設不註冊。
5. 辨識正式 DB/storage、停服務、成對備份並驗可讀，再授權 migration。啟動只檢查 schema，不靜默 upgrade，不建空 DB 冒充升級。
6. 說明 remote-only 附件不在本機備份、秘密不在 SQLite；離線原件由使用者選本機副本，不匯出明文 secrets 當備份。
7. 先完成本機；需其他裝置才驗 Tailscale。OAuth/token/Tailscale/Firewall 易變設定查當時官方文件；不擅改網路/公開服務。
8. 真實端到端：來源→解鎖→逐筆核對→入帳→Excel→重跑→撤銷/恢復→Excel 佔用重試→重啟恢復；報告不含秘密/全文。

**完成：** 全套 backend/build、隔離操作測試、固定網址及一鍵啟停可用；正式資料/跨日驗收各有證據。外部未完成明列，不以 localhost 可開就稱自動化交付。

## 14. 固定驗收資料與數值

以下全為合成資料，不使用對話真實個資。同一合成帳戶，期別覆蓋這些列；核對摘要另依測試銀行規格建立。

| line_index | 日期 | 入帳日 | kind | amount | 幣別 | 條件 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-31 | 2026-02-02 | purchase | -1000.00 | TWD | 算一月，不是二月 |
| 2 | 2026-02-05 | 2026-02-06 | purchase | -200.00 | TWD | 與下列同店/日期/金額 |
| 3 | 2026-02-05 | 2026-02-06 | purchase | -200.00 | TWD | 仍為獨立交易 |
| 4 | 2026-02-06 | 2026-02-07 | refund | 50.00 | TWD | 不是收入 |
| 5 | 2026-02-07 | 2026-02-08 | payment | 1500.00 | TWD | 不是收入/支出 |
| 6 | 2026-02-08 | 2026-02-09 | fee | -10.00 | TWD | 費用分列 |
| 7 | 2026-02-08 | 2026-02-09 | interest | -5.00 | TWD | 利息分列 |
| 8 | 2026-02-09 | 2026-02-10 | purchase | -8.00 | USD | 與 TWD 分開 |

預期：一月 TWD 消費 1000；二月 TWD 消費 400、退款 50、淨消費 350、費用 10、利息 5、含費用支出 365；繳款 1500 只供核對；二月 USD 支出 8。卡片收入 0，不能用應繳推算這些數字。

加一份二月 legacy CSV +3000/-100 TWD：舊 CSV 摘要收入 3000/支出 100，不進「信用卡月支出」。共用一般查詢若含兩者按語意相加，不把 +50/+1500 當額外收入。

重跑/重複確認仍 8 筆卡片交易且 IDs 不變；撤銷該 Document 後移除卡片金額、CSV 不變；恢復相同 8 個 IDs。另測只有退款、零交易、缺日期、unknown。

## 15. 例外與回復

以下為語意要求，已有等價 reason code 就沿用，不為改名稱破壞 API。

| 例外 | 狀態/動作 | 禁止 |
| --- | --- | --- |
| 需要密碼/規則 | pending，指向本機解鎖設定 | 讀聊天秘密、遍歷成員、暴力猜密碼 |
| 不支援/缺日期/unknown | pending，看來源或等待 parser | 任意 regex/AI 猜列 |
| 核對不符 | pending，顯示差額/缺項 | 造平衡列或確認跳過 |
| 帳戶歧義 | pending，使用者選取/修正 | 只靠末四碼/寄件者 |
| 同期不同文件 | pending conflict，指向既有來源 | 自動替換已入帳/已撤銷 |
| 來源不可用/OAuth 失效 | 保留文件，修連線再試 | 刪來源/假成功/洩 token |
| 原子匯入失敗 | 無部分交易，安全失敗紀錄 | 清空已有交易重跑 |
| Excel 佔用/寫入失敗 | 入帳不變、保留舊檔、重試輸出 | 重匯一次 PDF |
| 版本過期/正在處理 | 明確衝突、重載/等待 | 失效程序覆寫新結果 |

回退先關新自動入帳，保留資料/來源；Excel 可由 DB 重建。開發用隔離 DB；正式回退須授權，還原升級前成對備份及相符程式，不以破壞性 downgrade/reset 丟資料。

只有缺樣本、必要外部授權、無法自行排除的契約決策才停對應關卡，列具體缺件與已驗證範圍，不另開平台任務填時間。

## 16. 完成標準與舊計畫差異

| 關卡 | 必須交付 | 不要求 |
| --- | --- | --- |
| M9 / S0-S6 | 一家銀行兩期驗證、原子確認/去重/撤銷、真實 PDF 正確到 Excel | 完整 Dashboard、分類、每日排程 |
| M10 / S7 | 最小帳戶設定/待處理/確認/Excel 操作，桌面手機可用 | 全站重排、財務管理平台 |
| M11 / S8-S9 | 沿用 Gmail 的受控自動入帳、固定 Windows 入口、授權真實驗收 | History 重寫、事件平台、原生 App |

- 舊 S7 Excel 提前到 S6C；月報圖表及分類/備註不再列本輪待辦。
- 舊 S8 的 90 天水位、每日/退避新排程、停止 History 取消本輪要求，不刪已有實作。
- Documents/SecretStore/去重/撤銷是必要可靠性，不為縮短檔案數拆除。
- 不以測試數量、抽取字數、文件數、Excel 存在判定成功；要逐筆正確、重跑 0 新增、撤銷/恢復一致。

## 17. 可執行驗證命令

從 repo 根目錄用既有 .venv，先確認測試設定隔離 DB，不自動安裝/升級依賴。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini heads
git diff --check
```

S1-S4 現有 focused tests：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_gmail_sync.py backend/tests/test_password_rules.py backend/tests/test_pdf_api.py backend/tests/test_pdf_processor.py backend/tests/test_pdf_processing.py backend/tests/test_statement_contracts.py backend/tests/test_statement_normalization.py -q -p no:cacheprovider
```

S5-S6 現有回歸 tests：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_migrations.py backend/tests/test_imports.py backend/tests/test_document_lifecycle.py backend/tests/test_workbook_export.py backend/tests/test_xlsx_writer.py -q -p no:cacheprovider
```

`test_statement_parser.py`、`test_statement_import.py` 等為待新增，建立後才列 focused command，不引用不存在檔案當驗證。S8 另查現有 scheduler/client 測試並跑受影響集合。

Alembic heads 只讀 migration 定義；schema 驗證沿用 `test_migrations.py` 的 tmp_path + Config，明確覆寫暫存 URL，測 upgrade/資料保留/限制。**未指定隔離 DB 的 upgrade head 不得當測試命令。**

每包回報變更/檔案、實際命令/結果、真實/合成範圍、未完成、下一步。文件回報只列實際文件檢查，不冒稱測試/build。

## 18. 給 Luna max 的啟動指示

> 請開始實作「家庭收支記錄」。先讀 `AGENTS.md`、`README.md`、`HANDOFF.md`、`TASKS.md`、`IMPLEMENTATION_PLAN.md`、`FREE_AI_PASSWORD_RULE_PLAN.md`，並重新確認 Git HEAD/status。`main` 已包含 `eeb6883` 的 Groq 程式，禁止重做或覆蓋。先核實 S1-S3、S3F-A 與 Statement contract；如果 runtime 尚未切 Groq，先完成 S3F-B synthetic activation，並優先補 S3F-C safe-switch preflight；之後從真正未完成的 S4 接續。目標是信用卡 PDF 正確到 SQLite/Excel，不是擴建家庭平台。S6 必須先交付正確 Excel，不做完整 Dashboard、分類或同步引擎重寫。parser 需要一家銀行兩期授權樣本，缺樣本不得猜格式/假稱通過。使用隔離資料/fake provider，不讀聊天秘密，不自行操作正式 DB、啟用外部服務/排程或改網路；Git 寫入依使用者當次授權。遇必要外部關卡才停並列缺件。
