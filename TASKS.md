# 家庭收支記錄里程碑

## 每次交付必測：E2E-GMAIL-3BANK

- [x] 當次從 Gmail 重新下載三家不同銀行的真實信用卡對帳單，先確認來源郵件密碼格式，再完成加密解鎖、完整交易解析/核對及冪等重跑；三家全 PASS 才可宣稱專案交付完成。

使用者 2026-09-30 指定強制執行，UI/設定/部署修復也不省略。詳細步驟、秘密保護、正式資料不自動入帳及 FAIL/BLOCKED 條件見 `IMPLEMENTATION_PLAN.md` 第 4.1 節；當次結果見 HANDOFF。舊測試結果、合成資料、只抽文字及三封同一家銀行都不算通過。此 checkbox 只表示本次交付關卡，不是一次勾選後永久完成。

2026-09-30 正式部署後最新實測為 **PASS（3/3）**，證據在 `data/gmail-acceptance/retest-20260930-1903/`：用 `prepare → 附件下載 → collect` 從 Gmail 新下載九月中國信託、國泰世華、永豐加密帳單，先確認郵件格式，於隔離 API 完整解析 1/19/31 列，獨立逐列／合計核對及冪等通過。中信第一次未產生新檔，重新載入原信、確認附件可用後以新 checkpoint 重試成功；沒有借用舊檔。利息認列仍依批准政策；驗收期間正式 Finance 18 → 18、schema 0012／fingerprint 不變，隔離 Finance 0 筆，沒有 confirm 或 AI request。完整 backend 326 passed（含 16 項下載回歸）、2 warnings，frontend 29 passed／production build 成功。網頁替代不是 MCP／cron 驗收；正式分類頁桌面與 320px／390px 已實測，實體手機仍未驗證。詳細證據見 HANDOFF。

本次更新研究 MD 與 Git 封存，沒有新的程式／部署交付；重新跑現有 backend 326、frontend 29 及隔離 build 通過，未再下載 Gmail。上方 checkbox 及三銀行 PASS 僅指前次 1903 部署驗收，不適用未来 M13/A1-A6；純文件與交付關卡的區分見 canonical plan 第 15 節及 HANDOFF。

## 目前執行入口：信用卡 PDF 到 Excel

2026-09-30 已將日常 Gmail 收件責任移出網站：Codex Gmail MCP／排程負責搜尋與下載，FamilyHub 只接收本機匯入、SHA-256 去重、遮罩提示、解析核對與入帳。網站內建 Gmail OAuth UI/scheduler 預設停用，舊程式只保留相容。中國信託 parser → Finance → Excel、Groq provider 程式與 safe-switch 已完成；下一個外部關卡是 Codex 排程的真實 Gmail 執行、第二期盲測、更多已授權版型及真實 Groq 驗證。

- [x] S0：重新確認 Git/隔離環境，重跑測試與 build。
- [x] S1：Gmail 自訂 query 與預設 cursor 隔離、分頁、失敗重試；FakeGmail 聚焦測試通過。
- [x] S2：密碼提示 HTML/重疊上下文、遮罩後截斷；測試僅使用合成資料。
- [x] S3：共用 PDF 解鎖 application use case、唯一安全 profile 匹配及 API 相容性測試。
- [x] S3F-A：Groq/OpenAI provider-neutral 程式、Groq Responses adapter、設定 API/UI、安全邊界與合成測試已完成；實作 commit `eeb6883` 已合併至 `main`。
- [x] S3F-C：Safe switch hardening——已增加不落盤的 provider test、保存前 preflight、穩定 provider error reason codes；新設定失敗會保留舊 Active Provider，且不會自動 fallback 到 OpenAI。
  - Status API 必須區分「DB profile 存在」與「credential 可用」，但不得回傳 credential。
  - UI 明確顯示目前 Active Provider + Model，並拆成「測試連線」與「保存並切換」。
  - PDF 預覽只有在 profile 已設定且 credential 可用時才會啟用 AI；credential 遺失時直接維持本機／手動流程。
  - 深度審查、實作落點與測試矩陣見 `GROQ_RUNTIME_REVIEW.md`。
