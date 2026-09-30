# 交接

## 2026-09-30 消費分類／Donut 規劃

- 使用者已明确把「每笔交易分类、同类归组、支出 Donut、一层类別点入商家小计再看逐笔明细」批准为下一阶段产品功能。
- 新增 canonical 规划：`CATEGORY_SPENDING_PLAN.md`。目前**只有设计与 Test Matrix，尚未实作**；没有新增 migration、model、API、chart dependency 或 frontend test dependency。
- 核心设计：V1 不把 category 写回 `FinanceTransaction`；新增 Category / CategoryRule / TransactionCategoryOverride，由 `CategorizationService` 在 read time 解析 Effective Category。单笔 override > exact rule > contains rule > system default > 未分类。
- 财务语义与显示分类分开：purchase/fee/interest/refund/payment 继续沿用现有 Finance 语义；分类不能让 payment 进入消费，也不能改变 amount/date/source/row_hash/statement identity。
- Drill-down 固定为 Category → Merchant subtotal → Transaction；V1 不做 subcategory taxonomy、AI 分类、Budget、Tag、汇率换算或通用 Dashboard builder。
- Donut 单次只显示一种币别；Top 5 +「其余类别」，真正的 `uncategorized` 显示「未分类」。负净额 category 不画 slice，另列退款／抵扣。
- 前端计划采用 Recharts，并首次加入最小 Vitest + React Testing Library；不导入大型 E2E framework。
- Excel 必须复用同一个 CategorizationService，并让 rule/override 变化进入 snapshot fingerprint；只改分类也要触发重建。
- C1-C5 与完整 P0/P1/P2 Test Matrix 已写入 CATEGORY_SPENDING_PLAN；TASKS 已新增 M12。
- 本轮是**纯文件规划更新**，没有修改业务程式，因此未重跑 backend/frontend，也未执行新的 E2E-GMAIL-3BANK；按 AGENTS 只能宣称规划文件已更新，不能宣称分类功能或项目验收完成。

## 2026-09-30 推送前驗證狀態

- 本輪重新執行完整 backend：258 passed、2 個既有相依套件棄用警告；frontend production build 與 `git diff --check` 成功。只提交程式、測試及文件，原始帳單、資料庫、秘密、build 產物及未追蹤測試暫存資料夾不納入 Git。
- 本輪 `E2E-GMAIL-3BANK` 的重新下載關卡為 **BLOCKED**：以 `in:anywhere`、未設日期搜尋並找到中國信託、國泰世華及永豐九月月帳單，確認實際郵件的密碼格式後嘗試下載；三家下載事件均逾時，中國信託另以已顯示的附件連結下載仍逾時。未取得可驗證的新下載檔案，未宣稱本輪全新 Gmail 驗收通過；原因尚未確認，後續先恢復附件下載再重跑完整外部關卡。
- 本輪用上一輪成功下載的三份加密原件做本機回歸：解鎖、1/19/31 列逐筆來源與 API 比對、摘要合計、認列日期及重跑冪等均 PASS。這不取代重新下載關卡；沒有 AI request 或正式 confirm，Finance 仍為 18 筆。
- 本機 health 及正常 Windows 使用者環境的既有私有 HTTPS 首頁/health 已確認屬於本專案，並載入本輪 build。沙箱 HTTPS 曾因憑證驗證失敗，未關閉 TLS 驗證；實體手機未驗收。

## 2026-09-30 實作修正後的三銀行 Gmail 驗收

使用者新增交付要求：每次完成本專案工作前都要重新從 Gmail 下載三家不同銀行的信用卡對帳單並成功解鎖、解析及核對。已寫入 AGENTS 完成標準、TASKS 及 IMPLEMENTATION_PLAN 第 4.1 節，測試 ID 為 `E2E-GMAIL-3BANK`。此要求不授權正式資料自動確認入帳；任一 FAIL/BLOCKED 都不能宣稱專案驗收完成。

**本次結果：PASS，3/3 通過。** 最後修正後已再次從 Gmail 下載三家九月份原始加密月帳單。搜尋使用 `in:anywhere has:attachment filename:pdf {信用卡 "credit card"} {帳單 對帳單 賬單 statement}`，未設日期，搜尋範圍涵蓋可存取信箱最早信件至當下；實際只查閱首頁選取三家，沒有宣稱逐封查完整個信箱。當次工具清單沒有 Gmail MCP，採已登入 Gmail 網頁下載、`POST /api/documents` 及既有 preview/statement-analysis；不計為 Codex MCP/cron 收件驗收。永豐來源在垃圾桶，未移動或恢復郵件。

| 銀行 / 郵件帳期 | Gmail 重新下載 | 來源格式確認 | 加密解鎖 | 交易解析與核對 | 冪等重跑 | 結果 |
| --- | --- | --- | --- | --- | --- | --- |
| 中國信託 / 2026-09 | PASS | PASS | PASS，2 頁 | PASS，1 列；獨立原文欄位與當次 parser/API 全列相符，合計差額零 | 同一 Document/Statement，來源/明細筆數不變 | PASS |
| 國泰世華 / 2026-09 | PASS | PASS | PASS，3 頁 | PASS，19 列；包含繳款與利息，逐列/摘要/本期消費核對相符，差額零 | 同一 Document/Statement，來源/明細筆數不變 | PASS |
| 永豐 / 2026-09 | PASS，非繳款聯 | PASS | PASS，4 頁 | PASS，31 列；含退款、繳款、費用及本期分期額，逐列/摘要核對相符，差額零 | 同一 Document/Statement，來源/明細筆數不變 | PASS |

