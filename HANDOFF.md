# 家庭收支記錄交接

更新：2026-10-01。先讀 AGENTS、README、TASKS、IMPLEMENTATION_PLAN；分類規格以 CATEGORY_SPENDING_PLAN 為準。本文只保留現況與下一步，歷史交給 Git。

## 本次 Git 交付

- 使用者明確要求「整理好推上 git 並且 merge」。範圍是既有下載修復、分類圖表修正、正式部署文件與交付驗證，不再重啟／遷移正式服務、不撤銷來源、不自動分類未知交易。
- 起始本機 `master`／遠端 `main` 同為 `2061e99`；正式網路 fetch 已確認沒有待整合提交。提交後仍須再次 fetch，正常 merge `origin/main`，以 `git push origin HEAD:main` 發布並核對 remote SHA。若遠端未新增提交，Already up to date 是正確結果，不製造空 merge。
- 只提交明確程式／測試／文件路徑；原有未追蹤 `pytest-of-brad/`、`tmpe9fanwiq/` 保留。帳單、DB、工作簿、下載收據、秘密、dependencies、build 及 ignored 驗收證據不得加入 Git。

## 最新驗證

- 完整 backend：**399 passed，2 warnings**（52.05 秒）；警告為既有 Starlette/httpx／anyio 棄用訊息。frontend：**38 passed**；Node 下載 helper：**7 passed**。
- TypeScript／Vite build 成功，輸出 `frontend/dist-category-preview`；與既有正式 build 雜湊相同，沒有覆蓋正式 dist。
- 本次收尾唯讀確認本機 3000 與正式私有 HTTPS 首頁皆為「家庭收支記錄」／`index-CstSTstV.js`，同源 Finance API 皆為 82 筆；13 份 tracked Markdown 的 38 個本機檔案連結、衝突標記與 diff 格式檢查通過。沒有冒稱實體手機驗收。
- **本次 E2E-GMAIL-3BANK：PASS 3/3。** 沒有可呼叫的 Gmail MCP，使用已登入 Chrome Gmail fallback。查詢以 `in:anywhere` 搭配銀行／信用卡／帳單／PDF 關鍵字，不限收信日期；實際驗所選 2026-09 月帳單，不宣稱審完所有郵件。
- 三家均先讀當次原信密碼格式，再 prepare → 先監聽下載事件 → 單次點指定可用 PDF 按鈕 → collect；本次新 checkpoint／receipt、stable bytes／strict PDF／EOF／SHA-256 全通過，不取舊檔代替。瀏覽器仍未回傳事件，但新完整加密 PDF 以 `.tmp` 留在 Windows Downloads。
- 中信 **1 列／2 頁**、國泰 **19 列／3 頁**、永豐 **31 列／4 頁**：本機解鎖、銀行／帳期、獨立逐列全欄位與摘要對帳、API／重複收錄與分析全 PASS。國泰一列利息依既有批准以明示結帳日認列，原始無交易日仍保留。
- ignored 證據：`data/gmail-acceptance/retest-20261001-git-delivery/` 的加密原件、checkpoint、receipt、`cases.json` 及 `audit-result.json`。不保存解密全文、身分資料、生日、密碼或私人郵件連結。
- 隔離 Finance／confirm／外部 AI 均 0、無隔離 Excel；正式 Finance **82 → 82**、交易 fingerprint／schema **0013_category_taxonomy** 不變。驗收後核對命令列只停止本次臨時 API 8031，正式與其他預覽服務保留。這是收錄與草稿解析驗收，不是正式新增入帳、分類品質盲測、Gmail MCP 排程或第二期盲測。
- 每次交付仍須當次重跑三銀行；前輪 FAIL 保留，不以本次 PASS 改寫歷史。

## 已完成與正式狀態

