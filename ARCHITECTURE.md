# 家庭收支記錄架構

## 近期交付範圍

近期產品目標為信用卡 PDF 解鎖、解析與核對後寫入 SQLite，產生每月支出 Excel；Web 補設定、核對確認及例外處理。完整 Dashboard、新家庭模組及新同步引擎不是前置。既有 Documents/Sources、SecretStore、去重、撤銷及 Excel 安全輸出仍保留。

以下記錄現有架構與邊界；後續擴充點不等於已排定待辦。工作及驗收以 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 為準；目前已驗證中國信託/國泰世華/永豐文字版型及受限台新零交易，未知版型與第二期仍需授權樣本。

Statement 保留 `closing_date` 與來源 transaction date。僅依使用者批准，未列日期的 interest 可由共用 resolver 按明示結帳日認列；正規化與月彙總一致，API/raw_json 保留來源缺日期、有效日期及 date basis。此政策不屬於銀行 regex，不補普通消費/費用/繳款，也不繞過核對閘門；舊 JSON 沒有 closing_date 仍向後相容。

## 執行拓樸

```text
Windows 主機
  React/Vite Web UI  ->  FastAPI Modular Monolith  ->  SQLite + Alembic
                                                ->  Local filesystem adapter
Codex 排程 + Gmail MCP  ----------------------->  Codex MCP import API
MacBook / iPhone  -- Tailscale private network --> Windows 主機
```

開發與此主機正式服務均綁定 loopback，透過 Tailscale Serve 私有 HTTPS 提供同源 Web／API，不需 `0.0.0.0`。僅直接存取 Tailscale IP 的替代部署才需另設定監聽介面與防火牆。

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

### 文件匯入生命週期

- `Document.revoked_at` 為撤銷狀態的單一來源，`revocation_reason` 保存原因；`lifecycle_version` 用於避免預覽後的過期操作。既有文件升級後均為有效狀態。
- 撤銷以 logical `document_id` 為範圍，涵蓋其全部來源與 `source_document_id` 關聯交易，不依檔名、日期或金額猜測。不同文件即使同名也不受影響。
- `DocumentLifecycleUseCase` 協調 Documents 狀態與 Jobs 稽核，擁有同一筆 DB transaction。Finance 提供影響查詢；交易本身不刪除或複製，Dashboard、交易列表及 Search 共用 `active_transaction_filter` 排除已撤銷來源。
- `GET /api/documents/{id}/import-impact` 回傳筆數、各幣別金額與包含版本／影響摘要的 `impact_token`。`POST .../revoke` 和 `POST .../restore` 需附 token；影響已變更回應 409，要求重新預覽。同狀態重複操作回應 `changed=false`，不新增稽核紀錄。
- `GET /api/documents` 預設只列有效文件，`state=revoked` 或 `state=all` 用於恢復清單。原始文件讀取、PDF 預覽和保存副本仍可使用；不改變來源本身的可用性。
- 手動 CSV 與 Codex MCP Gmail 匯入在解析前檢查撤銷狀態。保留 SHA-256 和 source records 作為防重匯依據，新 source 若同 hash 仍略過交易匯入；不默默恢復。匯入 API 回報 `skipped_revoked`，不把這種情況當失敗或新匯入。
- 恢復只啟用既有交易，不重新解析。未來新增 domain 時，需在自己的查詢中遵守文件有效狀態，並於 lifecycle use case 中整合本模組的影響預覽；不可跨模組直接刪表或資料列。
- 永久清除文件及移除本機副本是不同操作，目前尚未提供。不同 bytes 的語意重複帳單、單筆交易撤銷和跨文件合併亦不在本次範圍。

## v0.1 模組

- Documents：共用文件身分、SHA-256、metadata 與 1:N `DocumentSourceRecord` 關聯。v0.1 上傳內容經 StoragePort 本地持久化並建立可用的本機來源記錄；未來 remote source 可與本機副本並存。
- Finance：CSV 解析、交易資料及來源文件關聯；v0.1 CSV 必須先由 Documents 接收。
- Jobs：匯入作業狀態、來源與可供 UI 顯示的錯誤摘要。
- Search：跨文件 metadata 與 Finance 交易的查詢服務。
- Dashboard：以 Finance 查詢服務提供統計資料。
- Exports：把已提交的 Documents/Finance 快照投影成可重建的專用 Excel；不擁有交易資料，也不反向讀取 Excel 更新 domain。