- 三份原件均確認是加密 PDF；下載至使用者 Downloads，測試原件不加入 Git。服務安全資料 presence API 確認身分證與生日均已保存，秘密不讀給模型。
- 已修正兩家解鎖失敗原因：`ExplicitPasswordRuleParser` 新增完整證號的括號說明與「開啟帳單請輸入正卡人資料」明示句型；部分證號、多欄組合、大小寫歧義仍 fail closed。先讀實際郵件完整必要上下文，未修改提示迎合 parser，也沒有猜密碼或允許 AI。
- `taiwan-credit-card-v2` 新增國泰世華及永豐已驗證 TWD 文字版型，保留中國信託及受限台新。核對上期、繳款、本期列帳、利息與應繳額；永豐分期只取本期額，未到期餘額不計支出。未知/不完整列、缺核對欄位或不平仍停止，不代表通用銀行解析。
- 使用者已明確允許未列日期的利息按帳單結帳日認列。`StatementData.closing_date` 及共用 resolver 在正規化/月彙總採此政策，原始日期仍為空；API 明細提供 effective date/date basis，確認入帳的 raw_json 保留來源日期與認列依據。國泰本次有 1 列套用政策；普通消費、費用、繳款缺日期或利息缺明示結帳日仍 pending，不放寬核對。舊 Statement JSON 沒有 closing_date 仍可讀。
- 中國信託原本已入帳，故三家均以本次解鎖文字另執行當前 parser，不只看 cached/imported。原文獨立欄位抽查程式按全列日期/商家/金額/幣別/類型對照 parser 與 API，再核對列數及摘要；國泰、永豐交易頁另已視覺檢查。本次不是另一期未參與調整的盲測。
- 已修正文件詳情只讀摘要列表造成「沒有新增交易」的 UI bug，改讀 `statementDetail` 並清除舊文件狀態。Tailscale 桌面瀏覽器實測國泰 19 列含「結帳日認列」、永豐 31 列，皆不再誤顯示零交易；頁面無水平溢出。Chrome 尺寸覆寫呼叫未改變實際 viewport，手機尺寸及實體手機未驗收；目前沒有獨立 frontend 自動化測試框架。
- 本次只收錄/預覽/分析與冪等重跑，未呼叫正式 confirm，AI provider request 為零；正式 Finance 前後均為 18 筆，國泰/永豐草稿等待人工確認，不算正式入帳或真實 Excel 驗收。合成隔離 tests 已覆蓋認列日期、確認後 provenance、重複確認及 Excel 月彙總。附件、原文、秘密與消費內容不寫 repository。
- 完整 backend **258 passed、2 個既有相依套件棄用警告**；frontend TypeScript/Vite production build、`git diff --check` 成功。Windows 長路徑測試目錄曾失敗，改用 Documents/Codex 下短且唯一的 pytest basetemp；測試與 build 不取代上方三銀行外部關卡。
- 長駐服務曾再次退出，排程 LastTaskResult 為 `3221225786`（程序中斷），沒有足夠事件證據判定來源；已用既有 `FamilyFinanceHub` 排程恢復，資料庫與路由不變。接手先驗 health/帳戶，不在沙箱背景起正式服務；跨次對話持續運行、重開機觸發及意外退出原因仍需驗證。

**下一步：** 第二期未參與調整的真實盲測、Codex Gmail cron 首次真實執行與跨日重跑、Groq runtime activation 及實體手機驗收仍未完成。每次交付重新跑三銀行；本次 PASS 不是永久豁免，也不是無人確認入帳授權。

## 2026-09-30 Windows 安全儲存修復

- 原因已確認：3000 埠的 FamilyHub 程序以 `CodexSandboxOffline` 執行；缺少有效的 Windows 憑證登入工作階段，保存回報 Windows 1312，也讀不到使用者原有憑證。先前「未保存」不代表原帳戶資料已遺失。
- 已停止此已核對的沙箱程序，改由既有 `FamilyFinanceHub` 互動式登入排程啟動；實際 listener owner 已確認為登入中的 Windows 使用者。服務仍使用 `data/family-finance-hub-live.db`，18 筆有效交易保留。
- `KeyringSecretStore.verify_access()` 與啟動腳本已加入保管庫寫入/讀取/清除閘門。Probe 使用獨立隨機 service 與合成值，不變更應用程式憑證；任何一步失敗即拒絕啟動。此主機沙箱啟動拒絕及正常登入帳戶通過均已實測。
- 設定頁以使用者當次已填寫的欄位再次安全保存成功，欄位已清空，重新載入後身分證、生日皆顯示「已保存」。本機 API 及既有 Tailscale HTTPS 設定頁/health 均已驗證；實體手機及重開機自動觸發未重驗。
- 聚焦驗證：`test_keyring_store.py`、`test_imports.py`、`test_pdf_api.py` 共 47 passed、2 個既有相依套件棄用警告；frontend production build 成功。本輪未重跑完整 backend suite，未發出 AI provider request。
- 正確帳戶也重新讀到既有 OpenAI key：狀態 API 為 `openai / gpt-4.1-mini`、`credential_available=true`。這只確認本機憑證可讀，不代表 key 授權/額度有效，也不代表已切換 Groq；S3F-B 仍待使用者提供 Groq key 與真實驗收。

## 2026-09-30 Codex MCP Gmail 主流程

- 使用者已決定移除網站 Gmail OAuth 主流程。設定頁不再提供 OAuth JSON、連接帳戶、立即同步或內建排程控制；Gmail 授權、搜尋及排程改由 Codex Gmail MCP／Codex 自動化負責。
- 已新增 `POST /api/integrations/codex-mcp/gmail/import`：接收附件與來源識別，先套用全域大小限制、遮罩密碼提示、計算 SHA-256，再透過 `StoragePort` 保存本機文件並建立 `codex_mcp_gmail` source。原始 Gmail ID 只用於計算不可逆 source key；subject、sender、完整本文、身分資料及實際密碼不落盤。
- 相同來源及相同內容重跑為冪等；同一 source key 對應不同 bytes 回 409；已撤銷文件不會被重新收件恢復。PDF 後續仍走既有解鎖、Statement parser、合計核對與人工確認，Codex 收件不會直接建立 Finance transaction。
- 已新增 `GET /api/integrations/codex-mcp/status` 供 UI 顯示本機模式與最近匯入狀態。Legacy Gmail OAuth/API/scheduler 預設停用，舊 API 回 410；`FAMILY_FINANCE_HUB_LEGACY_GMAIL_OAUTH=true` 只供歷史相容／測試。
- 程式聚焦驗證已通過：Codex MCP import、來源衝突、敏感資料不落盤、legacy 410、Codex 提示解鎖共 27 passed；完整 backend 為 215 passed、2 個既有相依套件棄用警告，frontend production build 成功。Live server 已重新啟動；本機 status API、legacy 410 與 Tailscale 設定頁的 Codex MCP 畫面均已實測。
- Codex 應用程式已建立並啟用「家庭收支 Gmail 帳單收錄」自動化：`gpt-6-luna`、Max reasoning、每 30 分鐘執行，最近 45 天補抓，僅將 PDF、來源識別及密碼提示附近的必要文字送入本機 endpoint；沒有新附件時保持安靜。首次真實 Gmail 執行與至少一次冪等重跑仍待驗收，完成前不可宣稱跨日自動收件已驗收。