- Documents 共用底層、SHA-256／來源冪等、Jobs、generic Finance CSV、Statement 草稿／正規化／原子確認、可恢復來源撤銷與 Excel 專用投影已實作。
- 網站 Gmail OAuth UI／scheduler 預設停用；Codex MCP 或已登入網頁負責收件，網站只接收本機收錄／解析。收錄與 confirm 分開，不因下載成功自動入帳。
- M13 A2／A3 已正式部署：16 類 taxonomy、版本化本機明確規則、Donut／Category → Merchant → Transaction 下鑽、逐筆／批次預覽確認與 Excel 分類。規則版本 `2026-10-01.2`，人工 override／使用者規則優先；費用／退款語意優先，多用途商家／支付平台不猜用途。
- Donut 最多六片，正額未分類獨立保留，負淨額另列退款／抵扣，幣別不混加。補初始尺寸、待分類筆數／整理入口及 body 最小寬度的窄螢幕溢出。
- taxonomy migration 保留自訂名稱、ID、引用與交易事實；批次最多 50 筆，確認時原子重算預覽 token，stale／撤銷／錯誤拒絕整批，保護人工例外。
- 正式由原 `FamilyFinanceHub` 互動式登入排程使用正常 Windows 帳戶啟動；安全保存狀態顯示身分證／生日皆已保存，沒有修改秘密或 provider。
- 正式 schema 已依前輪授權升至 0013，**82 筆交易與 20 個原件保留**；owned Excel 82 個唯一 ID、核心欄位／分類及月分類合計與 API 相符。唯一 ID 不代表語意去重。
- 正式 build：`index-CstSTstV.js`／`SpendingByCategory-55ht5RAW.js`／`index-BFE7AgX_.css`。前輪 Chrome 九月五色圖、下鑽與整理入口正常、console 無警告／錯誤；桌面 CSS 1524px／窄螢幕實際 CSS 300px 無橫向溢出。390px 工具請求未按指定尺寸回傳，不能冒稱正式已驗 390px；實體手機／Mac／screen reader 未驗收。
- 成對備份與部署證據：ignored `data/backups/20261001-m13-chart-fix/`，包含一致性 DB、20 文件、Excel、舊 dist、排程 XML、後端 source、M12 相容程式封存及截圖。副本 upgrade／downgrade／再 upgrade 已驗；正式只 upgrade。啟動時只新增正常 completed excel_export job，既有 jobs 保留。

## 環境與啟動

| 環境 | 本機入口與資料 | 私有 HTTPS |
| --- | --- | --- |
| 正式日常服務 | 127.0.0.1:3000；`data/family-finance-hub-live.db`，0013、暫 82 筆；既有 Windows 排程 | `https://desktop-vcgfqnq.tailb47104.ts.net/`，443 → 3000 |
| 舊 M12 合成預覽 | 前端 3001 → API 8030；`data/category-preview/synthetic.db`，來源已撤銷、有效 0 筆，不恢復 | `https://desktop-vcgfqnq.tailb47104.ts.net:8443/` |
| M13 合成預覽 | 前端 3002 → API 8032；`data/category-preview-20261001/synthetic.db`，0013、18 筆，SecretStore／Excel 關閉 | `https://desktop-vcgfqnq.tailb47104.ts.net:8444/?month=2026-09` |
| 當次三銀行驗收 | 臨時 API 8031；當次專用 ignored acceptance.db，秘密只讀、AI 禁止 | 無 Serve 路由 |

Serve 路由不啟動程式，裝置須加入同一 Tailscale，服務須持續運行。保留既有路由，不 reset Serve、不啟用 Funnel。本機／HTTPS 測試不代表實體手機驗收。

預覽埠均已使用，不重複啟動。重新啟動前先查程序／命令列／埠，只有確認空閒且屬於本專案才使用：

```powershell
./scripts/start_category_preview.ps1 -MobileHostname desktop-vcgfqnq.tailb47104.ts.net -FrontendPort 3002 -BackendPort 8032 -DataName category-preview-20261001
```

正式啟動沿用 `scripts/start_server.ps1` 與既有排程／live.db 設定，指令見 README／docs/operations；此啟動器不自動 migration。未來正式升級／回退另取當次授權、成對備份及相容程式／schema 副本驗證；停止排程仍可能殘留 Python 子程序，不得以不分專案的 kill 清理。

## 仍有缺口

