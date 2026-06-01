# 🌿 Smart Budget

Gamified eco-finance tracker with AI spending analysis, carbon footprint tracking, and ESG scoring.

## Live Demo
[smart-budget-production-42d1.up.railway.app](https://smart-budget-production-42d1.up.railway.app/)

---

## 🚀 Deploy to Railway (update existing project)

### Option A — GitHub (recommended)

1. Push this folder to your GitHub repo:
   ```bash
   git init
   git add .
   git commit -m "feat: add AI spending analysis"
   git remote add origin https://github.com/YOUR_USERNAME/smart-budget.git
   git push -u origin main
   ```

2. In Railway dashboard → your project → **Settings → Source** → connect the repo.  
   Railway will auto-deploy on every push.

### Option B — Railway CLI

```bash
npm install -g @railway/cli   # install once
railway login
railway link                  # link to your existing project
railway up                    # deploy
```

---

## ⚙️ Environment Variables (Railway Dashboard)

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Optional | Enables Claude AI analysis. Without it, falls back to rule-based reports. |
| `DATABASE_URL` | Auto-set | Railway PostgreSQL plugin sets this automatically. |

To set in Railway:  
**Project → Variables → + New Variable**

---

## 🏃 Run Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 3. Run
python app.py
# → http://localhost:5000
```

---

## 📁 Project Structure

```
smart-budget/
├── app.py                # Flask backend + all API routes
├── templates/
│   └── index.html        # Single-page frontend (Tailwind + Chart.js)
├── requirements.txt
├── Procfile              # For Railway / Heroku
├── railway.toml          # Railway build config
└── .env.example          # Environment variable template
```

## ✨ Features

- **Dashboard** — Monthly overview, eco health bar, budget progress
- **AI Analysis** — Claude-powered personalised spending report
- **Analytics** — Spending trends, category charts, carbon footprint, emotion breakdown, anomaly detection
- **History** — Searchable, filterable transaction list
- **Eco Profile** — Earth companion, gamification ranks, budget manager
- **Carbon Tracking** — GHG Protocol Scope 3 spend-based methodology
