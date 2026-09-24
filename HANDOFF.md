# 交接

## 目前狀態

產品「家庭收支記錄」v0.1 為 Windows 主機上的 local-first Modular Monolith。M1-M5.4 的共用平台與既定流程已實作：Documents/1:N source records、SHA-256 冪等匯入、通用 Finance CSV、Dashboard/Search/Jobs、密碼規則安全邊界、加密 PDF transient preview、Gmail 手動/增量同步與 opt-in 每 30 分鐘 scheduler。銀行專用 PDF parser 與外部環境驗收尚未完成。

PDF 文字抽取不足時才走 `OcrProvider`；目前 Tesseract adapter 使用 PDFium 在記憶體渲染，透過 stdin 傳頁面影像，最多 20 頁、每頁約 8 MP、總逾時 120 秒。OCR 文字僅保留於此次處理記憶體，不寫 DB/log/文件暫存；OCR 失敗不影響原始/解密 PDF 預覽。OCR 執行檔和 `chi_tra`/`eng` 語言資料尚未在此 Windows 主機安裝/驗收。銀行專用 PDF statement parser 尚未實作；PDF 仍只屬於共用 Document，不會猜測或自動建立 Finance transaction。

Gmail 使用者授權尚未設定或執行；自動同步預設關閉，需使用者在 UI 完成 readonly OAuth 後明確啟用。排程與手動按鈕共用 `GmailSyncUseCase` 及鎖，PDF 只收錄文件，CSV 才走通用匯入。替換 OAuth client 設定會關閉排程。

## 最近驗證

- Backend：`python -m pytest backend\\tests -q`，43 passed、2 個 Starlette/httpx/anyio 相依套件 deprecation warnings。
- OCR focused tests：11 passed；含加密 PDF 解密後才呼叫 provider、OCR 錯誤不阻斷預覽、Tesseract stdin 資料流測試。
- 使用目前 Codex Python runtime 的 PDFium 對合成 PDF 實際渲染一頁至記憶體，Tesseract 子程序以 stub 驗證 PNG stdin/output；不是實際辨識品質驗收。
- Frontend：`npm run build` 成功。
- 修正 PDF OCR 狀態標頭未透過 CORS 暴露的整合問題；跨來源 API 測試通過，瀏覽器以合成 PDF 驗證「OCR 尚未就緒」提示出現且仍可預覽。
- Alembic head 為 `0008_gmail_auto_sync`；migration 僅在隔離暫存 SQLite 驗證。OCR 無 schema migration。
- `backend/tests/test_backup_restore.py` 以合成 DB + documents storage 演練備份/還原，恢復 PDF bytes、Finance transaction 與搜尋結果。
- Tesseract executable 未找到；Tailscale CLI/service 亦未找到，無法做真實 OCR runtime 或 tailnet/Firewall 驗證。

## 下一步

1. 安裝 `backend[ocr]`（README 開發安裝已含此 extra），並在 Windows 安裝 Tesseract 及 `chi_tra`/`eng` traineddata；用合成掃描 PDF 驗證實際辨識、超時與缺語言資料處理。
2. 由使用者設定 Google Cloud OAuth 桌面 client 並在家庭主機互動授權；以真實台灣信用卡帳單在本機核對解密和 OCR 結果，不把帳單放入 repository。
3. 根據核對過的真實格式定義 bank-specific `BankStatementParser`/profile，補日期、幣別、金額、退款與冪等映射；通過人工核對前不自動寫交易。
4. 安裝/登入 Tailscale 並確認家庭裝置與 Windows Firewall 規則後，再做遠端 Web 使用檢查。不要公開服務或設 router port forwarding。
5. 尚未驗證真實資料庫的生產備份/還原；目前只完成隔離合成 rehearsal。未提供自動或加密備份。

## 安全界線

- 不讀取或回填先前對話裡曾提供的個人秘密；SQLite、log、repository 與 plaintext config 不可存 secrets。身分資料、PDF password、OAuth token 只透過使用者明確操作的本機 SecretStore/Credential Manager。
- 不曾連線 Gmail、不曾遷移或讀取使用中的資料庫，也未啟用排程或修改防火牆。測試與 restore rehearsal 僅用合成資料及隔離 SQLite/storage。
- 正式升級前先確認 DB 與 storage 路徑，停止 API 並成對備份 DB 和 `data/documents`，再明確執行 migration；禁止刪除/重建舊 DB 或讓 app 靜默升級 schema。
- 不自動 commit、push 或覆蓋其他既有修改。
