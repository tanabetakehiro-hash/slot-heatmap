// docs/assets/app.js
"use strict";

const els = {
  dateSelect: document.getElementById("dateSelect"),
  daysSelect: document.getElementById("daysSelect"),
  unitSearch: document.getElementById("unitSearch"),
  updatedAt: document.getElementById("updatedAt"),
  filterStatus: document.getElementById("filterStatus"),
  rankingTbody: document.querySelector("#rankingTable tbody"),
  predictTbody: document.querySelector("#predictTable tbody"),
};

let INDEX = null;
let HISTORY = null;
let PREDICTION = null;

const state = {
  currentDate: null,
  heatmapDays: 30,
  unitFilter: "",
  dailyRows: [],
};

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

function normalizeFilter(s) {
  if (!s) return "";
  // 数字以外も一応許すが、空白は除去
  return String(s).trim();
}

function filterByUnitNo(rows, filter) {
  const f = normalizeFilter(filter);
  if (!f) return rows;
  return rows.filter(r => String(r.unit_no ?? "").includes(f));
}

function setFilterStatus() {
  const f = normalizeFilter(state.unitFilter);
  if (!f) {
    els.filterStatus.textContent = "";
    return;
  }
  els.filterStatus.textContent = `｜フィルタ：${f}`;
}

function renderRanking(rows) {
  const filtered = filterByUnitNo(rows, state.unitFilter);

  // 最大持玉 desc
  const sorted = [...filtered].sort((a, b) => {
    const av = (a.max_payout ?? -999999);
    const bv = (b.max_payout ?? -999999);
    return bv - av;
  });

  els.rankingTbody.innerHTML = "";
  if (sorted.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8" class="muted">該当する台番号がありません</td>`;
    els.rankingTbody.appendChild(tr);
    return;
  }

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
  const f = normalizeFilter(state.unitFilter);

  els.predictTbody.innerHTML = "";

  if (!predObj) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="muted">予測データがありません</td>`;
    els.predictTbody.appendChild(tr);
    return;
  }

  // フィルタ無し：top を表示
  // フィルタ有り：all から該当台だけ拾って pred_max_payout desc
  let list = [];
  if (!f) {
    list = (predObj.top || []).slice(0, 30);
  } else {
    const all = predObj.all || [];
    list = all
      .filter(p => String(p.unit_no ?? "").includes(f))
      .filter(p => typeof p.pred_max_payout === "number")
      .sort((a, b) => (b.pred_max_payout - a.pred_max_payout))
      .slice(0, 30);
  }

  if (list.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="muted">該当する台番号がありません</td>`;
    els.predictTbody.appendChild(tr);
    return;
  }

  let rank = 1;
  for (const p of list) {
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
  const f = normalizeFilter(state.unitFilter);

  const dates = history.dates.slice(-days);
  const unitsAll = history.units;
  const valuesAll = history.values.slice(-days);

  // フィルタ対象の units と index を作る
  let units = unitsAll;
  let idx = null;

  if (f) {
    idx = [];
    units = [];
    for (let i = 0; i < unitsAll.length; i++) {
      if (String(unitsAll[i]).includes(f)) {
        idx.push(i);
        units.push(unitsAll[i]);
      }
    }
  }

  // z を絞る
  const values = valuesAll.map(row => {
    if (!idx) return row;
    const out = [];
    for (const i of idx) out.push(row[i]);
    return out;
  });

  // 該当なし表示
  if (f && units.length === 0) {
    Plotly.purge("heatmap");
    const div = document.getElementById("heatmap");
    div.innerHTML = `<div class="muted" style="padding:12px;">該当する台番号がありません</div>`;
    return;
  }

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
        onDateChange(clickedDate);
      }
    } catch (e) {
      console.warn(e);
    }
  });
}

async function loadDaily(dateStr) {
  const url = INDEX.daily_path_format.replace("{date}", dateStr);
  const obj = await fetchJson(url);
  state.dailyRows = obj.rows || [];
  renderRanking(state.dailyRows);
}

async function loadPrediction() {
  try {
    PREDICTION = await fetchJson(INDEX.prediction_path);
  } catch (e) {
    PREDICTION = null;
  }
  renderPrediction(PREDICTION);
}

async function onDateChange(dateStr) {
  state.currentDate = dateStr;
  await loadDaily(dateStr);
}

function rerenderAll() {
  setFilterStatus();
  renderHeatmap(HISTORY, state.heatmapDays);
  renderRanking(state.dailyRows);
  renderPrediction(PREDICTION);
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

async function init() {
  INDEX = await fetchJson("data/index.json");
  els.updatedAt.textContent = `更新: ${INDEX.updated_at ?? ""}`;

  setOptions(els.dateSelect, INDEX.dates, INDEX.latest_date);
  state.currentDate = INDEX.latest_date;

  HISTORY = await fetchJson(INDEX.history_path);

  state.heatmapDays = Number(els.daysSelect.value);
  renderHeatmap(HISTORY, state.heatmapDays);

  await onDateChange(state.currentDate);
  await loadPrediction();

  els.dateSelect.addEventListener("change", async () => {
    await onDateChange(els.dateSelect.value);
  });

  els.daysSelect.addEventListener("change", async () => {
    state.heatmapDays = Number(els.daysSelect.value);
    renderHeatmap(HISTORY, state.heatmapDays);
  });

  const onSearch = debounce(() => {
    state.unitFilter = els.unitSearch.value;
    rerenderAll();
  }, 200);

  els.unitSearch.addEventListener("input", onSearch);

  setFilterStatus();
}

init().catch((e) => {
  console.error(e);
  alert("読み込みに失敗しました。docs/data の生成（build_site.py）を確認してください。");
});