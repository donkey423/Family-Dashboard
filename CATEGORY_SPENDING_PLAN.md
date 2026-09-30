# 消費分類、支出圓餅圖與下鑽實作計畫

> 狀態：**已規劃、尚未實作。**
>
> 使用者於 2026-09-30 明確把「每筆交易分類、同類歸組、支出圓餅圖、點類別查看子項目」提升為下一階段產品需求。本文件取代舊文件中「本輪不做分類／圖表」對這個特定功能的限制；仍不授權擴張成通用財務平台、AI 理財、Budget、Tag 系統或完整 Dashboard 重寫。
>
> 本輪規劃時 repo 基準：`main @ f34550d`。開始實作前必須重新確認最新 HEAD/status，保留後續既有修改。

## 1. 使用者目標

使用者打開 Family Dashboard 時，要能一眼回答：

1. 這個月總共花多少？
2. 錢主要花在哪些類別？
3. 每個類別裡主要是哪一些商家／項目？
4. 點進商家後，實際是哪幾筆交易？
5. 對未分類或分錯的交易，只整理一次，未來相同商家能自動沿用。

目標流程：

```text
FinanceTransaction
       ↓
CategorizationService
       ↓
Effective Category
       ↓
月份 + 單一幣別彙總
       ↓
Donut / 排序清單
       ↓
Category
       ↓
Merchant subtotal
       ↓
Transaction rows
```

分類功能只改變「這筆錢屬於什麼」，**不能改變金額、日期、來源、Statement identity、transaction_kind、去重或會計語意**。

---

## 2. 最新 repo 現況與設計前提

目前 `FinanceTransaction` 已有：

- `transaction_date`
- `description`
- `amount`
- `currency`
- `statement_id`
- `posting_date`
- `transaction_kind`
- `statement_line_index`

目前沒有 category 欄位。

現有 Dashboard 支出語意在 `finance/queries.py`：

- legacy CSV 負數：支出。
- statement `purchase` / `fee` / `interest`：支出。
- statement `refund`：沖抵支出。
- statement `payment`：不是收入，也不是支出。

**分類彙總必須重用同一套支出語意。** 圓餅圖與分類合計不得另寫一套金額判定。

目前前端沒有 chart library，也沒有 frontend test framework；只有 React 19、Vite、TypeScript。

目前 Alembic head 為 `0011_statement_import`，分類 schema 以 `0012_transaction_categories` 為預定下一版，除非實作前 HEAD 已新增其他 migration。

---

## 3. 核心架構決策

### 3.1 V1 採 read-time effective category，不把 category 寫回 FinanceTransaction

第一版不新增：

```text
FinanceTransaction.category_id
FinanceTransaction.category_source
```

改成三個分類資料來源：

```text
FinanceTransaction
      │
      ├── TransactionCategoryOverride
      ├── CategoryRule
      └── System default
               ↓
        Effective Category
```

理由：

1. 修改規則後，歷史資料立即重分類，不需要批次 UPDATE。
2. 新交易會自動使用同一規則。
3. 單筆人工例外不會被後續規則覆蓋。
4. 不污染 parser / Statement / transaction identity。
5. 每月幾百～幾千筆的家庭規模，read-time resolution 足夠簡單。
6. 若未來 10k+ 交易的實測效能不足，再考慮 materialized cache；V1 不預先做。

### 3.2 新增三張表

#### `finance_categories`

```text
id
code                 UNIQUE
display_name
sort_order
is_system
is_active
created_at
updated_at
```

第一版不把 UI 顏色存 DB。顏色由前端依穩定 `code` 映射，避免多出非核心 CRUD。

#### `finance_category_rules`

```text
id
category_id          FK
match_type           normalized_exact | contains
normalized_pattern
priority
enabled
created_at
updated_at
```

V1 不支援 regex、embedding、模糊相似度或 AI 自動分類。

#### `transaction_category_overrides`

```text
transaction_id       UNIQUE FK
category_id          FK
created_at
updated_at
```

用途：單筆人工例外。

### 3.3 Effective Category 優先序

