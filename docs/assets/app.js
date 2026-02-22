// docs/assets/app.js
"use strict";

const els = {
  dateSelect: document.getElementById("dateSelect"),
  daysSelect: document.getElementById("daysSelect"),
  metricSelect: document.getElementById("metricSelect"),
  unitSearch: document.getElementById("unitSearch"),
  modelSelect: document.getElementById("modelSelect"),
  updatedAt: document.getElementById("updatedAt"),
  filterStatus: document.getElementById("filterStatus"),
  heatmapTitle: document.getElementById("heatmapTitle"),
  rankingTitle: document.getElementById("rankingTitle"),
  metricColName: document.getElementById("metricColName"),
  rankingTbody: document.querySelector("#rankingTable tbody"),
  predictTbody: document.querySelector("#predictTable tbody"),
};

let INDEX = null;
let HISTORY = null;       // max_payout のみ（既存 history.json）
let PREDICTION = null;

const state = {
  currentDate: null,
  heatmapDays: 30,
  metric: "max_payout",   // "max_payout" | "diff_medals" | "bb_rb_sum"
  unitFilter: "",
  modelFilter: "__ALL__",
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

function normalizeFilter(s) {
  if (!s) return "";
  return String(s).trim();
}

/** model_name が無ければ machine_name などを使う */
function getModelName(row) {
  const name = row?.model_name ?? row?.machine_name ?? row?.model ?? row?.name ?? "";
  return String(name).trim();
}

function getUnitNo(row) {
  return String(row?.unit_no ?? row?.machine_id ?? "").trim();
}

function getMaxPayout(row) {
  const v = row?.max_payout ?? row?.max_medals;
  return (typeof v === "number") ? v : (v === null || v === undefined ? null : Number(v));
}

function getDiffMedals(row) {
  const v = row?.diff_medals ?? row?.diff_payout;
  return (typeof v === "number") ? v : (v === null || v === undefined ? null : Number(v));
}

function getBbRbSum(row) {
  const bb = row?.bb;
  const rb = row?.rb;
  const bbn = (typeof bb === "number") ? bb : Number(bb);
  const rbn = (typeof rb === "number") ? rb : Number(rb);
  if (Number.isNaN(bbn) && Number.isNaN(rbn)) return null;
  return (Number.isNaN(bbn) ? 0 : bbn) + (Number.isNaN(rbn) ? 0 : rbn);
}

function metricLabel(metric) {
  if (metric === "diff_medals") return "差枚";
  if (metric === "bb_rb_sum") return "BB+RB";
  return "最大持玉";
}

function metricValueFromRow(row, metric) {
  if (metric === "diff_medals") return getDiffMedals(row);
  if (metric === "bb_rb_sum") return getBbRbSum(row);
  return getMaxPayout(row);
}

function buildUnitToModelMap(rows) {
  const m = new Map();
  for (const r of rows || []) {
    const u = getUnitNo(r);
    const model = getModelName(r);
    if (u && model) m.set(u, model);
  }
  return m;
}

function passesFiltersUnit(unitNo) {
  const f = normalizeFilter(state.unitFilter);
  if (!f) return true;
  return String(unitNo ?? "").includes(f);
}

function passesFiltersModel(unitNo, unitToModel) {
  if (!state.modelFilter || state.modelFilter === "__ALL__") return true;
  const model = unitToModel.get(String(unitNo ?? ""));
  return model === state.modelFilter;
}

function filterRows(rows) {
  const unitToModel = buildUnitToModelMap(state.dailyRows);
  const out = [];
  for (const r of rows || []) {
    const unitNo = getUnitNo(r);
    if (!passesFiltersUnit(unitNo)) continue;
    if (!passesFiltersModel(unitNo, unitToModel)) continue;
    out.push(r);
  }
  return out;
}

function setFilterStatus() {
  const parts = [];
  const uf = normalizeFilter(state.unitFilter);
  if (uf) parts.push(`台番号=${uf}`);
  if (state.modelFilter && state.modelFilter !== "__ALL__") parts.push(`機種=${state.modelFilter}`);
  parts.push(`指標=${metricLabel(state.metric)}`);
  els.filterStatus.textContent = `｜${parts.join(" / ")}`;
}

function updateTitles() {
  const label = metricLabel(state.metric);
  if (els.heatmapTitle) els.heatmapTitle.textContent = `ヒートマップ（${label}）`;
  if (els.rankingTitle) els.rankingTitle.textContent = `ランキング（${label}）`;
  if (els.metricColName) els.metricColName.textContent = label;
}

function updateModelOptionsFromDaily() {
  const prev = (els.modelSelect && els.modelSelect.value) ? els.modelSelect.value : "__ALL__";

  const models = new Set();
  for (const r of state.dailyRows || []) {
    const name = getModelName(r);
    if (name) models.add(name);
  }
  const sorted = Array.from(models).sort((a, b) => a.localeCompare(b, "ja"));

  els.modelSelect.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "__ALL__";
  optAll.textContent = "全機種";
  els.modelSelect.appendChild(optAll);

  for (const name of sorted) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    els.modelSelect.appendChild(opt);
  }

  // 維持できなければ全機種
  const canKeep = Array.from(els.modelSelect.options).some(o => o.value === prev);
  const nextValue = canKeep ? prev : "__ALL__";
  els.modelSelect.value = nextValue;
  state.modelFilter = nextValue;
}

