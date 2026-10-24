/**
 * Self-reported share ledger for a possible SpaceX combination.
 *
 * A holder adds a signed share change at one broker. +60 at Schwab and later
 * +50 at Webull are two rows. -20 at Schwab reduces that stance. The same
 * hashed address, browser token, broker, and signed delta is rejected once.
 * The net of counted rows for one identity, broker, and stance cannot go
 * below zero. An absolute change above 100,000 shares is stored as "held"
 * and left out of the public totals.
 *
 * The raw IP address is never stored. Turnstile and the hash salt are required
 * outside localhost. The Cloudflare test secret is rejected on any other host.
 */

interface D1Prepared {
  bind(...values: unknown[]): D1Prepared;
  first<T>(): Promise<T | null>;
  all<T>(): Promise<{ results: T[] }>;
  run(): Promise<unknown>;
}

interface D1Database {
  prepare(query: string): D1Prepared;
}

interface Env {
  DB?: D1Database;
  IP_HASH_SALT?: string;
  TURNSTILE_SECRET_KEY?: string;
}

interface PagesContext {
  request: Request;
  env: Env;
}

const BROKERS = [
  "Schwab",
  "Fidelity",
  "Robinhood",
  "Webull",
  "E*TRADE/Morgan Stanley",
  "Vanguard",
  "Interactive Brokers",
  "Merrill",
  "SoFi",
  "Public",
  "Other",
] as const;

const STANCES = ["for", "against", "undecided"] as const;
type Stance = (typeof STANCES)[number];

const COOKIE = "esv_browser";
const MAX_AGE = 60 * 60 * 24 * 400;
const HOLD_ABOVE = 100_000;
const MAX_ABS = 1_000_000_000;
const HOUR_LIMIT = 8;
const DAY_LIMIT = 30;
const TEST_SECRET = "1x0000000000000000000000000000000AA";

export async function onRequestGet(context: PagesContext): Promise<Response> {
  const db = context.env.DB;
  if (!db) return json({ error: "unconfigured", message: "D1 binding DB is missing." }, 503);
  const salt = context.env.IP_HASH_SALT;
  const secure = new URL(context.request.url).protocol === "https:";
  const token = await ensureToken(context.request);
  let yours: Entry[] = [];
  if (salt && token.token) {
    const ip = clientIp(context.request);
    if (ip) {
      const ipHash = await sha256(`${salt}|${ip}`);
      yours = await ownEntries(db, ipHash, token.token);
    }
  }
  const totals = await publicTotals(db);
  return json({ ...totals, yours, selfReported: true, unverified: true }, 200, token.cookie && token.set ? cookieHeader(token.token, secure) : undefined);
}