```text
1. Transaction override
2. normalized_exact rule
3. contains rule
   - priority 高者優先
   - 同 priority 時較長 pattern 優先
   - 再以穩定 ID / created order 作 deterministic tie-break
4. system semantic default
5. uncategorized
```

任何 resolver 都必須 deterministic；相同輸入與相同 rules 不能因 DB 回傳順序不同而改變分類。

### 3.4 財務語意與顯示分類分離

分類不能改變：

```text
purchase → 支出
refund   → 支出抵扣
fee      → 支出
interest → 支出
payment  → 不計入消費
```

即使使用者把 `payment` 顯示類別改成其他名稱，也不能讓它進入支出 Donut。

---

## 4. 預設類別

第一版 seed：

| Code | 顯示名稱 | 消費圖 |
| --- | --- | --- |
| food | 餐飲 | 是 |
| groceries | 日常採買 | 是 |
| transport | 交通 | 是 |
| shopping | 購物 | 是 |
| home | 居家／水電通訊 | 是 |
| family | 家庭／育兒 | 是 |
| health | 醫療／健康 | 是 |
| entertainment | 娛樂／訂閱 | 是 |
| travel | 旅遊 | 是 |
| education | 教育 | 是 |
| finance | 金融／手續費／保險 | 是 |
| uncategorized | 未分類 | 是 |
| income | 收入 | 否 |
| transfer | 轉帳／信用卡繳款 | 否 |

V1 不建立 subcategory table。

使用者說的「子項目」定義為：

```text
Category
  ↓
Merchant subtotal
  ↓
Transaction rows
```

未來若真實使用證明「餐飲 → 外送／咖啡／餐廳」有價值，再另加 taxonomy。

---

## 5. Merchant normalization 與規則

新增純函式：

```python
normalize_description(description: str) -> str
```

V1 只做：

- Unicode NFKC。
- trim。
- 多重 whitespace collapse。
- case normalize。

**不做：**

- 自動刪數字。
- 自動刪店號。
- 編輯距離。
- fuzzy match。
- embedding。
- AI 猜商家。

例：

```text
"  Uber   Eats " → "UBER EATS"
"7-ELEVEN 001"   ≠ "7-ELEVEN 002"
```

若使用者希望兩間店都歸同類，明確建立 `contains("7-ELEVEN")` rule。

Merchant drill-down 不新增 Merchant table。以 normalized description 作 grouping key；顯示名稱取該 group 中最近一筆交易的原始 description，保持 deterministic。

---

## 6. 使用者操作語意

### 6.1 只改這一筆

```text
交易 → 選類別 →「只修改這一筆」
```

Backend upsert `transaction_category_overrides`。

### 6.2 相同商家以後都這樣

```text
交易 → 選類別 →「相同商家都套用」
```

Backend upsert `normalized_exact` rule。

因為分類在 read time 計算：

- 歷史同商家非 override 交易立即反映。
- 未來新交易自動反映。
- 既有單筆 override 保留。

### 6.3 未分類整理入口

新增「未分類商家」工作流：

```text
未分類
27 個商家 · NT$18,430

Uber Eats      12 筆   NT$4,520   [餐飲 ▼] [相同商家都套用]
PChome          4 筆   NT$3,890   [購物 ▼] [相同商家都套用]
Spotify         3 筆     NT$537   [娛樂／訂閱 ▼] [...]
```

目標是第一個月整理較多，之後只處理新商家。

---

## 7. 支出彙總與 Donut 語意

### 7.1 單一幣別

Donut 一次只顯示一種 currency。

禁止：

```text
TWD 1000 + JPY 1000 = 2000
```

若使用者選「全部幣別」，分類區顯示可用幣別切換，不做未授權匯率換算。

### 7.2 Refund

同類別：

```text
purchase 1000
refund    300
→ category net spend = 700
```

所有 category signed net 合計必須等於同月份／同幣別 Dashboard expense。

### 7.3 負淨額類別

跨月退款可能造成：

```text
9 月餐飲 purchase = 0
9 月餐飲 refund   = 1000
category net      = -1000
```

