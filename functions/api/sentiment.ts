/**
 * Unscientific sentiment poll.
 *
 * One stored response per browser: an HttpOnly cookie holds a random id,
 * and that id is the primary key in D1. Clearing site data allows another
 * response. This is not a share vote and not a scientific sample.
 *
 * Binding: D1 database, name DB. See wrangler.toml and the README.
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
}

interface PagesContext {
  request: Request;
  env: Env;
}

const CHOICES = ["favor", "against", "undecided"] as const;
type Choice = (typeof CHOICES)[number];

const QUESTION =
  "If TSLA shareholders are asked to vote on a combination with SpaceX, which way do you lean today?";

const COOKIE = "esv_voter";
const MAX_AGE = 60 * 60 * 24 * 400;

export async function onRequestGet(context: PagesContext): Promise<Response> {
  return handle(context, false);
}

export async function onRequestPost(context: PagesContext): Promise<Response> {
  return handle(context, true);
}

async function handle(context: PagesContext, isPost: boolean): Promise<Response> {
  const db = context.env.DB;
  if (!db) {
    return json(
      {
        error: "unconfigured",
        message:
          "The poll database is not bound. Create the D1 database, apply migrations/0001_sentiment.sql, and bind it as DB.",
      },
      503,
    );
  }

  const secure = new URL(context.request.url).protocol === "https:";
  let voterId = readCookie(context.request.headers.get("cookie"), COOKIE);
  let setCookie = false;
  if (!voterId || !isUuid(voterId)) {
    voterId = crypto.randomUUID();
    setCookie = true;
  }

  if (isPost) {
    const choice = await readChoice(context.request);
    if (choice instanceof Response) return choice;
    await db
      .prepare("INSERT OR IGNORE INTO votes (voter_id, choice, created_at) VALUES (?, ?, ?)")
      .bind(voterId, choice, new Date().toISOString())
      .run();
    setCookie = true;
  }

  const yourChoice = await db
    .prepare("SELECT choice FROM votes WHERE voter_id = ?")
    .bind(voterId)
    .first<{ choice: Choice }>();
  const counts = await db
    .prepare("SELECT choice, COUNT(*) AS n FROM votes GROUP BY choice")
    .all<{ choice: Choice; n: number }>();

  const tallies = { favor: 0, against: 0, undecided: 0, total: 0 };
  for (const row of counts.results) {
    if (row.choice === "favor" || row.choice === "against" || row.choice === "undecided") {
      const n = Number(row.n);
      tallies[row.choice] = n;
      tallies.total += n;
    }
  }

  return json(
    {
      question: QUESTION,
      unscientific: true,
      tallies,
      yourChoice: yourChoice?.choice ?? null,
      voted: Boolean(yourChoice),
    },
    200,
    setCookie ? cookieHeader(voterId, secure) : undefined,
  );
}

async function readChoice(request: Request): Promise<Choice | Response> {
  const length = Number(request.headers.get("content-length") || "0");
  if (length > 2000) {
    return json({ error: "too_large" }, 413);
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const choice = typeof body === "object" && body && "choice" in body ? (body as { choice: unknown }).choice : null;
  if (choice !== "favor" && choice !== "against" && choice !== "undecided") {
    return json({ error: "invalid_choice" }, 400);
  }
  return choice;
}

function readCookie(header: string | null, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    const key = part.slice(0, separator).trim();
    if (key === name) return part.slice(separator + 1).trim();
  }
  return null;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function cookieHeader(voterId: string, secure: boolean): string {
  const parts = [
    `${COOKIE}=${voterId}`,
    "HttpOnly",
    "SameSite=Lax",
    "Path=/",
    `Max-Age=${MAX_AGE}`,
  ];
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
