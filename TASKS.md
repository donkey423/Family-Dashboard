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

## M7：使用體驗、導覽與排版（進行中）

2026-09-27 已完成 M7.1 搜尋與導覽、M7.2 新增資料與來源追溯、M7.3 月份與幣別總覽、M7.4 設定／PDF 預覽及 M7.5 排版／共用介面。不取代 M5 的真實銀行 PDF 交易解析或 M6 的正式資料庫驗收。

建議順序：搜尋與導覽修正 → 明確區分文件收錄與交易入帳 → 文件、交易及匯入紀錄關聯 → 月份／幣別總覽 → 設定與排版。先改善操作與資訊結構，不全面重寫介面。

### M7.1 搜尋與導覽

- [x] 將搜尋獨立為結果頁，修正搜尋後切換設定仍顯示總覽／搜尋區塊的狀態混用；標題、導覽選取與內容一致。
- [x] 搜尋 API 提供各類結果總筆數及分頁；前端不再只顯示固定筆數或以「查看全部」清除搜尋。
- [x] 將搜尋頁、搜尋字詞及兩類分頁同步至 URL，支援重新整理與瀏覽器上一頁；密碼、身分資料及文件內容不進入 URL。
- [x] 為搜尋提供獨立載入、無結果與失敗狀態；快速切換字詞或頁面時，舊請求不得覆蓋新結果。

### M7.2 新增資料與來源追溯

- [x] 統一「新增資料」入口，內含文件上傳、財務 CSV 匯入及 Gmail 同步；明確呈現「僅收錄文件」與「建立交易」的結果。
- [x] 根據實際文件、交易及處理結果顯示「已收錄，尚未入帳」、新增／略過交易筆數或失敗原因；本機副本標記不代表入帳成功。
- [x] 增加文件詳細檢視，整合來源、收錄／入帳狀態、關聯交易、匯入紀錄、原始文件／預覽及撤銷／恢復；收錄日期與交易日期分開顯示。
- [x] 交易可回到 `source_document_id` 對應文件；Jobs 只有在具備 `document_id` 時提供文件連結，批次 Gmail 工作不任意連到單份文件。
- [x] Gmail 日常同步入口放在新增資料／文件流程；OAuth 連線設定保留設定頁，未授權時提供前往設定的下一步。
- [x] 保留 Documents 共用底層、SHA-256 冪等及撤銷保護；恢復仍使用原交易，不重新解析。PDF 仍明示只收錄／預覽／抽取文字，尚未建立交易。

### M7.3 月份與幣別總覽

- [x] 首頁預設顯示本月，可切換月份；支出、收入、淨額及交易筆數均由選定期間呈現，下方顯示該期間交易與待處理文件。
- [x] Dashboard API 支援月份／幣別篩選並由資料庫聚合全部符合資料，不以首頁最近 8 筆或單頁交易計算總額；交易頁共用月份定義及有效文件條件。
- [x] 多幣別以選單及分組結果顯示，不把不同幣別金額相加或默默換匯；總覽連往明細時保留月份／幣別條件。
- [x] 已驗收跨月、當月無交易、多幣別、格式錯誤及撤銷／恢復後的有效資料條件；零筆期間顯示明確空狀態，不推定匯入失敗。

### M7.4 設定與 PDF 預覽

- [x] 設定依「連線服務／家庭成員／文件解鎖／進階設定」分組導覽，避免手機需滑過全部表單才能找到 Gmail。
- [x] 使用者可見的「安全 profile」改為「文件解鎖設定」等一致名稱；不為文案改動重命名既有資料識別或 schema。
- [x] 一般 PDF 開啟即預覽，需要密碼時才展開解鎖設定；錯誤區分需要密碼、密碼錯誤、來源不可用與 OCR 未就緒。預覽成功不代表財務入帳。
- [x] AI 規則解析維持明確 opt-in，真實秘密只在本機組合；自動預覽不得暗中呼叫 AI、啟用同步或永久保存遠端附件。
- [x] PDF 與撤銷／恢復對話框統一鍵盤行為：開啟時移入焦點、Tab 留在對話框、Escape 關閉並回到觸發按鈕。保留撤銷影響確認與過期預覽保護。

### M7.5 排版與共用介面

- [x] 主要內容採固定 14–16px、次要文字 12–13px 的可讀層級；金額靠右且數字等寬，避免多幣別大字擠在同一區塊。不使用隨視窗寬度縮放的字級。
- [x] 手機交易改為能同時看到項目與金額的排列，日期作次行；390px／320px 下不必橫向捲動才看得到金額。長檔名、錯誤文字與按鈕不得互相遮蔽。
- [x] 減少手機頁首及導覽佔高，統一工具列、常見圖示與操作層級，主要觸控操作保留足夠點擊範圍；維持適合日常查帳的緊湊布局，不增加裝飾性巢狀卡片。
- [x] 隨上述功能逐步從 `App.tsx` 分離頁面與共用元件，隔離搜尋、設定及預覽狀態；沿用既有工具與架構，不另起前端或順手重構無關模組。

### M7 驗收與完成標準

- [ ] 每個子里程碑執行受影響的測試及 frontend production build；API／資料查詢有改動時執行 backend 測試，完成後更新 HANDOFF，才能勾選對應項目。
- [ ] 補前端行為測試：搜尋後切頁、URL／上一頁、分頁保留字詞、月份／幣別連動與對話框鍵盤焦點；API 覆蓋搜尋總筆數、分頁及期間聚合。
- [ ] 隔離合成資料涵蓋超過 8 筆交易／5 份文件與每類超過 50 筆搜尋結果、長檔名、大額、多幣別、空狀態、載入及失敗；於桌面、390px、320px 實際操作檢查。
- [ ] 回歸驗證同 hash 不重複入帳、撤銷不被重新匯入復活、恢復不新增交易、過期影響預覽要求重新確認；不讀取正式資料或秘密來完成 UI 驗收。

## M8：Gmail 帳單到 Excel 的長期自動化

產品目標為 Gmail 新帳單 → 共用 Documents → 解鎖／解析／核對 → Finance → 專用 Excel 自動更新。Excel 為可重建的輸出；SQLite 保留交易與來源的單一事實來源。先接通可驗證的 CSV 到 Excel，再以真實銀行樣本完成 PDF 入帳，不能把 PDF 收錄當成交易解析成功。

- [x] 專用 Excel 包含月份／幣別摘要、交易與文件待處理狀態，保留穩定來源 ID。
- [x] 自動偵測已提交資料變更並更新 Excel；重複同步不重複列，撤銷／恢復同步反映。
- [x] Excel 佔用或寫入失敗保留上一版，定時重試；重啟仍可重建，狀態與錯誤可見；外部修改或替換後停止下載並安全重建。
- [x] 設定頁提供啟停、立即更新、下載與尚未入帳 PDF 筆數。
- [ ] 取得第一份真實銀行帳單，在本機驗證日期、幣別、退款、消費／繳款區分及總額核對。
- [ ] 已驗證 PDF parser 接入共用入帳流程；未知格式／解鎖失敗保留待處理並可重試。
- [ ] Windows 常駐／登入啟動與真實 Gmail OAuth 長期有效性驗收。
- [ ] 真實郵件 → PDF → Finance → Excel 端到端驗收。

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
