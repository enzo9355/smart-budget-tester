"""
Smart Budget — Gamified Eco-Finance Cultivation App
Flask backend with carbon footprint tracking, ESG scoring, and gamification.
nlp_service replaced by inline Claude API (anthropic SDK).
"""
import os
import csv
import io
import json
import time
import threading
import urllib.request
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import Flask, jsonify, request, render_template, Response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///budget.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ── Anthropic Claude client (optional) ──────────────────────────────────────
_anthropic_client = None

def get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                _anthropic_client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                pass
    return _anthropic_client


# ── Carbon Categories & Emission Factors ─────────────────────────────────────
CARBON_CATEGORIES = {
    "Car & Fuel":           {"factor": 0.120, "icon": "🚗", "group": "Transport"},
    "Public Transport":     {"factor": 0.012, "icon": "🚌", "group": "Transport"},
    "Taxi & Rideshare":     {"factor": 0.060, "icon": "🚕", "group": "Transport"},
    "Flight":               {"factor": 0.280, "icon": "✈️", "group": "Transport"},
    "Meat & Dairy":         {"factor": 0.090, "icon": "🥩", "group": "Food"},
    "Groceries":            {"factor": 0.010, "icon": "🥦", "group": "Food"},
    "Restaurant":           {"factor": 0.055, "icon": "🍽️", "group": "Food"},
    "Cafe & Drinks":        {"factor": 0.040, "icon": "☕", "group": "Food"},
    "Seafood":              {"factor": 0.070, "icon": "🐟", "group": "Food"},
    "Fashion":              {"factor": 0.080, "icon": "👗", "group": "Shopping"},
    "Electronics":          {"factor": 0.100, "icon": "📱", "group": "Shopping"},
    "Books & Stationery":   {"factor": 0.008, "icon": "📚", "group": "Shopping"},
    "Beauty & Personal":    {"factor": 0.045, "icon": "💄", "group": "Shopping"},
    "Furniture & Home":     {"factor": 0.060, "icon": "🏠", "group": "Shopping"},
    "Electricity":          {"factor": 0.095, "icon": "⚡", "group": "Utilities"},
    "Water":                {"factor": 0.005, "icon": "💧", "group": "Utilities"},
    "Gas":                  {"factor": 0.110, "icon": "🔥", "group": "Utilities"},
    "Rent & Housing":       {"factor": 0.020, "icon": "🏘️", "group": "Housing"},
    "Streaming & Software": {"factor": 0.015, "icon": "📺", "group": "Digital"},
    "Education":            {"factor": 0.008, "icon": "🎓", "group": "Education"},
    "Healthcare":           {"factor": 0.025, "icon": "🏥", "group": "Health"},
    "Entertainment":        {"factor": 0.030, "icon": "🎬", "group": "Entertainment"},
    "Insurance":            {"factor": 0.010, "icon": "🛡️", "group": "Finance"},
    "Other":                {"factor": 0.040, "icon": "📦", "group": "Other"},
}

CATEGORIES = list(CARBON_CATEGORIES.keys())

LEGACY_CATEGORY_MAP = {
    "Food & Dining": "Restaurant",
    "Transport":     "Public Transport",
    "Shopping":      "Fashion",
    "Health":        "Healthcare",
    "Utilities":     "Electricity",
}


def calculate_carbon(amount, category):
    mapped = LEGACY_CATEGORY_MAP.get(category, category)
    if mapped == "Electricity":
        kwh = amount / 3.5
        return round(kwh * 0.495, 3)
    info = CARBON_CATEGORIES.get(mapped, CARBON_CATEGORIES["Other"])
    return round(amount * info["factor"], 3)


def get_earth_state(monthly_carbon):
    if monthly_carbon < 300:
        return {"state": "thriving", "label": "Thriving", "color": "#4ade80",
                "message": "Your planet is thriving! Keep it up!"}
    elif monthly_carbon < 600:
        return {"state": "neutral", "label": "Neutral", "color": "#fbbf24",
                "message": "Your planet is doing okay. Small changes help!"}
    elif monthly_carbon < 900:
        return {"state": "stressed", "label": "Stressed", "color": "#fb923c",
                "message": "Your planet needs a break. Try greener choices!"}
    else:
        return {"state": "critical", "label": "Critical", "color": "#94a3b8",
                "message": "Your planet is struggling. Every eco-choice matters!"}


