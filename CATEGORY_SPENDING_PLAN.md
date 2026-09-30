# 家庭收支記錄：消費分類、支出圓餅圖與下鑽實作計畫

> 狀態（2026-09-30）：**C1-C5 人工分類／商家規則／圖表 V1 已實作並部署；逐筆自動辨識尚未實作。** 第 18 節為使用者要求的深度研究與後續工作包，本次只授權更新文件及 Git，不等於批准自動分類程式或雲端資料傳送。
>
> 使用者於 2026-09-30 明確把「每筆交易分類、同類歸組、支出圓餅圖、點類別查看子項目」提升為下一階段產品需求。本文件取代舊文件中「本輪不做分類／圖表」對這個特定功能的限制；仍不授權擴張成通用財務平台、AI 理財、Budget、Tag 系統或完整 Dashboard 重寫。
>
> 規劃起點為 `f34550d`，遠端分類文件基準為 `main @ bf3d4f6`；目前版本與同步結果須以 `git status`、`git log` 及遠端 ref 重查，不由本文件推定。使用者授權後正式資料庫已升級 `0012_transaction_categories`，18 筆既有交易與來源保留；分類預覽仍是独立合成資料庫，不是正式日常入口。

## 1. 使用者目標

使用者打開 Family Dashboard 時，要能一眼回答：

1. 這個月總共花多少？
2. 錢主要花在哪些類別？
3. 每個類別裡主要是哪一些商家／項目？
4. 點進商家後，實際是哪幾筆交易？
5. 明確且穩定的商家可記住分類；多用途商家須允許逐筆不同分類，不把一次選擇擴張為所有商品的分類。

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

前端已加入 Recharts，以及 Vitest / React Testing Library / user-event / jsdom。分類功能以 lazy-loaded 元件載入，不重寫既有 Dashboard。

程式與正式資料庫均為 `0012_transaction_categories`，down revision 為 `0011_statement_import`。本輪授權部署已完成成對備份、副本還原及 migration downgrade/re-upgrade、正式 migration／同步 build／正常登入帳戶啟動與回歸。後續不得把新版程式直接重啟到不同 schema 的正式資料庫；仍需當次授權、備份及驗證。

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

第一版不把 UI 顏色存 DB。顏色由前端依穩定 `code` 映射，避免多出非核心 CRUD。`code` 唯一；`display_name` 可重複，避免改名造成識別或關聯變更。

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

## 4. 分類 Taxonomy：2026-09-30 深度審查後建議

> 狀態：**使用者已核准把本節建議寫入規劃並 merge；程式／migration 尚未因此自動完成。** 目前正式 0012 仍是既有 14 類。後續 A1-A3 實作時才依本節調整 schema、seed、顯示名稱、規則與測試。

分類設計的原則不是「圓餅圖只能有幾類」，而是把兩層問題分開：

1. **資料 taxonomy 要足夠有分析價值。**
2. **Donut 顯示要克制，最多約 6 個 slice。**

因此不為了圖表可讀性把資料硬壓成 5～6 類；圖表以 Top-N／其餘類別控制視覺複雜度。

### 4.1 建議最終類別

#### 消費側類別

| Code | 建議顯示名稱 | 定義 | Donut |
| --- | --- | --- | --- |
| `food` | 飲食 | 餐廳、咖啡、飲料、明確外送；核心是立即食用／飲用 | 是 |
| `groceries` | 日常採買 | 超市、生鮮、家庭日常消耗品；核心是帶回家儲存／使用 | 是 |
| `transport` | 交通 | 捷運、公車、高鐵、計程車、停車、油資、過路費等移動成本 | 是 |
| `shopping` | 購物 | 服飾、3C、一般實體／網購商品；沒有更明確用途時才用 | 是 |
| `home` | 居家／水電通訊 | 水電、瓦斯、網路、電信、管理費、居家維護 | 是 |
| `family` | 家庭／育兒 | 托育、兒童用品、家庭成員專屬支出 | 是 |
| `health` | 醫療／健康 | 醫院、診所、藥局、治療、健身等健康用途 | 是 |
| `entertainment` | 娛樂／數位服務 | 串流、遊戲、影音、數位內容／服務；「訂閱」本身不是分類 | 是 |
| `travel` | 旅遊 | 航空、住宿、景點、旅行租車等明顯旅行專屬支出 | 是 |
| `books` | 圖書 | 實體書、電子書、漫畫、可辨識書籍交易 | 是 |
| `education` | 課程／教育 | 學費、課程、培訓、補習、教學服務 | 是 |
| `insurance` | 保險 | 保費；與利息／手續費分離，避免大型保費污染金融費用分析 | 是 |
| `finance` | 金融費用 | 手續費、利息、卡費等金融成本 | 是 |
| `uncategorized` | 未分類 | 資訊不足或多用途商家，不能可靠判斷時的正確結果 | 是 |

