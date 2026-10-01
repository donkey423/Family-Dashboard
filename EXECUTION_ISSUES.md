# 家庭收支記錄：執行問題與處理

> 更新日期：2026-10-01
>
> 本文件只記錄工程執行時可觀察到的問題、處理方式與剩餘限制，不保存帳單內容、身分資料、生日、PDF 密碼、API key、OAuth token 或其他秘密。

## 0. 目前問題與處理

正式站已依使用者 2026-10-01 的升級授權部署 M13／0013，82 筆交易與 20 個原件完整保留、owned Excel 同步。修正明確描述分類、圖表初始尺寸、待分類入口及窄螢幕溢出；backend **399 passed**（2 warnings）、frontend **38 passed**、Node helper **7 passed** 與正式 build 通過。本輪再次下載中信／國泰／永豐，原信格式／解鎖／全列／摘要／API／冪等均 PASS，證據在 ignored `data/gmail-acceptance/retest-20261001-chart-fix/`。前輪下載對照及歷史 FAIL 保留；未完成分類盲測、長期 MCP 或舊 CSV 語意去重，見 [HANDOFF](HANDOFF.md)。

0.1-0.6 是已解決的 M12 問題及殘餘限制；1-4 節是 2026-09-29 歷史，不是今日待執行指令。未完成工作為品質盲測、未知交易整理、長期 MCP、Groq runtime 及實體裝置驗收；不要因舊記錄再次要求網站 OAuth。

### 0.11 Git 交付重測與文件狀態修正

- **本次驗證：**新下載中信／國泰／永豐九月月帳單，解鎖、全列／摘要、API 及冪等 PASS 3/3；backend 399、frontend 38、Node helper 7 passed，隔離 build 通過。證據在 ignored `data/gmail-acceptance/retest-20261001-git-delivery/`；正式 82 筆／0013 不變，沒有額外入帳或外部 AI。驗收後只停止確認屬於本次的臨時 API 8031。
- **文件矛盾：**TASKS 的 M13 標題與 CATEGORY_SPENDING_PLAN 7.4 仍寫未部署，已按正式狀態修正。HANDOFF 移除重複歷史驗證段落，保留目前環境、當次測試、證據路徑、缺口與停止條件；舊紀錄由 Git／既有 ignored 報告保留。
- **Gmail 查詢：**搜尋操作後即刻快照曾仍顯示未篩選收件匣；廣泛讀取主區域被安全審查阻擋。改先送出限定銀行查詢、核對當前搜尋 URL，再只讀匹配月帳單列，不讀無關健保／認證郵件。過窄的假設標題沒有匹配時，改銀行／信用卡／帳單關鍵字並確認實際主旨，不把零結果當銀行沒有寄信。
- **Git 連線：**sandbox fetch 曾因 Windows schannel 無可用認證失敗；相同命令經正常 Windows 帳戶的提升執行成功，沒有修改 TLS 驗證、取出憑證或更改 remote。起始本機／遠端均為 `2061e99`，不存在待 merge 提交；發布前再次 fetch／正常 merge／push 並核對 remote SHA，不 force push 或製造空 merge。

### 0.10 正式圖表／分類與 M13 部署

