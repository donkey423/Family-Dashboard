# 執行問題與處理紀錄

> 更新日期：2026-09-29
>
> 本文件只記錄工程執行時可觀察到的問題、處理方式與剩餘限制，不保存帳單內容、身分資料、生日、PDF 密碼、API key、OAuth token 或其他秘密。

## 1. 本次範圍

本次工作同時完成了兩件事：

1. 將免費 AI 密碼規則 provider 的程式、設定頁與驗收狀態更新到文件。
2. 重新執行後端測試、前端 production build，並以一份使用者授權的 Gmail PDF 驗證文件收錄、SHA-256 去重及預覽失敗時不誤入帳。

本次不是銀行專用 PDF parser 或 PDF → Excel 正式入帳的完成驗收。實際結果仍是「文件已收錄、尚未解鎖/解析/入帳」。

## 2. 問題與處理

### 2.1 本機分支落後最新遠端文件提交

- **現象：** 接手時本機 `master` 為 `001ca5d`，`origin/main` 已是 `4f9bfb5`；工作區另外有先前未提交的 Groq 程式與文件修改。
- **風險：** 直接 push 會因遠端不是本機歷史的 fast-forward 而失敗；直接 reset、checkout 或覆蓋又可能遺失既有實作。
- **處理：** 保留工作區修改，先讀取並以目前程式行為校正文件；完成本地 commit 後再把 `origin/main` 整合進來，最後以明確的 `master:main` 推送。
- **結論：** 本次以不覆蓋遠端歷史的 merge 方式整合；Groq 實作 `eeb6883` 已進入 `main`。使用者之後再次 push 得到 `Everything up-to-date` 且回報 local working tree 乾淨。不可再把「Groq 仍只存在本機未提交」當目前狀態。

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
- **目前限制：** Groq 程式已在 `main`，但最後一次有證據的 runtime 仍是 OpenAI。只有完成 safe-switch、重新讀取 Active Provider，並跑過真實 synthetic Groq request，才可宣稱 runtime 已切換。

### 2.5 內建 Gmail OAuth 與 Gmail 網頁操作不是同一條連線

- **現象：** 使用者可在 Gmail 網頁看到並下載授權的 PDF，但 FamilyHub 的內建 Gmail OAuth 狀態仍未設定/未授權。
- **原因：** Gmail 網頁登入、ChatGPT/Gmail app 連線與 FamilyHub 自己保存的 readonly OAuth token 是不同的授權邊界，不能互相推定已連線。
- **處理：** 本次只把 Gmail 網頁下載的 PDF 交給 FamilyHub 文件入口；沒有把它記成內建 Gmail scheduler 已成功抓取，也沒有改寫 FamilyHub OAuth 設定。
- **後續：** 若要驗收長期自動化，仍需在 Windows 本機完成 FamilyHub readonly OAuth，並另外驗證手動同步、定時同步與 token refresh。

### 2.6 真實 PDF 預覽被目前 OpenAI 額度擋住

- **現象：** 實際開啟收錄的 PDF 時，runtime 使用既有 OpenAI profile，AI 預覽因帳戶額度不足停止。
- **原因：** Groq 尚未在本機保存 key；系統遵守「Groq 失敗/未設定不得自動 fallback 到可能付費的 OpenAI」的 provider 邊界，同時也不會把現有 OpenAI profile 偷換成 Groq。
- **處理：** 預覽回到安全的 pending/錯誤結果，沒有猜密碼、沒有把完整帳單送出、沒有建立 Finance transaction。
- **目前結果：** 文件收錄成功，但仍未解鎖、未解析、未入帳；這不是 Gmail 下載失敗，也不是銀行 parser 成功。
- **後續：** 先在設定頁保存 Groq key，以合成提示驗證 Groq 真實 response，再重跑授權 PDF；若仍選 OpenAI，額度問題需由使用者自行處理。

### 2.7 文件去重成功，但不代表交易解析完成

- **現象：** 同一份 PDF 第一次收錄成功；以相同 bytes 再次收錄回報 `duplicate=true`。
- **處理：** 保留 SHA-256 idempotency，避免重複文件或重複交易；文件詳情仍顯示 0 筆交易。
- **重要區分：** Documents 收錄、PDF 解鎖、Statement parser、Finance 入帳、Excel 投影是不同階段。沒有經銀行 parser 與人工核對的交易，不得因文件已存在就寫入 Excel。

### 2.8 HANDOFF 與舊文件曾有互相矛盾的驗證數字

