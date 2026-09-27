# 交接

## 目前狀態

產品「家庭收支記錄」v0.1 為 Windows 主機上的 local-first Modular Monolith。M1-M5.4 的共用平台與既定流程已實作：Documents/1:N source records、SHA-256 冪等匯入、通用 Finance CSV、Dashboard/Search/Jobs、密碼規則安全邊界、加密 PDF transient preview、Gmail 手動/增量同步與 opt-in 每 30 分鐘 scheduler。M7.1-M7.5 的搜尋、來源追溯、月份／幣別總覽、設定分組、PDF 預覽體驗及手機排版也已實作；銀行專用 PDF parser 與外部環境驗收尚未完成。

PDF 文字抽取不足時才走 `OcrProvider`；目前 Tesseract adapter 會先以 `--list-langs` 確認設定所需 traineddata，再使用 PDFium 在記憶體渲染、透過 stdin 傳頁面影像，最多 20 頁、每頁約 8 MP、總逾時 120 秒。缺少語言資料會回報獨立狀態；OCR 文字僅保留於此次處理記憶體，不寫 DB/log/文件暫存；OCR 失敗不影響原始/解密 PDF 預覽。OCR 執行檔和 `chi_tra`/`eng` 語言資料尚未在此 Windows 主機安裝/驗收。銀行專用 PDF statement parser 尚未實作；PDF 仍只屬於共用 Document，不會猜測或自動建立 Finance transaction。

Gmail 使用者授權尚未設定或執行；自動同步預設關閉，需使用者在 UI 完成 readonly OAuth 後明確啟用。排程與手動按鈕共用 `GmailSyncUseCase` 及鎖，PDF 只收錄文件，CSV 才走通用匯入。替換 OAuth client 設定會關閉排程。

通用 CSV 匯入會拒絕無效日期、非有限/超精度金額、格式不合的幣別與欄位數異常，失敗資料不會留下部分交易。Gmail 先保存 CSV 文件；單份財務解析失敗會保留文件與失敗工作紀錄，並繼續處理後續郵件。完整交易頁提供月份／幣別篩選和分頁；首頁只讀選定期間最近 8 筆，Dashboard 金額由 SQLite 依期間與幣別聚合。Alembic 與 API 共用 `FAMILY_FINANCE_HUB_DATABASE_URL`。

## 帳單撤銷／恢復已完成

- 文件頁提供「有效／已撤銷」與撤銷／恢復操作，確認前顯示關聯交易筆數、各幣別收入／支出／淨額及撤銷原因。
- 撤銷會讓對應交易退出 Dashboard、交易列表與搜尋；保留來源、交易與工作紀錄，可恢復既有交易而不重新解析。沒有交易的文件恢復後仍為零筆。
- 本機上傳與 Gmail 同步均保留相同 SHA-256 文件的撤銷狀態；不同內容仍視為新文件，尚無語意層級帳單去重。保存本機副本不會恢復收支。
- 狀態更新與工作紀錄在同一 transaction；重複操作不新增紀錄，預覽後狀態或影響金額改變則要求重新確認。
- `0009_document_revocation` 已在隔離 SQLite 升級驗證；既有文件預設有效。使用中的資料庫尚未遷移。

## 使用體驗評估與待辦

2026-09-27 已完成 M7.1-M7.5 程式修改及隔離合成資料的桌面與 390px／320px 操作驗證。M7 的前端自動化測試基礎設施及更大規模合成資料矩陣仍待補強；實作順序及驗收條件見 `TASKS.md` 的 M7。

