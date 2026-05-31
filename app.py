"""
Smart Budget — Gamified Eco-Finance Cultivation App
Flask backend with carbon footprint tracking, ESG scoring, and gamification.
"""
import os
import csv
import io
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


# ── Carbon Categories & Emission Factors ─────────────────────────────────────
# Based on GHG Protocol Scope 3 spend-based methodology
# Factors: kg CO2e per TWD spent
# Derived from EU consumption emission factor data, converted at 1 EUR ~ 35 TWD

CARBON_CATEGORIES = {
    "Car & Fuel":           {"factor": 0.120, "icon": "\U0001f697", "group": "Transport"},
    "Public Transport":     {"factor": 0.012, "icon": "\U0001f68c", "group": "Transport"},
    "Taxi & Rideshare":     {"factor": 0.060, "icon": "\U0001f695", "group": "Transport"},
    "Flight":               {"factor": 0.280, "icon": "✈️", "group": "Transport"},
    "Meat & Dairy":         {"factor": 0.090, "icon": "\U0001f969", "group": "Food"},
    "Groceries":            {"factor": 0.010, "icon": "\U0001f966", "group": "Food"},
    "Restaurant":           {"factor": 0.055, "icon": "\U0001f37d️", "group": "Food"},
    "Cafe & Drinks":        {"factor": 0.040, "icon": "☕",     "group": "Food"},
    "Seafood":              {"factor": 0.070, "icon": "\U0001f41f", "group": "Food"},
    "Fashion":              {"factor": 0.080, "icon": "\U0001f457", "group": "Shopping"},
    "Electronics":          {"factor": 0.100, "icon": "\U0001f4f1", "group": "Shopping"},
    "Books & Stationery":   {"factor": 0.008, "icon": "\U0001f4da", "group": "Shopping"},
    "Beauty & Personal":    {"factor": 0.045, "icon": "\U0001f484", "group": "Shopping"},
    "Furniture & Home":     {"factor": 0.060, "icon": "\U0001f3e0", "group": "Shopping"},
    "Electricity":          {"factor": 0.095, "icon": "⚡",     "group": "Utilities"},
    "Water":                {"factor": 0.005, "icon": "\U0001f4a7", "group": "Utilities"},
    "Gas":                  {"factor": 0.110, "icon": "\U0001f525", "group": "Utilities"},
    "Rent & Housing":       {"factor": 0.020, "icon": "\U0001f3d8️", "group": "Housing"},
    "Streaming & Software": {"factor": 0.015, "icon": "\U0001f4fa", "group": "Digital"},
    "Education":            {"factor": 0.008, "icon": "\U0001f393", "group": "Education"},
    "Healthcare":           {"factor": 0.025, "icon": "\U0001f3e5", "group": "Health"},
    "Entertainment":        {"factor": 0.030, "icon": "\U0001f3ac", "group": "Entertainment"},
    "Insurance":            {"factor": 0.010, "icon": "\U0001f6e1️", "group": "Finance"},
    "Other":                {"factor": 0.040, "icon": "\U0001f4e6", "group": "Other"},
}

CATEGORIES = list(CARBON_CATEGORIES.keys())

# Backward compatibility for old category names
LEGACY_CATEGORY_MAP = {
    "Food & Dining": "Restaurant",
    "Transport":     "Public Transport",
    "Shopping":      "Fashion",
    "Health":        "Healthcare",
    "Utilities":     "Electricity",
}


def calculate_carbon(amount, category):
    """Calculate carbon footprint (kg CO2e) for a transaction amount in TWD."""
    mapped = LEGACY_CATEGORY_MAP.get(category, category)
    if mapped == "Electricity":
        kwh = amount / 3.5    # Taiwan avg electricity price: 3.5 TWD/kWh
        return round(kwh * 0.495, 3)  # Taiwan EPA grid emission factor
    info = CARBON_CATEGORIES.get(mapped, CARBON_CATEGORIES["Other"])
    return round(amount * info["factor"], 3)