#### 非消費系統類別

| Code | 顯示名稱 | 語意 | Donut |
| --- | --- | --- | --- |
| `income` | 收入 | legacy CSV 正向收入等 | 否 |
| `transfer` | 轉帳／信用卡繳款 | 資金搬移／信用卡繳款，不是消費 | 否 |

後續若新增 `books`／`insurance`，或把既有顯示名稱由「餐飲」改為「飲食」、「娛樂／訂閱」改為「娛樂／數位服務」、「金融／手續費／保險」收斂為「金融費用」，必须：

- 保留既有 category identity／references。
- migration seed 冪等。
- workbook fingerprint 能反映 taxonomy 版本变化。
- upgrade／downgrade 在副本驗證。
- 不把顯示名稱變更當成 transaction identity 變更。

### 4.2 分類依「消費目的」，不是單看商家名稱

只有描述足夠明確時才自动分類；商家本身可卖多种商品时，未知优于硬猜。

#### 可以作为明确规则的例子

```text
UBER EATS      → 飲食
NETFLIX        → 娛樂／數位服務
明确航空公司   → 旅遊
明确药局／诊所 → 醫療／健康
明确电子书服务 → 圖書
```

#### 不应建立粗略 merchant-wide 自动规则的例子

```text
7-ELEVEN / 全家
Costco
蝦皮 / momo / PChome
百貨公司
LINE Pay / 街口 / Apple Pay
Apple / Google
```

理由：它们可能同时对应饮食、日常采购、购物、图书、数位服务、缴费或纯支付通路。

支付平台尤其只能当支付方式，不能当消费类别。

### 4.3 容易混淆的边界

#### 交通 vs 旅遊

不要依「使用者当时是不是在旅行」推断，因为交易本身通常没有可靠 trip context。

```text
日常移动性质 → 交通
明显旅行专属 → 旅遊
```

示例：

- 捷运／公车／计程车／停车／加油／高铁：默认交通。
- 航空／饭店／景点／旅行租车：默认旅游。
- 若某一笔高铁实际要算旅游，由 transaction override 处理，不建立全域猜测。

#### 飲食 vs 日常採買

```text
立即吃／喝 → 飲食
带回家储存／家庭消耗 → 日常採買
```

便利商店属于典型多用途商家，没有 item-level data 时保持未分类或逐笔确认。

#### 圖書 vs 課程／教育

```text
买内容 → 圖書
买教学服务 → 課程／教育
```

例如电子书／明确书店交易可进图书；线上课程、学费、培训进教育。

#### 娛樂／數位服務 vs「訂閱」

「订阅」是付款频率，不是消费目的：

- Netflix → 娱乐／数位服务。
- iCloud → 数位服务。
- 健身房月费 → 医疗／健康。
- 线上课程月费 → 课程／教育。

未来若要 recurring detection，应作为独立属性，不新增「订阅」为万能类别。

### 4.4 自动分类信心等级

后续 A1-A3 建议把商家规则分成三层，而不是追求 100% 自动覆盖：

| 等级 | 定义 | 行为 |
| --- | --- | --- |
| A：确定 | 描述高度明确且单一用途 | 可由经过验证的本机规则自动采用 |
| B：高概率但仍可能多用途 | 有明显倾向，但存在合理反例 | 显示建议，默认逐笔确认 |
| C：多用途／支付通路 | 单靠描述无法可靠判断 | 保持未分类，不建立 merchant-wide 自动规则 |

品质目标应优先提高 **precision**，而不是强迫 coverage 接近 100%。未知是安全结果，不是失败。

### 4.5 V1 仍不增加 subcategory group

第一阶段维持：

```text
Category
  ↓
Merchant subtotal
  ↓
Transaction rows
```

不新增：

```text
Group
  ↓
Category
  ↓
Subcategory
  ↓
Merchant
```

Top-N 已解决 Donut 视觉复杂度。只有未来实际需要 Budget、Need/Want、固定／弹性支出或年度分析时，再评估 category group。


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

### 7.4 Donut 最多 6 slices；未分類要可見

