# 家庭收支記錄架構

## 執行拓樸

```text
Windows 主機
  React/Vite Web UI  ->  FastAPI Modular Monolith  ->  SQLite + Alembic
                                                ->  Local filesystem adapter
                                                ->  Gmail source adapter + future providers
MacBook / iPhone  -- Tailscale private network --> Windows 主機
```

開發預設只綁定 loopback。遠端使用時，依部署文件設定主機監聽介面與 Windows 防火牆，僅允許 Tailscale 網路。

## 依賴方向

```text
Presentation (React)
        -> HTTP API / Application services
        -> Domain services and domain models
        -> Ports (storage, document source, processor/provider boundaries)
Infrastructure adapters implement ports
```

Domain 不直接依賴 FastAPI、SQLite、Windows 路徑、Gmail SDK 或其他第三方服務。模組之間透過 application service/API 與穩定識別碼互動，不直接修改其他模組資料表。

## Documents 的定位

Documents 是文件的 logical identity、metadata 與來源關聯，不應等同「一定有一份本地實體檔案」。

文件可能有兩種主要生命週期：

1. **Local persisted document**：內容由 `StoragePort` 持久化在 Windows 本機 filesystem。
2. **Remote referenced document**：SQLite 保存可重新取得內容的 source reference；實際 bytes 由對應的 `DocumentSource` adapter 按需取得。

每個 `DocumentSourceRecord` 表示一個來源，包含 `source_type`、provider 內唯一的 `source_key`、optional `source_reference`、optional `storage_key`、availability 狀態及 `last_verified_at`。同一個 Document 可同時具有 Gmail remote source 與本機副本；新增本機副本不會覆寫 remote source。

來源狀態為 `unknown`、`available` 或 `unavailable`。既有資料經 migration 回填為 `unknown`；讀取成功會更新為 `available` 並記錄 `last_verified_at`，已設定的 adapter 讀取失敗則更新為 `unavailable`。來源暫時不可讀不等於 Document 消失；API 回傳來源不可用，而保留 Document 與其 metadata。未設定 adapter 的來源維持原狀，不可據此判定來源已失效。

## v0.1 模組

- Documents：共用文件身分、SHA-256、metadata 與 1:N `DocumentSourceRecord` 關聯。v0.1 上傳內容經 StoragePort 本地持久化並建立可用的本機來源記錄；未來 remote source 可與本機副本並存。
- Finance：CSV 解析、交易資料及來源文件關聯；v0.1 CSV 必須先由 Documents 接收。
- Jobs：匯入作業狀態、來源與可供 UI 顯示的錯誤摘要。
- Search：跨文件 metadata 與 Finance 交易的查詢服務。
- Dashboard：以 Finance 查詢服務提供統計資料。

SQLAlchemy 持久化 model 集中在 infrastructure/schema 邊界，由各 domain service 擁有其資料操作。Application use case 協調跨模組工作並擁有 transaction boundary；底層 service 不可 commit 整個 use case。Alembic migration 是資料庫 schema 變更的正式路徑。

## v0.1 本機匯入流程

```text
HTTP multipart upload
 -> validate extension/size
 -> Documents service computes SHA-256
 -> application use case owns the database transaction
 -> existing hash: reuse document; otherwise StoragePort writes local file
 -> ensure local_file DocumentSourceRecord exists and create import job
 -> DocumentSourceRegistry reads imported bytes through LocalFileDocumentSource
 -> CsvDocumentProcessor parses CSV structure; Finance maps normalized values
 -> row hash (source document + row index + normalized row) prevents re-import duplicates
 -> persist transactions linked to source document and commit the use case
```

檔案儲存使用 content-addressed 相對路徑，先寫暫存檔再原子替換。雜湊唯一索引負責資料完整性；新增文件遇到 SHA-256 唯一索引競爭時，使用 savepoint 回復並重用已建立的文件。交易 row hash 含來源文件及列序，因此相同 CSV 重送不重複匯入，同一檔案內內容相同但列序不同的兩筆交易仍可保留。SQLite engine 明確發出 `BEGIN`，確保 savepoint 不會意外提交外層 use case。