- [ ] S3F-B：Runtime activation——S3F-C 完成後，在本機明確啟用 Groq，確認 Active Provider/Model=`groq`/`openai/gpt-oss-20b`，用 synthetic prompt 驗證真實 Groq response，再確認相同提示命中 verified cache 而不重打 API。
- [ ] S4：Statement 契約/月支出、正規化閘門、中國信託/國泰世華/永豐已驗證文字版型及受限台新零交易已接入；三銀行當次關卡通過，仍需第二期未參與調整的盲測。
- [x] S5：最小 Statement/account 模型、狀態、冪等約束與 `0011_statement_import` migration。
- [x] S6：分析/帳戶 API、原子確認/查詢、冪等入帳與正確 Excel；已用實際中國信託帳單驗證一筆交易落入 Finance/Excel。
- [x] S7：最小帳戶自動建立、待處理/核對確認及 Excel 操作介面；本機來源另有不含密碼的郵件規則提示 fallback。
- [x] S8A：新增 Codex MCP Gmail 本機匯入 API、來源雜湊、SHA-256 冪等、遮罩提示保存及網站連線狀態；停用網站 OAuth UI 與內建 scheduler。
- [x] S8B-1：建立並啟用 Codex Gmail 自動化；使用 Luna Max 每 30 分鐘搜尋最近 45 天的 PDF 帳單，沒有新附件時保持安靜，自動確認入帳保持關閉。
- [ ] S8B-2：完成首次真實 Gmail 執行與至少一次重跑，驗證新附件可收錄、重跑不重複且失敗需要人工處理時會通知。
- [ ] S9：固定 Windows 入口、授權後的正式升級與真實端到端驗收。

M9 為 S0-S6 的正確 Excel，M10 為 S7 最小操作介面，M11 為 S8-S9 自動化與交付。每步 focused tests，S0/S6/S7/S9 全套 backend/build，schema 另做隔離 migration；更新 HANDOFF 才勾選。缺真實樣本/外部驗收保持未完成，不能拿合成資料代替。S0 已勾是前輪基線，接手仍要重驗。

本輪仍延後完整 Dashboard 重寫、備註/Tag、AI 分類、Budget、Excel 事件驅動重寫，以及 legacy Gmail History/schema 的破壞性移除。2026-09-30 使用者已明确批准 M12「分类支出＋Donut＋Category → Merchant → Transaction 下钻」，canonical 设计与 Test Matrix 只维护在 `CATEGORY_SPENDING_PLAN.md`，避免多份冲突规格。

## M12：消費分類、Donut 與下鑽

2026-09-30 使用者已明確批准；**C1-C5 與正式部署已完成。** 正式 DB／程式均為 0012，18 筆既有交易不變；原網址的真實 Donut／下鑽與分類 Excel 已驗。分類 preview 仍隔離，合成來源已撤銷、有效交易 0 筆。詳細測試對照見 `CATEGORY_SPENDING_PLAN.md`，執行入口與證據見 README／HANDOFF。

- [x] C1：0012 migration、Category／Rule／Override，不修改 FinanceTransaction identity。
- [x] C2：read-time resolver、正規化、穩定優先序、system default、批次 3 次配置 query。
- [x] C3：分類／規則／summary／商家／未分類 APIs、有效分類及篩選後分頁。
- [x] C4：Recharts Donut、Top 5／其餘、退款／抵扣、商家明細下鑽與修改、未分類整理、Vitest／RTL。
- [x] C5：Excel 分類／分類支出／fingerprint、backup／restore、全套 tests／build 及當次三銀行關卡。
- [x] P0：migration／FK／identity、規則、override、退款／付款／多幣別、撤銷恢復、Statement 重跑、API 分頁、Excel 安全及 fingerprint。
- [x] P1：Top-N／下鑽／rollback／stale／URL／鍵盤與 labels／管理／backup；實際桌面及 320px／390px 長名稱修正已驗，實體手機／輔助工具另待驗。
- [ ] P2 效能目標：一萬筆／50 規則 API 首次 259.6ms，暖機 187.4／185.4ms；冷啟動尚未達 200ms。500 商家無 N+1、generated invariants 已通過。
- [x] 使用者授權後：成對備份與副本還原／migration 演練、正式 0011 → 0012、正式 build／正常登入帳戶啟動、正式 Web／Excel 回歸及本輪新下載三銀行關卡。
- [ ] 實體手機、真正螢幕閱讀器與重新開機後持續服務驗收。