## 2026-09-29 AI Provider Safe Switch 里程碑

- 已新增 `POST /api/security/ai-provider/test`：只用固定 synthetic 密碼規則與指定 provider/model 發出一次有界限 request，不讀 Gmail、個資或 PDF，不保存 credential，也不改 Active Provider。
- `POST /api/security/ai-provider` 現在會在任何 SecretStore/DB 寫入前重新 preflight；auth、rate limit、quota、model、schema、timeout、service failure 都會 fail closed 並回穩定 reason code。失敗不會替換舊 profile、刪除舊 credential 或 fallback 到 OpenAI。
- `GET /api/security/ai-provider` 現在分開回報 `configured` 與 `credential_available`。設定頁明確顯示作用中 Provider、模型與憑證狀態，並提供「測試連線」及「保存並切換」。PDF 預覽也只有兩個狀態都可用時才啟用 AI，credential 遺失時不會先發出失敗的 AI request。
- 驗證：完整 backend 211 passed、2 個既有相依套件棄用警告；frontend production build 成功；`git diff --check` 通過。合成測試已覆蓋不落盤測試、失敗保留舊設定、憑證遺失狀態及安全錯誤碼；Tailscale 網址實測設定頁狀態及 PDF 預覽的 AI 停用閘門正確。
- 本機 runtime 尚未切到 Groq：Active Provider 仍是 `OpenAI / gpt-4.1-mini`。2026-09-30 修正 Windows 執行帳戶後既有 key 已可讀（`credential_available=true`），但未重驗 provider 授權/額度。必須由使用者在設定頁提供可用 Groq key，才能完成真實 request、cache 與 synthetic encrypted PDF 的 S3F-B 驗收；不得把合成測試寫成真實 Groq 成功。

## 2026-09-29 信用卡帳單匯入里程碑

- 已完成第一個實際中國信託加密信用卡帳單的端到端驗證：來源文件 → 郵件規則提示 → Windows Credential Manager 解鎖 → `TaiwanCreditCardStatementParser` → 帳單合計核對 → 使用者確認 → Finance transaction → `data/exports/家庭收支記錄.xlsx`。
- 已新增 `0011_statement_import` migration、Statement/StatementLine/匯入狀態模型、分析／確認 API、冪等入帳，以及文件詳情的「分析帳單／確認匯入」介面。支援中國信託交易列與受限台新零交易版型；未知版型、交易列不完整或對帳不符會停在 pending。
- 實際服務已在 `data/family-finance-hub-live.db` 完成 migration；本次匯入後 Finance 有 18 筆有效交易，Excel 已重建為含 18 筆交易明細的專用工作簿。再次確認同一 Statement 回報 `reused=true`，沒有重複入帳。
- 本機來源沒有保留 Gmail message context，因此 UI 新增「郵件中的密碼規則提示」fallback；只接受規則文字，不接受實際密碼。Gmail 附件若保留來源郵件，仍優先自動使用該郵件提示。
- 驗證：帳單／入帳聚焦測試 33 passed；前端 production build 成功；最新完整 backend 為 211 passed、2 個既有套件棄用警告；Tailscale 瀏覽器實測首頁與 `/api/health` 可用。
- 尚未完成：Codex Gmail cron 的真實／跨日收件驗收、第二期未參與調整的真實盲測、其他銀行版型、OCR runtime、實體 iPhone 驗收。不要把單一中國信託 parser 宣稱成通用銀行 parser。

## 2026-09-29 Gmail 密碼格式確認閘門

- 加密 Gmail PDF 現在只採來源郵件的 subject/body/sender，不再將預覽表單的手動提示與 Gmail 提示合併；本機上傳文件仍可手動提供提示。
- 新增本機 `ExplicitPasswordRuleParser`：郵件明確指定完整身分證字號及英文字母大小寫時，建立單一受限 DSL 規則；若同時明確區分本國籍身分證與外籍生日 `YYYYMMDD`，只建立這兩個候選並按郵件順序嘗試。成功後只保存真正命中的規則；提示缺格式、局部證號或多欄位組合不走此快速路徑，明確候選全失敗時回報 `pdf_wrong_password`，不再呼叫 AI 改猜。
- 成功解鎖後仍只保存不含秘密的 verified rule；身分證字號、生日與候選密碼不進 SQLite、log 或 AI request。此修改只處理解鎖規則；帳單交易解析與 Excel 入帳另由本次 Statement 流程負責。
- 最新聚焦回歸：`test_password_rules.py`、`test_pdf_processor.py`、`test_pdf_processing.py`、`test_pdf_api.py` 共 78 passed、2 個既有相依套件棄用警告。較早的完整後端為 197 passed、3 failed；失敗均來自工作樹原有、尚未完成同步測試的 Excel 新工作表／欄位修改（`test_xlsx_writer.py`），不是本次 Gmail/PDF 變更。前端未修改，較早的 production build 成功。

## 2026-09-29 免費 AI provider 與真實流程狀態

