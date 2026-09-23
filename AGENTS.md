# 專案指引

## 專案導覽

- `README.md`：目前功能、環境、啟動和測試命令。
- `PROJECT.md`：產品目標、v0.1 邊界與明確排除項目。
- `ARCHITECTURE.md`：模組邊界、資料流、依賴方向與部署設計。
- `TASKS.md`：目前里程碑與待辦。
- `HANDOFF.md`：當前可驗證狀態、下一步與風險。
- `backend/src/family_finance_hub`：FastAPI、domain services、ports 與 adapters。
- `backend/tests`：後端自動化測試。
- `frontend/src`：React/TypeScript Web UI。

## 邊界與限制

- 保持 Modular Monolith；不引入 microservices、Redis、Kafka、Kubernetes 或 PostgreSQL。
- 所有文件先由 Documents domain 接收。Finance 只能透過文件服務匯入 CSV，並保存來源文件 ID。
- Domain/Application 不直接依賴 Windows filesystem、FastAPI request objects 或供應商 SDK。
- SQLAlchemy/Alembic 是 SQLite schema 持久化路徑；migration 不可由生產程式啟動時靜默取代。
- 不記錄文件內容、secret、token 或完整敏感資料。未來秘密使用 Windows Credential Manager/SecretStore。
- v0.1 只做 Documents、通用 Finance CSV、Dashboard、Search、Jobs/import history 與 tests。
- 新增模組應新增自己的 domain/service/schema migration，避免直接操作其他模組資料。

## 驗證

從 repository 根目錄執行 `python -m pytest backend\tests` 與 `cd frontend; npm run build`。資料庫 schema 變更需另外檢查 `alembic -c backend\alembic.ini upgrade head`。若環境未安裝 Python 或前端依賴，明確回報未執行的驗證，不可宣稱通過。

## 完成標準

- 更新與實際行為相符的文件及 HANDOFF。
- 執行受影響的測試/建置並回報結果。
- 不自動 commit、push、merge、reset，也不覆蓋使用者未提交內容。
