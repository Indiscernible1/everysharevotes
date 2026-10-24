-- Unscientific one-response-per-browser poll.
-- voter_id is a random id stored in an HttpOnly cookie, not an account.

CREATE TABLE IF NOT EXISTS votes (
  voter_id TEXT PRIMARY KEY,
  choice TEXT NOT NULL CHECK (choice IN ('favor', 'against', 'undecided')),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_votes_choice ON votes (choice);
