# 免費 AI 密碼規則解析導入計畫

> 狀態：**第一階段程式已完成，合成測試已通過；真實 Groq key 尚未保存，真實帳單流程已完成收錄與去重，但尚未完成 Groq 解鎖及交易入帳驗收。**
>
> 更新日期：2026-09-29。免費額度、模型與 API 相容性會變動；真正實作或切換模型前，必須重新確認 provider 官方文件，不可把本文數字當永久保證。

## 1. 目的

信用卡帳單 PDF 的密碼規則有時只寫在 Gmail 郵件中，例如「身分證後四碼 + 生日 YYYYMMDD」。AI 的責任只是在**遮罩後的郵件提示**中理解組合規則，輸出受限的 `PasswordRule`；真實身分證、生日與最後 PDF 密碼只在 Windows 本機透過 `SecretStore` / `PasswordComposer` 使用。

此工作量極小，每月通常只有少量帳單，因此優先採用免費 API，避免為密碼提示解析固定支付 LLM API 費用。

## 2. Provider 決策

### 第一選擇：Groq Free Plan

預設 provider：

- provider: `groq`
- model: `openai/gpt-oss-20b`
- base URL: `https://api.groq.com/openai/v1`
- Responses endpoint: `https://api.groq.com/openai/v1/responses`

選擇理由：

1. Groq 提供 OpenAI-compatible API，現有 OpenAI Responses payload 可大幅重用。
2. `openai/gpt-oss-20b` 目前支援 Structured Outputs 的 `strict: true` JSON Schema，適合現有 `PasswordRule.model_json_schema()`。
3. 目前 Free Plan 對此模型的官方限制足以應付家庭帳單用途。

2026-09-29 查到的官方 Free Plan 上限：

- 30 RPM
- 1,000 RPD
- 8,000 TPM
- 200,000 TPD

這些數字只作為目前決策依據。若官方調整模型、免費方案或限制，後續模型必須重新查證。

官方參考：

- Groq rate limits: https://console.groq.com/docs/rate-limits
- Groq OpenAI compatibility: https://console.groq.com/docs/openai
- Groq Responses API: https://console.groq.com/docs/responses-api
- Groq Structured Outputs: https://console.groq.com/docs/structured-outputs

### 第二選擇：Cloudflare Workers AI

只有 Groq 免費方案取消、長期不穩定或不再提供合適 Structured Outputs 模型時，再實作 Cloudflare adapter。

2026-09-29 官方資料顯示 Workers Free 目前每日有 10,000 Neurons 免費 allocation；超過 Free allocation 後，在 Free plan 上應失敗而不是默默轉為付費。部分高成本模型要求 Paid plan，因此實作時必須選仍可在 Free plan 使用的模型。

Cloudflare REST API 還需要 Account ID，設定面比 Groq 多，因此**不作第一階段 provider**。

官方參考：

- Pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- REST API setup: https://developers.cloudflare.com/workers-ai/get-started/rest-api/
- Data usage: https://developers.cloudflare.com/workers-ai/platform/data-usage/

### OpenAI

保留既有 OpenAI adapter 作相容/手動選項，但**不要把 OpenAI API 視為保證免費方案，也禁止 Groq 失敗後自動切到可能付費的 OpenAI API**。

## 3. 不可破壞的安全邊界

無論 provider 為何，都必須維持：

- API 不接收真實身分證字號。
- API 不接收真實生日。
- API 不接收已組合的 PDF 密碼。
- API 不接收完整信用卡帳單內容。
- 只傳 `PasswordInstructionExtractor` 遮罩後的密碼提示與必要非敏感 context。
- API key 只保存到 Windows Credential Manager / `SecretStore`；不寫 SQLite plaintext、repo、log 或前端持久化儲存。
- LLM 只能輸出受限 `PasswordRule` DSL，不得輸出或執行 Python/JavaScript。
- candidate 密碼最多 3 個，不因免費 API 而增加 brute-force 行為。
- provider 失敗不能降低安全限制，也不能把原始個資改送另一 provider。

## 4. 目前程式狀態

目前 repo 已有可重用基礎：

- `security/password_rules/ports.py` 的 `PasswordRuleInterpreter` 已是 provider-neutral Protocol。
- `AIProviderProfile` 已有 `provider`、`model`、`api_key_credential_ref` 欄位。
- `PasswordRuleService` 已保存 verified rule，可避免相同提示每次重新呼叫 API。
- `PasswordComposer` 與 `SecretStore` 已把真實秘密留在本機。

第一階段已完成的 provider-neutral 修改：

- `security/password_rules/provider_service.py` 接受 `groq` / `openai` 白名單，沿用 legacy profile id `openai`，並依 `AIProviderProfile.provider` dispatch；未知 provider fail closed。
- `security/password_rules/groq_responses.py` 使用 `https://api.groq.com/openai/v1/responses`、`openai/gpt-oss-20b` 可用的 JSON Schema，且不送 Groq 不支援的 `store` 欄位。
- `security/password_rules/openai_responses.py` 保留既有 OpenAI adapter，僅抽出 provider 名稱與 `store` 開關供 Groq 相容 adapter 使用。
- `main.py` 與 `frontend/src/api.ts` 支援 provider；設定頁預設 Groq 與 `openai/gpt-oss-20b`，仍可明確選擇 OpenAI。