export async function onRequestPost(context: PagesContext): Promise<Response> {
  const db = context.env.DB;
  const salt = context.env.IP_HASH_SALT?.trim();
  const secret = context.env.TURNSTILE_SECRET_KEY?.trim();
  if (!db) return json({ error: "unconfigured", message: "D1 binding DB is missing." }, 503);
  if (!salt) return json({ error: "unconfigured", message: "IP_HASH_SALT is not set." }, 503);
  if (!secret) return json({ error: "unconfigured", message: "TURNSTILE_SECRET_KEY is not set." }, 503);

  const url = new URL(context.request.url);
  const local = isLocalHost(url.hostname);
  if (secret === TEST_SECRET && !local) {
    return json({ error: "unconfigured", message: "The Turnstile test secret only works on localhost." }, 503);
  }

  const parsed = await readBody(context.request);
  if (parsed instanceof Response) return parsed;

  const ip = clientIp(context.request);
  if (!ip) return json({ error: "missing_ip" }, 400);
  const ipHash = await sha256(`${salt}|${ip}`);
  const token = await ensureToken(context.request);
  const secure = url.protocol === "https:";
  const now = new Date();
  const nowIso = now.toISOString();

  const limited = await rateLimit(db, ipHash, now);
  if (limited) return limited;

  const verified = await verifyTurnstile(secret, parsed.turnstileToken, ip);
  if (!verified) return json({ error: "turnstile" }, 403);

  const duplicate = await db
    .prepare(
      `SELECT id FROM share_entries
       WHERE ip_hash = ? AND browser_token = ? AND broker = ? AND share_delta = ?
         AND status IN ('counted', 'held')
       LIMIT 1`,
    )
    .bind(ipHash, token.token, parsed.broker, parsed.shares)
    .first<{ id: number }>();
  if (duplicate) {
    return json(
      { error: "duplicate", message: "That share change at that broker is already stored for this browser." },
      409,
      token.set ? cookieHeader(token.token, secure) : undefined,
    );
  }

  const current = await db
    .prepare(
      `SELECT COALESCE(SUM(share_delta), 0) AS net FROM share_entries
       WHERE ip_hash = ? AND browser_token = ? AND broker = ? AND stance = ? AND status = 'counted'`,
    )
    .bind(ipHash, token.token, parsed.broker, parsed.stance)
    .first<{ net: number }>();
  const net = Number(current?.net ?? 0);
  if (net + parsed.shares < 0) {
    return json(
      {
        error: "below_zero",
        message: "That would take the counted shares for this broker and stance below zero. Held rows are not in the counted total.",
        counted: net,
      },
      400,
      token.set ? cookieHeader(token.token, secure) : undefined,
    );
  }

  const status = Math.abs(parsed.shares) > HOLD_ABOVE ? "held" : "counted";
  await db
    .prepare(
      `INSERT INTO share_entries
        (created_at, ip_hash, browser_token, broker, stance, share_delta, status)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(nowIso, ipHash, token.token, parsed.broker, parsed.stance, parsed.shares, status)
    .run();

  const totals = await publicTotals(db);
  const yours = await ownEntries(db, ipHash, token.token);
  return json(
    {
      ...totals,
      yours,
      stored: { status, stance: parsed.stance, broker: parsed.broker, shares: parsed.shares },
      selfReported: true,
      unverified: true,
    },
    200,
    token.set ? cookieHeader(token.token, secure) : undefined,
  );
}

async function publicTotals(db: D1Database) {
  const sums = await db
    .prepare(
      `SELECT stance, SUM(share_delta) AS shares
       FROM share_entries WHERE status = 'counted' GROUP BY stance`,
    )
    .all<{ stance: Stance; shares: number }>();
  const totals = { for: 0, against: 0, undecided: 0 };
  for (const row of sums.results) {
    if (row.stance === "for" || row.stance === "against" || row.stance === "undecided") {
      totals[row.stance] = Number(row.shares);
    }
  }
  const holdersRow = await db
    .prepare(
      `SELECT COUNT(*) AS n FROM (
         SELECT ip_hash, browser_token FROM share_entries
         WHERE status = 'counted'
         GROUP BY ip_hash, browser_token
         HAVING SUM(share_delta) > 0
       )`,
    )
    .first<{ n: number }>();
  const brokers = await db
    .prepare(
      `SELECT broker, stance, SUM(share_delta) AS shares
       FROM share_entries WHERE status = 'counted'
       GROUP BY broker, stance
       HAVING SUM(share_delta) != 0`,
    )
    .all<{ broker: string; stance: Stance; shares: number }>();
  const byBrokerMap = new Map<string, { broker: string; for: number; against: number; undecided: number }>();
  for (const row of brokers.results) {
    const bucket = byBrokerMap.get(row.broker) ?? { broker: row.broker, for: 0, against: 0, undecided: 0 };
    if (row.stance === "for" || row.stance === "against" || row.stance === "undecided") {
      bucket[row.stance] = Number(row.shares);
    }
    byBrokerMap.set(row.broker, bucket);
  }
  const days = await db
    .prepare(
      `SELECT substr(created_at, 1, 10) AS day,
              SUM(CASE WHEN stance = 'for' THEN share_delta ELSE 0 END) AS for_shares,
              SUM(CASE WHEN stance = 'against' THEN share_delta ELSE 0 END) AS against_shares,
              SUM(CASE WHEN stance = 'undecided' THEN share_delta ELSE 0 END) AS undecided_shares
       FROM share_entries
       WHERE status = 'counted'
       GROUP BY substr(created_at, 1, 10)
       ORDER BY day`,
    )
    .all<{ day: string; for_shares: number; against_shares: number; undecided_shares: number }>();
  const series: SeriesPoint[] = [];
  let running = { for: 0, against: 0, undecided: 0 };
  for (const row of days.results) {
    running = {
      for: running.for + Number(row.for_shares),
      against: running.against + Number(row.against_shares),
      undecided: running.undecided + Number(row.undecided_shares),
    };
    series.push(point(row.day, running, false));
  }
  const today = new Date().toISOString().slice(0, 10);
  if (series.length > 0 && series[series.length - 1].date < today) {
    series.push(point(today, running, true));
  }
  const held = await db
    .prepare("SELECT COUNT(*) AS n FROM share_entries WHERE status = 'held'")
    .first<{ n: number }>();
  return {
    totals,
    holders: Number(holdersRow?.n ?? 0),
    byBroker: [...byBrokerMap.values()],
    series,
    heldCount: Number(held?.n ?? 0),
  };
}

function point(
  date: string,
  totals: { for: number; against: number; undecided: number },
  carriedForward: boolean,
): SeriesPoint {
  const denom = totals.for + totals.against;
  return {
    date,
    for: totals.for,
    against: totals.against,
    undecided: totals.undecided,
    pctFor: denom > 0 ? (totals.for / denom) * 100 : null,
    carriedForward,
  };
}

interface SeriesPoint {
  date: string;
  for: number;
  against: number;
  undecided: number;
  pctFor: number | null;
  carriedForward: boolean;
}

interface Entry {
  id: number;
  createdAt: string;
  broker: string;
  stance: Stance;
  shares: number;
  status: string;
}

async function ownEntries(db: D1Database, ipHash: string, token: string): Promise<Entry[]> {
  const rows = await db
    .prepare(
      `SELECT id, created_at, broker, stance, share_delta, status
       FROM share_entries
       WHERE ip_hash = ? AND browser_token = ?
       ORDER BY id DESC
       LIMIT 50`,
    )
    .bind(ipHash, token)
    .all<{ id: number; created_at: string; broker: string; stance: Stance; share_delta: number; status: string }>();
  return rows.results.map((row) => ({
    id: row.id,
    createdAt: row.created_at,
    broker: row.broker,
    stance: row.stance,
    shares: Number(row.share_delta),
    status: row.status,
  }));
}

async function rateLimit(db: D1Database, ipHash: string, now: Date): Promise<Response | null> {
  const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  const hourAgo = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
  const pruneBefore = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString();
  await db.prepare("DELETE FROM share_attempts WHERE ip_hash = ? AND created_at < ?").bind(ipHash, pruneBefore).run();
  const counts = await db
    .prepare(
      `SELECT
         SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS hour_n,
         SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS day_n
       FROM share_attempts WHERE ip_hash = ?`,
    )
    .bind(hourAgo, dayAgo, ipHash)
    .first<{ hour_n: number; day_n: number }>();
  if (Number(counts?.hour_n ?? 0) >= HOUR_LIMIT || Number(counts?.day_n ?? 0) >= DAY_LIMIT) {
    return json({ error: "rate_limit", message: "Too many submissions from this network. Try again later." }, 429);
  }
  await db.prepare("INSERT INTO share_attempts (ip_hash, created_at) VALUES (?, ?)").bind(ipHash, now.toISOString()).run();
  return null;
}

async function verifyTurnstile(secret: string, token: string, ip: string): Promise<boolean> {
  const body = new URLSearchParams();
  body.set("secret", secret);
  body.set("response", token);
  body.set("remoteip", ip);
  try {
    const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body,
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as { success?: boolean };
    return payload.success === true;
  } catch {
    return false;
  }
}

interface Submission {
  stance: Stance;
  broker: (typeof BROKERS)[number];
  shares: number;
  turnstileToken: string;
}

async function readBody(request: Request): Promise<Submission | Response> {
  const length = Number(request.headers.get("content-length") || "0");
  if (length > 4000) return json({ error: "too_large" }, 413);
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!body || typeof body !== "object") return json({ error: "invalid_json" }, 400);
  const record = body as Record<string, unknown>;
  const stance = record.stance;
  const broker = record.broker;
  const shares = record.shares;
  const turnstileToken = record.turnstileToken;
  if (stance !== "for" && stance !== "against" && stance !== "undecided") {
    return json({ error: "invalid_stance" }, 400);
  }
  if (typeof broker !== "string" || !BROKERS.includes(broker as (typeof BROKERS)[number])) {
    return json({ error: "invalid_broker" }, 400);
  }
  if (typeof shares !== "number" || !Number.isSafeInteger(shares) || shares === 0 || Math.abs(shares) > MAX_ABS) {
    return json({ error: "invalid_shares" }, 400);
  }
  if (typeof turnstileToken !== "string" || turnstileToken.length < 8 || turnstileToken.length > 2048) {
    return json({ error: "turnstile" }, 400);
  }
  return { stance, broker: broker as (typeof BROKERS)[number], shares, turnstileToken };
}

function clientIp(request: Request): string {
  const header = request.headers.get("cf-connecting-ip")?.trim();
  if (header) return header;
  const host = new URL(request.url).hostname;
  if (isLocalHost(host)) return "127.0.0.1";
  return "";
}

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function ensureToken(request: Request): Promise<{ token: string; set: boolean; cookie: boolean }> {
  const existing = readCookie(request.headers.get("cookie"), COOKIE);
  if (existing && isUuid(existing)) return { token: existing, set: false, cookie: true };
  return { token: crypto.randomUUID(), set: true, cookie: true };
}

function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() === name) return decodeURIComponent(part.slice(separator + 1).trim());
  }
  return null;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function cookieHeader(token: string, secure: boolean): string {
  const parts = [`${COOKIE}=${token}`, "HttpOnly", "SameSite=Lax", "Path=/", `Max-Age=${MAX_AGE}`];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}

function json(payload: unknown, status: number, setCookie?: string): Response {
  const headers: Record<string, string> = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  };
  if (setCookie) headers["set-cookie"] = setCookie;
  return new Response(JSON.stringify(payload), { status, headers });
}
