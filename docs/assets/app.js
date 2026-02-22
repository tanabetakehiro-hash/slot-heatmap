// docs/assets/app.js
"use strict";

const els = {
  dateSelect: document.getElementById("dateSelect"),
  daysSelect: document.getElementById("daysSelect"),
  updatedAt: document.getElementById("updatedAt"),
  rankingTbody: document.querySelector("#rankingTable tbody"),
  predictTbody: document.querySelector("#predictTable tbody"),
};

let INDEX = null;
let HISTORY = null;

function fmtNum(v) {
  if (v === null || v === undefined) return "";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("ja-JP");
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`fetch failed: ${url} ${res.status}`);
  return await res.json();
}

function setOptions(selectEl, values, selectedValue) {
  selectEl.innerHTML = "";
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (v === selectedValue) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function renderRanking(rows) {
  // 最大持玉 desc
  const sorted = [...rows].sort((a, b) => {
    const av = (a.max_payout ?? -999999);
    const bv = (b.max_payout ?? -999999);
    return bv - av;
  });

  els.rankingTbody.innerHTML = "";
  let rank = 1;
  for (const r of sorted) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rank++}</td>
      <td>${r.unit_no ?? ""}</td>
      <td class="wrap">${r.model_name ?? ""}</td>
      <td class="num">${fmtNum(r.max_payout)}</td>
      <td class="num">${fmtNum(r.bb)}</td>
      <td class="num">${fmtNum(r.rb)}</td>
      <td class="num">${fmtNum(r.total_start)}</td>
      <td class="num">${fmtNum(r.diff_medals)}</td>
    `;
    els.rankingTbody.appendChild(tr);
  }
}

function renderPrediction(predObj) {
  if (!predObj || !predObj.top) {
    els.predictTbody.innerHTML = "";
    return;
  }

  const top = predObj.top;
  els.predictTbody.innerHTML = "";
  let rank = 1;
  for (const p of top.slice(0, 30)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rank++}</td>
      <td>${p.unit_no ?? ""}</td>
      <td class="num">${fmtNum(p.pred_max_payout)}</td>
      <td class="num">${fmtNum(p.based_on_days)}</td>
    `;
    els.predictTbody.appendChild(tr);
  }
}

function renderHeatmap(history, days) {
  const dates = history.dates.slice(-days);
  const units = history.units;
  const values = history.values.slice(-days);

  const data = [{
    type: "heatmap",
    x: units,
    y: dates,
    z: values,
    hovertemplate: "日付=%{y}<br>台=%{x}<br>最大持玉=%{z}<extra></extra>",
  }];

  const layout = {
    margin: { l: 90, r: 20, t: 10, b: 60 },
    xaxis: { title: "台番号", automargin: true },
    yaxis: { title: "日付", automargin: true },
  };

  Plotly.newPlot("heatmap", data, layout, { responsive: true });

  const heatmapDiv = document.getElementById("heatmap");
  heatmapDiv.on("plotly_click", (ev) => {
    try {
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      const clickedDate = pt.y;
      if (clickedDate) {
        els.dateSelect.value = clickedDate;
        loadDaily(clickedDate);
      }
    } catch (e) {
      console.warn(e);
    }
  });
}

async function loadDaily(dateStr) {
  const url = INDEX.daily_path_format.replace("{date}", dateStr);
  const obj = await fetchJson(url);
  renderRanking(obj.rows || []);
}

async function loadPrediction() {
  try {
    const pred = await fetchJson(INDEX.prediction_path);
    renderPrediction(pred);
  } catch (e) {
    // prediction が無い/失敗は無視（UIは空でOK）
    renderPrediction(null);
  }
}

async function init() {
  INDEX = await fetchJson("data/index.json");
  els.updatedAt.textContent = `更新: ${INDEX.updated_at ?? ""}`;

  setOptions(els.dateSelect, INDEX.dates, INDEX.latest_date);

  HISTORY = await fetchJson(INDEX.history_path);

  const days = Number(els.daysSelect.value);
  renderHeatmap(HISTORY, days);

  await loadDaily(INDEX.latest_date);
  await loadPrediction();

  els.dateSelect.addEventListener("change", async () => {
    await loadDaily(els.dateSelect.value);
  });

  els.daysSelect.addEventListener("change", async () => {
    const d = Number(els.daysSelect.value);
    renderHeatmap(HISTORY, d);
  });
}

init().catch((e) => {
  console.error(e);
  alert("読み込みに失敗しました。docs/data の生成（build_site.py）を確認してください。");
});