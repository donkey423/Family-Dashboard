# 家庭收支記錄交接

更新：2026-09-30。本文件描述目前狀態；歷史驗證以 Git 為準。接手先讀 AGENTS、README、TASKS、IMPLEMENTATION_PLAN；分類功能另讀 CATEGORY_SPENDING_PLAN。

## 正式分類部署已完成

使用者以「開始做」授權後，已完成正式 0011 → 0012 migration、同步 production build、由既有 `FamilyFinanceHub` 正常 Windows 登入帳戶排程啟動。原私有網址的總覽已顯示真實分類支出／Donut，分類 → 商家 → 逐筆 → 來源文件及設定頁分類管理均已實測。正式資料仍為原有 18 筆；沒有自動分類、confirm 或恢復已撤銷資料。既有消費尚未建立分類規則，因此圓環目前只有「未分類」。使用者現另要求交通／圖書／飲食等逐筆自動辨識，規劃见 canonical plan 第 18 節，不將人工分類 V1 當成自動辨識已完成。

成對備份與本機驗證證據位於 Git 忽略的 `data/backups/20260930-categories-1845/`：一致性 DB、20 個文件原檔、owned Excel、舊 frontend/dist、排程 XML、Git 基準程式封存；副本還原、migration downgrade/re-upgrade、原有全表資料及文件 hash 保留通過。正式啟動後再核對交易／Statement／來源／秘密參照／撤銷資料；只有輸出狀態及工作紀錄允許正常更新。已保存 `before.json`、`rehearsal.json`、`migration.json`、`runtime.json` 與 `excel_verified.json`。沒有對正式 DB 執行 downgrade；後續回退仍需授權、成對備份與相符程式。

## 本輪成果與 Git 狀態

- 已讀取遠端 `origin/main @ bf3d4f6` 的七個 MD-only 提交，依已核准的 C1-C5 實作消費分類、Donut、商家／逐筆下鑽與 Excel 分類投影。
- 分類實作起點為 `f34550d`。本次已收到使用者更新 MD 與推送 Git 的授權；遠端七個 MD-only 提交須保留，整合另依當次核准，不 force push 或 reset。目前 HEAD／提交範圍及遠端同步結果由 `git status`、`git log`、`git ls-remote origin refs/heads/main` 確認，不在文件固定一個會過時的 HEAD。
- 推送只包含程式、測試、腳本及 MD；不加入 Downloads、data、DB／帳單／工作簿／秘密、build／dependencies 或原有未追蹤 `pytest-of-brad/`、`tmpe9fanwiq/`，不刪這些內容。
- M12 正式部署及本輪三銀行關卡已完成；預覽不是日常資料入口，不把合成資料加入正式資料庫。
- 已新增 Gmail 網頁附件下載檢查點／驗證工具及受控三銀行隔離驗收腳本；不改正式匯入契約、重新導入 OAuth 或更動排程。後續必測步驟見 IMPLEMENTATION_PLAN 4.1。

## 最新需求：逐筆自動分類研究（未實作）

2026-09-30 唯讀正式 API：14 類、沒有 books，商家規則／有效單筆 override 皆 0；九月 6 筆支出皆未分類，分類淨額與 Dashboard 一致。resolver 缺少商家知識來源，不是圓環失效。現有樣本多為旧 CSV、缺少 transaction_kind；不能用分類處理去猜退款／利息／折抵的會計資料。

下一階段以每筆刷卡交易為範圍，先做本機明確規則、圖書與逐筆確認，混合商家不能記住為所有商品用途。可選 AI 只提建議且需另取雲端同意。A1-A6／AUTO-01-08、privacy、驗收與回退只維護於 `CATEGORY_SPENDING_PLAN.md` 第 18 節；TASKS M13 保持實作未勾選。這次只將研究／既有成果文件化與 Git 封存，沒有新分類程式、正式 migration、部署或帳本寫入。

下面 M12／三銀行結果屬於前次已完成部署與 `retest-20260930-1903`，不是這次文件更新的新 Gmail 測試。依 canonical plan 第 15 節，純文件整理不重複下載；未來 A1-A6 程式交付仍須當次完整三銀行，不能沿用舊 PASS。

## 本次文件與 Git 封存驗證

