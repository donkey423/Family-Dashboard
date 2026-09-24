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

### 密碼保護 PDF

Password-protected PDF processor 可以對 memory/temporary bytes 解密與解析，不要求永久落地。PDF 密碼、OAuth token、refresh token 與其他 secret 不得存入一般 SQLite table、log、repository 或明文設定檔；Windows 整合採 Credential Manager/SecretStore。

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
- 未來秘密使用 Windows Credential Manager/SecretStore，不存 SQLite 或 repository 設定檔。