因此第一階段沒有重寫 PasswordRule DSL、沒有新增 migration，也沒有建立通用 AI framework。尚未完成的驗收是使用者在本機保存 Groq key、以合成提示呼叫真實 Groq，以及在授權的真實 PDF 上確認解鎖；這些不在測試中假裝完成。

### 4.1 2026-09-29 實際執行狀態

- 程式與設定頁已支援 Groq，但目前線上服務的已保存 profile 仍回報 `runtime_provider=openai`、`runtime_model=gpt-4.1-mini`；`groq_adapter_in_worktree=true` 不代表 Groq key 已設定。設定頁的 Groq 預設值不會自動覆寫既有的 SecretStore profile，必須由使用者在「設定 → 進階設定」明確保存 Groq key。
- 已從使用者授權的 Gmail 網頁下載一份信用卡 PDF，透過 FamilyHub 文件入口收錄；同一份 bytes 再次收錄回報 `duplicate=true`，證明 SHA-256 冪等路徑正常。FamilyHub 內建 Gmail OAuth 仍未授權，因此這次是 Gmail 網頁手動下載，不是內建 Gmail scheduler 的真實驗收。
- 開啟該 PDF 的 AI 預覽時，實際呼叫的是既有 OpenAI profile，服務回報額度不足；系統沒有自動改呼叫 Groq，也沒有建立任何 Finance transaction。這次結果是「文件已收錄、尚未解鎖/入帳」，不是帳單解析成功。
- 後續應先在本機保存 Groq key，以合成提示確認真實 Groq request，再重新跑授權 PDF；不得把 key、身分資料、生日、PDF 密碼或帳單全文貼到聊天或提交到 repository。

## 5. 實作順序

### Phase A：讓 AI provider 真正 provider-neutral

1. 保留 `PasswordRuleInterpreter` Protocol，不改 domain contract。
2. 修改 `AIProviderInput`：
   - 新增 `provider`
   - 第一版只允許 `groq` / `openai`
   - API key 與 model 維持必填
3. 修改 `AIProviderService.configure(...)`：
   - 接受 provider
   - provider 做白名單驗證
   - API key 仍只存 `SecretStore`
   - `AIProviderProfile.provider` 成為 provider 真正來源
4. 修改 `AIProviderService.interpreter()`：
   - `groq` → `GroqResponsesInterpreter`
   - `openai` → 既有 `OpenAIResponsesInterpreter`
   - 未知 provider → `PasswordRuleInterpreterUnavailable`
5. 保留舊 `openai` profile 相容性。
   - 不為了 row id 名稱不好看就做 migration。
   - 現有 primary key 可視為 legacy storage key；真正判斷 provider 看 `provider` 欄位。
   - 除非實作時發現無法安全維持單一設定，否則**不要新增 migration**。

### Phase B：新增 Groq adapter

建議新增：

`backend/src/family_finance_hub/security/password_rules/groq_responses.py`

第一版可直接沿用現有 OpenAI Responses 結構：

- Authorization Bearer API key
- `Content-Type: application/json`
- model 預設 `openai/gpt-oss-20b`
- `store` 若 Groq endpoint 不接受則依官方 Responses API 規格移除，不可猜測
- system instruction 沿用「只轉換規則、不猜缺失資訊、不輸出密碼」
- user input 只包含 masked instruction + safe context
- `text.format.type = json_schema`
- schema 使用 `PasswordRule.model_json_schema()`
- 優先 `strict: true`；若官方當時模型不再支援 strict，不能默默改成 unrestricted text，需明確使用受支援模式並保留本機 Pydantic validation

為避免 provider 差異被藏太深，第一版可以用獨立 `GroqResponsesInterpreter`，不用急著建立大型 generic SDK abstraction。若兩個 adapter 實際重複非常高，再抽小型 shared helper。

### Phase C：前端設定改成免費方案優先

設定 UI 改成：

- Provider 下拉：
  - `Groq（免費優先）`
  - `OpenAI（自費/既有相容）`
- 選 Groq 時預設 model：`openai/gpt-oss-20b`
- API key label 改成通用「AI API key」
- 不在 UI 宣稱「永久免费」；顯示「目前使用 Groq Free Plan，額度與模型可能由供應商調整」
- 切換 provider 時可帶入合理預設 model，但使用者仍可修改
- 保存后由 GET API 回传实际 provider/model，不由前端硬写 `openai`

### Phase D：调用顺序

目标流程：

```text
Gmail password hint
      ↓
PasswordInstructionExtractor
(mask PII + context window)
      ↓
fingerprint
      ↓
verified PasswordRule cache?
      ├─ yes → directly reuse, 0 API call
      └─ no
          ↓
optional deterministic local rule
          ├─ resolved → use locally
          └─ unresolved
               ↓
configured remote provider
(default Groq Free)
               ↓
validated PasswordRule
               ↓
PasswordComposer + SecretStore (local only)
               ↓
try PDF decrypt
               ↓
success → save verified rule
failure → pending/manual review
```

