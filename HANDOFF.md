# 交接

## 目前狀態

產品「家庭收支記錄」v0.1 為 Windows 主機上的 local-first Modular Monolith。M1-M5.4 的共用平台與既定流程已實作：Documents/1:N source records、SHA-256 冪等匯入、通用 Finance CSV、Dashboard/Search/Jobs、密碼規則安全邊界、加密 PDF transient preview、Gmail 手動/增量同步與 opt-in 每 30 分鐘 scheduler。銀行專用 PDF parser 與外部環境驗收尚未完成。

PDF 文字抽取不足時才走 `OcrProvider`；目前 Tesseract adapter 會先以 `--list-langs` 確認設定所需 traineddata，再使用 PDFium 在記憶體渲染、透過 stdin 傳頁面影像，最多 20 頁、每頁約 8 MP、總逾時 120 秒。缺少語言資料會回報獨立狀態；OCR 文字僅保留於此次處理記憶體，不寫 DB/log/文件暫存；OCR 失敗不影響原始/解密 PDF 預覽。OCR 執行檔和 `chi_tra`/`eng` 語言資料尚未在此 Windows 主機安裝/驗收。銀行專用 PDF statement parser 尚未實作；PDF 仍只屬於共用 Document，不會猜測或自動建立 Finance transaction。

Gmail 使用者授權尚未設定或執行；自動同步預設關閉，需使用者在 UI 完成 readonly OAuth 後明確啟用。排程與手動按鈕共用 `GmailSyncUseCase` 及鎖，PDF 只收錄文件，CSV 才走通用匯入。替換 OAuth client 設定會關閉排程。

通用 CSV 匯入會拒絕無效日期、非有限/超精度金額、格式不合的幣別與欄位數異常，失敗資料不會留下部分交易。Gmail 先保存 CSV 文件；單份財務解析失敗會保留文件與失敗工作紀錄，並繼續處理後續郵件。完整交易頁提供月份篩選和分頁；首頁只讀最近 8 筆，Dashboard 金額由 SQLite 聚合。Alembic 與 API 共用 `FAMILY_FINANCE_HUB_DATABASE_URL`。

## 帳單撤銷／恢復已完成

- 文件頁提供「有效／已撤銷」與撤銷／恢復操作，確認前顯示關聯交易筆數、各幣別收入／支出／淨額及撤銷原因。
- 撤銷會讓對應交易退出 Dashboard、交易列表與搜尋；保留來源、交易與工作紀錄，可恢復既有交易而不重新解析。沒有交易的文件恢復後仍為零筆。
- 本機上傳與 Gmail 同步均保留相同 SHA-256 文件的撤銷狀態；不同內容仍視為新文件，尚無語意層級帳單去重。保存本機副本不會恢復收支。
- 狀態更新與工作紀錄在同一 transaction；重複操作不新增紀錄，預覽後狀態或影響金額改變則要求重新確認。
- `0009_document_revocation` 已在隔離 SQLite 升級驗證；既有文件預設有效。使用中的資料庫尚未遷移。

## 最近驗證

- Backend：`.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/revocation-final`，67 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋撤銷範圍、多幣別、恢復、冪等、過期預覽、失敗回滾、Gmail 已撤銷文件保護及備份／migration。
- OCR/PDF processor focused tests：10 passed；含加密 PDF 解密後才呼叫 provider、OCR 錯誤不阻斷預覽、Tesseract 語言資料預檢及 stdin 資料流測試。
- 使用目前 Codex Python runtime 的 PDFium 對合成 PDF 實際渲染一頁至記憶體，Tesseract 子程序以 stub 驗證 PNG stdin/output；不是實際辨識品質驗收。
- Frontend：`npm run build` 成功。
- 瀏覽器以隔離合成帳單驗證桌面及 390px／320px 手機版撤銷、恢復、取消、摘要更新與過期預覽 409 後重新確認；沒有頁面水平溢出。撤銷後僅剩另一份文件的交易，恢復後精確回到原有四筆與各幣別金額。正常流程無 console 錯誤。
- 本次預覽為 `http://127.0.0.1:5177/`，API 為 8018；DB/storage 位於忽略的 `backend/.test-tmp/lifecycle-preview-20260926/`。僅含合成資料，與正式資料隔離。
- 修正 PDF OCR 狀態標頭未透過 CORS 暴露的整合問題；跨來源 API 測試通過，瀏覽器以合成 PDF 驗證「OCR 尚未就緒」提示出現且仍可預覽。
- Alembic head 為 `0009_document_revocation`；測試覆蓋既有資料保留，以及有已撤銷文件時拒絕 downgrade，避免舊程式重新計入收支。OCR 無 schema migration。
- `backend/tests/test_backup_restore.py` 以有效／已撤銷兩種合成 DB + documents storage 演練備份／還原，恢復 PDF bytes、Finance transaction、撤銷狀態及工作紀錄；已撤銷交易需明確恢復才重新計入。
- Tesseract executable 未找到；Tailscale CLI/service 亦未找到，無法做真實 OCR runtime 或 tailnet/Firewall 驗證。

## 下一步

正式使用撤銷功能前，先停止 API、成對備份正式 DB/storage，確認資料庫位址後升級至 `0009_document_revocation` 並重新啟動。此步尚未執行；操作方式見 `docs/operations.md`。

1. 在 Windows 安裝 Tesseract 及 `chi_tra`/`eng` traineddata；以合成掃描 PDF 驗證實際辨識品質與真實子程序逾時。缺語言資料的提早檢查已由合成測試覆蓋，但真實 runtime 尚未驗收。
2. 由使用者設定 Google Cloud OAuth 桌面 client 並在家庭主機互動授權；以真實台灣信用卡帳單在本機核對解密和 OCR 結果，不把帳單放入 repository。
3. 根據核對過的真實格式定義 bank-specific `BankStatementParser`/profile，補日期、幣別、金額、退款與冪等映射；通過人工核對前不自動寫交易。
4. 安裝/登入 Tailscale 並確認家庭裝置與 Windows Firewall 規則後，再做遠端 Web 使用檢查。不要公開服務或設 router port forwarding。
5. 尚未驗證真實資料庫的生產備份/還原；目前只完成隔離合成 rehearsal。未提供自動或加密備份。
6. 若交易筆數進一步增長，再評估搜尋結果分頁及匯入批次大小；目前搜尋 API 每類最多回傳 50 筆，工作歷史最多 100 筆。

## 安全界線

- 不讀取或回填先前對話裡曾提供的個人秘密；SQLite、log、repository 與 plaintext config 不可存 secrets。身分資料、PDF password、OAuth token 只透過使用者明確操作的本機 SecretStore/Credential Manager。
- 不曾連線 Gmail、不曾遷移或讀取使用中的資料庫，也未啟用排程或修改防火牆。測試與 restore rehearsal 僅用合成資料及隔離 SQLite/storage。
- 正式升級前先確認 DB 與 storage 路徑，停止 API 並成對備份 DB 和 `data/documents`，再明確執行 migration；禁止刪除/重建舊 DB 或讓 app 靜默升級 schema。
- 不自動 commit、push 或覆蓋其他既有修改。