## DocumentSource / DocumentProcessor

```text
                     +---------------- Local File
                     |
DocumentSource ------+---------------- Gmail Attachment
                     |
                     +---------------- Future: Drive / other provider
                                  |
                                  v
                         Document identity/metadata
                                  |
                                  v
                        DocumentProcessor boundary
                          |       |        |
                         PDF     CSV      Image
                          |
                   password-protected PDF
                          |
                         OCR
                                  |
                                  v
                               Finance
```

`DocumentSource` 負責「如何取得 bytes」；`DocumentProcessor` 負責「如何理解 bytes」。目前已實作來源 registry、本機檔案及 Gmail attachment adapters、CSV processor、PDF processor、通用 OCR port/Tesseract adapter 與受限密碼規則流程。真實銀行帳單的專用交易 parser 仍未實作。兩者必須分離，避免 Finance 或其他 domain 直接依賴 Gmail、filesystem、PDF library 或 OCR provider。

### Gmail attachment 流程

```text
Gmail query
 -> identify message + attachment
 -> fetch attachment bytes on demand
 -> keep bytes in memory; enforce size limit
 -> parse CSV or classify PDF
 -> compute/verify SHA-256 and create logical Document/source record
 -> persist normalized CSV Finance rows (PDF remains a Document)
 -> discard transient bytes
```

預設不將 Gmail attachment 永久寫入 Windows storage。SQLite 只保存必要的 source reference 與 metadata：

- provider/source type
- Gmail message ID
- Gmail attachment ID
- filename
- SHA-256
- optional local persistence state

目前不保存 sender、subject 或郵件本文。同步預設搜尋 `in:anywhere has:attachment {filename:pdf filename:csv}`，涵蓋可存取的全部郵件，包含垃圾郵件與封存郵件，不設日期範圍。PDF 附件先以共用 Document 收錄；沒有真實銀行格式 parser 前，不從 PDF 臆測/建立財務交易。

若使用者選擇「保存到家庭文件匣」，application service 才將該 attachment 寫入 `StoragePort`，並為同一 Document 新增本機來源記錄；不覆寫 Gmail remote source。

### Gmail Sync Use Case 與 Trigger

Gmail 同步的業務邏輯集中在單一 `GmailSyncUseCase`。Trigger 只負責「何時執行」，不得自行實作 Gmail 搜尋、附件解析、去重或 Finance 寫入。

```text
               +-- Manual: 立即同步 Gmail
               |
Trigger --------+-- Scheduler: 每 30 分鐘
               |
               +-- Future: Gmail Push / Pub/Sub
                         |
                         v
                  GmailSyncUseCase
                         |
                         v
               Gmail DocumentSource
                         |
                         v
                 DocumentProcessor
                         |
                         v
                  Finance / Jobs
```

實作順序固定為：

1. **Manual sync**：UI/API 可手動觸發；合成 Gmail client 已驗證 query、remote reference、attachment bytes、CSV persistence、重複同步與續跑。
2. **Incremental sync**：保存 Gmail history cursor/state，只處理新加入郵件；若 cursor 過期則受控 full sync，超過每批上限會保存 page token 續跑。
3. **Scheduler third**：已提供本機 opt-in scheduler；設定預設關閉，使用者完成唯讀 OAuth 後可明確啟用，每 30 分鐘呼叫同一個 `GmailSyncUseCase`。手動/排程觸發共用同步鎖；scheduler 不自行實作 Gmail 搜尋、附件解析或 Finance 寫入。真實 PDF 交易解析尚未完成，因此排程只將 PDF 收錄為 Documents，不會建立猜測交易。
4. **Push optional**：只有產品真的需要近即時更新時，才導入 Gmail Push / Pub/Sub；Push 仍只是一種 trigger。

Windows 關機時 scheduler 不執行，這是 local-first 架構的預期行為。重新開機後會補跑已到期的排程，由 incremental sync 補抓關機期間的新信，因此不要求主機 24 小時常駐。OAuth 設定被替換時會自動停用排程，須重新授權並再次明確啟用。

### 即時查看原始帳單

