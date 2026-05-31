"""
NLP service using Google Gemini API.
Updated for carbon-aware categories.
All functions fall back to rule-based logic if Gemini is unavailable.
"""
import os
import re
import json
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Car & Fuel", "Public Transport", "Taxi & Rideshare", "Flight",
    "Meat & Dairy", "Groceries", "Restaurant", "Cafe & Drinks", "Seafood",
    "Fashion", "Electronics", "Books & Stationery", "Beauty & Personal", "Furniture & Home",
    "Electricity", "Water", "Gas", "Rent & Housing",
    "Streaming & Software", "Education", "Healthcare", "Entertainment",
    "Insurance", "Other",
]
EMOTIONS     = ["positive", "neutral", "negative"]
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
- context_tag : one of {CONTEXT_TAGS}

Category guidance:
- Food: "Restaurant" for dining out, "Groceries" for supermarket/veg/fruit, "Meat & Dairy" for meat purchases, "Cafe & Drinks" for coffee/tea/bubble tea, "Seafood" for fish/sushi
- Transport: "Car & Fuel" for gas/petrol, "Public Transport" for bus/MRT/train, "Taxi & Rideshare" for taxi/Uber, "Flight" for airplane
- Shopping: "Fashion" for clothes/shoes, "Electronics" for gadgets, "Books & Stationery" for books/study supplies
- Utilities: "Electricity" for power bills, "Water" for water bills, "Gas" for natural gas
- Other: "Healthcare" for medical/gym, "Education" for tuition/courses, "Entertainment" for movies/games/streaming

Return JSON only (example shape):
{{"amount":0,"category":"Other","description":"","date":"{today}","emotion":"neutral","context_tag":"none"}}"""

        try:
            resp   = model.generate_content(prompt)
            parsed = json.loads(_clean_json(resp.text))

            if parsed.get("category") not in CATEGORIES:
                parsed["category"] = _best_match_category(parsed.get("category", ""))
            if parsed.get("emotion") not in EMOTIONS:
                parsed["emotion"] = "neutral"
            if parsed.get("context_tag") not in CONTEXT_TAGS:
                parsed["context_tag"] = "none"

            return parsed
        except Exception as exc:
            logger.error("parse_expense Gemini error: %s", exc)

    return _fallback_parse(text, today)


def _best_match_category(raw: str) -> str:
    """Try to match an unknown category string to our list."""
    if not raw:
        return "Other"
    raw_lower = raw.lower()
    for cat in CATEGORIES:
        if cat.lower() in raw_lower or raw_lower in cat.lower():
            return cat
    # Legacy mappings
    legacy = {
        "food": "Restaurant", "dining": "Restaurant", "transport": "Public Transport",
        "shopping": "Fashion", "health": "Healthcare", "utilities": "Electricity",
    }
    for key, val in legacy.items():
        if key in raw_lower:
            return val
    logger.warning("Unknown category '%s', falling back to Other", raw)
    return "Other"


def generate_monthly_summary(month: str, stats: dict) -> str:
    """
    Generate a 3-sentence personal finance + eco narrative for the given month.
    Falls back to a template string if Gemini fails.
    """
    model = _get_model()
    if model:
        prompt = f"""Write a 3-sentence personal finance and eco-impact summary for {month}.

Spending data:
{json.dumps(stats, indent=2)}

Tone  : helpful eco-aware financial advisor — encouraging, non-judgmental.
Rules :
  Sentence 1 — one specific observation about spending patterns or top category.
  Sentence 2 — note on carbon footprint or emotional spending patterns if data is present.
  Sentence 3 — one actionable, personalised suggestion for both saving money and reducing carbon.