def get_eco_rank(score):
    if score >= 300:
        return {"rank": "Earth Protector", "emoji": "🌍", "next_at": None}
    elif score >= 150:
        return {"rank": "Guardian", "emoji": "🌳", "next_at": 300}
    elif score >= 50:
        return {"rank": "Sprout", "emoji": "🌿", "next_at": 150}
    else:
        return {"rank": "Seedling", "emoji": "🌱", "next_at": 50}


# ── NLP helpers (Claude API) ─────────────────────────────────────────────────

def parse_expense(text, today_str):
    """Parse natural language expense description using Claude API."""
    client = get_anthropic()
    if not client:
        return _rule_based_parse(text, today_str)

    categories_list = ", ".join(CATEGORIES)
    prompt = f"""Parse this expense description into structured data. Today is {today_str}.

Description: "{text}"

Return ONLY valid JSON (no markdown, no explanation) with these fields:
- amount: number or null
- category: one of [{categories_list}] or null
- date: ISO date string YYYY-MM-DD or null
- description: clean short description string
- emotion: "positive", "negative", or "neutral"

Example: {{"amount": 180, "category": "Restaurant", "date": "{today_str}", "description": "Lunch at MOS Burger", "emotion": "negative"}}"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception:
        return _rule_based_parse(text, today_str)


def _rule_based_parse(text, today_str):
    """Fallback rule-based parser when Claude API is unavailable."""
    import re
    result = {"amount": None, "category": "Other", "date": today_str,
              "description": text, "emotion": "neutral"}
    # Extract amount
    m = re.search(r'\b(\d+(?:\.\d+)?)\b', text)
    if m:
        result["amount"] = float(m.group(1))
    # Keyword → category mapping
    kw_map = {
        "lunch|dinner|restaurant|burger|pizza|meal|eat|food|noodle": "Restaurant",
        "coffee|cafe|tea|bubble|drink|boba": "Cafe & Drinks",
        "bus|mrt|metro|train|transit|ubike": "Public Transport",
        "taxi|uber|lyft|grab|rideshare": "Taxi & Rideshare",
        "flight|air|plane|ticket": "Flight",
        "beef|pork|chicken|meat|dairy|milk|cheese": "Meat & Dairy",
        "grocery|supermarket|market|vegetable|fruit": "Groceries",
        "cloth|shirt|shoe|fashion|outfit|dress": "Fashion",
        "phone|laptop|computer|electronic|gadget": "Electronics",
        "book|stationery|pen|notebook": "Books & Stationery",
        "electric|electricity|power|bill": "Electricity",
        "gym|hospital|clinic|medicine|health|doctor": "Healthcare",
        "movie|cinema|concert|entertainment|game": "Entertainment",
        "school|course|textbook|tuition|education": "Education",
        "rent|housing|apartment": "Rent & Housing",
        "netflix|spotify|streaming|subscription|software": "Streaming & Software",
        "gas|petrol|fuel|car": "Car & Fuel",
    }
    t_lower = text.lower()
    for pattern, cat in kw_map.items():
        if re.search(pattern, t_lower):
            result["category"] = cat
            break
    # Detect emotion
    if re.search(r'stress|anxious|sad|bad|upset|angry|disappoint|regret|wrong', t_lower):
        result["emotion"] = "negative"
    elif re.search(r'happy|great|excit|celebrat|fun|love|amazing|wonderful|joy', t_lower):
        result["emotion"] = "positive"
    return result


def generate_monthly_summary(month, stats):
    """Generate AI monthly summary using Claude API."""
    client = get_anthropic()
    if not client:
        return _rule_based_summary(month, stats)

    prompt = f"""You are a friendly personal finance assistant with an eco-focus.
Write a concise 3-4 sentence monthly spending summary for {month}.

Data:
- Total spent: TWD {stats['total']:.0f}
- Transactions: {stats['count']}
- Top category: {stats['top_category']}
- Total carbon footprint: {stats['total_carbon']} kg CO₂e
- Spending by category: {json.dumps(stats['by_category'], ensure_ascii=False)}
- Emotion breakdown: {json.dumps({k: v['count'] for k, v in stats['by_emotion'].items()}, ensure_ascii=False)}

