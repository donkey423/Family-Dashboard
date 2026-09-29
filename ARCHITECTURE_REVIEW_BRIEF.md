# 架構重新審查 Brief：信用卡帳單優先

> 狀態：**原始 scope-reset / Overdesign 分析已保留作背景；2026-09-29 已再次依最新程式收斂執行方向，仍不授權大規模重構。實際工作以 `IMPLEMENTATION_PLAN.md`、`TASKS.md` 與最新 repo 為準。**
>
> 原始分析基準：`488cee7`。目前 GitHub `main` 已包含 Groq provider 實作 `eeb6883`；本文中早期假說若與最新程式衝突，以最新程式與執行文件為準。

## 1. 使用者目前真正需求（最高優先級）

這個專案目前最重要的產品目標不是建立通用家庭資料平台，而是：

> **每個月自動取得信用卡帳單，解鎖 PDF，正確解析當月消費，讓使用者快速知道這個月花了什麼、花多少；需要時再輸出 Excel。**

理想主流程：

```text
Gmail 找到信用卡帳單
        ↓
取得 PDF attachment
        ↓
判斷是否需要密碼
        ↓
從郵件說明理解密碼組合規則
        ↓
本機使用 SecretStore 中的身分證/生日產生密碼
        ↓
解密 PDF
        ↓
extract text（必要時才 OCR）
        ↓
BankStatementParser
        ↓
日期 / 商店 / 金額 / 幣別 / 退款等
        ↓
SQLite
        ↓
本月消費 Dashboard
        ↓
可選：更新 Excel
```

核心成功標準不是「平台功能很多」，而是上述鏈路對真實信用卡帳單可靠、可重跑、不重複入帳。

## 2. 目前不是優先目標

除非未來出現真實需求，以下方向先凍結，不因「可能以後會用」而繼續擴充：

- Google Drive / Dropbox / 其他 DocumentSource provider。
- Insurance、Assets、Warranty、Travel、Vehicle、Property 等家庭資料 domain。
- 通用 AI agent / 通用 AIProvider 能力。
- Gmail Push / Pub/Sub 近即時同步。
- 更完整的文件管理平台能力。
- 更複雜的 OCR pipeline 優化（除非真實帳單證明 text extraction 不足）。
- 為大規模、多使用者或 SaaS 場景預先設計的基礎設施。

仍維持 local-first、Windows、SQLite、Modular Monolith，不引入 microservices。

## 3. 目前架構現況

截至基準 commit，已存在：

- Documents + 1:N `DocumentSourceRecord`
- Local/Gmail sources
- SHA-256 去重
- Gmail OAuth / manual sync / incremental history sync / scheduler
- SecretStore / Windows Credential Manager
- PasswordInstructionExtractor
- versioned PasswordRule DSL
- AI rule interpreter
- PasswordComposer
- PDF decrypt / text extraction
- optional PDFium + Tesseract OCR
- Finance CSV / Dashboard / Search
- 文件撤銷 / 恢復 lifecycle
- Jobs / import history
- Excel snapshot projection / ownership marker / output hash / background retry worker
- React UI
- Alembic migrations through `0010_workbook_export`
- 大量合成測試

**目前最關鍵、但仍未完成的核心能力：真實台灣信用卡 PDF → Finance transaction 的 bank-specific parser。**

## 4. Overdesign 假說（請高階模型重新判斷）

以下不是已決定刪除，而是要求重新審查「對每月少量信用卡帳單是否值得」。

### 4.1 Gmail incremental/full-sync state

目前包含 history ID、history expiration fallback、full sync continuation/page token、每批上限與 scheduler。

可能的更小方案：

```text
啟動時 + 每天一次 + 手動同步
→ 搜尋最近 60~90 天
→ 限定已知銀行 sender / subject / PDF
→ message+attachment ID + SHA-256 去重
```

請評估：對單一家庭、每月少量帳單，簡單重掃窗口是否比 Gmail History API 狀態機更可靠、更易維護。

### 4.2 Gmail 30 分鐘 scheduler

信用卡帳單通常不是即時事件。請評估是否改成：

- Windows/App 啟動時一次
- 每天一次
- 手動「立即同步」

若每日同步足夠，就沒有必要持續 30 分鐘輪詢。

### 4.3 Excel 30 秒 projection worker + 前端 5 秒 polling