- **證據：**原正式服務仍載入 M12 程式／0012，九月 99.61% 支出落在未分類；repo 新功能存在不代表部署成功。真實描述的捷運法律名稱／A- 前綴及完整訂閱文字未匹配舊規則，ResponsiveContainer 初次尺寸警告，窄螢幕實際 CSS 300px 被 body min-width 320px 撐寬、金額被截。
- **修復：**版本化 fullmatch 補明確描述及反例，不猜多用途商家；圖表提供固定初始尺寸／minWidth=0，增加待分類筆數與整理入口，body min-width=0。本輪副本 migration／回退及授權後成對備份、正式 migration／build／原帳戶排程啟動已完成。
- **停止排程仍有程序：**`Stop-ScheduledTask` 後排程為 Ready、3000 卻仍由原 uvicorn Python 子程序監聽。先核對完整命令列、父程序及帳戶，再停止確認的本專案殘留，才備份遷移。沒有中止其他預覽服務；操作程序必須檢查實際監聽，不能只看排程狀態。
- **資料保留檢查：**遷移只有版本／分類表變更。Runtime 初次檢查額外發現 import_jobs 改變，逐列比對確認只有新增一筆正常 completed excel_export、既有 jobs 全相同；檢查器只容許這種預期輸出工作，不放寬其他資料差異。交易全欄位、82 筆、20 個原件 hash 及 Excel／API parity 全 PASS。
- **正式驗收：**私有 HTTPS 九月顯示五色圓環與分類／金額，下鑽與整理入口正常、console 無警告／錯誤。桌面 CSS 1524px／窄螢幕實際 CSS 300px 無橫向溢出；安全保存狀態正常。備份及截圖在 ignored `data/backups/20261001-m13-chart-fix/`。390px 請求未按指定尺寸回傳，不當作實測 390px；實體手機／Mac 未驗收。
- **仍有未分類：**九月 20 筆支出仍待整理，商城及混合商家不能由帳单描述保證商品用途。正式帳本含待決策的舊 CSV 重複；未擅自撤銷，不把畫面正常當完整去重或分類準確率。

### 0.1 Gmail 下載事件逾時，完整附件以 `.tmp` 留在 Downloads

- **證據：** 下載按鈕操作後，瀏覽器 download event 逾時且未回傳路徑；Windows Downloads 卻產生完整的新加密 PDF `.tmp`。最終再次下載中國信託／國泰／永豐，完整檔案分別為 643,152／902,897／743,221 bytes。先前只等事件或找 `.pdf` 的流程會誤報失敗，不能據此認定使用者沒有下載。
- **修復：** `scripts/gmail_attachment_download.py` 先 `prepare` 記錄既有檔與唯一 checkpoint，再於原信呼叫 `scripts/gmail_browser_download.mjs` 先監聽再點指定附件，最後 `collect`（先監聽要求由 0.9 本輪對照補上）。只接受新檔，至少兩秒大小／修改時間穩定、讀取前後一致、PDF header／EOF／strict 結構通過才保存 SHA-256 命名的加密副本及 receipt；不改名或刪除 Downloads 原檔。
- **失敗處理：** 舊檔、`.crdownload`、HTML、截斷檔、超限檔、多檔歧義及遭修改的副本不能冒充成功。預設等待 90 秒、上限 180 秒；checkpoint 十分鐘後失效。無完整新檔即非零退出，先查證 Downloads／附件／介面，再建立新 checkpoint 重試；不盲目連點或繞過瀏覽器安全限制。步驟見 `IMPLEMENTATION_PLAN.md` 4.1。
- **回歸中發現的問題：** Windows 時間戳可能在兩次 `prepare` 相同；單靠時間會讓舊 receipt 被誤接受。改為 UUID checkpoint 與時間雙重綁定，新增同時間戳重測與失效 receipt 測試，完整後端重跑 326 passed。
- **部署後重測：** 中信原郵件按鈕等待 90 秒沒有新檔，檢視器下載等待 30 秒亦無新檔，支援的連結下載工具逾時；這些嘗試不是 PASS。國泰／永豐的原信按鈕各產生新的完整 `.tmp`。中信重新載入來源郵件，觀察到「正在掃描病毒」／disabled，待掃描結束確認 enabled 後重新 prepare／下載，也產生完整新檔。此為實際成功恢復步驟，不足以證實前幾次失敗的内部根因；沒有盲目連點、改安全設定或查受限瀏覽器內部頁。
- **真實驗收：** 用本輪三份新原件及各自 checkpoint／receipt，先確認郵件格式，再於受控 `8031`／`acceptance.db` 走既有收錄、解鎖、分析入口。中國信託／國泰／永豐 1／19／31 列全欄位、摘要合計、API 及冪等核對通過；國泰利息按已批准的明示結帳日認列。結果與加密原件在 Git 忽略的 `data/gmail-acceptance/retest-20260930-1903/`，未保存明文 PDF、全文或秘密。
- **隔離界線：** 驗收腳本先核對 API 隔離識別與 receipt，只從正式 DB 唯讀複製 credential references，SecretStore 禁止寫入／刪除；AI 0 次、confirm 0 次、隔離 Finance 0 筆，不生成隔離 Excel。驗收期間正式 Finance 18 → 18、schema 0012 及全交易 fingerprint 不變；正式 Excel 分類重建另在授權部署驗證，非三銀行自動入帳。
- **剩餘限制：** 本次使用已登入 Gmail 網頁 fallback，不代表 Gmail MCP／cron 或正式入帳驗收。下載事件／最終改名缺失的瀏覽器內部根因仍未證實；沒有停用安全保護或宣稱外部服務永不失敗。PDF 結構完整也不等於來源銀行正確或惡意檔案檢查，仍須後續銀行／帳期／逐列核對。