function renderRanking(rows) {
  const filtered = filterRows(rows);

  const sorted = [...filtered].sort((a, b) => {
    const av = metricValueFromRow(a, state.metric);
    const bv = metricValueFromRow(b, state.metric);
    const an = (typeof av === "number" && !Number.isNaN(av)) ? av : -999999999;
    const bn = (typeof bv === "number" && !Number.isNaN(bv)) ? bv : -999999999;
    return bn - an;
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
    const unitNo = getUnitNo(r);
    const modelName = getModelName(r);
    const metricVal = metricValueFromRow(r, state.metric);

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${rank++}</td>
      <td>${unitNo}</td>
      <td class="wrap">${modelName}</td>
      <td class="num">${fmtNum(metricVal)}</td>
      <td class="num">${fmtNum(r.bb)}</td>
      <td class="num">${fmtNum(r.rb)}</td>
      <td class="num">${fmtNum(r.total_start)}</td>
      <td class="num">${fmtNum(getDiffMedals(r))}</td>
    `;
    els.rankingTbody.appendChild(tr);
  }
}

function renderPrediction(predObj) {
  // 予測は最大持玉のみのまま（UIにも注記あり）
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
      .filter(p => passesFiltersUnit(p.unit_no))
      .filter(p => passesFiltersModel(p.unit_no, unitToModel))
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

/**
 * ヒートマップ：
 * - max_payout は history.json を使う
 * - diff_medals / bb_rb_sum は「選択中の日付のデータ」だけで簡易ヒートマップ（1日分）にする
 *   （差枚/BB+RB を日次で見たい場合は build_site 側で history を追加生成する拡張が必要）
 */
function renderHeatmap() {
  updateTitles();

  const label = metricLabel(state.metric);
  const unitToModel = buildUnitToModelMap(state.dailyRows);

  // units をフィルタ
  const unitsFiltered = [];
  const values1day = []; // 1日分の z（指標切替時に使う）
  for (const r of state.dailyRows) {
    const unitNo = getUnitNo(r);
    if (!passesFiltersUnit(unitNo)) continue;
    if (!passesFiltersModel(unitNo, unitToModel)) continue;
    unitsFiltered.push(unitNo);
    values1day.push(metricValueFromRow(r, state.metric));
  }

  if (unitsFiltered.length === 0) {
    Plotly.purge("heatmap");
    const div = document.getElementById("heatmap");
    div.innerHTML = `<div class="muted" style="padding:12px;">該当する台がありません（フィルタ条件を確認）</div>`;
    return;
  }

  // max_payout：従来の履歴ヒートマップ
  if (state.metric === "max_payout") {
    const days = state.heatmapDays;
    const dates = HISTORY.dates.slice(-days);
    const unitsAll = HISTORY.units;
    const valuesAll = HISTORY.values.slice(-days);

    // HISTORY の units index を作る（unitsFiltered を基準）
    const idx = [];
    const units = [];
    const setWanted = new Set(unitsFiltered);
    for (let i = 0; i < unitsAll.length; i++) {
      const u = String(unitsAll[i]);
      if (setWanted.has(u)) {
        idx.push(i);
        units.push(u);
      }
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
      hovertemplate: "日付=%{y}<br>台=%{x}<br>" + label + "=%{z}<extra></extra>",
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
    return;
  }

  // diff_medals / bb_rb_sum：1日分の簡易ヒートマップ（横一列）
  Plotly.purge("heatmap");
  const dates = [state.currentDate];
  const values = [values1day];

  const data = [{
    type: "heatmap",
    x: unitsFiltered,
    y: dates,
    z: values,
    hovertemplate: "日付=%{y}<br>台=%{x}<br>" + label + "=%{z}<extra></extra>",
  }];

  const layout = {
    margin: { l: 90, r: 20, t: 10, b: 60 },
    xaxis: { title: "台番号", automargin: true },
    yaxis: { title: "日付（選択中の1日）", automargin: true },
  };

  Plotly.newPlot("heatmap", data, layout, { responsive: true });
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
  renderHeatmap();
  renderPrediction(PREDICTION);
  setFilterStatus();
}

function rerenderAll() {
  setFilterStatus();
  renderHeatmap();
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
  state.metric = els.metricSelect ? (els.metricSelect.value || "max_payout") : "max_payout";
  updateTitles();

  await loadDaily(state.currentDate);
  await loadPrediction();

  renderHeatmap();
  setFilterStatus();

  els.dateSelect.addEventListener("change", async () => {
    await onDateChange(els.dateSelect.value);
  });

  els.daysSelect.addEventListener("change", async () => {
    state.heatmapDays = Number(els.daysSelect.value);
    if (state.metric === "max_payout") renderHeatmap(); // max_payoutだけ日数が効く
  });

  if (els.metricSelect) {
    els.metricSelect.addEventListener("change", () => {
      state.metric = els.metricSelect.value || "max_payout";
      rerenderAll();
    });
  }

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
}

init().catch((e) => {
  console.error(e);
  alert("読み込みに失敗しました。docs/data の生成（build_site.py）を確認してください。");
});