def get_earth_state(monthly_carbon):
    """Determine Earth companion visual state from monthly carbon (kg CO2e)."""
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
    """Get gamification rank based on eco score."""
    if score >= 300:
        return {"rank": "Earth Protector", "emoji": "\U0001f30d", "next_at": None}
    elif score >= 150:
        return {"rank": "Guardian", "emoji": "\U0001f333", "next_at": 300}
    elif score >= 50:
        return {"rank": "Sprout", "emoji": "\U0001f33f", "next_at": 150}
    else:
        return {"rank": "Seedling", "emoji": "\U0001f331", "next_at": 50}


# ── Models ──────────────────────────────────────────────────────────────────

class Expense(db.Model):
    __tablename__ = "expenses"
    id          = db.Column(db.Integer, primary_key=True)
    amount      = db.Column(db.Float,   nullable=False)
    category    = db.Column(db.String(50), nullable=False, default="Other")
    description = db.Column(db.Text)
    emotion     = db.Column(db.String(20), default="neutral")
    emotion_note= db.Column(db.Text)
    context_tag = db.Column(db.String(50))
    carbon_kg   = db.Column(db.Float, default=0.0)
    date        = db.Column(db.Date, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def month_range(month_str):
    """Return (start_date, end_date_exclusive) for a YYYY-MM string."""
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
    return jsonify({"ai_enabled": bool(os.environ.get("GEMINI_API_KEY"))})


@app.route("/api/categories")
def get_categories():
    """Return all categories with their carbon info for the frontend."""
    return jsonify(CARBON_CATEGORIES)


# ── Expenses ─────────────────────────────────────────────────────────────────

@app.route("/api/expenses", methods=["POST"])
def create_expense():
    data = request.json or {}
    try:
        expense_date = (
            datetime.strptime(data["date"], "%Y-%m-%d").date()
            if data.get("date") else date.today()
        )
        ctx = data.get("context_tag")
        amount = float(data["amount"])
        category = data.get("category", "Other")

        # Auto-calculate carbon or use manual override
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


# ── NLP Parse (preview only) ────────────────────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def parse_route():
    from nlp_service import parse_expense
    text   = (request.json or {}).get("text", "")
    result = parse_expense(text, date.today().isoformat())
    # Map legacy categories to new carbon-aware categories
    if result.get("category"):
        result["category"] = LEGACY_CATEGORY_MAP.get(result["category"], result["category"])
    # Attach carbon estimate
    if result.get("amount") and result.get("category"):
        result["carbon_kg"] = calculate_carbon(float(result["amount"]), result["category"])
    return jsonify(result)


# ── Carbon Endpoints ─────────────────────────────────────────────────────────

@app.route("/api/carbon/estimate")
def carbon_estimate():
    """Live carbon estimate for a given amount and category."""
    amount   = float(request.args.get("amount", 0))
    category = request.args.get("category", "Other")
    return jsonify({"carbon_kg": calculate_carbon(amount, category)})


@app.route("/api/carbon/summary")
def carbon_summary():
    """Return carbon totals grouped by category and time period."""
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

    # Carbon equivalences
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
    """Return eco score, streak, rank, and earth state for gamification."""
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    # Eco score: low-carbon txs earn points, high-carbon txs cost points
    score = 0
    monthly_carbon = 0.0
    for ex in expenses:
        c = ex.carbon_kg or 0.0
        monthly_carbon += c
        if c < 0.05:
            score += 5
        elif c > 2.0:
            score -= 10
    score = max(score, 0)

    # Streak: consecutive days with at least one transaction (1-day grace)
    streak = 0
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
        budget.monthly_limit = limit
    else:
        budget = Budget(category=category, monthly_limit=limit)
        db.session.add(budget)
    db.session.commit()
    return jsonify(budget.to_dict())


@app.route("/api/budgets")
def get_budgets():
    month   = request.args.get("month", date.today().strftime("%Y-%m"))
    budgets = Budget.query.all()
    s, e    = month_range(month)
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


# ── Monthly Summary (NLP narrative) ─────────────────────────────────────────

@app.route("/api/summary/<month>")
def get_summary(month):
    force   = request.args.get("force", "false") == "true"
    cached  = (MonthlySummary.query
               .filter_by(year_month=month)
               .order_by(MonthlySummary.generated_at.desc())
               .first())
    if cached and not force:
        return jsonify(cached.to_dict())

    s, e     = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()
    if not expenses:
        return jsonify({"summary_text": "No expenses recorded for this month.", "year_month": month})

    by_category = defaultdict(float)
    by_emotion  = defaultdict(list)
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

    from nlp_service import generate_monthly_summary
    text = generate_monthly_summary(month, stats)

    row = MonthlySummary(year_month=month, summary_text=text)
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


# ── Anomaly Detection ───────────────────────────────────────────────────────

@app.route("/api/anomalies")
def anomalies():
    today = date.today()
    cur_m = today.strftime("%Y-%m")
    prv_m = f"{today.year}-{today.month - 1:02d}" if today.month > 1 else f"{today.year - 1}-12"

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

    from nlp_service import detect_anomalies_nlp
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
    db.session.commit()

    rows = [
        ("2026-05-01", 180,  "Restaurant",         "Lunch at MOS Burger",                     "negative", "feeling stressed before exam",       "study-related"),
        ("2026-05-02",  45,  "Public Transport",    "Bus pass top-up",                          "neutral",  "",                                   None),
        ("2026-05-03", 320,  "Entertainment",       "Concert tickets with friends",             "positive", "so excited for tonight!",            "social"),
        ("2026-05-04",  95,  "Groceries",           "Weekly vegetable shopping",                "neutral",  "",                                   None),
        ("2026-05-05", 580,  "Fashion",             "New running shoes on sale",                "positive", "great deal, 40% off!",               None),
        ("2026-05-06", 220,  "Education",           "Textbook for statistics course",           "negative", "expensive but necessary",            "study-related"),
        ("2026-05-07",  60,  "Cafe & Drinks",       "Coffee and snacks during study session",   "neutral",  "",                                   "study-related"),
        ("2026-05-08", 150,  "Healthcare",          "Hospital checkup copay",                   "negative", "anxious about appointment",          "health-related"),
        ("2026-05-09",  85,  "Electricity",         "Monthly electricity bill",                 "neutral",  "",                                   None),
        ("2026-05-10", 200,  "Restaurant",          "Team dinner after project presentation",   "positive", "celebrating our success!",           "work-related"),
        ("2026-05-12",1200,  "Electronics",         "Impulse bought gaming controller",         "negative", "retail therapy gone wrong",          None),
        ("2026-05-14",  75,  "Taxi & Rideshare",    "Taxi home late night after studying",      "negative", "exhausted from finals prep",         "study-related"),
        ("2026-05-16", 350,  "Streaming & Software","Streaming subscriptions and snacks",       "positive", "needed a break from studying",       "social"),
        ("2026-05-18", 480,  "Healthcare",          "Gym membership monthly fee",               "positive", "investing in my health",             "health-related"),
        ("2026-05-20", 130,  "Cafe & Drinks",       "Stress eating bubble tea and snacks",      "negative", "finals week anxiety hitting hard",   "study-related"),
        ("2026-05-22",2800,  "Flight",              "Round trip to Taipei for interview",       "positive", "nervous but excited",                "work-related"),
        ("2026-05-24", 650,  "Meat & Dairy",        "BBQ supplies for graduation party",        "positive", "celebrating with friends",           "social"),
        ("2026-05-26", 120,  "Public Transport",    "MRT monthly pass renewal",                 "neutral",  "",                                   None),
        ("2026-05-28",  35,  "Groceries",           "Fruit and vegetables from market",         "positive", "trying to eat healthier",            "health-related"),
        ("2026-05-30", 890,  "Car & Fuel",          "Gas for road trip to Kenting",             "positive", "weekend adventure with friends!",    "social"),
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

    db.session.commit()
    return jsonify({"message": "Seed data loaded", "expenses": len(rows)})


# ── Init & Migration ────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    # Add carbon_kg column to existing databases
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

    # Backfill carbon_kg for any existing records missing it
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


# ── Self-ping (keeps Render free tier alive) ─────────────────────────────────

_PING_URL = "https://smart-budget-tester.onrender.com/api/status"
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
