# 交接

## 目前狀態

新 repository `family-finance-hub` 已初始化，產品名稱為「家庭收支記錄」。v0.1 本機功能已完成：Documents（上傳、列表與原始檔檢視）、Finance CSV、Dashboard、Search、Jobs history 與 React UI。介面採深綠導覽、清爽淺色工作區、依收支分類色彩的摘要列與響應式文件/交易區。Documents 以 SHA-256 去重，財務列以來源文件和 CSV 列內容冪等匯入。

目前程式仍採「每個 Document 都有本地檔案」的 v0.1 實作；Gmail / remote source 設計已寫入 PROJECT、ARCHITECTURE 與 TASKS，但尚未實作。

## 已決定的下一階段方向

- Documents 將從「本機檔案記錄」擴充為 logical document identity + source reference。
- Gmail 信用卡帳單預設不永久下載到 Windows storage；Backend 按需取得 attachment bytes，在 memory 或受控 temporary buffer 中解析後丟棄。
- SQLite 預設保存 Gmail message ID、attachment ID、filename、sender、received_at、SHA-256、parsed_at 等 source metadata 與解析結果。
- 使用者查看原始帳單時，Backend 可即時 fetch Gmail attachment 並 stream 給瀏覽器。
- 只有使用者明確選擇「保存到家庭文件匣」時，才把 Gmail attachment 寫入本機 StoragePort。
- 密碼保護 PDF 可以 transient bytes 解密與解析；PDF 密碼、OAuth token 等 secret 不可存一般 DB/log/plain config。
- 下一階段引入 `DocumentSource` 與 `DocumentProcessor` 邊界，但保持 Modular Monolith，不拆 microservices。
- 在擴充 Gmail 前，應同步整理 transaction ownership，並補齊 SHA-256 concurrent duplicate 的衝突 recovery。

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

先完成 Windows Tailscale 網路與備份/還原的實機驗證，接著進入 M5：先做 Documents/source abstraction 與 transaction boundary，再接 Gmail 手動同步。不要在核心資料流尚未穩定前先做 scheduler。

## 驗證與風險

v0.1 既有驗證結果：backend `pytest` 4 passed；Alembic 初始 migration 成功；frontend `npm run build` 成功；API `/api/health` 回傳 ok；Codex 內建瀏覽器確認總覽畫面正常顯示並檢查窄版面。最近一次 UI 視覺更新後 production build 通過。本機 API/UI 分別運行於 127.0.0.1:8000/5173。環境有 Node.js 25.2.1、npm 11.6.2、Git 2.53.0。Windows 沒有系統 Python runtime；驗證使用 Codex 隨附 Python 3.12 建立 repository `.venv`，新環境需先安裝 Python 3.11+。

本次只更新專案設計文件，沒有修改程式碼，因此沒有宣稱 Gmail/remote source/scheduler 功能已通過測試。

已知風險：
- Tailscale 遠端連線設定與 Windows 防火牆規則尚未實機驗證。
- v0.1 沒有多使用者授權。
- CSV 金額格式預設使用一般十進位數值，銀行專用格式留待後續以真實帳單驗證。
- remote-only Gmail document 依賴 Gmail 授權及原始信件/附件仍存在；若原始來源消失，只能保留 metadata 與已解析資料，除非事前保存本地副本。
- scheduler 只在 Windows 主機運行時工作，因此資料新鮮度不是嚴格 24/7；這是目前 local-first 設計的刻意取捨。
