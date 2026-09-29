# Groq Runtime 深度審查與切換方案

> 更新日期：2026-09-29
>
> 本文件記錄 Groq provider 程式合併後的實際架構審查結果。Groq 實作 commit 為 `eeb6883`；本次程式審查基準為 `b40163d`。後續純文件 commit 可能使 `main` SHA 前移，不代表 Groq 程式重新實作。

## 結論

Groq provider **已實作並合併**，現在的問題不是「還沒有 Groq」，而是「runtime 是否真的已切到 Groq」。最後一次可驗證 smoke check 仍使用既有 OpenAI / `gpt-4.1-mini` profile，因此不能因 UI 預設 Groq 或 Git 已含 Groq adapter 就宣稱真實 PDF 已經走 Groq。

## 三種 Provider 狀態

- **Recommended**：Groq Free。
- **Default for new setup**：Groq + `openai/gpt-oss-20b`。
- **Active Provider**：backend 已保存的 `AIProviderProfile.provider/model` 與 Windows SecretStore 中的 credential。只有 Active Provider 決定 runtime 真正呼叫誰。

既有 OpenAI profile 不應自動切換到 Groq。這是正確行為，因為程式不能無提示替使用者建立外部服務 credential，也不能偷偷改變可能產生費用的 API 路徑。

## 已完成

- `AIProviderService` 支援 `groq` / `openai`。
- `GroqResponsesInterpreter` 使用 Groq OpenAI-compatible Responses endpoint。
- 前端可選 Groq / OpenAI，新設定預設 `openai/gpt-oss-20b`。
- verified PasswordRule cache 先於 remote provider 呼叫。
- Groq 失敗不會自動 fallback 到 OpenAI。
- 完整 backend 測試紀錄為 187 passed，frontend production build 成功。

## 尚未完成

### 1. Runtime activation

需要在本機明確啟用 Groq，然後重新讀取 `/api/security/ai-provider` 確認 Active Provider/Model。接著先用 synthetic 密碼提示呼叫真實 Groq，再用相同提示第二次執行，確認 verified cache 命中且不再產生 remote request。

### 2. Safe switch hardening

目前 `AIProviderService.configure()` 不會先驗證新 provider/model 就替換 Active Provider。若新設定輸入錯誤、模型下架或 Structured Output 不相容，可能在真正呼叫時才發現。

建議新增最小 preflight：

```text
POST /api/security/ai-provider/test
  provider
  credential
  model
      ↓
固定 synthetic password instruction
      ↓
PasswordRule JSON Schema
      ↓
成功 → 才保存並切換 Active Provider
失敗 → 舊 Active Provider 完全不變
```

Preflight 不讀 Gmail、不讀身分資料、不保存 credential，也不是多 provider fallback。

### 3. Provider 錯誤 reason codes

建議將目前安全錯誤訊息再收斂成穩定 code：

- `ai_auth_failed`
- `ai_rate_limited`
- `ai_quota_unavailable`
- `ai_model_unavailable`
- `ai_schema_invalid`
- `ai_timeout`
- `ai_service_unavailable`

UI 根據 Active Provider 顯示下一步，但任何錯誤都不應自動切換到其他 provider。

## 官方能力確認（2026-09-29）

- Groq Free Plan 對 `openai/gpt-oss-20b`：30 RPM、1,000 RPD、8,000 TPM、200,000 TPD。
- Rate limit 使用 HTTP 429，並可提供 `retry-after`。
- Groq Responses API 使用 `https://api.groq.com/openai/v1`，目前官方文件仍標示 beta。
- `openai/gpt-oss-20b` 支援 Structured Outputs strict mode。
- strict mode 要求 object `additionalProperties: false`，所有欄位列入 required；nullable 欄位以 union 表達。

真正切換前仍要重新查 Groq 官方文件；免費額度、模型和 beta 狀態不是永久契約。

## 下一步順序

1. 完成 provider preflight / Test Connection。
2. 本機明確切到 Groq。
3. 讀 API 確認 Active Provider/Model。
4. synthetic real-Groq smoke test。
5. 相同提示重跑，確認 cache 0 remote call。
6. 再測授權的真實加密 PDF。
7. 回到 S4：第一家銀行兩期真實樣本 parser。

Groq activation 是自動解鎖的前置驗收；真正的產品主 blocker 仍是 bank-specific PDF → Finance → Excel。