資料 taxonomy 可以有 10+ 類，但 Donut 不應把每一類都畫成 slice。

现行程式是 Top 5 +「其餘類別」。後續 A2/A3 建議微調為：

- 若 `uncategorized` 净额 > 0，**保留一个明确的「未分类」slice**，不要让它被聚合进「其余类别」。
- 总 slice 数仍最多 6。
- 当正向类别 > 6 且存在未分类时：显示金额最高的 4 个已分类类别 + 未分类 + 其余类别。
- 当没有未分类时：维持 Top 5 + 其余类别。
- 当正向类别总数 <= 6：全部直接显示，不建立其余类别。
- `其餘類別` 永远放最后；`未分類` 使用固定中性灰色。
- 同一个 category 跨月份必须保持固定颜色，不因排名变化换色。
- 负净额／0 类别继续不进 Donut，使用退款／抵扣区块。

理由：「未分类」不是普通分析类别，而是待处理工作量；即使金额较小，也应该让使用者一眼看见。

```text
有未分类且类别很多：
饮食
日常采购
交通
购物
未分类
其余类别
```

`未分類` 与 `其餘類別` 必须是两个不同概念。点击「其余类别」先展开真实 categories；点击「未分类」直接进入待分类商家／逐笔整理。

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

目前已實作模組；後續沿用這個邊界，不另外建立平行 categorization engine：

```text
backend/src/family_finance_hub/finance/categories/
    domain.py
    service.py
    api.py
```

Migration：

```text
backend/alembic/versions/0012_transaction_categories.py
```

本次已確認基準 head 為 0011，並完成 0012。後續新增 migration 前仍須重新檢查 head，不可重用既有 revision。

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

本功能已加入最小測試框架：

- Vitest。
- React Testing Library。

已覆蓋：

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

## 13.0 本次驗證與測試落點

2026-09-30 正式部署前重新跑完整 backend：**326 passed，2 個既有相依套件棄用警告**（原分類／核心回歸 310 + 16 項附件下載驗證）；frontend：**29 passed**；TypeScript + Vite production build 通過，先建置至備份目錄 `new-frontend`，保留舊產物後部署至正式 `frontend/dist`。

下表將後續驗收 ID 對應到實際測試；同一參數化測試可覆蓋多個 case，不是每個 ID 都新增一個 test function。

| 驗收群組 | 實際落點與驗證 |
| --- | --- |
| CAT-M01-M08 | `backend/tests/test_categories.py`：migration forward/downgrade/re-upgrade、seed、runtime FK、inactive references；保留原 CSV/Statement 全欄位與 identity |
| CAT-N01-N07、R01-R10 | `test_category_domain.py`：NFKC、空白、店號、literal contains、stable ties；`test_categories.py`：rule CRUD、停用、重複 conflict 與即時重分類 |
| CAT-O01-O07、API01-API08 | `test_categories.py`：單筆／商家規則、20 筆中的 3 筆例外、未來匯入、404/422、失敗 rollback、SQLite BUSY、並行寫入及 filtered pagination；回應不含 raw_json |
| CAT-A01-A10、F01-F05、L01-L09 | `test_category_domain.py` / `test_categories.py`：purchase/fee/interest/refund/payment/CSV、金額不變、五種退款邊界、三幣別、閏日/NULL、撤銷與復原；`test_statement_import.py`：重解析及重確認保留 override identity |
| CAT-X01-X09、B01-B04、C01-C06 | `test_categories.py` / `test_xlsx_writer.py`：Web/Excel 同 resolver、分類 fingerprint、公式防護、工作簿重建、多幣別、備份還原、不重建規則、rename/停用/重複 code 契約 |
| CAT-D01-D10 | `frontend/src/categories/chart.test.ts`：0/1/5/6/12 類、Top 5 + 其餘、未分類、負/零、穩定排序、整數 cents 與百分比；真實瀏覽器確認 Recharts SVG 有 6 個 slice |
| CAT-MER01-MER06、UI01-UI05、UI08-UI09、UI11-UI12 | `test_categories.py` 的 merchant/filter tests + `frontend/src/categories/categories.test.tsx`：subtotal/count、頁碼、來源文件、slice/文字/鍵盤、兩種寫入範圍、error、stale month/currency、URL 重開與空狀態；隔離瀏覽器操作分類後重新核對金額 |
| CAT-UI06-UI07 | 真實瀏覽器桌面、320px、390px，長商家與類別不重疊；另有交易表有／無來源欄兩個結構回歸測試。這不是實體手機驗收 |
| CAT-UI10 | 已驗證 accessible label 與鍵盤入口；**尚未以實際 screen reader 驗收** |
| CAT-P02-P07 | `test_categories.py`：500 商家與 1,000 筆 filtered pagination 至多 6 queries；10k batch resolver 3 config queries；固定 seed 生成資料 invariants。`test_category_domain.py`：100 次 shuffled rules/override 保留；`chart.test.ts`：0-64 類生成資料 Top-N 金額守恆 |
| CAT-P01 | 10,008 筆／50 規則：resolver + aggregation 37.7ms；完整 API 首次 259.6ms、暖機 187.4/185.4ms。**首次未達 <200ms 目標**；ORM 載入及 serialization 仍是後續優化項，不以局部耗時宣稱 API 全數達標 |

