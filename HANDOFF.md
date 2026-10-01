# 家庭收支記錄交接

更新：2026-10-01。先讀 AGENTS、README、TASKS、IMPLEMENTATION_PLAN；分類以 CATEGORY_SPENDING_PLAN 為準。本文描述目前狀態，歷史交給 Git。

## 本輪範圍與 Git

- 使用者本次要求整理所有文件、推送與 merge。已檢查全部 13 份 tracked MD 與程式／設定，統一實作、隔離驗證、待驗收與歷史紀錄；不新增產品功能。
- 先將既有 M13 A2／A3 實作保存為 `90328b0`，再正常 merge 遠端 `main @ 430ef5c` 的六個 MD-only 提交。五份文件衝突逐段整合，保留遠端 taxonomy 邊界及 AUTO-09／10 測試要求，不 reset／rebase／force push。
- 本次 Git 操作有明確授權；不包含正式 migration／部署、正式 confirm／撤銷／恢復或交易描述送外部 AI。Git 更新不等於正式服務已升級；發布 SHA 與整合後驗證見下節。
- 原有未追蹤 `pytest-of-brad/`、`tmpe9fanwiq/` 保留；data、Downloads、DB、帳單、工作簿、秘密、build 與 dependencies 不加入 Git。

## 已實作：M13 A2／A3

- `0013_category_taxonomy`（down_revision 0012）：新增圖書／保險，16 類 taxonomy，改舊預設顯示名稱與排序；保留自訂名稱、ID、引用及所有交易事實。upgrade／downgrade 在副本測試，正式仍為 0012。
- `finance/categories/builtin.py`：小型版本化完整比對規則，只處理描述明確的外送、串流、交通、圖書、學費、保費、醫療或機票。多用途商家／支付平台維持未分類，不從泛稱商家猜商品。
- 優先序：單筆 override > 使用者 exact > 使用者 contains > system semantic > 內建明確規則 > 未分類。API 提供分類理由／規則 ID；版本、內容 hash、啟用狀態與分類設定進入 Excel fingerprint。關閉開關為 `FAMILY_FINANCE_HUB_BUILTIN_CATEGORY_RULES=false`。
- Donut 最多六片；正額未分類獨立保留，不能藏入「其餘」。負淨額另列退款／抵扣，幣別不混加。
- 整理流程顯示每筆真實日期、金額與來源，預設只改單筆。記住商家先預覽跨月影響與人工例外；預覽 token 防止過期確認。
- 批次最多 50 筆，先選真實交易再選類別及預覽；SQLite `BEGIN IMMEDIATE` 下重算 token、一次原子寫入。包含停用類別的人工 override 均受保護；錯誤／撤銷／過期預覽拒絕整批，途中失敗完整 rollback。不自動建立商家規則。
- `category_preview.py` 僅接受 data 下專用 category-preview 目錄；schema migration 不受外部正式 DB 環境變數誤導。18 筆合成資料不進正式帳本，撤銷來源不因重啟被恢復。啟動器可指定前後端埠與資料目錄，占用或不能查埠時拒絕啟動，不停止既有服務。

## 分類實作驗證結果（2026-10-01）

以下是文件整理前的分類實作驗證，不自動代替本次 Git 整合關卡。

- 完整 backend：**376 passed，2 warnings**，兩個既有 Starlette/httpx／anyio 棄用警告。
- Frontend：**37 passed**；TypeScript／Vite build 成功，輸出 `frontend/dist-category-preview`，沒有替換正式 dist。
- 覆蓋 taxonomy migration／引用保留、明確與多用途反例、人工優先與停用 fallback、Excel fingerprint／parity、商家預覽 stale token、批次拒絕／原子 rollback、非消費及缺失交易拒絕。
- 隔離 API／合成 CSV 逐列核對；撤銷來源重新啟動後仍為 0，不復活資料。
- 預覽啟動器通過 PowerShell 語法、占用埠拒絕，以及臨時 3003／8033 的真實啟動／同源 API 測試，16 類／18 筆相符；僅停止確認為本輪建立的臨時程序，未動正式或 M13 預覽。
- 真實瀏覽器驗過桌面、CSS 320px／390px Donut、逐筆與批次實際操作；沒有對話框文字溢出。預覽總額維持 TWD 10,205／USD 25 分開計算，未知 7-ELEVEN 保留；不是實體手機或螢幕閱讀器驗收。
- 這些技術測試不是分類 precision／coverage 的真實盲測，M13 尚未全部完成。