Pie / Donut 不能畫負 slice。

因此：

- Donut 只顯示 **net > 0** 的消費類別。
- `net <= 0` 不畫 slice。
- 另外顯示「退款／抵扣」區塊，列出負淨額類別。
- Dashboard 的「支出」仍使用現有正式語意。
- Donut 不冒充所有 refund 後的完整 signed sum；UI 必須同時顯示正向分類總額與退款／抵扣。

### 7.4 Top 5 + 其餘類別

資料層可有 10+ 類，但圖表最多顯示：

```text
Top 5
+
其餘類別
```

注意：

- 真實 category `uncategorized` 顯示「未分類」。
- 圖表 aggregate 顯示「其餘類別」。
- 兩者不可都叫「其他」。

點「其餘類別」先看到它包含哪些真實 categories，再繼續 drill-down。

---

## 8. Backend API

### 8.1 Categories

```http
GET   /api/finance/categories
POST  /api/finance/categories
PATCH /api/finance/categories/{category_id}
```

V1 不硬刪已被 rule/override 使用的 category；以 `is_active` 停用。

### 8.2 Rules

```http
GET    /api/finance/category-rules
POST   /api/finance/category-rules
PATCH  /api/finance/category-rules/{rule_id}
DELETE /api/finance/category-rules/{rule_id}
```

DELETE 可採真正刪除 rule，因為交易本身不保存規則結果；刪除後自然回到下一層 resolution。

### 8.3 Spending summary

```http
GET /api/finance/spending-by-category?month=2026-09&currency=TWD
```

建議 payload：

```json
{
  "month": "2026-09",
  "currency": "TWD",
  "dashboard_expense": "38080.00",
  "positive_category_total": "39380.00",
  "refund_credit_total": "-1300.00",
  "categories": [
    {
      "category_id": "food",
      "name": "餐飲",
      "net_amount": "12430.00",
      "transaction_count": 21
    }
  ],
  "negative_categories": []
}
```

### 8.4 Merchant drill-down

```http
GET /api/finance/category-merchants
  ?month=2026-09
  &currency=TWD
  &category_id=<id>
```

回 category 內 merchant key / display name / signed net / count。

### 8.5 Transaction API 擴充

既有：

```http
GET /api/finance/transactions
```

新增 filter：

- `category_id`
- `merchant_key`

每筆回傳：

- effective category id/name。
- category source：`override | exact_rule | contains_rule | system | uncategorized`。
- 原有 transaction identity 欄位不變。

Category filter 在 read-time classification 後再 pagination；`total` 必須是 category filter 後的真實總數。

### 8.6 修改分類

```http
PATCH /api/finance/transactions/{transaction_id}/category
```

Body：

```json
{
  "category_id": "...",
  "scope": "transaction"
}
```

或：

```json
{
  "category_id": "...",
  "scope": "merchant"
}
```

- `transaction`：upsert override。
- `merchant`：upsert exact rule。
- 不修改 FinanceTransaction identity。

### 8.7 未分類商家

```http
GET /api/finance/uncategorized-merchants?month=&currency=
```

用于快速整理。

---

## 9. Backend 實作落點

建議新模組：

```text
backend/src/family_finance_hub/finance/categorization/
    contracts.py
    normalization.py
    resolver.py
    service.py
    queries.py
```

Migration：

```text
backend/alembic/versions/0012_transaction_categories.py
```

開始實作前若 Alembic head 已不再是 0011，必須使用新的下一 revision，不可硬搶 0012。

Resolver 每次 request：

1. 一次讀 active categories/rules。
2. 一次讀候選 transaction IDs 的 overrides。
3. 在 Python 中建立 resolver map。
4. 批次分類，禁止 N+1 rule/override query。

V1 不在 parser 中加入銀行分類關鍵字。

---

## 10. Frontend

新增獨立元件，不繼續把 `App.tsx` 變成單檔大元件：

```text
SpendingByCategory.tsx
CategoryDonut.tsx
CategoryDetailPanel.tsx
CategoryPicker.tsx
UncategorizedReview.tsx
CategorySettings.tsx
```