正式部署後 `E2E-GMAIL-3BANK` 又以本輪新下載原檔通過：中國信託 1 列、國泰 19 列、永豐 31 列；先讀來源郵件格式、本機記憶體解鎖、獨立逐欄核對、normalizer/analysis ready、重複收錄與 Statement reuse。證據在 `data/gmail-acceptance/retest-20260930-1903/`，中信首次下載未產生新檔，重新載入原信／確認附件可用後以新 checkpoint 重試才通過。AI 0 次、confirm 0 次，驗收期間正式 0012／18 筆與 fingerprint 不變。這不是長期 MCP 排程、第二期盲測或新增正式 Excel 交易的驗收。

正式入口：`http://127.0.0.1:3000/`／`https://desktop-vcgfqnq.tailb47104.ts.net/`，已驗真實 Donut 非空、分類 → 商家 → 單筆 → 原始文件、分類設定與 320px／390px 響應式畫面。正式驗收未建立規則／override，既有消費目前顯示「未分類」，不猜分類。Owned Excel 18 筆、各月／幣別／分類淨額與 API／Dashboard 核對一致。成對備份與部署證據見 HANDOFF。

隔離預覽維持 3001／8030／私有 HTTPS 8443 與 `data/category-preview/synthetic.db`；合成來源已撤銷、有效交易 0 筆，不自行恢復或當作使用者真實支出。

尚未完成：實體手機、screen reader、重開機後持續服務、CAT-P01 首次 API 延遲目標。正式資料的分類寫入由使用者日常決定；已驗真實瀏覽／Excel parity，寫入／rollback 由隔離測試覆蓋。下方保留驗收規格，不能僅因自動測試通過就把未驗證項目勾掉。

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

若以后要 AI 分类，只能作为另外授權的 opt-in 建議：發送最小且去識別的商家描述，不發送金額、日期、帳戶、銀行或完整歷史。使用者確認後預設保存為單筆 override，只有另行選擇記住商家才建立 rule。不得成为 V1 前置；完整後續邊界見第 18 節。

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

---

## 18. 逐筆自動分類研究與後續流程（規劃，未實作）

### 18.1 根因與唯讀實測

2026-09-30 重新讀取正式服務的 categories、category-rules、transactions 及 spending-by-category API：有 14 個類別，但 `books` 不存在；商家規則與有效單筆 override 均為 0。正式有效交易 18 筆；九月 TWD 的 6 筆支出全部解析為 `uncategorized`，分類淨額合計與 Dashboard 相符。這是分類來源缺失，不是沒有交易、圓環未載入或需要假資料。

`CategoryResolver.resolve()` 只有 override、normalized exact、contains、system semantic fallback；沒有內建商家知識或 AI 消費分類。交易契約包含描述及財務欄位，不提供商品清單或 MCC。舊 CSV 多數缺少 transaction_kind，不能靠分類規則猜測退款、利息或折抵的會計語意。

以上是當次觀察，不是永久固定資料；接手須重新唯讀查詢。原始商家、消費金額、帳單、郵件及測試證據只留本機 Git 忽略區，不加入公開文件。

### 18.2 目標、假設、核准 taxonomy 與授權

