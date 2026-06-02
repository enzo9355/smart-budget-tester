# Smart Budget — Project Overview / 專案說明

> **NLP Final Project · 2026-06-04**
> Live Demo: https://smart-budget-tester.onrender.com

---

## 1. Motivation & Purpose / 動機與目的

**EN:**
Managing personal finances is something most university students know they should do — but almost nobody actually sticks with it. Traditional budgeting apps demand manual data entry, rigid category systems, and offer no feedback beyond numbers. More importantly, they treat every purchase as financially equivalent, ignoring the fact that *how* we spend money has real-world environmental consequences.

We built Smart Budget to make daily financial tracking genuinely motivating. By combining AI-powered natural language input, a carbon footprint layer tied to every transaction, and a gamification system that reacts visually to spending behavior, we aimed to turn a chore into something that feels like a daily wellness habit — not a corporate spreadsheet.

**ZH:**
管理個人財務是大多數大學生都「知道該做」但幾乎沒人真正堅持的事。傳統記帳 App 需要手動輸入、僵化的類別系統，除了數字外幾乎沒有任何回饋。更重要的是，它們把每一筆消費當作財務上等價的行為，忽略了「如何花錢」在現實世界中有真實的環境影響。

我們打造 Smart Budget，目的是讓日常財務追蹤真正令人有動力持續。透過 AI 自然語言輸入、與每筆交易連結的碳足跡計算、以及對消費行為即時視覺反應的遊戲化系統，我們希望將記帳從一件苦差事，變成類似每日健康習慣的體驗——而非一個企業試算表。

---

## 2. The Problem / 問題陳述

**EN:**
Three specific pain points guided our design:

1. **Friction kills habits.** If it takes more than 5 seconds to log a purchase, most users quit within a week. We needed input that was as fast as sending a message.
2. **Numbers without context are meaningless.** Seeing "NT$3,500 spent on Food" tells you nothing about whether that's good or bad. You need comparison, trend, and emotional context.
3. **Sustainability is invisible in personal finance tools.** A student who takes a taxi every day instead of the MRT is spending roughly the same money, but generating 5× the carbon. No existing student-targeted budgeting tool surfaces this.

**ZH:**
三個具體痛點引導了我們的設計：

1. **摩擦力殺死習慣。** 如果記一筆消費要超過 5 秒，大多數使用者一週內就會放棄。我們需要快如發訊息的輸入方式。
2. **沒有情境的數字毫無意義。** 看到「餐飲花了 3,500 元」什麼都說明不了。你需要比較、趨勢和情緒脈絡。
3. **永續性在個人財務工具中是隱形的。** 一個每天搭計程車而非 MRT 的學生，花費差不多，但產生的碳排放是 5 倍。目前沒有任何針對學生的記帳工具呈現這一點。

---

## 3. Technical Architecture / 技術架構

**EN:**

| Layer | Technology | Role |
|---|---|---|
| Frontend | HTML + Tailwind CSS + Vanilla JS + Chart.js | Single-page app, Material Design 3 dark theme, responsive (desktop sidebar + mobile bottom nav) |
| Backend | Python Flask + SQLAlchemy | 24 REST API endpoints, business logic, carbon calculations |
| Database | SQLite (dev) / PostgreSQL (production) | 4 models: Expense, Budget, MonthlySummary, Setting |
| AI Layer | Anthropic Claude API (`claude-sonnet-4-20250514`) | NLP parsing, monthly summaries, spending analysis, anomaly detection |
| Deployment | Render + Railway | Auto-deploy on every push to `main`, self-ping to prevent free-tier spin-down |

**ZH:**

| 層級 | 技術 | 角色 |
|---|---|---|
| 前端 | HTML + Tailwind CSS + Vanilla JS + Chart.js | 單頁應用，Material Design 3 深色主題，響應式（桌面側邊欄 + 手機底部導覽） |
| 後端 | Python Flask + SQLAlchemy | 24 個 REST API 端點、業務邏輯、碳排計算 |
| 資料庫 | SQLite（開發）/ PostgreSQL（正式環境） | 4 個模型：Expense、Budget、MonthlySummary、Setting |
| AI 層 | Anthropic Claude API（`claude-sonnet-4-20250514`） | NLP 解析、月報生成、消費分析、異常偵測 |
| 部署 | Render + Railway | 每次 push 自動重新部署，self-ping 防止免費版休眠 |

---

## 4. Key Features / 核心功能

### 4.1 Natural Language Transaction Entry / 自然語言記帳

**EN:**
Instead of filling out a form, users describe their spending in plain English or Chinese: *"Lunch at MOS Burger 180, feeling stressed."* Claude extracts the amount, category, date, and emotional tone, then estimates the carbon footprint automatically. A rule-based fallback parser activates if the Claude API is unavailable, ensuring the app never fails silently.

**ZH:**
使用者不需要填表單，而是用自然語言描述消費：「MOS 漢堡午餐 180，壓力好大。」Claude 提取金額、類別、日期和情緒語氣，並自動估算碳足跡。若 Claude API 無法使用，規則型 fallback 解析器會自動啟用，確保 App 不會無聲地失敗。