- GitHub `main` 已包含 Groq 實作 commit `eeb6883`；2026-09-29 使用者已確認本機 push 回覆 `Everything up-to-date` 且工作區乾淨。後續模型不可再把 Groq 描述成「只在本機未提交」。

- 已完成第一階段 provider-neutral 實作：Groq Free 預設 `openai/gpt-oss-20b`、既有 OpenAI 相容路徑、設定 API/UI provider 選擇，以及不送 `store` 的 Groq Responses payload。兩者共用既有 `PasswordRule` DSL、遮罩後提示、verified rule cache、SecretStore 與本機 PasswordComposer。
- Groq 失敗、429、schema/網路錯誤會留在 pending/manual 路徑，不會自動呼叫可能付費的 OpenAI；API key 不進 repo、SQLite、log 或前端持久化。這次完整驗證為 backend 187 passed、frontend production build 成功，另有 2 個既有相依套件棄用警告。
- 最後一次有證據的 runtime smoke check 仍回報 Active Provider=`openai`、Model=`gpt-4.1-mini`。Groq 程式已在 `main`，但 Git 狀態不代表 runtime 已切換；設定頁的 Groq 預設也不會覆寫既有 Active Provider。切換後必須重新讀取 `/api/security/ai-provider` 才能確認真正使用的 provider/model。
- 本次已從使用者授權的 Gmail 網頁下載一份信用卡 PDF，收錄到 FamilyHub 文件匣；同一 bytes 再次收錄回報 `duplicate=true`。FamilyHub 內建 Gmail OAuth 仍未授權，所以這次不是內建 Gmail scheduler 的驗收。
- 舊 runtime 第一次允許 AI 的預覽仍因既有 OpenAI profile 額度不足而停止；這是 provider 問題，不是錯誤密碼。確認郵件明示格式後，改以目前 parser 產生的受限規則、關閉 AI，透過 live processor 與 Windows SecretStore 成功解鎖同一份 Gmail 下載 PDF。
- 後續實際驗證已完成：中國信託加密帳單由 parser 解析交易列並核對帳單合計，確認後建立 Finance transaction，再重建 Excel；重複確認回報 `reused=true`。未知銀行版型仍停在待處理，不猜測入帳。
- 此次 Gmail 搜尋使用 `in:anywhere`，但下載由已登入的 Gmail 網頁手動完成；這是 2026-09-29 的歷史驗證。現行主流程已改由 Codex MCP 收件，分析與確認匯入仍維持明確使用者操作。
- 尚未完成：S3F-B Groq runtime activation、真實 Groq request、第二期盲測、更多銀行 parser 與 Codex Gmail cron 真實驗收。S3F-C safe-switch 已完成；Groq 不再是明示格式帳單本機解鎖的前置，取得 key 後依 `GROQ_RUNTIME_REVIEW.md` 完成真實 Groq 驗收。

本次執行遇到的 Git 分支同步、Windows pytest 暫存權限、runtime provider 未切換、Gmail OAuth 邊界、OpenAI 額度及文件狀態漂移，已逐項記錄在 [EXECUTION_ISSUES.md](EXECUTION_ISSUES.md)。

Groq 的最新深度審查與執行規格見 [GROQ_RUNTIME_REVIEW.md](GROQ_RUNTIME_REVIEW.md)；`FREE_AI_PASSWORD_RULE_PLAN.md` 保留 provider 設計與安全邊界。

## 目前接手入口

文件解鎖設定頁只需保存身分證字號及/或生日，系統內部建立固定個人 profile；來源郵件明確描述完整格式時先走本機 parser，只有其餘規則才需要可選 AI。舊銀行/成員 profile API 保留相容，但不是新 UI 的前置。中國信託已完成真實 Finance/Excel，國泰及永豐已完成本次解鎖、交易解析、核對及草稿冪等；第二期盲測、Codex cron 真實收件、其他未知版型及實體手機仍未完成。

近期目標已收斂為「Codex MCP 收錄信用卡 PDF，FamilyHub 解鎖、解析、核對後更新每月支出 Excel」。Web 只補設定、核對確認及例外處理，不先擴充平台或完整 Dashboard。S0-S9 工作包依 2026-09-30 決策執行；三銀行當次關卡已通過，接著完成第二期盲測及 Codex cron 真實執行，不擴張平台。

S1-S3 與 S3F-C 已完成補強及隔離合成測試；S4 已有 Statement 契約、月支出語意、正規化閘門與中國信託/國泰/永豐已驗證版型，未知版型及第二期仍需授權樣本。接手重驗基線，從未完成處繼續，不重做已有功能、不把規格當程式完成。