### 0.2 啟用 SQLite FK 後，安全資料 flush 順序錯誤

- **證據：** 全 suite 有 13 個安全／文件流程失敗，FK constraint 揭露 ORM 未宣告相依關係。
- **修復：** 補上 `DocumentSecurityProfile.secret_profile` 與 `PasswordRuleRecord.document_security_profile` 的 ORM 關係，讓 flush 依 FK 順序執行；未停用 FK 或放寬安全檢查。
- **驗證：** 完整 backend 310 passed；分類 migration forward/downgrade/re-upgrade 與既有 CSV/Statement identity 保留通過。

### 0.3 手機交易列新增分類欄後，長商家被擠成單字換行

- **證據：** 舊 mobile grid 假設四欄；第五欄及分類按鈕 nowrap 使商家可用寬度大幅縮小。
- **修復：** 只對含分類的交易表加入語意 grid areas，分類跨欄、來源／日期明確定位，長標籤允許換行；不重排無關頁面。
- **驗證：** 有／無來源欄回歸測試、桌面與 320px/390px 實際瀏覽器長文字檢查通過。尚未實體手機或 screen reader 驗收。

### 0.4 Windows 前端測試暫存目錄 EPERM

- **處理：** Vitest 與 pytest 使用 `C:/Users/brad/Documents/Codex` 下每次唯一的短 TEMP/TMP 或 basetemp，避免舊權限目錄及過長路徑；不刪除既有未追蹤目錄。
- **驗證：** frontend 29 passed，最新 backend 326 passed；命令見 `README.md`。

### 0.5 完整分類 API 首次延遲仍高於目標

- **量測：** 10,008 筆／50 規則，resolver + aggregation 37.7ms；完整 API 259.6/187.4/185.4ms。500 商家及 filtered pagination 至多 6 queries，沒有每筆交易查詢規則的 N+1。
- **限制：** 首次尚未達 CAT-P01 的 <200ms local 目標。後續先量測 ORM row loading / serialization，評估窄欄位查詢與 SQL filter；不直接加 cache 或 materialized table。

### 0.6 正式網址缺圖與分類：舊 runtime 尚未部署（已處理）

- **證據：** 原 3000／HTTPS 443 有真實資料，但仍提供旧 dist／0011；隔離 3001／8030／8443 不同 DB 的新版測試畫面不能解決正式首頁缺圖。新版 API 不可直接搭配沒有分類表的 0011。
- **修復：** 授權後停止已確認的原排程服務，備份 DB／documents／owned Excel／dist／排程；先對成對副本驗還原與 migration downgrade/re-upgrade，再正式升級 0012、同步 production dist、原 Windows 登入帳戶排程啟動。備份與證據在 `data/backups/20260930-categories-1845/`；未更改 443／8443 Serve 路由。
- **驗證：** 原有全交易、Statement、來源、秘密參照及撤銷資料／文件 hash 保留；18 筆不變。正式分類 API／非空 Donut／分類到來源文件／分類設定、320px／390px 畫面與 owned Excel 全分類／每期 parity 通過。未給正式資料猜分類，因此圓環目前是「未分類」一個區塊，可由使用者在「待分類商家」整理。
- **隔離：** 預覽仍用獨立 synthetic.db；合成來源已撤銷，有效交易 0 筆，SecretStore／Excel 關閉，未自行恢復。正式資料使用 3000／443。
- **限制：** 沙箱 Windows 帳戶曾因 TLS／Credential Manager 環境失敗，正常登入帳戶 HTTPS／安全憑證狀態已重驗；沒有關閉憑證驗證。實體手機／screen reader／重開機仍未驗收，後續新部署仍需當次授權及備份。