- 搜尋與導覽：搜尋獨立為結果頁，文件／交易各自有總數與分頁，搜尋字詞及分頁保留在 URL，且具備獨立載入、空結果、錯誤與舊請求防護。
- 新增資料與入帳：統一入口區分只收錄文件、CSV 建立交易及 Gmail 同步；文件詳情集中顯示來源、有效狀態、關聯交易與匯入歷史。PDF 收錄仍明示尚未建立交易。
- 來源追溯：交易與 Jobs 只有在有 `source_document_id`／`document_id` 時提供文件連結；文件詳情可回看本機／遠端來源及所有關聯處理結果。
- 月份／幣別總覽：首頁預設本月，Dashboard 由資料庫依月份與幣別聚合；不同幣別不相加，連往交易頁會保留同一組條件，空月份顯示明確空狀態。
- 設定已依「連線服務／家庭成員／文件解鎖／進階設定」分組，Gmail 預設在第一組；使用者可見名稱統一為「文件解鎖設定」，未更動既有資料識別或 schema。
- PDF 開啟後會先自動預覽；只有需要密碼或密碼規則錯誤時才展開解鎖設定。來源不可用、需要密碼、密碼不符及 OCR 未就緒都有獨立提示，且明示預覽不會建立交易。
- PDF 與撤銷／恢復對話框已補焦點移入、Tab 循環、Escape 關閉及回到觸發按鈕；自動預覽仍固定不呼叫 AI、不啟用 Gmail 同步、不保存遠端附件。
- M7.5 已完成：主要字級層級與多幣別摘要、手機交易兩行排列、單排導覽、長內容縮排／換行及共用 `EmptyState`／`TransactionTable` 元件已整理。
- 待處理：M7 前端行為測試基礎設施與更大規模長檔名／失敗狀態矩陣，銀行 PDF parser 也仍未完成。

下一輪優先補 M7 前端行為測試與隔離資料矩陣；再依真實帳單樣本決定 bank-specific PDF parser。隨功能調整拆分 `App.tsx`，不全面重寫。

本輪已修改程式、測試及本機 Markdown；未操作正式資料、未保存秘密、未提交或推送 Git。

## 最近程式驗證

- M7.1-M7.2 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-2`，69 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。
- M7.1-M7.2 Frontend：`npm run build` 成功；隔離合成資料瀏覽器驗證搜尋結果頁、URL／上一頁、分頁、新增資料入口、未授權 Gmail 下一步、文件詳情、來源連結與匯入歷史，沒有目前頁面的 console error。
- M7.3 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-3-final`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋 Dashboard 跨月、多幣別、空期間、幣別／月份格式錯誤、有效文件條件及撤銷／恢復回歸。
- M7.3 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5188/` 搭配隔離合成 DB/storage 驗證本月總覽、空月份、月份／幣別控制，以及「查看全部交易」保留 `month` URL 條件；新分頁沒有 console error。
- M7.4 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-4-full`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings；PDF focused suite 為 10 passed。新增 PDF 錯誤分類的 CORS header 暴露驗證。
- M7.4 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5189/` 搭配隔離合成 DB/storage 驗證設定四組分頁、一般 PDF 自動預覽、OCR 未就緒提示、加密 PDF 需要解鎖提示、PDF／撤銷對話框 Escape 回到觸發按鈕及 Shift+Tab 焦點循環；目前頁面 console error 為空。
- M7.5 Frontend：`npm run build` 成功；以隔離合成資料驗證交易頁桌面回歸，並用 Chromium device metrics 實際量測 390px／320px：`body.scrollWidth` 與 viewport 相等、交易表格 `scrollWidth` 等於內容寬度、項目／金額／日期／來源均在列內，五個主導覽維持單排。交易表格已抽至 `frontend/src/TransactionTable.tsx`，空狀態抽至 `frontend/src/EmptyState.tsx`；目前未建立獨立 frontend test runner。

- Backend：`.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/revocation-final`，67 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋撤銷範圍、多幣別、恢復、冪等、過期預覽、失敗回滾、Gmail 已撤銷文件保護及備份／migration。
- OCR/PDF processor focused tests：10 passed；含加密 PDF 解密後才呼叫 provider、OCR 錯誤不阻斷預覽、Tesseract 語言資料預檢及 stdin 資料流測試。
- 使用目前 Codex Python runtime 的 PDFium 對合成 PDF 實際渲染一頁至記憶體，Tesseract 子程序以 stub 驗證 PNG stdin/output；不是實際辨識品質驗收。
- Frontend：`npm run build` 成功。
- 瀏覽器以隔離合成帳單驗證桌面及 390px／320px 手機版撤銷、恢復、取消、摘要更新與過期預覽 409 後重新確認；沒有頁面水平溢出。撤銷後僅剩另一份文件的交易，恢復後精確回到原有四筆與各幣別金額。正常流程無 console 錯誤。
- 上一輪驗證預覽為 `http://127.0.0.1:5177/`，API 為 8018；DB/storage 位於忽略的 `backend/.test-tmp/lifecycle-preview-20260926/`。僅含合成資料，與正式資料隔離；此處記錄驗證環境，不保證服務持續執行。
- 修正 PDF OCR 狀態標頭未透過 CORS 暴露的整合問題；跨來源 API 測試通過，瀏覽器以合成 PDF 驗證「OCR 尚未就緒」提示出現且仍可預覽。
- Alembic head 為 `0009_document_revocation`；測試覆蓋既有資料保留，以及有已撤銷文件時拒絕 downgrade，避免舊程式重新計入收支。OCR 無 schema migration。
- `backend/tests/test_backup_restore.py` 以有效／已撤銷兩種合成 DB + documents storage 演練備份／還原，恢復 PDF bytes、Finance transaction、撤銷狀態及工作紀錄；已撤銷交易需明確恢復才重新計入。
- Tesseract executable 未找到；Tailscale CLI/service 亦未找到，無法做真實 OCR runtime 或 tailnet/Firewall 驗證。