- 2026-09-30 重新執行完整 backend：326 passed、2 個既有相依套件棄用警告；frontend：29 passed；TypeScript／Vite production build 成功，輸出到 `frontend/dist-category-preview`，未替換正式 dist。
- 正式本機與私有 HTTPS 首頁、health、首頁 JS／CSS 及分類 API 唯讀正常；產品名稱是家庭收支記錄，14 類／0 規則仍與根因一致。這不是實體手機驗收，也沒有測分類 AI。
- 待提交檔案掃描未發現長格式 API key／私鑰或 MD 中證號；仍須人工確認 staged 路徑，只納入原始碼／測試／腳本／文件，排除 data、DB、PDF、Excel、暫存與 build。此掃描不是萬用秘密檢測保證。
- 正常帳戶 fetch 已讀到 `origin/main @ bf3d4f6`；沙箱 Schannel `SEC_E_NO_CREDENTIALS` 與正常帳戶 repo ownership 檢查，透過當次提升權限及命令限定的 `safe.directory` 處理，不關閉 TLS 或更動全域 Git 信任設定。整合及 push 須依當次核准，推送成功另以遠端 SHA 核對。

## M12 已實作

- `0012_transaction_categories`：新增 FinanceCategory、FinanceCategoryRule、TransactionCategoryOverride；14 個預設類別。FinanceTransaction 的日期、金額、來源、row_hash、Statement identity 不變。
- `finance/categories/domain.py` 為純分類規則；NFKC／空白／大寫正規化保留店號，exact/contains 為文字比對，不是 SQL wildcard。
- `CategorizationService` 批次解析 read-time effective category：單筆 override > exact > contains（priority、長度、穩定 ID）> system > 未分類。停用類別安全 fallback；重新啟用保留既有 references。
- APIs：分類／規則 CRUD、單筆或商家套用、清除 override、分類支出、商家小計、未分類整理、分類／商家篩選後分頁。分類代碼唯一，顯示名稱可重複；付款不進消費、退款沖抵、幣別不混加。
- React：Recharts Donut，Top 5 +「其餘類別」，負淨額另列退款／抵扣；Category → Merchant → Transaction，下鑽 URL／幣別／月份、来源文件、單筆修改／商家記憶、設定與未分類整理。
- Excel 共用同一 resolver；交易明細新增「分類」，新增「分類支出」工作表。分類／規則／override 進入 fingerprint；只改分類也標示待更新。沿用 ownership、公式防護、hash、原子替換及檔案占用保護。
- SQLite 連線啟用 foreign_keys；安全 profile／PasswordRule ORM relationship 已同步，以保證父子寫入順序。完整舊流程回歸通過。
- 手機交易新增第五欄後，舊四欄 grid 會被長分類擠壓，已修成語意 cell 與獨立分類列；320px／390px 長名稱實際瀏覽器檢查通過。

## M12 部署驗證（前次結果）

- 完整 backend：**326 passed**（既有 310 + 16 項下載回歸）、2 個既有 Starlette/httpx／anyio 棄用警告。
- 下載回歸涵蓋完整加密 `.tmp`、舊檔修改、HTML／截斷／`.crdownload`／超限、多檔歧義、讀取競態、寫入中轉完成、兩秒穩定、冪等／hash 改變、過期、路徑逃逸、同時間戳不同 checkpoint 及失效 receipt。
- Frontend：**29 passed**，Vitest + React Testing Library；TypeScript/Vite production build 成功。先輸出至本輪備份目錄的 `new-frontend`，保留舊產物後才部署到正式 `frontend/dist`。
- 隔離 migration：0011 → 0012、downgrade／re-upgrade、既有 CSV／Statement 全欄位 identity 保留、seed、FK／whitelist。
- 回歸涵蓋優先序／停用／重分類、20 筆商家三筆例外、失敗 rollback、SQLite lock／concurrency、退款／付款／跨月／閏日／多幣別、撤銷恢復、Statement 重分析重確認、Excel／backup parity、公式防護與 fingerprint。
- Frontend 覆蓋 Top-N／整數 cents／固定百分比、stale request、URL、分頁／來源、寫入失敗、pending Escape、分類與規則操作、鍵盤 Enter／Space 及 accessible labels。真正螢幕閱讀器和實體手機未驗收。
- 分類寫入／回復與長名稱先於隔離資料驗證；正式私有 HTTPS 另驗真實 Donut 非空、分類 → 商家 → 單筆 → 文件、14 個類別設定及 320px／390px 響應式畫面。正式驗收只讀，沒有建立規則或 override。預覽合成文件已撤銷，目前有效交易 0 筆，不能擅自恢復來補圖。
- 正式 owned Excel 已由啟動檢查重建，18 筆交易穩定 ID／分類與 API 全數一致；「分類支出」每月／幣別／分類筆數與淨額對上 API，各期合計對上 Dashboard；ownership marker 保留，沒有覆寫非本系統檔案。
- 效能：10,008 筆／50 規則 resolver＋彙總 37.7ms，3 次配置／override query（不含載入 ORM rows）；完整 API 三次 259.6／187.4／185.4ms。首次未達 200ms 目標，暖機後達標，不當跨機器 SLA。500 商家 API／分類分頁均不超過 6 次 query；固定種子的 generated invariants 通過。
- 可重跑命令見 README／IMPLEMENTATION_PLAN；Windows 暫存目錄須使用 Documents/Codex 下短且唯一的名稱。