说明：

- **verified cache 必须在 remote API 前。**
- Local deterministic rule 是省 API 的额外优化，可在 Groq 接入后再做；不要为了它延误真实帐单 parser。
- Groq 失败不得自动 fallback 到付费 OpenAI。
- 若用户明确选择 OpenAI，才调用 OpenAI。
- 若 API 不可用，PDF 留在 pending/manual，不影响文件收录。

## 6. Groq 帐号与导入步骤

给实际部署者：

1. 建立/登入 Groq 帐号。
2. 在 Groq Console 建立 API key。
3. 不把 key 写进 `.env`、PowerShell script、GitHub Secret 或 repo 文件。
4. 开启 Family Dashboard → 设置 → AI 密码规则辨识。
5. Provider 选 `Groq（免费优先）`。
6. 贴入 Groq API key。
7. Model 使用 `openai/gpt-oss-20b`，除非官方已调整支持模型。
8. 点击保存。
9. Backend 将 API key 写入现有 Windows `SecretStore` / Credential Manager，并只在 SQLite 保存 credential reference。
10. 使用**合成密码提示**测试，不先使用真实身分资料。
11. 测试成功后再用授权的真实 Gmail 提示/PDF 做本机验收；日志与测试报告不得包含提示全文、个人秘密或实际 PDF 密码。

如果 Groq Console 或模型/免费限制与本文不同，应停止并重新查官方文件，而不是强行照旧参数。

## 7. 错误与费用保护

至少区分：

- 401 / 403：API key 或 provider 权限问题 → 显示设定错误，留 pending。
- 429：免费额度/rate limit → 留 pending，可手动稍后重试；**不可自动转付费 provider**。
- timeout / network / 5xx：provider 暂时不可用 → 留 pending/manual。
- schema validation failure：当作 provider 输出不可用；不能放宽到任意 text 后直接执行。
- unsupported model：要求重新确认官方 model list，不自动挑一个未知收费模型。

第一版不做无限 retry/backoff。家庭帐单不需要即时性；避免 retry loop 造成意外调用量。若未来真的需要自动重试，最多使用有上限、可观察的 retry。

## 8. 测试要求

后续模型实现时至少补：

### Backend

- `AIProviderService` 可正确 dispatch Groq / OpenAI。
- legacy OpenAI profile 仍能读取。
- Groq request endpoint/model/schema 正确。
- request body 只含 masked instruction + safe context。
- synthetic national ID / birthday / composed password 不得出现在 outbound request。
- Groq valid strict JSON → `PasswordRule`。
- 401/403/429/timeout/5xx → `PasswordRuleInterpreterUnavailable` 或等价安全错误。
- invalid schema 不可进入 `PasswordComposer`。
- verified rule cache 命中时不会呼叫 provider。
- Groq 失败不会自动呼叫 OpenAI。
- API response 不回传 API key。

### Frontend

- 可选 Groq / OpenAI。
- 默认 Groq + `openai/gpt-oss-20b`。
- 切 provider 时 model 默认值合理。
- 保存后显示 backend 回传的 provider/model。
- 不在 UI 保存或重新显示 API key 原值。

## 9. 驗收標準

免费方案接入完成至少要证明：

1. 使用 synthetic Gmail 密码提示可透过 Groq 得到合法 `PasswordRule`。
2. outbound payload 不含 synthetic 身分证、生日或最终密码。
3. `PasswordComposer` 只在本机取得 synthetic secrets 并产生 candidate。
4. synthetic encrypted PDF 可成功解锁。
5. 相同提示第二次处理命中 verified cache，不再次调用 Groq。
6. Groq 回 429 时文件留 pending/manual，系统不自动调用 OpenAI。
7. 移除/停用 Groq key 后核心文件与 Finance 功能仍可使用。
8. backend tests 与 frontend production build 通过。

### 9.1 本次驗收結果

- [x] `backend/tests` 完整測試：187 passed；2 個既有 FastAPI/anyio 相依套件棄用警告，不是失敗。
- [x] `npm --prefix frontend run build` production build 成功。
- [x] Groq/OpenAI dispatch、遮罩 payload、verified cache、失敗不 fallback 與設定 API/UI 有合成測試覆蓋。
- [ ] 真實 Groq key、真實 Groq 回應與加密 PDF 解鎖尚未驗收。
- [ ] 真實銀行 PDF 的逐筆 parser、核對與 PDF → Excel 入帳尚未完成；本次實際 PDF 維持 0 筆交易。

## 10. 实作优先级

这项工作属于 **S3 与真实 S4 之间的小型基础改善**：

- 可以先完成，因为真实信用卡 PDF 解锁可能会依赖 AI 密码提示。
- 不应扩张成通用 multi-provider AI platform。
- 第一阶段只做 Groq；Cloudflare 只是备用设计，不同时实现。
- 不延误第一家真实 `BankStatementParser`。
- 不改变 S4-S9 主线顺序。

後續修改或驗收請先讀本文件，再檢查 provider 官方文件是否仍與 2026-09-29 的事實一致。