目前 M8 為 Excel 做了 snapshot hash、output SHA-256、ownership validation、atomic replace、背景每 30 秒 refresh、UI 週期 polling。

建議候選簡化：

```text
Finance transaction commit / revoke / restore
             ↓
      request Excel rebuild
             ↓
        atomic replace
```

並保留手動「重新產生 Excel」。

建議保留 ownership marker + atomic replace，以避免覆蓋未知 Excel；請重新判斷 snapshot hash、output hash、30 秒 worker、5 秒 UI polling 是否真的需要。

### 4.4 Documents / 1:N source records

若從零開始，信用卡帳單可用更小的 `Statement` model；但現在 Documents/1:N sources 已實作、migration 與測試都存在。

**建議不是立即拆掉，而是停止泛化。**

高階模型需評估：
- 保留現有 Documents 當已完成基礎設施，未來不再擴張；或
- 有足夠收益才逐步收斂成 statement-centric model。

禁止只為「架構更漂亮」而全面重寫。

### 4.5 Document revocation / lifecycle

對單人家庭工具可能只需要 active / ignored；目前已存在 revoked_at、reason、lifecycle version、impact preview、restore。

建議：功能已完成則保留，但停止繼續擴大 lifecycle subsystem，除非真實使用證明需要。

### 4.6 OCR

目前 OCR subsystem 已完整到 PDFium、Tesseract、語言預檢、頁數/像素/timeout 限制。

建議：**凍結功能開發。**

第一份真實帳單先跑 `pypdf.extract_text()`。只有真實銀行 PDF 沒有可用 text layer 時，才把 OCR 納入主流程驗收。

## 5. 明確建議保留的設計

即使進行簡化，以下價值高，不應為了減少檔案數而破壞：

- SQLite 作為唯一結構化 source of truth。
- SHA-256 / source identity 去重與 idempotency。
- Gmail readonly OAuth。
- Windows Credential Manager / SecretStore。
- 「AI 只理解密碼規則，真實身分證/生日只在本機使用」安全邊界。
- PasswordRule 使用受限 DSL，不 eval LLM 程式碼。
- PDF 密碼 candidate 數量有硬限制，不 brute force。
- 原始 PDF 與 decrypted preview 分離。
- unknown bank/PDF format 不可猜測入帳。
- Excel 若保留自動覆寫，至少保留 ownership marker + safe/atomic replacement。
- Modular Monolith；不改 microservices。

## 6. 優先要改善的實際問題

### P0：先完成第一個真實 BankStatementParser

停止增加平台功能，先取得一份可本機測試的真實信用卡帳單，驗證：

- statement period
- transaction date / posting date
- merchant description
- amount
- currency
- refund / reversal
- installment（若有）
- payment / fee / interest 与一般消费区分
- statement total / transaction sum reconciliation
- 重跑同一帳單不得重複交易

第一個 parser 只支援實際使用的銀行即可，不先追求「全台銀行通用 parser」。

### P0：PasswordInstructionExtractor 改為 context window

目前實作偏向只保留包含「密碼/password」關鍵字的行。真實郵件可能是：

```text
附件密碼規則如下：
身分證後四碼
加出生日期 YYYYMMDD
```

應評估改為找到關鍵行後，保留鄰近上下文（例如前 1 行、後 2~4 行），再做 PII masking，避免 AI 只看到「規則如下」卻看不到實際組合。

### P0：sender_pattern 自動選 Bank/Security Profile

`DocumentSecurityProfile.sender_pattern` 已存在，但主流程仍偏手動選 profile。

目標：

```text
Gmail sender / subject
        ↓
match bank profile
        ↓
自動選 secret profile + verified PasswordRule
        ↓
只有無法匹配/失敗才要求人工選擇
```

成功處理過一次後，下個月同銀行帳單應盡量不需要人工操作。

### P1：縮小 Gmail 搜尋範圍

目前預設 `in:anywhere has:attachment {filename:pdf filename:csv}` 太廣。

建議候選：
- 最近 60~90 天。
- 已知銀行 sender / domain。
- 信用卡帳單 subject pattern。
- PDF attachment。

需保留手動 full/backfill 能力，但日常同步不必掃整個 Gmail。

### P1：同步頻率重新評估