SQLAlchemy 持久化 model 集中在 infrastructure/schema 邊界，由各 domain service 擁有其資料操作。Application use case 協調跨模組工作並擁有 transaction boundary；底層 service 不可 commit 整個 use case。Alembic migration 是資料庫 schema 變更的正式路徑。

## Finance 分類邊界

`finance/categories/domain.py` 定義純 merchant normalization／EffectiveCategory resolver；`service.py` 是批次資料存取與月／幣別彙總，`api.py` 為 HTTP adapter。銀行 parser 不做商家分類，分類不能改交易事實。

`0012_transaction_categories` 新增 `finance_categories`、`finance_category_rules`、`transaction_category_overrides`；不在 FinanceTransaction 增加分類欄。M13 優先序為單筆 override > 使用者 normalized exact > 使用者 contains（priority／長度／穩定 ID）> system semantic > 內建明確規則 > 未分類，停用類別安全 fallback。`builtin.py` 只對完整匹配的明確描述分類，多用途商家／支付平台不猜用途；`FAMILY_FINANCE_HUB_BUILTIN_CATEGORY_RULES=false` 可停用。SQLite foreign_keys 開啟，Category／transaction references 由 FK 保護；停用不刪既有引用。

每個查詢批次載入 categories、rules、overrides，不逐筆查 DB。API 依有效文件、日期／幣別和既有 consumption expression 選交易，再解析分類與商家；分類篩選在分頁之前。退款有符號沖抵，payment 不進消費；分類總額與 Dashboard expense 一致。V1 仍於記憶體解析選定交易；萬筆規模冷啟動 API 尚有優化空間，不新增快取平台。

`0013_category_taxonomy` 在隔離環境新增 books／insurance，只改仍為舊預設值的顯示名稱及排序；保留自訂名稱、ID、引用與交易事實。降級保留已有引用或自訂的新類別，不破壞人工資料。

單筆操作預設 transaction scope；merchant scope 先以 `GET /api/finance/transactions/{id}/category-impact` 預覽跨月影響，確認帶 token。批次 `POST /api/finance/transactions/category-batch/preview` 與 `PATCH /api/finance/transactions/category-batch` 最多 50 筆，於同一 SQLite `BEGIN IMMEDIATE` transaction 重算 token 後原子更新；人工 override（含停用類別）受保護，過期、撤銷、途中失敗拒絕或回滾整批，不建立商家規則。

Web／Excel 共用 CategorizationService；分類名稱／規則／override、內建規則版本／內容 hash／啟用狀態也進入 snapshot fingerprint，不只有 amount/date 變更才刷新輸出。Excel ownership／hash／sanitizer／原子替換保持原邊界。React chart 與 drill-down 分離、Recharts lazy load，Top-N 百分比使用整數 cents 分配，負／零淨額不畫 slice。

正在執行的正式 M12 服務／DB 仍為 0012，3000／私有 HTTPS 443、18 筆交易及原正式 dist／Excel 保留；repository 開發 head 已是 0013，不能直接重啟到舊 schema。M13 使用獨立 0013 合成 DB、3002／8032／HTTPS 8444，18 筆合成資料，secrets／Excel 關閉。舊 M12 預覽 3001／8030／8443 的來源已撤銷，有效 0 筆，不自行恢復。後續正式升級須當次授權、成對備份、副本 migration／回退、同步 build 與正常登入帳戶啟動；測試腳本不得靜默升級正式 DB。Donut 最多六片、正額未分類獨立保留，負淨額另列。

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
DocumentSource ------+---------------- Codex MCP Gmail (local persisted)
                     |
                     +---------------- Legacy Gmail remote reference
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

`DocumentSource` 負責「如何取得 bytes」；`DocumentProcessor` 負責「如何理解 bytes」。目前有來源 registry、本機/Codex MCP/legacy Gmail adapter、CSV/PDF processor、OCR port/Tesseract adapter、受限密碼規則與上述已驗證銀行 parser。兩者保持分離，Finance 不直接依賴 Gmail、filesystem、PDF library 或 OCR provider。

### Codex MCP Gmail attachment 流程

```text
Codex scheduled task + Gmail MCP
 -> search for eligible statement PDF messages
 -> obtain attachment bytes and nearby password wording
 -> POST local multipart import endpoint
 -> validate size and sanitize/mask password instruction
 -> compute SHA-256; persist through StoragePort
 -> create/reuse logical Document + codex_mcp_gmail source
 -> leave statement analysis/confirmation to the existing safe workflow
```

