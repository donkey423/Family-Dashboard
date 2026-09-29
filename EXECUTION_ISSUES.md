# 執行問題與處理紀錄

> 更新日期：2026-09-29
>
> 本文件只記錄工程執行時可觀察到的問題、處理方式與剩餘限制，不保存帳單內容、身分資料、生日、PDF 密碼、API key、OAuth token 或其他秘密。

## 1. 本次範圍

本次工作同時完成了三件事：

1. 將免費 AI 密碼規則 provider 的程式、設定頁與驗收狀態更新到文件。
2. 重新執行後端測試、前端 production build，並以一份使用者授權的 Gmail PDF 驗證文件收錄、SHA-256 去重、郵件格式確認、本機解鎖與文字抽取。
3. 接上已驗證的中國信託 Statement parser，完成帳單核對、Finance 冪等匯入與 Excel 重建；同時補上本機來源缺少 Gmail 內文時的規則提示 fallback。

本次不是所有銀行版型或內建 Gmail OAuth 長期自動化的完成驗收。實際完成範圍是「一份實際中國信託帳單已收錄、解鎖、解析、核對、匯入並更新 Excel」；未知版型仍停在待處理。

## 2. 問題與處理

### 2.1 本機分支落後最新遠端文件提交

- **現象：** 接手時本機 `master` 為 `001ca5d`，`origin/main` 已是 `4f9bfb5`；工作區另外有先前未提交的 Groq 程式與文件修改。
- **風險：** 直接 push 會因遠端不是本機歷史的 fast-forward 而失敗；直接 reset、checkout 或覆蓋又可能遺失既有實作。
- **處理：** 保留工作區修改，先讀取並以目前程式行為校正文件；完成本地 commit 後再把 `origin/main` 整合進來，最後以明確的 `master:main` 推送。
- **結論：** 本次以不覆蓋遠端歷史的 merge 方式整合，完成 push 後以本機與 `origin/main` 的 commit hash 相同作為同步完成條件；不可使用 `reset --hard` 或 force push 解決。

### 2.2 Git 權限與 Credential Manager 行為

- **現象：** repository 所有權與目前執行環境的 Git 安全檢查不一致；一般 Git 操作可能出現 `dubious ownership`，第一次遠端讀取也曾受到 Git Credential Manager/Windows 憑證存取限制影響。
- **處理：** 只對這個 repository 使用 `-c safe.directory=C:/Users/brad/Documents/Codex/family-finance-hub` 執行必要的 Git 查詢、fetch、commit/push；未修改全域 Git 設定，也未索取或寫入使用者 token。
- **安全界線：** push 只能使用既有的 Windows Credential Manager 登入狀態；若憑證不可用，不應把 PAT 或 API key 貼到聊天、`.env` 或 repository。

### 2.3 pytest 暫存目錄權限錯誤

