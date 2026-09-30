# 家庭收支記錄

## 產品定位

家庭收支記錄的近期目標是：信用卡帳單 PDF → 本機解鎖 → 逐筆解析與核對 → SQLite → 每月支出 Excel。先讓一家實際使用的銀行可靠運作，再由 Codex Gmail MCP 自動收錄附件；不以通用家庭資料平台的功能完整度作為交付標準。

目前產品優先目標已收斂為：**每月自動取得信用卡帳單，安全解鎖 PDF，正確解析消費交易，讓使用者快速知道本月花了什麼與花多少；Excel 是主要使用成果，並由 SQLite 可重建。**

既有 Documents、Finance、Gmail、PDF、Search、Jobs、Excel 等能力可作為已完成基礎設施，但「可持續擴充的通用家庭資料平台」不再是近期開發驅動力。除非出現真實需求，不為 Google Drive、Insurance、Assets、Vehicle 等未來領域繼續預先擴充。詳細的 scope reset、Overdesign 假說與高階模型審查問題見 `ARCHITECTURE_REVIEW_BRIEF.md`。

Windows 家用電腦保存結構化資料與需要本地持久化的原始文件，其他裝置以瀏覽器透過 Tailscale 私有網路存取。

Excel 是主要使用成果，Web 用於連線/解鎖設定、首次核對與例外處理。Windows 主機保存結構化資料及選擇保留的原始文件，其他裝置需要時透過 Tailscale 私有網路使用 Web。信用卡資料不代表所有家庭支出，也不保證當月尚未出帳的交易已齊全。

保留可維護的模組邊界，不重建現有核心；未來擴充退為次要，不先建空殼功能。詳細工作包與驗收以 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) 為準，進度見 TASKS/HANDOFF。

Documents 代表「文件的 logical identity 與來源」。目前主流程支援本機上傳，以及由 Codex MCP 取得後持久化的 Gmail attachment；舊版 remote-reference Gmail source 只保留相容能力，不再是新資料的預設路徑。

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

原始 v0.1 之後已加入 Codex MCP Gmail 收件、加密 PDF 本機解鎖／預覽、OCR 邊界、帳單撤銷／恢復、銀行帳單核對及專用 Excel 自動更新。Excel 投影 SQLite 已提交的有效交易；目前只驗證中國信託交易列及受限台新零交易版型，其他銀行不能因已收錄或解鎖 PDF 就視為可自動入帳。

第一個新交付是人工確認的真實 PDF 正確進 Excel，含去重、重跑、撤銷與恢復；目前接續工作仍包含 Codex MCP 受控收件、更多已授權銀行版型及固定 Windows 入口。2026-09-30 使用者另行核准「消費分類＋支出 Donut＋Category → Merchant → Transaction 下鑽」作為下一階段產品功能；它不回头改写 parser/Statement 核心，也不扩张成完整财务管理平台。

## 現有文件來源原則

新的 Gmail 信用卡帳單採「Codex MCP 取得、本機保存」：

- Gmail 的授權、搜尋與排程由 Codex 管理，FamilyHub 不取得 Gmail OAuth JSON/token，也不在 Web UI 提供連線流程。
- Codex 將附件及密碼規則附近的必要文字送入本機匯入 API；Backend 先遮罩提示、計算 SHA-256，再透過 `StoragePort` 保存附件。
- 原始 Gmail message/attachment ID 只用於計算不可逆來源 key；主旨、寄件者、完整本文及實際密碼不保存。
- 相同 bytes 及相同來源重跑均保持冪等；來源識別衝突會 fail closed，不自動覆寫。
- 收錄不代表入帳。交易資料仍需 parser、帳單合計核對及使用者確認；密碼保護 PDF 只在本機記憶體解密，密碼與其他 secret 不得寫入一般 SQLite table、log、repository 或明文設定檔。
- 舊版 remote-reference Gmail source/API 保留相容，但預設停用且不再驅動日常自動化。

## 延後範圍

保留既有 `DocumentSource`、`DocumentProcessor`、Gmail、PDF、OCR 與 AIProvider 邊界；不新增 Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property、股票 API 或其他 provider。未來需求真正發生再設計，不為「通用」先做 registry、多銀行 framework 或空殼 UI。

本輪仍不做完整 Dashboard 重寫、備註/Tag 系統、交易 AI、Budget、理財建議、雙向 Excel 同步或任意手寫工作表保留。分類功能是已核准例外：只做 `CATEGORY_SPENDING_PLAN.md` 定義的有效分類、規則/單筆 override、Donut、商家/明細下鑽、未分類整理及 Excel 投影。Gmail 搜尋與排程移到 Codex 自動化；網站內舊 Gmail History/scheduler 凍結為相容程式。Excel 背景檢查沿用，不重寫為事件平台。

近期不再以「預留所有家庭資料領域」作為開發目標。既有 `DocumentSource`、`DocumentProcessor`、Gmail source、password-protected PDF processor、OCR 邊界可保留；新的 provider/domain/通用 AI 能力一律等真實需求再新增。第一優先是完成並驗證 bank-specific 信用卡 PDF 交易解析的真實端到端流程。

Document source 可包含 Local File、Codex MCP Gmail Attachment 及舊版 Gmail remote reference，未來可再增加其他已證實需要的 provider；processor 可包含 PDF、CSV、Image、password-protected PDF、OCR 等。來源與處理器應透過 port 隔離，核心不得直接依賴供應商 SDK。

## 部署與資料原則

- 單一 Windows 主機、單一 Modular Monolith、SQLite、Alembic、本機檔案系統。
- Web UI 由 React/TypeScript/Vite 提供；FastAPI 提供 HTTP API。
- 家庭裝置透過 Tailscale 存取，不要求公網入口、DNS 反向代理或路由器埠轉送。
- SQLite 是結構化資料來源；需要本地持久化的原始文件保存在 storage adapter 管理的本機目錄。外部來源文件可只保存可重新取得內容的 source reference。
- SHA-256 是內容識別與去重的重要欄位；對本地持久化內容，相同內容不建立第二份文件。重複匯入應避免重複建立相同來源文件的交易。
- 不在一般 SQLite table、log 或明文設定檔存放秘密；現有 Windows 整合使用 Credential Manager/SecretStore。AI 僅可在 opt-in 下解析遮罩密碼規則，不接收真實身分/生日/密碼或交易全文。

## 不採用

v0.1 不引入 microservices、Redis、Kafka、Kubernetes、PostgreSQL 或雲端儲存；以家庭使用規模可維護的最小部署為準。
