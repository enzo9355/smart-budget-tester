"""
NLP service using Google Gemini API.
All functions fall back to rule-based logic if Gemini is unavailable or returns
invalid JSON — the app never crashes due to NLP failures.
"""
import os
import re
import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Food & Dining", "Transport", "Entertainment", "Shopping",
    "Health", "Education", "Utilities", "Other",
]
EMOTIONS    = ["positive", "neutral", "negative"]
CONTEXT_TAGS = ["study-related", "health-related", "social", "work-related", "none"]


def _get_model():
    """Return a configured Gemini GenerativeModel, or None if unavailable."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as exc:
        logger.error("Gemini init failed: %s", exc)
        return None


def _clean_json(raw: str) -> str:
    """Strip markdown code fences that Gemini sometimes wraps around JSON."""
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*",     "", raw)
    return raw.strip()


# ── Public functions ──────────────────────────────────────────────────────────

def parse_expense(text: str, today: str) -> dict:
    """
    Extract expense fields from a natural-language description.
    Returns a dict with keys: amount, category, description, date, emotion, context_tag.
    """
    model = _get_model()
    if model:
        prompt = f"""Parse this expense text and return ONLY a valid JSON object (no markdown, no explanation).

Text: "{text}"
Today's date: {today}

Extract these fields:
- amount      : number (required — pull from text)
- category    : exactly one of {CATEGORIES}
- description : cleaned text (remove raw amount and date words)
- date        : YYYY-MM-DD (use today if unspecified; handle "yesterday", "last Friday", etc.)
- emotion     : one of ["positive","neutral","negative"] — infer from tone and keywords
- context_tag : one of {CONTEXT_TAGS} — "study-related" for exam/class context, "health-related" for medical, "social" for friends/parties, "work-related" for office/meetings, "none" otherwise

Return JSON only (example shape):
{{"amount":0,"category":"Other","description":"","date":"{today}","emotion":"neutral","context_tag":"none"}}"""

        try:
            resp   = model.generate_content(prompt)
            parsed = json.loads(_clean_json(resp.text))

            if parsed.get("category") not in CATEGORIES:
                parsed["category"] = "Other"
            if parsed.get("emotion") not in EMOTIONS:
                parsed["emotion"] = "neutral"
            if parsed.get("context_tag") not in CONTEXT_TAGS:
                parsed["context_tag"] = "none"

            return parsed
        except Exception as exc:
            logger.error("parse_expense Gemini error: %s", exc)

    return _fallback_parse(text, today)


def generate_monthly_summary(month: str, stats: dict) -> str:
    """
    Generate a 3-sentence personal finance narrative for the given month.
    Falls back to a template string if Gemini fails.
    """
    model = _get_model()
    if model:
        prompt = f"""Write a 3-sentence personal finance summary for {month}.

Spending data:
{json.dumps(stats, indent=2)}

Tone  : helpful financial advisor — encouraging, non-judgmental.
Rules :
  Sentence 1 — one specific observation about spending patterns or top category.
  Sentence 2 — note on emotional spending if data is present, or comparison insight.
  Sentence 3 — one actionable, personalised suggestion.

Return ONLY the 3-sentence paragraph. No bullet points, no JSON, no headers."""

        try:
            return model.generate_content(prompt).text.strip()
        except Exception as exc:
            logger.error("generate_monthly_summary Gemini error: %s", exc)

    total   = stats.get("total", 0)
    top_cat = stats.get("top_category", "Other")
    count   = stats.get("count", 0)
    return (
        f"This month you recorded {count} transactions totalling ${total:.0f}. "
        f"Your highest spending category was {top_cat}, which drove most of your budget. "
        f"Consider setting a stricter limit for {top_cat} next month to stay on track."
    )


def detect_anomalies_nlp(current: dict, previous: dict) -> list:
    """
    Compare two months of spending data and return up to 3 anomaly dicts:
    [{category, change_percent, message}]
    """
    model = _get_model()
    if model:
        prompt = f"""Compare these two months of personal spending data and identify anomalies.

Current month : {json.dumps(current,  indent=2)}
Previous month: {json.dumps(previous, indent=2)}

