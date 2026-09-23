# 交接

## 目前狀態

新 repository `family-finance-hub` 已初始化，產品名稱為「家庭收支記錄」。v0.1 本機功能已完成：Documents（上傳、列表與原始檔檢視）、Finance CSV、Dashboard、Search、Jobs history 與 React UI。介面採深綠導覽、清爽淺色工作區、依收支分類色彩的摘要列與響應式文件/交易區。Documents 以 SHA-256 去重，財務列以來源文件和 CSV 列內容冪等匯入。

## 下一步

下一階段先在 Windows Tailscale 網路中驗證遠端裝置存取與防火牆規則，再規劃資料備份/還原演練；未來 domain 和外部來源仍依 PROJECT.md 延後。

## 驗證與風險

驗證結果：backend `pytest` 4 passed；Alembic 初始 migration 成功；frontend `npm run build` 成功；API `/api/health` 回傳 ok；Codex 內建瀏覽器確認總覽畫面正常顯示並檢查窄版面。最近一次 UI 視覺更新後 production build 通過。本機 API/UI 分別運行於 127.0.0.1:8000/5173。環境有 Node.js 25.2.1、npm 11.6.2、Git 2.53.0。Windows 沒有系統 Python runtime；驗證使用 Codex 隨附 Python 3.12 建立 repository `.venv`，新環境需先安裝 Python 3.11+。

Tailscale 遠端連線設定與 Windows 防火牆規則尚未實機驗證。v0.1 沒有多使用者授權。CSV 金額格式預設使用一般十進位數值，銀行專用格式留待未來支援。
