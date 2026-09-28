# 家庭收支記錄

## 產品定位

家庭收支記錄的近期目標是：信用卡帳單 PDF → 本機解鎖 → 逐筆解析與核對 → SQLite → 每月支出 Excel。先讓一家實際使用的銀行可靠運作，再接既有 Gmail 同步自動處理；不以通用家庭資料平台的功能完整度作為交付標準。
家庭收支記錄的近期目標是：信用卡帳單 PDF → 本機解鎖 → 逐筆解析與核對 → SQLite → 每月支出 Excel。先讓一家實際使用的銀行可靠運作，再接既有 Gmail 同步自動處理；不以通用家庭資料平台的功能完整度作為交付標準。

目前產品優先目標已收斂為：**每月自動取得信用卡帳單，安全解鎖 PDF，正確解析消費交易，讓使用者快速知道本月花了什麼與花多少；Excel 是主要使用成果，並由 SQLite 可重建。**

既有 Documents、Finance、Gmail、PDF、Search、Jobs、Excel 等能力可作為已完成基礎設施，但「可持續擴充的通用家庭資料平台」不再是近期開發驅動力。除非出現真實需求，不為 Google Drive、Insurance、Assets、Vehicle 等未來領域繼續預先擴充。詳細的 scope reset、Overdesign 假說與高階模型審查問題見 `ARCHITECTURE_REVIEW_BRIEF.md`。

Windows 家用電腦保存結構化資料與需要本地持久化的原始文件，其他裝置以瀏覽器透過 Tailscale 私有網路存取。

Excel 是主要使用成果，Web 用於連線/解鎖設定、首次核對與例外處理。Windows 主機保存結構化資料及選擇保留的原始文件，其他裝置需要時透過 Tailscale 私有網路使用 Web。信用卡資料不代表所有家庭支出，也不保證當月尚未出帳的交易已齊全。

保留可維護的模組邊界，不重建現有核心；未來擴充退為次要，不先建空殼功能。詳細工作包與驗收以 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 為準，進度見 TASKS/HANDOFF。

Documents 代表「文件的 logical identity 與來源」，不等同於「一定存在 Windows 硬碟上的本地檔案」。目前支援本機上傳與 Gmail attachment 來源；只有使用者選擇保留的遠端附件才持久化到本機 storage。

## 已建立的 v0.1 基礎

- 共用 Documents：匯入及瀏覽 PDF、JPG、PNG、CSV，保存 SHA-256、媒體類型、大小、來源關聯與匯入時間；v0.1 上傳文件持久化於本機檔案系統。
- 通用 Finance CSV：將 CSV 先匯入 Documents，再解析日期、描述、金額、幣別與原始欄位，並建立交易至來源文件的關聯。
- Dashboard：顯示交易筆數、收入、支出與淨額。
- Search：搜尋文件名稱、文件類型、交易描述與金額相關文字。
- Jobs / Import history：顯示匯入來源、狀態、結果及錯誤摘要。
- Tests：覆蓋文件雜湊去重、重複匯入冪等性、CSV 解析及 API 基本流程。

## 原始 v0.1 明確不包含

原始 v0.1 未包含 Gmail、密碼 PDF、OCR、AI、自動分類、會計科目、銀行專用格式及其他模組；這是初版邊界，不表示下列後續功能都尚未實作。

## 目前延伸里程碑

原始 v0.1 之後已加入 Gmail 唯讀同步、加密 PDF 本機解鎖／預覽、OCR 邊界、帳單撤銷／恢復及專用 Excel 自動更新。Excel 目前投影 SQLite 已提交的有效交易；銀行專用 PDF parser 尚未完成，信用卡退款／繳款語意也尚未接入持久化與輸出，不能把收錄 PDF 當作自動入帳。

第一個新交付是人工確認的真實 PDF 正確進 Excel，含去重、重跑、撤銷與恢復；接著補最小 Web 操作、沿用 Gmail 的受控自動入帳及固定 Windows 入口。完整 Dashboard、分類系統及同步引擎重寫不是前置。

## 現有文件來源原則

Gmail 信用卡帳單採「remote source first」：

- Backend 可從 Gmail 取得 attachment bytes，在記憶體或受控 temporary buffer 中解析，完成後丟棄，不要求永久寫入 Windows storage。
- 保存 Gmail source reference 與必要文件 metadata；原始附件預設不永久落地。現有收錄不代表已保存信用卡交易解析結果，交易資料需待 parser 與核對流程完成。
- 使用者查看原始帳單時，Backend 可依 source reference 即時向 Gmail 取得附件並 stream 給瀏覽器 PDF viewer。
- 只有使用者明確選擇「保存到家庭文件匣」時，才將 Gmail attachment 持久化到本機 Documents storage。
- 密碼保護 PDF 亦可在記憶體中取得完整 bytes、解密及解析；密碼與其他 secret 不得寫入一般 SQLite table、log、repository 或明文設定檔。

## 延後範圍

保留既有 `DocumentSource`、`DocumentProcessor`、Gmail、PDF、OCR 與 AIProvider 邊界；不新增 Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property、股票 API 或其他 provider。未來需求真正發生再設計，不為「通用」先做 registry、多銀行 framework 或空殼 UI。

本輪不做完整 Dashboard、分類/備註管理、交易 AI、雙向 Excel 同步或任意手寫工作表保留。Gmail History/message search、30 分鐘 opt-in 排程及 Excel 背景檢查沿用，不重寫為 90 天水位、每日新排程或事件平台。

近期不再以「預留所有家庭資料領域」作為開發目標。既有 `DocumentSource`、`DocumentProcessor`、Gmail source、password-protected PDF processor、OCR 邊界可保留；新的 provider/domain/通用 AI 能力一律等真實需求再新增。第一優先是完成並驗證 bank-specific 信用卡 PDF 交易解析的真實端到端流程。

Document source 可包含 Local File、Gmail Attachment，未來可再增加 Google Drive 或其他 provider；processor 可包含 PDF、CSV、Image、password-protected PDF、OCR 等。來源與處理器應透過 port 隔離，核心不得直接依賴供應商 SDK。

## 部署與資料原則

- 單一 Windows 主機、單一 Modular Monolith、SQLite、Alembic、本機檔案系統。
- Web UI 由 React/TypeScript/Vite 提供；FastAPI 提供 HTTP API。
- 家庭裝置透過 Tailscale 存取，不要求公網入口、DNS 反向代理或路由器埠轉送。
- SQLite 是結構化資料來源；需要本地持久化的原始文件保存在 storage adapter 管理的本機目錄。外部來源文件可只保存可重新取得內容的 source reference。
- SHA-256 是內容識別與去重的重要欄位；對本地持久化內容，相同內容不建立第二份文件。重複匯入應避免重複建立相同來源文件的交易。
- 不在一般 SQLite table、log 或明文設定檔存放秘密；現有 Windows 整合使用 Credential Manager/SecretStore。AI 僅可在 opt-in 下解析遮罩密碼規則，不接收真實身分/生日/密碼或交易全文。

## 不採用

v0.1 不引入 microservices、Redis、Kafka、Kubernetes、PostgreSQL 或雲端儲存；以家庭使用規模可維護的最小部署為準。
