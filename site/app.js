// Renders site/data/site.json (written by `wedge site-export`). No maths beyond formatting.
"use strict";

const ET = "America/New_York";
const MODEL_LABELS = {
  flows: "Wednesday Edge (flows)", gbm: "LightGBM (shadow)", ensemble: "Ensemble (shadow)",
  zero: "Zero change", seasonal_5y: "5-year seasonal", last_week: "Last week's change",
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const mb = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`);
const pct = (v) => (v == null ? "–" : `${(v * 100).toFixed(0)}%`);
const etTime = (iso, opts = {}) => new Date(iso).toLocaleString("en-US", {
  timeZone: ET, weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", ...opts,
}) + " ET";
const day = (isoDate) => new Date(`${isoDate}T12:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
const $ = (id) => document.getElementById(id);

function svg(w, h, body) {
  return `<svg viewBox="0 0 ${w} ${h}" role="img" preserveAspectRatio="xMidYMid meet">${body}</svg>`;
}

function scale(d0, d1, r0, r1) {
  return (v) => r0 + ((v - d0) / (d1 - d0 || 1)) * (r1 - r0);
}

function niceTicks(lo, hi, n = 5) {
  const step0 = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function recentChart(data) {
  const actuals = data.recent_actuals.filter(([, v]) => v != null);
  const byWeek = Object.fromEntries((data.weeks || []).filter((w) => w.status === "forecast").map((w) => [w.week, w]));
  const weeks = actuals.map(([w]) => w);
  const next = data.latest && !weeks.includes(data.latest.week) ? data.latest : null;
  if (next) weeks.push(next.week);
  const W = 560, H = 260, L = 36, R = 10, T = 10, B = 26;
  const vals = actuals.map(([, v]) => v);
  Object.values(byWeek).forEach((f) => vals.push(f.p10, f.p90));
  const lo = Math.min(-2, ...vals), hi = Math.max(2, ...vals);
  const ticks = niceTicks(lo, hi);
  const y = scale(ticks[0], ticks[ticks.length - 1], H - B, T);
  const bw = (W - L - R) / weeks.length;
  const x = (i) => L + i * bw + bw / 2;
  let g = ticks.map((t) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}" ${t === 0 ? 'style="stroke:var(--muted)"' : ""}/><text x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("");
  actuals.forEach(([w, v], i) => {
    const top = Math.min(y(0), y(v)), h = Math.abs(y(v) - y(0));
    g += `<rect x="${x(i) - bw * 0.38}" y="${top}" width="${bw * 0.76}" height="${Math.max(h, 0.5)}" fill="var(--${v >= 0 ? "build" : "draw"})" opacity="0.75"><title>${esc(day(w))}: ${mb(v)} mb</title></rect>`;
  });
  weeks.forEach((w, i) => {
    const f = byWeek[w] || (next && next.week === w ? next : null);
    if (!f) return;
    const isNext = next && next.week === w;
    g += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(f.p10)}" y2="${y(f.p90)}" stroke="var(--accent)" stroke-width="${isNext ? 3 : 1.5}"/>`;
    g += `<circle cx="${x(i)}" cy="${y(f.point)}" r="${isNext ? 5 : 3}" fill="var(--accent)" stroke="var(--surface)" stroke-width="1.5"><title>Forecast ${esc(day(w))}: ${mb(f.point)} mb (80% ${mb(f.p10)} to ${mb(f.p90)})</title></circle>`;
  });
  [0, Math.floor(weeks.length / 2), weeks.length - 1].forEach((i) => {
    g += `<text x="${x(i)}" y="${H - 8}" text-anchor="${i === 0 ? "start" : i === weeks.length - 1 ? "end" : "middle"}">${esc(day(weeks[i]).replace(/, \d{4}$/, (m) => (i === 0 || i === weeks.length - 1 ? m : "")))}</text>`;
  });
  $("recent-chart").innerHTML = svg(W, H, g);
}

function rollingChart(bt) {
  const series = [["seasonal_5y", "var(--muted)"], ["zero", "var(--draw)"], ["flows", "var(--accent)"]];
  const all = series.flatMap(([m]) => bt.rolling_mae[m]);
  const times = all.map(([t]) => Date.parse(t));
  const W = 900, H = 240, L = 36, R = 12, T = 10, B = 24;
  const ticks = niceTicks(Math.min(...all.map(([, v]) => v)) - 0.2, Math.max(...all.map(([, v]) => v)) + 0.2, 4);
  const y = scale(ticks[0], ticks[ticks.length - 1], H - B, T);
  const x = scale(Math.min(...times), Math.max(...times), L, W - R);
  let g = ticks.map((t) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${t.toFixed(1)}</text>`).join("");
  const y0 = new Date(Math.min(...times)).getUTCFullYear(), y1 = new Date(Math.max(...times)).getUTCFullYear();
  for (let yr = y0 + 1; yr <= y1; yr++) {
    const xv = x(Date.UTC(yr, 0, 1));
    g += `<text x="${xv}" y="${H - 6}" text-anchor="middle">${yr}</text>`;
  }
  const sel = Date.parse(bt.selection_window[0]);
  g += `<rect x="${x(sel)}" y="${T}" width="${W - R - x(sel)}" height="${H - B - T}" fill="var(--band)" opacity="0.5"/><text x="${x(sel) + 6}" y="${T + 14}" style="fill:var(--ink)">selection window</text>`;
  series.forEach(([m, color]) => {
    const pts = bt.rolling_mae[m].map(([t, v]) => `${x(Date.parse(t)).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    g += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="${m === "flows" ? 2.5 : 1.6}"/>`;
  });
  $("rolling-chart").innerHTML = svg(W, H, g);
}

function forecastCard(data) {
  const h = data.health, f = data.latest;
  const pill = `<span class="pill ${esc(h.state)}" title="${esc(h.note)}">${h.state === "ok" ? "Pipeline healthy" : esc(h.note)}</span>`;
  const current = f && f.week === h.next_target ? f : null;
  if (!current) {
    const last = f ? `<p class="sub" style="margin-top:14px">Latest forecast: week ending ${esc(day(f.week))}, ${mb(f.point)} mb.</p>` : "";
    return `<div class="eyebrow">Week ending ${esc(day(h.next_target))}</div>
      <p style="font-size:1.25rem;margin:10px 0 4px;font-weight:600">Forecast not yet committed</p>
      <p class="sub">The forecast job runs after the API print, from ${esc(etTime(h.next_window_opens))}. Deadline ${esc(etTime(h.next_deadline))}.</p>
      ${last}<div style="margin-top:12px">${pill}</div>`;
  }
  const dir = current.point >= 0 ? "build" : "draw";
  return `<div class="eyebrow">Week ending ${esc(day(current.week))} · forecast</div>
    <div class="big ${dir}">${mb(current.point)} <span style="font-size:0.4em;font-weight:600">mb</span></div>
    <div class="sub" style="margin:0">${pct(current.p_build)} chance of a build</div>
    <dl class="kv">
      <dt>80% range</dt><dd>${mb(current.p10)} to ${mb(current.p90)} mb</dd>
      <dt>EIA release</dt><dd>${esc(etTime(current.release_time))}</dd>
      <dt>Committed</dt><dd><a href="${esc(current.file)}">${esc(etTime(current.created_at))}</a></dd>
      <dt>Model</dt><dd class="mono">${esc(current.model)}</dd>
      ${current.api_print != null ? `<dt>API print</dt><dd>${mb(current.api_print)} mb</dd>` : ""}
      ${current.consensus != null ? `<dt>Consensus</dt><dd>${mb(current.consensus)} mb</dd>` : ""}
    </dl>
    <div style="margin-top:14px">${pill}</div>`;
}

function scoreboard(data) {
  const s = data.scoreboard;
  const stat = (n, l) => `<div class="card stat"><div class="n">${n}</div><div class="l">${l}</div></div>`;
  $("scoreboard").innerHTML = [
    stat(s.weeks_scored, "weeks scored"),
    stat(s.mae != null ? `${s.mae.toFixed(2)}` : "–", "average miss (mb)"),
    stat(pct(s.hit_rate), "direction right"),
    stat(pct(s.coverage_80), "inside 80% range"),
    stat(s.weeks_missed, "weeks missed"),
  ].join("");
  if (!s.rows.length) {
    $("benchmarks").innerHTML = `<p class="empty">No scored weeks yet. The first score lands after the first release following a committed forecast.</p>`;
  } else {
    $("benchmarks").innerHTML = `<table><thead><tr><th>Versus</th><th>Weeks</th><th>Their avg miss</th><th>Ours, same weeks</th></tr></thead><tbody>${s.rows.map((r, i) => `<tr class="${i === 0 ? "hl" : ""}"><td>${esc(r.name)}</td><td>${r.n}</td><td>${r.mae.toFixed(2)}</td><td>${(r.model_mae_same_weeks ?? s.mae).toFixed(2)}</td></tr>`).join("")}</tbody></table>`;
  }
  const rows = [...(data.weeks || [])].reverse();
  if (!rows.length) {
    $("weeks").innerHTML = `<p class="empty">The ledger is empty. The first forecast is due ${esc(etTime(data.health.next_window_opens))}.</p>`;
    return;
  }
  const yn = (v) => (v == null ? "<td>–</td>" : `<td class="${v ? "yes" : "no"}">${v ? "✓" : "✗"}</td>`);
  $("weeks").innerHTML = `<table><thead><tr><th>Week ending</th><th>Forecast</th><th>80% range</th><th>Actual</th><th>Error</th><th>In range</th><th>Direction</th><th>Consensus</th><th>API</th><th>Ledger</th></tr></thead><tbody>${rows.map((w) => w.status === "missed"
    ? `<tr><td>${esc(day(w.week))}</td><td colspan="2" class="no">missed</td><td>${mb(w.actual)}</td><td colspan="5" style="text-align:left;color:var(--muted)">${esc(w.reason)}</td><td><a href="${esc(w.file)}">file</a></td></tr>`
    : `<tr><td>${esc(day(w.week))}</td><td>${mb(w.point)}</td><td>${mb(w.p10)} to ${mb(w.p90)}</td><td>${mb(w.actual)}</td><td>${mb(w.error)}</td>${yn(w.in_80)}${yn(w.direction_hit)}<td>${mb(w.consensus)}</td><td>${mb(w.api_print)}</td><td><a href="${esc(w.file)}">file</a></td></tr>`).join("")}</tbody></table>`;
}

function backtest(bt) {
  if (!bt) return;
  $("backtest-sub").innerHTML = `Walk-forward replay of ${esc(bt.period[0].slice(0, 4))}–${esc(bt.period[1].slice(0, 4))}. Each week is forecast as of Tuesday 6 pm ET using only data released by then. The model was chosen by a rule <a href="${esc(window.REPO)}/blob/main/pm/adr/0005-baselines-and-selection-rule.md">committed before</a> it was scored on the ${esc(bt.selection_window[0].slice(0, 4))}–${esc(bt.selection_window[1].slice(0, 4))} selection window.`;
  rollingChart(bt);
  const full = Object.fromEntries(bt.full.map((r) => [r.model, r]));
  $("backtest-table").innerHTML = `<table><thead><tr><th>Model</th><th>Avg miss ${esc(bt.period[0].slice(0, 4))}–${esc(bt.period[1].slice(0, 4))}</th><th>Avg miss 2022–2025</th><th>Direction right</th><th>In 80% range</th><th>Skill vs seasonal</th></tr></thead><tbody>${bt.selection.map((r) => `<tr class="${r.model === "flows" ? "hl" : ""}"><td>${esc(MODEL_LABELS[r.model] || r.model)}</td><td>${full[r.model].mae.toFixed(2)}</td><td>${r.mae.toFixed(2)}</td><td>${pct(r.hit_rate)}</td><td>${pct(r.coverage_80)}</td><td>${r.skill == null ? "–" : `${(r.skill * 100).toFixed(1)}%`}</td></tr>`).join("")}</tbody></table>`;
}

async function main() {
  let data;
  try {
    const res = await fetch("data/site.json", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch (e) {
    $("forecast-card").innerHTML = `<p class="empty">Could not load data (${esc(e.message)}).</p>`;
    return;
  }
  window.REPO = data.meta.repo;
  if (data.meta.mode === "shadow") {
    $("banner").hidden = false;
    $("banner-text").innerHTML = "<strong>Shadow mode.</strong> The pipeline is running for real before launch, but these results are not part of the public track record.";
  }
  $("forecast-card").innerHTML = forecastCard(data);
  recentChart(data);
  scoreboard(data);
  backtest(data.backtest);
  $("footer").innerHTML = `Data: U.S. Energy Information Administration. Not investment advice. Updated ${esc(etTime(data.meta.generated_at))} from commit <a class="mono" href="${esc(data.meta.repo)}/commit/${esc(data.meta.git_sha)}">${esc(String(data.meta.git_sha).slice(0, 7))}</a>. Last data: week ending ${esc(day(data.health.last_data_period))}.`;
}

main();