網站不管理 Gmail 帳戶授權、郵件查詢或排程；這三項由 Codex Gmail MCP 與 Codex 自動化負責。`POST /api/integrations/codex-mcp/gmail/import` 是唯一新收件入口。附件會永久寫入 Windows storage，讓後續預覽、解鎖、重跑與備份不依賴 Gmail 連線。

SQLite 只保存必要 metadata：

- `source_type=codex_mcp_gmail`
- filename、SHA-256 與 local storage key
- 由 Gmail message ID + attachment ID 計算的不可逆 source key
- 已遮罩及截斷的密碼規則提示（若可辨識）

不保存原始 Gmail message/attachment ID、subject、sender、完整郵件本文或實際密碼。同一來源重跑會重用 source record；同一來源 key 對應不同內容時回 409，避免來源漂移被靜默覆寫。相同 SHA-256 亦重用既有 Document，已撤銷文件不會因重新收件而自動恢復。

### Codex Trigger 與處理邊界

Codex trigger 只負責 Gmail 搜尋、取得附件及呼叫本機匯入 API。FamilyHub 仍擁有內容去重、文件生命週期、PDF 解鎖、Statement parser、核對、Finance 寫入及 Excel 投影；自動化 prompt 不得複製或繞過這些規則。

```text
Codex cron
 -> Gmail MCP read-only search/download
 -> FamilyHub CodexMcpGmailImportUseCase
 -> Documents + StoragePort + Jobs
 -> PDF preview / Statement analysis
 -> explicit user confirmation
 -> Finance -> Excel
```

網站內建的 OAuth UI/API 與 Gmail scheduler 預設停用；舊端點回 410。`FAMILY_FINANCE_HUB_LEGACY_GMAIL_OAUTH=true` 只提供歷史資料相容／測試，不是日常部署選項。舊 `GmailSyncUseCase`、History schema 與 remote source adapter 暫不做破壞性 migration，避免現有來源失讀；待歷史 remote-only 文件已保存本機副本後，才另案評估移除依賴。

Codex 自動化的搜尋窗口與頻率屬外部任務設定，不寫進 FamilyHub DB。無新信時保持安靜；附件重複由本機 source key 與 SHA-256 共同去重。Codex、Windows 主機或 FamilyHub 服務未執行時不會收件，下次執行可重掃近期窗口補回，不能把排程建立等同於已完成跨日真實驗收。

### Excel 投影與重建

```text
Documents + Finance committed state
              |
              v
      WorkbookExportService
       (full snapshot/hash)
              |
              v
        WorkbookWriter port
              |
              v
 Windows local .xlsx adapter
```

Excel 是輸出投影，不是資料來源。`WorkbookExportService` 只讀取已提交資料，並複用 Finance 的有效文件條件排除已撤銷帳單；writer 在 DB session/transaction 結束後寫入同目錄 temporary file，再以原子替換更新目標。成功替換並計算輸出 SHA-256 後才更新 `WorkbookExportState` 與完成 Job；失敗不會前移快照指紋，也不會破壞上一版。

輸出檔含應用程式 ownership marker。既有無標記工作簿、symlink 或格式異常檔案不會被覆蓋。狀態同時保存輸入快照 hash 與輸出檔 SHA-256；目標消失、被外部修改或與目前 SQLite 快照不一致時，下載端點回報尚待更新。背景 worker 為 opt-in，每 30 秒檢查；啟動後立即檢查一次，檔案被 Excel 佔用時保留舊檔並重試。

目前投影包括月份／幣別摘要、所有有效交易與文件狀態。零交易 PDF 只顯示為待處理，不會觸發猜測解析；未來銀行 parser 必須先寫回 Finance transaction，再由同一投影自然進入 Excel。

### 查看原始帳單

```text
Browser requests original document
 -> Backend resolves Document source
 -> Codex MCP source reads local persisted bytes through StoragePort
 -> Backend streams bytes with correct media type
 -> Browser PDF viewer displays content
```

新匯入不依賴 Gmail 即時可用性。歷史 legacy remote-only document 仍可能因 Gmail 暫時不可用、授權失效或原始信件遭刪除而無法取得；UI 應清楚顯示來源狀態，且不把 legacy 來源失效解讀成已刪除 Document。

### 密碼保護 PDF 與密碼規則解析

