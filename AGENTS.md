# 專案指引

## 專案導覽

- `README.md`：目前功能、環境、啟動和測試命令。
- `PROJECT.md`：信用卡 PDF 到 Excel 的近期目標、歷史 v0.1 範圍與明確排除項目。
- `ARCHITECTURE.md`：模組邊界、資料流、依賴方向與部署設計。
- `TASKS.md`：目前里程碑與待辦。
- `HANDOFF.md`：當前可驗證狀態、下一步與風險。
- `IMPLEMENTATION_PLAN.md`：Excel 優先的 S0-S9 工作包、檔案落點、固定驗收數值、停止條件及 Luna max 啟動指示。
- `ARCHITECTURE_REVIEW_BRIEF.md`：2026-09-28 使用者最新的信用卡帳單優先需求、Overdesign 假說、候選簡化方向與高階模型 review gate。
- `backend/src/family_finance_hub`：FastAPI、application use cases、domain services、ports 與 adapters。
- `backend/tests`：後端自動化測試。
- `frontend/src`：React/TypeScript Web UI。

## 邊界與限制

- 近期工作依 `IMPLEMENTATION_PLAN.md` 收斂為信用卡 PDF 解鎖、解析、核對、SQLite 入帳及每月支出 Excel；Web 只補設定與例外處理。S6 先交付正確 Excel，不以完整 Dashboard、分類或同步引擎重寫為前置，不擴充通用家庭平台。獲得實作指示後按 S0-S9 連續完成，每步驗證及更新交接後繼續；必要真實樣本/外部授權不足才停在關卡。未通過真實資料關卡不得宣稱自動化完成；候選簡化不是任意刪除/重構授權。
- 保留現有 Gmail History/message search、每 30 分鐘 opt-in 排程及 Excel 背景檢查；本輪只接帳單 PDF-only 與受控入帳，不新增 90 天掃描水位、每日排程或事件平台。舊計畫中這些重寫要求已延後，以新版 IMPLEMENTATION_PLAN 為準。
- 保持 Modular Monolith；不引入 microservices、Redis、Kafka、Kubernetes 或 PostgreSQL。
- v0.1 本機上傳由 Documents 接收並透過 StoragePort 保存；文件讀取與解析必須透過 `DocumentSource` / `DocumentProcessor` 邊界，不可假設每筆 Document 都有永久 local file。
- Documents 是 logical document identity + metadata + source relationship。Local File、Gmail Attachment 及未來 Drive 等來源應透過 `DocumentSource` port 取得內容。
- PDF、CSV、Image、password-protected PDF、OCR 等內容理解應透過 `DocumentProcessor` 邊界，不得讓 Finance domain 直接依賴 Gmail SDK、filesystem 或特定 parser/provider SDK。
- Gmail attachment 預設採 remote-reference 模式：解析可使用 memory/受控 temporary bytes，但除非使用者明確選擇保存，否則不要永久寫入本機 Documents storage。
- 查看 remote-only 原始文件時，優先由 source adapter 即時取得並 stream；必須處理 provider unavailable、authorization expired、source deleted 等錯誤。
- 跨 Documents、Finance、Jobs 的 use case transaction 由 application/use-case 層擁有；底層 service 不應自行 commit 整個 use case。
- 文件撤銷／恢復由 `DocumentLifecycleUseCase` 原子更新並留下工作紀錄。Finance 列表、搜尋、統計需共用有效文件條件；任何匯入來源不得自動恢復已撤銷的相同 SHA-256 文件。新增模組需遵守文件有效狀態並提供本模組的影響預覽。
- Domain/Application 不直接依賴 Windows filesystem、FastAPI request objects 或供應商 SDK。
- SQLAlchemy/Alembic 是 SQLite schema 持久化路徑；migration 不可由生產程式啟動時靜默取代。
- 不記錄文件內容、PDF 密碼、secret、OAuth token、身分證字號、生日或完整敏感資料。M5.2 必須使用 Windows Credential Manager/SecretStore；AI 只解析密碼規則文字，不得接收真實身分證字號、生日或實際密碼。
- 新增模組應新增自己的 domain/service/schema migration，避免直接操作其他模組資料。
- 進度以 TASKS.md 與 HANDOFF.md 為準：M5 共用流程、M6 撤銷／恢復、M7.1-M7.5 使用體驗改善及 M8 的 Excel 自動投影已實作；銀行 PDF 交易解析、正式資料庫升級與外部環境驗收仍未完成。不得把文件收錄、PDF 解密／抽取文字或合成測試當成真實帳單自動入帳驗收。
- 近期產品方向以 `ARCHITECTURE_REVIEW_BRIEF.md` 為 review gate：核心目標收斂到每月信用卡帳單自動分析。高階審查完成前，不新增非核心平台能力，也不得把 brief 中的候選簡化直接視為已批准的刪除/重構。
- Excel 是 SQLite 已提交交易的可重建投影，不是資料來源。只能覆蓋帶應用程式 ownership marker 的專用工作簿；外部修改、檔案佔用與輸出 hash 不一致必須保留可見狀態，不得靜默覆蓋未知檔案或把 Excel 反向匯入 Finance。
- M5.2 密碼流程必須使用 versioned PasswordRule DSL；禁止直接執行/eval LLM 產生的程式碼，禁止以大量排列組合暴力猜密碼。
- Bank-specific 密碼說明辨識、PasswordComposer、PDF decrypt、BankStatementParser 必須分層；不要把銀行規則硬編碼進通用 PdfDocumentProcessor。
- 修改 Gmail、PDF 或密碼流程前，先閱讀 ARCHITECTURE.md 的「密碼保護 PDF 與密碼規則解析」及 HANDOFF.md 的目前狀態與安全界線。

## 驗證

從 repository 根目錄以既有 `.venv` 執行後端測試及 `npm --prefix frontend run build`，完整命令見 IMPLEMENTATION_PLAN。schema 變更沿用 `backend/tests/test_migrations.py` 的暫存 SQLite/Alembic Config，驗證升級、資料保留與限制；不把未指定隔離 DB 的 `upgrade head` 當測試。若缺 runtime 或依賴，明確回報未執行範圍，不可宣稱通過。

若只修改設計文件，不必為了文件變更虛構程式驗證；HANDOFF 必須清楚區分「已決定/已規劃」與「已實作/已驗證」。

接手先檢查 Git 狀態並保留未提交修改，再讀本指引、README、HANDOFF、TASKS 與 IMPLEMENTATION_PLAN。`ARCHITECTURE_REVIEW_BRIEF.md` 是背景，checkout 缺檔時可唯讀查看本機已有的 `4ca61b1` 版本，不自行合併。S1-S3 及 S4 純契約已有程式與隔離測試，先核對而非重寫；銀行 parser 仍需兩期授權樣本。文件修改與程式實作授權分開；開始實作後每步完成即接下一步，必要外部關卡才停止。

## 完成標準

- 更新與實際行為相符的文件及 HANDOFF。
- 執行受影響的測試/建置並回報結果。
- 未收到使用者明確要求時，不自動 commit、push、merge、reset，也不覆蓋使用者未提交內容。