Be encouraging, mention eco impact, and suggest one actionable improvement. Keep it warm and personal."""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text.strip()
    except Exception:
        return _rule_based_summary(month, stats)


def _rule_based_summary(month, stats):
    top = stats.get("top_category", "Other")
    total = stats.get("total", 0)
    carbon = stats.get("total_carbon", 0)
    count = stats.get("count", 0)
    eco_note = ("Great job keeping your carbon footprint low this month! 🌿"
                if carbon < 300 else
                "Consider swapping some high-carbon choices for greener alternatives. 🌱")
    return (f"In {month}, you made {count} transactions totalling TWD {total:.0f}. "
            f"Your biggest spending area was {top}. "
            f"Your carbon footprint was {carbon:.1f} kg CO₂e. "
            f"{eco_note}")


def detect_anomalies_nlp(cur, prv):
    """Detect spending anomalies using Claude API or rule-based fallback."""
    client = get_anthropic()
    if not client:
        return _rule_based_anomalies(cur, prv)

    prompt = f"""Analyze these monthly spending patterns and identify anomalies.

Current month: {json.dumps(cur, ensure_ascii=False)}
Previous month: {json.dumps(prv, ensure_ascii=False)}

Return ONLY valid JSON (no markdown) with:
{{
  "anomalies": [
    {{"category": "string", "message": "string", "severity": "low|medium|high"}}
  ],
  "summary": "one sentence overall assessment"
}}