Password-protected PDF processor 對 StoragePort 讀出的 bytes 在記憶體中解密與解析，不保存明文副本。PDF 密碼、legacy OAuth token、身分證字號、生日與其他 secret 不得存入一般 SQLite table、log、repository 或明文設定檔；Windows 整合採 Credential Manager/SecretStore。

密碼流程採「**先確認來源郵件的明確格式；AI 只理解其餘規則；敏感資料只在本機組合**」：

```text
Codex 提供的郵件規則片段 + attachment filename
                    |
                    v
        PasswordInstructionExtractor
                    |
                    v
      explicit local rule or known
          verified PasswordRule?
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

密碼規則優先從 Codex MCP 提供的來源郵件規則片段、附件檔名與未加密可讀 metadata 取得。若規則文字只存在於「必須先解密才能看到」的 PDF 頁面，系統無法靠該 PDF 自己推導密碼，必須改用郵件說明或人工補充。

Codex 只把密碼關鍵字附近的必要文字交給 import endpoint；Backend 立即經 `PasswordInstructionExtractor` 遮罩、截斷並保存受限提示，subject、sender、完整本文與 Gmail 原始 ID 不落盤。`codex_mcp_gmail` 文件預覽只使用這份來源提示，不允許表單覆蓋；一般本機上傳才可由使用者輸入不含實際密碼的說明。歷史 legacy Gmail source 仍沿用既有即時讀取相容路徑。

遮罩後的提示若明確表示「完整身分證字號」及英文字母大小寫，`ExplicitPasswordRuleParser` 會在本機產生單一受限 DSL 規則，不需要 AI。若同一提示明確區分本國籍使用完整身分證、外籍使用西元生日 `YYYYMMDD`，parser 會產生且只產生這兩個候選，依提示順序交給 PDF processor，成功後只保存實際命中的單一規則。只說「請輸入密碼」、只說大小寫、要求證號局部或多欄位組合時，不會被這條快速路徑猜測；改用已成功驗證的規則，或在允許時交給 AI 解讀。所有明確候選仍無法解鎖時直接回報密碼不符，不擴張其他排列。

#### PasswordRuleInterpreter

只有本機明確規則與已驗證 cache 都無法決定格式時，AI 才接收遮罩後的「密碼說明文字」及必要的非敏感 context；預設個人解鎖流程只傳文件類型。**不得把真實身分證字號、生日、PDF 密碼或完整帳單內容送給 AI 來算密碼**。AI 輸出受 schema 約束的 `PasswordRule`，不輸出可執行 Python/JavaScript，也不可由系統對 AI 回傳內容使用 `eval`。設定 AI key 後，開啟加密 PDF 的預覽會自動允許此分析；使用者可在預覽視窗關閉後重試。

PasswordRule DSL 第一版只允許白名單操作，例如：

- source：`national_id`、`birthday`
- transform：`full`、`prefix`、`suffix`、`substring`、`upper`、`lower`、`date_format`
- birthday format：`YYYYMMDD`、`YYMMDD`、`MMDD`、`DDMM`，並預留台灣民國年格式
- separator：空字串或明確允許的少數分隔符

若說明不充分，AI 必須回傳 ambiguous/multiple-candidates，而不是自行大量猜測。系統只允許少量 deterministic candidates，預設最多 3 個；不得把此功能做成 brute-force engine。

成功開啟 PDF 後，預設個人解鎖流程保存與遮罩提示指紋關聯的已驗證 PasswordRule；多個明確候選只保存成功的候選，之後優先重用。提示改變或規則失效時才重新判斷，不要求使用者建立銀行、機構、寄件者或家庭成員設定。舊的明確指定 profile/sender 匹配 API 保留相容性。

#### SecretStore / PasswordComposer

`SecretStore` 是獨立 port，已由 Windows `keyring`/Credential Manager adapter 實作，且會拒絕不安全或 Null backend。新 UI 只保存個人身分證字號及/或生日；內部建立固定的個人 SecretProfile/DocumentSecurityProfile，沿用既有 schema，但不要求輸入銀行或成員。SQLite 只保存不透明 `credential_ref` 與非秘密 metadata；不得保存實際身分證字號、生日或組合後密碼。`GET /api/security/personal-unlock` 只回傳兩項是否已保存，不回傳原值。舊 profile API 保留供既有資料相容。

`PasswordComposer` 是 deterministic 本機程式，只接受已驗證 PasswordRule 與 SecretStore 取出的值；只用規則實際需要且已保存的欄位，輸出短生命週期 candidate password。candidate 不寫入 DB、log、Job summary 或一般 exception message。

#### PDF processor 邊界

目前 `DocumentProcessor.process(request: ProcessingRequest)` 已使用 `ProcessingContext` 傳遞 filename、content type、document security profile ID 與非秘密 metadata。`PasswordAwarePdfProcessor` 另接受只在本機記憶體存在的 `password_candidates`；共用 `PdfPreviewUseCase` 預設使用內部個人 profile，協調來源、SecretStore、規則與處理器，不把秘密放進 context、DB、log 或 API response。後續 Statement 入帳沿用此 application 流程，不再建立第二套解鎖流程。

第一版 PDF stack 以 `pypdf[crypto]` 處理 encryption detection、in-memory decrypt 與 text extraction；只有真實銀行 PDF 驗證出現相容性問題時才增加 pikepdf/qpdf fallback。OCR 只在成功解密後且文字抽取不足時啟用，不對所有 PDF 預設執行。通用 `OcrProvider` port 目前有本機 Tesseract adapter，以 PDFium 記憶體渲染並透過 stdin 傳送頁面影像；每份文件最多 20 頁、每頁最多約 8 百萬像素，總逾時 120 秒。Tesseract executable 及 `chi_tra`/`eng` traineddata 需在 Windows 主機另行安裝；無引擎或 OCR 失敗不阻止 PDF 預覽。

#### 錯誤與 UI 語意

底層例外需轉為明確 domain error/error code，例如：`pdf_password_required`、`pdf_wrong_password`、`pdf_unsupported_encryption`、`pdf_malformed`、`pdf_processing_limit`。`X-FamilyHub-Text-Extraction` 只回報 `available`、`completed`、`partial`、`insufficient`、`unavailable` 或 `failed`，不包含抽取文字或底層例外。Job/UI 不直接顯示或持久化可能含敏感內容的底層 exception。

原始文件與解密預覽需區分語意：

- `/content`：原始 provider bytes；若來源本身是加密 PDF，仍維持加密。
- `/preview`：必要時由後端 transient decrypt 後回傳供檢視，使用 `Cache-Control: private, no-store`，不永久保存 decrypted copy。

## 擴充介面

儲存透過 `StoragePort` 隔離，v0.1 adapter 為本機檔案系統。外部內容取得透過 Codex MCP import boundary／`DocumentSource` 隔離；內容理解透過 `DocumentProcessor`/`OcrProvider` 隔離。Codex MCP Gmail source、受限密碼規則 AI boundary、password-protected PDF processor 與本機 OCR adapter 已有實作；legacy Gmail OAuth/source 預設停用。Google Drive、通用 AIProvider 及各家庭領域模組仍為後續擴充，不讓核心依賴供應商 SDK。

Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property 等 domain 僅於需要時新增模組與 migration。

## 一致性原則

跨 Documents、Finance、Jobs 的 use case 由 application/use-case 層擁有 transaction boundary；較底層的 document/source/processor service 不自行決定整個 use case 的 commit 時機。v0.1 文件匯入與 Finance CSV 匯入已依此原則調整。

## 安全與限制

- 不記錄郵件全文、Gmail 原始 ID、PDF 密碼、legacy OAuth token、secret 或完整敏感欄位；一般操作 log 僅可包含 job/document ID、provider 類型與狀態。
- Transient attachment bytes 不應寫入一般 log、crash dump 或永久 temporary directory；若處理 library 必須使用 temporary file，應使用受控位置並在處理完成後可靠刪除。
- SQLite、local storage 和備份均視為家庭敏感資料，需保留在受控 Windows 使用者目錄並納入備份。
- Remote-only document 的可用性依賴外部 provider；metadata 與已解析的 normalized data 可保留，但原始內容不保證永久可重新取得。
- v0.1 尚無多使用者授權；部署於 Tailscale 私有網路並限可信家庭裝置。
- 遠端使用的非 loopback 綁定須搭配 Windows 防火牆僅允許 Tailscale 介面/網段。不可公開埠至 Internet。
- SecretStore 是 M5.2 的必要基礎，不再視為延後項目；Windows 使用 Credential Manager/相容 keyring backend，不存 SQLite 或 repository 設定檔。
- AI 不接收真實身分證字號、生日、PDF 密碼或其他可直接組合出秘密的家庭敏感資料；AI 僅解析密碼規則文字並輸出受限 DSL。
- Password candidate 僅在本機記憶體短暫存在，不寫入 DB、log、Job summary、analytics 或一般 exception。