### 0.7 圓環全部未分類（M13 已隔離實作，正式部署待授權）

- **證據：** 正式唯讀 API 有 14 類、没有 books，規則／有效單筆 override 為 0；九月六筆支出均未分類且合計與 Dashboard 一致。這是 M12／0012 的觀察，不是最新 M13 resolver；當時只有分類工具、沒有內建用途規則，不證明能辨識真實用途。
- **規劃：** `CATEGORY_SPENDING_PLAN.md` 第 18 節及 TASKS M13 定義 A1-A6：先本機明確規則、圖書與逐筆整理，再決定可選 AI。多用途商家不得套用同一商品類別，預設只改單筆、記住商家前看影響範圍。
- **實作／驗證：** M13 隔離環境已完成 0013／16 類、小型版本化明確 fullmatch 規則、單筆／批次影響預覽及原子確認、Donut 未分類獨立槽位；多用途商家仍未知、人工優先，規則版本／hash／啟停納入 Excel fingerprint，測試／隔離瀏覽器通過。
- **剩餘：** 正式尚未升級，仍可見未分類；A1 人工標註盲測與 A5 正式資料 dry-run／部署待完成。舊 CSV 缺 kind 須以來源核對，不藉分類改金額／日期／類型。未使用消費 AI，也未批准雲端用途。

### 0.8 文件狀態與遠端 taxonomy 衝突

- **證據：** 舊 Groq 計畫將已完成的 S3F-C 列為待辦，部署文件仍把 head 寫成 0012；本機分類實作與遠端六個 MD-only 提交同時修改五份文件。
- **處理：** 先保存實作 commit `90328b0`，正常 merge `origin/main`，逐段保留遠端用途邊界／AUTO-09-10 並同步隔離實作狀態；README 建立文件索引，所有 current／歷史／待驗收資訊分開。
- **停止條件：** 新 head 0013 不可直接重啟正式 0012 服務。Git 整合不等於正式部署／分類套用或三銀行重新驗收；推送結果以 remote SHA 核對，不把本機 commit 當 push 成功。

### 0.9 指定附件只 click 無新檔（已修復／三銀行重測通過）