- 本機 `master` 已包含 `ARCHITECTURE_REVIEW_BRIEF.md`。Tailscale Serve 既有設定為私有 HTTPS → `localhost:3000`，網頁與 API 現由同一 FastAPI 服務提供；個人解鎖及單一服務部署已在此主機驗證。此主機使用 `data/family-finance-hub-live.db`，由舊資料庫的一致性快照升級至 `0011_statement_import`；原始舊 DB 與 `data/backups/2026-09-29-pre-deploy/` 保留。舊 DB 不可直接用新版程式啟動。
- `FamilyFinanceHub` Windows 排程在使用者登入後啟動 `scripts/start_server.ps1 -DatabasePath data/family-finance-hub-live.db`，目前由手動觸發的排程執行中。Tailscale HTTPS 首頁與 `/api/dashboard` 均驗證成功；重新開機後的自動觸發及實體 iPhone 尚未驗證。其他舊開發連接埠可能仍寫入舊 DB，兩者不自動同步，應只用新的 Tailscale 網址操作。
- 此主機的跨專案手機預覽工具位於全域 Codex 設定，不屬於本 repository。2026-09-29 以兩個只回傳測試文字的服務驗證 `3001 -> HTTPS 8443`、`3002 -> HTTPS 8444` 可並行、重複註冊保持原路由、錯誤首頁文字與覆蓋 `443` 均被拒絕；測試路由及服務已移除。最後再驗證 Serve 僅剩 `443 -> localhost:3000`、本站 `/api/health` 回傳 200。未以實體手機驗收，也未替尚不存在的新專案預先建立網址。
- 前輪 S0 基線：backend 128 passed、2 個既有棄用警告，frontend production build 成功。變更後聚焦測試與完整 suite 見上方及下方；目前 Alembic head 為 `0011_statement_import`。`test_xlsx_writer.py` 已同步新版信用卡欄位契約。
- 固定取捨：S4 一家銀行 parser → S5 最小模型 → S6 原子入帳與正確 Excel → S7 最小設定/待處理 → S8 Codex MCP 受控收件 → S9 固定 Windows 入口。保留 Documents 1:N、SecretStore、撤銷/恢復及 Excel 安全投影；不擴充 DSL/OCR/domain。
- Legacy Gmail History/OAuth/scheduler 凍結為相容程式，預設不啟用；日常搜尋與排程由 Codex 管理。Excel 背景檢查先沿用；Excel 從選配改為主要交付，不代表未知銀行已具正確信用卡語意。
- 外部關卡：Codex Gmail cron 首次真實執行與重跑、S4 第二期未參與調整的真實樣本及逐筆核對。缺件不可猜測，不回填聊天中的個人秘密，不以合成測試代替外部驗收。
- 下一步：完成 Codex cron 真實收件驗收，再以另一份已授權期別盲測 parser。未知版型先維持 pending，不擴充多銀行 framework。原始文件不進 repo、聊天或外部 AI。

## 目前狀態

產品「家庭收支記錄」v0.1 為 Windows 主機上的 local-first Modular Monolith。M1-M5.4 的共用平台與既定流程已實作：Documents/1:N source records、SHA-256 冪等匯入、通用 Finance CSV、Dashboard/Search/Jobs、密碼規則安全邊界、加密 PDF transient preview，以及 Codex MCP Gmail 本機匯入。Legacy Gmail 手動/增量同步與 scheduler 仍在程式中但預設停用。M7.1-M7.5 的搜尋、來源追溯、月份／幣別總覽、設定分組、PDF 預覽體驗及手機排版，以及 M8 的專用 Excel 投影與 Statement 匯入流程也已實作；目前 parser 範圍仍限於已驗證版型，Codex cron 長期驗收與外部環境驗收尚未完成。

PDF 文字抽取不足時才走 `OcrProvider`；目前 Tesseract adapter 會先以 `--list-langs` 確認設定所需 traineddata，再使用 PDFium 在記憶體渲染、透過 stdin 傳頁面影像，最多 20 頁、每頁約 8 MP、總逾時 120 秒。缺少語言資料會回報獨立狀態；OCR 文字僅保留於此次處理記憶體，不寫 DB/log/文件暫存；OCR 失敗不影響原始/解密 PDF 預覽。OCR 執行檔和 `chi_tra`/`eng` 語言資料尚未在此 Windows 主機安裝/驗收。Statement parser 目前限於中國信託、國泰世華、永豐的已驗證文字版型及受限台新零交易版型；未知 PDF 不猜測或自動建立 Finance transaction。

舊 FakeGmail 測試只保護 legacy 相容路徑，不代表現行 Gmail 連線狀態。網站不再提供 OAuth 或自動同步控制；新附件由 Codex Gmail MCP 呼叫本機 import endpoint。支援版型仍需在文件詳情分析並確認後才走 Statement 入帳，CSV 手動匯入維持通用流程。

通用 CSV 匯入會拒絕無效日期、非有限/超精度金額、格式不合的幣別與欄位數異常，失敗資料不會留下部分交易。CSV 目前由手動匯入處理；Codex 日常自動化限定 PDF 帳單。完整交易頁提供月份／幣別篩選和分頁；首頁只讀選定期間最近 8 筆，Dashboard 金額由 SQLite 依期間與幣別聚合。Alembic 與 API 共用 `FAMILY_FINANCE_HUB_DATABASE_URL`。

S1 的 Gmail History/query 測試仍保留 legacy 相容性；不再代表產品日常路徑。S2 已驗證 HTML table row/cell、inline 空白、重疊上下文保序，以及先遮罩再套輸出上限；測試使用合成值。S3 已把 PDF 來源讀取、寄件者唯一匹配、已驗證規則重用、本機密碼組合、解密與文字抽取協調移到可直接測試的 application use case；格式錯誤／多地址不自動匹配，明確手動 profile 優先。測試確認歧義時不讀秘密、匹配失敗不遍歷其他家庭成員秘密、`/content` 保持原始 bytes、`/preview` 維持 no-store。另已完成 Gmail 網頁手動下載、文件收錄/去重及真實加密 PDF 解鎖/文字抽取；現行收件改由 Codex MCP。

S4 的 `finance/statements/contracts.py` 保留純輸入/輸出、unsupported 原因碼、符號/對帳限制及按日期/幣別的月彙總。`taiwan_credit_cards.py` 只接已驗證中國信託/國泰/永豐及受限台新版型。`normalization.py` 以 `statement_id + line_index` 產生穩定 SHA-256 row hash，保留合法相同交易，只讓 `ready` 進入確認入帳。缺日期只有「利息 + 明示結帳日」適用使用者批准的認列政策，其餘仍 pending；unknown、未核對或對帳不符不能靠確認繞過。

## 帳單撤銷／恢復已完成

- 文件頁提供「有效／已撤銷」與撤銷／恢復操作，確認前顯示關聯交易筆數、各幣別收入／支出／淨額及撤銷原因。
- 撤銷會讓對應交易退出 Dashboard、交易列表與搜尋；保留來源、交易與工作紀錄，可恢復既有交易而不重新解析。沒有交易的文件恢復後仍為零筆。
- 本機上傳、Codex MCP 與 legacy Gmail 匯入均保留相同 SHA-256 文件的撤銷狀態；不同內容仍視為新文件，尚無語意層級帳單去重。保存本機副本不會恢復收支。
- 狀態更新與工作紀錄在同一 transaction；重複操作不新增紀錄，預覽後狀態或影響金額改變則要求重新確認。
- `0009_document_revocation` 已在隔離 SQLite 升級驗證；既有文件預設有效。使用中的資料庫尚未遷移。