```text
Browser requests original document
 -> Backend resolves Document source
 -> Gmail DocumentSource fetches attachment bytes
 -> Backend streams bytes with correct media type
 -> Browser PDF viewer displays content
 -> no permanent local copy required
```

Gmail 暫時不可用、權限失效或原始信件遭刪除時，remote-only document 可能無法重新取得內容；UI 應清楚顯示 source availability，並允許使用者事前選擇保存本地副本。

### 密碼保護 PDF 與密碼規則解析

Password-protected PDF processor 可以對 memory/temporary bytes 解密與解析，不要求永久落地。PDF 密碼、OAuth token、refresh token、身分證字號、生日與其他 secret 不得存入一般 SQLite table、log、repository 或明文設定檔；Windows 整合採 Credential Manager/SecretStore。

密碼流程採「**AI 只理解規則，敏感資料只在本機組合**」：

```text
Gmail subject/body/sender + attachment filename + readable metadata
                    |
                    v
        PasswordInstructionExtractor
                    |
                    v
       known verified PasswordRule?
             |               |
            yes             no
             |               v
             |      AI PasswordRuleInterpreter
             |      (only instruction text)
             |               |
             +-------+-------+
                     v
           validated PasswordRule DSL
                     |
                     v
                 SecretStore
          +----------+----------+
          |                     |
      national_id             birthday
          |                     |
          +----------+----------+
                     v
             PasswordComposer
                     |
                     v
             1-3 candidates max
                     |
                     v
          PdfDocumentProcessor
           decrypt in memory
                     |
          +----------+----------+
          |                     |
       success                 fail
          |                     |
          v                     v
     extract text        explicit error code
          |
          v
   BankStatementParser
          |
          v
       Finance
```

#### PasswordInstructionExtractor

密碼規則優先從 Gmail subject/body、sender、附件檔名與未加密可讀 metadata 取得。若規則文字只存在於「必須先解密才能看到」的 PDF 頁面，系統無法靠該 PDF 自己推導密碼，必須改用郵件說明、已知 bank profile 或人工補充。

對 Gmail 來源 PDF，只有初次 PDF 處理回報需要密碼時，Backend 才即時取得來源郵件的 subject/from 與純文字/HTML body；不將郵件資料保存至 SQLite。Extractor 遮罩後才交由 AI；本機上傳文件則可由使用者在預覽視窗輸入說明。

#### PasswordRuleInterpreter

AI 只接收「密碼說明文字」及必要的非敏感 context，例如銀行名稱或文件類型；**不得把真實身分證字號、生日、PDF 密碼或完整帳單內容送給 AI 來算密碼**。AI 輸出受 schema 約束的 `PasswordRule`，不輸出可執行 Python/JavaScript，也不可由系統對 AI 回傳內容使用 `eval`。

PasswordRule DSL 第一版只允許白名單操作，例如：

- source：`national_id`、`birthday`
- transform：`full`、`prefix`、`suffix`、`substring`、`upper`、`lower`、`date_format`
- birthday format：`YYYYMMDD`、`YYMMDD`、`MMDD`、`DDMM`，並預留台灣民國年格式
- separator：空字串或明確允許的少數分隔符

若說明不充分，AI 必須回傳 ambiguous/multiple-candidates，而不是自行大量猜測。系統只允許少量 deterministic candidates，預設最多 3 個；不得把此功能做成 brute-force engine。

成功開啟某銀行/卡別後，應保存「已驗證的 PasswordRule 與 bank/sender/document pattern」，之後優先重用；只有規則不存在、已驗證規則失效或說明文字改變時才再次呼叫 AI。

#### SecretStore / PasswordComposer

`SecretStore` 是獨立 port，已由 Windows `keyring`/Credential Manager adapter 實作，且會拒絕不安全或 Null backend。SQLite 的 `secret_profiles` 與 `document_security_profiles` 僅保存不透明 `credential_ref`、顯示名稱與銀行/寄件者關聯；不得保存實際身分證字號、生日或組合後密碼。profile API 不回傳秘密值。