- 目標是每筆已確認 Finance 交易的消費用途：明確項目自動分類，模糊項目才確認；不能以一律人工整理或全部填滿類別冒充完成。
- 第一階段仍為一筆刷卡交易一個類別。單筆蝦皮或百貨交易可能包含多種商品；沒有訂單／發票資訊時，不推測明細，也不在本輪新增拆帳模型。
- 使用者已核准本文件第 4 節的 taxonomy 建议写入主规划：消费侧建议为饮食、日常采购、交通、购物、居家／水电通讯、家庭／育儿、医疗／健康、娱乐／数位服务、旅游、图书、课程／教育、保险、金融费用、未分类；另有收入、转帐／信用卡缴款两个非消费系统类别。
- 相较当前正式 0012，后续程式会需要新增 `books`、`insurance`，并调整部分 display name／语义边界；这次只批准文件与 Git merge，**不等于已批准直接 migration／部署正式数据库**。
- 分类按消费目的而非商家品牌；多用途商家／支付平台默认未知。A/B/C 信心等级与边界定义以第 4 节为准。
- 本节只完成研究及文件。實作、正式 migration／部署與雲端傳送交易描述均需後續明確授權；密碼規則 AI 的既有設定不構成消費資料傳送同意。

### 18.3 推薦分類流程與範圍

沿用 `finance/categories`，不修改 parser、交易事實、付款排除、退款符號、撤銷條件或 Excel ownership。建議純 resolver 延伸為 override > 使用者 exact > 使用者 contains > 已知 system semantic default > 經驗證的內建商家規則 > 未分類；新增規則不得覆蓋人工指定或把 payment 送入消費圖。

內建規則使用小而可追溯的版本化清單，不建立 Merchant master、embedding／模糊相似度平台或遠端商家查詢前置。完整比對、明確服務別名及受限關鍵字須有來源、反例與測試；保留店號，不能自動合併不同商家。`Uber Eats` 與叫車服務分開，不以 `UBER` 粗略判定交通；蝦皮、PChome、百貨、便利商店與支付平台不預設成飲食／圖書。這些例子是測試情境，不是對目前私人交易的認定。

AI 只產生建議，不列入正式有效分類；確認後使用既有 override／rule 路徑。預設只改單筆，「記住商家」另行選擇並先顯示跨月歷史非 override 的影響筆數、保留例外及未來套用範圍。沒有可靠原交易關聯時，也不替退款猜原消費類別。

本機規則清單的版本／內容 hash 必須參與 workbook fingerprint；停用內建規則後也須觸發同一個 Excel 更新邊界。不得在 Dashboard GET 或 resolver 中發送 AI 請求。

### 18.4 工作包與交接落點

| 工作包 | 修改落點與步驟 | 驗收／停止條件 |
| --- | --- | --- |
| A1 基準與樣本 | 唯讀盤點既有交易，定義 taxonomy；在本機建立經人工標註的三銀行描述樣本及混合商家反例，區分分類與會計語意缺口 | 記錄样本數與正確答案／資訊不足理由；沒有來源就不判定真實商品；不改正式帳本 |
| A2 本機自動分類 | 檢查最新 Alembic head，再以新 migration 加 `books`／`insurance`、调整核准 display names 並保留既有引用；延伸 `domain.py`／`service.py`、A/B/C 本機規則清單與 Donut 未分類保留槽位，API source 契約與 Excel fingerprint 同步 | seed 冪等、upgrade／rollback 副本驗證；manual 優先、停用安全 fallback、穩定規則衝突、無 N+1；多用途商家與支付平台未知保持未分類；Donut 最多 6 slices 且未分類不被聚合掉 |
| A3 逐筆整理 UI | 調整 `UncategorizedReview.tsx`／`CategoryPicker.tsx`：從商家進入逐筆，預設 transaction scope，顯示建議理由、記住商家影響預覽及批次確認 | 同商家可同時有飲食／圖書；寫入原子、失敗 rollback、過期預覽重查；手機／鍵盤操作與原 drill-down 不退化 |
| A4 可選 AI 建議 | 只有取得雲端用途同意後才加小型 suggestion port／provider adapter；輸出限制 active category code 或 unknown，驗證 JSON schema，快取依描述摘要／taxonomy／provider 版本失效 | AI 關閉／離線仍可用；新 profile／模型／規則變更使舊建議失效；429／timeout 有界重試，無付費 fallback、無 PII／全文；不 eval、不執行模型指令 |
| A5 既有資料整理 | 先產生分類與影響預覽；核准後只透過分類資料或讀取投影套用，更新 Donut／明細／owned Excel | 交易 ID／日期／金額／來源／kind／row_hash／Statement 全不變；重跑冪等、人工例外保留、Web／API／Excel 全相符 |
| A6 交付 | 每步 focused tests／build／更新 TASKS、HANDOFF；完成時 full suite、production build、桌面／320px／390px，以及當次三銀行真實 Gmail 驗收 | 每家新下載、來源密碼提示、解鎖、完整解析／核對及冪等均 PASS；入帳另依核准隔離流程，不自動 confirm 正式草稿 |

