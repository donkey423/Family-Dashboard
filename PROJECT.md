# 家庭收支記錄

## 產品定位

家庭收支記錄是可持續擴充的 local-first 家庭資料平台。它不把核心限制為一次性記帳 App；Finance 是第一個消費共用文件資料的 domain。Windows 家用電腦保存結構化資料與需要本地持久化的原始文件，其他裝置以瀏覽器透過 Tailscale 私有網路存取。

Documents 代表「文件的 logical identity 與來源」，不等同於「一定存在 Windows 硬碟上的本地檔案」。未來文件可以來自本機上傳、Gmail attachment 或其他外部來源；只有需要永久保存的內容才寫入本機 storage。

## v0.1 目標

- 共用 Documents：匯入及瀏覽 PDF、JPG、PNG、CSV，保存 SHA-256、媒體類型、大小、來源關聯與匯入時間；v0.1 上傳文件持久化於本機檔案系統。
- 通用 Finance CSV：將 CSV 先匯入 Documents，再解析日期、描述、金額、幣別與原始欄位，並建立交易至來源文件的關聯。
- Dashboard：顯示交易筆數、收入、支出與淨額。
- Search：搜尋文件名稱、文件類型、交易描述與金額相關文字。
- Jobs / Import history：顯示匯入來源、狀態、結果及錯誤摘要。
- Tests：覆蓋文件雜湊去重、重複匯入冪等性、CSV 解析及 API 基本流程。

## 原始 v0.1 明確不包含

Gmail 連線、密碼保護 PDF 解密、OCR、AI 分析與自動分類、會計科目管理、銀行專用格式、其他未列模組的使用者功能均不在此版本。

## 目前延伸里程碑

原始 v0.1 之後已加入 Gmail 唯讀同步、加密 PDF 本機解鎖／預覽、OCR 邊界、帳單撤銷／恢復及專用 Excel 自動更新。Excel 只投影 SQLite 中已確認的有效交易；銀行專用 PDF 交易解析仍須以真實樣本逐項核對後實作，未知格式不得自動猜測入帳。

## 下一階段文件來源設計

Gmail 信用卡帳單採「remote source first」：

- Backend 可從 Gmail 取得 attachment bytes，在記憶體或受控 temporary buffer 中解析，完成後丟棄，不要求永久寫入 Windows storage。
- 預設只保存 Gmail source reference 與解析結果，例如 message ID、attachment ID、filename、sender、received time、SHA-256、parsed time。
- 使用者查看原始帳單時，Backend 可依 source reference 即時向 Gmail 取得附件並 stream 給瀏覽器 PDF viewer。
- 只有使用者明確選擇「保存到家庭文件匣」時，才將 Gmail attachment 持久化到本機 Documents storage。
- 密碼保護 PDF 亦可在記憶體中取得完整 bytes、解密及解析；密碼與其他 secret 不得寫入一般 SQLite table、log、repository 或明文設定檔。

## 延伸方向

保留 `DocumentSource`、`DocumentProcessor`、Gmail source、password-protected PDF processor、OCR processor、AIProvider、Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property 等未來擴充點。這些只作為架構邊界預留，不在 v0.1 提供空殼功能或外部整合。

Document source 可包含 Local File、Gmail Attachment，未來可再增加 Google Drive 或其他 provider；processor 可包含 PDF、CSV、Image、password-protected PDF、OCR 等。來源與處理器應透過 port 隔離，核心不得直接依賴供應商 SDK。

## 部署與資料原則

- 單一 Windows 主機、單一 Modular Monolith、SQLite、Alembic、本機檔案系統。
- Web UI 由 React/TypeScript/Vite 提供；FastAPI 提供 HTTP API。
- 家庭裝置透過 Tailscale 存取，不要求公網入口、DNS 反向代理或路由器埠轉送。
- SQLite 是結構化資料來源；需要本地持久化的原始文件保存在 storage adapter 管理的本機目錄。外部來源文件可只保存可重新取得內容的 source reference。
- SHA-256 是內容識別與去重的重要欄位；對本地持久化內容，相同內容不建立第二份文件。重複匯入應避免重複建立相同來源文件的交易。
- 不在一般 SQLite table、log 或明文設定檔存放秘密。未來 Windows 整合採 Credential Manager/SecretStore。

## 不採用

v0.1 不引入 microservices、Redis、Kafka、Kubernetes、PostgreSQL 或雲端儲存；以家庭使用規模可維護的最小部署為準。