Find up to 3 noteworthy anomalies (new categories, big spikes, unusually large single transactions).
Return ONLY a JSON array (no markdown):
[{{"category":"string","change_percent":number,"message":"brief user-friendly explanation"}}]
If no significant anomalies exist, return: []"""

        try:
            raw       = _clean_json(model.generate_content(prompt).text)
            anomalies = json.loads(raw)
            if isinstance(anomalies, list):
                return anomalies[:3]
        except Exception as exc:
            logger.error("detect_anomalies Gemini error: %s", exc)

    return _fallback_anomalies(current, previous)


# ── Fallback rule-based implementations ──────────────────────────────────────

def _fallback_parse(text: str, today: str) -> dict:
    # Amount
    m      = re.search(r"\$?(\d{1,6}(?:\.\d{1,2})?)", text)
    amount = float(m.group(1)) if m else 0.0

    # Date
    expense_date = today
    tl = text.lower()
    if "yesterday" in tl:
        expense_date = (date.fromisoformat(today) - timedelta(days=1)).isoformat()

    # Category
    category = "Other"
    if any(w in tl for w in ["food","lunch","dinner","breakfast","eat","restaurant","burger",
                               "coffee","cafe","meal","snack","drink","tea","boba","bubble"]):
        category = "Food & Dining"
    elif any(w in tl for w in ["bus","taxi","uber","mrt","train","transport","fare","cab","subway","grab"]):
        category = "Transport"
    elif any(w in tl for w in ["movie","concert","game","netflix","spotify","entertainment",
                                "ticket","streaming","show","cinema"]):
        category = "Entertainment"
    elif any(w in tl for w in ["shop","buy","purchase","clothes","shoes","mall","amazon","store"]):
        category = "Shopping"
    elif any(w in tl for w in ["doctor","hospital","medicine","pharmacy","health","gym","clinic","checkup"]):
        category = "Health"
    elif any(w in tl for w in ["textbook","course","tuition","study","school","university","exam","class"]):
        category = "Education"
    elif any(w in tl for w in ["bill","electricity","water","internet","phone","utility","subscription"]):
        category = "Utilities"

    # Emotion
    emotion = "neutral"
    if any(w in tl for w in ["happy","excited","great","love","celebrat","joy","fun","good","amazing"]):
        emotion = "positive"
    elif any(w in tl for w in ["stress","sad","anxious","tired","depress","anger","frustrat","worried","bad"]):
        emotion = "negative"

    # Context tag
    context_tag = None
    if any(w in tl for w in ["study","exam","school","class","textbook","lecture","homework"]):
        context_tag = "study-related"
    elif any(w in tl for w in ["hospital","doctor","medicine","health","medical","clinic"]):
        context_tag = "health-related"
    elif any(w in tl for w in ["friend","party","social","date","gathering","outing"]):
        context_tag = "social"
    elif any(w in tl for w in ["work","office","meeting","boss","colleague","project"]):
        context_tag = "work-related"

    # Clean description
    desc = re.sub(r"\$?\d{1,6}(?:\.\d{1,2})?", "", text)
    desc = re.sub(r"\b(yesterday|today|tomorrow)\b", "", desc, flags=re.IGNORECASE)
    desc = " ".join(desc.split()) or text

    return {
        "amount":      amount,
        "category":    category,
        "description": desc,
        "date":        expense_date,
        "emotion":     emotion,
        "context_tag": context_tag or "none",
    }


def _fallback_anomalies(current: dict, previous: dict) -> list:
    anomalies = []
    cur_cats  = current.get("by_category", {})
    prv_cats  = previous.get("by_category", {})

    # No previous data — only flag very large single transactions
    if not prv_cats:
        big = current.get("max_single", 0)
        if big > 500:
            anomalies.append({
                "category":       "General",
                "change_percent": 0,
                "message":        f"Large single transaction detected: ${big:.0f}. Check if this was intentional.",
            })
        return anomalies

    # New categories never seen before
    for cat, amt in cur_cats.items():
        if cat not in prv_cats and amt > 0:
            anomalies.append({
                "category":       cat,
                "change_percent": 100,
                "message":        f"New spending category this month: {cat} (${amt:.0f}).",
            })

    # Category spikes > 50 %
    for cat, amt in cur_cats.items():
        if cat in prv_cats and prv_cats[cat] > 0:
            pct = (amt - prv_cats[cat]) / prv_cats[cat] * 100
            if pct > 50:
                anomalies.append({
                    "category":       cat,
                    "change_percent": round(pct),
                    "message":        f"{cat} spending rose {pct:.0f}% vs. last month (${prv_cats[cat]:.0f} → ${amt:.0f}).",
                })

    # Unusually large single transaction (> 40 % of monthly total)
    total = current.get("total", 1) or 1
    big   = current.get("max_single", 0)
    if big > total * 0.4 and big > 200:
        anomalies.append({
            "category":       "General",
            "change_percent": 0,
            "message":        f"One transaction (${big:.0f}) accounts for over 40 % of your total spending this month.",
        })

    return anomalies[:3]