## M13：逐筆自動分類（taxonomy 建議已核准寫入，程式實作待授權）

使用者要求以每筆消費用途分類為交通、圖書、飲食等。根因、範圍、取捨、落點、停止條件與品質測試統一在 `CATEGORY_SPENDING_PLAN.md` 第 18 節；本次只更新文件及 Git，不改正式資料或將研究當作程式完成。

- [x] 確認 V1 分類來源缺失：14 類、規則／有效 override 為 0；没有 books 或自動商家辨識，九月六筆支出全未分類，API 合計守恆。
- [x] 定義以每筆刷卡交易為第一階段、多用途商家不硬猜、單筆優先與雲端另取同意，完成 A1-A6 工作包；2026-09-30 进一步核准 taxonomy 建议：饮食、日常采购、交通、购物、居家／水电通讯、家庭／育儿、医疗／健康、娱乐／数位服务、旅游、图书、课程／教育、保险、金融费用、未分类 + 收入／转帐系统类别，并新增 AUTO-09/10 边界与 Donut 测试。
- [ ] A1：依核准 taxonomy 建立經人工核對的分類樣本與未知／反例，重点覆盖交通/旅游、饮食/日常采购、图书/教育、保险/金融费用、娱乐/数位服务及多用途商家；盤點舊 CSV 會計語意缺口。
- [ ] A2：检查最新 Alembic head 后，以新 migration 新增 `books`／`insurance`、调整核准 display names，加入经过验证的本机 A/B/C 商家规则、来源追踪、Donut 未分类保留槽位与 Excel taxonomy fingerprint；正式 DB migration／部署仍需另行授权。
- [ ] A3：逐筆待確認、預設 transaction scope、記住商家影響預覽及原子批次確認。
- [ ] A4：按實際未知樣本決定是否需要可選 AI；雲端用途同意、schema／白名單、安全降級與版本快取。
- [ ] A5：既有資料分類 dry-run、核准後套用，保留原 identity 與 Web／API／Excel parity。
- [ ] A6：完整測試／build、當次新下載三銀行、盲測品質報告與授權部署；未知不可冒充自動成功。


## M0：產品與架構基線

- [x] 固定產品名稱、v0.1 範圍與排除項目
- [x] 固定 Modular Monolith、Clean/Hexagonal 依賴方向
- [x] 固定 Windows、local-first、Tailscale 部署方式

## M1：文件與 repository 骨架

- [x] 建立新 Git repository
- [x] 建立 README、PROJECT、ARCHITECTURE、TASKS、AGENTS、HANDOFF
- [x] 建立 Python backend、React frontend 與操作文件目錄
- [x] 建置/測試與工作區環境檢查

## M2：Documents 與 Jobs

- [x] local filesystem StoragePort adapter
- [x] 文件上傳、格式/大小限制、SHA-256 去重及冪等回應
- [x] Jobs history API 與資料持久化
- [x] migration、文件服務與 API 測試

## M3：Finance CSV、Dashboard、Search

- [x] 通用 CSV 欄位辨識與原始欄位保留
- [x] 交易與來源 Document 關聯及 row-level 冪等匯入
- [x] Dashboard 與跨 Documents/Finance 搜尋 API
- [x] 交易明細 API 支援月份篩選、分頁；總覽金額由 SQLite 聚合
- [x] 匯入解析、重複列與 API 測試

## M4：Web UI 與端到端檢查

