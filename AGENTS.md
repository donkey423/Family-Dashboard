# 專案指引

## 專案導覽

- `README.md`：目前功能、環境、啟動和測試命令。
- `PROJECT.md`：信用卡 PDF 到 Excel 的近期目標、歷史 v0.1 範圍與明確排除項目。
- `ARCHITECTURE.md`：模組邊界、資料流、依賴方向與部署設計。
- `TASKS.md`：目前里程碑與待辦。
- `HANDOFF.md`：當前可驗證狀態、下一步與風險。
- `IMPLEMENTATION_PLAN.md`：Excel 優先的 S0-S9 工作包、檔案落點、固定驗收數值、停止條件及 Luna max 啟動指示。
- `ARCHITECTURE_REVIEW_BRIEF.md`：2026-09-28 使用者最新的信用卡帳單優先需求、Overdesign 假說、候選簡化方向與高階模型 review gate。
- `FREE_AI_PASSWORD_RULE_PLAN.md`：Groq Free 密碼規則解析的 provider 設計、安全邊界與驗收規格；實作/切換前必須重新查官方額度與模型支援。
- `GROQ_RUNTIME_REVIEW.md`：Groq 已實作後的程式級深度審查；明確區分 Recommended / Default / Active Provider，並定義 safe-switch preflight、runtime activation 與真實 smoke test。
- `CATEGORY_SPENDING_PLAN.md`：C1-C5 為已核准且已實作的人工分類／商家規則／Donut／下鑽；第 4/18 節记录 2026-09-30 使用者核准写入的下一版 taxonomy、Donut「未分类保持可见」规则、A1-A6 与 AUTO-01-10，**仅文件/Git 已授权，程式 migration／正式部署仍未授权**。分類功能以此文件為 canonical plan。
- `backend/src/family_finance_hub`：FastAPI、application use cases、domain services、ports 與 adapters。
- `backend/tests`：後端自動化測試。
- `frontend/src`：React/TypeScript Web UI。
- `scripts/start_server.ps1`：建置前端後，在 `127.0.0.1:3000` 同時提供 Web 與 API；此主機的登入排程指定 `data/family-finance-hub-live.db`。

## 邊界與限制

