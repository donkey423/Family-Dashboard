# 家庭收支記錄架構

## 執行拓樸

```text
Windows 主機
  React/Vite Web UI  ->  FastAPI Modular Monolith  ->  SQLite + Alembic
                                                ->  Local filesystem adapter
MacBook / iPhone  -- Tailscale private network --> Windows 主機
```

開發預設只綁定 loopback。遠端使用時，依部署文件設定主機監聽介面與 Windows 防火牆，僅允許 Tailscale 網路。

## 依賴方向

```text
Presentation (React)
        -> HTTP API / Application services
        -> Domain services and domain models
        -> Ports (storage, future source/provider boundaries)
Infrastructure adapters implement ports
```

Domain 不直接依賴 FastAPI、SQLite、Windows 路徑或第三方服務。模組之間透過 application service/API 與穩定識別碼互動，不直接修改其他模組資料表。

## v0.1 模組

- Documents：共用文件身分、SHA-256、metadata 與檔案儲存 port。允許 PDF/JPG/PNG/CSV。
- Finance：CSV 解析、交易資料及來源文件關聯；CSV 必須先由 Documents 接收。
- Jobs：匯入作業狀態、來源與可供 UI 顯示的錯誤摘要。
- Search：跨文件 metadata 與 Finance 交易的查詢服務。
- Dashboard：以 Finance 查詢服務提供統計資料。

SQLAlchemy 持久化 model 集中在 infrastructure/schema 邊界，由各 domain service 擁有其資料操作。Alembic migration 是資料庫 schema 變更的正式路徑。

## 匯入流程

```text
HTTP multipart upload
 -> validate extension/size
 -> Documents service computes SHA-256
 -> existing hash: reuse document; otherwise StoragePort writes local file
 -> create import job
 -> Finance CSV parser reads the imported document bytes
 -> row hash (source document + row index + normalized row) prevents re-import duplicates
 -> persist transactions linked to source document
```

檔案儲存使用 content-addressed 相對路徑，先寫暫存檔再原子替換。雜湊唯一索引處理併發重複匯入；單一程序和 SQLite transaction 是 v0.1 的一致性範圍。交易 row hash 含來源文件及列序，因此相同 CSV 重送不重複匯入，同一檔案內內容相同但列序不同的兩筆交易仍可保留。

## 擴充介面

儲存透過 `StoragePort` 隔離，v0.1 adapter 為本機檔案系統。未來可在來源/處理器邊界接 Gmail、密碼保護 PDF、OCR 與 `AIProvider`，不讓核心依賴供應商 SDK。Insurance、Assets、Warranty、Travel、Vehicle、Subscriptions、Property 等 domain 僅於需要時新增模組與 migration。

## 安全與限制

- 不記錄文件內容、秘密或完整敏感欄位；一般操作 log 僅可包含 job/document ID 與狀態。
- SQLite、storage 和備份均視為家庭敏感資料，需保留在受控 Windows 使用者目錄並納入備份。
- v0.1 尚無多使用者授權；部署於 Tailscale 私有網路並限可信家庭裝置。
- 遠端使用的非 loopback 綁定須搭配 Windows 防火牆僅允許 Tailscale 介面/網段。不可公開埠至 Internet。
- 未來秘密使用 Windows Credential Manager/SecretStore，不存 SQLite 或 repository 設定檔。