- [x] React/TypeScript 操作介面：Dashboard、Documents、匯入、搜尋、Jobs
- [x] 增加完整交易清單、月份篩選與分頁；首頁只載入最近交易
- [x] API 連線錯誤與空狀態
- [x] frontend production build
- [x] 本機啟動及核心流程檢查

## M5：文件來源抽象與 Gmail 帳單

### M5.1 基礎架構

- [x] 調整 Documents model，使 logical document identity 不要求每筆都有 local storage key
- [x] 定義 `DocumentSource` port 與 registry，v0.1 local source 透過來源邊界讀取 bytes
- [x] 定義 `DocumentProcessor` port 並將 v0.1 CSV 結構解析移至 CSV processor adapter；PDF 解密/OCR 於 M5.2d 實作，銀行專用解析仍延後
- [x] 將 Documents + Finance + Jobs 的 transaction ownership 上移至 application/use-case 層
- [x] 補齊 SHA-256 併發重複匯入的 IntegrityError recovery 與測試
- [x] 新增 Alembic migration，保留既有本機文件及其關聯

### M5.2 Gmail 手動同步與加密 PDF 先跑通

#### M5.2a 文件來源模型補強

- [x] 在接 Gmail 前將 Document source 從 1:1 欄位模型調整為 Document 1:N source records，使 remote source 與 local persisted source 可同時存在
- [x] 以 `0003_document_source_records` migration 回填並保留既有 `0002_document_sources` 資料，補升級及安全降級測試
- [x] 定義 source availability / last verified 狀態，避免來源不可用時誤判為 Document 消失

#### M5.2b SecretStore 與家庭秘密資料

- [x] 定義 `SecretStore` port，Windows 實作使用 Credential Manager/相容 keyring backend
- [x] 身分證字號、生日、PDF 密碼、OAuth token/refresh token 不得存一般 SQLite、log、repo 或 plaintext config
- [x] SQLite 僅保存 `secret_profile_id` / `credential_ref` 等非秘密 reference
- [x] 建立家庭成員 secret profile 與銀行/卡別文件安全 profile 關聯；秘密資料不複製進 document metadata
- [x] 簡化目前 UI 為一份個人解鎖資料：只填身分證字號及/或生日，內部沿用 profile schema，無須輸入銀行或家庭成員；舊 API 保留相容

#### M5.2c Password Rule pipeline

- [x] 建立 `PasswordInstructionExtractor`，優先從 Gmail subject/body、sender、attachment filename 與 readable metadata 擷取密碼規則說明並遮罩個資/密碼
- [x] 定義 versioned `PasswordRule` schema/DSL；只允許白名單 source/transform/date-format/separator
- [x] 建立 `PasswordRuleInterpreter` AI boundary；AI 只接收規則文字與必要非敏感 context，不接收真實身分證字號、生日或實際密碼
- [x] AI 回傳 ambiguous/multiple-candidates 時不得自行大量排列組合；預設最多產生 3 個 deterministic candidates
- [x] 建立本機 `PasswordComposer`，由 PasswordRule + SecretStore 組合 candidate；candidate 不可進 DB/log/Job summary
- [x] Gmail PDF 只採來源郵件提示；明確的完整身分證格式先由本機規則確認，若郵件明確區分本國籍身分證與外籍生日則只嘗試這兩個候選並保存成功規則；未確認格式不嘗試，明確候選全失敗也不改猜其他組合
- [x] 已成功驗證的 bank/sender/document pattern + PasswordRule 可持久化重用；只有規則缺失、改變或失效時才重新呼叫 AI
- [x] 支援常見生日格式及台灣民國年格式，但必須由 PasswordRule 明確指定，不以 brute force 猜測
- [x] 將目前 OpenAI-only provider 改為 Groq Free 優先；沿用 `PasswordRuleInterpreter`、`AIProviderProfile.provider`、SecretStore 與 verified rule cache，不建立通用 AI 平台

#### M5.2d PDF processor