---

### 4.2 Carbon Footprint Tracking / 碳足跡追蹤

**EN:**
Every transaction automatically computes a carbon footprint using the **GHG Protocol Scope 3 spend-based methodology** — the same framework used by corporations to report Scope 3 emissions. The formula is:

```
carbon_kg = amount (TWD) × emission_factor (kg CO₂e / TWD)
```

Emission factors for 24 categories are derived from EU consumption emission factor data, converted at 1 EUR ≈ 35 TWD. Electricity uses a specialized formula based on Taiwan's average electricity price (3.5 TWD/kWh) and the Taiwan EPA grid emission factor (0.495 kg CO₂e/kWh).

Users can see their monthly carbon footprint compared against the Taiwan average (750 kg CO₂e/month), along with equivalence labels ("= X km of driving" or "= X trees needed per year").

**ZH:**
每筆交易自動計算碳足跡，使用 **GHG Protocol Scope 3 消費支出法**——與企業申報 Scope 3 排放所用的相同框架。計算公式為：

```
carbon_kg = 金額 (TWD) × 排放因子 (kg CO₂e / TWD)
```

24 個類別的排放因子來自歐盟消費排放因子資料，以 1 EUR ≈ 35 TWD 換算。電費使用特殊公式，基於台灣平均電價（3.5 TWD/kWh）和台灣 EPA 電網排放因子（0.495 kg CO₂e/kWh）。

使用者可看到月碳排放與台灣平均值（750 kg CO₂e/月）的比較，以及等價換算標籤（「= X 公里行駛」或「= 每年需要 X 棵樹」）。

---

### 4.3 Gamification System / 遊戲化系統

**EN:**
Gamification in Smart Budget is designed around **positive reinforcement, not guilt**. The Earth Companion is the central visual element — a planet emoji that changes its animation and glow color based on a composite eco-score derived from monthly carbon, the ratio of high-emission vs. low-emission category spending, and the user's daily tracking streak.

The rank system (Seedling → Sprout → Guardian → Earth Protector) uses eco points that accumulate from low-carbon transactions and decrease for high-carbon ones. When a user crosses a rank threshold, a celebration modal fires with confetti — a deliberate "wow moment" designed to make sustainable spending feel rewarding.

**ZH:**
Smart Budget 的遊戲化設計圍繞**正向強化而非罪惡感**。地球夥伴是核心視覺元素——一個根據複合環保評分改變動畫和光暈顏色的地球表情符號，評分由月碳排量、高/低碳類別消費比例和每日記帳 Streak 共同決定。

段位系統（🌱 幼苗 → 🌿 嫩芽 → 🌳 守護者 → 🌍 地球守護者）使用從低碳交易累積、高碳交易扣減的環保點數。當使用者跨越段位閾值時，觸發帶彩紙的慶祝彈窗——這是刻意設計的「驚喜時刻」，讓永續消費行為感覺有獎勵。

---

### 4.4 Claude API Integration / Claude API 整合

**EN:**
The project uses Claude in four distinct ways, each with a carefully designed prompt and a rule-based fallback:

| Use Case | Model | Max Tokens | Purpose |
|---|---|---|---|
| Transaction parsing | claude-sonnet-4-20250514 | 256 | Extract structured JSON from free-text descriptions |
| Monthly summary | claude-sonnet-4-20250514 | 300 | Generate 3-4 sentence personalized finance + eco narrative |
| AI spending analysis | claude-sonnet-4-20250514 | 300 | Produce a warm, coach-style monthly report with eco tips |
| Anomaly detection | claude-sonnet-4-20250514 | 400 | Compare current vs. previous month, flag unusual patterns |

All prompts are designed to output **structured JSON or bounded prose**, making the responses predictable and safe to parse. The system never crashes due to API failures — every Claude call has a complete rule-based fallback.

**ZH:**
本專案以四種不同方式使用 Claude，每種均有精心設計的 prompt 和規則型 fallback：

| 使用情境 | 模型 | Max Tokens | 目的 |
|---|---|---|---|
| 交易解析 | claude-sonnet-4-20250514 | 256 | 從自由文字描述提取結構化 JSON |
| 月報生成 | claude-sonnet-4-20250514 | 300 | 生成 3-4 句個人化財務 + 環保敘述 |
| AI 消費分析 | claude-sonnet-4-20250514 | 300 | 以教練風格產出含環保建議的月度報告 |
| 異常偵測 | claude-sonnet-4-20250514 | 400 | 比較當月 vs 上月，標記異常模式 |

所有 prompt 均設計為輸出**結構化 JSON 或有邊界的散文**，使回應可預測且易於解析。系統不會因 API 失敗而崩潰——每個 Claude 呼叫都有完整的規則型 fallback。

---

## 5. Design Decisions / 設計決策說明

**EN:**