Focus on: categories with >50% increase, unusually large single transactions, new categories."""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception:
        return _rule_based_anomalies(cur, prv)


def _rule_based_anomalies(cur, prv):
    anomalies = []
    cur_cat = cur.get("by_category", {})
    prv_cat = prv.get("by_category", {})
    for cat, amount in cur_cat.items():
        prev_amt = prv_cat.get(cat, 0)
        if prev_amt > 0:
            pct = (amount - prev_amt) / prev_amt * 100
            if pct > 100:
                anomalies.append({"category": cat,
                                   "message": f"Spending up {pct:.0f}% vs last month (TWD {amount:.0f} vs {prev_amt:.0f})",
                                   "severity": "high" if pct > 200 else "medium"})
            elif pct > 50:
                anomalies.append({"category": cat,
                                   "message": f"Spending up {pct:.0f}% vs last month",
                                   "severity": "low"})
        elif amount > 500:
            anomalies.append({"category": cat,
                               "message": f"New category this month: TWD {amount:.0f}",
                               "severity": "low"})
    if cur.get("max_single", 0) > 2000:
        anomalies.append({"category": "Single Transaction",
                           "message": f"Large single transaction: TWD {cur['max_single']:.0f}",
                           "severity": "medium"})
    summary = (f"Found {len(anomalies)} anomaly(ies) this month."
               if anomalies else "Spending patterns look normal this month.")
    return {"anomalies": anomalies, "summary": summary}


# ── Models ──────────────────────────────────────────────────────────────────

class Expense(db.Model):
    __tablename__ = "expenses"
    id           = db.Column(db.Integer, primary_key=True)
    amount       = db.Column(db.Float,   nullable=False)
    category     = db.Column(db.String(50), nullable=False, default="Other")
    description  = db.Column(db.Text)
    emotion      = db.Column(db.String(20), default="neutral")
    emotion_note = db.Column(db.Text)
    context_tag  = db.Column(db.String(50))
    carbon_kg    = db.Column(db.Float, default=0.0)
    date         = db.Column(db.Date, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":           self.id,
            "amount":       self.amount,
            "category":     self.category,
            "description":  self.description,
            "emotion":      self.emotion,
            "emotion_note": self.emotion_note,
            "context_tag":  self.context_tag,
            "carbon_kg":    self.carbon_kg or 0.0,
            "date":         self.date.isoformat(),
            "created_at":   self.created_at.isoformat(),
        }


class Budget(db.Model):
    __tablename__ = "budgets"
    id            = db.Column(db.Integer, primary_key=True)
    category      = db.Column(db.String(50), unique=True, nullable=False)
    monthly_limit = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {"id": self.id, "category": self.category, "monthly_limit": self.monthly_limit}


class MonthlySummary(db.Model):
    __tablename__ = "monthly_summaries"
    id           = db.Column(db.Integer, primary_key=True)
    year_month   = db.Column(db.String(7), nullable=False)
    summary_text = db.Column(db.Text)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "year_month": self.year_month,
            "summary_text": self.summary_text,
            "generated_at": self.generated_at.isoformat(),
        }


class Setting(db.Model):
    __tablename__ = "settings"
    id    = db.Column(db.Integer, primary_key=True)
    key   = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)


# ── Helpers ──────────────────────────────────────────────────────────────────

def month_range(month_str):
    year, m = map(int, month_str.split("-"))
    start = date(year, m, 1)
    end   = date(year + 1, 1, 1) if m == 12 else date(year, m + 1, 1)
    return start, end


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "ai_enabled": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ai_provider": "claude" if os.environ.get("ANTHROPIC_API_KEY") else None
    })


@app.route("/api/categories")
def get_categories():
    return jsonify(CARBON_CATEGORIES)


# ── Monthly Income Setting ───────────────────────────────────────────────────

@app.route("/api/settings/income", methods=["GET"])
def get_income():
    s = Setting.query.filter_by(key="monthly_income").first()
    return jsonify({"monthly_income": float(s.value) if s else 0})


@app.route("/api/settings/income", methods=["POST"])
def set_income():
    data   = request.json or {}
    amount = float(data.get("monthly_income", 0))
    s = Setting.query.filter_by(key="monthly_income").first()
    if s:
        s.value = str(amount)
    else:
        s = Setting(key="monthly_income", value=str(amount))
        db.session.add(s)
    db.session.commit()
    return jsonify({"monthly_income": float(s.value)})


# ── Expenses ─────────────────────────────────────────────────────────────────

@app.route("/api/expenses", methods=["POST"])
def create_expense():
    data = request.json or {}
    try:
        expense_date = (
            datetime.strptime(data["date"], "%Y-%m-%d").date()
            if data.get("date") else date.today()
        )
        ctx    = data.get("context_tag")
        amount = float(data["amount"])
        category = data.get("category", "Other")

        if data.get("carbon_kg") is not None and data["carbon_kg"] != "":
            carbon = float(data["carbon_kg"])
        else:
            carbon = calculate_carbon(amount, category)

        expense = Expense(
            amount       = amount,
            category     = category,
            description  = data.get("description", ""),
            emotion      = data.get("emotion", "neutral"),
            emotion_note = data.get("emotion_note", ""),
            context_tag  = ctx if ctx and ctx != "none" else None,
            carbon_kg    = carbon,
            date         = expense_date,
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(expense.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    month = request.args.get("month")
    q = Expense.query
    if month:
        s, e = month_range(month)
        q = q.filter(Expense.date >= s, Expense.date < e)
    return jsonify([ex.to_dict() for ex in q.order_by(Expense.date.desc()).all()])


@app.route("/api/expenses/<int:eid>", methods=["DELETE"])
def delete_expense(eid):
    ex = db.session.get(Expense, eid)
    if not ex:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(ex)
    db.session.commit()
    return jsonify({"message": "Deleted"})


@app.route("/api/expenses/search")
def search_expenses():
    q        = request.args.get("q", "")
    category = request.args.get("category", "all")
    emotion  = request.args.get("emotion", "all")
    ctx_tag  = request.args.get("context_tag", "all")
    month    = request.args.get("month", "")

    query = Expense.query
    if q:
        query = query.filter(Expense.description.ilike(f"%{q}%"))
    if category and category != "all":
        query = query.filter(Expense.category == category)
    if emotion and emotion != "all":
        query = query.filter(Expense.emotion == emotion)
    if ctx_tag and ctx_tag != "all":
        query = query.filter(Expense.context_tag == ctx_tag)
    if month:
        s, e = month_range(month)
        query = query.filter(Expense.date >= s, Expense.date < e)

    return jsonify([ex.to_dict() for ex in query.order_by(Expense.date.desc()).all()])


# ── NLP Parse ────────────────────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def parse_route():
    text   = (request.json or {}).get("text", "")
    result = parse_expense(text, date.today().isoformat())
    if result.get("category"):
        result["category"] = LEGACY_CATEGORY_MAP.get(result["category"], result["category"])
    if result.get("amount") and result.get("category"):
        result["carbon_kg"] = calculate_carbon(float(result["amount"]), result["category"])
    return jsonify(result)


# ── Carbon Endpoints ─────────────────────────────────────────────────────────

@app.route("/api/carbon/estimate")
def carbon_estimate():
    amount   = float(request.args.get("amount", 0))
    category = request.args.get("category", "Other")
    return jsonify({"carbon_kg": calculate_carbon(amount, category)})


@app.route("/api/carbon/summary")
def carbon_summary():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    today_iso  = date.today().isoformat()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()

    by_category  = defaultdict(float)
    by_day       = defaultdict(float)
    total_today  = 0.0
    total_week   = 0.0
    total_month  = 0.0

    for ex in expenses:
        c = ex.carbon_kg or 0.0
        by_category[ex.category] += c
        by_day[ex.date.isoformat()] += c
        total_month += c
        if ex.date.isoformat() == today_iso:
            total_today += c
        if ex.date.isoformat() >= week_start:
            total_week += c

    driving_km   = round(total_month / 0.21, 1) if total_month > 0 else 0
    trees_needed = round(total_month / (21 / 12), 1) if total_month > 0 else 0

    return jsonify({
        "by_category":  dict(by_category),
        "by_day":       dict(by_day),
        "total_today":  round(total_today, 2),
        "total_week":   round(total_week, 2),
        "total_month":  round(total_month, 2),
        "equivalences": {
            "driving_km":   driving_km,
            "trees_needed": trees_needed,
        },
    })


@app.route("/api/carbon/eco-score")
def eco_score():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    score          = 0
    monthly_carbon = 0.0
    for ex in expenses:
        c = ex.carbon_kg or 0.0
        monthly_carbon += c
        if c < 0.05:
            score += 5
        elif c > 2.0:
            score -= 10
    score = max(score, 0)

    streak     = 0
    check_date = date.today()
    if not Expense.query.filter(Expense.date == check_date).first():
        check_date -= timedelta(days=1)
    while True:
        has_tx = Expense.query.filter(Expense.date == check_date).first()
        if has_tx:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    earth = get_earth_state(monthly_carbon)
    rank  = get_eco_rank(score)

    return jsonify({
        "eco_score":      score,
        "rank":           rank["rank"],
        "rank_emoji":     rank["emoji"],
        "next_rank_at":   rank["next_at"],
        "streak":         streak,
        "monthly_carbon": round(monthly_carbon, 2),
        "taiwan_avg":     750,
        "earth_state":    earth["state"],
        "earth_label":    earth["label"],
        "earth_color":    earth["color"],
        "earth_message":  earth["message"],
    })


# ── Budgets ──────────────────────────────────────────────────────────────────

@app.route("/api/budgets", methods=["POST"])
def set_budget():
    data     = request.json or {}
    category = data.get("category")
    limit    = data.get("monthly_limit")
    if not category or limit is None:
        return jsonify({"error": "category and monthly_limit required"}), 400

    budget = Budget.query.filter_by(category=category).first()
    if budget:
        budget.monthly_limit = float(limit)
    else:
        budget = Budget(category=category, monthly_limit=float(limit))
        db.session.add(budget)
    db.session.commit()
    return jsonify(budget.to_dict())


@app.route("/api/budgets/<int:bid>", methods=["DELETE"])
def delete_budget(bid):
    b = db.session.get(Budget, bid)
    if not b:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(b)
    db.session.commit()
    return jsonify({"message": "Deleted"})


@app.route("/api/budgets")
def get_budgets():
    month    = request.args.get("month", date.today().strftime("%Y-%m"))
    budgets  = Budget.query.all()
    s, e     = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    spent_by = defaultdict(float)
    for ex in expenses:
        spent_by[ex.category] += ex.amount

    result = []
    for b in budgets:
        d = b.to_dict()
        d["spent"]      = spent_by.get(b.category, 0.0)
        d["percentage"] = (d["spent"] / b.monthly_limit * 100) if b.monthly_limit > 0 else 0
        result.append(d)
    return jsonify(result)


# ── Monthly Summary ──────────────────────────────────────────────────────────

@app.route("/api/summary/<month>")
def get_summary(month):
    force  = request.args.get("force", "false") == "true"
    cached = (MonthlySummary.query
              .filter_by(year_month=month)
              .order_by(MonthlySummary.generated_at.desc())
              .first())
    if cached and not force:
        return jsonify(cached.to_dict())

    s, e     = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()
    if not expenses:
        return jsonify({"summary_text": "No expenses recorded for this month.", "year_month": month})

    by_category  = defaultdict(float)
    by_emotion   = defaultdict(list)
    total_carbon = sum(ex.carbon_kg or 0 for ex in expenses)
    for ex in expenses:
        by_category[ex.category] += ex.amount
        by_emotion[ex.emotion or "neutral"].append(ex.amount)

    stats = {
        "total":        sum(ex.amount for ex in expenses),
        "count":        len(expenses),
        "by_category":  dict(by_category),
        "by_emotion":   {
            k: {"total": sum(v), "avg": sum(v) / len(v), "count": len(v)}
            for k, v in by_emotion.items()
        },
        "top_category":  max(by_category, key=by_category.get) if by_category else "Other",
        "total_carbon":  round(total_carbon, 2),
    }

    text = generate_monthly_summary(month, stats)
    row  = MonthlySummary(year_month=month, summary_text=text)
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict())


# ── Stats ────────────────────────────────────────────────────────────────────

@app.route("/api/stats/monthly")
def monthly_stats():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    by_category = defaultdict(float)
    by_day      = defaultdict(float)
    for ex in expenses:
        by_category[ex.category]    += ex.amount
        by_day[ex.date.isoformat()] += ex.amount

    daily = {}
    cur = s
    while cur < e:
        daily[cur.isoformat()] = by_day.get(cur.isoformat(), 0.0)
        cur += timedelta(days=1)

    return jsonify({
        "total":       sum(ex.amount for ex in expenses),
        "count":       len(expenses),
        "by_category": dict(by_category),
        "by_day":      daily,
    })


@app.route("/api/stats/emotion")
def emotion_stats():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    by_emotion  = defaultdict(list)
    emotion_cat = defaultdict(lambda: defaultdict(float))
    for ex in expenses:
        em = ex.emotion or "neutral"
        by_emotion[em].append(ex.amount)
        emotion_cat[em][ex.category] += ex.amount

    result = {}
    for em, amounts in by_emotion.items():
        top = max(emotion_cat[em], key=emotion_cat[em].get) if emotion_cat[em] else "Other"
        result[em] = {
            "total": sum(amounts),
            "avg":   sum(amounts) / len(amounts),
            "count": len(amounts),
            "top_category": top,
        }
    return jsonify(result)


# ── AI Dashboard Analysis ────────────────────────────────────────────────────

@app.route("/api/ai-analysis")
def ai_analysis():
    """Generate a rich AI spending analysis for the dashboard."""
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    if not expenses:
        return jsonify({"error": "no_data",
                        "message": "No expenses found for this period."})

    # ── Build stats payload ───────────────────────────────────────────────
    by_category  = defaultdict(float)
    by_emotion   = defaultdict(list)
    by_day       = defaultdict(float)
    total_carbon = 0.0

    for ex in expenses:
        by_category[ex.category]    += ex.amount
        by_emotion[ex.emotion or "neutral"].append(ex.amount)
        by_day[ex.date.isoformat()]  += ex.amount
        total_carbon                 += ex.carbon_kg or 0.0

    total      = sum(ex.amount for ex in expenses)
    top_cat    = max(by_category, key=by_category.get) if by_category else "Other"
    top_amount = by_category[top_cat]
    top_pct    = round(top_amount / total * 100, 1) if total else 0

    cat_breakdown = {
        cat: {"amount": round(amt, 0), "pct": round(amt / total * 100, 1)}
        for cat, amt in sorted(by_category.items(), key=lambda x: -x[1])
    }
    emotion_totals = {
        em: {"total": round(sum(v), 0), "count": len(v)}
        for em, v in by_emotion.items()
    }
    active_days  = len([v for v in by_day.values() if v > 0])
    avg_daily    = round(total / active_days, 0) if active_days else 0

    income_setting = Setting.query.filter_by(key="monthly_income").first()
    monthly_income = float(income_setting.value) if income_setting else 0

    stats_payload = {
        "month":          month,
        "total":          round(total, 0),
        "count":          len(expenses),
        "monthly_income": monthly_income,
        "savings":        round(monthly_income - total, 0) if monthly_income else None,
        "savings_rate":   round((monthly_income - total) / monthly_income * 100, 1) if monthly_income else None,
        "top_category":   top_cat,
        "top_pct":        top_pct,
        "avg_daily":      avg_daily,
        "active_days":    active_days,
        "total_carbon":   round(total_carbon, 2),
        "by_category":    cat_breakdown,
        "by_emotion":     emotion_totals,
    }

    # ── Claude API call ───────────────────────────────────────────────────
    client = get_anthropic()
    if not client:
        lines = [
            f"This month you spent TWD {total:,.0f} across {len(expenses)} transactions.",
            f"Your biggest spending area was {top_cat}, making up {top_pct}% of your budget.",
        ]
        if monthly_income:
            savings = monthly_income - total
            lines.append(
                f"You {'saved' if savings >= 0 else 'overspent by'} TWD {abs(savings):,.0f} this month."
            )
        lines.append(f"Your carbon footprint was {total_carbon:.1f} kg CO\u2082e.")
        neg = emotion_totals.get("negative", {}).get("total", 0)
        if neg > total * 0.25:
            lines.append("A notable share of spending happened when you felt stressed — mindful pauses before purchases can help.")
        return jsonify({"analysis": " ".join(lines), "stats": stats_payload, "ai_powered": False})

    cat_lines = "\n".join(
        f"  - {cat}: TWD {v['amount']:,.0f} ({v['pct']}%)"
        for cat, v in list(cat_breakdown.items())[:8]
    )
    income_line = (
        f"Monthly income: TWD {monthly_income:,.0f} | Remaining: TWD {stats_payload['savings']:,.0f} ({stats_payload['savings_rate']}% savings rate)"
        if monthly_income else "Income not set."
    )

    prompt = f"""You are a warm, insightful personal finance coach with an eco-conscious perspective.
