#!/usr/bin/env python3
"""Fetch prediction-market and headline series. Never writes a point that was not returned.

Market line: Polymarket YES price for "Tesla and SpaceX merger officially announced
by December 31?" only. Other deadlines and other venues are stored beside it and
are not averaged, because the questions are different.

Media line: GDELT DOC API average tone for the documented query, rescaled for
display. On HTTP 429 the script waits and retries, then tries a shorter article
list. If GDELT still returns nothing, titles from the Google News RSS search are
scored with the same lexicon. If that also fails, points already stored in
sentiment.json are kept and the new attempts are recorded. No day is invented.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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


def normalize_day(value: str) -> str:
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def get_text(url: str, timeout: int = 45) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "everysharevotes.com/1.0 (contact@everysharevotes.com)",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(500).decode("utf-8", "replace")
    except urllib.error.URLError as error:
        return 0, str(error)


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
        date = normalize_day(str(row.get("date") or row.get("datetime") or ""))
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


def fetch_with_backoff(url: str, pauses: tuple[int, ...] = (12, 24)) -> tuple[int, object]:
    status, payload = get_json(url)
    for pause in pauses:
        if status not in (0, 429) and status < 500:
            return status, payload
        print(f"waiting {pause}s after HTTP {status}", flush=True)
        time.sleep(pause)
        status, payload = get_json(url)
    return status, payload


def yes_token(market: dict) -> str | None:
    raw = market.get("clobTokenIds")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(raw, list) and raw:
        token = str(raw[0]).strip()
        return token or None
    return None


def google_news_points() -> tuple[int, str, list[dict]]:
    """Titles from the public Google News RSS search. Scored with the lexicon. No filled days."""
    query = urllib.parse.urlencode(
        {"q": "Tesla SpaceX merger", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    url = f"https://news.google.com/rss/search?{query}"
    status, body = get_text(url)
    if status != 200 or "<item" not in body:
        return status, url, []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return status, url, []
    buckets: dict[str, list[float]] = defaultdict(list)
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        pub = item.findtext("pubDate") or ""
        try:
            day = parsedate_to_datetime(pub).astimezone(timezone.utc).date().isoformat()
        except (TypeError, ValueError, OverflowError):
            continue
        scored = score_title(title)
        if scored is None:
            continue
        buckets[day].append(scored)
    points = []
    for day in sorted(buckets):
        values = buckets[day]
        tone = sum(values) / len(values)
        display = max(0.0, min(100.0, 50 + tone * 50))
        points.append({"date": day, "tone": round(tone, 4), "display": round(display, 2), "articles": len(values)})
    return status, url, points


def manifold_bet_points(market_id: str) -> tuple[int, list[dict]]:
    """Last filled-bet probability per UTC day. Unfilled orders are not prices."""
    before: str | None = None
    bets: list[dict] = []
    status = 0
    for _ in range(5):
        url = f"https://api.manifold.markets/v0/bets?contractId={market_id}&limit=1000"
        if before:
            url += f"&before={urllib.parse.quote(before)}"
        status, payload = get_json(url)
        if not isinstance(payload, list) or not payload:
            break
        bets.extend(row for row in payload if isinstance(row, dict))
        last_id = payload[-1].get("id") if isinstance(payload[-1], dict) else None
        if not isinstance(last_id, str) or len(payload) < 1000:
            break
        before = last_id
        time.sleep(0.3)
    daily: dict[str, tuple[int, float]] = {}
    for bet in bets:
        if bet.get("isCancelled") or not bet.get("isFilled"):
            continue
        try:
            timestamp = int(bet.get("createdTime") or 0)
            probability = float(bet.get("probAfter"))
        except (TypeError, ValueError):
            continue
        if timestamp <= 0 or not 0 <= probability <= 1:
            continue
        millis = timestamp > 10_000_000_000
        day = day_from_unix(timestamp // 1000 if millis else timestamp)
        current = daily.get(day)
        if current is None or timestamp >= current[0]:
            daily[day] = (timestamp, probability)
    points = [{"date": day, "yes": daily[day][1]} for day in sorted(daily)]
    return status, points


def manifold_market(market_id: str) -> dict:
    status, payload = get_json(f"https://api.manifold.markets/v0/market/{market_id}")
    if not isinstance(payload, dict) or "probability" not in payload:
        return {"id": market_id, "status": status, "error": payload}
    history_status, points = manifold_bet_points(market_id)
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
                "yesToken": yes_token(market),
                "closed": market.get("closed"),
                "endDate": market.get("endDate"),
                "url": POLY_PRIMARY_URL if str(market.get("id")) == POLY_MARKET_ID else f"{POLY_EVENT}/{market.get('slug') or ''}",
                "inChart": str(market.get("id")) == POLY_MARKET_ID,
            }
        )
    return markets


def load_previous() -> dict:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_media(previous: dict) -> dict:
    print("waiting 6s before GDELT", flush=True)
    time.sleep(6)
    media_method = "none"
    media_points: list[dict] = []
    media_requests: list[dict] = []
    source = "GDELT DOC 2.0 API"
    source_url = GDELT
    timespan = "3months"

    tone_params = urllib.parse.urlencode(
        {"query": GDELT_QUERY, "mode": "timelinetone", "format": "json", "timespan": "3months"}
    )
    tone_url = f"{GDELT}?{tone_params}"
    tone_status, tone_payload = fetch_with_backoff(tone_url)
    tone_points = media_from_tone(tone_payload)
    media_requests.append({"url": tone_url, "status": tone_status, "points": len(tone_points)})
    if tone_points:
        media_method = "gdelt-tone"
        media_points = tone_points
    else:
        print("waiting 8s before shorter GDELT artlist", flush=True)
        time.sleep(8)
        art_params = urllib.parse.urlencode(
            {
                "query": GDELT_QUERY,
                "mode": "artlist",
                "format": "json",
                "timespan": "14days",
                "maxrecords": "25",
            }
        )
        art_url = f"{GDELT}?{art_params}"
        art_status, art_payload = fetch_with_backoff(art_url, pauses=(20,))
        media_points = media_from_articles(art_payload)
        media_requests.append({"url": art_url, "status": art_status, "points": len(media_points)})
        timespan = "14days"
        if media_points:
            media_method = "title-lexicon"

    cached = False
    cached_from = None
    if not media_points:
        news_status, news_url, news_points = google_news_points()
        media_requests.append({"url": news_url, "status": news_status, "points": len(news_points)})
        if news_points:
            media_method = "google-news-rss-lexicon"
            media_points = news_points
            source = "Google News RSS search, scored with the title lexicon"
            source_url = news_url
            timespan = "rss"
        else:
            old = previous.get("media") if isinstance(previous.get("media"), dict) else {}
            old_points = old.get("points") if isinstance(old, dict) else None
            if isinstance(old_points, list) and old_points:
                media_method = str(old.get("method") or "cached")
                media_points = old_points
                cached = True
                cached_from = previous.get("generatedAt")
                source = str(old.get("source") or source)
                source_url = str(old.get("sourceUrl") or source_url)

    return {
        "method": media_method,
        "query": GDELT_QUERY if media_method != "google-news-rss-lexicon" else "Tesla SpaceX merger",
        "source": source,
        "sourceUrl": source_url,
        "timespan": timespan,
        "requests": media_requests,
        "cached": cached,
        "cachedFrom": cached_from,
        "rescale": "GDELT tone: display = clamp(50 + tone * 5, 0, 100). Title lexicon, including Google News RSS titles: tone is (positive hits - negative hits) / title words, and display = clamp(50 + tone * 50, 0, 100).",
        "lexicon": {"positive": list(POSITIVE), "negative": list(NEGATIVE)},
        "points": media_points,
    }


def main() -> int:
    previous = load_previous()
    generated = datetime.now(timezone.utc).isoformat()
    history_status, history = get_json(POLY_HISTORY)
    points = polymarket_points(history)
    if not points:
        old_primary = ((previous.get("market") or {}) if isinstance(previous.get("market"), dict) else {}).get("primary")
        if isinstance(old_primary, dict) and old_primary.get("points"):
            points = old_primary["points"]
            history_status = old_primary.get("historyStatus", history_status)
    gamma = gamma_markets()
    primary_meta = next((market for market in gamma if market.get("inChart")), None)

    chartable: list[dict] = []
    for market in gamma:
        if market.get("inChart") or not market.get("yesToken"):
            continue
        history_url = (
            "https://clob.polymarket.com/prices-history?market="
            + str(market["yesToken"])
            + "&interval=max&fidelity=1440"
        )
        extra_status, extra_history = get_json(history_url)
        extra_points = polymarket_points(extra_history)
        chartable.append(
            {
                "id": f"polymarket-{market.get('id')}",
                "venue": "Polymarket",
                "question": market.get("question"),
                "url": market.get("url"),
                "historyUrl": history_url,
                "historyStatus": extra_status,
                "asOf": generated,
                "points": extra_points,
                "note": "Separate deadline. Not averaged with the December 31 line.",
            }
        )
        time.sleep(0.4)

    media = fetch_media(previous)

    manifolds = []
    for market_id, fallback_url in MANIFOLD:
        fetched = manifold_market(market_id)
        if "url" not in fetched or not fetched.get("url"):
            fetched["url"] = fallback_url
        manifolds.append(fetched)
        time.sleep(0.4)

    kalshi = kalshi_search()
    for market in manifolds:
        points_for_market = market.get("points") or []
        if market.get("question") and points_for_market:
            chartable.append(
                {
                    "id": f"manifold-{market.get('id')}",
                    "venue": "Manifold",
                    "question": market.get("question"),
                    "url": market.get("url"),
                    "historyStatus": market.get("historyStatus"),
                    "asOf": generated,
                    "points": points_for_market,
                    "note": "Filled-bet history for this Manifold question. Not averaged with Polymarket.",
                }
            )

    chartable_ids = {item.get("question") for item in chartable if item.get("points")}
    venues = []
    for market in gamma:
        if market.get("question"):
            optional = (not market.get("inChart")) and market.get("question") in chartable_ids
            venues.append(
                {
                    "venue": "Polymarket",
                    "question": market.get("question"),
                    "url": market.get("url") or POLY_EVENT,
                    "yes": market.get("yes"),
                    "asOf": generated,
                    "inChart": market.get("inChart"),
                    "chartable": bool(market.get("inChart") or optional),
                    "note": "Default chart line." if market.get("inChart") else (
                        "Own series. Turn it on from the sentiment page. Not averaged."
                        if optional
                        else "No price history returned for this deadline."
                    ),
                }
            )
    for market in manifolds:
        if market.get("question"):
            has_history = bool(market.get("points"))
            venues.append(
                {
                    "venue": "Manifold",
                    "question": market.get("question"),
                    "url": market.get("url"),
                    "yes": market.get("probability"),
                    "asOf": generated,
                    "inChart": False,
                    "chartable": has_history,
                    "historyPoints": len(market.get("points") or []),
                    "note": "Own series from filled bets. Not averaged with Polymarket."
                    if has_history
                    else "No filled-bet history returned. The latest probability is listed and not charted.",
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
        "media": media,
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
                "asOf": generated,
                "points": points,
                "note": "One UTC-day snapshot, the last YES price returned for that day. No days were filled in.",
            },
            "chartable": [item for item in chartable if item.get("points")],
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
        f"wrote {OUT} market-days {len(points)} extra-series {len(document['market']['chartable'])} media-days {len(media['points'])} method {media['method']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