**Why single-user (no authentication)?**
This is a deliberate MVP decision. Authentication adds significant complexity (session management, password hashing, CSRF protection) without contributing to the core research questions of the project: *Can NLP make financial tracking frictionless? Does combining ESG data with gamification change spending behavior?* A future version with multi-user support is listed in Future Ideas.

**Why spend-based carbon rather than product-level data?**
Product-level carbon data (scanning a barcode to get exact CO₂e per item) requires proprietary databases that are either expensive or inaccurate in Taiwan's market. The GHG Protocol Scope 3 spend-based methodology is the industry standard for corporate sustainability reporting and provides reasonable estimates at the category level, which is sufficient for behavioral nudging purposes.

**Why Tailwind CDN rather than a bundled framework?**
For a single-developer academic project, build pipeline complexity (webpack, vite, npm scripts) adds maintenance overhead without meaningful benefit. The CDN approach keeps the project self-contained in two files (`app.py` + `index.html`), making it trivial to inspect, deploy, and demonstrate.

**ZH:**

**為什麼是單用戶（無驗證）？**
這是有意識的 MVP 決策。驗證增加了大量複雜性（session 管理、密碼雜湊、CSRF 保護），卻無助於本專案的核心研究問題：*NLP 能否讓財務追蹤變得無摩擦？將 ESG 資料與遊戲化結合是否能改變消費行為？* 多用戶支援版本已列入未來方向。

**為什麼使用支出型碳排而非產品級資料？**
產品級碳排資料（掃描條碼獲得每件商品的精確 CO₂e）需要昂貴或在台灣市場不準確的專有資料庫。GHG Protocol Scope 3 消費支出法是企業永續報告的行業標準，在類別層級提供合理估算，對行為引導目的而言已足夠。

**為什麼使用 Tailwind CDN 而非打包框架？**
對於單人學術專案，建置管線複雜度（webpack、vite、npm scripts）增加維護負擔而無實質效益。CDN 方式讓專案只包含兩個檔案（`app.py` + `index.html`），極易於檢查、部署和展示。

---

## 6. Work Allocation / 工作分工

| Responsibility | Team Member A | Team Member B |
|---|---|---|
| （請填寫） | | |
| （請填寫） | | |
| （請填寫） | | |
| （請填寫） | | |

---

## 7. Future Ideas / 未來方向

**EN:**

1. **Multi-user authentication** — Flask-Login + bcrypt, each user has isolated data. Transforms this from a personal tool into a shareable platform.
2. **PWA (Progressive Web App)** — Service Worker for offline logging and push notifications when approaching budget limits.
3. **Community carbon comparison** — Anonymized comparison of carbon footprint against peers in the same age/region group, with leaderboard mechanics.
4. **Open Banking / payment integration** — Auto-import transactions from LINE Pay, JKoPay, and credit card statements via Open Banking APIs. Zero manual entry.
5. **Agentic spending coach** — Using Claude's agentic capabilities to proactively monitor spending patterns, send weekly personalized recommendations, and suggest specific behavioral interventions.

**ZH:**

1. **多用戶驗證** — Flask-Login + bcrypt，每位用戶有獨立資料。將工具從個人工具升級為可分享平台。
2. **PWA 行動 App** — Service Worker 支援離線記帳，接近預算上限時發送推播通知。
3. **社群碳排比較** — 與同年齡/地區群體的匿名碳足跡比較，加入排行榜機制。
4. **Open Banking / 支付串接** — 透過 Open Banking API 自動匯入 LINE Pay、街口支付和信用卡帳單。零手動輸入。
5. **Agentic 消費教練** — 利用 Claude 的 Agentic 能力主動監控消費模式，每週發送個人化建議，並提出具體行為改變建議。

---

## 8. Carbon Emission Factor Reference / 碳排放因子參考

**EN:** Factors below are in kg CO₂e per TWD spent, derived from EU EXIOBASE consumption emission data converted at 1 EUR ≈ 35 TWD. Taiwan EPA grid factor: 0.495 kg CO₂e/kWh.

| Category | Factor | Category | Factor |
|---|---|---|---|
| Flight ✈️ | 0.280 | Groceries 🥦 | 0.010 |
| Car & Fuel 🚗 | 0.120 | Books & Stationery 📚 | 0.008 |
| Gas 🔥 | 0.110 | Education 🎓 | 0.008 |
| Meat & Dairy 🥩 | 0.090 | Water 💧 | 0.005 |
| Electronics 📱 | 0.100 | Public Transport 🚌 | 0.012 |
| Fashion 👗 | 0.080 | Streaming & Software 📺 | 0.015 |
| Seafood 🐟 | 0.070 | Healthcare 🏥 | 0.025 |
| Taxi & Rideshare 🚕 | 0.060 | Entertainment 🎬 | 0.030 |
| Restaurant 🍽️ | 0.055 | Rent & Housing 🏘️ | 0.020 |
| Cafe & Drinks ☕ | 0.040 | Insurance 🛡️ | 0.010 |
| Electricity ⚡ | (special) | Other 📦 | 0.040 |

---

*This project was built as a final project for an NLP course. All Claude API prompts are hardcoded in `app.py` and documented in the presentation slides.*