從 30 分鐘改成「啟動 + 每日 + 手動」是否更符合帳單頻率與 local-first 特性。

### P1：Excel 改 event-driven

優先評估在交易成功 commit、撤銷、恢復之後標記/觸發 rebuild，而非固定每 30 秒掃描。

### P2：凍結而不是重寫

以下模組若沒有 bug，先不重構：
- Documents 1:N source
- revocation/restore
- OCR
- Search / Jobs
- Excel ownership safety

目標是降低**未來新增複雜度**，不是花更多時間把已完成模組「重寫得更簡單」。

## 7. 建議的收斂後主流程

```text
Gmail
  │
  ├─ 啟動 / 每日 / 手動
  ▼
StatementDiscovery
(sender + subject + PDF)
  │
  ▼
Dedup
(message/attachment ID + SHA256)
  │
  ▼
Bank/Profile auto match
  │
  ▼
Password instruction context
  │
  ├─ verified rule → reuse
  └─ unknown rule → AI interprets masked text
  │
  ▼
PasswordComposer (local secrets)
  │
  ▼
PDF decrypt
  │
  ▼
extract_text()
  │
  ├─ sufficient → parser
  └─ insufficient → OCR fallback
  │
  ▼
BankStatementParser
  │
  ▼
validation / statement reconciliation
  │
  ▼
FinanceTransaction + SQLite
  │
  ├─ Dashboard
  └─ optional Excel rebuild
```

## 8. 高階模型必須回答的問題

請重新讀取目前 repository 實作，而不是只看本文件，並逐項回答：

1. 以「每月信用卡帳單消費分析」為目標，目前哪些模組屬於必要複雜度，哪些確實 Overdesign？
2. 已經做完的複雜功能，哪些「保留比拆除便宜」，哪些會持續造成維護成本、值得現在簡化？
3. Gmail History incremental sync vs 最近 60~90 天 idempotent re-scan，哪一種對此使用規模更適合？請比較 failure modes。
4. 30 分鐘 Gmail scheduler 是否應改為 startup + daily + manual？
5. Excel background projection worker / snapshot hash / output SHA 是否有必要？若簡化成 event-driven rebuild，會失去哪些實際保障？
6. Documents 1:N source records 是否應保留為穩定底層，還是應遷移成 statement-centric model？請把 migration/rewrite 成本納入判斷。
7. PasswordRule DSL 是否已達「足夠」，應停止擴充嗎？
8. PasswordInstructionExtractor 的上下文擷取與 sender_pattern auto-profile 是否應列為 P0？
9. 第一個 BankStatementParser 應如何設計，才能先支援一間真實銀行，又不重新走向過度抽象？
10. 對整個 repo 提出一份 **Keep / Simplify / Freeze / Remove-later** 清單。
11. 給出未來 2~3 個 milestone；不可新增與核心目標無關的平台功能。
12. 指出哪些修改應「現在做」，哪些應等真實帳單 evidence 後再做。

## 9. 審查原則

高階模型提出建議時必須遵守：

- 不以「理論最漂亮」為目標，以最小可維護產品為目標。
- 不因為有 120+ 測試就假設現有架構必須保留，也不因為覺得 overdesign 就忽略既有 migration/rewrite 成本。
- 不全面重寫。
- 不先建立多銀行 framework；第一個真實 parser 先跑通。
- 不把 PDF 解密/文字抽取成功等同於交易解析成功。
- 不用合成測試取代真實帳單驗收。
- 每項簡化都要說明：省掉什麼複雜度、失去什麼能力、風險如何補償。
- 安全邊界（SecretStore、PII 不送 AI、禁止 brute force）不得因簡化而降低。

## 10. 建議的近期完成定義

下一階段真正完成應至少達到：

1. 一個真實信用卡帳單來源可被 Gmail 找到。
2. 可自動選中正確 bank/security profile。
3. 加密 PDF 可依郵件規則自動解鎖。
4. 可從 PDF 正確建立交易。
5. 人工核對交易與帳單總額一致。
6. 同一帳單重跑不重複入帳。
7. Dashboard 可看到該月份消費。
8. Excel（若啟用）反映相同交易。
9. 無法辨識的新格式停在待處理，不猜測。
10. 全流程不把身分證、生日、PDF 密碼送給 AI 或寫入一般 DB/log。
