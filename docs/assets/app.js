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

  floormap: document.getElementById("floormap"),
  floormapStats: document.getElementById("floormapStats"),
};

let INDEX = null;
let HISTORY = null;
let PREDICTION = null;

const FLOORMAP = {
  loaded: false,
  svg: null,
  unitToRect: new Map(), // key: "729" など
  unitToText: new Map(),
};

const state = {
  currentDate: null,
  heatmapDays: 30,
  metric: "max_payout",
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

function isDigits(s) {
  return /^\d+$/.test(String(s || "").trim());
}

function normUnitKey(u) {
  const s = String(u ?? "").trim();
  if (!isDigits(s)) return s;
  return String(parseInt(s, 10)); // "0729" -> "729"
}

/** 台番号フィルタ：ゼロ埋めも考慮して部分一致 */
function unitMatchesFilter(unitAny, filterRaw) {
  const f = normalizeFilter(filterRaw);
  if (!f) return true;

  const u = String(unitAny ?? "").trim();
  if (u.includes(f)) return true;

  // 数字同士なら、ゼロ埋め4桁でも判定
  if (isDigits(u) && isDigits(f)) {
    const uNum = String(parseInt(u, 10));
    const uPad = uNum.padStart(4, "0");  // 729 -> 0729
    if (uNum.includes(String(parseInt(f, 10)))) return true;
    if (uPad.includes(f)) return true;   // f="07" なら 0729 にヒット
  }
  return false;
}

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
    const u = normUnitKey(getUnitNo(r));
    const model = getModelName(r);
    if (u && model) m.set(u, model);
  }
  return m;
}

function passesFiltersUnit(unitNoAny) {
  return unitMatchesFilter(unitNoAny, state.unitFilter);
}

function passesFiltersModel(unitNoAny, unitToModel) {
  if (!state.modelFilter || state.modelFilter === "__ALL__") return true;
  const key = normUnitKey(unitNoAny);
  const model = unitToModel.get(key);
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
      <td><a class="link" href="unit.html?unit=${encodeURIComponent(unitNo)}">${unitNo}</a></td>
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
 * - diff_medals / bb_rb_sum は 1日分（選択中の日付）を簡易ヒートマップ化
 */
function renderHeatmap() {
  updateTitles();

  const label = metricLabel(state.metric);
  const unitToModel = buildUnitToModelMap(state.dailyRows);

  const unitsFiltered = [];
  const values1day = [];
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

  if (state.metric === "max_payout") {
    const days = state.heatmapDays;
    const dates = HISTORY.dates.slice(-days);
    const unitsAll = HISTORY.units;
    const valuesAll = HISTORY.values.slice(-days);

    const setWanted = new Set(unitsFiltered.map(normUnitKey));
    const idx = [];
    const units = [];
    for (let i = 0; i < unitsAll.length; i++) {
      const u = normUnitKey(unitsAll[i]);
      if (setWanted.has(u)) {
        idx.push(i);
        units.push(unitsAll[i]);
      }
    }

    const values = valuesAll.map(row => idx.map(i => row[i]));

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
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      const clickedDate = pt.y;
      if (clickedDate) {
        els.dateSelect.value = clickedDate;
        onDateChange(clickedDate);
      }
    });
    return;
  }

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

/* ===== フロアマップ（SVG） ===== */

function hexToRgb(hex) {
  const h = String(hex).replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}
function rgbToHex(r, g, b) {
  const to2 = (x) => Math.max(0, Math.min(255, x)).toString(16).padStart(2, "0");
  return (to2(r) + to2(g) + to2(b)).toUpperCase();
}
function lerp(a, b, t) { return a + (b - a) * t; }
function lerpColor(c1, c2, t) {
  const a = hexToRgb(c1);
  const b = hexToRgb(c2);
  return rgbToHex(lerp(a.r, b.r, t), lerp(a.g, b.g, t), lerp(a.b, b.b, t));
}
function luminance(hexNoHash) {
  const c = hexToRgb("#" + hexNoHash);
  return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
}

function colorForValue(metric, v, vmin, vmax, maxAbs) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return null;

  // 差枚：青(マイナス)→白(0)→赤(プラス)
  if (metric === "diff_medals") {
    if (!maxAbs || maxAbs <= 0) return null;
    const t = Math.max(-1, Math.min(1, Number(v) / maxAbs)); // -1..1
    if (t < 0) return lerpColor("#2B8CBE", "#FFFFFF", t + 1); // -1..0 => 0..1
    return lerpColor("#FFFFFF", "#DE2D26", t);                // 0..1
  }

  // それ以外：白→赤
  if (!(vmax > vmin)) return lerpColor("#FFFFFF", "#DE2D26", 0.5);
  const t = Math.max(0, Math.min(1, (Number(v) - vmin) / (vmax - vmin)));
  return lerpColor("#FFFFFF", "#DE2D26", t);
}