- **實際範圍：** 2026-10-01 使用已登入 Gmail 網頁，`in:anywhere`、不限日期搜尋；只選中信／國泰／永豐九月信用卡月帳單，不把每日通知、銀行綜合對帳單、證券文件或繳款聯當樣本。三家先讀郵件密碼格式。當前工具清單沒有可呼叫的 Gmail MCP，使用 repository 允許的 browser fallback；不宣稱已完成 MCP／排程。
- **先前失敗證據：** ignored `data/gmail-acceptance/retest-20261001-merge/` 保留三家 checkpoint 與 audit FAIL：指定按鈕 enabled，但 collect 沒有新完整原件，缺 receipt 使驗收非零退出，未進入解密或 parser。重新載入、換正常 Windows 使用者、延長等待均不足以解決；不是解析問題。
- **同來源 A/B/A：** 在同一中信原信、同一可用按鈕，先註冊 `waitForEvent("download")` 再 click，兩次均產生新完整 643,152 bytes 加密 `.tmp`；中間僅 click，沒有新檔、無 receipt。證據在本輪 `download-control.json`。可確定流程缺少預先監聽是本環境中可重現、可修復的操作差異；尚不能確定瀏覽器內部實作、事件逾時或最終改名缺失的原因，也不能承諾外部服務永不失敗。
- **固定流程：** `prepare → downloadGmailAttachment → collect`。Browser helper 限 HTTPS Gmail、唯一可見且 enabled 的指定 PDF 附件，先監聽再點一次，清理失敗 promise，不重點／不輸出 raw error。事件逾時仍 collect；event 或 path 不當完成證明。Python 保留兩秒穩定／PDF header／EOF／strict／SHA-256／唯一 checkpoint，僅複製新加密原件。操作見 IMPLEMENTATION_PLAN 4.1；不能在 click 後才註冊監聽。
- **可診斷失敗：** 每個 label 有 `diagnostic.json`。`no_new_file` 先查監聽順序、原信／登入／指定按鈕及可觀察的下載位置；`pdf_not_ready` 提供進行中、空檔、超限及候選計數；`checkpoint_expired` 需新 prepare 並重新下載。診斷不保存私人檔名、密碼或全文，不拿舊檔／部分 bytes 填驗收；若多檔歧義、瀏覽器保護、權限或登入受阻，停止該來源並交接，不放寬安全檢查。
- **中斷恢復：** 國泰一次因工作中斷超過十分鐘，checkpoint 正確失效；重新 prepare／helper／collect 後通過。不得延長 freshness 或利用舊 receipt 繞過。
- **真實驗收：** 本輪 `data/gmail-acceptance/retest-20261001-download-fix/` 的三個 `*-final/` 各有 fresh checkpoint、加密原件與 receipt；三次事件都未觀察到，實體檔均驗證通過。中信 2 頁／1 列、國泰 3 頁／19 列、永豐 4 頁／31 列，本機解鎖、獨立全列欄位、摘要對帳、API 與冪等均 PASS；國泰 1 列利息依已批准的明示結帳日認列，未捏造來源交易日期。`audit-result.json` 為 `PASS_3BANK`。
- **回歸：** Node helper 7 項測試包含先監聽、逾時／路徑不當 receipt、click 失敗不重試／不洩漏 raw error、來源與按鈕限制；Python collector 20 項含新增診斷及失敗不寫 receipt／不越界。完整 backend 380 passed（2 warnings）、frontend 37 passed、TypeScript／Vite 隔離 build 通過，沒有覆蓋正式 dist。
- **安全與剩餘：** 隔離驗收使用既有 read-only SecretStore／NoExternalAI，外部 AI 0、confirm 0、隔離 Finance 0、不產生隔離 Excel；正式 Finance 18 → 18、fingerprint 與 schema 0012 不變，沒有重啟正式或預覽。這是草稿收錄／解析驗收，不是正式新增入帳、分類盲測、長期自動下載或正式部署。本輪修復尚未 commit／push；未新增 OAuth、讀 cookies、操控受限瀏覽器內部頁或停用安全保護。
- **收尾：** 只停止核對歸屬為本輪的臨時 8031 API，正式 3000／預覽 3002 保留。正式本機與私有 HTTPS 首頁／同源 API 重新實測皆為此產品及 18 筆，Chrome 開啟首頁正常；不冒稱實體手機驗收。

## 1. 歷史範圍（2026-09-29）

本次工作同時完成了三件事：

1. 將免費 AI 密碼規則 provider 的程式、設定頁與驗收狀態更新到文件。
2. 重新執行後端測試、前端 production build，並以一份使用者授權的 Gmail PDF 驗證文件收錄、SHA-256 去重、郵件格式確認、本機解鎖與文字抽取。
3. 接上已驗證的中國信託 Statement parser，完成帳單核對、Finance 冪等匯入與 Excel 重建；同時補上本機來源缺少 Gmail 內文時的規則提示 fallback。

本次不是所有銀行版型或內建 Gmail OAuth 長期自動化的完成驗收。實際完成範圍是「一份實際中國信託帳單已收錄、解鎖、解析、核對、匯入並更新 Excel」；未知版型仍停在待處理。

## 2. 歷史問題與處理

### 2.1 本機分支落後最新遠端文件提交

- **現象：** 接手時本機 `master` 為 `001ca5d`，`origin/main` 已是 `4f9bfb5`；工作區另外有先前未提交的 Groq 程式與文件修改。
- **風險：** 直接 push 會因遠端不是本機歷史的 fast-forward 而失敗；直接 reset、checkout 或覆蓋又可能遺失既有實作。
- **處理：** 保留工作區修改，先讀取並以目前程式行為校正文件；完成本地 commit 後再把 `origin/main` 整合進來，最後以明確的 `master:main` 推送。
- **結論：** 本次以不覆蓋遠端歷史的 merge 方式整合；Groq 實作 `eeb6883` 已進入 `main`。使用者之後再次 push 得到 `Everything up-to-date` 且回報 local working tree 乾淨。不可再把「Groq 仍只存在本機未提交」當目前狀態。

