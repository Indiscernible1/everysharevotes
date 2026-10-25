const PLACEHOLDER = "PUBLIC_TURNSTILE_SITE_KEY";

/** Cloudflare's published dummy site keys. They are real keys; they are not production. */
const TEST_SITEKEYS = new Set([
  "1x00000000000000000000AA",
  "2x00000000000000000000AB",
  "1x00000000000000000000BB",
  "2x00000000000000000000BB",
  "3x00000000000000000000FF",
]);

/**
 * A usable Turnstile site key. Empty, whitespace, the literal variable name
 * `PUBLIC_TURNSTILE_SITE_KEY`, and other non-keys are rejected.
 * Production keys look like `0x4AAAAAAABUYP0XeMJF0xoy`.
 */
export function isTurnstileSiteKey(value: string | null | undefined): boolean {
  if (typeof value !== "string") return false;
  const key = value.trim();
  if (!key || key === PLACEHOLDER) return false;
  if (/\s/.test(key)) return false;
  if (TEST_SITEKEYS.has(key)) return true;
  return /^0x[A-Za-z0-9_-]{20,80}$/.test(key);
}

export function usableTurnstileSiteKey(value: string | null | undefined): string {
  if (!isTurnstileSiteKey(value)) return "";
  return (value as string).trim();
}
