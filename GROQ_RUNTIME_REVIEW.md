# Groq Runtime 深度審查與切換方案

> 更新日期：2026-09-29
>
> Groq 實作 commit：`eeb6883`。本次程式級審查最初以 `b40163d` 為基準，之後的文件 commit 只更新規格與交接，不代表 Groq provider 被重新實作。開始工作前仍須讀取最新 `main`。

## 1. 結論

Groq provider **已實作並合併**。現在真正的問題不是「還沒有 Groq」，而是四件事：

1. runtime 是否真的已切到 Groq；
2. 切換前是否能安全驗證新 provider/model；
3. 設定頁是否能清楚顯示真正 Active Provider，而不是讓 UI 預設造成誤解；
4. 真實 Groq request、verified cache 與真實加密 PDF 是否完成端到端驗收。

最後一次有證據的 runtime smoke check 仍使用 OpenAI / `gpt-4.1-mini`。因此不能因 UI 預設 Groq 或 Git 已包含 Groq adapter，就宣稱真實 PDF 已經走 Groq。

## 2. Recommended / Default / Active 必須分開

- **Recommended Provider**：目前建議 Groq Free。
- **Default for new setup**：前端新設定表單預填 Groq + `openai/gpt-oss-20b`。
- **Active Provider**：backend 已保存的 `AIProviderProfile.provider/model` 加上 Windows SecretStore 中實際可取得的 credential。
- **Runtime Provider**：真正建立 interpreter 並發出 request 的 provider；正常情況應與 Active Provider 相同。

既有 OpenAI profile 不應因軟體升級自動切換到 Groq。這是正確安全行為：系統不能無提示建立外部服務 credential，也不能偷偷改變可能產生費用的 API 路徑。

Backend `AIProviderInput.provider="openai"` 的 default 只作舊 client 相容，不是產品建議預設。新版前端已明確傳 provider。

## 3. 已完成的程式

### Backend

- `security/password_rules/ports.py` 已有 provider-neutral `PasswordRuleInterpreter`。
- `provider_service.py` 支援 `groq` / `openai` 白名單。
- `groq_responses.py` 重用既有 Responses adapter，只覆寫 endpoint/provider name/`store` 行為。
- Groq endpoint 為 `https://api.groq.com/openai/v1/responses`。
- Groq request 不送官方目前不支援的 `store` 欄位。
- `PdfPreviewUseCase` 先查 verified PasswordRule cache；只有 cache miss 且使用者允許 AI 時才建立 remote interpreter。
- 成功解鎖後才保存 verified rule；ambiguous candidate 會收斂為真正命中的 resolved rule。

### Frontend

- 可選 Groq / OpenAI。
- 新設定預設 Groq + `openai/gpt-oss-20b`。
- 載入既有設定後，provider/model 會由 backend 狀態覆蓋表單預設。
- credential 欄位不會由 server 回填。

### 已有驗證

- 完整 backend 測試紀錄：187 passed。
- frontend production build 成功。
- 合成測試覆蓋 Groq/OpenAI dispatch、Groq endpoint/schema、legacy profile、設定 API、不自動 fallback 等。
- 這些都**不是**真實 Groq credential/request 或真實銀行 PDF 驗收。

## 4. 深度審查發現的剩餘問題

### 4.1 P0：切換前沒有 preflight

目前 `AIProviderService.configure()` 的流程是：

```text
建立新 credential reference
    ↓
SecretStore.set(new)
    ↓
DB profile 改成新 provider/model/reference
    ↓
DB transaction 成功
    ↓
刪除舊 credential
```

它**不會先向新 provider 驗證 credential/model/schema**。

因此如果新設定輸入錯誤、模型下架、權限不足或 Structured Output 不相容，Active Provider 可能已切換，而且舊 credential 已被移除後才在第一次真正 request 發現問題。

### 4.2 P0：設定狀態可能「DB 有 row，但 credential 不存在」

目前 `GET /api/security/ai-provider` 的 `configured` 只判斷 DB profile 是否存在：

```text
configured = profile is not None
```

但真正建立 interpreter 時，`AIProviderService.interpreter()` 還會去 SecretStore 取得 credential。

所以存在這個邊界案例：

```text
DB profile 存在
SecretStore credential 遺失 / 不可用
      ↓
GET status 顯示 configured=true
      ↓
真正 PDF 解鎖才失敗
```

後續應讓 status 能反映「profile 存在」與「credential 可用」的差別，但不能回傳 credential 本身。

### 4.3 P1：UI 沒有把 Active Provider 顯示得夠清楚

設定頁目前狀態徽章主要顯示：

```text
已設定 · <model>
```

雖然 provider selector 會載入 backend 值，但對使用者仍不夠直觀。建議直接顯示：

```text
目前使用：Groq · openai/gpt-oss-20b
```

或：

```text
目前使用：OpenAI · gpt-4.1-mini
推薦：Groq Free
```

按鈕也應從模糊的「保存 AI 設定」收斂成兩個行為：

- **測試連線**
- **保存並切換**

### 4.4 P1：provider 錯誤目前主要是文字，不是穩定 reason code

目前 adapter 已安全處理 400/401/403/429/network/schema failure，且不暴露 upstream body；但 application/UI 仍主要依賴文字。

