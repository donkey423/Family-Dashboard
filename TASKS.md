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

## M5：文件來源抽象與 Gmail 帳單

- [ ] 調整 Documents model，使 logical document identity 不要求每筆都有 local storage key
- [ ] 定義 `DocumentSource` port，v0.1 local upload 與未來 Gmail attachment 都透過來源邊界取得 bytes
- [ ] 定義 `DocumentProcessor` port，分離 PDF / CSV / Image / password-protected PDF / OCR 處理
- [ ] 將 Documents + Finance + Jobs 的 transaction ownership 上移至 application/use-case 層
- [ ] 補齊 SHA-256 併發重複匯入的 IntegrityError recovery 與測試
- [ ] 實作 Gmail source authentication 與安全的 token/secret storage
- [ ] 以 Gmail message ID + attachment ID 保存 remote source reference，不預設永久下載附件
- [ ] Gmail attachment 以 memory/受控 temporary buffer 解析，完成後移除 transient bytes
- [ ] 支援「查看原始帳單」：Backend 即時 fetch Gmail attachment 並 stream 給瀏覽器
- [ ] 支援「保存到家庭文件匣」：使用者明確選擇後才將 remote attachment 寫入 StoragePort
- [ ] 定義 Gmail 原始信件被刪除、授權失效或 attachment 不可取得時的 UI/error handling
- [ ] 密碼保護 PDF processor：可在 memory/temporary bytes 解密，不在一般 DB/log/plain config 保存密碼
- [ ] 以真實台灣信用卡帳單驗證第一個 bank/card parser，再決定 bank-specific adapter interface

## 延後項目

- [ ] OCR、AIProvider
- [ ] Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property
- [ ] Google Drive 或其他 DocumentSource provider
- [ ] Windows Credential Manager/SecretStore adapter
- [ ] Tailscale 家庭裝置部署檢查與備份/還原操作演練
