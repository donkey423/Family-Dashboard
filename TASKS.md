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

### M5.1 基礎架構

- [x] 調整 Documents model，使 logical document identity 不要求每筆都有 local storage key
- [x] 定義 `DocumentSource` port 與 registry，v0.1 local source 透過來源邊界讀取 bytes
- [x] 定義 `DocumentProcessor` port 並將 v0.1 CSV 結構解析移至 CSV processor adapter；PDF / Image / password-protected PDF / OCR 實作仍延後
- [x] 將 Documents + Finance + Jobs 的 transaction ownership 上移至 application/use-case 層
- [x] 補齊 SHA-256 併發重複匯入的 IntegrityError recovery 與測試
- [x] 新增 Alembic migration，保留既有本機文件及其關聯

### M5.2 Gmail 手動同步與加密 PDF 先跑通

#### M5.2a 文件來源模型補強

- [ ] 在接 Gmail 前評估並優先把 Document source 從目前 1:1 欄位模型調整為 Document 1:N source records，使 Gmail remote source 與 local persisted source 可同時存在
- [ ] 補 migration 與相容性測試，保留既有 `0002_document_sources` 資料
- [ ] 定義 source availability / last verified 等必要狀態，避免 provider 消失時誤判為 Document 消失

#### M5.2b SecretStore 與家庭秘密資料

- [ ] 定義 `SecretStore` port，Windows 實作使用 Credential Manager/相容 keyring backend
- [ ] 身分證字號、生日、PDF 密碼、OAuth token/refresh token 不得存一般 SQLite、log、repo 或 plaintext config
- [ ] SQLite 僅保存 `secret_profile_id` / `credential_ref` 等非秘密 reference
- [ ] 建立家庭成員 secret profile，可讓銀行/卡別 profile 指向正確持有人，但不要把秘密資料複製進 document metadata

#### M5.2c Password Rule pipeline

- [ ] 建立 `PasswordInstructionExtractor`，優先從 Gmail subject/body、sender、attachment filename 與 readable metadata 擷取密碼規則說明
- [ ] 定義 versioned `PasswordRule` schema/DSL；只允許白名單 source/transform/date-format/separator
- [ ] 建立 `PasswordRuleInterpreter` AI boundary；AI 只接收規則文字與必要非敏感 context，不接收真實身分證字號、生日或實際密碼
- [ ] AI 回傳 ambiguous/multiple-candidates 時不得自行大量排列組合；預設最多產生 3 個 deterministic candidates
- [ ] 建立本機 `PasswordComposer`，由 PasswordRule + SecretStore 組合 candidate；candidate 不可進 DB/log/Job summary
- [ ] 已成功驗證的 bank/sender/document pattern + PasswordRule 可持久化重用；只有規則缺失、改變或失效時才重新呼叫 AI
- [ ] 支援常見生日格式及台灣民國年格式，但必須由 PasswordRule 明確指定，不以 brute force 猜測

#### M5.2d PDF processor

- [ ] 在實作 PDF 前擴充 `DocumentProcessor` request/context，不再只接受 `bytes`；context 傳遞 filename/content type/profile/`credential_ref` 等非秘密 reference
- [ ] 第一版採 `pypdf[crypto]`：encryption detection、in-memory decrypt、text extraction
- [ ] 只有真實帳單相容性失敗時才加入 pikepdf/qpdf fallback，不先增加多套 PDF dependency
- [ ] OCR 僅在成功解密且 text extraction 不足時啟動
- [ ] 定義 domain errors：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_ocr_required`
- [ ] `/content` 保持原始 bytes；另提供 transient decrypted `/preview`，回應使用 `Cache-Control: private, no-store`

#### M5.2e Gmail source 與手動同步

- [ ] 實作 Gmail source authentication 與安全 token storage
- [ ] 建立單一 `GmailSyncUseCase`，讓所有 trigger 共用同一條同步流程
- [ ] 先提供「立即同步 Gmail」手動 trigger，不先做 scheduler
- [ ] 以 Gmail message ID + attachment ID 保存 remote source reference，不預設永久下載附件
- [ ] Gmail attachment 以 memory/受控 temporary buffer 解析，完成後移除 transient bytes
- [ ] 支援「查看原始帳單」：Backend 即時 fetch Gmail attachment 並 stream 給瀏覽器
- [ ] 支援「保存到家庭文件匣」：使用者明確選擇後新增 local source，不覆寫 Gmail source
- [ ] 定義 Gmail 原始信件被刪除、授權失效或 attachment 不可取得時的 UI/error handling
- [ ] 以真實台灣信用卡帳單驗證第一個 bank/card parser，再決定 bank-specific adapter interface
- [ ] 驗收：連續按「立即同步 Gmail」不會建立重複 Document、Job 或 Finance transaction
- [ ] 驗收：AI 流程的 request/log/DB fixture 中不含真實身分證字號、生日或組合後 PDF 密碼
- [ ] 驗收：同一帳單可同時擁有 Gmail remote source 與使用者保存的 local source

### M5.3 Incremental Sync

- [ ] 保存 Gmail incremental sync state（例如 history ID、last successful sync time）
- [ ] 同步時只處理上次成功同步後的新變更，不每次重掃整個 Gmail
- [ ] history state 過期或失效時可安全 fallback 到受控 full sync
- [ ] UI 顯示最後成功同步時間、同步狀態與錯誤摘要

### M5.4 定時自動同步

- [ ] 在手動同步與 incremental sync 穩定後，再加入 scheduler
- [ ] 預設每 30 分鐘觸發一次同一個 `GmailSyncUseCase`
- [ ] Windows 關機期間不要求背景執行；下次啟動後由 incremental sync 補抓漏掉的信件
- [ ] UI 顯示「下一次同步」並保留「立即同步 Gmail」按鈕
- [ ] scheduler 本身不得包含 Gmail 搜尋、解析或 Finance 業務邏輯，只負責 trigger

### 未來選配：Gmail Push

- [ ] 僅在確實需要「信件到達後數秒內更新」時，再評估 Gmail Push / Pub/Sub
- [ ] Push 仍只觸發既有 `GmailSyncUseCase`，不建立第二套同步流程

## 延後項目

- [ ] 通用 OCR provider 與非密碼規則用途的 AIProvider
- [ ] Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property
- [ ] Google Drive 或其他 DocumentSource provider
- [ ] Tailscale 家庭裝置部署檢查與備份/還原操作演練
