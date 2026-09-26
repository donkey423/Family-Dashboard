# 專案指引

## 專案導覽

- `README.md`：目前功能、環境、啟動和測試命令。
- `PROJECT.md`：產品目標、v0.1 邊界與明確排除項目。
- `ARCHITECTURE.md`：模組邊界、資料流、依賴方向與部署設計。
- `TASKS.md`：目前里程碑與待辦。
- `HANDOFF.md`：當前可驗證狀態、下一步與風險。
- `backend/src/family_finance_hub`：FastAPI、application use cases、domain services、ports 與 adapters。
- `backend/tests`：後端自動化測試。
- `frontend/src`：React/TypeScript Web UI。

## 邊界與限制

- 保持 Modular Monolith；不引入 microservices、Redis、Kafka、Kubernetes 或 PostgreSQL。
- v0.1 本機上傳由 Documents 接收並透過 StoragePort 保存；文件讀取與解析必須透過 `DocumentSource` / `DocumentProcessor` 邊界，不可假設每筆 Document 都有永久 local file。
- Documents 是 logical document identity + metadata + source relationship。Local File、未來 Gmail Attachment、Drive 等來源應透過 `DocumentSource` port 取得內容。
- PDF、CSV、Image、password-protected PDF、OCR 等內容理解應透過 `DocumentProcessor` 邊界，不得讓 Finance domain 直接依賴 Gmail SDK、filesystem 或特定 parser/provider SDK。
- Gmail attachment 預設採 remote-reference 模式：解析可使用 memory/受控 temporary bytes，但除非使用者明確選擇保存，否則不要永久寫入本機 Documents storage。
- 查看 remote-only 原始文件時，優先由 source adapter 即時取得並 stream；必須處理 provider unavailable、authorization expired、source deleted 等錯誤。
- 跨 Documents、Finance、Jobs 的 use case transaction 由 application/use-case 層擁有；底層 service 不應自行 commit 整個 use case。
- 文件撤銷／恢復由 `DocumentLifecycleUseCase` 原子更新並留下工作紀錄。Finance 列表、搜尋、統計需共用有效文件條件；任何匯入來源不得自動恢復已撤銷的相同 SHA-256 文件。新增模組需遵守文件有效狀態並提供本模組的影響預覽。
- Domain/Application 不直接依賴 Windows filesystem、FastAPI request objects 或供應商 SDK。
- SQLAlchemy/Alembic 是 SQLite schema 持久化路徑；migration 不可由生產程式啟動時靜默取代。
- 不記錄文件內容、PDF 密碼、secret、OAuth token、身分證字號、生日或完整敏感資料。M5.2 必須使用 Windows Credential Manager/SecretStore；AI 只解析密碼規則文字，不得接收真實身分證字號、生日或實際密碼。
- 新增模組應新增自己的 domain/service/schema migration，避免直接操作其他模組資料。
- v0.1 已完成；下一階段工作以 TASKS.md 的 M5 為準，不得把尚未實作的 Gmail/remote source/SecretStore/password-rule/PDF 功能寫成已完成。
- M5.2 密碼流程必須使用 versioned PasswordRule DSL；禁止直接執行/eval LLM 產生的程式碼，禁止以大量排列組合暴力猜密碼。
- Bank-specific 密碼說明辨識、PasswordComposer、PDF decrypt、BankStatementParser 必須分層；不要把銀行規則硬編碼進通用 PdfDocumentProcessor。
- 實作 Gmail 前先閱讀 ARCHITECTURE.md 的「密碼保護 PDF 與密碼規則解析」與 HANDOFF.md 的 M5.2 邊界。

## 驗證

從 repository 根目錄執行 `python -m pytest backend\tests` 與 `cd frontend; npm run build`。資料庫 schema 變更需另外檢查 `alembic -c backend\alembic.ini upgrade head`。若環境未安裝 Python 或前端依賴，明確回報未執行的驗證，不可宣稱通過。

若只修改設計文件，不必為了文件變更虛構程式驗證；HANDOFF 必須清楚區分「已決定/已規劃」與「已實作/已驗證」。

## 完成標準

- 更新與實際行為相符的文件及 HANDOFF。
- 執行受影響的測試/建置並回報結果。
- 未收到使用者明確要求時，不自動 commit、push、merge、reset，也不覆蓋使用者未提交內容。
