# 交接

## 目前狀態

新 repository `family-finance-hub` 已初始化，產品名稱為「家庭收支記錄」。v0.1 本機功能已完成：Documents（上傳、列表與原始檔檢視）、Finance CSV、Dashboard、Search、Jobs history 與 React UI。介面採深綠導覽、清爽淺色工作區、依收支分類色彩的摘要列與響應式文件/交易區。Documents 以 SHA-256 去重，財務列以來源文件和 CSV 列內容冪等匯入。

Gmail / remote source 的產品設計已寫入 PROJECT、ARCHITECTURE 與 TASKS，但 provider 整合尚未實作；目前只註冊本機檔案來源。

M5.1 基礎架構已完成：Document 支援來源類型與 optional source reference，`storage_key` 不再必填；本機內容讀取經 `DocumentSourceRegistry` / `LocalFileDocumentSource`，CSV 結構解析經 `DocumentProcessor` / `CsvDocumentProcessor`。Documents 與 Finance CSV 匯入由 application use case 管理 transaction，SQLite engine 明確啟動外層交易，SHA-256 唯一索引競爭會透過 savepoint 恢復並重用既有文件。Migration `0002_document_sources` 已套用至本機資料庫。

目前只有本機來源與 CSV processor 有實作。Gmail source/OAuth、remote-only 文件建立與讀取、PDF/Image/OCR/password-protected PDF processor、手動同步 UI/API 及 scheduler 均未實作。

## 已決定的下一階段方向

- Documents 已改為 logical document identity + source metadata；各 source adapter 的選擇透過 registry 管理。
- Gmail 信用卡帳單預設不永久下載到 Windows storage；Backend 按需取得 attachment bytes，在 memory 或受控 temporary buffer 中解析後丟棄。
- SQLite 預設保存 Gmail message ID、attachment ID、filename、sender、received_at、SHA-256、parsed_at 等 source metadata 與解析結果。
- 使用者查看原始帳單時，Backend 可即時 fetch Gmail attachment 並 stream 給瀏覽器。
- 只有使用者明確選擇「保存到家庭文件匣」時，才把 Gmail attachment 寫入本機 StoragePort。
- 密碼保護 PDF 可以 transient bytes 解密與解析；PDF 密碼、OAuth token 等 secret 不可存一般 DB/log/plain config。
- `DocumentSource`、`DocumentProcessor`、application transaction boundary 與 SHA-256 concurrent duplicate recovery 已就緒；保持 Modular Monolith，不拆 microservices。

## Gmail 自動化實作順序

Gmail 自動化採「先正確、再自動、最後才即時」：

1. 先完成 Documents/source abstraction、transaction boundary 與 Gmail source。
2. 先做「立即同步 Gmail」手動 trigger，驗證搜尋、附件取得、解析、去重、寫入 Finance 的完整流程。
3. 手動同步穩定後，加入 incremental sync state，只處理上次成功同步後的新變更。
4. incremental sync 穩定後，再加入預設每 30 分鐘一次的 scheduler。
5. Windows 關機期間不要求背景常駐；重新開機後應利用 incremental sync 補抓關機期間的新信。
6. scheduler 只能 trigger 同一個 `GmailSyncUseCase`，不得另外實作一套 Gmail/Finance 邏輯。
7. Gmail Push / Pub/Sub 僅保留為未來選配；只有確實需要近即時更新時才導入。

UI 後續應提供「最後同步時間」、「下一次同步時間」、「同步狀態」與「立即同步 Gmail」。

## 下一步

接著進入 M5.2：先建立 Gmail source authentication 與安全 token storage，再做「立即同步 Gmail」完整手動流程。Windows Tailscale 網路與備份/還原的實機驗證仍未完成，應在遠端家庭裝置試用前完成。不要在手動同步及 incremental sync 尚未穩定前加入 scheduler。

## 驗證與風險

驗證結果：backend `pytest` 9 passed；Alembic migration 測試從 `0001_initial` 升級並保留既有文件、Finance transaction 與 Job 關聯，也能新增無 `storage_key` 的 remote-source 記錄；migration `0002_document_sources` 已套用至本機資料庫。以新版本 FastAPI app 對本機資料庫做唯讀 smoke test，確認 2 份文件、17 筆交易可列出且可讀回原始文件；既有 API/UI 分別運行於 127.0.0.1:8000/5173；frontend `npm run build` 成功，`git diff --check` 通過。環境有 Node.js 25.2.1、npm 11.6.2、Git 2.53.0。Windows 沒有系統 Python runtime；驗證使用 repository `.venv` 的 Python 3.12，新環境需先安裝 Python 3.11+。

本次完成 M5.1 程式與 schema 調整，沒有宣稱 Gmail/remote source/scheduler 功能已實作或驗證。測試輸出另有 httpx/Starlette 與 Alembic 設定相容性 deprecation warnings，不影響通過結果。

已知風險：
- Tailscale 遠端連線設定與 Windows 防火牆規則尚未實機驗證。
- v0.1 沒有多使用者授權。
- CSV 金額格式預設使用一般十進位數值，銀行專用格式留待後續以真實帳單驗證。
- remote-only Gmail document 依賴 Gmail 授權及原始信件/附件仍存在；若原始來源消失，只能保留 metadata 與已解析資料，除非事前保存本地副本。
- scheduler 只在 Windows 主機運行時工作，因此資料新鮮度不是嚴格 24/7；這是目前 local-first 設計的刻意取捨。
