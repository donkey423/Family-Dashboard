# 家庭收支記錄

## 產品定位

家庭收支記錄是可持續擴充的 local-first 家庭資料平台。它不把核心限制為一次性記帳 App；Finance 是第一個消費共用文件資料的 domain。Windows 家用電腦保存結構化資料與原始文件，其他裝置以瀏覽器透過 Tailscale 私有網路存取。

## v0.1 目標

- 共用 Documents：匯入及瀏覽 PDF、JPG、PNG、CSV，保存 SHA-256、媒體類型、大小、原始檔案位置與匯入時間。
- 通用 Finance CSV：將 CSV 先匯入 Documents，再解析日期、描述、金額、幣別與原始欄位，並建立交易至來源文件的關聯。
- Dashboard：顯示交易筆數、收入、支出與淨額。
- Search：搜尋文件名稱、文件類型、交易描述與金額相關文字。
- Jobs / Import history：顯示匯入來源、狀態、結果及錯誤摘要。
- Tests：覆蓋文件雜湊去重、重複匯入冪等性、CSV 解析及 API 基本流程。

## 明確不在 v0.1

Gmail 連線、密碼保護 PDF 解密、OCR、AI 分析與自動分類、會計科目管理、銀行專用格式、其他未列模組的使用者功能均不在此版本。

## 延伸方向

保留 Gmail source、password-protected PDF processor、OCR processor、AIProvider、Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property 等未來擴充點。這些只作為架構邊界預留，不在 v0.1 提供空殼功能或外部整合。

## 部署與資料原則

- 單一 Windows 主機、單一 Modular Monolith、SQLite、Alembic、本機檔案系統。
- Web UI 由 React/TypeScript/Vite 提供；FastAPI 提供 HTTP API。
- 家庭裝置透過 Tailscale 存取，不要求公網入口、DNS 反向代理或路由器埠轉送。
- SQLite 是結構化資料來源；原始文件保存在 storage adapter 管理的本機目錄。
- SHA-256 是內容去重鍵；相同內容不建立第二份文件。重複匯入回傳既有文件，並避免重複建立相同來源文件的交易。
- 不在一般 SQLite table、log 或明文設定檔存放秘密。未來 Windows 整合採 Credential Manager/SecretStore。

## 不採用

v0.1 不引入 microservices、Redis、Kafka、Kubernetes、PostgreSQL 或雲端儲存；以家庭使用規模可維護的最小部署為準。