Return ONLY the 3-sentence paragraph. No bullet points, no JSON, no headers."""

        try:
            return model.generate_content(prompt).text.strip()
        except Exception as exc:
            logger.error("generate_monthly_summary Gemini error: %s", exc)

    total   = stats.get("total", 0)
    top_cat = stats.get("top_category", "Other")
    count   = stats.get("count", 0)
    carbon  = stats.get("total_carbon", 0)
    return (
        f"This month you recorded {count} transactions totalling ${total:.0f}. "
        f"Your highest spending category was {top_cat}, generating approximately {carbon:.1f} kg CO₂e. "
        f"Consider choosing lower-carbon alternatives in {top_cat} next month to save money and help the planet."
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

    # Category — carbon-aware mapping
    category = "Other"
    if any(w in tl for w in ["lunch","dinner","breakfast","restaurant","burger","noodle","rice","bento"]):
        category = "Restaurant"
    elif any(w in tl for w in ["coffee","cafe","tea","boba","bubble","latte","starbucks"]):
        category = "Cafe & Drinks"
    elif any(w in tl for w in ["grocery","vegetable","fruit","supermarket","market"]):
        category = "Groceries"
    elif any(w in tl for w in ["meat","beef","pork","chicken","steak","bbq","barbecue","dairy","milk"]):
        category = "Meat & Dairy"
    elif any(w in tl for w in ["fish","sushi","seafood","shrimp","salmon"]):
        category = "Seafood"
    elif any(w in tl for w in ["gas","fuel","petrol","parking","car"]):
        category = "Car & Fuel"
    elif any(w in tl for w in ["bus","mrt","train","metro","subway"]):
        category = "Public Transport"
    elif any(w in tl for w in ["taxi","uber","grab","lyft","ride"]):
        category = "Taxi & Rideshare"
    elif any(w in tl for w in ["flight","airplane","airport","fly","plane"]):
        category = "Flight"
    elif any(w in tl for w in ["movie","concert","game","ticket","cinema","show","karaoke"]):
        category = "Entertainment"
    elif any(w in tl for w in ["netflix","spotify","streaming","subscription","software","app"]):
        category = "Streaming & Software"
    elif any(w in tl for w in ["clothes","shoes","fashion","shirt","dress","pants","jacket","mall"]):
        category = "Fashion"
    elif any(w in tl for w in ["phone","laptop","computer","tablet","electronics","gadget","controller"]):
        category = "Electronics"
    elif any(w in tl for w in ["book","textbook","stationery","pen","notebook"]):
        category = "Books & Stationery"
    elif any(w in tl for w in ["cosmetic","makeup","beauty","skincare","shampoo","personal"]):
        category = "Beauty & Personal"
    elif any(w in tl for w in ["doctor","hospital","medicine","pharmacy","gym","clinic","checkup","health"]):
        category = "Healthcare"
    elif any(w in tl for w in ["tuition","course","study","school","university","exam","class","education"]):
        category = "Education"
    elif any(w in tl for w in ["electricity","power","electric bill"]):
        category = "Electricity"
    elif any(w in tl for w in ["water bill"]):
        category = "Water"
    elif any(w in tl for w in ["rent","lease","housing"]):
        category = "Rent & Housing"
    elif any(w in tl for w in ["insurance"]):
        category = "Insurance"
    elif any(w in tl for w in ["furniture","sofa","desk","chair","home","decor"]):
        category = "Furniture & Home"

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
    elif any(w in tl for w in ["work","office","meeting","boss","colleague","project","interview"]):
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

    if not prv_cats:
        big = current.get("max_single", 0)
        if big > 500:
            anomalies.append({
                "category":       "General",
                "change_percent": 0,
                "message":        f"Large single transaction detected: ${big:.0f}. Check if this was intentional.",
            })
        return anomalies

    for cat, amt in cur_cats.items():
        if cat not in prv_cats and amt > 0:
            anomalies.append({
                "category":       cat,
                "change_percent": 100,
                "message":        f"New spending category this month: {cat} (${amt:.0f}).",
            })

    for cat, amt in cur_cats.items():
        if cat in prv_cats and prv_cats[cat] > 0:
            pct = (amt - prv_cats[cat]) / prv_cats[cat] * 100
            if pct > 50:
                anomalies.append({
                    "category":       cat,
                    "change_percent": round(pct),
                    "message":        f"{cat} spending rose {pct:.0f}% vs. last month (${prv_cats[cat]:.0f} -> ${amt:.0f}).",
                })

    total = current.get("total", 1) or 1
    big   = current.get("max_single", 0)
    if big > total * 0.4 and big > 200:
        anomalies.append({
            "category":       "General",
            "change_percent": 0,
            "message":        f"One transaction (${big:.0f}) accounts for over 40% of your total spending this month.",
        })

    return anomalies[:3]
