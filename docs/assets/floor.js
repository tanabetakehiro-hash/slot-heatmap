(() => {
  const $ = (id) => document.getElementById(id);

  const dateInput = $("dateInput");
  const metricSelect = $("metricSelect");
  const reloadBtn = $("reloadBtn");
  const statusEl = $("status");
  const svg = $("floorSvg");
  const tooltip = $("tooltip");

  const legendBar = $("legendBar");
  const legendMin = $("legendMin");
  const legendMid = $("legendMid");
  const legendMax = $("legendMax");

  // ---- helpers ----
  const pad2 = (n) => String(n).padStart(2, "0");
  const formatYMD = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;

  // JSTの今日をデフォルト
  const todayJst = () => {
    const now = new Date();
    const utc = now.getTime() + now.getTimezoneOffset() * 60000;
    return new Date(utc + 9 * 60 * 60000);
  };

  const clamp01 = (t) => Math.max(0, Math.min(1, t));
  const lerp = (a, b, t) => a + (b - a) * t;
  const toHex = (n) => Math.round(n).toString(16).padStart(2, "0");
  const rgb = (r, g, b) => `#${toHex(r)}${toHex(g)}${toHex(b)}`;

  // diff_medals用（0中心: マイナス=赤、プラス=緑）
  function colorDiff(v, minNeg, maxPos) {
    if (!Number.isFinite(v)) return "#d9d9d9"; // 欠損
    if (v === 0) return "#ffffff";

    if (v > 0) {
      const t = clamp01(v / (maxPos || 1));
      return rgb(lerp(255, 40, t), lerp(255, 180, t), lerp(255, 70, t));
    } else {
      const t = clamp01(v / (minNeg || -1)); // minNegは負
      return rgb(lerp(255, 220, t), lerp(255, 60, t), lerp(255, 60, t));
    }
  }

  // 0..max 用（白→青）
  function colorSeq(v, vmax) {
    if (!Number.isFinite(v)) return "#d9d9d9";
    const t = clamp01(v / (vmax || 1));
    return rgb(lerp(255, 50, t), lerp(255, 120, t), lerp(255, 240, t));
  }

  async function fetchJsonTry(paths) {
    let lastErr = null;
    for (const p of paths) {
      try {
        const res = await fetch(p, { cache: "no-store" });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText} (${p})`);
        return await res.json();
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error("fetch failed");
  }

  function setStatus(msg) {
    statusEl.textContent = msg;
  }

  function clearSvg() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  function showTooltip(x, y, html) {
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    tooltip.style.left = `${x + 12}px`;
    tooltip.style.top = `${y + 12}px`;
  }
  function hideTooltip() {
    tooltip.hidden = true;
  }

  function setLegend(metric, stats) {
    if (metric === "diff_medals") {
      legendBar.style.background = "linear-gradient(90deg, #dc3c3c 0%, #ffffff 50%, #28b446 100%)";
      legendMin.textContent = String(stats.minNeg ?? "min");
      legendMid.textContent = "0";
      legendMax.textContent = String(stats.maxPos ?? "max");
    } else {
      legendBar.style.background = "linear-gradient(90deg, #ffffff 0%, #3278f0 100%)";
      legendMin.textContent = "0";
      legendMid.textContent = "";
      legendMax.textContent = String(stats.vmax ?? "max");
    }
  }

  function normUnitNo(x) {
    if (x == null) return "";
    return String(x).trim();
  }

  function extractDailyRows(dailyJson) {
    if (Array.isArray(dailyJson)) return dailyJson;
    if (dailyJson && Array.isArray(dailyJson.rows)) return dailyJson.rows;
    if (dailyJson && Array.isArray(dailyJson.data)) return dailyJson.data;
    if (dailyJson && Array.isArray(dailyJson.machines)) return dailyJson.machines;
    return [];
  }

  function buildValueMap(dailyRows) {
    const map = new Map();
    for (const r of dailyRows || []) {
      const key = normUnitNo(r.unit_no ?? r.machine_id ?? r.n ?? r.unit ?? "");
      if (!key) continue;
      map.set(key, r);
    }
    return map;
  }

  function sortUnitNos(units) {
    // 文字列でも数値でも混ざるので「数値化できるものは数値順」
    return [...units].sort((a, b) => {
      const na = Number(a);
      const nb = Number(b);
      const fa = Number.isFinite(na);
      const fb = Number.isFinite(nb);
      if (fa && fb) return na - nb;
      if (fa && !fb) return -1;
      if (!fa && fb) return 1;
      return String(a).localeCompare(String(b));
    });
  }

  function normalizeOverrideMap(overrides) {
    const map = new Map();
    for (const o of overrides || []) {
      const k = normUnitNo(o.unit_no);
      if (!k) continue;
      map.set(k, o);
    }
    return map;
  }

  function autoGridLayout(unitNos, layoutCfg) {
    const grid = layoutCfg.grid || {};
    const cols = Number(grid.cols ?? 12);
    const cellW = Number(grid.cell_w ?? 86);
    const cellH = Number(grid.cell_h ?? 56);
    const gapX = Number(grid.gap_x ?? 10);
    const gapY = Number(grid.gap_y ?? 10);
    const marginX = Number(grid.margin_x ?? 18);
    const marginY = Number(grid.margin_y ?? 18);

    const overridesMap = normalizeOverrideMap(layoutCfg.overrides);

    const machines = [];
    const sorted = sortUnitNos(unitNos);

    // グリッド配置（基本）
    for (let i = 0; i < sorted.length; i++) {
      const unit = sorted[i];

      const col = i % cols;
      const row = Math.floor(i / cols);

      const base = {
        unit_no: unit,
        x: marginX + col * (cellW + gapX),
        y: marginY + row * (cellH + gapY),
        w: cellW,
        h: cellH,
        label: unit
      };

      // 上書き（任意）
      const ov = overridesMap.get(unit);
      machines.push(ov ? { ...base, ...ov, unit_no: unit } : base);
    }

    // SVGサイズ（全部収まる）
    const rows = Math.max(1, Math.ceil(sorted.length / cols));
    const width = marginX * 2 + cols * cellW + (cols - 1) * gapX;
    const height = marginY * 2 + rows * cellH + (rows - 1) * gapY;

    return { width, height, machines };
  }

  function calcStats(machines, valueMap, metric) {
    const vals = [];
    for (const m of machines) {
      const row = valueMap.get(normUnitNo(m.unit_no));
      const v = row ? Number(row[metric]) : NaN;
      if (Number.isFinite(v)) vals.push(v);
    }

    if (metric === "diff_medals") {
      const minNeg = vals.filter((v) => v < 0).reduce((a, b) => Math.min(a, b), 0);
      const maxPos = vals.filter((v) => v > 0).reduce((a, b) => Math.max(a, b), 0);
      return { minNeg, maxPos };
    } else {
      const vmax = vals.reduce((a, b) => Math.max(a, b), 0);
      return { vmax };
    }
  }

  function render(layout, valueMap, metric, stats) {
    clearSvg();

    const W = layout.width || 1200;
    const H = layout.height || 700;

    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("x", "0");
    bg.setAttribute("y", "0");
    bg.setAttribute("width", String(W));
    bg.setAttribute("height", String(H));
    bg.setAttribute("class", "floor-bg");
    svg.appendChild(bg);

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    g.setAttribute("class", "machines");
    svg.appendChild(g);

    for (const m of layout.machines || []) {
      const unit = normUnitNo(m.unit_no);
      const row = valueMap.get(unit);
      const v = row ? Number(row[metric]) : NaN;

      let fill = "#d9d9d9";
      if (metric === "diff_medals") fill = colorDiff(v, stats.minNeg, stats.maxPos);
      else fill = colorSeq(v, stats.vmax);

      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(m.x));
      rect.setAttribute("y", String(m.y));
      rect.setAttribute("width", String(m.w));
      rect.setAttribute("height", String(m.h));
      rect.setAttribute("rx", "8");
      rect.setAttribute("class", "machine-rect");
      rect.setAttribute("fill", fill);

      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", String(m.x + 8));
      label.setAttribute("y", String(m.y + 18));
      label.setAttribute("class", "machine-label");
      label.textContent = m.label ?? unit;

      const valueText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      valueText.setAttribute("x", String(m.x + 8));
      valueText.setAttribute("y", String(m.y + 38));
      valueText.setAttribute("class", "machine-value");
      if (Number.isFinite(v)) {
        const s = metric === "diff_medals" && v > 0 ? `+${v}` : String(v);
        valueText.textContent = s;
      } else {
        valueText.textContent = "-";
      }

      rect.addEventListener("mousemove", (ev) => {
        const name = row?.machine_name ?? row?.model_name ?? "";
        const html = `
          <div class="tt-title">${unit}${name ? " / " + name : ""}</div>
          <div class="tt-row">${metric}: <b>${Number.isFinite(v) ? (metric === "diff_medals" && v > 0 ? `+${v}` : v) : "-"}</b></div>
          <div class="tt-row">BB: ${row?.bb ?? "-"} / RB: ${row?.rb ?? "-"}</div>
          <div class="tt-row">total_start: ${row?.total_start ?? "-"}</div>
          <div class="tt-row">max_medals: ${row?.max_medals ?? row?.max_payout ?? "-"}</div>
        `;
        showTooltip(ev.pageX, ev.pageY, html);
      });
      rect.addEventListener("mouseleave", hideTooltip);

      g.appendChild(rect);
      g.appendChild(label);
      g.appendChild(valueText);
    }
  }

  async function loadAndDraw() {
    const date = dateInput.value;
    const metric = metricSelect.value;

    setStatus(`読み込み中... date=${date} metric=${metric}`);

    // 1) レイアウト設定
    const layoutCfg = await fetchJsonTry(["./data/floor_layout.json", "./docs/data/floor_layout.json"]);

    // 2) 日別データ（GitHub Pages なら docs/data/daily にある想定）
    const daily = await fetchJsonTry([
      `./data/daily/${date}.json`,
      `./data/daily/${date}.json?ts=${Date.now()}`,
      `../data/daily/${date}.json`,
      `./daily/${date}.json`
    ]);

    const rows = extractDailyRows(daily);
    const valueMap = buildValueMap(rows);

    // 3) 全台を「日別データに存在する台番号」から作る
    const unitSet = new Set();
    for (const r of rows) {
      const u = normUnitNo(r.unit_no ?? r.machine_id ?? r.n ?? r.unit ?? "");
      if (u) unitSet.add(u);
    }

    if (unitSet.size === 0) {
      throw new Error("日別データから台番号が取得できません（unit_no / machine_id が見つからない）");
    }

    // 4) 自動グリッドで全台配置（＋ overrides で任意上書き）
    const auto = autoGridLayout(unitSet, layoutCfg);
    const layout = {
      width: auto.width,
      height: auto.height,
      machines: auto.machines
    };

    const stats = calcStats(layout.machines, valueMap, metric);
    setLegend(metric, stats);
    render(layout, valueMap, metric, stats);

    setStatus(`OK: ${date} / ${metric}（全台: ${layout.machines.length}）`);
  }

  function init() {
    dateInput.value = formatYMD(todayJst());

    reloadBtn.addEventListener("click", () => {
      loadAndDraw().catch((e) => setStatus(`読み込み失敗: ${String(e.message || e)}`));
    });

    metricSelect.addEventListener("change", () => {
      loadAndDraw().catch((e) => setStatus(`読み込み失敗: ${String(e.message || e)}`));
    });

    loadAndDraw().catch((e) => setStatus(`読み込み失敗: ${String(e.message || e)}`));
  }

  init();
})();