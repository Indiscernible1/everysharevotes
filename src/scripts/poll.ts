type Choice = "favor" | "against" | "undecided";

type PollResponse = {
  question?: string;
  tallies?: { favor: number; against: number; undecided: number; total: number };
  yourChoice?: Choice | null;
  voted?: boolean;
  error?: string;
  message?: string;
};

const labels: Record<Choice, string> = {
  favor: "Lean in favor",
  against: "Lean against",
  undecided: "Undecided",
};

export function mountPoll(): void {
  const form = document.querySelector<HTMLFormElement>("#poll-form");
  const results = document.querySelector<HTMLElement>("#poll-results");
  const status = document.querySelector<HTMLElement>("#poll-status");
  if (!form || !results || !status) return;

  const paint = (payload: PollResponse) => {
    if (payload.error === "unconfigured") {
      status.textContent = payload.message ?? "The poll database is not configured.";
      results.replaceChildren();
      return;
    }
    if (!payload.tallies) {
      status.textContent = "The poll did not return a tally.";
      return;
    }
    status.textContent = payload.voted
      ? `Your response is stored in this browser: ${labels[payload.yourChoice as Choice]}.`
      : payload.tallies.total === 0
        ? "No responses yet."
        : `${payload.tallies.total} responses stored. This is not a scientific sample.`;
    if (payload.voted) {
      form.querySelectorAll<HTMLInputElement>("input").forEach((input) => {
        input.disabled = true;
      });
      const submit = form.querySelector<HTMLButtonElement>("button[type=submit]");
      if (submit) submit.hidden = true;
    }
    results.replaceChildren(
      ...(["favor", "against", "undecided"] as Choice[]).map((choice) => {
        const row = document.createElement("div");
        const n = payload.tallies?.[choice] ?? 0;
        const total = payload.tallies?.total || 0;
        const pct = total === 0 ? 0 : Math.round((n / total) * 100);
        const name = document.createElement("div");
        name.textContent = `${labels[choice]}: ${n}`;
        const bar = document.createElement("div");
        bar.className = "bar";
        const span = document.createElement("span");
        span.style.width = `${pct}%`;
        bar.append(span);
        const note = document.createElement("div");
        note.className = "source";
        note.textContent = total === 0 ? "Share of responses will appear after the first stored vote." : `${pct}% of stored responses, calculated from the tally above.`;
        row.append(name, bar, note);
        return row;
      }),
    );
  };

  fetch("/api/sentiment")
    .then(async (response) => {
      const payload = (await response.json()) as PollResponse;
      paint(payload);
    })
    .catch(() => {
      status.textContent =
        "The poll endpoint did not answer. On a static preview that is expected. It runs when this site is served with the Cloudflare Pages function and the D1 binding named DB.";
    });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const choice = data.get("choice");
    status.textContent = "Saving…";
    const response = await fetch("/api/sentiment", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ choice }),
    });
    const payload = (await response.json()) as PollResponse;
    paint(payload);
  });
}
