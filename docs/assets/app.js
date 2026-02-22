// docs/assets/app.js
"use strict";

const els = {
  dateSelect: document.getElementById("dateSelect"),
  daysSelect: document.getElementById("daysSelect"),
  unitSearch: document.getElementById("unitSearch"),
  modelSelect: document.getElementById("modelSelect"),
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
  modelFilter: "__ALL__", // "__ALL__" = 全機種
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
  if (!selectEl) return;
  selectEl.innerHTML = "";
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v.value;
    opt.textContent = v.label;
    if (v.value === selectedValue) opt.selected = true;
    selectEl.appendChild(opt);
  }
}

function normalizeFilter(s) {
  if (!s) return "";
  return String(s).trim();
}

/** ★ここが重要：model_name が無ければ machine_name 等を使う */
function getModelName(row) {
  const name = row?.model_name ?? row?.machine_name ?? row?.model ?? row?.name ?? "";
  return String(name).trim();
}

function buildUnitToModelMap(rows) {
  const m = new Map();
  for (const r of rows || []) {
    const u = String(r.unit_no ?? r.machine_id ?? "").trim();
    const model = getModelName(r);
    if (u && model) m.set(u, model);
  }
  return m;
}

function passesFiltersUnit(unitNo, unitFilter) {
  const f = normalizeFilter(unitFilter);
  if (!f) return true;
  return String(unitNo ?? "").includes(f);
}

function passesFiltersModel(unitNo, modelFilter, unitToModel) {
  if (!modelFilter || modelFilter === "__ALL__") return true;
  const model = unitToModel.get(String(unitNo ?? ""));
  return model === modelFilter;
}

function filterRows(rows) {
  const unitToModel = buildUnitToModelMap(state.dailyRows);
  const out = [];
  for (const r of rows || []) {
    const unitNo = String(r.unit_no ?? r.machine_id ?? "").trim();
    if (!passesFiltersUnit(unitNo, state.unitFilter)) continue;
    if (!passesFiltersModel(unitNo, state.modelFilter, unitToModel)) continue;
    out.push(r);
  }
  return out;
}

function setFilterStatus() {
  const parts = [];
  const uf = normalizeFilter(state.unitFilter);
  if (uf) parts.push(`台番号=${uf}`);
  if (state.modelFilter && state.modelFilter !== "__ALL__") parts.push(`機種=${state.modelFilter}`);
  els.filterStatus.textContent = parts.length ? `｜フィルタ：${parts.join(" / ")}` : "";
}

function updateModelOptionsFromDaily() {
  const prev = (els.modelSelect && els.modelSelect.value) ? els.modelSelect.value : "__ALL__";

  const models = new Set();
  for (const r of state.dailyRows || []) {
    const name = getModelName(r);
    if (name) models.add(name);
  }

  const sorted = Array.from(models).sort((a, b) => a.localeCompare(b, "ja"));

  const options = [
    { value: "__ALL__", label: "全機種" },
    ...sorted.map(x => ({ value: x, label: x })),
  ];

  const nextValue = options.some(o => o.value === prev) ? prev : "__ALL__";
  setOptions(els.modelSelect, options, nextValue);

  state.modelFilter = nextValue;
  setFilterStatus();
}

function renderRanking(rows) {
  const filtered = filterRows(rows);

  const sorted = [...filtered].sort((a, b) => {
    const av = (a.max_payout ?? a.max_medals ?? -999999);
    const bv = (b.max_payout ?? b.max_medals ?? -999999);
    return bv - av;
  });

  els.rankingTbody.innerHTML = "";
  if (sorted.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="8" class="muted">該当する台がありません（フィルタ条件を確認）</td>`;
    els.rankingTbody.appendChild(tr);
    return;
  }

  let rank = 1;
  for (const r of sorted) {
    const unitNo = String(r.unit_no ?? r.machine_id ?? "").trim();
    const modelName = getModelName(r);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rank++}</td>
      <td>${unitNo}</td>
      <td class="wrap">${modelName}</td>
      <td class="num">${fmtNum(r.max_payout ?? r.max_medals)}</td>
      <td class="num">${fmtNum(r.bb)}</td>
      <td class="num">${fmtNum(r.rb)}</td>
      <td class="num">${fmtNum(r.total_start)}</td>
      <td class="num">${fmtNum(r.diff_medals ?? r.diff_payout)}</td>
    `;
    els.rankingTbody.appendChild(tr);
  }
}

function renderPrediction(predObj) {
  els.predictTbody.innerHTML = "";

  if (!predObj) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="muted">予測データがありません</td>`;
    els.predictTbody.appendChild(tr);
    return;
  }

  const unitToModel = buildUnitToModelMap(state.dailyRows);

  const hasAnyFilter = normalizeFilter(state.unitFilter) || (state.modelFilter && state.modelFilter !== "__ALL__");

  let list = [];
  if (!hasAnyFilter) {
    list = (predObj.top || []).slice(0, 30);
  } else {
    const all = predObj.all || [];
    list = all
      .filter(p => typeof p.pred_max_payout === "number")
      .filter(p => passesFiltersUnit(p.unit_no, state.unitFilter))
      .filter(p => passesFiltersModel(p.unit_no, state.modelFilter, unitToModel))
      .sort((a, b) => (b.pred_max_payout - a.pred_max_payout))
      .slice(0, 30);
  }

  if (list.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="muted">該当する台がありません（フィルタ条件を確認）</td>`;
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
  const unitToModel = buildUnitToModelMap(state.dailyRows);

  const dates = history.dates.slice(-days);
  const unitsAll = history.units;
  const valuesAll = history.values.slice(-days);

  const idx = [];
  const units = [];
  for (let i = 0; i < unitsAll.length; i++) {
    const u = unitsAll[i];
    if (!passesFiltersUnit(u, state.unitFilter)) continue;
    if (!passesFiltersModel(u, state.modelFilter, unitToModel)) continue;
    idx.push(i);
    units.push(u);
  }

  if (units.length === 0) {
    Plotly.purge("heatmap");
    const div = document.getElementById("heatmap");
    div.innerHTML = `<div class="muted" style="padding:12px;">該当する台がありません（フィルタ条件を確認）</div>`;
    return;
  }

  const values = valuesAll.map(row => {
    const out = [];
    for (const i of idx) out.push(row[i]);
    return out;
  });

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
  updateModelOptionsFromDaily();
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
  renderHeatmap(HISTORY, state.heatmapDays);
  renderPrediction(PREDICTION);
  setFilterStatus();
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

  // 日付
  els.dateSelect.innerHTML = "";
  for (const d of INDEX.dates) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    if (d === INDEX.latest_date) opt.selected = true;
    els.dateSelect.appendChild(opt);
  }
  state.currentDate = INDEX.latest_date;

  HISTORY = await fetchJson(INDEX.history_path);
  state.heatmapDays = Number(els.daysSelect.value);

  await loadDaily(state.currentDate);
  renderHeatmap(HISTORY, state.heatmapDays);
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

  if (els.modelSelect) {
    els.modelSelect.addEventListener("change", () => {
      state.modelFilter = els.modelSelect.value || "__ALL__";
      rerenderAll();
    });
  }

  setFilterStatus();
}

init().catch((e) => {
  console.error(e);
  alert("読み込みに失敗しました。docs/data の生成（build_site.py）を確認してください。");
});