推薦先做 A1-A3；以真實未知樣本的數量與種類決定是否需要 A4，不把安裝 AI runtime 或建立通用 provider 平台當前置。本次沒有勾選任何 A1-A6 實作完成項目。

### 18.5 新增測試矩陣與品質報告

| ID | 必測案例 | Expected |
| --- | --- | --- |
| AUTO-01 | 全半形、空白、中文／英文別名、店號及規則衝突 | deterministic；不過度合併或因順序而改分類 |
| AUTO-02 | 叫車與外送、書籍與課程、混合商家／支付平台 | 明確服務可區分；未知／多用途不硬猜 |
| AUTO-03 | 同商家多種用途、人工例外、停用類別／內建規則 | 只改單筆預設；manual 不被自動或批次流程覆蓋；影響預覽與實際一致 |
| AUTO-04 | 舊 CSV 缺 kind、payment、refund、interest、跨月／多幣別 | 沿用會計語意，不猜日期或金額；分類只改歸組、合計不變 |
| AUTO-05 | override／規則／字典版本／名稱變更，Excel 佔用與外部修改 | Web／API／Excel parity，fingerprint 更新；保留 ownership／hash／原子替換與錯誤可見性 |
| AUTO-06 | 模型未知 code、格式錯誤、prompt injection、429／timeout、未同意雲端 | 安全拒絕／unknown；只處理資料，不接受模型指令；無外部請求或未授權保存 |
| AUTO-07 | 快速切月份／幣別、stale 建議、批次半途失敗、重複確認 | 舊回應／預覽不得覆蓋新狀態；原子寫入或完整 rollback，重跑不複製 |
| AUTO-08 | 撤銷／恢復、重分析、備份還原及字典停用 | 沿用原 identity／override；新 effective category 與 Excel 一致 |
| AUTO-09 | 核准 taxonomy 邊界：交通/旅遊、飲食/日常採買、圖書/教育、保險/金融費用、娛樂/數位服務 | 明確交易 deterministic；多用途商家／支付平台保持 unknown，不以粗略 contains 硬猜 |
| AUTO-10 | Donut 有 7+ 正向類且含未分類 | 最多 6 slices；未分類固定可見，最高 4 個已分類 + 未分類 + 其餘類別；金额守恒、颜色稳定 |

報告分開列自動分類 precision（自動採用中正確筆數／人工核對的自動採用筆數）、coverage（自動分類筆數／可分類消費筆數）、待確認率、各類別／銀行的樣本量與錯誤原因。未知不是成功，也不是一定要消除的錯誤；不得把人工確認混進自動 precision，或把模型自報 confidence 當準確率。先使用未參與規則調整的盲測，再決定可自動採用的規則範圍；目前尚無自動分类品質結果。

### 18.6 研究來源、取捨與回退

- [Visa Merchant Data Standards Manual](https://usa.visa.com/content/dam/VCOM/download/merchants/visa-merchant-data-standards-manual.pdf)（2026-04，2026-09-30 查閱）：MCC 描述主要商業活動，不是商品清單。因此不能用 MCC 或商城名稱保證實際購買項目；目前契約也未提供 MCC，不能憑空新增或作交付前置。
- [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs)（2026-09-30 查閱）：支援模型可限制 JSON schema；推論上這只保證格式，不能保證消費用途正確。實作前再查模型支援、額度與安全設定，不承諾永久免費，也不推定作用中 provider 已切換。
- [Ollama FAQ](https://docs.ollama.com/faq) 與 [Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)（2026-09-30 查閱）：可選本機、關閉 cloud 的部署方式，但本主機分類模型的效能／品質未實測；不自動安裝或改變既有 runtime。

雲端建議只傳經去識別的必要短描述；不傳身分證、生日、完整 mail／PDF、銀行／帳戶、日期、金額或消費歷史，key 仍在 SecretStore。原始描述視為不可信輸入；schema whitelist 與程式驗證限制输出，不允許模型更改交易、呼叫工具或生成可執行規則。

回退先停用新增自動規則／provider，保留人工 override、原始帳本與來源，透過同一投影更新 Excel。schema rollback 只對成對備份與相容程式副本演練，正式回退另取授權；不能刪分類引用、reset 工作樹或清空 DB 來恢復。