## 使用體驗評估與待辦

2026-09-27 已完成 M7.1-M7.5 程式修改及隔離合成資料的桌面與 390px／320px 操作驗證。M7 的前端自動化測試基礎設施及更大規模合成資料矩陣仍待補強；實作順序及驗收條件見 `TASKS.md` 的 M7。

- 搜尋與導覽：搜尋獨立為結果頁，文件／交易各自有總數與分頁，搜尋字詞及分頁保留在 URL，且具備獨立載入、空結果、錯誤與舊請求防護。
- 新增資料與入帳：統一入口區分手動收錄文件、CSV 建立交易及 Codex MCP 自動收件狀態；文件詳情集中顯示來源、有效狀態、關聯交易與匯入歷史。PDF 收錄仍明示尚未建立交易。
- 來源追溯：交易與 Jobs 只有在有 `source_document_id`／`document_id` 時提供文件連結；文件詳情可回看本機／遠端來源及所有關聯處理結果。
- 月份／幣別總覽：首頁預設本月，Dashboard 由資料庫依月份與幣別聚合；不同幣別不相加，連往交易頁會保留同一組條件，空月份顯示明確空狀態。
- 設定目前依「文件解鎖／連線服務／進階設定」分組，預設顯示個人解鎖資料；不再要求使用者建立銀行或家庭成員設定。舊 profile schema/API 保留相容。
- PDF 開啟後會先自動預覽；只有需要密碼或密碼規則錯誤時才展開解鎖設定。來源不可用、需要密碼、密碼不符及 OCR 未就緒都有獨立提示，且明示預覽不會建立交易。
- PDF 與撤銷／恢復對話框已補焦點移入、Tab 循環、Escape 關閉及回到觸發按鈕；若已設定 AI key，加密 PDF 預覽可分析遮罩後提示（預覽視窗可關閉）；不啟用 Gmail 同步、不保存遠端附件。
- M7.5 已完成：主要字級層級與多幣別摘要、手機交易兩行排列、單排導覽、長內容縮排／換行及共用 `EmptyState`／`TransactionTable` 元件已整理。
- 待處理：M7 前端行為測試基礎設施與更大規模長檔名／失敗狀態矩陣，銀行 PDF parser 也仍未完成。

下一步依 `IMPLEMENTATION_PLAN.md` 完成 S4：等待銀行名稱及兩期 PDF 樣本，保存在使用者授權的私有位置，或以欄位/版面相同的合成副本提供；一份用來開發，一份盲測。缺樣本期間不推測銀行格式、不建多銀行 framework，也不先建立依賴實際 parser 契約的 Statement schema。前端行為測試隨 S7 需要補強，不為完成舊清單而重排非核心功能，不全面重寫 `App.tsx`。

M7 `2b21333`、M8 `488cee7`、免費 API 文件與 Groq 程式 `eeb6883` 均已包含於目前 `main` 歷史；後續接手只以最新 Git HEAD 為準，不再使用 `4f9bfb5` 當最新遠端。

## M8 第一階段：Excel 自動投影已完成

M8 第一階段已完成專用 Excel 輸出、背景重試與設定介面；新目標以 Excel 為主要使用成果，但目前仍須 S6C 補正信用卡退款/繳款分類、自然月摘要及 Statement 狀態。SQLite 仍是唯一事實來源；啟用後會立即並每 30 秒檢查快照與輸出，只有需要更新時才重建應用程式擁有的工作簿，只輸出有效交易，另列待處理 PDF。撤銷/恢復反映在下一次輸出；Excel 佔用時保留舊版並重試；外部修改由 SHA-256 偵測，暫停下載後從 SQLite 重建。手寫內容會被重建覆蓋；下載為當次副本，持續更新的是設定的本機檔。預設路徑為 `data/exports/家庭收支記錄.xlsx`（由 storage_root 上層衍生），可由 `FAMILY_FINANCE_HUB_EXCEL_PATH` 覆寫。

密碼規則另修正候選值去重後規則索引錯位：預覽成功時會保存原始、真正命中的規則，不會因空白或重複候選值記錯規則。尚無經驗證的真實銀行 PDF parser，因此不能宣稱 PDF 已自動入帳。程式測試使用隔離合成 DB／PDF／Excel；本次另以使用者授權的 Gmail 網頁手動下載一份真實加密 PDF，完成文件去重、關閉 AI 解鎖及文字抽取驗證，沒有建立財務交易。

## 前一輪文件更新的驗證

前一輪只更新 7 份 MD 的 S0-S9 規格及產品/交接說明，不執行業務功能、不連線 Gmail/AI、不操作正式 DB/SecretStore。當時契約測試 collection 為 18 項（未執行測試）；7 份文件的 12 個本機連結、11 個既有測試路徑及 code fences 檢查通過，`git diff --check` 通過。更新前後的 14 份既有已修改/未追蹤程式檔 SHA-256 完全相同，沒有新增或遺失程式變更。未重跑 backend suite 或 frontend build，不沿用前輪結果冒稱本次通過。

## 前輪程式驗證

- 2026-09-28 S0 基線（S1-S3 修改前）：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests -q -p no:cacheprovider`，128 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings；`npm --prefix frontend run build` 成功。此結果是修改前基線，不代表本輪程式改動後完整 backend suite 已通過。
- 2026-09-28 S1-S4 契約聚焦測試：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_gmail_sync.py backend/tests/test_password_rules.py backend/tests/test_pdf_api.py backend/tests/test_pdf_processor.py backend/tests/test_pdf_processing.py backend/tests/test_statement_contracts.py -q -p no:cacheprovider`，74 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings；僅使用合成資料。覆蓋 Gmail 自訂 query 與 history 隔離、密碼提示上下文／遮罩、寄件者 profile 唯一匹配及加密 PDF 預覽整合、Statement 契約與月報語意。
- 前輪 S1-S4 修改後 `git diff --check` 通過；當時未重跑完整 backend suite 或 frontend build。接手須重驗 S0，並依新計畫在 S6/S7/S9 跑完整關卡。

