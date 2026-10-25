/**
 * Public runtime config. The Turnstile site key is not a secret.
 * Pages Functions read PUBLIC_TURNSTILE_SITE_KEY from the deployment env,
 * so correcting that variable does not require baking it into the HTML.
 */

import { usableTurnstileSiteKey } from "../../src/lib/turnstile-sitekey";

interface Env {
  PUBLIC_TURNSTILE_SITE_KEY?: string;
}

interface PagesContext {
  env: Env;
}

export function onRequestGet(context: PagesContext): Response {
  const turnstileSiteKey = usableTurnstileSiteKey(context.env.PUBLIC_TURNSTILE_SITE_KEY);
  return new Response(JSON.stringify({ turnstileSiteKey }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