## 正式使用與外部驗收

正式使用撤銷功能前，先停止 API、成對備份正式 DB/storage，確認資料庫位址後升級至 `0009_document_revocation` 並重新啟動。此步尚未執行；操作方式見 `docs/operations.md`。

1. 在 Windows 安裝 Tesseract 及 `chi_tra`/`eng` traineddata；以合成掃描 PDF 驗證實際辨識品質與真實子程序逾時。缺語言資料的提早檢查已由合成測試覆蓋，但真實 runtime 尚未驗收。
2. 由使用者設定 Google Cloud OAuth 桌面 client 並在家庭主機互動授權；以真實台灣信用卡帳單在本機核對解密和 OCR 結果，不把帳單放入 repository。
3. 根據核對過的真實格式定義 bank-specific `BankStatementParser`/profile，補日期、幣別、金額、退款與冪等映射；通過人工核對前不自動寫交易。
4. 安裝/登入 Tailscale 並確認家庭裝置與 Windows Firewall 規則後，再做遠端 Web 使用檢查。不要公開服務或設 router port forwarding。
5. 尚未驗證真實資料庫的生產備份/還原；目前只完成隔離合成 rehearsal。未提供自動或加密備份。
6. 搜尋分頁已列入 M7.1，不再等資料量增長才處理；工作歷史目前最多 100 筆，其分頁與匯入批次大小另依使用量評估。

## 安全界線

- 不讀取或回填先前對話裡曾提供的個人秘密；SQLite、log、repository 與 plaintext config 不可存 secrets。身分資料、PDF password、OAuth token 只透過使用者明確操作的本機 SecretStore/Credential Manager。
- 不曾連線 Gmail、不曾遷移或讀取使用中的資料庫，也未啟用排程或修改防火牆。測試與 restore rehearsal 僅用合成資料及隔離 SQLite/storage。
- 正式升級前先確認 DB 與 storage 路徑，停止 API 並成對備份 DB 和 `data/documents`，再明確執行 migration；禁止刪除/重建舊 DB 或讓 app 靜默升級 schema。
- 不自動 commit、push 或覆蓋其他既有修改。