### 10.1 Chart library

採 **Recharts**，不自行維護完整 SVG chart geometry。

理由：

- responsive。
- touch。
- tooltip。
- slice click。
- resize。
- accessibility state。
- single/zero slice edge cases。

不因一個 dependency 建立通用 chart framework。

### 10.2 Overview

放在現有月份／幣別總覽指標後：

```text
本月支出分類
[ Donut ]

餐飲          NT$12,430  32%
交通           NT$7,800  20%
購物           NT$6,300  16%
...
```

Donut 与排序清单都可点击。

### 10.3 Drill-down

```text
Category
   ↓
Merchant subtotal
   ↓
Transaction rows
```

手机优先用可滚动 detail panel / bottom sheet；不要要求点很小的 slice 才能操作。

### 10.4 URL / 页面状态

沿用现有轻量 URL state，不为了分类引入 React Router。

月份、币别、category filter 应可写入 URL，返回交易页/总览时保持上下文。

### 10.5 Frontend tests

目前 frontend 没有测试框架。本功能首次加入最小：

- Vitest。
- React Testing Library。

先覆盖：

- `CategoryDonut`
- `CategoryDetailPanel`
- `CategoryPicker`
- `UncategorizedReview`

不因为这项功能顺便导入大型 E2E framework。

---

## 11. Excel

SQLite 仍是事实来源，分类是可重算视图。

`WorkbookExportService` 读取 snapshot 时调用同一个 `CategorizationService`，不能在 xlsx writer 里重写规则。

`ExportTransaction` 增加：

- effective category code/name。

「交易明细」新增：

- 分类。

新增 worksheet：

```text
分类支出
月份 | 币别 | 分类 | 净支出 | 笔数
```

若存在负净额类别，明确显示负值，不伪造成 pie slice。

**分类规则／override 变化必须参与 workbook snapshot fingerprint。**
只改分类而没改金额，也必须让 Excel `needs_update=true`。

---

## 12. C1-C5 工作包

### C1 — Category domain + migration

- 新增 category/rule/override models。
- seed system categories。
- 不改 FinanceTransaction identity。
- migration upgrade/downgrade/data preservation tests。

### C2 — Categorization engine

- normalization。
- deterministic precedence。
- overrides。
- exact / contains rules。
- system defaults。
- uncategorized。
- batch resolver，无 N+1。

### C3 — APIs

- categories CRUD。
- rules CRUD。
- spending-by-category。
- category-merchants。
- transaction effective category / filters。
- transaction vs merchant 分类 action。
- uncategorized merchant inbox。

### C4 — Dashboard / Donut / Drill-down

- Recharts。
- Top 5 + 其余类别。
- refund/credit block。
- category → merchant → transaction。
- 分类编辑与未分类整理。
- mobile + keyboard + textual fallback。
- Vitest + RTL。

### C5 — Excel + delivery regression

- Excel 分类栏。
- 分类支出 worksheet。
- fingerprint。
- backup/restore regression。
- full backend suite + frontend tests/build。
- 当次 `E2E-GMAIL-3BANK` delivery gate。

---

# 13. Test Matrix

## 13.1 P0：没有这些不能 merge

### Migration / schema

| ID | Case | Expected |
| --- | --- | --- |
| CAT-M01 | 0011 → 分类 migration，已有 CSV/Statement 交易 | 交易内容/identity 完全保留 |
| CAT-M02 | 空 DB upgrade | system categories 各一份 |
| CAT-M03 | upgrade / downgrade / re-upgrade | 不重复 seed，不丢原交易 |
| CAT-M04 | invalid category FK | constraint 拒绝 |
| CAT-M05 | override transaction FK | transaction 不存在时拒绝 |
| CAT-M06 | rule match type 非 whitelist | 拒绝 |
| CAT-M07 | 停用 category 仍被 override/rule 引用 | 不产生 dangling reference |
| CAT-M08 | migration 前后 `row_hash` / statement identity | 完全不变 |