## 正式部署後 E2E-GMAIL-3BANK：PASS 3/3

當次沒有可呼叫的 Gmail MCP 工具，使用已登入 Gmail 網頁。未指定日期，以 `in:anywhere has:attachment filename:pdf subject:<銀行> subject:帳單` 按三家搜尋可存取最早信件至當下；只查閱所選九月信用卡月帳單，不宣稱逐封查完整個信箱。永豐來源在垃圾桶，未移動／恢復。

| 銀行／帳期 | 新下載／郵件格式確認 | 加密解鎖 | 完整交易及摘要核對 | 冪等重跑 |
| --- | --- | --- | --- | --- |
| 中國信託／2026-09 | PASS | 2 頁 | 1 列，原文／parser／API 相符 | 同一 Document／Statement，筆數不變 |
| 國泰世華／2026-09 | PASS | 3 頁 | 19 列，含 1 列按明示結帳日認列的利息 | 同上 |
| 永豐／2026-09 | PASS，非繳款聯 | 4 頁 | 31 列，含退款／繳款／費用／本期分期額 | 同上 |

- 使用 `prepare → 指定附件下載按鈕 → collect` 再次從 Gmail 取得三家新檔。中信第一次原信／檢視器下載沒有新檔，工具下載亦逾時，沒有把它標成 PASS；重新載入原信、確認掃描結束且按鈕可用、重建 checkpoint 後成功。新 `.tmp` 經兩秒穩定、strict PDF／EOF、SHA-256 與唯一 checkpoint 驗證；來源 bytes 分別為 643,152／902,897／743,221。原 Downloads 檔未刪除／改名；沒有拿前次檔案補本次驗收。
- 本輪加密原件、checkpoint、receipt、manifest 與 `audit-result.json` 在 Git 忽略的 `data/gmail-acceptance/retest-20260930-1903/`，label 為 `ctbc`／`cathay`／`sinopac`，結果 `PASS_3BANK`。未保存解密 PDF、抽取全文或秘密，不把此目錄加入 Git。
- 用 `scripts/gmail_acceptance_app.py` 啟動隔離 8031／`acceptance.db`（0012），只讀正式 credential references，SecretStore 禁止寫入／刪除，外部 AI 明確關閉。`gmail_statement_acceptance.py` 驗隔離識別後走既有 Codex import 邊界，從保存的實際郵件提示解鎖；沒有手動密碼或提示 override。全列日期／商家／金額／幣別／類型、摘要及 API 核對一致，重送 Document／Source／Statement 不新增。
- 本次隔離 Finance **0 筆**、confirm **0 次**、AI **0 次**，不生成隔離 Excel。驗收期間正式 Finance **18 → 18**，全交易欄位 fingerprint 及正式 schema **0012** 不變；下載／解鎖測試只向隔離 API 寫入。正式 Excel 的分類投影另在部署驗證完成；既有國泰／永豐正式草稿仍待人工確認。
- 驗收完成後已關閉本次臨時 8031 程序；正式 3000 與既有分類預覽 8030 健康檢查仍為 ok。下一次驗收須另行啟動隔離 API，不把保留的舊 PASS 當成新一輪結果。
- 此結果不是 MCP／cron 收件驗收，不是第二期盲測，也不是新增真實交易的 Excel 入帳驗收。以後每次交付仍須重新跑三銀行，不能永久沿用此 PASS。
- 下載首次失敗的瀏覽器內部根因仍未證實；重新載入後成功不等於保證永不失敗。不停用瀏覽器保護，也不進受限的瀏覽器內部頁面繞過限制。