建議增加穩定 reason code：

- `ai_auth_failed`
- `ai_rate_limited`
- `ai_quota_unavailable`
- `ai_model_unavailable`
- `ai_schema_invalid`
- `ai_timeout`
- `ai_service_unavailable`

UI 可以依 Active Provider 顯示下一步，但任何錯誤都不能自動切到另一 provider。

## 5. 建議實作：S3F-C Safe Switch

### 5.1 最小 Test Connection API

新增等價於：

```text
POST /api/security/ai-provider/test

input:
  provider
  credential
  model

server:
  ↓
固定 synthetic password instruction
  ↓
既有 PasswordRule JSON Schema
  ↓
呼叫指定 provider
  ↓
Pydantic 再驗證
```

限制：

- 不讀 Gmail。
- 不讀身分證/生日。
- 不讀真實 PDF。
- 不保存新 credential。
- 不修改 Active Provider。
- 不建立多 provider fallback。
- 一次按鈕只做一次有界限的 request，不建立 retry loop。

### 5.2 保存與切換

只有 Test Connection 成功後才執行既有 `configure()`。

更穩健的最終流程：

```text
新 provider 設定
      ↓
synthetic preflight
      ├─ fail → 保留舊 Active Provider，結束
      └─ pass
           ↓
     寫入新 credential
           ↓
     更新 DB Active Provider
           ↓
     重新讀取 status 驗證
           ↓
     再清理舊 credential
```

如果最後清理舊 credential 失敗，應記錄不含秘密的維護警告；不能因此把已成功的新 Active Provider rollback 成未知狀態。

### 5.3 Status API

建議 status 至少能安全區分：

```json
{
  "configured": true,
  "provider": "groq",
  "model": "openai/gpt-oss-20b",
  "credential_available": true
}
```

`credential_available` 只能表示可取得與否，絕不回傳 credential。

若 Windows SecretStore 本身不可用，可回既有 503 類型錯誤，不要假裝 configured/healthy。

## 6. S3F-B Runtime Activation 驗收

S3F-C 完成後再做 S3F-B：

1. 在本機選 Groq + `openai/gpt-oss-20b`。
2. 執行 Test Connection。
3. Test Connection 成功才「保存並切換」。
4. 重新讀取 `/api/security/ai-provider`，確認 Active Provider/Model 與 credential availability。
5. 用 synthetic 密碼提示做一次**真實 Groq request**。
6. 確認回傳可被現有 `PasswordRule` Pydantic schema 驗證。
7. 以 synthetic local secrets 完成一份 synthetic encrypted PDF 解鎖。
8. 對相同提示第二次執行，確認 verified rule cache 命中，remote Groq request 數為 0。
9. Groq 429/401/403/timeout/schema failure 都只能 fail closed；不得呼叫 OpenAI。
10. 完成後才使用授權真實 PDF 做解鎖驗收。

## 7. 官方能力確認（2026-09-29）

依 Groq 官方文件重新確認：

- `openai/gpt-oss-20b` Free Plan：30 RPM、1,000 RPD、8,000 TPM、200,000 TPD。
- rate limit 超過時回 HTTP 429，官方文件列出 `retry-after` 等 rate-limit headers。
- OpenAI-compatible base URL：`https://api.groq.com/openai/v1`。
- Responses API 可使用 `openai/gpt-oss-20b`。
- Groq Responses API 目前不支援 request 欄位 `store`；現有 Groq adapter 不送它，方向正確。
- `openai/gpt-oss-20b` 支援 Structured Outputs strict mode。
- strict mode 要求所有 object `additionalProperties: false`、所有 properties 都列為 required；optional 語意用 nullable union 表達。
- 現有 `PasswordRule` Pydantic models 使用 `extra="forbid"`，nullable transform 欄位沒有 default，與 strict-mode schema 限制方向一致；最終仍以真實 Groq smoke test 為準。

官方參考：

- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/openai
- https://console.groq.com/docs/responses-api
- https://console.groq.com/docs/structured-outputs

免費額度、模型與 API beta 狀態可能改變；每次真正切換/重新驗收前重新查官方文件。

## 8. 不要做的事

- 不重寫已完成的 Groq adapter。
- 不新增 Cloudflare adapter，除非 Groq 免費方案真的不再適用。
- 不建立 provider priority、provider pool、自動 fallback chain。
- 不把真實身分資料、生日、PDF password 或帳單全文送 remote AI。
- 不為了 Groq 改 PasswordRule DSL。
- 不讓 Groq 工作延誤真正產品主線 beyond 必要的安全解鎖前置。

## 9. 下一步順序

```text
S3F-A Groq implementation        ✅
        ↓
S3F-C Safe switch / Test         ⬜
        ↓
S3F-B Runtime activation         ⬜
        ↓
Real encrypted PDF unlock        ⬜
        ↓
S4 BankStatementParser           ⬜
        ↓
S5 / S6 PDF → SQLite → Excel     ⬜
```

**产品主 blocker 仍是 S4 BankStatementParser。** S3F-C/B 只负责把「自动解锁」这条前置链路安全地完成，不应扩张成新的 AI 平台。
