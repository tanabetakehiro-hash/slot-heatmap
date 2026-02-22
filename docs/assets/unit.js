"use strict";

const qs = new URLSearchParams(location.search);
const unit = qs.get("unit");

const els = {
  unitLabel: document.getElementById("unitLabel"),
  modelLabel: document.getElementById("modelLabel"),
  metricSelect: document.getElementById("metricSelect2"),
  updatedAt: document.getElementById("updatedAt2"),
  chartTitle: document.getElementById("chartTitle"),
  statLine: document.getElementById("statLine"),
  tbody: document.querySelector("#unitTable tbody"),
};

function fmtNum(v) {
  if (v === null || v === undefined) return "";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("ja-JP");
}

function metricLabel(metric) {
  if (metric === "diff_medals") return "差枚";
  if (metric === "bb_rb_sum") return "BB+RB";
  if (metric === "total_start") return "累計スタート";
  return "最大持玉";
}

function metricValue(row, metric) {
  if (metric === "diff_medals") return row.diff_medals ?? null;
  if (metric === "total_start") return row.total_start ?? null;
  if (metric === "bb_rb_sum") {
    const bb = (typeof row.bb === "number") ? row.bb : Number(row.bb);
    const rb = (typeof row.rb === "number") ? row.rb : Number(row.rb);
    if (Number.isNaN(bb) && Number.isNaN(rb)) return null;
    return (Number.isNaN(bb) ? 0 : bb) + (Number.isNaN(rb) ? 0 : rb);
  }
  return row.max_payout ?? null;
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch failed: ${url} ${res.status}`);
  return await res.json();
}

function calcStats(values) {
  const nums = values.filter(v => typeof v === "number" && !Number.isNaN(v));
  if (!nums.length) return null;
  const sum = nums.reduce((a, b) => a + b, 0);
  const avg = sum / nums.length;
  const max = Math.max(...nums);
  const min = Math.min(...nums);
  return { count: nums.length, avg, max, min };
}

function renderTable(series) {
  els.tbody.innerHTML = "";
  for (const r of series) {
    const bbRb = metricValue(r, "bb_rb_sum");
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.date}</td>
      <td class="num">${fmtNum(r.max_payout)}</td>
      <td class="num">${fmtNum(r.diff_medals)}</td>
      <td class="num">${fmtNum(r.bb)}</td>
      <td class="num">${fmtNum(r.rb)}</td>
      <td class="num">${fmtNum(bbRb)}</td>
      <td class="num">${fmtNum(r.total_start)}</td>
    `;
    els.tbody.appendChild(tr);
  }
}

function renderChart(series, metric) {
  const label = metricLabel(metric);
  els.chartTitle.textContent = `推移（${label}）`;

  const x = series.map(r => r.date);
  const y = series.map(r => metricValue(r, metric));

  const data = [{
    type: "scatter",
    mode: "lines+markers",
    x,
    y,
    hovertemplate: "日付=%{x}<br>" + label + "=%{y}<extra></extra>",
  }];

  const layout = {
    margin: { l: 60, r: 20, t: 10, b: 60 },
    xaxis: { title: "日付", automargin: true },
    yaxis: { title: label, automargin: true },
  };

  Plotly.newPlot("unitChart", data, layout, { responsive: true });

  const stats = calcStats(y);
  els.statLine.textContent = stats
    ? `データ日数=${stats.count} / 平均=${fmtNum(stats.avg.toFixed(1))} / 最大=${fmtNum(stats.max)} / 最小=${fmtNum(stats.min)}`
    : "データがありません";
}

async function main() {
  if (!unit) {
    els.unitLabel.textContent = "unit パラメータがありません";
    return;
  }

  const url = `data/units/${encodeURIComponent(unit)}.json`;
  const obj = await fetchJson(url);

  els.unitLabel.textContent = obj.unit_no ?? unit;
  els.modelLabel.textContent = obj.model_name_latest ? `機種：${obj.model_name_latest}` : "";
  els.updatedAt.textContent = `更新: ${obj.updated_at ?? ""}`;

  const series = obj.series || [];
  renderTable(series);

  const metric = els.metricSelect.value || "max_payout";
  renderChart(series, metric);

  els.metricSelect.addEventListener("change", () => {
    renderChart(series, els.metricSelect.value || "max_payout");
  });
}

main().catch((e) => {
  console.error(e);
  alert("台詳細の読み込みに失敗しました。build_site.py で units を生成しているか確認してください。");
});