### Normalization

| ID | Case | Expected |
| --- | --- | --- |
| CAT-N01 | case difference | 相同 normalized key |
| CAT-N02 | 前后空白 / 多空白 | 相同 |
| CAT-N03 | 全形/半形 NFKC | 相同 |
| CAT-N04 | normalize(normalize(x)) | 等于 normalize(x) |
| CAT-N05 | 数字店号不同 | V1 不自动合并 |
| CAT-N06 | `%` / `_` / `\\` 等特殊字符 | 不意外变 SQL wildcard |
| CAT-N07 | 中文/emoji/超长描述 | 安全、deterministic |

### Rule precedence

| ID | Case | Expected |
| --- | --- | --- |
| CAT-R01 | override + exact | override |
| CAT-R02 | exact + contains | exact |
| CAT-R03 | 两个 contains | priority 高者 |
| CAT-R04 | 同 priority contains | 较长 pattern，再稳定 tie-break |
| CAT-R05 | disabled rule | 忽略 |
| CAT-R06 | inactive category rule | 不作为有效分类 |
| CAT-R07 | 无任何规则 | uncategorized |
| CAT-R08 | 相同规则重复建立 | 明确 conflict 或 idempotent，不产生歧义 |
| CAT-R09 | rule 改类別 | 非 override 历史交易即时反映 |
| CAT-R10 | rule 改类別 + existing override | override 保留 |

### Manual / remember merchant

| ID | Case | Expected |
| --- | --- | --- |
| CAT-O01 | 只改单笔 | 只有该 transaction override |
| CAT-O02 | 相同商家套用 | 建 exact rule，历史/未来即时反映 |
| CAT-O03 | merchant rule 覆盖 20 笔，其中 3 笔 override | 17 笔跟规则，3 笔不变 |
| CAT-O04 | rule 写入失败 | 不留半成品 |
| CAT-O05 | override 写入失败 | 原分类维持 |
| CAT-O06 | 删除 rule | 非 override 交易回到下一层 resolution |
| CAT-O07 | 停用 category | API 不允许新的 assignment 到停用 category |

### 财务语义 / aggregation invariant

| ID | Case | Expected |
| --- | --- | --- |
| CAT-A01 | purchase | 增加该分类支出 |
| CAT-A02 | fee | 增加支出，默认 finance |
| CAT-A03 | interest | 增加支出，默认 finance |
| CAT-A04 | refund 同类别 | 减少该类别净支出 |
| CAT-A05 | payment | 不进入消费图 |
| CAT-A06 | CSV 正收入 | 不进入消费图，system income |
| CAT-A07 | CSV 负支出 | 正常分类 |
| CAT-A08 | 同 month/currency 所有 signed category net 总和 | == 既有 Dashboard expense |
| CAT-A09 | transaction category 修改 | Dashboard 总支出不变 |
| CAT-A10 | category 修改 | amount/date/source/row_hash/statement identity 全不变 |

### Refund edge cases

| ID | Case | Expected |
| --- | --- | --- |
| CAT-F01 | purchase > refund | 正净额 slice |
| CAT-F02 | purchase == refund | 0，不画 slice |
| CAT-F03 | purchase < refund | 负净额进退款/抵扣，不画 slice |
| CAT-F04 | 跨月只有 refund | 当月负净额正确 |
| CAT-F05 | 多个 refund + purchase | signed net 正确 |

### Currency / date / lifecycle

| ID | Case | Expected |
| --- | --- | --- |
| CAT-L01 | TWD/JPY/USD 同类别 | 绝不相加 |
| CAT-L02 | 月初/月末 | 正确进入该月 |
| CAT-L03 | leap day | 正确 |
| CAT-L04 | transaction_date NULL | 不偷偷进入任一月份 |
| CAT-L05 | revoked document | 完全退出 category summary/drill-down |
| CAT-L06 | restore | 精确恢复分类视图 |
| CAT-L07 | revoked 时规则改变、再 restore | override 保留；非 override 使用当前规则 |
| CAT-L08 | Statement re-analyze/reuse | 不改变 transaction identity 或 override |
| CAT-L09 | CSV 与 Statement transaction | 走同一个 resolver |