## 2026-10-01 分類實作驗收：Gmail 三銀行 PASS 3/3

該次沒有可呼叫的 Gmail MCP 工具，依 repository 允許的 fallback 使用已登入 Gmail 網頁。搜尋 `in:anywhere has:attachment filename:pdf {subject:信用卡 subject:帳單 subject:對帳單}`，沒有日期篩選，可涵蓋可存取最早信件至當下；實際驗所選九月月帳單，不宣稱逐封審完整個信箱。

| 銀行／帳期 | 新下載、郵件提示、解鎖 | 全列與摘要核對 | 冪等 |
| --- | --- | --- | --- |
| 中國信託／2026-09 | PASS，2 頁 | 1 列，原文／parser／API 一致 | PASS |
| 國泰世華／2026-09 | PASS，3 頁 | 19 列；1 列利息按已授權明示結帳日認列 | PASS |
| 永豐／2026-09 | PASS，4 頁 | 31 列，含退款／繳款／費用／本期分期額 | PASS |

- 三家均先讀原信密碼格式，再走 `prepare → 指定附件下載 → collect`，取得新原件；不是拿舊 Downloads 補驗收。
- 國泰曾無新檔，未當 PASS；離開原信再開啟、等掃描完成及按鈕可用、重建 checkpoint 後成功。瀏覽器內部根因未證實，不承諾永不失敗，也不關閉下載保護。
- 新加密原件經穩定時間、strict PDF／EOF、SHA-256、唯一 checkpoint／receipt 核對，bytes 為 643,152／902,897／743,221。未保存解密 PDF、全文或秘密。
- 本機 ignored 證據：`data/gmail-acceptance/retest-20261001-taxonomy/`，`audit-result.json` 為 `PASS_3BANK`。
- 驗收完成後已停止確認歸屬的臨時 8031 API；正式與 M13 預覽保持健康。下次驗收另啟隔離 API，不沿用舊 PASS。
- 使用專用 8031 acceptance API，SecretStore 只讀正式 credential references，禁止秘密寫入／刪除，外部 AI 關閉；依實際郵件提示走既有 Codex import 邊界，沒有手動密碼／提示 override。
- 隔離 Finance 0、confirm 0、外部 AI 0，未產生隔離 Excel。正式 Finance **18 → 18**、交易 fingerprint 及 schema **0012** 不變。
- 此結果不是分類盲測、正式新增入帳／Excel、MCP 排程或第二期 parser 盲測驗收。後續程式交付仍須當次新下載三銀行，不永久沿用 PASS。

## 本次文件整理與 Git 整合驗證

- 13 份文件已整理；README 提供完整索引，TASKS 保留未完成項目，舊審查／測試數字明示日期。
- 已修正 Groq safe-switch 過時待辦、legacy OAuth 歷史狀態、M13／正式 M12 差異及可能誤重啟正式服務的指令。
- 整合後重新跑完整 backend：**376 passed，2 warnings**（33.42 秒）；frontend：**37 passed**（2.80 秒），TypeScript／Vite 隔離 build 成功。沒有覆蓋正式 dist。
- 13 份 tracked MD 的 38 個本機檔案連結、3 個章節錨點均通過；沒有 merge conflict markers 或 diff whitespace errors。Alembic 唯讀 heads 為 `0013_category_taxonomy`。
- **本次 E2E-GMAIL-3BANK：BLOCKED，audit 為 FAIL，不能交付成當次三銀行 PASS。** 三家九月原信與密碼規則均已重新閱讀，分別 prepare／按指定帳單附件／collect；國泰另做重新載入、更新 checkpoint、正常 Windows 帳戶 collect 與可見附件連結下載。沒有任何新穩定完整 PDF；未拿旧 Downloads 或上節 taxonomy 原件代替。
- 本輪證據在 ignored `data/gmail-acceptance/retest-20261001-merge/`：三家 checkpoint、隔離 server log 及 `audit-result.json`。collect 均 `DownloadNotReady`；receipt 缺失使 acceptance 明確非零退出／`FAIL: FileNotFoundError`，未進入文件收錄／解密／parser；這不是 parser 失敗。瀏覽器內部根因未證實，詳見 EXECUTION_ISSUES 0.9。
- 臨時 8031 acceptance API 已停止；沒有新正式入帳、秘密變更、外部 AI 或 Excel 輸出。正式 API 仍 18 筆；正式服務與合成預覽未重啟。
- 本次唯讀核對正式 3000／HTTPS 443、預覽 3002／HTTPS 8444，首頁 title 均為家庭收支記錄；預覽同源 API 18 筆、瀏覽器非空 Donut／圖書／保險／未知類別正常。實體手機未測。
- 正常 merge 保留 `90328b0` 與 `430ef5c` 的雙方歷史；以 `git push origin HEAD:main` 發布。發布後須核對 `git ls-remote origin refs/heads/main` 與本機 HEAD 相同，實際 commit／遠端核對結果見此次交付回覆及 Git log。Git 同步不等於真實驗收或正式部署完成。

