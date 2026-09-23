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
python -m pip install -e "backend[dev]"
alembic -c backend\alembic.ini upgrade head
uvicorn family_finance_hub.main:app --app-dir backend\src --host 127.0.0.1 --port 8000
```

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
