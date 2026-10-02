# Family-Dashboard Project Rules

本檔只補充 Family-Dashboard 專案特例。通用工作規則由 `$CODEX_HOME/AGENTS.md` 提供。

## Start Here

開始任務前：

- 先檢查 Git HEAD / status，保留使用者未提交修改。
- 讀 `README.md`、`HANDOFF.md`、`TASKS.md`。
- 涉及架構、資料流或 deployment 時讀 `ARCHITECTURE.md` / `IMPLEMENTATION_PLAN.md`。
- 涉及分類功能時讀 `CATEGORY_SPENDING_PLAN.md`。
- 涉及 AI 密碼規則或 provider 時讀 `FREE_AI_PASSWORD_RULE_PLAN.md` / `GROQ_RUNTIME_REVIEW.md`。
- 專案當前狀態、版本、port、測試紀錄與暫時限制以 `HANDOFF.md` 為準，不要複製回本檔。

## Product Scope

- 核心仍是：信用卡帳單取得、解鎖、解析、核對、入帳與可重建輸出正確。
- 已核准的分類功能依 `CATEGORY_SPENDING_PLAN.md` 實作。
- 未明確核准時，不擴張成完整 Budget / Tag / AI 理財 / 通用家庭平台。
- 新需求優先沿用既有能力，不因新功能回頭重寫已穩定核心。

## Architecture Boundaries

- 維持 Modular Monolith；除非有明確需求，不引入 microservices、Redis、Kafka、Kubernetes 或 PostgreSQL。
- Finance domain 不直接依賴 Gmail SDK、filesystem、FastAPI request object 或特定 AI/provider SDK。
- 文件內容取得與處理需經既有 `DocumentSource` / `DocumentProcessor` 邊界。
- 跨 Documents / Finance / Jobs 的 transaction 由 application/use-case 層管理。
- SQLAlchemy / Alembic 是 SQLite schema 的正式持久化路徑；production startup 不得偷偷取代 migration。
- 分類邏輯留在 Finance categorization 邊界，不寫進 bank parser。
- Excel 是 SQLite 已提交交易的可重建投影，不是資料來源。

## Security & Provider Rules

- 不落盤或記錄完整郵件本文、PDF 密碼、secret、token、身分證字號、生日等敏感資料。
- 真實 credential 使用既有 SecretStore / Windows Credential Manager 路徑。
- AI 只處理必要且已遮罩的規則資訊；不得傳送真實密碼、完整帳單或個資。
- Provider 切換需先通過 synthetic preflight，再替換 active provider。
- 免費 provider 失敗時，不自動 fallback 到可能付費的 provider。
- 不執行 / eval LLM 產生的程式碼來組合密碼，也不暴力猜密碼。

## Gmail / Statement Rules

- 日常 Gmail 收件由 Codex Gmail MCP / automation 負責；FamilyHub 接收本機 import，不新增另一套網站內 Gmail scheduler。
- 匯入流程需保持冪等，不因重複來源自動新增重複資料。
- Bank-specific 密碼提示、密碼組合、PDF decrypt 與 statement parser 維持分層。
- 未知版型或無法確認的資料不要猜；保留 pending / review 狀態。

## Validation

實作修改後至少執行：

- 後端相關 tests
- `npm --prefix frontend run build`
- 受影響 runtime flow 的實際驗證

若涉及 schema，使用既有 migration test 路徑驗證升級、資料保留與限制。

### E2E-GMAIL-3BANK

只要任務改到 Gmail attachment、PDF 解鎖、statement parser、入帳流程，或宣稱相關流程正式可用，必須依 `IMPLEMENTATION_PLAN.md` 的 `E2E-GMAIL-3BANK` 流程，用三家不同銀行的真實新下載帳單完成隔離驗收。

- 三家都 PASS 才能宣稱該 E2E gate 通過。
- 不以舊紀錄、快取附件、合成 PDF 或只抽文字取代真實驗收。
- 測試不得自動 confirm 正式入帳、不得寫 SecretStore、不得啟用付費 AI fallback。
- 若只是純文件修改，無需虛構程式或 E2E 驗證。

## Completion

- 更新與實際行為直接相關的文件。
- `HANDOFF.md` 記錄當前可驗證狀態、剩餘限制與下一步。
- 不把暫時執行紀錄、日期、port、版本數字或測試統計堆回本 `AGENTS.md`。