async function loadFloormapSvg() {
  if (!els.floormap) return;
  try {
    const res = await fetch("assets/floormap.svg", { cache: "no-store" });
    if (!res.ok) throw new Error("floormap.svg not found");
    const text = await res.text();

    // SVGをDOMとして挿入
    els.floormap.innerHTML = text;
    const svg = els.floormap.querySelector("svg");
    if (!svg) throw new Error("svg parse failed");

    FLOORMAP.svg = svg;
    FLOORMAP.unitToRect.clear();
    FLOORMAP.unitToText.clear();

    svg.querySelectorAll("[data-unit]").forEach((g) => {
      const unit = normUnitKey(g.getAttribute("data-unit"));
      const rect = g.querySelector("rect");
      const txt = g.querySelector("text");
      if (rect) FLOORMAP.unitToRect.set(unit, rect);
      if (txt) FLOORMAP.unitToText.set(unit, txt);

      // クリックで台詳細へ
      g.addEventListener("click", () => {
        location.href = `unit.html?unit=${encodeURIComponent(unit)}`;
      });
    });

    FLOORMAP.loaded = true;
  } catch (e) {
    FLOORMAP.loaded = false;
    if (els.floormap) {
      els.floormap.innerHTML = `<div class="muted" style="padding:12px;">floormap.svg がありません（SVG生成を実行してください）</div>`;
    }
  }
}

function renderFloormap() {
  if (!FLOORMAP.loaded) return;

  const unitToModel = buildUnitToModelMap(state.dailyRows);

  // 台ごとの値マップ（keyは "729" など）
  const valMap = new Map();
  const activeUnits = new Set(); // フィルタに通ったユニット

  const values = [];
  const absValues = [];

  for (const r of state.dailyRows || []) {
    const uRaw = getUnitNo(r);
    const uKey = normUnitKey(uRaw);

    // filter判定は raw/ゼロ埋めも含める
    const okUnit = passesFiltersUnit(uRaw);
    const okModel = passesFiltersModel(uRaw, unitToModel);

    const v = metricValueFromRow(r, state.metric);
    valMap.set(uKey, v);

    if (okUnit && okModel) {
      activeUnits.add(uKey);
      if (typeof v === "number" && !Number.isNaN(v)) {
        values.push(v);
        absValues.push(Math.abs(v));
      }
    }
  }

  const vmin = values.length ? Math.min(...values) : 0;
  const vmax = values.length ? Math.max(...values) : 1;
  const maxAbs = absValues.length ? Math.max(...absValues) : 0;

  // 表示ステータス
  if (els.floormapStats) {
    els.floormapStats.textContent =
      values.length
        ? `範囲：min=${fmtNum(vmin)} / max=${fmtNum(vmax)}（${metricLabel(state.metric)}）`
        : `範囲：データなし（フィルタ条件を確認）`;
  }

  // SVG上の全ユニットを塗る（active以外は薄く）
  FLOORMAP.unitToRect.forEach((rect, unitKey) => {
    const isActive = activeUnits.has(unitKey);
    const v = valMap.get(unitKey);

    if (!isActive) {
      rect.setAttribute("fill", "#0F1522");
      rect.setAttribute("fill-opacity", "0.25");
      return;
    }

    const col = colorForValue(state.metric, v, vmin, vmax, maxAbs);
    if (!col) {
      rect.setAttribute("fill", "#0F1522");
      rect.setAttribute("fill-opacity", "0.5");
      return;
    }

    rect.setAttribute("fill", "#" + col);
    rect.setAttribute("fill-opacity", "1.0");

    const txt = FLOORMAP.unitToText.get(unitKey);
    if (txt) {
      const lum = luminance(col);
      txt.setAttribute("fill", lum < 140 ? "#FFFFFF" : "#000000");
    }
  });
}

/* ===== ロード/イベント ===== */

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
  renderFloormap();
  setFilterStatus();
}

function rerenderAll() {
  setFilterStatus();
  renderHeatmap();
  renderRanking(state.dailyRows);
  renderPrediction(PREDICTION);
  renderFloormap();
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

  await loadFloormapSvg();

  renderHeatmap();
  renderFloormap();
  setFilterStatus();

  els.dateSelect.addEventListener("change", async () => {
    await onDateChange(els.dateSelect.value);
  });

  els.daysSelect.addEventListener("change", async () => {
    state.heatmapDays = Number(els.daysSelect.value);
    if (state.metric === "max_payout") renderHeatmap();
  });

  if (els.metricSelect) {
    els.metricSelect.addEventListener("change", () => {
      state.metric = els.metricSelect.value || "max_payout";
      updateTitles();
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