### API

| ID | Case | Expected |
| --- | --- | --- |
| CAT-API01 | category filter + month + currency | total/items 正确 |
| CAT-API02 | category filter pagination | total 是 filter 后总数 |
| CAT-API03 | invalid category ID | 404/422，不 fallback |
| CAT-API04 | invalid month/currency | 沿用现有 validation |
| CAT-API05 | merchant_key 不存在 | 空结果，不 500 |
| CAT-API06 | stale/deleted transaction override target | fail safe |
| CAT-API07 | concurrent two category writes | 最终状态明确，不出现半写 |
| CAT-API08 | API response | 不泄露 raw secret/source sensitive content |

### Excel

| ID | Case | Expected |
| --- | --- | --- |
| CAT-X01 | 只改分类，不改金额 | workbook `needs_update=true` |
| CAT-X02 | 交易明细分类 | 与 Web effective category 一致 |
| CAT-X03 | 分类支出 worksheet | signed net 与 API 一致 |
| CAT-X04 | payment | 不进分类消费汇总 |
| CAT-X05 | refund | 正确负向冲抵 |
| CAT-X06 | 多币别 | 分开 |
| CAT-X07 | revoked/restore | 与 Web 一致 |
| CAT-X08 | category 名称类似 Excel formula | sanitizer 阻止公式注入 |
| CAT-X09 | workbook fingerprint | rules + overrides 变化会改变 snapshot |

## 13.2 P1：正式日常使用前完成

### Donut / grouping

- CAT-D01：0 transaction → 空状态，不出现 NaN/Infinity。
- CAT-D02：1 category → 单 slice 正常。
- CAT-D03：刚好 5 categories → 不建立「其余类别」。
- CAT-D04：6+ categories → Top 5 + 其余类别。
- CAT-D05：「其余类别」金额 = 被合并 categories 总和。
- CAT-D06：「未分类」与「其余类别」是不同概念。
- CAT-D07：同金额 categories 排序 deterministic。
- CAT-D08：负/0 类别不进入 donut。
- CAT-D09：pie displayed total = 所有 eligible positive category net。
- CAT-D10：百分比 rounding 行为固定，不因 render 顺序漂移。

### Merchant drill-down

- CAT-MER01：category merchant subtotals 合计 = category signed net。
- CAT-MER02：merchant transaction count 正确。
- CAT-MER03：相同 normalized key 聚合。
- CAT-MER04：不同店号 V1 不自动合并。
- CAT-MER05：代表显示名称 deterministic。
- CAT-MER06：点 merchant 后 transaction list 与 subtotal 一致。

### Frontend state

- CAT-UI01：点击 donut slice = 点击文字清单，同一结果。
- CAT-UI02：在餐饮 drill-down 把一笔改交通后，餐饮列表/金额/Donut 同步减少，交通同步增加，总支出不变。
- CAT-UI03：PATCH 失败时 UI rollback，不与 DB 分叉。
- CAT-UI04：快速切 month/currency 时旧 request 不覆盖新 request。
- CAT-UI05：URL 保存 month/currency/category。
- CAT-UI06：320px / 390px 不需横向卷动。
- CAT-UI07：超长 category/merchant 不破版。
- CAT-UI08：keyboard Enter/Space 可进入 drill-down。
- CAT-UI09：不只靠颜色，文字列含 category/name/amount/%。
- CAT-UI10：screen reader 有可理解 label。
- CAT-UI11：退款/抵扣区块可进入明细。
- CAT-UI12：没有该币别资料时明确空状态。

### Category management

- CAT-C01：rename category 后 Web/Excel 共同反映。
- CAT-C02：停用 category 不再可选，但历史 resolution 有安全 fallback。
- CAT-C03：不能停用必要 system category 到让 resolver 无 fallback。
- CAT-C04：duplicate code/name 规则明确。
- CAT-C05：规则 CRUD 后历史立即反映。
- CAT-C06：删除 override 后回到 rule/system。

