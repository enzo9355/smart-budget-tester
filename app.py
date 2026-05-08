import os
import csv
import io
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

CATEGORIES = [
    "Food & Dining", "Transport", "Entertainment", "Shopping",
    "Health", "Education", "Utilities", "Other"
]


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
        expense = Expense(
            amount       = float(data["amount"]),
            category     = data.get("category", "Other"),
            description  = data.get("description", ""),
            emotion      = data.get("emotion", "neutral"),
            emotion_note = data.get("emotion_note", ""),
            context_tag  = ctx if ctx and ctx != "none" else None,
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


# ── NLP Parse (preview only — does NOT save) ─────────────────────────────────

@app.route("/api/parse", methods=["POST"])
def parse_route():
    from nlp_service import parse_expense
    text   = (request.json or {}).get("text", "")
    result = parse_expense(text, date.today().isoformat())
    return jsonify(result)


# ── Budgets ───────────────────────────────────────────────────────────────────

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


# ── Monthly Summary (NLP narrative) ──────────────────────────────────────────

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
    for ex in expenses:
        by_category[ex.category] += ex.amount
        by_emotion[ex.emotion or "neutral"].append(ex.amount)

    stats = {
        "total":       sum(ex.amount for ex in expenses),
        "count":       len(expenses),
        "by_category": dict(by_category),
        "by_emotion":  {
            k: {"total": sum(v), "avg": sum(v) / len(v), "count": len(v)}
            for k, v in by_emotion.items()
        },
        "top_category": max(by_category, key=by_category.get) if by_category else "Other",
    }

    from nlp_service import generate_monthly_summary
    text = generate_monthly_summary(month, stats)

    row = MonthlySummary(year_month=month, summary_text=text)
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict())


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.route("/api/stats/monthly")
def monthly_stats():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    s, e  = month_range(month)
    expenses = Expense.query.filter(Expense.date >= s, Expense.date < e).all()

    by_category = defaultdict(float)
    by_day      = defaultdict(float)
    for ex in expenses:
        by_category[ex.category]       += ex.amount
        by_day[ex.date.isoformat()]    += ex.amount

    # Fill every day in the month
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


# ── Anomaly Detection ─────────────────────────────────────────────────────────

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
            "total":      sum(ex.amount for ex in exps),
            "by_category": dict(by_cat),
            "max_single": max((ex.amount for ex in exps), default=0),
            "categories": list({ex.category for ex in exps}),
        }

    from nlp_service import detect_anomalies_nlp
    return jsonify(detect_anomalies_nlp(month_data(cur_m), month_data(prv_m)))


# ── CSV Export ────────────────────────────────────────────────────────────────

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
    w.writerow(["Date", "Description", "Category", "Amount", "Emotion", "Context Tag", "Emotion Note"])
    for ex in exps:
        w.writerow([ex.date, ex.description, ex.category, ex.amount,
                    ex.emotion, ex.context_tag or "", ex.emotion_note or ""])
    buf.seek(0)
    fname = f"smart-budget-{month or 'all'}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})


# ── Seed Data ─────────────────────────────────────────────────────────────────

@app.route("/api/seed")
def seed():
    Expense.query.delete()
    Budget.query.delete()
    MonthlySummary.query.delete()
    db.session.commit()

    rows = [
        ("2026-05-01", 180,  "Food & Dining",  "Lunch at MOS Burger",                      "negative", "feeling stressed before exam",        "study-related"),
        ("2026-05-02",  45,  "Transport",       "Bus pass top-up",                           "neutral",  "",                                    None),
        ("2026-05-03", 320,  "Entertainment",   "Concert tickets with friends",              "positive", "so excited for tonight!",             "social"),
        ("2026-05-04",  95,  "Food & Dining",   "Weekly grocery shopping",                   "neutral",  "",                                    None),
        ("2026-05-05", 580,  "Shopping",        "New running shoes on sale",                 "positive", "great deal, 40% off!",                None),
        ("2026-05-06", 220,  "Education",       "Textbook for statistics course",            "negative", "expensive but necessary",             "study-related"),
        ("2026-05-07",  60,  "Food & Dining",   "Coffee and snacks during study session",    "neutral",  "",                                    "study-related"),
        ("2026-05-08", 150,  "Health",          "Grabbed food on way to hospital checkup",   "negative", "anxious about appointment",           "health-related"),
        ("2026-05-09",  85,  "Utilities",       "Mobile phone bill",                         "neutral",  "",                                    None),
        ("2026-05-10", 200,  "Food & Dining",   "Team dinner after project presentation",    "positive", "celebrating our success!",            "work-related"),
        ("2026-05-12",1200,  "Shopping",        "Impulse bought gaming controller",          "negative", "retail therapy gone wrong",           None),
        ("2026-05-14",  75,  "Transport",       "Taxi home late night after studying",       "negative", "exhausted from finals prep",          "study-related"),
        ("2026-05-16", 350,  "Entertainment",   "Streaming subscriptions and snacks",        "positive", "needed a break from studying",        "social"),
        ("2026-05-18", 480,  "Health",          "Gym membership monthly fee",                "positive", "investing in my health",              "health-related"),
        ("2026-05-20", 130,  "Food & Dining",   "Stress eating bubble tea and snacks",       "negative", "finals week anxiety hitting hard",    "study-related"),
    ]

    for d, amt, cat, desc, em, en, ctx in rows:
        db.session.add(Expense(
            amount=amt, category=cat, description=desc,
            emotion=em, emotion_note=en, context_tag=ctx,
            date=datetime.strptime(d, "%Y-%m-%d").date(),
        ))

    budgets = [
        ("Food & Dining", 500), ("Transport", 200), ("Entertainment", 400),
        ("Shopping", 800),      ("Health", 600),     ("Education", 500),
        ("Utilities", 200),
    ]
    for cat, lim in budgets:
        db.session.add(Budget(category=cat, monthly_limit=lim))

    db.session.commit()
    return jsonify({"message": "Seed data loaded", "expenses": len(rows)})


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