### 2.2 Git 權限與 Credential Manager 行為

- **現象：** repository 所有權與目前執行環境的 Git 安全檢查不一致；一般 Git 操作可能出現 `dubious ownership`，第一次遠端讀取也曾受到 Git Credential Manager/Windows 憑證存取限制影響。
- **處理：** 只對這個 repository 使用 `-c safe.directory=C:/Users/brad/Documents/Codex/family-finance-hub` 執行必要的 Git 查詢、fetch、commit/push；未修改全域 Git 設定，也未索取或寫入使用者 token。
- **安全界線：** push 只能使用既有的 Windows Credential Manager 登入狀態；若憑證不可用，不應把 PAT 或 API key 貼到聊天、`.env` 或 repository。

### 2.3 pytest 暫存目錄權限錯誤

- **第一次現象：** 使用 `--basetemp backend/.test-tmp/free-ai-status` 時，大量測試在 setup 失敗，錯誤為 Windows `WinError 5` `PermissionError`；失敗數為 110，並不是測試 assertion 失敗。
- **原因：** 指定的 backend 暫存目錄受到 Windows 目錄權限/既有擁有者限制，pytest 無法建立測試隔離目錄。
- **第二次現象：** 改到 repository 根目錄的 `.pytest-tmp/free-ai-status` 時，父目錄尚不存在，錯誤改為 `WinError 3` `FileNotFoundError`。
- **處理：** 只在 repository 根目錄建立測試用父目錄，重跑：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp .pytest-tmp\free-ai-status
  ```

  測試完成後刪除這個只由本次產生的暫存目錄，避免未追蹤檔案進入 commit。
- **最終結果：** `187 passed`、2 個既有 FastAPI/anyio 相依套件棄用警告；沒有測試失敗。

### 2.4 UI 預設 provider 與實際已保存 provider 不一致

- **現象：** 程式與設定頁已加入 Groq，UI 預設為 Groq + `openai/gpt-oss-20b`；但現場服務 API 仍回報已保存的 `openai` / `gpt-4.1-mini` profile。
- **原因：** UI 預設值只是新設定的預填，不能為了切換 provider 自動覆寫 Windows Credential Manager 中既有的 profile。這是避免無提示改變外部 API 用量與秘密設定的安全行為。
- **處理：** 文件明確寫出「必須在設定頁選擇 Groq、輸入 key、按保存」，並保留 OpenAI 只有使用者明確選擇時才可用的路徑。
- **目前限制：** Groq 程式已在 `main`，但最後一次有證據的 runtime 仍是 OpenAI。只有完成 safe-switch、重新讀取 Active Provider，並跑過真實 synthetic Groq request，才可宣稱 runtime 已切換。

### 2.5 內建 Gmail OAuth 與 Gmail 網頁操作不是同一條連線

- **現象：** 使用者可在 Gmail 網頁看到並下載授權的 PDF，但 FamilyHub 的內建 Gmail OAuth 狀態仍未設定/未授權。
- **原因：** Gmail 網頁登入、ChatGPT/Gmail app 連線與 FamilyHub 自己保存的 readonly OAuth token 是不同的授權邊界，不能互相推定已連線。
- **處理：** 本次只把 Gmail 網頁下載的 PDF 交給 FamilyHub 文件入口；沒有把它記成內建 Gmail scheduler 已成功抓取，也沒有改寫 FamilyHub OAuth 設定。
- **當時後續／現已取代：** 這是改用 Codex MCP 前的 OAuth 路線；2026-09-30 起不再要求 FamilyHub OAuth，長期驗收改由 Codex connector／外部排程進行。

### 2.6 真實 PDF 的 AI 路徑受阻，但明示規則可在本機解鎖

- **現象：** 實際開啟收錄的 PDF 時，runtime 使用既有 OpenAI profile，AI 預覽因帳戶額度不足停止。
- **原因：** live runtime 啟動早於最新明確規則 parser，第一次預覽沿用既有 OpenAI profile；Groq 尚未在本機保存 key，系統也不會偷換 provider。
- **處理：** 先在來源 Gmail 郵件確認其明確列出的兩種客戶格式，再由目前 parser 產生受限候選規則；規則不含秘密。因 live process 尚未重啟，先把該規則寫入 verified cache，關閉 AI 後由 live processor 與 Windows SecretStore 嘗試，沒有把帳單或個人資料送給 AI。
- **目前結果：** 同一份 Gmail 下載 PDF 已成功解鎖；原始檔為加密，輸出為未加密 2 頁 PDF，文字抽取可用。成功後 cache 只保留真正命中的規則，驗證用明文輸出已刪除，Finance transaction 仍為 0。
- **後續：** 正式 migration/restart 後重驗動態 parser 路徑。真實 Groq request 可另行驗收，但不再是這種郵件已明示格式的解鎖前置；下一個產品關卡仍是銀行 parser 與人工對帳。

### 2.7 文件去重成功，但不代表交易解析完成

- **現象：** 同一份 PDF 第一次收錄成功；以相同 bytes 再次收錄回報 `duplicate=true`。
- **處理：** 保留 SHA-256 idempotency，避免重複文件或重複交易；文件詳情仍顯示 0 筆交易。
- **重要區分：** Documents 收錄、PDF 解鎖、Statement parser、Finance 入帳、Excel 投影是不同階段。沒有經銀行 parser 與人工核對的交易，不得因文件已存在就寫入 Excel。

### 2.8 HANDOFF 與舊文件曾有互相矛盾的驗證數字

- **現象：** 舊交接文字同時留下 167/173/181 等前輪測試數字，也曾寫成「未重新下載 Gmail 附件」；這些描述會讓後續模型誤判目前狀態。
- **處理：** 在當時「只有文件收錄／解鎖、尚未入帳」的階段，以實際命令與服務回應校正文件；後續本次 Statement 里程碑已再更新為「中國信託帳單完成核對、Finance 匯入與 Excel 重建」。最新完整 backend 為 207 passed。
- **規則：** 歷史測試數字可保留作歷史，但目前狀態只能引用本次可重跑的命令與結果；不能把合成測試當成真實銀行驗收。

### 2.9 Git 行尾提示不是程式錯誤

- **現象：** `git diff --check` 通過，但 Git 顯示工作區 LF 下次可能轉成 CRLF 的提示。
- **判斷：** 這是 Windows checkout 的行尾轉換提示，不是測試、build 或安全失敗。
- **處理：** 不做與本次需求無關的全 repo 格式化；保留現有 `.gitattributes`/Git 行為，只確認 diff 沒有 whitespace error。

### 2.10 本機來源缺少 Gmail 內文，導致解鎖提示不可自動取得

- **現象：** 實際帳單已保存在 Documents，但該筆來源只有 `local_file`，沒有可讀的 `gmail_attachment` message context；即使 Windows Credential Manager 已保存個人解鎖資料，分析 API 仍會回報缺少郵件密碼提示。
- **處理：** 沒有把銀行規則硬編碼到 parser；後端分析 API 支援非秘密的 `subject`/`body` context，文件詳情 UI 只在本機來源顯示「郵件中的密碼規則提示」欄位。使用者只需提供規則文字，不得貼實際密碼。
- **結果：** 以不含個資、密碼的規則提示完成同一份實際中國信託帳單解鎖；parser 解析 1 筆交易列且與帳單合計相符，確認後建立 1 筆 Finance transaction。再次確認回報 `reused=true`。

### 2.11 Excel 輸出與舊 writer 測試契約仍有落差

- **現象：** 新版工作簿已包含信用卡交易欄位，完整 backend suite 仍有 3 個既有 `test_xlsx_writer.py` assertion 使用舊工作表順序／欄數。
- **處理：** 沒有為了讓測試通過而回退新的 Statement 欄位；保留失敗證據，後續獨立同步 writer 測試契約。
- **結果：** 已將測試契約同步至信用卡專用工作表與 15 欄交易明細；完整 backend suite 重新通過。
### 2.12 Groq 程式已合併，但 runtime 尚未等同 Groq

- **現象：** Groq adapter、provider API/UI 與合成測試都已在 `main`，但最後一次有證據的 runtime smoke check 仍使用 OpenAI / `gpt-4.1-mini`。
- **原因：** UI 的 Groq 預設只是 Recommended / new-setup Default；真正 runtime 由 backend 的 Active Provider + Windows SecretStore credential 決定。
- **規則：** 只有重新讀取 `/api/security/ai-provider` 並完成真實 synthetic Groq request，才可宣稱 runtime 已切 Groq。

### 2.13 Provider 切換缺少 preflight

- **現象：** `AIProviderService.configure()` 會保存新設定、更新 DB profile，之後清理舊 credential，但不先驗證新 provider/model。
- **風險：** credential 輸入錯誤、模型下架、權限不足或 Structured Output 不相容，都可能到第一次真實 request 才發現。
- **處理方向：** 先增加固定 synthetic prompt 的 Test Connection / preflight，不讀 Gmail/個資、不保存新設定；只有 preflight 成功才切換 Active Provider。失敗時舊 provider 保持可用。
- **範圍：** 仍維持單一 Active Provider；不做自動 fallback chain。

### 2.14 AI provider status 可能誤報 configured

- **現象：** `GET /api/security/ai-provider` 目前只檢查 DB profile 是否存在；若 DB row 還在但 Windows SecretStore credential 遺失，UI 仍可能顯示已設定。
- **風險：** 使用者在真正解鎖 PDF 時才發現 provider 不可用。
- **處理方向：** status API 應安全區分 profile 存在與 credential 可用，例如增加 `credential_available`，但絕不回傳 credential 本身。SecretStore 整體不可用時應明確 fail closed。

### 2.15 Provider UI 狀態不夠明確

- **現象：** 設定頁狀態徽章目前主要顯示 model，沒有直接寫出 Active Provider。
- **風險：** 容易把「表單預設 Groq」誤認為「目前正在使用 Groq」。
- **處理方向：** 顯示「目前使用：Provider · Model」，並拆成「測試連線」與「保存並切換」兩個動作。

## 3. 歷史驗證結果（非目前測試數字）

| 項目 | 結果 | 備註 |
| --- | --- | --- |
| Backend tests | 通過 | 207 passed；2 個既有 FastAPI/anyio 相依套件棄用警告 |
| Frontend build | 通過 | `npm --prefix frontend run build` |
| Git diff check | 通過 | 未發現 whitespace error |
| Groq provider code path | 通過合成驗證 | 真實 runtime activation 尚未完成；不得由 UI 預設推定 |
| Provider safe switch | 未完成 | Test Connection/preflight、credential health status、Active Provider 顯示待補 |
| Gmail PDF 文件收錄 | 通過 | 使用 Gmail 網頁手動下載，不是內建 OAuth scheduler |
| SHA-256 重複收錄 | 通過 | 第二次收錄 `duplicate=true` |
| PDF 本機解鎖 | 通過 | 真實 Gmail 下載加密 PDF；郵件明示規則、AI 關閉 |
| Groq 真實 request | 未完成 | key 尚未保存；不是本次明示規則解鎖的前置 |
| BankStatementParser | 部分完成 | 中國信託版型已由實際帳單驗證；受限台新零交易版型有測試；其他版型與第二期盲測待完成 |
| Finance transaction / Excel 入帳 | 通過（限定範圍） | 實際中國信託帳單已核對、冪等匯入並重建專用 Excel |

## 4. 歷史後續清單（目前交接以 HANDOFF.md 為準）

1. 先讀 `HANDOFF.md`、`FREE_AI_PASSWORD_RULE_PLAN.md` 與本文件，不要只看 UI 的 provider 預設值。
2. 以設定 API 或設定頁確認實際 runtime provider/model；不要假設已保存 Groq key。
3. 正式 migration/restart 後重驗來源郵件到明確規則的動態路徑；若另外驗證 Groq，先用合成提示，不要在聊天傳送 key、身分資料、生日或 PDF 密碼。
4. 執行 pytest 時使用 repository 根目錄下可寫的暫存目錄，避免重用受 Windows 權限保護的 backend 暫存路徑。
5. 後續做第二期盲測與其他已授權版型驗收；push 前檢查 `git status`、`git diff --check`、測試與 build；不要用 reset/checkout 覆蓋既有修改。
