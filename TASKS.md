# 家庭收支記錄里程碑

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
- [x] 匯入解析、重複列與 API 測試

## M4：Web UI 與端到端檢查

- [x] React/TypeScript 操作介面：Dashboard、Documents、匯入、搜尋、Jobs
- [x] API 連線錯誤與空狀態
- [x] frontend production build
- [x] 本機啟動及核心流程檢查

## 延後項目

- [ ] Gmail、密碼保護 PDF、OCR、AIProvider
- [ ] Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property
- [ ] Windows Credential Manager/SecretStore adapter
- [ ] Tailscale 家庭裝置部署檢查與備份/還原操作演練