## 本輪程式驗證

- 2026-09-29 S3F-C safe-switch：完整 backend `211 passed`、2 個既有相依套件棄用警告；frontend production build 成功；`git diff --check` 通過。
- 新增測試確認 provider test 不落盤、不切換；configure preflight 失敗保留舊 provider/key；status 可辨識 credential 遺失；錯誤回穩定 reason code 且不洩漏 upstream body/API key。
- 2026-09-29 免費 AI provider 實作回歸：`.\.venv\Scripts\python.exe -m pytest backend\tests -q -p no:cacheprovider --basetemp .pytest-tmp\free-ai-status`，187 passed、2 個既有 FastAPI/anyio 相依套件棄用警告。
- 2026-09-29 Frontend production build：`npm --prefix frontend run build` 成功；`git diff --check` 通過。
- 合成測試覆蓋 Groq/OpenAI dispatch、legacy profile、遮罩 payload、verified cache、失敗不 fallback、設定 API/UI 與 PDF preview contract；未把真實 Groq key 或真實帳單內容放進測試。
- 實際服務 smoke check 顯示已保存 provider 仍為 OpenAI；授權 Gmail 網頁下載的 PDF 已收錄，重複 bytes 回報 `duplicate=true`。AI 預覽因 OpenAI 額度不足停止後，改以郵件明示規則且關閉 AI 成功解鎖；原始檔為加密、輸出為未加密 2 頁 PDF，文字抽取可用，Finance transaction 維持 0。

## 2026-09-29 Gmail 真實信用卡帳單解密驗證

- 使用 Gmail 網頁以 `in:anywhere has:attachment filename:pdf (信用卡 OR 對帳單 OR statement)` 搜尋可存取信箱從最早可見信件到目前時間；只處理信用卡帳單，沒有把郵件內文的其他連結當成操作指示。
- 中國信託：實際下載附件到本機，原始 PDF 判定為加密；關閉 AI，依來源郵件明示的身分證規則完成本機解密與文字抽取。
- 台新：實際下載信用卡帳單附件；來源郵件明確寫出本國人密碼組合後，僅依該單一規則完成本機解密，輸出為 2 頁且可抽取文字，並確認內容具有台新信用卡帳單標記。
- 永豐、國泰世華：來源郵件分別明示身分證字號規則；在 Gmail PDF 預覽輸入該郵件允許的規則後均成功解密，未把預覽明文輸出另存成一般檔案。
- 本次只使用來源郵件明示的規則，不做排列猜測或暴力嘗試；密碼、身分證字號、生日、帳單內容與明文輸出未寫入 repository、文件、log 或測試資料。其後已以中國信託帳單建立第一個銀行 parser 並完成核對／確認入帳；台新、永豐、國泰世華仍不可因已解鎖就宣稱可解析交易。

## 目前產品方向的重新審查 Gate

2026-09-28 使用者重新確認：近期核心需求不是繼續擴張「家庭資料平台」，而是**每月信用卡帳單自動分析**。最新詳細需求、疑似 Overdesign 清單、建議簡化方向與交給高階模型的 12 個審查問題，集中在 `ARCHITECTURE_REVIEW_BRIEF.md`。

2026-09-30 已決定停用網站內建 Gmail OAuth/scheduler，改由 Codex MCP 管理收件；legacy incremental sync 暫留相容，不做破壞性 schema 移除。Documents 1:N、revocation、OCR 邊界與 Excel safety 仍保留；不要新增 Drive、其他家庭 domain、通用 AI、Push/PubSub 等非核心能力。

近期開發優先序應暫時指向：
1. 第一份真實信用卡帳單與 bank-specific parser。
2. 密碼規則上下文擷取的真實郵件可靠性。
3. sender/profile 自動匹配。
4. 驗證 Codex cron 真實收件及重跑冪等；Excel background projection 先沿用，legacy Gmail scheduler 不再啟用。


## 最近程式驗證

- M8 Backend：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m8-full`，120 passed、2 個既有 FastAPI TestClient／Starlette anyio deprecation warnings。覆蓋 Excel 完整重建、冪等、撤銷／恢復、檔案佔用、重新啟動、外部修改偵測、下載保護，以及 PDF 密碼規則原始索引回歸。
- M8 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5190/?view=settings` 搭配隔離合成 DB 驗證 Excel 啟用、立即更新、4 筆交易、1 份待處理 PDF 與下載入口。桌面及 390px／320px 均無水平溢出，console error 為空。
- M8 Migration：空白隔離 SQLite 已由 `0001` 完整升級至 `0011_statement_import`；使用中的 `data/family-finance-hub-live.db` 也已完成相同 migration，並通過 live Statement API smoke check。
- M7.1-M7.2 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-2`，69 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。
- M7.1-M7.2 Frontend：`npm run build` 成功；隔離合成資料瀏覽器驗證搜尋結果頁、URL／上一頁、分頁、新增資料入口、未授權 Gmail 下一步、文件詳情、來源連結與匯入歷史，沒有目前頁面的 console error。
- M7.3 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-3-final`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋 Dashboard 跨月、多幣別、空期間、幣別／月份格式錯誤、有效文件條件及撤銷／恢復回歸。
- M7.3 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5188/` 搭配隔離合成 DB/storage 驗證本月總覽、空月份、月份／幣別控制，以及「查看全部交易」保留 `month` URL 條件；新分頁沒有 console error。
- M7.4 Backend：`\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/m7-4-full`，70 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings；PDF focused suite 為 10 passed。新增 PDF 錯誤分類的 CORS header 暴露驗證。
- M7.4 Frontend：`npm run build` 成功；以 `http://127.0.0.1:5189/` 搭配隔離合成 DB/storage 驗證設定四組分頁、一般 PDF 自動預覽、OCR 未就緒提示、加密 PDF 需要解鎖提示、PDF／撤銷對話框 Escape 回到觸發按鈕及 Shift+Tab 焦點循環；目前頁面 console error 為空。
- M7.5 Frontend：`npm run build` 成功；以隔離合成資料驗證交易頁桌面回歸，並用 Chromium device metrics 實際量測 390px／320px：`body.scrollWidth` 與 viewport 相等、交易表格 `scrollWidth` 等於內容寬度、項目／金額／日期／來源均在列內，五個主導覽維持單排。交易表格已抽至 `frontend/src/TransactionTable.tsx`，空狀態抽至 `frontend/src/EmptyState.tsx`；目前未建立獨立 frontend test runner。

