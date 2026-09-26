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

#### M5.2c Password Rule pipeline

- [x] 建立 `PasswordInstructionExtractor`，優先從 Gmail subject/body、sender、attachment filename 與 readable metadata 擷取密碼規則說明並遮罩個資/密碼
- [x] 定義 versioned `PasswordRule` schema/DSL；只允許白名單 source/transform/date-format/separator
- [x] 建立 `PasswordRuleInterpreter` AI boundary；AI 只接收規則文字與必要非敏感 context，不接收真實身分證字號、生日或實際密碼
- [x] AI 回傳 ambiguous/multiple-candidates 時不得自行大量排列組合；預設最多產生 3 個 deterministic candidates
- [x] 建立本機 `PasswordComposer`，由 PasswordRule + SecretStore 組合 candidate；candidate 不可進 DB/log/Job summary
- [x] 已成功驗證的 bank/sender/document pattern + PasswordRule 可持久化重用；只有規則缺失、改變或失效時才重新呼叫 AI
- [x] 支援常見生日格式及台灣民國年格式，但必須由 PasswordRule 明確指定，不以 brute force 猜測

#### M5.2d PDF processor

- [x] 擴充 `DocumentProcessor` request/context，context 傳遞 filename/content type/profile 等非秘密資料
- [x] 採 `pypdf[crypto]`：encryption detection、in-memory decrypt、text extraction
- [x] 僅使用一套 PDF dependency；尚無真實帳單相容性證據要求 fallback
- [x] OCR 僅在成功解密且 text extraction 不足時啟動；以 optional PDFium + Tesseract adapter，假 provider 測試觸發條件及記憶體資料流
- [x] OCR 啟動前檢查設定所需 traineddata；缺少語言時提早回報，保留 PDF 預覽並以合成測試驗證
- [x] 定義 domain errors：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_processing_limit`；抽取狀態以 response header 回報，不回傳文件文字
- [x] `/content` 保持原始 bytes；另提供 transient decrypted `/preview`，回應使用 `Cache-Control: private, no-store`

#### M5.2e Gmail source 與手動同步

- [x] 實作 Gmail OAuth 與安全 token storage；程式採 Gmail read-only scope，client JSON/token 僅存 SecretStore
- [x] 建立單一 `GmailSyncUseCase`，讓所有 trigger 共用同一條同步流程
- [x] 提供「立即同步 Gmail」手動 trigger，不先做 scheduler
- [x] 以 Gmail message ID + attachment part/ID 保存 remote source reference，不預設永久下載附件
- [x] Gmail attachment 以記憶體解析，不落一般 temporary directory
- [x] 支援「查看原始帳單」：Backend 即時 fetch Gmail attachment 並回傳原始 bytes
- [x] 支援「保存到家庭文件匣」：使用者明確選擇後新增 local source，不覆寫 Gmail source
- [x] 定義 Gmail 授權失效或 attachment 不可取得時的 UI/API error handling
- [ ] 以真實台灣信用卡帳單驗證第一個 bank/card parser，再決定 bank-specific adapter interface
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
- [ ] 使用中的家庭資料庫備份、升級與實際帳單驗收（本次未操作）

## 延後項目

- [x] 通用 OCR provider port、本機 Tesseract adapter 與語言資料預檢（真實 Windows OCR runtime 仍待安裝/驗收）
- [ ] 非密碼規則用途的通用 AIProvider
- [ ] Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property
- [ ] Google Drive 或其他 DocumentSource provider
- [ ] Tailscale 家庭裝置連線及 Windows 防火牆實機檢查
- [x] 以隔離合成資料完成 SQLite + 文件儲存的備份/還原演練測試；未操作使用中資料

## 尚待外部條件

- Google Cloud Gmail API / OAuth 桌面用戶端設定與真實帳戶授權尚未執行；本機 UI 已提供設定及授權流程。
- Windows 主機尚未確認 Tesseract 執行檔及 `chi_tra`/`eng` 語言資料；OCR pipeline 以合成 provider 完成測試，真實辨識待安裝 runtime 後驗收。
- 尚無真實信用卡帳單樣本完成銀行專用 PDF 交易解析、密碼規則與金額核對；目前 Gmail CSV 可用通用解析器，PDF 可原始查看/解密預覽及抽取文字，不會臆測 PDF 交易。
- Gmail 定時同步程式已完成，但預設關閉；只有完成唯讀授權並由使用者開啟後才會每 30 分鐘同步 CSV 與收錄 PDF 文件。真實帳單 PDF 交易解析仍須另行驗收，不能由 scheduler 取代。