### Backup / restore

- CAT-B01：categories/rules/overrides 全部进入 backup。
- CAT-B02：restore 后 effective categories 完全一致。
- CAT-B03：restore 不自动新增/改写 rules。
- CAT-B04：restore 后 Excel 重建结果一致。

## 13.3 P2：资料量增加后

- CAT-P01：10,000 transactions + 20～50 rules，月分类汇总目标 < 200 ms local（以实际 Windows 主机记录为准，不作为跨机器绝对 SLA）。
- CAT-P02：500 merchant drill-down 不出现 N+1。
- CAT-P03：category filter 不为每笔 transaction 单独 query rule/override。
- CAT-P04：property test：相同 input/rules resolution deterministic。
- CAT-P05：property test：manual override 经任意自动规则执行仍保留。
- CAT-P06：property test：所有 signed category net == Dashboard expense。
- CAT-P07：property test：Top-N grouping 不丢金额。

---

## 14. Frontend 测试策略

新增最小测试依赖：

```text
vitest
@testing-library/react
@testing-library/user-event
jsdom
```

不因这项功能直接导入 Playwright/Cypress。

Component tests 至少覆盖：

- Donut data transformation。
- click / keyboard drill-down。
- Top 5 + 其余类别。
- refund/credit display。
- CategoryPicker success/error rollback。
- UncategorizedReview remember merchant。
- stale request protection。

另保留真实桌面 + 390px/320px 浏览器 smoke test。

---

## 15. E2E 与交付关卡

分类功能自己的正确性主要由上方合成／隔离 tests 验证。

但是本 repository 当前有使用者指定的全项目交付关卡：

`E2E-GMAIL-3BANK`

因此：

- 仅更新本规划文件：不需要假装重跑三银行；只能宣称「文件已更新」，不能宣称项目验收完成。
- 真正 C1-C5 实作准备交付时：仍必须依 `AGENTS.md` / `IMPLEMENTATION_PLAN.md 4.1` 当次重新跑三银行。
- E2E-GMAIL-3BANK 是 delivery regression gate，不是分类算法本身的 unit test。
- 分类实作不授权正式资料自动 confirm，也不降低 parser/reconciliation 标准。

---

## 16. 明确不做

本功能不顺手加入：

- AI 自动分类。
- Budget / 预算。
- 理财建议。
- Savings goal。
- Tag / 多标签系统。
- 多层 subcategory taxonomy。
- Merchant master database。
- 模糊字符串／embedding merchant resolution。
- 汇率换算。
- 通用 Dashboard builder。
- 双向 Excel 编辑。
- 新 microservice。

若以后要 AI 分类，只能作为 opt-in 建议：发送最小 normalized merchant description，不发送金额、日期、账户、银行或完整历史；使用者确认后写成普通 rule。不得成为 V1 前置。

---

## 17. Definition of Done

只有同时满足以下条件，才能说分类支出功能完成：

1. 每一笔有效交易都能解析出 Effective Category；没有匹配时明确为「未分类」。
2. 同月份＋同币别的所有 signed category net 合计永远等于既有 Dashboard expense。
3. payment 不进入消费图；refund 正确冲抵。
4. 多币别绝不直接相加。
5. Donut 能一眼显示主要支出去向，并提供文字金额列表。
6. 可由 Category → Merchant → Transaction 下钻。
7. 「只改这一笔」不会影响同商家其他交易。
8. 「相同商家都套用」会立即影响历史非 override 交易，并自动作用于未来交易。
9. 人工 override 永远优先于自动 rule。
10. revoked/restore、Statement 重跑、CSV/PDF 来源都保持一致。
11. Web 与 Excel 使用同一个 CategorizationService 结果。
12. 只改分类也会触发 Excel projection 更新。
13. P0 tests 全通过；P1 完成后才能作为日常功能交付。
14. frontend component tests + production build 通过。
15. 当次 repository delivery 依现行规则完成 E2E-GMAIL-3BANK，或明确标示外部 BLOCKED，不以旧结果冒充。