`PasswordComposer` 是 deterministic 本機程式，只接受已驗證 PasswordRule 與 SecretStore 取出的值，輸出短生命週期 candidate password。candidate 不寫入 DB、log、Job summary 或一般 exception message。

#### PDF processor 邊界

目前 `DocumentProcessor.process(content: bytes)` 對加密 PDF 不足。實作 PDF 前應加入 processing request/context，至少能傳遞 filename、content type、document/bank profile 與 `credential_ref` 等非秘密 reference；不要把 plaintext password 當成通用 processor 參數四處傳遞。

第一版 PDF stack 以 `pypdf[crypto]` 處理 encryption detection、in-memory decrypt 與 text extraction；只有真實銀行 PDF 驗證出現相容性問題時才增加 pikepdf/qpdf fallback。OCR 只在成功解密後且文字抽取不足時啟用，不對所有 PDF 預設執行。通用 `OcrProvider` port 目前有本機 Tesseract adapter，以 PDFium 記憶體渲染並透過 stdin 傳送頁面影像；每份文件最多 20 頁、每頁最多約 8 百萬像素，總逾時 120 秒。Tesseract executable 及 `chi_tra`/`eng` traineddata 需在 Windows 主機另行安裝；無引擎或 OCR 失敗不阻止 PDF 預覽。

#### 錯誤與 UI 語意

底層例外需轉為明確 domain error/error code，例如：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_processing_limit`。`X-FamilyHub-Text-Extraction` 只回報 `available`、`completed`、`partial`、`insufficient`、`unavailable` 或 `failed`，不包含抽取文字或底層例外。Job/UI 不直接顯示或持久化可能含敏感內容的底層 exception。

原始文件與解密預覽需區分語意：

- `/content`：原始 provider bytes；若來源本身是加密 PDF，仍維持加密。
- `/preview`：必要時由後端 transient decrypt 後回傳供檢視，使用 `Cache-Control: private, no-store`，不永久保存 decrypted copy。

## 擴充介面

儲存透過 `StoragePort` 隔離，v0.1 adapter 為本機檔案系統。外部內容取得透過 `DocumentSource` 隔離；內容理解透過 `DocumentProcessor`/`OcrProvider` 隔離。Gmail OAuth/source、受限密碼規則 AI boundary、password-protected PDF processor 與本機 OCR adapter 已有實作；Google Drive、通用 AIProvider 及各家庭領域模組仍為後續擴充，不讓核心依賴供應商 SDK。

Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property 等 domain 僅於需要時新增模組與 migration。

## 一致性原則

跨 Documents、Finance、Jobs 的 use case 由 application/use-case 層擁有 transaction boundary；較底層的 document/source/processor service 不自行決定整個 use case 的 commit 時機。v0.1 文件匯入與 Finance CSV 匯入已依此原則調整。

## 安全與限制

- 不記錄文件內容、PDF 密碼、OAuth token、secret 或完整敏感欄位；一般操作 log 僅可包含 job/document ID、provider 類型與狀態。
- Transient attachment bytes 不應寫入一般 log、crash dump 或永久 temporary directory；若處理 library 必須使用 temporary file，應使用受控位置並在處理完成後可靠刪除。
- SQLite、local storage 和備份均視為家庭敏感資料，需保留在受控 Windows 使用者目錄並納入備份。
- Remote-only document 的可用性依賴外部 provider；metadata 與已解析的 normalized data 可保留，但原始內容不保證永久可重新取得。
- v0.1 尚無多使用者授權；部署於 Tailscale 私有網路並限可信家庭裝置。
- 遠端使用的非 loopback 綁定須搭配 Windows 防火牆僅允許 Tailscale 介面/網段。不可公開埠至 Internet。
- SecretStore 是 M5.2 的必要基礎，不再視為延後項目；Windows 使用 Credential Manager/相容 keyring backend，不存 SQLite 或 repository 設定檔。
- AI 不接收真實身分證字號、生日、PDF 密碼或其他可直接組合出秘密的家庭敏感資料；AI 僅解析密碼規則文字並輸出受限 DSL。
- Password candidate 僅在本機記憶體短暫存在，不寫入 DB、log、Job summary、analytics 或一般 exception。