- Backend：`.\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider --basetemp backend/.test-tmp/revocation-final`，67 passed、2 個既有 Starlette/httpx/anyio 相依套件 deprecation warnings。覆蓋撤銷範圍、多幣別、恢復、冪等、過期預覽、失敗回滾、Gmail 已撤銷文件保護及備份／migration。
- OCR/PDF processor focused tests：10 passed；含加密 PDF 解密後才呼叫 provider、OCR 錯誤不阻斷預覽、Tesseract 語言資料預檢及 stdin 資料流測試。
- 使用目前 Codex Python runtime 的 PDFium 對合成 PDF 實際渲染一頁至記憶體，Tesseract 子程序以 stub 驗證 PNG stdin/output；不是實際辨識品質驗收。
- Frontend：`npm run build` 成功。
- 瀏覽器以隔離合成帳單驗證桌面及 390px／320px 手機版撤銷、恢復、取消、摘要更新與過期預覽 409 後重新確認；沒有頁面水平溢出。撤銷後僅剩另一份文件的交易，恢復後精確回到原有四筆與各幣別金額。正常流程無 console 錯誤。
- 上一輪驗證預覽為 `http://127.0.0.1:5177/`，API 為 8018；DB/storage 位於忽略的 `backend/.test-tmp/lifecycle-preview-20260926/`。僅含合成資料，與正式資料隔離；此處記錄驗證環境，不保證服務持續執行。
- 修正 PDF OCR 狀態標頭未透過 CORS 暴露的整合問題；跨來源 API 測試通過，瀏覽器以合成 PDF 驗證「OCR 尚未就緒」提示出現且仍可預覽。
- Alembic head 為 `0011_statement_import`；`0009_document_revocation` 的既有資料保留、`0010_workbook_export` 與 Statement migration 仍由測試覆蓋。OCR 無 schema migration。
- `backend/tests/test_backup_restore.py` 以有效／已撤銷兩種合成 DB + documents storage 演練備份／還原，恢復 PDF bytes、Finance transaction、撤銷狀態及工作紀錄；已撤銷交易需明確恢復才重新計入。
- Tesseract executable 與 `chi_tra`/`eng` runtime 尚未完成真實 OCR 驗收。較早的「Tailscale CLI/service 未找到」已被後續部署結果取代：Tailscale 私有 HTTPS → `localhost:3000` 已驗證可用；仍待重新開機自動觸發與實體 iPhone/MacBook 驗收。

## 正式使用與外部驗收

此主機已使用成對備份後升級至 `0011_statement_import` 的 `data/family-finance-hub-live.db`；舊 DB 仍保留且不可直接用新版程式啟動。其他主機若尚未升級，仍須先停止 API、成對備份 DB/storage、確認位址後依 `docs/operations.md` 操作。

1. OCR 為條件式待辦，不是下一步前置：僅當 S4 真實帳單證明文字抽取不足，才安裝/驗收 Tesseract 及 `chi_tra`/`eng` traineddata。缺語言資料的提早檢查已有合成測試，真實 runtime 尚未驗收；近期順序依 S0-S9，不先擴充 OCR。
2. 確認 Codex Gmail connector 可讀取授權信箱，建立 read-only 排程並以真實台灣信用卡帳單驗證附件收錄；不把帳單、郵件全文或秘密放入 repository／prompt。
3. 根據核對過的真實格式定義 bank-specific `BankStatementParser`/profile，補日期、幣別、金額、退款與冪等映射；通過人工核對前不自動寫交易。
4. 完成 Windows 開機啟動與背景常駐包裝，並確認 Codex cron 在主機與 FamilyHub 可用時可重複執行、離線後能靠近期窗口補抓；不要用一次手動執行宣稱已可長期自動化。
5. 安裝/登入 Tailscale 並確認家庭裝置與 Windows Firewall 規則後，再做遠端 Web 使用檢查。不要公開服務或設 router port forwarding。
6. 尚未驗證真實資料庫的生產備份/還原；目前只完成隔離合成 rehearsal。未提供自動或加密備份。
7. 搜尋分頁已列入 M7.1，不再等資料量增長才處理；工作歷史目前最多 100 筆，其分頁與匯入批次大小另依使用量評估。

## 安全界線

- 不讀取或回填先前對話裡曾提供的個人秘密；SQLite、log、repository 與 plaintext config 不可存 secrets。身分資料與 PDF password 只透過使用者明確操作的本機 SecretStore/Credential Manager；Gmail connector credential 由 Codex 管理，不傳給 FamilyHub。
- 程式測試與 restore rehearsal 使用合成資料及隔離 SQLite/storage；較早另以使用者授權的 Gmail 網頁手動下載真實帳單，完成本機文件去重、SecretStore 解鎖與文字抽取驗證。Codex MCP import 的合成測試不等同真實排程、交易解析或 Excel 入帳驗收。
- 正式升級前先確認 DB 與 storage 路徑，停止 API 並成對備份 DB 和 `data/documents`，再明確執行 migration；禁止刪除/重建舊 DB 或讓 app 靜默升級 schema。
- 不自動 commit、push 或覆蓋其他既有修改。
