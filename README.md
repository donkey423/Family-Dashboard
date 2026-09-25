# 家庭收支記錄

家庭收支記錄是以 Windows 家用電腦為主機的 local-first 家庭資料平台。第一版提供文件匣、通用財務 CSV 匯入、收支總覽、搜尋及匯入工作紀錄；文件先進入共用 Documents domain，再由 Finance 等模組建立關聯。

## 開發環境

- Windows 10/11
- Python 3.11 或更新版本（需先安裝 Windows Python runtime）
- Node.js 22.12+（或 20.19+）與 npm

## 啟動

在 repository 根目錄開啟兩個 PowerShell 視窗：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "backend[dev,ocr]"
alembic -c backend\alembic.ini upgrade head
uvicorn family_finance_hub.main:app --app-dir backend\src --host 127.0.0.1 --port 8000
```

`alembic upgrade head` 會更新資料庫結構。若你已有舊資料庫，先停止 API 並備份 SQLite 檔與 `data\documents`，再執行 migration；不要刪除或重建舊資料庫。

若以 `FAMILY_FINANCE_HUB_DATABASE_URL` 指定 SQLite 路徑，API 與 Alembic migration 會使用同一個值。

另一個視窗：

```powershell
cd frontend
$env:NODE_OPTIONS = "--use-system-ca"
npm --cache .npm-cache install
npm run dev -- --host 127.0.0.1
```

開啟 Vite 顯示的網址。預設 API 為 `http://127.0.0.1:8000`。設定 `VITE_API_BASE_URL` 可指定其他 API 位址。

## CSV 格式

使用 UTF-8、逗號分隔並含標題列的 CSV。日期欄可用 `date`、`posted_at` 或 `transaction_date`；描述欄可用 `description`、`memo`、`name`、`payee` 或 `merchant`。金額欄可用 `amount` 或 `transaction amount`，支出請用負數、收入用正數；也可提供 `debit`/`withdrawal` 與 `credit`/`deposit` 欄，前者會記為支出。`currency` 選填，未提供時使用 TWD。原始列會保留在本機資料庫，且每筆交易都連回匯入的 CSV 文件。

匯入會拒絕無效日期、非有限或超過兩位小數的金額、非三字母幣別，以及與標題欄數不符的資料列；失敗會記入匯入紀錄，不會留下部分交易。總覽以資料庫聚合金額，完整交易明細可按月份篩選並分頁。

## Gmail 與加密 PDF

在「設定」頁匯入 Google Cloud 的 Gmail API OAuth 桌面應用程式 JSON，然後按「連接 Google 帳戶」及「立即同步 Gmail」。同步使用唯讀權限；預設查詢 `in:anywhere has:attachment {filename:pdf filename:csv}`，不限制日期，涵蓋可存取的全部郵件（含封存與垃圾郵件）。初次同步超過單次上限時，再按一次同步即可接續。OAuth 設定與 token 僅放 Windows Credential Manager。連線後可手動同步；定時同步需另外勾選啟用，預設關閉，每 30 分鐘同步一次。Windows 關機時不會執行，重新啟動後會補跑已到期的同步。替換 OAuth 設定會關閉定時同步，需重新授權及手動啟用。

Gmail CSV 會使用通用欄位解析匯入交易；解析失敗的 CSV 仍會保存在共用文件匣並留下失敗紀錄，不會阻止後續郵件同步。PDF 會先進共用文件匣，不會把抽取文字猜成交易。查看加密 PDF 時，可建立家庭成員及文件安全 profile；系統可即時讀取該 Gmail 郵件的主旨、寄件者與文字本文，僅在記憶體中擷取並遮罩密碼規則。勾選允許 AI 後，AI 僅會收到遮罩後的規則文字；身分證字號、生日及實際密碼都留在本機 Credential Manager/本機記憶體。非 Gmail 文件可在預覽視窗手動輸入郵件密碼說明。解密預覽不會改寫原始 PDF。

PDF 內嵌文字不足時，系統才會嘗試使用本機 OCR；PDFium 會在記憶體中渲染，Tesseract 透過標準輸入處理影像，不建立臨時帳單影像。OCR 需要另外安裝 Tesseract 及 `chi_tra`、`eng` 語言資料；亦可用 `FAMILY_FINANCE_HUB_TESSERACT` 指向執行檔，並以 `FAMILY_FINANCE_HUB_OCR_LANG` 指定語言。執行 OCR 前會檢查設定所需的語言資料；引擎尚未就緒或缺少語言資料時仍可檢視 PDF，介面會分別顯示狀態。OCR 文字只在此次處理的記憶體中使用，不寫入資料庫；銀行專用 PDF 交易 parser 尚未實作。

AI API key 為可選設定，只在需要 AI 協助解讀密碼規則時使用；未設定或未勾選 AI 時，不呼叫 AI。定時同步只會處理 CSV 與建立 PDF 文件來源，不會將 PDF 自動解析為財務交易。

## 測試與建置

```powershell
python -m pytest backend\tests
cd frontend
npm run build
```

## 家用網路使用

先讓 Web 與 API 只監聽 Windows 主機，再依 [部署說明](docs/operations.md) 使用 Tailscale 私有網路連線。不要將服務公開到網際網路或設定路由器連接埠轉送。

## 文件

- [專案目標](PROJECT.md)
- [架構](ARCHITECTURE.md)
- [里程碑與待辦](TASKS.md)
- [維護交接](HANDOFF.md)
- [操作與部署](docs/operations.md)