## 執行與資料隔離

| 環境 | 本機入口 | SQLite／輸出 | 私有 HTTPS |
| --- | --- | --- | --- |
| 正式日常服務 | 127.0.0.1:3000，既有 FamilyFinanceHub 使用者登入排程 | `data/family-finance-hub-live.db`：0012、18 筆；新版分類 dist／Excel | `https://desktop-vcgfqnq.tailb47104.ts.net/`，443 → 3000 |
| M12 隔離預覽 | 前端 3001 → API 8030 | `data/category-preview/synthetic.db`：0012、有效交易 0 筆；合成來源已撤銷；SecretStore／Excel 關閉 | `https://desktop-vcgfqnq.tailb47104.ts.net:8443/?month=2026-09`，8443 → 3001 |

啟動預覽：`./scripts/start_category_preview.ps1 -MobileHostname desktop-vcgfqnq.tailb47104.ts.net`。此腳本只對指定合成 DB 自動 migration，不能改作正式啟動器。Vite API 同源代理到 8030；只 bind loopback。已驗本機首頁／API 與 HTTPS 實際分類畫面，未以實體手機驗收；預覽沒有登入自動啟動排程，服務仍須保持執行。既有 443 Serve 保留，沒有 Funnel。

**後續部署停止條件：** 重新核對程式 head 與目標 DB；若不同，先取得當次升級授權與成對備份，再測副本 migration／同步 build／正常登入帳戶啟動。`start_server.ps1` 不自動 migration。舊 `data/family-finance-hub.db` 與既有備份保留，不同步或直接升級；不更改其他專案 Serve 路由。

## 核心安全與既有狀態

- Codex 收錄附件與 FamilyHub 分析／确认入帳分開；網站 Gmail OAuth／scheduler 預設停用，legacy 只保留相容。收錄不等於交易入帳。
- 秘密只在正常 Windows 登入帳戶的 Credential Manager／SecretStore。沙箱帳戶曾出現 Windows 1312；正式啟動器使用隨機合成 probe 做寫／讀／清除，失败拒絕占用 3000。
- 未列日期只有 interest + 明示 closing_date 可依使用者批准認列；來源日期保留空值。其他缺日期／未知列／對帳不符維持 pending。
- Bank parser 範圍限於已驗證中國信託／國泰／永豐文字版型及受限台新零交易；不能宣稱通用銀行支援。
- Groq provider-neutral／safe-switch 程式已有；上次正常帳戶 runtime 是 OpenAI／gpt-4.1-mini，credential 可讀不代表額度有效。本輪未做 provider request／切換。Groq 真實 activation 仍未完成，明示格式不需 AI；不允許付費 fallback 或 PII／全文送 AI。
- SQLite 是事實來源；Excel 是專用可重建投影。保留 Documents 1:N、SHA-256、撤銷／恢復與原子入帳；不同 bytes 的語意重複目前未自動判定。

## 下一步與未完成

1. 待使用者另行核准後，先依 canonical plan 第 18 節執行 A1-A3；逐筆自動分類、圖書與安全的確認流程尚未實作。既有 V1 仍可人工指定單筆或商家，但多用途商家不宜整組套用；不為補圖擅自替正式資料猜分類。
2. 第二期未參與 parser 調整的真實盲測；更多銀行需授權樣本，未知版型保持 pending。
3. Codex Gmail 自動化首次真實收件／冪等重跑／跨日／離線補抓；任務曾設定 Luna Max 每 30 分鐘，接手須查現況，不能由設定存在推定成功。
4. Groq key／真實 runtime activation、OCR runtime、實體手機／螢幕閱讀器、重開機排程与服務意外退出原因仍未驗收。
5. 一萬筆分類 API 冷啟動效能仍可優化；目前無 N+1，不先引入 cache／background 平台。