- 最近兩個完整帳期暫按 **2026-08／2026-09** 收集；8 家、14 份候選中，11 份新附件已下載，3 份僅連結受官方登入／CAPTCHA 限制。沒有保證所有銀行均已寄出；不能把部分收集說成全部完成。
- 六份信用卡原件已在正式 Documents；中信九月原有 1 筆，國泰九月 19、永豐九月 31、永豐八月 14 已正式入帳。國泰八月已解鎖但列值不可靠維持 pending；玉山八月原信未明示開啟格式，不猜密碼。
- **正式舊國泰九月 CSV 17 筆與新原件有日期／金額／幣別重疊，12 筆正規化描述相同。82 筆 Dashboard／Excel 含語意重複風險。**尚未取得撤銷同意，不能自動刪。若批准，重新取 import-impact token、可恢復撤銷舊 CSV，再核對 65 筆、來源保留與 Excel。
- 五份銀行綜合對帳單在本機按原信格式解鎖，但 SHA 對應正式文件先前已撤銷；未取得恢復同意、不恢復或套信用卡 parser。銀行交易 parser 尚未驗證，不把轉帳／餘額當消費。
- 富邦八／九月信用卡須官方身分驗證／CAPTCHA、國泰八月銀行對帳單須 CUBE 登入；必要人機／身分驗證交給使用者，不繞過。
- 九月仍有 **20 筆支出待分類**；未知商家需人工提供用途。分類 A1 人工標註 precision／coverage 盲測未完成，A4 可選雲端 AI 未授權，A5 人工整理與語意重複待決策，M13 不全勾。
- Codex Gmail 首次自動收件／至少一次重跑與跨日離線補抓、第二期 parser 盲測、Groq／OCR 真實 runtime、重開機持續服務、實體手機／輔助工具及冷啟動效能仍待驗。設定存在不能當 runtime 通過。

## 下一步與安全邊界

1. 先取得舊 CSV 撤銷、已撤銷銀行文件恢復、帳期範圍及富邦驗證頁決策；未批准保持現狀。
2. 修國泰八月 parser 時只針對真實失敗輸入，保留逐列／摘要對帳閘門；玉山先補原信明示密碼格式。
3. A1 真實人工標註與未參與規則調整的第二期盲測分開；報 precision／coverage／待確認率，不把未知當成功。
4. 秘密只在 Windows Credential Manager／SecretStore；本機安全組合，不讀出或保存秘密、全文／PII 不送 AI。僅 interest + 明示 closing_date 可沿用既有批准認列；其他缺日期、未知列或對帳不符維持 pending。
5. SQLite 是事實來源、Excel 是 owned 可重建投影；保留 Documents 1:N、SHA-256、原子入帳及可恢復撤銷。下載 helper 的監聽／collect 已有回歸測試，但不能承諾外部服務永不失敗。


## Secure Documents Skill v0.1（2026-10-02）

- 新增 `skills/secure-documents/` 實驗性獨立 Skill/package；目的為文件種類無關的安全 PDF unlock + native extraction → `DocumentIR`，不是信用卡銀行白名單，也不是新的 Dashboard。
- 保留安全邊界：PasswordRule 只含 symbolic secret reference；實際 national ID／birthday／PDF password 不進 repo、IR 或 model prompt；最多 3 個本機候選，解密只在 memory，Windows Credential Manager adapter 為 read-only。
- 包含 `SourceDocument`、`UnlockResult`、`DocumentIR`、`ExtractedFact+Evidence` contract、local PDF adapter、Family Dashboard credential-reference 唯讀匯入、CLI、PowerShell 入口及 regression tests。
- 本輪隔離生成物已實跑 `pytest -q`：**6 passed**，另通過 `python -m compileall -q src`。測試含 synthetic encrypted PDF，驗證可由 symbolic rule + local in-memory secret 解鎖且 IR 不洩漏候選值。
- **未驗證**：此執行環境不是使用者的 Windows 登入 session，因此尚未真實讀取該主機 Windows Credential Manager，也未拿真實加密文件跑 Skill；本輪亦未重新執行 Family Dashboard 的 E2E-GMAIL-3BANK。故此項為 prototype merge，不宣稱正式 runtime / 真實 Gmail 交付已驗收。
- 此變更沒有啟動/重啟正式服務、沒有 migration、沒有修改 live DB、沒有寫入 Finance/Excel，也沒有修改任何 secret/provider。
- 2026-10-03 補上 Codex repo-scoped discovery：`.codex/skills/secure-documents/SKILL.md` 是薄入口，canonical implementation 仍只有 `skills/secure-documents/`；canonical `SKILL.md` 已加入標準 front matter。這只改善 Codex 發現/載入，不等於 Windows Credential Manager 真機驗收。
