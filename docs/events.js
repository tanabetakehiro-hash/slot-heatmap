(() => {
  const STORAGE_KEY = "slotHeatmapEvents_v1";

  const $ = (id) => document.getElementById(id);

  const form = $("eventForm");
  const eventId = $("eventId");
  const dateEl = $("date");
  const typeEl = $("type");
  const titleEl = $("title");
  const memoEl = $("memo");
  const saveBtn = $("saveBtn");
  const resetBtn = $("resetBtn");

  const exportBtn = $("exportBtn");
  const importBtn = $("importBtn");
  const importFile = $("importFile");
  const wipeBtn = $("wipeBtn");

  const tbody = $("tbody");
  const countLabel = $("countLabel");
  const monthFilter = $("monthFilter");
  const qEl = $("q");

  const toast = $("toast");
  let toastTimer = null;

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 1600);
  }

  function loadAll() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const data = JSON.parse(raw);
      if (!Array.isArray(data)) return [];
      return data;
    } catch {
      return [];
    }
  }

  function saveAll(list) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list, null, 2));
  }

  function normalizeEvent(e) {
    return {
      id: String(e.id ?? cryptoRandomId()),
      date: String(e.date ?? "").slice(0, 10),
      type: String(e.type ?? "その他"),
      title: String(e.title ?? ""),
      memo: String(e.memo ?? ""),
      updatedAt: new Date().toISOString(),
    };
  }

  function cryptoRandomId() {
    // 端末対応用に fallback も用意
    if (crypto?.randomUUID) return crypto.randomUUID();
    return "id_" + Math.random().toString(16).slice(2) + Date.now().toString(16);
  }

  function validate(e) {
    if (!e.date || e.date.length !== 10) return "日付が不正です";
    if (!e.title.trim()) return "タイトルは必須です";
    return null;
  }

  function getFilters() {
    const ym = monthFilter.value; // YYYY-MM
    const q = qEl.value.trim().toLowerCase();
    return { ym, q };
  }

  function applyFilters(list) {
    const { ym, q } = getFilters();
    let out = list;

    if (ym) {
      out = out.filter((e) => (e.date || "").startsWith(ym));
    }
    if (q) {
      out = out.filter((e) => {
        const hay = `${e.date} ${e.type} ${e.title} ${e.memo}`.toLowerCase();
        return hay.includes(q);
      });
    }
    return out;
  }

  function sortByDateDesc(list) {
    return [...list].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  }

  function clearForm() {
    eventId.value = "";
    dateEl.value = "";
    typeEl.value = "取材";
    titleEl.value = "";
    memoEl.value = "";
    saveBtn.textContent = "保存";
  }

  function fillForm(e) {
    eventId.value = e.id;
    dateEl.value = e.date;
    typeEl.value = e.type;
    titleEl.value = e.title;
    memoEl.value = e.memo;
    saveBtn.textContent = "更新";
  }

  function render() {
    const all = sortByDateDesc(loadAll());
    const filtered = applyFilters(all);

    countLabel.textContent = `${filtered.length}件`;

    tbody.innerHTML = "";
    for (const e of filtered) {
      const tr = document.createElement("tr");

      const tdDate = document.createElement("td");
      tdDate.textContent = e.date || "-";

      const tdType = document.createElement("td");
      const pill = document.createElement("span");
      pill.className = "pill";
      pill.textContent = e.type || "その他";
      tdType.appendChild(pill);

      const tdTitle = document.createElement("td");
      tdTitle.textContent = e.title || "";

      const tdMemo = document.createElement("td");
      tdMemo.textContent = e.memo || "";

      const tdAct = document.createElement("td");
      tdAct.className = "actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.textContent = "編集";
      editBtn.addEventListener("click", () => {
        fillForm(e);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.textContent = "削除";
      delBtn.addEventListener("click", () => {
        const ok = confirm(`${e.date}「${e.title}」を削除しますか？`);
        if (!ok) return;
        const now = loadAll().filter((x) => x.id !== e.id);
        saveAll(now);
        if (eventId.value === e.id) clearForm();
        render();
        showToast("削除しました");
      });

      tdAct.appendChild(editBtn);
      tdAct.appendChild(delBtn);

      tr.appendChild(tdDate);
      tr.appendChild(tdType);
      tr.appendChild(tdTitle);
      tr.appendChild(tdMemo);
      tr.appendChild(tdAct);

      tbody.appendChild(tr);
    }
  }

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();

    const candidate = normalizeEvent({
      id: eventId.value || undefined,
      date: dateEl.value,
      type: typeEl.value,
      title: titleEl.value,
      memo: memoEl.value,
    });

    const err = validate(candidate);
    if (err) {
      alert(err);
      return;
    }

    const all = loadAll();
    const idx = all.findIndex((x) => x.id === candidate.id);

    if (idx >= 0) {
      all[idx] = candidate;
      saveAll(all);
      showToast("更新しました");
    } else {
      all.push(candidate);
      saveAll(all);
      showToast("保存しました");
    }

    clearForm();
    render();
  });

  resetBtn.addEventListener("click", () => {
    clearForm();
    showToast("入力をクリアしました");
  });

  exportBtn.addEventListener("click", () => {
    const all = sortByDateDesc(loadAll());
    const data = JSON.stringify(all, null, 2);
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    a.download = `events_${y}${m}${day}.json`;
    a.href = url;
    a.click();

    URL.revokeObjectURL(url);
    showToast("エクスポートしました");
  });

  importBtn.addEventListener("click", () => importFile.click());

  importFile.addEventListener("change", async () => {
    const file = importFile.files?.[0];
    importFile.value = "";
    if (!file) return;

    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) throw new Error("配列JSONではありません");

      const normalized = parsed.map(normalizeEvent);
      saveAll(normalized);
      clearForm();
      render();
      showToast("インポートしました");
    } catch (e) {
      alert(`インポート失敗: ${e?.message ?? e}`);
    }
  });

  wipeBtn.addEventListener("click", () => {
    const ok = confirm("全イベントを削除します。よろしいですか？");
    if (!ok) return;
    localStorage.removeItem(STORAGE_KEY);
    clearForm();
    render();
    showToast("全削除しました");
  });

  monthFilter.addEventListener("change", render);
  qEl.addEventListener("input", () => {
    // 入力中に重くならない程度で即反映
    render();
  });

  // 初期日付：今日
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  dateEl.value = `${yyyy}-${mm}-${dd}`;

  render();
})();