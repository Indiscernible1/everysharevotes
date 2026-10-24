#!/usr/bin/env python3
"""Fetch prediction-market and headline series. Never writes a point that was not returned.

Market line: Polymarket YES price for "Tesla and SpaceX merger officially announced
by December 31?" only. Other deadlines and other venues are stored beside it and
are not averaged, because the questions are different.

Media line: GDELT DOC API average tone for the documented query, rescaled for
display. If GDELT returns no tone series, titles from the article list are scored
with the lexicon in this file. If neither call returns articles, the series is empty.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "data" / "sentiment.json"

POLY_TOKEN = "54008746047030401937229622392846672148881831664328316511258982815120785809185"
POLY_MARKET_ID = "2252540"
POLY_QUESTION = "Tesla and SpaceX merger officially announced by December 31?"
POLY_EVENT = "https://polymarket.com/event/tesla-and-spacex-merger-officially-announced-by-june-30"
POLY_PRIMARY_URL = (
    POLY_EVENT + "/tesla-and-spacex-merger-officially-announced-by-december-31"
)
POLY_HISTORY = (
    "https://clob.polymarket.com/prices-history?market="
    + POLY_TOKEN
    + "&interval=max&fidelity=1440"
)
GAMMA_EVENT = "https://gamma-api.polymarket.com/events/192962"

MANIFOLD = [
    ("EN9qAdzp9A", "https://manifold.markets/BarryJones/will-tesla-and-spacex-officially-an"),
    ("6zSLgNQR2E", "https://manifold.markets/browse?q=SpaceX%20Tesla%20Merger"),
    ("s5sARpupPO", "https://manifold.markets/browse?q=SpaceX%20Tesla"),
]

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = '"Tesla" "SpaceX" merger'
POSITIVE = (
    "approve",
    "approved",
    "approves",
    "support",
    "supports",
    "supported",
    "back",
    "backs",
    "backed",
    "win",
    "wins",
    "agree",
    "agrees",
    "synergy",
    "synergies",
    "optimistic",
    "rally",
    "rallies",
    "surge",
    "surges",
)
NEGATIVE = (
    "against",
    "oppose",
    "opposes",
    "opposed",
    "reject",
    "rejects",
    "rejected",
    "block",
    "blocks",
    "blocked",
    "dilution",
    "dilutive",
    "conflict",
    "conflicts",
    "sue",
    "sues",
    "lawsuit",
    "fail",
    "fails",
    "failed",
    "worry",
    "worries",
    "risk",
    "risks",
    "crash",
    "plunge",
    "plunges",
)


def get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> tuple[int, object]:
    request = urllib.request.Request(url, headers={"User-Agent": "everysharevotes.com/1.0 (contact@everysharevotes.com)", "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            if not body.strip():
                return response.status, None
            return response.status, json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read()[:500].decode("utf-8", "replace")
        return error.code, {"error": detail}
    except urllib.error.URLError as error:
        return 0, {"error": str(error)}


def day_from_unix(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


def polymarket_points(history: object) -> list[dict]:
    rows = []
    if isinstance(history, dict):
        rows = history.get("history") or []
    daily: dict[str, tuple[int, float]] = {}
    for row in rows:
        if not isinstance(row, dict) or "t" not in row or "p" not in row:
            continue
        try:
            timestamp = int(row["t"])
            price = float(row["p"])
        except (TypeError, ValueError):
            continue
        if not 0 <= price <= 1:
            continue
        day = day_from_unix(timestamp)
        current = daily.get(day)
        if current is None or timestamp >= current[0]:
            daily[day] = (timestamp, price)
    return [{"date": day, "yes": daily[day][1]} for day in sorted(daily)]


def clamp_display(tone: float) -> float:
    value = 50 + tone * 5
    return max(0.0, min(100.0, value))


def score_title(title: str) -> float | None:
    words = [token.strip(".,:;!?\"'()[]").lower() for token in title.split()]
    words = [word for word in words if word]
    if not words:
        return None
    pos = sum(1 for word in words if word in POSITIVE)
    neg = sum(1 for word in words if word in NEGATIVE)
    if pos == 0 and neg == 0:
        return 0.0
    return (pos - neg) / max(len(words), 1)


def media_from_tone(payload: object) -> list[dict]:
    """GDELT timelinetone returns a timeline array when it has data."""
    if not isinstance(payload, dict):
        return []
    timeline = payload.get("timeline") or payload.get("data") or []
    if isinstance(timeline, dict):
        timeline = timeline.get("data") or timeline.get("timeline") or []
    points = []
    if not isinstance(timeline, list):
        return []
    for row in timeline:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or row.get("datetime") or "")[:10]
        tone = row.get("value")
        if tone is None:
            tone = row.get("tone")
        try:
            tone_value = float(tone)
        except (TypeError, ValueError):
            continue
        if len(date) != 10:
            continue
        points.append(
            {
                "date": date,
                "tone": tone_value,
                "display": round(clamp_display(tone_value), 2),
                "articles": row.get("count"),
            }
        )
    return points


def media_from_articles(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    articles = payload.get("articles") or []
    if not isinstance(articles, list):
        return []
    buckets: dict[str, list[float]] = defaultdict(list)
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "")
        seen = str(article.get("seendate") or article.get("date") or "")
        # GDELT seendate looks like 20261023T120000Z
        digits = "".join(ch for ch in seen if ch.isdigit())
        if len(digits) < 8:
            continue
        day = f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
        scored = score_title(title)
        if scored is None:
            continue
        buckets[day].append(scored)
    points = []
    for day in sorted(buckets):
        values = buckets[day]
        tone = sum(values) / len(values)
        # Lexicon tone is already about -1..1. Map with the same 50 + tone*50 center,
        # and store it in `tone` so the page can say which scale was used.
        display = max(0.0, min(100.0, 50 + tone * 50))
        points.append({"date": day, "tone": round(tone, 4), "display": round(display, 2), "articles": len(values)})
    return points


def manifold_market(market_id: str) -> dict:
    status, payload = get_json(f"https://api.manifold.markets/v0/market/{market_id}")
    if not isinstance(payload, dict) or "probability" not in payload:
        return {"id": market_id, "status": status, "error": payload}
    history_status, history = get_json(f"https://api.manifold.markets/v0/market/{market_id}/prob-history")
    points = []
    if isinstance(history, list):
        daily: dict[str, tuple[int, float]] = {}
        for row in history:
            if not isinstance(row, dict):
                continue
            try:
                timestamp = int(row.get("timestamp") or row.get("createdTime") or 0)
                probability = float(row.get("probability") if "probability" in row else row.get("p"))
            except (TypeError, ValueError):
                continue
            if timestamp <= 0 or not 0 <= probability <= 1:
                continue
            day = day_from_unix(timestamp // 1000 if timestamp > 10_000_000_000 else timestamp)
            current = daily.get(day)
            if current is None or timestamp >= current[0]:
                daily[day] = (timestamp, probability)
        points = [{"date": day, "yes": daily[day][1]} for day in sorted(daily)]
    return {
        "id": market_id,
        "status": status,
        "question": payload.get("question"),
        "url": payload.get("url"),
        "probability": payload.get("probability"),
        "closeTime": payload.get("closeTime"),
        "historyStatus": history_status,
        "points": points,
    }


def kalshi_search() -> dict:
    queries = [
        "https://api.elections.kalshi.com/trade-api/v2/events?limit=200&status=open&with_nested_markets=true",
        "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open",
    ]
    notes = []
    matches = []
    for url in queries:
        status, payload = get_json(url)
        notes.append({"url": url, "status": status})
        events = []
        if isinstance(payload, dict):
            events = payload.get("events") or payload.get("markets") or []
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            blob = json.dumps(event).lower()
            if "spacex" in blob and ("merger" in blob or "combination" in blob or "tesla" in blob):
                matches.append(
                    {
                        "title": event.get("title") or event.get("event_ticker") or event.get("ticker"),
                        "ticker": event.get("event_ticker") or event.get("ticker"),
                    }
                )
        time.sleep(0.3)
    return {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "queries": notes,
        "matches": matches,
        "status": "found" if matches else "no-market",
    }


def gamma_markets() -> list[dict]:
    status, payload = get_json(GAMMA_EVENT)
    markets = []
    if not isinstance(payload, dict):
        return [{"status": status, "error": payload}]
    for market in payload.get("markets") or []:
        if not isinstance(market, dict):
            continue
        prices = market.get("outcomePrices")
        yes = None
        if isinstance(prices, str):
            try:
                parsed = json.loads(prices)
                yes = float(parsed[0]) if parsed else None
            except (json.JSONDecodeError, TypeError, ValueError, IndexError):
                yes = None
        elif isinstance(prices, list) and prices:
            try:
                yes = float(prices[0])
            except (TypeError, ValueError):
                yes = None
        markets.append(
            {
                "venue": "Polymarket",
                "id": market.get("id"),
                "question": market.get("question"),
                "slug": market.get("slug"),
                "yes": yes,
                "closed": market.get("closed"),
                "endDate": market.get("endDate"),
                "url": POLY_PRIMARY_URL if str(market.get("id")) == POLY_MARKET_ID else f"{POLY_EVENT}/{market.get('slug') or ''}",
                "inChart": str(market.get("id")) == POLY_MARKET_ID,
            }
        )
    return markets


def main() -> int:
    generated = datetime.now(timezone.utc).isoformat()
    history_status, history = get_json(POLY_HISTORY)
    points = polymarket_points(history)
    gamma = gamma_markets()
    primary_meta = next((market for market in gamma if market.get("inChart")), None)

    print("waiting 6s before GDELT", flush=True)
    time.sleep(6)
    tone_params = urllib.parse.urlencode(
        {"query": GDELT_QUERY, "mode": "timelinetone", "format": "json", "timespan": "3months"}
    )
    tone_url = f"{GDELT}?{tone_params}"
    tone_status, tone_payload = get_json(tone_url)
    tone_points = media_from_tone(tone_payload)
    media_method = "none"
    media_points: list[dict] = []
    media_requests = [{"url": tone_url, "status": tone_status, "points": len(tone_points)}]
    art_url = ""
    if tone_points:
        media_method = "gdelt-tone"
        media_points = tone_points
    else:
        print("waiting 6s before GDELT artlist", flush=True)
        time.sleep(6)
        art_params = urllib.parse.urlencode(
            {"query": GDELT_QUERY, "mode": "artlist", "format": "json", "timespan": "3months", "maxrecords": "75"}
        )
        art_url = f"{GDELT}?{art_params}"
        art_status, art_payload = get_json(art_url)
        media_points = media_from_articles(art_payload)
        media_requests.append({"url": art_url, "status": art_status, "points": len(media_points)})
        if media_points:
            media_method = "title-lexicon"

    manifolds = []
    for market_id, fallback_url in MANIFOLD:
        fetched = manifold_market(market_id)
        if "url" not in fetched or not fetched.get("url"):
            fetched["url"] = fallback_url
        manifolds.append(fetched)
        time.sleep(0.4)

    kalshi = kalshi_search()
    venues = []
    for market in gamma:
        if market.get("question"):
            venues.append(
                {
                    "venue": "Polymarket",
                    "question": market.get("question"),
                    "url": market.get("url") or POLY_EVENT,
                    "yes": market.get("yes"),
                    "asOf": generated,
                    "inChart": market.get("inChart"),
                    "note": "Charted YES price." if market.get("inChart") else "Different deadline. Not included in the chart line.",
                }
            )
    for market in manifolds:
        if market.get("question"):
            venues.append(
                {
                    "venue": "Manifold",
                    "question": market.get("question"),
                    "url": market.get("url"),
                    "yes": market.get("probability"),
                    "asOf": generated,
                    "inChart": False,
                    "historyPoints": len(market.get("points") or []),
                    "note": "Stored as its own question. Not averaged with Polymarket.",
                }
            )
    venues.append(
        {
            "venue": "Kalshi",
            "question": None,
            "status": kalshi["status"],
            "asOf": kalshi["checkedAt"],
            "inChart": False,
            "matches": kalshi["matches"],
            "note": "No open Kalshi market matching SpaceX and a Tesla combination was in the queried pages."
            if kalshi["status"] == "no-market"
            else "A Kalshi title matched the search. It is listed and not blended into the Polymarket line.",
        }
    )

    document = {
        "generatedAt": generated,
        "media": {
            "method": media_method,
            "query": GDELT_QUERY,
            "source": "GDELT DOC 2.0 API",
            "sourceUrl": GDELT,
            "timespan": "3months",
            "requests": media_requests,
            "rescale": "GDELT tone: display = clamp(50 + tone * 5, 0, 100). Title lexicon: tone is (positive hits - negative hits) / title words, and display = clamp(50 + tone * 50, 0, 100).",
            "lexicon": {"positive": list(POSITIVE), "negative": list(NEGATIVE)},
            "points": media_points,
        },
        "market": {
            "primary": None
            if not points
            else {
                "venue": "Polymarket",
                "question": (primary_meta or {}).get("question") or POLY_QUESTION,
                "marketId": POLY_MARKET_ID,
                "tokenId": POLY_TOKEN,
                "url": POLY_PRIMARY_URL,
                "historyUrl": POLY_HISTORY,
                "historyStatus": history_status,
                "points": points,
                "note": "One UTC-day snapshot, the last YES price returned for that day. No days were filled in.",
            },
            "venues": venues,
            "manifoldHistory": [
                {"id": market.get("id"), "points": market.get("points") or [], "historyStatus": market.get("historyStatus")}
                for market in manifolds
                if market.get("points")
            ],
            "kalshi": kalshi,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, indent=2) + "\n")
    print(
        f"wrote {OUT} market-days {len(points)} media-days {len(media_points)} method {media_method}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