- 既有 S0-S9 仍以信用卡 PDF 解鎖、解析、核對、SQLite 入帳及 Excel 正確性為基線，不因新功能回頭重寫核心。2026-09-30 使用者已明確核准下一階段 `CATEGORY_SPENDING_PLAN.md`：每筆交易有效分類、同類歸組、支出 Donut、Category → Merchant → Transaction 下鑽與未分類整理。這是特定產品需求，不等同授權完整 Dashboard、Budget、Tag、AI 理財或通用家庭平台。
- 日常 Gmail 收件由 Codex Gmail MCP／自動化負責；FamilyHub 只接受本機 import endpoint、處理文件與入帳。網站內建 Gmail OAuth/UI/scheduler 預設停用，legacy History/remote source 程式僅供既有資料相容，不再新增功能；Excel 背景檢查維持既有設計。
- 保持 Modular Monolith；不引入 microservices、Redis、Kafka、Kubernetes 或 PostgreSQL。
- v0.1 本機上傳由 Documents 接收並透過 StoragePort 保存；文件讀取與解析必須透過 `DocumentSource` / `DocumentProcessor` 邊界，不可假設每筆 Document 都有永久 local file。
- Documents 是 logical document identity + metadata + source relationship。Local File、Codex MCP Gmail Attachment 與 legacy Gmail remote source 應透過 application／`DocumentSource` 邊界取得內容。
- PDF、CSV、Image、password-protected PDF、OCR 等內容理解應透過 `DocumentProcessor` 邊界，不得讓 Finance domain 直接依賴 Gmail SDK、filesystem 或特定 parser/provider SDK。
- Codex MCP Gmail attachment 採本機持久化模式：匯入端點先檢查大小、SHA-256 與來源 key，再透過 StoragePort 保存；原始郵件本文／Gmail ID 不落盤。Legacy remote-only 文件仍由 source adapter 即時取得並處理 provider unavailable、authorization expired、source deleted 等錯誤。
- 跨 Documents、Finance、Jobs 的 use case transaction 由 application/use-case 層擁有；底層 service 不應自行 commit 整個 use case。
- 文件撤銷／恢復由 `DocumentLifecycleUseCase` 原子更新並留下工作紀錄。Finance 列表、搜尋、統計需共用有效文件條件；任何匯入來源不得自動恢復已撤銷的相同 SHA-256 文件。新增模組需遵守文件有效狀態並提供本模組的影響預覽。
- Domain/Application 不直接依賴 Windows filesystem、FastAPI request objects 或供應商 SDK。
- SQLAlchemy/Alembic 是 SQLite schema 持久化路徑；migration 不可由生產程式啟動時靜默取代。
- 此主機的舊 `data/family-finance-hub.db` 是不相容 revision，保留作原始資料；新網址只用 `data/family-finance-hub-live.db`。兩者不自動同步，禁止直接對舊檔執行新版 migration 或讓新版服務寫入它。
- 不記錄文件內容、PDF 密碼、secret、OAuth token、身分證字號、生日或完整敏感資料。M5.2 必須使用 Windows Credential Manager/SecretStore；AI 只解析密碼規則文字，不得接收真實身分證字號、生日或實際密碼。
- 此主機的常態服務由 `FamilyFinanceHub` 互動式登入排程執行。`scripts/start_server.ps1` 會以獨立、隨機且立即清除的合成憑證測試安全儲存的寫入/讀取/清除；未通過不得占用 3000。Codex 沙箱帳戶曾造成 Windows 1312 寫入錯誤及已存憑證誤顯示未保存；重啟正式服務應使用既有 Windows 使用者排程，而非在沙箱中背景啟動。
- 目前文件解鎖 UI 只收身分證字號及/或生日；內部固定個人 profile 沿用既有 schema，不能把銀行、機構或家庭成員設定重新變成使用者前置步驟。保存 AI key 後，加密 PDF 預覽可分析遮罩提示並在本機組合密碼；不得把這當作 PDF 交易自動入帳。
- 新增模組應新增自己的 domain/service/schema migration，避免直接操作其他模組資料。分類功能必须放在 Finance categorization 边界，不把银行分类逻辑写进 BankStatementParser；V1 以 Category/Rule/TransactionOverride 做 read-time effective category，不把 category 写回 FinanceTransaction identity。
- 2026-09-30 使用者另要求交通／圖書／飲食等逐筆自動辨識，并核准 taxonomy 建议写入 MD/Git：新增规划中的 `books`／`insurance`，收敛显示名称与边界，Donut 在类别很多时保留「未分类」独立 slice。這不等於開始 A1-A6 程式、正式升級／部署或同意交易資料送雲端；当前正式 0012 仍维持既有分类。
- 進度以 TASKS.md 與 HANDOFF.md 為準：平台、Excel、`0011_statement_import` 及 Codex MCP 匯入邊界已有實作；中國信託已完成真實 Finance/Excel，2026-09-30 中國信託/國泰/永豐新下載加密帳單皆通過逐列/合計核對及冪等，後兩家未自動確認入帳。第二期盲測、未知版型、Codex 排程真實/跨日及實體手機仍未完成；不得宣稱通用銀行支援。
- 使用者批准未列日期的利息按明示結帳日認列。只在 `interest` 且 Statement 有 `closing_date` 時適用；用共用 resolver 保持正規化/月彙總一致，來源日期仍為空，API/raw_json 保留認列依據。其他缺日期列仍 pending，不可擴張為所有列自動補日。
- 近期產品方向仍以信用卡帳單正確入帳為核心；但 2026-09-30 使用者已單獨批准分類支出扩展，實作時以 `CATEGORY_SPENDING_PLAN.md` 为准。除此之外仍不新增未核准平台能力，也不得把旧 brief 的候选简化直接视为删除/重构授权。
- Excel 是 SQLite 已提交交易的可重建投影，不是資料來源。只能覆蓋帶應用程式 ownership marker 的專用工作簿；外部修改、檔案佔用與輸出 hash 不一致必須保留可見狀態，不得靜默覆蓋未知檔案或把 Excel 反向匯入 Finance。
- M5.2 密碼流程必須使用 versioned PasswordRule DSL；禁止直接執行/eval LLM 產生的程式碼，禁止以大量排列組合暴力猜密碼。
- 修改 AI 密碼規則 provider 前必讀 `FREE_AI_PASSWORD_RULE_PLAN.md` 與 `GROQ_RUNTIME_REVIEW.md`。Groq 是 Recommended / 新設定 Default，不代表 Active Provider；runtime 只認 backend 已保存 profile + SecretStore credential。免費 API 只能解析遮罩後規則；Groq 失敗/429 不得自動 fallback 到可能付費的 OpenAI，也不得把真實身分證、生日、實際 PDF 密碼或帳單全文送給任何 provider。
- Provider 切換必須 fail-safe：先做 synthetic preflight/Test Connection，成功後才替換 Active Provider；新設定失敗時舊 provider 必須保持可用。不要把這項 hardening 擴張成 multi-provider fallback 平台。
- Bank-specific 密碼說明辨識、PasswordComposer、PDF decrypt、BankStatementParser 必須分層；不要把銀行規則硬編碼進通用 PdfDocumentProcessor。
- 修改 Codex MCP Gmail、legacy Gmail、PDF 或密碼流程前，先閱讀 ARCHITECTURE.md 的「Codex MCP Gmail attachment 流程」、「密碼保護 PDF 與密碼規則解析」及 HANDOFF.md 的目前狀態與安全界線。

