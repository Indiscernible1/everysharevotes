-- Self-reported share ledger. Rows are signed deltas, not a single vote.
-- ip_hash is a salted SHA-256. The raw address is never stored.
-- status: counted (in the public totals), held (over the review cap), rejected (dropped by review).

CREATE TABLE IF NOT EXISTS share_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  ip_hash TEXT NOT NULL,
  browser_token TEXT NOT NULL,
  broker TEXT NOT NULL,
  stance TEXT NOT NULL CHECK (stance IN ('for', 'against', 'undecided')),
  share_delta INTEGER NOT NULL CHECK (share_delta != 0),
  status TEXT NOT NULL CHECK (status IN ('counted', 'held', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_share_entries_identity
  ON share_entries (ip_hash, browser_token, broker, stance, status);

CREATE INDEX IF NOT EXISTS idx_share_entries_dup
  ON share_entries (ip_hash, browser_token, broker, share_delta);

CREATE INDEX IF NOT EXISTS idx_share_entries_created
  ON share_entries (created_at);

CREATE TABLE IF NOT EXISTS share_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_share_attempts_ip
  ON share_attempts (ip_hash, created_at);