## 執行與資料隔離

| 環境 | 本機入口 | SQLite／用途 | 私有 HTTPS |
| --- | --- | --- | --- |
| 正式日常服務 | 127.0.0.1:3000，既有 FamilyFinanceHub 排程 | `data/family-finance-hub-live.db`：0012、18 筆；既有正式 dist／Excel | `https://desktop-vcgfqnq.tailb47104.ts.net/`，443 → 3000 |
| 舊 M12 預覽 | 前端 3001 → API 8030 | `data/category-preview/synthetic.db`：有效 0 筆，來源已撤銷；不可自行恢復 | `https://desktop-vcgfqnq.tailb47104.ts.net:8443/` |
| M13 隔離預覽 | 前端 3002 → API 8032 | `data/category-preview-20261001/synthetic.db`：0013、18 筆合成；秘密／Excel 關閉 | `https://desktop-vcgfqnq.tailb47104.ts.net:8444/?month=2026-09` |

分類實作驗收已確認 M13 本機及私有 HTTPS 為此產品，保留原 443／8443 路由，沒有 Funnel。實體 Mac／手機未驗收；Tailscale 路由不會啟動程式，預覽仍須保持執行。

若指定埠空閒才啟動：

```powershell
./scripts/start_category_preview.ps1 -MobileHostname desktop-vcgfqnq.tailb47104.ts.net -FrontendPort 3002 -BackendPort 8032 -DataName category-preview-20261001
```

腳本只用合成 DB，自動 migration 不得改為正式用途。目前埠已運行時不要重複啟動。網站同源代理 API、只 bind loopback；手機路由註冊沿用全域 register-mobile-preview.ps1，不能重設 Serve 或覆寫其他路由。

## 正式部署停止條件與安全

- 正式程式與 DB 仍在 M12／0012；目前新程式 head 為 0013，**不得直接重新啟動正式服務**。先取得當次升級授權，成對備份、副本 migration／回退、同步 build，再由正常登入 Windows 帳戶啟動並唯讀核對全欄位／Excel。
- 上次成對備份與部署證據保留於 ignored `data/backups/20260930-categories-1845/`（DB、原件、owned Excel、舊 dist、排程與程式基準）。不對正式 DB 自行 downgrade，不清空來源或覆蓋非本系統工作簿。
- Codex 收錄與分析／confirm 入帳分開；Gmail OAuth／scheduler 預設停用。秘密只在正常 Windows 使用者 Credential Manager／SecretStore，不進 SQLite 普通表、log 或設定檔。
- 未列日期只有 interest + 明示 closing_date 可依既有批准認列；其他缺日期／未知列／對帳不符維持 pending。Parser 支援限已驗證的銀行文字版型，不能宣稱通用。
- 本輪分類沒有外部 AI 請求或 provider 切換。Groq 真實 activation 仍待驗；設定／credential 存在不代表額度或 runtime 成功，不允許付費 fallback 或 PII／全文傳送。
- SQLite 是事實來源，Excel 是專用可重建投影；保留 Documents 1:N、SHA-256、撤銷／恢復與原子入帳。不同 bytes 的語意重複仍未自動判定。

## 下一步

1. A1：取得並人工標註三銀行真實描述及反例；盲測與規則調整樣本分開，報 precision／coverage／待確認率，未知不當成功。不為填圖猜正式資料。
2. A5：分類品質與當次部署授權具備後，先成對備份／副本演練，再正式升級、唯讀預覽既有資料；真實分類寫入另確認，核對 Web／API／owned Excel。
3. A4 只有取得用途同意及確認真實未知樣本需要時才做 AI 建議；目前預設本機，不把 AI 平台當前置。
4. 其他未完成：第二期 parser 盲測、Codex Gmail 首次自動收件／跨日離線補抓、Groq runtime、OCR runtime、實體手機／螢幕閱讀器、重開機排程與冷啟動效能。接手先查現況，不能由設定存在推定驗收完成。