Analyse this user's spending data for {month} and write a concise, personalised report in 4-5 sentences.

KEY METRICS:
- Total spent: TWD {total:,.0f} ({len(expenses)} transactions)
- {income_line}
- Top category: {top_cat} ({top_pct}% of total, TWD {top_amount:,.0f})
- Avg daily spend: TWD {avg_daily:,.0f} over {active_days} active days
- Carbon footprint: {total_carbon:.1f} kg CO2e

CATEGORY BREAKDOWN (top 8):
{cat_lines}

EMOTION BREAKDOWN:
{chr(10).join(f"  - {em}: TWD {v['total']:,.0f} ({v['count']} txns)" for em, v in emotion_totals.items())}

INSTRUCTIONS:
1. Open with a warm one-line summary of the month.
2. Highlight the top spending category and whether it seems healthy or worth reviewing.
3. If income data is available, comment on savings rate.
4. Note the carbon footprint with one concrete eco tip.
5. If significant spending was while feeling "negative"/"stressed", gently acknowledge it.
6. Close with one actionable suggestion for next month.
Keep it personal, encouraging, and under 120 words. Flowing prose only — no bullet points."""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        analysis_text = msg.content[0].text.strip()
    except Exception as ex_err:
        analysis_text = f"Analysis unavailable ({ex_err})."

    return jsonify({"analysis": analysis_text, "stats": stats_payload, "ai_powered": True})


# ── Anomaly Detection ─────────────────────────────────────────────────────────

@app.route("/api/anomalies")
def anomalies():
    today = date.today()
    cur_m = today.strftime("%Y-%m")
    prv_m = (f"{today.year}-{today.month - 1:02d}"
             if today.month > 1 else f"{today.year - 1}-12")

    def month_data(m):
        ms, me = month_range(m)
        exps   = Expense.query.filter(Expense.date >= ms, Expense.date < me).all()
        by_cat = defaultdict(float)
        for ex in exps:
            by_cat[ex.category] += ex.amount
        return {
            "total":       sum(ex.amount for ex in exps),
            "by_category": dict(by_cat),
            "max_single":  max((ex.amount for ex in exps), default=0),
            "categories":  list({ex.category for ex in exps}),
        }

    return jsonify(detect_anomalies_nlp(month_data(cur_m), month_data(prv_m)))


# ── CSV Export ───────────────────────────────────────────────────────────────

@app.route("/api/export/csv")
def export_csv():
    month = request.args.get("month")
    q     = Expense.query
    if month:
        s, e = month_range(month)
        q    = q.filter(Expense.date >= s, Expense.date < e)
    exps = q.order_by(Expense.date.desc()).all()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["Date", "Description", "Category", "Amount", "Carbon_kg_CO2e",
                "Emotion", "Context Tag"])
    for ex in exps:
        w.writerow([ex.date, ex.description, ex.category, ex.amount,
                    ex.carbon_kg or 0.0, ex.emotion, ex.context_tag or ""])
    buf.seek(0)
    fname = f"smart-budget-{month or 'all'}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


# ── Seed Data ────────────────────────────────────────────────────────────────

@app.route("/api/seed")
def seed():
    Expense.query.delete()
    Budget.query.delete()
    MonthlySummary.query.delete()
    Setting.query.delete()
    db.session.commit()

    rows = [
        ("2026-06-01", 180,  "Restaurant",         "Lunch at MOS Burger",                     "negative", "feeling stressed before exam",       "study-related"),
        ("2026-06-02",  45,  "Public Transport",    "Bus pass top-up",                          "neutral",  "",                                   None),
        ("2026-06-03", 320,  "Entertainment",       "Concert tickets with friends",             "positive", "so excited for tonight!",            "social"),
        ("2026-06-04",  95,  "Groceries",           "Weekly vegetable shopping",                "neutral",  "",                                   None),
        ("2026-06-05", 580,  "Fashion",             "New running shoes on sale",                "positive", "great deal, 40% off!",               None),
        ("2026-06-06", 220,  "Education",           "Textbook for statistics course",           "negative", "expensive but necessary",            "study-related"),
        ("2026-06-07",  60,  "Cafe & Drinks",       "Coffee and snacks during study session",   "neutral",  "",                                   "study-related"),
        ("2026-06-08", 150,  "Healthcare",          "Hospital checkup copay",                   "negative", "anxious about appointment",          "health-related"),
        ("2026-06-09",  85,  "Electricity",         "Monthly electricity bill",                 "neutral",  "",                                   None),
        ("2026-06-10", 200,  "Restaurant",          "Team dinner after project presentation",   "positive", "celebrating our success!",           "work-related"),
        ("2026-06-12",1200,  "Electronics",         "Impulse bought gaming controller",         "negative", "retail therapy gone wrong",          None),
        ("2026-06-14",  75,  "Taxi & Rideshare",    "Taxi home late night after studying",      "negative", "exhausted from finals prep",         "study-related"),
        ("2026-06-16", 350,  "Streaming & Software","Streaming subscriptions and snacks",       "positive", "needed a break from studying",       "social"),
        ("2026-06-18", 480,  "Healthcare",          "Gym membership monthly fee",               "positive", "investing in my health",             "health-related"),
        ("2026-06-20", 130,  "Cafe & Drinks",       "Stress eating bubble tea and snacks",      "negative", "finals week anxiety hitting hard",   "study-related"),
        ("2026-06-22",2800,  "Flight",              "Round trip to Taipei for interview",       "positive", "nervous but excited",                "work-related"),
        ("2026-06-24", 650,  "Meat & Dairy",        "BBQ supplies for graduation party",        "positive", "celebrating with friends",           "social"),
        ("2026-06-26", 120,  "Public Transport",    "MRT monthly pass renewal",                 "neutral",  "",                                   None),
        ("2026-06-28",  35,  "Groceries",           "Fruit and vegetables from market",         "positive", "trying to eat healthier",            "health-related"),
        ("2026-06-30", 890,  "Car & Fuel",          "Gas for road trip to Kenting",             "positive", "weekend adventure with friends!",    "social"),
    ]

    for d, amt, cat, desc, em, en, ctx in rows:
        carbon = calculate_carbon(amt, cat)
        db.session.add(Expense(
            amount=amt, category=cat, description=desc,
            emotion=em, emotion_note=en, context_tag=ctx,
            carbon_kg=carbon,
            date=datetime.strptime(d, "%Y-%m-%d").date(),
        ))

    budgets = [
        ("Restaurant", 800),      ("Public Transport", 200),
        ("Entertainment", 400),   ("Fashion", 600),
        ("Healthcare", 600),      ("Education", 500),
        ("Electricity", 300),     ("Groceries", 500),
    ]
    for cat, lim in budgets:
        db.session.add(Budget(category=cat, monthly_limit=lim))

    db.session.add(Setting(key="monthly_income", value="12000"))
    db.session.commit()
    return jsonify({"message": "Seed data loaded", "expenses": len(rows)})


# ── Init & Migration ─────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    try:
        db.session.execute(db.text("SELECT carbon_kg FROM expenses LIMIT 1"))
    except Exception:
        try:
            db.session.execute(db.text(
                "ALTER TABLE expenses ADD COLUMN carbon_kg FLOAT DEFAULT 0.0"
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        nulls = Expense.query.filter(
            db.or_(Expense.carbon_kg == None, Expense.carbon_kg == 0.0)
        ).all()
        if nulls:
            for ex in nulls:
                ex.carbon_kg = calculate_carbon(ex.amount, ex.category)
            db.session.commit()
    except Exception:
        db.session.rollback()


# ── Self-ping ─────────────────────────────────────────────────────────────────

_PING_URL      = "https://smart-budget-tester.onrender.com/api/status"
_PING_INTERVAL = 14 * 60

def _ping_loop():
    while True:
        time.sleep(_PING_INTERVAL)
        try:
            urllib.request.urlopen(_PING_URL, timeout=10)
        except Exception:
            pass

threading.Thread(target=_ping_loop, daemon=True).start()


if __name__ == "__main__":
    app.run(debug=True)
