export interface ChartPoint {
  date: string;
  value: number;
}

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  points: ChartPoint[];
}

export function renderChart(host: HTMLElement, series: ChartSeries[], compact: boolean): void {
  const dated = series.filter((item) => item.points.length > 0);
  if (dated.length === 0) {
    host.replaceChildren(paragraph("No points yet. Empty series stay empty."));
    return;
  }
  const dates = [...new Set(dated.flatMap((item) => item.points.map((point) => point.date)))].sort();
  const width = 640;
  const height = compact ? 168 : 240;
  const pad = { left: 36, right: 8, top: 12, bottom: 22 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const xAt = (index: number) => pad.left + (dates.length === 1 ? innerW / 2 : (index / (dates.length - 1)) * innerW);
  const yAt = (value: number) => pad.top + ((100 - value) / 100) * innerH;

  const grids = [0, 50, 100]
    .map((value) => {
      const y = yAt(value).toFixed(1);
      return `<line x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}" class="grid"></line><text x="0" y="${y}" class="axis">${value}</text>`;
    })
    .join("");

  const lines = series
    .map((item) => {
      const byDate = new Map(item.points.map((point) => [point.date, point.value]));
      const segments: string[][] = [];
      let current: string[] = [];
      dates.forEach((date, index) => {
        const value = byDate.get(date);
        if (value === undefined || Number.isNaN(value)) {
          if (current.length) segments.push(current);
          current = [];
          return;
        }
        current.push(`${xAt(index).toFixed(1)},${yAt(value).toFixed(1)}`);
      });
      if (current.length) segments.push(current);
      const marks = segments
        .map((segment) => {
          if (segment.length === 1) {
            const [x, y] = segment[0].split(",");
            return `<circle cx="${x}" cy="${y}" r="3.5" fill="${item.color}"></circle>`;
          }
          return `<polyline points="${segment.join(" ")}" fill="none" stroke="${item.color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"></polyline>`;
        })
        .join("");
      return marks;
    })
    .join("");

  const first = dates[0];
  const last = dates[dates.length - 1];
  const svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Sentiment over time, 0 to 100">
    ${grids}
    ${lines}
    <text x="${pad.left}" y="${height - 4}" class="axis">${first}</text>
    <text x="${width - pad.right}" y="${height - 4}" class="axis" text-anchor="end">${last}</text>
  </svg>`;

  const legend = document.createElement("ul");
  legend.className = "legend";
  for (const item of series) {
    const li = document.createElement("li");
    const swatch = document.createElement("i");
    swatch.style.background = item.color;
    const latest = item.points[item.points.length - 1];
    li.append(swatch, document.createTextNode(latest ? `${item.label}: ${latest.value.toFixed(1)} on ${latest.date}` : `${item.label}: no points`));
    legend.append(li);
  }
  host.replaceChildren();
  host.insertAdjacentHTML("beforeend", svg);
  host.append(legend);
}

function paragraph(text: string): HTMLParagraphElement {
  const node = document.createElement("p");
  node.className = "status";
  node.textContent = text;
  return node;
}
