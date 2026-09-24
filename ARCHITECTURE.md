# 家庭收支記錄架構

## 執行拓樸

```text
Windows 主機
  React/Vite Web UI  ->  FastAPI Modular Monolith  ->  SQLite + Alembic
                                                ->  Local filesystem adapter
                                                ->  Future external source adapters
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

Document metadata 以來源類型及 optional provider reference 描述內容來源；`storage_key` 僅供本機持久化來源使用，不假設每筆 Document 都有可直接讀取的 local storage key。

目前 schema 暫時把 `source_type/source_reference/storage_key` 放在 `documents` 上，因此一份 Document 同時只能表示一個主要來源。M5.2 在接 Gmail 前應先評估並優先調整為 **Document 1:N DocumentSourceRecord**，使同一份內容可以同時保留 Gmail remote reference 與使用者後續選擇的 local persisted source，而不需要覆寫來源身分。

## v0.1 模組

- Documents：共用文件身分、SHA-256、metadata 與來源關聯。v0.1 上傳內容經 StoragePort 本地持久化；`storage_key` 可空，來源由 `source_type` 與 optional source reference 描述。
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
 -> record source_type=local_file and create import job
 -> DocumentSourceRegistry reads imported bytes through LocalFileDocumentSource
 -> CsvDocumentProcessor parses CSV structure; Finance maps normalized values
 -> row hash (source document + row index + normalized row) prevents re-import duplicates
 -> persist transactions linked to source document and commit the use case
```

檔案儲存使用 content-addressed 相對路徑，先寫暫存檔再原子替換。雜湊唯一索引負責資料完整性；新增文件遇到 SHA-256 唯一索引競爭時，使用 savepoint 回復並重用已建立的文件。交易 row hash 含來源文件及列序，因此相同 CSV 重送不重複匯入，同一檔案內內容相同但列序不同的兩筆交易仍可保留。SQLite engine 明確發出 `BEGIN`，確保 savepoint 不會意外提交外層 use case。

## 下一階段：DocumentSource / DocumentProcessor

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

`DocumentSource` 負責「如何取得 bytes」；`DocumentProcessor` 負責「如何理解 bytes」。目前已實作來源 registry 與本機檔案 adapter，以及 CSV processor；PDF/Image/OCR/password-protected PDF processor 與 Gmail source 尚未實作。兩者必須分離，避免 Finance 或其他 domain 直接依賴 Gmail、filesystem、PDF library 或 OCR provider。

### Gmail attachment 流程

```text
Gmail query
 -> identify message + attachment
 -> save/update Document source reference
 -> fetch attachment bytes on demand
 -> keep bytes in memory or controlled temporary buffer
 -> compute/verify SHA-256
 -> run PDF/CSV processor
 -> persist normalized Finance data + source relationship
 -> discard transient bytes
```

預設不將 Gmail attachment 永久寫入 Windows storage。SQLite 只保存必要的 source reference 與 metadata，例如：

- provider/source type
- Gmail message ID
- Gmail attachment ID
- filename
- sender
- received_at
- SHA-256
- parsed_at
- optional local persistence state

若使用者選擇「保存到家庭文件匣」，application service 才將該 attachment 寫入 `StoragePort`，並更新 Document 的本地持久化狀態。

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

1. **Manual sync first**：先由 UI/API 手動觸發，完整驗證 Gmail query、remote reference、attachment bytes、processor、去重與 Finance persistence。
2. **Incremental sync second**：保存 Gmail sync cursor/state，只處理上次成功同步後的新變更；若 state 過期則受控 fallback。
3. **Scheduler third**：前兩步穩定後，才加入預設每 30 分鐘一次的本機 scheduler，呼叫同一個 `GmailSyncUseCase`。
4. **Push optional**：只有產品真的需要近即時更新時，才導入 Gmail Push / Pub/Sub；Push 仍只是一種 trigger。

Windows 關機時 scheduler 不執行，這是 local-first 架構的預期行為。重新開機後由 incremental sync 補抓關機期間的新信，因此不要求主機 24 小時常駐。

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

`SecretStore` 是獨立 port，Windows adapter 使用 Credential Manager/相容 keyring backend。SQLite 只能保存不具秘密內容的 `secret_profile_id` / `credential_ref`，例如家庭成員 profile 識別碼；不得保存實際身分證字號、生日或組合後密碼。

`PasswordComposer` 是 deterministic 本機程式，只接受已驗證 PasswordRule 與 SecretStore 取出的值，輸出短生命週期 candidate password。candidate 不寫入 DB、log、Job summary 或一般 exception message。

#### PDF processor 邊界

目前 `DocumentProcessor.process(content: bytes)` 對加密 PDF 不足。實作 PDF 前應加入 processing request/context，至少能傳遞 filename、content type、document/bank profile 與 `credential_ref` 等非秘密 reference；不要把 plaintext password 當成通用 processor 參數四處傳遞。

第一版 PDF stack 以 `pypdf[crypto]` 處理 encryption detection、in-memory decrypt 與 text extraction；只有真實銀行 PDF 驗證出現相容性問題時才增加 pikepdf/qpdf fallback。OCR 只在成功解密後且文字抽取不足時啟用，不對所有 PDF 預設執行。

#### 錯誤與 UI 語意

底層例外需轉為明確 domain error/error code，例如：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_ocr_required`。Job/UI 不直接顯示或持久化可能含敏感內容的底層 exception。

原始文件與解密預覽需區分語意：

- `/content`：原始 provider bytes；若來源本身是加密 PDF，仍維持加密。
- `/preview`：必要時由後端 transient decrypt 後回傳供檢視，使用 `Cache-Control: private, no-store`，不永久保存 decrypted copy。

## 擴充介面

儲存透過 `StoragePort` 隔離，v0.1 adapter 為本機檔案系統。外部內容取得透過 `DocumentSource` 隔離；內容理解透過 `DocumentProcessor` 隔離。未來可接 Gmail、Google Drive、密碼保護 PDF、OCR 與 `AIProvider`，不讓核心依賴供應商 SDK。

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