## 驗證

從 repository 根目錄以既有 `.venv` 執行後端測試及 `npm --prefix frontend run build`，完整命令見 IMPLEMENTATION_PLAN。schema 變更沿用 `backend/tests/test_migrations.py` 的暫存 SQLite/Alembic Config，驗證升級、資料保留與限制；不把未指定隔離 DB 的 `upgrade head` 當測試。若缺 runtime 或依賴，明確回報未執行範圍，不可宣稱通過。

若只修改設計文件，不必為了文件變更虛構程式驗證；HANDOFF 必須清楚區分「已決定/已規劃」與「已實作/已驗證」。文件更新不代表專案已通過下列真實驗收。

### 必測交付關卡：E2E-GMAIL-3BANK

- 依使用者 2026-09-30 要求，本專案每次交付或宣稱工作完成前，必須重新從 Gmail 下載三家不同銀行的真實信用卡對帳單，確認來源郵件密碼格式、本機解鎖、交易明細解析及核對均成功。包括 UI、設定與部署修復，不得因程式測試通過或修改看似無關而省略。
- 完整測試步驟及通過標準以 `IMPLEMENTATION_PLAN.md` 第 4.1 節為準；三封同一家銀行、快取附件、合成 PDF、舊驗收紀錄、只解鎖或只抽出文字都不能代替本次三銀行測試。
- Gmail 網頁下載必須使用 `scripts/gmail_attachment_download.py`：下載前 `prepare`，點來源郵件的指定附件下載按鈕，再 `collect`。事件逾時不等於檔案不存在；但只有新的、穩定且結構完整的 PDF 才能收錄。禁止拿舊檔、`.crdownload` 或上一檢查點的 receipt 補成功；多個候選不猜。具體命令、重試及隔離核對見 IMPLEMENTATION_PLAN 4.1。
- 三家全部 PASS 才能宣稱真實驗收通過。任一 FAIL 必須先找證據、盡力修復並重跑三家，不得只記錄失敗就結束，也不得降低通過標準。只有缺權限、必要資料、外部服務阻塞或需要使用者決策才可交接；在 HANDOFF 及回覆列出已嘗試修復、具體阻塞及下一步。沒有 Gmail 工具、登入、秘密或受支援版型不是可略過的成功理由。
- 測試不授權自動確認入帳、付費 AI fallback、公開或保存秘密。正式 Finance 不因重複驗收新增紀錄；入帳/Excel 寫入另在已授權隔離流程驗證。

接手先檢查 Git HEAD/status 並保留未提交修改，再讀本指引、README、HANDOFF、TASKS、IMPLEMENTATION_PLAN、FREE_AI_PASSWORD_RULE_PLAN、GROQ_RUNTIME_REVIEW；若任務涉及分類/圖表，必讀 CATEGORY_SPENDING_PLAN。Groq adapter、S3F-C、S1-S3、Codex import、三銀行 parser、Statement 入帳及 M12 分類已有程式／驗證，不因舊紀錄重做。分類邊界在 `finance/categories/{domain,service,api}.py` 與 `frontend/src/categories`。

M12 程式與正式 DB 均已為 `0012_transaction_categories`／18 筆，使用者授權後已同步正式 `frontend/dist`、分類 Excel 與正常登入帳戶排程；入口維持 3000／HTTPS 443。部署備份／證據見 HANDOFF；後續變更仍須核对當次授權及 head，不自動 migration。隔離預覽 3001 → API 8030／HTTPS 8443，只使用 `data/category-preview/synthetic.db`；合成來源已撤銷，有效交易 0 筆，不得自行恢復。測試用短且唯一的 basetemp；未授权部署時 build 到 `dist-category-preview`，不覆蓋正式產物，完整命令見 README。

三銀行真實附件的隔離驗收另用 `scripts/gmail_acceptance_app.py --run-directory data/gmail-acceptance/retest-<唯一識別>`，預設 API 8031，先確認該埠沒有其他服務。此腳本只對受控 retest 目錄做 migration，從正式 DB 唯讀複製 credential references，SecretStore 禁止寫入／刪除且外部 AI 關閉；不作正式啟動器。`scripts/gmail_statement_acceptance.py` 先確認隔離狀態及當次下載 receipt，才呼叫收錄／預覽／分析，永不呼叫 confirm。結果及原始加密附件均只留 Git 忽略的 data 目錄。

## 完成標準

- 更新與實際行為相符的文件及 HANDOFF。
- 執行受影響的測試/建置並回報結果。
- 本次 `E2E-GMAIL-3BANK` 三家全部通過並記錄證據；尚未通過時只能回報局部工作完成，不可宣稱專案交付完成。
- 未收到使用者明確要求時，不自動 commit、push、merge、reset，也不覆蓋使用者未提交內容。