- **第一次現象：** 使用 `--basetemp backend/.test-tmp/free-ai-status` 時，大量測試在 setup 失敗，錯誤為 Windows `WinError 5` `PermissionError`；失敗數為 110，並不是測試 assertion 失敗。
- **原因：** 指定的 backend 暫存目錄受到 Windows 目錄權限/既有擁有者限制，pytest 無法建立測試隔離目錄。
- **第二次現象：** 改到 repository 根目錄的 `.pytest-tmp/free-ai-status` 時，父目錄尚不存在，錯誤改為 `WinError 3` `FileNotFoundError`。
- **處理：** 只在 repository 根目錄建立測試用父目錄，重跑：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp .pytest-tmp\free-ai-status
  ```

  測試完成後刪除這個只由本次產生的暫存目錄，避免未追蹤檔案進入 commit。
- **最終結果：** `187 passed`、2 個既有 FastAPI/anyio 相依套件棄用警告；沒有測試失敗。

### 2.4 UI 預設 provider 與實際已保存 provider 不一致

- **現象：** 程式與設定頁已加入 Groq，UI 預設為 Groq + `openai/gpt-oss-20b`；但現場服務 API 仍回報已保存的 `openai` / `gpt-4.1-mini` profile。
- **原因：** UI 預設值只是新設定的預填，不能為了切換 provider 自動覆寫 Windows Credential Manager 中既有的 profile。這是避免無提示改變外部 API 用量與秘密設定的安全行為。
- **處理：** 文件明確寫出「必須在設定頁選擇 Groq、輸入 key、按保存」，並保留 OpenAI 只有使用者明確選擇時才可用的路徑。
- **目前限制：** 尚未保存真實 Groq key，因此尚未宣稱真實 Groq request 已成功；`groq_adapter_in_worktree=true` 只代表程式存在，不代表 runtime 已切換。

### 2.5 內建 Gmail OAuth 與 Gmail 網頁操作不是同一條連線

- **現象：** 使用者可在 Gmail 網頁看到並下載授權的 PDF，但 FamilyHub 的內建 Gmail OAuth 狀態仍未設定/未授權。
- **原因：** Gmail 網頁登入、ChatGPT/Gmail app 連線與 FamilyHub 自己保存的 readonly OAuth token 是不同的授權邊界，不能互相推定已連線。
- **處理：** 本次只把 Gmail 網頁下載的 PDF 交給 FamilyHub 文件入口；沒有把它記成內建 Gmail scheduler 已成功抓取，也沒有改寫 FamilyHub OAuth 設定。
- **後續：** 若要驗收長期自動化，仍需在 Windows 本機完成 FamilyHub readonly OAuth，並另外驗證手動同步、定時同步與 token refresh。

### 2.6 真實 PDF 的 AI 路徑受阻，但明示規則可在本機解鎖

- **現象：** 實際開啟收錄的 PDF 時，runtime 使用既有 OpenAI profile，AI 預覽因帳戶額度不足停止。
- **原因：** live runtime 啟動早於最新明確規則 parser，第一次預覽沿用既有 OpenAI profile；Groq 尚未在本機保存 key，系統也不會偷換 provider。
- **處理：** 先在來源 Gmail 郵件確認其明確列出的兩種客戶格式，再由目前 parser 產生受限候選規則；規則不含秘密。因 live process 尚未重啟，先把該規則寫入 verified cache，關閉 AI 後由 live processor 與 Windows SecretStore 嘗試，沒有把帳單或個人資料送給 AI。
- **目前結果：** 同一份 Gmail 下載 PDF 已成功解鎖；原始檔為加密，輸出為未加密 2 頁 PDF，文字抽取可用。成功後 cache 只保留真正命中的規則，驗證用明文輸出已刪除，Finance transaction 仍為 0。
- **後續：** 正式 migration/restart 後重驗動態 parser 路徑。真實 Groq request 可另行驗收，但不再是這種郵件已明示格式的解鎖前置；下一個產品關卡仍是銀行 parser 與人工對帳。

### 2.7 文件去重成功，但不代表交易解析完成

- **現象：** 同一份 PDF 第一次收錄成功；以相同 bytes 再次收錄回報 `duplicate=true`。
- **處理：** 保留 SHA-256 idempotency，避免重複文件或重複交易；文件詳情仍顯示 0 筆交易。
- **重要區分：** Documents 收錄、PDF 解鎖、Statement parser、Finance 入帳、Excel 投影是不同階段。沒有經銀行 parser 與人工核對的交易，不得因文件已存在就寫入 Excel。

### 2.8 HANDOFF 與舊文件曾有互相矛盾的驗證數字

- **現象：** 舊交接文字同時留下 167/173/181 等前輪測試數字，也曾寫成「未重新下載 Gmail 附件」；這些描述會讓後續模型誤判目前狀態。
- **處理：** 在當時「只有文件收錄／解鎖、尚未入帳」的階段，以實際命令與服務回應校正文件；後續本次 Statement 里程碑已再更新為「中國信託帳單完成核對、Finance 匯入與 Excel 重建」。最新完整 backend 為 207 passed。
- **規則：** 歷史測試數字可保留作歷史，但目前狀態只能引用本次可重跑的命令與結果；不能把合成測試當成真實銀行驗收。

### 2.9 Git 行尾提示不是程式錯誤

- **現象：** `git diff --check` 通過，但 Git 顯示工作區 LF 下次可能轉成 CRLF 的提示。
- **判斷：** 這是 Windows checkout 的行尾轉換提示，不是測試、build 或安全失敗。
- **處理：** 不做與本次需求無關的全 repo 格式化；保留現有 `.gitattributes`/Git 行為，只確認 diff 沒有 whitespace error。

### 2.10 本機來源缺少 Gmail 內文，導致解鎖提示不可自動取得

- **現象：** 實際帳單已保存在 Documents，但該筆來源只有 `local_file`，沒有可讀的 `gmail_attachment` message context；即使 Windows Credential Manager 已保存個人解鎖資料，分析 API 仍會回報缺少郵件密碼提示。
- **處理：** 沒有把銀行規則硬編碼到 parser；後端分析 API 支援非秘密的 `subject`/`body` context，文件詳情 UI 只在本機來源顯示「郵件中的密碼規則提示」欄位。使用者只需提供規則文字，不得貼實際密碼。
- **結果：** 以不含個資、密碼的規則提示完成同一份實際中國信託帳單解鎖；parser 解析 1 筆交易列且與帳單合計相符，確認後建立 1 筆 Finance transaction。再次確認回報 `reused=true`。

### 2.11 Excel 輸出與舊 writer 測試契約仍有落差

- **現象：** 新版工作簿已包含信用卡交易欄位，完整 backend suite 仍有 3 個既有 `test_xlsx_writer.py` assertion 使用舊工作表順序／欄數。
- **處理：** 沒有為了讓測試通過而回退新的 Statement 欄位；保留失敗證據，後續獨立同步 writer 測試契約。
- **結果：** 已將測試契約同步至信用卡專用工作表與 15 欄交易明細；完整 backend suite 重新通過。

## 3. 最終驗證結果

| 項目 | 結果 | 備註 |
| --- | --- | --- |
| Backend tests | 通過 | 207 passed；2 個既有 FastAPI/anyio 相依套件棄用警告 |
| Frontend build | 通過 | `npm --prefix frontend run build` |
| Git diff check | 通過 | 未發現 whitespace error |
| Groq provider code path | 通過合成驗證 | 真實 key 尚未保存 |
| Gmail PDF 文件收錄 | 通過 | 使用 Gmail 網頁手動下載，不是內建 OAuth scheduler |
| SHA-256 重複收錄 | 通過 | 第二次收錄 `duplicate=true` |
| PDF 本機解鎖 | 通過 | 真實 Gmail 下載加密 PDF；郵件明示規則、AI 關閉 |
| Groq 真實 request | 未完成 | key 尚未保存；不是本次明示規則解鎖的前置 |
| BankStatementParser | 部分完成 | 中國信託版型已由實際帳單驗證；受限台新零交易版型有測試；其他版型與第二期盲測待完成 |
| Finance transaction / Excel 入帳 | 通過（限定範圍） | 實際中國信託帳單已核對、冪等匯入並重建專用 Excel |

## 4. 下一次執行前檢查

1. 先讀 `HANDOFF.md`、`FREE_AI_PASSWORD_RULE_PLAN.md` 與本文件，不要只看 UI 的 provider 預設值。
2. 以設定 API 或設定頁確認實際 runtime provider/model；不要假設已保存 Groq key。
3. 正式 migration/restart 後重驗來源郵件到明確規則的動態路徑；若另外驗證 Groq，先用合成提示，不要在聊天傳送 key、身分資料、生日或 PDF 密碼。
4. 執行 pytest 時使用 repository 根目錄下可寫的暫存目錄，避免重用受 Windows 權限保護的 backend 暫存路徑。
5. 後續做第二期盲測與其他已授權版型驗收；push 前檢查 `git status`、`git diff --check`、測試與 build；不要用 reset/checkout 覆蓋既有修改。