- [x] 擴充 `DocumentProcessor` request/context，context 傳遞 filename/content type/profile 等非秘密資料
- [x] 採 `pypdf[crypto]`：encryption detection、in-memory decrypt、text extraction
- [x] 僅使用一套 PDF dependency；尚無真實帳單相容性證據要求 fallback
- [x] OCR 僅在成功解密且 text extraction 不足時啟動；以 optional PDFium + Tesseract adapter，假 provider 測試觸發條件及記憶體資料流
- [x] OCR 啟動前檢查設定所需 traineddata；缺少語言時提早回報，保留 PDF 預覽並以合成測試驗證
- [x] 定義 domain errors：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_processing_limit`；抽取狀態以 response header 回報，不回傳文件文字
- [x] `/content` 保持原始 bytes；另提供 transient decrypted `/preview`，回應使用 `Cache-Control: private, no-store`
- [x] 以 Gmail 網頁實際下載的多份真實加密信用卡 PDF 驗證：中國信託與台新完成本機下載、郵件明示規則解鎖及文字抽取；永豐與國泰世華在 Gmail PDF 預覽完成解密驗證；驗證用明文輸出未保存

#### M5.2e Legacy Gmail source 與手動同步（歷史相容，預設停用）

- [x] 實作 Gmail OAuth 與安全 token storage；程式採 Gmail read-only scope，client JSON/token 僅存 SecretStore
- [x] 建立單一 `GmailSyncUseCase`，讓所有 trigger 共用同一條同步流程
- [x] 提供「立即同步 Gmail」手動 trigger，不先做 scheduler
- [x] 以 Gmail message ID + attachment part/ID 保存 remote source reference，不預設永久下載附件
- [x] Gmail attachment 以記憶體解析，不落一般 temporary directory
- [x] 支援「查看原始帳單」：Backend 即時 fetch Gmail attachment 並回傳原始 bytes
- [x] 支援「保存到家庭文件匣」：使用者明確選擇後新增 local source，不覆寫 Gmail source
- [x] 定義 Gmail 授權失效或 attachment 不可取得時的 UI/API error handling
- [x] 以真實中國信託信用卡帳單驗證第一個 bank/card parser、帳單合計核對、Finance 與 Excel；其他版型仍逐一取得授權樣本再擴充
- [x] 驗收：連續按「立即同步 Gmail」不會建立重複 Document 或 Finance transaction；Job 在新增、失敗或略過已撤銷文件的批次建立
- [x] 驗收：合成資料測試確認 AI request、API response、DB fixture 不含身分證字號、生日或組合後 PDF 密碼
- [x] 驗收：同一帳單可同時擁有 Gmail remote source 與使用者保存的 local source

### M5.3 Incremental Sync

- [x] 保存 Gmail incremental sync state（history ID、last successful sync time、full-sync continuation）
- [x] 同步時只處理上次成功同步後新增的郵件；初次/過期同步分批 full sync
- [x] history state 過期或失效時可安全 fallback 到受控 full sync
- [x] UI 顯示最後成功同步時間、同步狀態與錯誤摘要

### M5.4 定時自動同步

- [x] 在手動同步與 incremental sync 穩定後加入本機 scheduler；須先完成 Gmail 唯讀授權並由使用者明確開啟，預設關閉
- [x] 啟用後每 30 分鐘觸發一次同一個 `GmailSyncUseCase`
- [x] Windows 關機期間不要求背景執行；下次啟動後會補跑已到期排程，由 incremental sync 補抓漏掉的信件
- [x] UI 顯示「下一次同步」並保留「立即同步 Gmail」按鈕
- [x] scheduler 本身不包含 Gmail 搜尋、解析或 Finance 業務邏輯，只負責 trigger；手動與排程同步不得重疊

### 未來選配：Gmail Push

- [ ] 僅在確實需要「信件到達後數秒內更新」時，再評估 Gmail Push / Pub/Sub
- [ ] Push 仍只觸發既有 `GmailSyncUseCase`，不建立第二套同步流程

## M6：誤匯入撤銷與恢復

- [x] 文件級可逆撤銷，保留來源、原始交易及 Jobs 稽核紀錄
- [x] 影響預覽：筆數、各幣別金額，並拒絕過期的確認請求
- [x] Dashboard、交易列表與搜尋同步排除已撤銷來源；恢復原交易不重建
- [x] 手動上傳與 Gmail 對相同 hash 保持撤銷狀態，包括新郵件的相同附件
- [x] UI 有效／已撤銷清單、原因、確認及恢復流程
- [x] migration 保留既有資料；尚有撤銷文件時拒絕退回不理解撤銷狀態的舊 schema
- [x] 合成資料覆蓋冪等、原子性、Gmail、升降級及備份還原；桌面／手機瀏覽器操作驗證
- [x] 使用中的家庭資料庫以一致性快照升級至 `0011_statement_import`，並完成實際中國信託帳單驗收；舊資料庫保留未改動

## M7：使用體驗、導覽與排版（進行中）

2026-09-27 已完成 M7.1 搜尋與導覽、M7.2 新增資料與來源追溯、M7.3 月份與幣別總覽、M7.4 設定／PDF 預覽及 M7.5 排版／共用介面。不取代 M5 的真實銀行 PDF 交易解析或 M6 的正式資料庫驗收。

建議順序：搜尋與導覽修正 → 明確區分文件收錄與交易入帳 → 文件、交易及匯入紀錄關聯 → 月份／幣別總覽 → 設定與排版。先改善操作與資訊結構，不全面重寫介面。

### M7.1 搜尋與導覽

- [x] 將搜尋獨立為結果頁，修正搜尋後切換設定仍顯示總覽／搜尋區塊的狀態混用；標題、導覽選取與內容一致。
- [x] 搜尋 API 提供各類結果總筆數及分頁；前端不再只顯示固定筆數或以「查看全部」清除搜尋。
- [x] 將搜尋頁、搜尋字詞及兩類分頁同步至 URL，支援重新整理與瀏覽器上一頁；密碼、身分資料及文件內容不進入 URL。
- [x] 為搜尋提供獨立載入、無結果與失敗狀態；快速切換字詞或頁面時，舊請求不得覆蓋新結果。

### M7.2 新增資料與來源追溯

- [x] 統一「新增資料」入口，內含文件上傳、財務 CSV 匯入及 Gmail 同步；明確呈現「僅收錄文件」與「建立交易」的結果。
- [x] 根據實際文件、交易及處理結果顯示「已收錄，尚未入帳」、新增／略過交易筆數或失敗原因；本機副本標記不代表入帳成功。
- [x] 增加文件詳細檢視，整合來源、收錄／入帳狀態、關聯交易、匯入紀錄、原始文件／預覽及撤銷／恢復；收錄日期與交易日期分開顯示。
- [x] 交易可回到 `source_document_id` 對應文件；Jobs 只有在具備 `document_id` 時提供文件連結，批次 Gmail 工作不任意連到單份文件。
- [x] Gmail 日常同步入口放在新增資料／文件流程；OAuth 連線設定保留設定頁，未授權時提供前往設定的下一步。
- [x] 保留 Documents 共用底層、SHA-256 冪等及撤銷保護；恢復仍使用原交易，不重新解析。PDF 仍明示只收錄／預覽／抽取文字，尚未建立交易。

### M7.3 月份與幣別總覽

- [x] 首頁預設顯示本月，可切換月份；支出、收入、淨額及交易筆數均由選定期間呈現，下方顯示該期間交易與待處理文件。
- [x] Dashboard API 支援月份／幣別篩選並由資料庫聚合全部符合資料，不以首頁最近 8 筆或單頁交易計算總額；交易頁共用月份定義及有效文件條件。
- [x] 多幣別以選單及分組結果顯示，不把不同幣別金額相加或默默換匯；總覽連往明細時保留月份／幣別條件。
- [x] 已驗收跨月、當月無交易、多幣別、格式錯誤及撤銷／恢復後的有效資料條件；零筆期間顯示明確空狀態，不推定匯入失敗。

### M7.4 設定與 PDF 預覽

- [x] 設定依「文件解鎖／連線服務／進階設定」分組；目前解鎖頁只收身分證字號及/或生日，不要求銀行、機構或家庭成員。
- [x] 舊 profile API/schema 保留相容，新的個人解鎖 API 只回傳欄位是否已保存，不回傳原值。
- [x] 一般 PDF 開啟即預覽，需要密碼時才展開解鎖設定；錯誤區分需要密碼、密碼錯誤、來源不可用與 OCR 未就緒。預覽成功不代表財務入帳。
- [x] 保存 AI key 後，開啟需要密碼且有提示的 PDF 會自動分析遮罩提示；預覽中可關閉 AI 重試。真實秘密只在本機組合，預覽不啟用同步或永久保存遠端附件。
- [x] PDF 與撤銷／恢復對話框統一鍵盤行為：開啟時移入焦點、Tab 留在對話框、Escape 關閉並回到觸發按鈕。保留撤銷影響確認與過期預覽保護。

### M7.5 排版與共用介面

- [x] 主要內容採固定 14–16px、次要文字 12–13px 的可讀層級；金額靠右且數字等寬，避免多幣別大字擠在同一區塊。不使用隨視窗寬度縮放的字級。
- [x] 手機交易改為能同時看到項目與金額的排列，日期作次行；390px／320px 下不必橫向捲動才看得到金額。長檔名、錯誤文字與按鈕不得互相遮蔽。
- [x] 減少手機頁首及導覽佔高，統一工具列、常見圖示與操作層級，主要觸控操作保留足夠點擊範圍；維持適合日常查帳的緊湊布局，不增加裝飾性巢狀卡片。
- [x] 隨上述功能逐步從 `App.tsx` 分離頁面與共用元件，隔離搜尋、設定及預覽狀態；沿用既有工具與架構，不另起前端或順手重構無關模組。

### M7 驗收與完成標準

- [ ] 每個子里程碑執行受影響的測試及 frontend production build；API／資料查詢有改動時執行 backend 測試，完成後更新 HANDOFF，才能勾選對應項目。
- [ ] 補前端行為測試：搜尋後切頁、URL／上一頁、分頁保留字詞、月份／幣別連動與對話框鍵盤焦點；API 覆蓋搜尋總筆數、分頁及期間聚合。
- [ ] 隔離合成資料涵蓋超過 8 筆交易／5 份文件與每類超過 50 筆搜尋結果、長檔名、大額、多幣別、空狀態、載入及失敗；於桌面、390px、320px 實際操作檢查。
- [ ] 回歸驗證同 hash 不重複入帳、撤銷不被重新匯入復活、恢復不新增交易、過期影響預覽要求重新確認；不讀取正式資料或秘密來完成 UI 驗收。

## M8：Codex MCP Gmail 帳單到 Excel 的長期自動化

產品目標為 Codex Gmail MCP 發現新帳單 → FamilyHub 共用 Documents → 解鎖／解析／核對 → Finance → 專用 Excel 自動更新。Excel 為可重建的輸出；SQLite 保留交易與來源的單一事實來源。附件收錄與帳單確認入帳仍分開，避免錯誤版型直接建立交易。

- [x] 專用 Excel 包含月份／幣別摘要、交易與文件待處理狀態，保留穩定來源 ID。
- [x] 自動偵測已提交資料變更並更新 Excel；重複同步不重複列，撤銷／恢復同步反映。
- [x] Excel 佔用或寫入失敗保留上一版，定時重試；重啟仍可重建，狀態與錯誤可見；外部修改或替換後停止下載並安全重建。
- [x] 設定頁提供啟停、立即更新、下載與尚未入帳 PDF 筆數。
- [x] 真實 Gmail 網頁下載 PDF 已完成格式提示確認、SecretStore 解鎖及文字抽取驗收。
- [x] 取得第一份真實銀行帳單，在本機驗證日期、幣別、消費列與帳單合計核對；目前中國信託版型可用，實際帳單已匯入 Finance。
- [x] 已驗證支援版型的 PDF parser 接入共用入帳流程；未知格式／解鎖失敗／對帳不符保留待處理並可重試。
- [x] FamilyHub `codex_mcp_gmail` 匯入端點、狀態 API、本機附件持久化、來源／內容去重及敏感 context 遮罩。
- [x] 網站移除 Gmail OAuth 設定與同步操作；內建 OAuth API/scheduler 預設停用並 fail closed。
- [x] Codex 應用程式建立並啟用「家庭收支 Gmail 帳單收錄」自動化；Luna Max 每 30 分鐘執行，搜尋最近 45 天並只收錄 PDF，不自動確認入帳。
- [ ] Codex Gmail 排程首次真實執行與跨次重跑驗收；主機或服務離線後需靠近期窗口補抓。
- [ ] 新郵件 → 收錄 → 分析／人工確認 → Finance → Excel 的跨日長期驗收。

## 延後項目

- [x] 通用 OCR provider port、本機 Tesseract adapter 與語言資料預檢（真實 Windows OCR runtime 仍待安裝/驗收）
- [ ] 非密碼規則用途的通用 AIProvider
- [ ] Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property
- [ ] Google Drive 或其他 DocumentSource provider
- [ ] Tailscale 家庭裝置連線及 Windows 防火牆實機檢查
- [x] 以隔離合成資料完成 SQLite + 文件儲存的備份/還原演練測試；未操作使用中資料

## 尚待外部條件

- Codex 的 Gmail MCP 需維持可用連線；網站不再取得 Google Cloud Gmail OAuth。Codex 排程建立後仍需至少一次真實執行及一次重跑，才能宣稱長期收件可用。
- Windows 主機尚未確認 Tesseract 執行檔及 `chi_tra`/`eng` 語言資料；OCR pipeline 以合成 provider 完成測試，真實辨識待安裝 runtime 後驗收。
- 真實信用卡帳單已完成郵件密碼提示、PDF 解鎖、文字抽取、第一個中國信託版型的交易解析與帳單合計核對；目前 Gmail CSV 可用通用解析器，未知 PDF 版型不會因成功解鎖就被臆測為交易。
- Legacy Gmail 同步程式保留但預設停用，不再是產品待辦。Codex 排程只收錄 PDF，不能取代真實帳單 parser、核對與確認入帳驗收。


## M9：產品範圍收斂與架構重新審查（待高階模型確認）

> 本里程碑目前是 review gate，不代表下列簡化已決定實作。完整背景與審查問題見 `ARCHITECTURE_REVIEW_BRIEF.md`。

- [ ] 由高階模型以最新 `main` 實作重新判斷 Keep / Simplify / Freeze / Remove-later，不只閱讀文件。
- [x] 確認近期唯一核心產品流程：Gmail 信用卡帳單 → 安全解鎖 → BankStatementParser → Finance → 月份 Dashboard → optional Excel。
- [x] P0：以第一份真實中國信託信用卡帳單完成 bank-specific parser 與 statement total reconciliation。
- [x] P0：PasswordInstructionExtractor 已改為擷取密碼關鍵字附近的受限上下文並先遮罩敏感值。
- [x] P0：新個人解鎖流程已移除每月人工選 bank/document security profile 的需要；舊 sender 匹配僅供相容，不作為新 UI 前置。
- [x] Gmail 日常同步改由 Codex MCP 管理；FamilyHub legacy History API state 凍結為相容資料，不再新增功能。
- [x] 網站內建 Gmail scheduler 停用；排程頻率與補抓窗口由 Codex 自動化設定，依 source key/SHA-256 保持冪等。
- [ ] 決定 Excel 30 秒 projection worker / UI polling 是否改成交易變更事件驅動 + 手動 rebuild。
- [ ] 凍結 Google Drive、其他家庭 domain、通用 AI、Push/PubSub 與 OCR 進一步優化，直到核心真實帳單流程完成。
- [ ] 不為簡化而全面重寫已完成的 Documents 1:N source / revocation / Excel safety；只有確認維護收益大於 migration/rewrite 成本才修改。
- [ ] 高階審查完成後，先更新本里程碑與 ARCHITECTURE，再開始程式重構。