- **現象：** 舊交接文字同時留下 167/173/181 等前輪測試數字，也曾寫成「未重新下載 Gmail 附件」；這些描述會讓後續模型誤判目前狀態。
- **處理：** 本次以實際命令與目前服務回應為準，將 `HANDOFF.md`、`FREE_AI_PASSWORD_RULE_PLAN.md`、`IMPLEMENTATION_PLAN.md`、`TASKS.md`、`README.md` 與 `docs/operations.md` 更新為 187 passed、build 成功，以及「手動 Gmail PDF 收錄/去重、OpenAI 額度不足、0 筆交易」的現況。
- **規則：** 歷史測試數字可保留作歷史，但目前狀態只能引用本次可重跑的命令與結果；不能把合成測試當成真實銀行驗收。

### 2.9 Git 行尾提示不是程式錯誤

- **現象：** `git diff --check` 通過，但 Git 顯示工作區 LF 下次可能轉成 CRLF 的提示。
- **判斷：** 這是 Windows checkout 的行尾轉換提示，不是測試、build 或安全失敗。
- **處理：** 不做與本次需求無關的全 repo 格式化；保留現有 `.gitattributes`/Git 行為，只確認 diff 沒有 whitespace error。

### 2.10 Groq 程式已合併，但 runtime 尚未等同 Groq

- **現象：** Groq adapter、provider API/UI 與合成測試都已在 `main`，但最後一次有證據的 runtime smoke check 仍使用 OpenAI / `gpt-4.1-mini`。
- **原因：** UI 的 Groq 預設只是 Recommended / new-setup Default；真正 runtime 由 backend 的 Active Provider + Windows SecretStore credential 決定。
- **規則：** 只有重新讀取 `/api/security/ai-provider` 並完成真實 synthetic Groq request，才可宣稱 runtime 已切 Groq。

### 2.11 Provider 切換缺少 preflight

- **現象：** `AIProviderService.configure()` 會保存新設定、更新 DB profile，之後清理舊 credential，但不先驗證新 provider/model。
- **風險：** credential 輸入錯誤、模型下架、權限不足或 Structured Output 不相容，都可能到第一次真實 request 才發現。
- **處理方向：** 先增加固定 synthetic prompt 的 Test Connection / preflight，不讀 Gmail/個資、不保存新設定；只有 preflight 成功才切換 Active Provider。失敗時舊 provider 保持可用。
- **範圍：** 仍維持單一 Active Provider；不做自動 fallback chain。

### 2.12 AI provider status 可能誤報 configured

- **現象：** `GET /api/security/ai-provider` 目前只檢查 DB profile 是否存在；若 DB row 還在但 Windows SecretStore credential 遺失，UI 仍可能顯示已設定。
- **風險：** 使用者在真正解鎖 PDF 時才發現 provider 不可用。
- **處理方向：** status API 應安全區分 profile 存在與 credential 可用，例如增加 `credential_available`，但絕不回傳 credential 本身。SecretStore 整體不可用時應明確 fail closed。

### 2.13 Provider UI 狀態不夠明確

- **現象：** 設定頁狀態徽章目前主要顯示 model，沒有直接寫出 Active Provider。
- **風險：** 容易把「表單預設 Groq」誤認為「目前正在使用 Groq」。
- **處理方向：** 顯示「目前使用：Provider · Model」，並拆成「測試連線」與「保存並切換」兩個動作。

## 3. 最終驗證結果

| 項目 | 結果 | 備註 |
| --- | --- | --- |
| Backend tests | 通過 | 187 passed；2 個既有棄用警告 |
| Frontend build | 通過 | `npm --prefix frontend run build` |
| Git diff check | 通過 | 未發現 whitespace error |
| Groq provider code path | 通過合成驗證 | 真實 runtime activation 尚未完成；不得由 UI 預設推定 |
| Provider safe switch | 未完成 | Test Connection/preflight、credential health status、Active Provider 顯示待補 |
| Gmail PDF 文件收錄 | 通過 | 使用 Gmail 網頁手動下載，不是內建 OAuth scheduler |
| SHA-256 重複收錄 | 通過 | 第二次收錄 `duplicate=true` |
| PDF AI 解鎖 | 未完成 | 現存 OpenAI profile 額度不足 |
| BankStatementParser | 未完成 | 尚需兩期授權樣本 |
| Finance transaction / Excel 入帳 | 未完成 | 本次實際 PDF 為 0 筆交易 |

## 4. 下一次執行前檢查

1. 先讀 `HANDOFF.md`、`FREE_AI_PASSWORD_RULE_PLAN.md` 與本文件，不要只看 UI 的 provider 預設值。
2. 以設定 API 或設定頁確認實際 runtime provider/model；不要假設已保存 Groq key。
3. 先用合成提示驗證 Groq，再處理授權真實 PDF；不要在聊天傳送 key、身分資料、生日或 PDF 密碼。
4. 執行 pytest 時使用 repository 根目錄下可寫的暫存目錄，避免重用受 Windows 權限保護的 backend 暫存路徑。
5. push 前檢查 `git status`、`git diff --check`、測試與 build；不要用 reset/checkout 覆蓋既有修改。
