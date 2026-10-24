/**
 * Optional review for entries held because they exceed 100,000 shares.
 * Send header x-review-token matching ADMIN_REVIEW_TOKEN.
 * Body: { "id": 1, "decision": "counted" | "rejected" }
 * The response does not include IP hashes or browser tokens.
 */

interface D1Prepared {
  bind(...values: unknown[]): D1Prepared;
  first<T>(): Promise<T | null>;
  run(): Promise<unknown>;
}

interface D1Database {
  prepare(query: string): D1Prepared;
}

interface Env {
  DB?: D1Database;
  ADMIN_REVIEW_TOKEN?: string;
}

interface PagesContext {
  request: Request;
  env: Env;
}

export async function onRequestPost(context: PagesContext): Promise<Response> {
  const expected = context.env.ADMIN_REVIEW_TOKEN?.trim();
  const db = context.env.DB;
  if (!expected || !db) {
    return json({ error: "unconfigured" }, 503);
  }
  const provided = context.request.headers.get("x-review-token") || "";
  if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) {
    return json({ error: "forbidden" }, 403);
  }
  let body: unknown;
  try {
    body = await context.request.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const record = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const id = record.id;
  const decision = record.decision;
  if (typeof id !== "number" || !Number.isSafeInteger(id) || id < 1) return json({ error: "invalid_id" }, 400);
  if (decision !== "counted" && decision !== "rejected") return json({ error: "invalid_decision" }, 400);

  const row = await db
    .prepare("SELECT id, status, share_delta, ip_hash, browser_token, broker, stance FROM share_entries WHERE id = ?")
    .bind(id)
    .first<{
      id: number;
      status: string;
      share_delta: number;
      ip_hash: string;
      browser_token: string;
      broker: string;
      stance: string;
    }>();
  if (!row) return json({ error: "not_found" }, 404);
  if (row.status !== "held") return json({ error: "not_held" }, 409);

  if (decision === "counted") {
    const current = await db
      .prepare(
        `SELECT COALESCE(SUM(share_delta), 0) AS net FROM share_entries
         WHERE ip_hash = ? AND browser_token = ? AND broker = ? AND stance = ? AND status = 'counted'`,
      )
      .bind(row.ip_hash, row.browser_token, row.broker, row.stance)
      .first<{ net: number }>();
    if (Number(current?.net ?? 0) + Number(row.share_delta) < 0) {
      return json({ error: "below_zero" }, 400);
    }
  }

  await db.prepare("UPDATE share_entries SET status = ? WHERE id = ? AND status = 'held'").bind(decision, id).run();
  return json({ id, status: decision }, 200);
}

function timingSafeEqual(left: string, right: string): boolean {
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) {
    mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return mismatch === 0;
}

function json(payload: unknown, status: number): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
