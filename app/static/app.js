/* Customer Insights dashboard - front end. Reads /api/* and renders every tab. */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const fmt = n => (n == null ? "–" : Number(n).toLocaleString("en-GB"));
  const pc = n => (n == null ? "–" : `${Number(n).toFixed(1)}%`);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const series = () => [1, 2, 3, 4, 5, 6, 7, 8].map(i => css(`--s${i}`));
  const dateFmt = iso => iso ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "–";
  const ago = iso => {
    if (!iso) return "never";
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    if (m < 1) return "just now"; if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60); if (h < 48) return `${h} h ago`;
    return `${Math.round(h / 24)} days ago`;
  };

  const state = { shows: [], show: null, segment: "attendees", tab: "audience", data: null, charts: [], after: [] };
  const api = async p => { const r = await fetch(p); if (!r.ok) throw new Error(await r.text()); return r.json(); };

  /* ------------------------------------------------------------ charts */
  function chartDefaults() {
    Chart.defaults.font.family = css("--font");
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css("--ink-2");
    Chart.defaults.borderColor = css("--grid");
    Chart.defaults.animation = { duration: 450 };
    Object.assign(Chart.defaults.plugins.tooltip, {
      backgroundColor: css("--ink"), titleColor: css("--surface"), bodyColor: css("--surface"),
      padding: 10, cornerRadius: 8, displayColors: true, boxPadding: 4, usePointStyle: true,
    });
    Chart.defaults.plugins.legend.display = false;
  }

  // Value at the tip of each bar, in text ink (never the series colour).
  const tipLabels = {
    id: "tipLabels",
    afterDatasetsDraw(chart, _a, opts) {
      if (!opts || !opts.show) return;
      const { ctx } = chart;
      const horizontal = chart.options.indexAxis === "y";
      const last = chart.data.datasets.length - 1;
      ctx.save();
      ctx.font = `600 11.5px ${css("--font")}`;
      ctx.fillStyle = css("--ink-2");
      chart.getDatasetMeta(last).data.forEach((bar, i) => {
        const v = opts.format(i);
        if (v == null) return;
        if (horizontal) { ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(v, bar.x + 6, bar.y); }
        else { ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(v, bar.x, bar.y - 4); }
      });
      ctx.restore();
    },
  };
  // Vertical marker (e.g. show opening day) on a category axis.
  const marker = {
    id: "marker",
    afterDraw(chart, _a, opts) {
      if (!opts || opts.index == null || opts.index < 0) return;
      const { ctx, chartArea: a, scales: { x } } = chart;
      const px = x.getPixelForValue(opts.index);
      ctx.save();
      ctx.strokeStyle = css("--ink-2"); ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(px, a.top + 14); ctx.lineTo(px, a.bottom); ctx.stroke();
      ctx.font = `600 11.5px ${css("--font")}`; ctx.fillStyle = css("--ink");
      ctx.textAlign = px > a.right - 90 ? "right" : "left";
      ctx.fillText(opts.label, px + (ctx.textAlign === "right" ? -6 : 6), a.top + 12);
      ctx.restore();
    },
  };
  Chart.register(tipLabels, marker);

  const axis = (extra = {}) => ({
    grid: { color: css("--grid"), drawTicks: false, lineWidth: 1 },
    border: { display: false },
    ticks: { padding: 8, color: css("--muted") },
    ...extra,
  });

  function mount(id, cfg) {
    state.after.push(() => {
      const el = document.getElementById(id);
      if (!el) return;
      state.charts.push(new Chart(el, cfg));
    });
  }

  // Horizontal ranking bar (single series).
  function hbar(id, items, { color, colors, valueFmt, max } = {}) {
    const labels = items.map(i => i.label);
    const h = Math.max(120, items.length * 30 + 20);
    mount(id, {
      type: "bar",
      data: { labels, datasets: [{
        data: items.map(i => i.n),
        backgroundColor: colors || color || css("--s1"),
        borderRadius: { topRight: 4, bottomRight: 4 }, borderSkipped: "start",
        maxBarThickness: 18, categoryPercentage: .78, barPercentage: .9,
      }] },
      options: {
        indexAxis: "y", maintainAspectRatio: false, responsive: true,
        layout: { padding: { right: 62 } },
        scales: {
          x: axis({ beginAtZero: true, max, ticks: { display: false }, grid: { display: false } }),
          y: axis({ grid: { display: false }, ticks: { color: css("--ink"), autoSkip: false, padding: 6,
            callback(v) { const l = this.getLabelForValue(v); return l.length > 30 ? l.slice(0, 28) + "…" : l; } } }),
        },
        plugins: {
          tooltip: { callbacks: { label: c => ` ${fmt(items[c.dataIndex].n)} · ${pc(items[c.dataIndex].pct)}` } },
          tipLabels: { show: true, format: i => valueFmt ? valueFmt(items[i]) : `${fmt(items[i].n)}  ${pc(items[i].pct)}` },
        },
      },
    });
    return `<div class="chart-box" style="height:${h}px"><canvas id="${id}" role="img" aria-label="Bar chart"></canvas></div>`;
  }

  // Vertical column chart (single series).
  function vbar(id, labels, values, { color, height = 240, tip, tipFmt, colors } = {}) {
    mount(id, {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: colors || color || css("--s1"),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "start", maxBarThickness: 24,
        categoryPercentage: .8, barPercentage: .92 }] },
      options: {
        maintainAspectRatio: false, layout: { padding: { top: tipFmt ? 18 : 4 } },
        scales: { x: axis({ grid: { display: false }, ticks: { color: css("--ink-2"), maxRotation: 0, autoSkipPadding: 8 } }),
                  y: axis({ beginAtZero: true, ticks: { color: css("--muted"), callback: v => fmt(v), maxTicksLimit: 5 } }) },
        plugins: {
          tooltip: { callbacks: { label: tip || (c => ` ${fmt(c.raw)}`) } },
          tipLabels: tipFmt ? { show: true, format: tipFmt } : { show: false },
        },
      },
    });
    return `<div class="chart-box" style="height:${height}px"><canvas id="${id}" role="img" aria-label="Column chart"></canvas></div>`;
  }

  // 100% split bar in HTML - 2px surface gaps between segments, legend beneath.
  function split(items, colors) {
    const c = colors || series();
    const total = items.reduce((a, b) => a + b.n, 0) || 1;
    const segs = items.map((it, i) => `<span title="${esc(it.label)}: ${fmt(it.n)}" style="flex:${it.n};background:${c[i]}"></span>`).join("");
    const legend = items.map((it, i) => `<div class="split-l"><i style="background:${c[i]}"></i><span>${esc(it.label)}</span><b>${pc(it.pct ?? 100 * it.n / total)}</b><em>${fmt(it.n)}</em></div>`).join("");
    return `<div class="split"><div class="split-bar">${segs}</div><div class="split-legend">${legend}</div></div>`;
  }

  /* ------------------------------------------------------------ cards */
  let uid = 0;
  const nid = p => `${p}${++uid}`;
  const tables = {};

  function card({ title, sub = "", body, cls = "c6", table, insight, tools = "" }) {
    const id = nid("card");
    if (table) tables[id] = table;
    return `<section class="card ${cls}" id="${id}">
      <div class="card-head"><div><h3>${title}</h3>${sub ? `<div class="sub">${sub}</div>` : ""}</div>
        <div class="card-tools">${tools}${table ? `<button class="tool" data-table="${id}">Table</button>` : ""}</div></div>
      <div class="card-body">${body}</div>
      ${insight ? `<div class="insight"><span>${insight}</span></div>` : ""}
    </section>`;
  }

  function tableHtml(rows, cols) {
    const max = Math.max(...rows.map(r => r.n || 0), 1);
    return `<div class="scroll"><table class="data"><thead><tr>${cols.map(c => `<th class="${c.r ? "r" : ""}">${c.label}</th>`).join("")}</tr></thead><tbody>
      ${rows.map(r => `<tr>${cols.map(c => {
        if (c.bar) return `<td><div class="bar-cell"><div class="b" style="width:${Math.round(90 * (r.n || 0) / max)}px"></div><span>${fmt(r.n)}</span></div></td>`;
        const v = c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key]);
        return `<td class="${c.r ? "r" : ""}">${v}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  const stdCols = [{ key: "label", label: "Value" }, { key: "n", label: "Count", r: true, fmt: fmt }, { key: "pct", label: "Share", r: true, fmt: pc }];

  function pendingCard({ title, text, needs, cls = "c6", bullets }) {
    return `<section class="card pending ${cls}"><div class="pending-body">
      <div class="pending-icon"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg></div>
      <div><h3>${title}</h3><p>${text}</p>
        ${bullets ? `<ul>${bullets.map(b => `<li>${b}</li>`).join("")}</ul>` : ""}
        ${needs ? `<div class="chips" style="margin-top:10px">${needs.map(n => `<span class="status plan">Needs: ${n}</span>`).join("")}</div>` : ""}
      </div></div></section>`;
  }

  const intro = (h, p, right = "") => `<div class="section-intro"><div><h2>${h}</h2><p>${p}</p></div>${right}</div>`;

  /* ------------------------------------------------------------ shell */
  function renderRegions() {
    const byRegion = {};
    state.shows.forEach(s => { (byRegion[s.region] ||= []).push(s); });
    $("#regions").innerHTML = Object.entries(byRegion).map(([region, list]) => {
      const s = list[0];
      return `<button data-show="${s.code}" class="${state.show?.code === s.code ? "active" : ""}">
        <span class="dot ${s.records ? "live" : ""}"></span>${esc(region)}</button>`;
    }).join("");
    $$("#regions button").forEach(b => b.onclick = () => selectShow(b.dataset.show));
  }

  function renderHero() {
    const d = state.data, m = d.meta, s = state.show;
    const dates = s.start_date ? `${dateFmt(s.start_date)}${s.end_date && s.end_date !== s.start_date ? " – " + dateFmt(s.end_date) : ""}` : "Show dates not set";
    let kpis = "";
    if (m.has_data) {
      const k = d.kpis, mix = d.mix;
      const tile = (label, value, note, bar) => `<div class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value num">${value}</div>
        ${bar != null ? `<div class="kpi-bar"><span style="width:${Math.min(100, bar)}%"></span></div>` : ""}<div class="kpi-note">${note}</div></div>`;
      const isEx = m.segment === "exhibitors";
      kpis = `<div class="kpis">
        ${tile(isEx ? "Exhibitor registrations" : "Total attendees", fmt(k.total), isEx ? `${fmt(mix.attendees)} attendees` : `+ ${fmt(mix.exhibitors)} exhibitor registrations`)}
        ${tile("Countries", fmt(k.countries), `${esc(k.top_country)} leads with ${pc(k.top_country_pct)}`)}
        ${tile("Companies", fmt(k.companies), `${(k.total / Math.max(1, k.companies)).toFixed(1)} people per company`)}
        ${tile("Senior level", `${k.senior_pct.toFixed(0)}<small>%</small>`, `${fmt(k.senior)} Director, VP, Head or above`, k.senior_pct)}
        ${tile("Buying power", `${k.buying_power_pct.toFixed(0)}<small>%</small>`, `${fmt(k.buying_power)} hold or influence budget`, k.buying_power_pct)}
        ${tile("Buyers", `${k.buyers_pct.toFixed(0)}<small>%</small>`, `${fmt(k.buyers)} self-declared buyers`, k.buyers_pct)}
      </div>`;
    }
    $("#hero").innerHTML = `<div class="hero-inner">
      <div class="hero-head">
        <div>
          <div class="eyebrow">${esc(s.region)} · ${esc(s.code)}</div>
          <h1>${esc(s.name)}</h1>
          <div class="hero-meta"><span>${dates}</span>
            ${m.has_data ? `<span class="live-pill">Updated ${ago(m.last_ingest)}</span><span>Latest registration ${dateFmt(m.latest_registration?.slice(0, 10))}</span>` : `<span>No registration data yet</span>`}</div>
        </div>
        ${m.has_data ? `<div><div class="seg-label">Audience segment</div><div class="segments">${m.segments.map(g =>
          `<button data-seg="${g.key}" class="${g.key === m.segment ? "active" : ""}">${g.label}</button>`).join("")}</div></div>` : ""}
      </div>${kpis}</div>`;
    $$("#hero [data-seg]").forEach(b => b.onclick = () => { state.segment = b.dataset.seg; load(); });
    $("#footMeta").textContent = m.last_source ? `Source: ${m.last_source}` : "";
  }

  function renderTab() {
    state.charts.forEach(c => c.destroy());
    state.charts = []; state.after = [];
    Object.keys(tables).forEach(k => delete tables[k]);
    $$("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === state.tab));
    const d = state.data;
    let html;
    if (state.tab === "compare") html = compareTab();
    else if (state.tab === "sources") html = sourcesTab();
    else if (!d.meta.has_data) html = emptyTab();
    else html = { audience: audienceTab, behaviour: behaviourTab, geography: geographyTab, commercial: commercialTab,
                  journey: journeyTab, gaps: gapsTab }[state.tab](d);
    $("#main").innerHTML = html;
    state.after.forEach(f => f());
    bindCardTools();
    if (state.tab === "geography" && d.meta.has_data) drawMap(d.geography.countries);
    if (state.tab === "sources") bindSources();
    if (state.tab === "compare") bindCompare();
    if (state.tab === "geography") bindCountrySearch();
  }

  function bindCardTools() {
    $$("[data-table]").forEach(btn => btn.onclick = () => {
      const cardEl = document.getElementById(btn.dataset.table);
      const body = $(".card-body", cardEl);
      if (btn.classList.toggle("on")) {
        body.dataset.chart = body.innerHTML === "" ? "" : "1";
        body._chart = [...body.childNodes];
        const t = tables[btn.dataset.table];
        body.replaceChildren(); body.insertAdjacentHTML("beforeend", tableHtml(t.rows, t.cols || stdCols));
        btn.textContent = "Chart";
      } else {
        body.replaceChildren(...body._chart); btn.textContent = "Table";
      }
    });
  }

  function emptyTab() {
    return `<div class="card c12 empty-state"><h2>No registration data for ${esc(state.show.name)} yet</h2>
      <p>Upload the registration export on the Data & sources tab, or connect the reg pool feed so it updates automatically. Every chart for Europe will then appear here in the same layout, ready to compare.</p>
      <button class="btn" onclick="document.querySelector('[data-tab=sources]').click()">Go to Data &amp; sources</button></div>`;
  }

  /* ------------------------------------------------------------ Audience */
  function audienceTab(d) {
    const a = d.audience, mix = d.mix, k = d.kpis;
    const topSen = a.seniority.filter(x => ["Executive / Owner", "Director / VP / Head"].includes(x.label));
    const topInd = a.industry[0], topProd = a.products[0];
    const senPct = topSen.reduce((sum, x) => sum + x.pct, 0);
    return intro("Audience snapshot", `Who is ${esc(state.show.name)}'s ${esc(d.meta.segment_label.toLowerCase())} audience? Every figure below uses the same data dictionary, so Europe, North America and the Middle East line up side by side.`)
    + `<div class="grid">
      ${card({ cls: "c4", title: "Attendee and exhibitor mix", sub: "Customer audience kept separate from the supply side",
        body: `<div class="stat-row" style="grid-template-columns:1fr 1fr">
          <div class="stat"><b class="num">${fmt(mix.attendees)}</b><span>Visitors, VIPs &amp; speakers</span></div>
          <div class="stat"><b class="num">${fmt(mix.exhibitors)}</b><span>Exhibitor registrations</span></div></div>
          <div style="margin-top:14px">${split(mix.attendee_types.map(t => ({ label: t.label, n: t.n })))}</div>`,
        insight: `1 exhibitor registration for every ${mix.attendees_per_exhibitor} attendees. Exhibitors equal ${pc(mix.exhibitor_pct_of_attendees)} of the attendee count.` })}
      ${card({ cls: "c4", title: "Buyer vs supplier", sub: "Self-declared business opportunity",
        body: split(a.buyer_supplier), table: { rows: a.buyer_supplier },
        insight: `${pc(k.buyers_pct)} came to buy. Suppliers attend to meet their own customers.` })}
      ${card({ cls: "c4", title: "Purchasing influence", sub: "Budgetary responsibility",
        body: split(a.budget_responsibility, [css("--s1"), css("--s3"), css("--axis")]), table: { rows: a.budget_responsibility },
        insight: `${pc(k.buying_power_pct)} hold or influence a budget, so more than 7 in 10 have a say in purchasing.` })}

      ${card({ cls: "c6", title: "Seniority", sub: "Derived from job title using the standard seniority bands",
        body: hbar(nid("c"), a.seniority, { colors: a.seniority.map(x => ["Executive / Owner", "Director / VP / Head"].includes(x.label) ? css("--s1") : css("--seq-2")) }),
        table: { rows: a.seniority },
        insight: `${pc(senPct)} are Director level or above, roughly 1 in ${Math.round(100 / Math.max(1, senPct))} attendees. A strong story for exhibitors and sponsors.` })}
      ${card({ cls: "c6", title: "Job function", sub: "Standard function picklist",
        body: hbar(nid("c"), a.job_function), table: { rows: a.job_function } })}

      ${card({ cls: "c7", title: "Key industries", sub: "Main business activity, top 15",
        body: hbar(nid("c"), a.industry), table: { rows: a.industry },
        insight: `${esc(topInd.label)} is the largest single industry at ${pc(topInd.pct)}.` })}
      ${card({ cls: "c5", title: "Industry group", sub: "Supply chain vs the end users who buy lubricants",
        body: split(a.industry_group, [css("--s1"), css("--s2"), css("--axis")]) + `<div style="margin-top:18px">${hbar(nid("c"), a.products.slice(0, 10), { color: css("--s3") })}</div>`,
        table: { rows: a.products }, insight: `Top product interest: ${esc(topProd.label)} (${pc(topProd.pct)} of the audience). Each person can pick several products.` })}

      ${card({ cls: "c7", title: "Most common job titles", sub: "As typed at registration",
        body: tableHtml(a.top_job_titles, [{ key: "label", label: "Title" }, { key: "n", label: "People", bar: true }, { key: "pct", label: "Share", r: true, fmt: pc }]) })}
      <div class="c5 stack">
      ${a.new_vs_returning ? card({ cls: "", title: "New vs returning", body: split(a.new_vs_returning), table: { rows: a.new_vs_returning } })
        : pendingCard({ cls: "", title: "New vs returning", text: "Needs the previous edition's attendee list or CRM history, matched on email. Once connected, this card splits the audience into first-timers and returners.", needs: ["CRM / LEX25 attendance"] })}
      ${pendingCard({ cls: "", title: "Company size", text: `Company size isn't captured on the registration form. ${fmt(a.companies.total)} companies are represented, averaging ${a.companies.avg_per_company} people each. Add an employee-band question, or enrich it from the CRM, to answer "are smaller specialist companies missing?"`, needs: ["Form question", "CRM enrichment"] })}
      </div>
    </div>`;
  }

  /* ------------------------------------------------------------ Behaviour */
  function behaviourTab(d) {
    const b = d.behaviour;
    const labels = b.curve.map(p => p.date);
    const showIdx = labels.indexOf(b.show_start);
    const cumId = nid("c"), dayId = nid("c");
    mount(cumId, {
      type: "line",
      data: { labels, datasets: [{ data: b.curve.map(p => p.cum), borderColor: css("--s1"), borderWidth: 2,
        backgroundColor: css("--s1") + "1a", fill: true, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2,
        pointHoverBorderColor: css("--surface"), tension: .25 }] },
      options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: axis({ grid: { display: false }, ticks: { color: css("--muted"), maxTicksLimit: 8, maxRotation: 0,
            callback(v) { return dateFmt(this.getLabelForValue(v)).replace(/ \d{4}$/, ""); } } }),
          y: axis({ beginAtZero: true, ticks: { color: css("--muted"), callback: v => fmt(v), maxTicksLimit: 5 } }) },
        plugins: { marker: { index: showIdx, label: b.show_start_inferred ? "Show (est.)" : "Show opens" },
          tooltip: { callbacks: { title: c => dateFmt(c[0].label), label: c => ` ${fmt(c.raw)} registered (${pc(100 * c.raw / d.meta.segment_n)})` } } } },
    });
    mount(dayId, {
      type: "bar",
      data: { labels, datasets: [{ data: b.curve.map(p => p.n), backgroundColor: labels.map(l => l >= b.show_start ? css("--s3") : css("--s1")),
        borderRadius: { topLeft: 2, topRight: 2 }, borderSkipped: "start", categoryPercentage: 1, barPercentage: .8 }] },
      options: { maintainAspectRatio: false,
        scales: { x: axis({ grid: { display: false }, ticks: { color: css("--muted"), maxTicksLimit: 8, maxRotation: 0,
            callback(v) { return dateFmt(this.getLabelForValue(v)).replace(/ \d{4}$/, ""); } } }),
          y: axis({ beginAtZero: true, ticks: { color: css("--muted"), maxTicksLimit: 4 } }) },
        plugins: { tooltip: { callbacks: { title: c => dateFmt(c[0].label), label: c => ` ${fmt(c.raw)} registrations` } } } },
    });

    const phaseColor = { early: css("--s1"), late: css("--s2"), onsite: css("--s3") };
    const f7 = b.windows.find(w => w.label === "First 7 days"), l7 = b.windows.find(w => w.label === "Final 7 days");
    const l3 = b.windows.find(w => w.label === "Final 3 days"), l30 = b.windows.find(w => w.label === "Final 30 days");

    return intro("Customer behaviour", `When people decide to come, and how early deciders differ from late ones. The registration cycle ran ${fmt(b.cycle_days)} days, from ${dateFmt(b.first_registration)} to the ${b.show_start_inferred ? "estimated" : ""} show opening on ${dateFmt(b.show_start)}.`)
    + `<div class="grid">
      ${card({ cls: "c12", title: "Registration build-up", sub: "Cumulative registrations over time",
        body: `<div class="stat-row" style="margin-bottom:16px">
          <div class="stat"><b>${dateFmt(b.half_registered_by)}</b><span>Date half the audience had registered</span></div>
          <div class="stat"><b>${pc(l30.pct)}</b><span>registered in the final 30 days</span></div>
          <div class="stat"><b>${b.late_vs_early_ratio}×</b><span>more in the final 7 days than the first 7</span></div>
          <div class="stat"><b>${fmt(l3.n)}</b><span>registered in the final 3 days</span></div></div>
          <div class="chart-box" style="height:280px"><canvas id="${cumId}" role="img" aria-label="Cumulative registrations"></canvas></div>
          <div class="legend" style="margin:14px 0 4px"><span><i style="background:${css("--s1")}"></i>Before the show</span><span><i style="background:${css("--s3")}"></i>Onsite, during the show</span></div>
          <div class="chart-box" style="height:120px"><canvas id="${dayId}" role="img" aria-label="Daily registrations"></canvas></div>`,
        table: { rows: b.curve.filter(p => p.n).map(p => ({ label: dateFmt(p.date), n: p.n, pct: 100 * p.cum / d.meta.segment_n })),
                 cols: [{ key: "label", label: "Date" }, { key: "n", label: "Registrations", r: true, fmt }, { key: "pct", label: "Cumulative share", r: true, fmt: pc }] },
        insight: `Only ${pc(f7.pct)} registered in the first seven days, while ${pc(l7.pct)} registered in the final seven. Early and late registrants are different audiences and need different messaging and retargeting, such as a "Know Before You Go" journey for the late wave.` })}

      ${card({ cls: "c6", title: "Registration windows", sub: "Share of the audience registering in each window. Windows overlap.",
        body: `<div class="legend"><span><i style="background:${phaseColor.early}"></i>From launch</span><span><i style="background:${phaseColor.late}"></i>Before the show</span><span><i style="background:${phaseColor.onsite}"></i>Onsite</span></div>`
          + hbar(nid("c"), b.windows, { colors: b.windows.map(w => phaseColor[w.phase]) }),
        table: { rows: b.windows } })}
      ${card({ cls: "c6", title: "When people register", sub: "Day of week and hour (UTC)",
        body: vbar(nid("c"), b.weekday.map(x => x.label), b.weekday.map(x => x.n), { height: 150 })
          + `<div style="height:14px"></div>` + vbar(nid("c"), b.hours_utc.map(x => x.label), b.hours_utc.map(x => x.n), { height: 150, color: css("--s7") }),
        table: { rows: b.weekday.map(x => ({ ...x, pct: 100 * x.n / d.meta.segment_n })) },
        insight: (() => { const t = [...b.weekday].sort((a, c) => c.n - a.n)[0]; const h = [...b.hours_utc].sort((a, c) => c.n - a.n)[0];
          return `${t.label} is the busiest registration day and ${h.label}:00 UTC the busiest hour. Schedule sends and paid bursts to land just before these peaks.`; })() })}

      ${card({ cls: "c12", title: "Where early and late deciders behave differently", sub: "Each cohort's profile, compared with the audience overall. Blue is above average, red below.",
        body: cohortTable(b), insight: cohortInsight(b) })}

      ${pendingCard({ cls: "c6", title: "Returning behaviour", text: "Attended last year, didn't attend last year, registered but didn't attend, new to the show, returned to the show.", needs: ["Previous-edition attendance", "Badge scans"] })}
      ${pendingCard({ cls: "c6", title: "Engagement", text: "Email opens and clicks, website visits, content viewed, conference interest and app engagement, joined to registrants by email.", needs: ["Dotdigital", "GA4", "Show app"] })}
    </div>`;
  }

  function cohortTable(b) {
    const metrics = [
      ["pct", "Share of audience", false],
      ["senior_pct", "Senior level (Director+)", true],
      ["budget_pct", "Hold or influence budget", true],
      ["buyer_pct", "Self-declared buyers", true],
      ["procurement_pct", "Procurement function", true],
      ["international_pct", `Outside ${b.top_country}`, true],
      ["exhibit_interest_pct", "Interested in exhibiting / sponsoring", true],
    ];
    const total = b.cohorts.reduce((s, c) => s + c.n, 0);
    const overall = key => b.cohorts.reduce((s, c) => s + c[key] * c.n, 0) / total;
    const blue = css("--s1"), red = css("--s8");
    const rows = metrics.map(([key, label, compare]) => {
      const o = overall(key);
      return `<tr><td>${label}${compare ? `<div class="sub" style="font-size:11.5px;color:var(--muted)">overall ${pc(o)}</div>` : ""}</td>` + b.cohorts.map(c => {
        if (!compare) return `<td class="cell"><span>${pc(c[key])}<span class="d">${fmt(c.n)} people</span></span></td>`;
        const delta = c[key] - o;
        const a = Math.min(.42, Math.abs(delta) / 30);
        const bg = delta >= 0 ? blue : red;
        return `<td class="cell"><span style="background:color-mix(in srgb, ${bg} ${Math.round(a * 100)}%, transparent)">${pc(c[key])}<span class="d">${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)} pts</span></span></td>`;
      }).join("") + "</tr>";
    }).join("");
    return `<div style="overflow-x:auto"><table class="data heat"><thead><tr><th></th>${b.cohorts.map(c =>
      `<th style="text-align:center">${c.name}<div style="font-weight:500;color:var(--muted)">${c.desc}</div></th>`).join("")}</tr></thead>
      <tbody>${rows}<tr><td>Top countries</td>${b.cohorts.map(c => `<td style="text-align:center;font-size:12px;color:var(--ink-2)">${c.top_countries.map(esc).join(", ")}</td>`).join("")}</tr></tbody></table></div>`;
  }

  function cohortInsight(b) {
    const e = b.cohorts.find(c => c.name === "Early bird"), l = b.cohorts.find(c => c.name === "Last minute");
    if (!e || !l) return "";
    return `Early birds are ${pc(e.international_pct)} international and ${pc(e.budget_pct)} hold or influence a budget. Last-minute registrants are ${pc(100 - l.international_pct)} from ${esc(b.top_country)} and only ${pc(l.budget_pct)} hold or influence one. International buyers plan ahead; the local audience decides late. Budget campaigns to match: international paid media early, local retargeting late.`;
  }

  /* ------------------------------------------------------------ Geography */
  function geographyTab(d) {
    const g = d.geography, k = d.kpis;
    const top = g.countries.slice(0, 15).map(c => ({ ...c }));
    return intro("Geography", `${fmt(g.country_count)} countries. The top five markets supply ${pc(g.top5_share)} of the audience, and ${fmt(g.long_tail)} countries have fewer than 10 people.`)
    + `<div class="grid">
      ${card({ cls: "c8", title: "Where the audience comes from", sub: "People per country",
        body: `<div class="map-wrap" id="map"></div><div class="map-scale" id="mapScale"></div>`,
        table: { rows: g.countries, cols: [{ key: "label", label: "Country" }, { key: "region", label: "Region" }, { key: "n", label: "People", r: true, fmt }, { key: "pct", label: "Share", r: true, fmt: pc }] } })}
      ${card({ cls: "c4", title: "By world region", sub: "Grouped from country",
        body: hbar(nid("c"), g.regions, { color: css("--s1") }), table: { rows: g.regions } })}
      ${card({ cls: "c6", title: "Top 15 countries", body: hbar(nid("c"), top), table: { rows: g.countries },
        insight: `${esc(k.top_country)} alone is ${pc(k.top_country_pct)} of the audience. Worth protecting, but also a concentration risk.` })}
      ${card({ cls: "c6", title: "Markets to test or grow", sub: "Proven interest (30+ people) outside the six core markets",
        body: `<div class="opp-grid">${g.opportunity_markets.map(c => `<div class="opp"><div class="opp-n num">${fmt(c.n)}</div><div class="opp-l">${esc(c.label)}</div><div class="opp-p">${pc(c.pct)} · ${esc(c.region)}</div></div>`).join("")}</div>`,
        insight: "The aim isn't more spend everywhere. It's country-specific paid audiences where registrations already show demand and there's room to grow." })}
      ${card({ cls: "c12", title: "All countries", sub: "Search any market",
        body: `<input class="search" id="countrySearch" placeholder="Search countries or regions…">
          <div id="countryTable">${tableHtml(g.countries, [{ key: "label", label: "Country" }, { key: "region", label: "Region" }, { key: "n", label: "People", bar: true }, { key: "pct", label: "Share", r: true, fmt: pc }])}</div>` })}
    </div>`;
  }

  function bindCountrySearch() {
    const input = $("#countrySearch");
    if (!input) return;
    const all = state.data.geography.countries;
    input.oninput = () => {
      const q = input.value.toLowerCase();
      $("#countryTable").innerHTML = tableHtml(all.filter(c => c.label.toLowerCase().includes(q) || (c.region || "").toLowerCase().includes(q)),
        [{ key: "label", label: "Country" }, { key: "region", label: "Region" }, { key: "n", label: "People", bar: true }, { key: "pct", label: "Share", r: true, fmt: pc }]);
    };
  }

  const MAP_ALIAS = { "United States": "United States of America", "Türkiye": "Turkey", "Czech Republic": "Czechia",
    "North Macedonia": "Macedonia", "Bosnia and Herzegovina": "Bosnia and Herz.", "South Sudan": "S. Sudan",
    "Dominican Republic": "Dominican Rep.", "Central African Republic": "Central African Rep." };
  let worldCache;

  async function drawMap(countries) {
    const el = $("#map");
    if (!el) return;
    worldCache ||= await (await fetch("/static/vendor/countries-110m.json")).json();
    const byName = {};
    countries.forEach(c => { byName[MAP_ALIAS[c.label] || c.label] = c; });
    const features = topojson.feature(worldCache, worldCache.objects.countries).features.filter(f => f.properties.name !== "Antarctica");
    const w = 960, h = 470;
    const proj = d3.geoNaturalEarth1().fitSize([w, h], { type: "FeatureCollection", features });
    const path = d3.geoPath(proj);
    const steps = ["--seq-2", "--seq-3", "--seq-4", "--seq-5", "--seq-6", "--seq-7"].map(css);
    const bins = [5, 20, 50, 150, 500];
    const color = d3.scaleThreshold().domain(bins).range(steps);
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${w} ${h}`).attr("role", "img").attr("aria-label", "World map of attendees");
    const tip = $("#mapTip");
    svg.selectAll("path").data(features).join("path").attr("class", "country").attr("d", path)
      .attr("fill", f => byName[f.properties.name] ? color(byName[f.properties.name].n) : css("--surface-2"))
      .on("mousemove", (ev, f) => {
        const c = byName[f.properties.name];
        tip.innerHTML = c ? `<b>${esc(c.label)}</b> · ${fmt(c.n)} people · ${pc(c.pct)}` : `${esc(f.properties.name)} · none`;
        tip.style.left = ev.clientX + 12 + "px"; tip.style.top = ev.clientY + 12 + "px"; tip.style.opacity = 1;
      })
      .on("mouseleave", () => { tip.style.opacity = 0; });
    const labels = ["1–4", "5–19", "20–49", "50–149", "150–499", "500+"];
    $("#mapScale").innerHTML = `<span>People</span>` + steps.map((s, i) => `<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap"><i style="width:12px;height:12px;border-radius:3px;background:${s};display:inline-block"></i>${labels[i]}</span>`).join("")
      + `<span style="flex-basis:100%;color:var(--muted)">Small markets (e.g. Bahrain, Singapore) are too small for the map. See the table.</span>`;
  }

  /* ------------------------------------------------------------ Commercial */
  function commercialTab(d) {
    const c = d.commercial, k = d.kpis;
    const sb = c.seniority_by_buyer;
    const sbId = nid("c");
    const cols = series();
    mount(sbId, {
      type: "bar",
      data: { labels: sb.map(x => x.label), datasets: [
        { label: "Buyer", data: sb.map(x => x.Buyer), backgroundColor: cols[0] },
        { label: "Supplier", data: sb.map(x => x.Supplier), backgroundColor: cols[1] },
        { label: "Not stated", data: sb.map(x => x["Not stated"]), backgroundColor: css("--axis") },
      ].map((ds, i, arr) => ({ ...ds, maxBarThickness: 20, borderColor: css("--surface"), borderWidth: { right: i < arr.length - 1 ? 2 : 0 },
        borderSkipped: false, borderRadius: i === arr.length - 1 ? { topRight: 4, bottomRight: 4 } : 0 })) },
      options: { indexAxis: "y", maintainAspectRatio: false,
        scales: { x: axis({ stacked: true, ticks: { color: css("--muted"), callback: v => fmt(v) } }), y: axis({ stacked: true, grid: { display: false }, ticks: { color: css("--ink") } }) },
        plugins: { legend: { display: false }, tooltip: { mode: "index", intersect: false } } },
    });
    const ex = c.commercial_interest.find(x => x.label === "Exhibiting");
    return intro("Commercial relevance", "Audience quality in the terms exhibitors and sponsors care about: budget, buying intent, seniority and the companies attending.")
    + `<div class="grid">
      ${card({ cls: "c12", title: "Buying power at a glance", body: `<div class="stat-row">
        <div class="stat"><b>${pc(k.buying_power_pct)}</b><span>hold or influence budget (${fmt(k.buying_power)})</span></div>
        <div class="stat"><b>${fmt(c.budget_250k_plus)}</b><span>report annual budgets of $250k or more</span></div>
        <div class="stat"><b>${fmt(c.budget_1m_plus)}</b><span>report budgets over $1 million</span></div>
        <div class="stat"><b>${fmt(c.exhibit_interest + c.sponsor_interest)}</b><span>attendees interested in exhibiting or sponsoring: a sales pipeline</span></div></div>` })}
      ${card({ cls: "c6", title: "Reported annual budget", sub: `${fmt(c.budget_respondents)} people answered. Figures are reported responses, not a share of the whole audience.`,
        body: vbar(nid("c"), c.budget_bands.map(b => b.label), c.budget_bands.map(b => b.n), { height: 260, tipFmt: i => fmt(c.budget_bands[i].n),
          colors: ["--seq-2", "--seq-2", "--seq-3", "--seq-3", "--seq-4", "--seq-5", "--seq-6"].map(css),
          tip: x => ` ${fmt(x.raw)} · ${pc(c.budget_bands[x.dataIndex].pct)} of respondents` }),
        table: { rows: c.budget_bands },
        insight: `${pc(100 * c.budget_1m_plus / Math.max(1, c.budget_respondents))} of those who gave a budget control more than $1M a year.` })}
      ${card({ cls: "c6", title: "Seniority × buyer / supplier", sub: "Where the senior buyers are",
        body: `<div class="legend"><span><i style="background:${cols[0]}"></i>Buyer</span><span><i style="background:${cols[1]}"></i>Supplier</span><span><i style="background:${css("--axis")}"></i>Not stated</span></div>
          <div class="chart-box" style="height:240px"><canvas id="${sbId}" role="img" aria-label="Seniority by buyer or supplier"></canvas></div>`,
        table: { rows: sb, cols: [{ key: "label", label: "Seniority" }, { key: "Buyer", label: "Buyer", r: true, fmt }, { key: "Supplier", label: "Supplier", r: true, fmt }, { key: "Not stated", label: "Not stated", r: true, fmt }] } })}
      ${card({ cls: "c7", title: "Top companies attending", sub: "By number of registrations",
        body: tableHtml(c.top_companies, [{ key: "company", label: "Company" }, { key: "country", label: "Main country" }, { key: "n", label: "People", bar: true }, { key: "senior", label: "Senior", r: true, fmt }]) })}
      ${card({ cls: "c5", title: "Company delegation size", sub: "How many people each company sent",
        body: vbar(nid("c"), c.company_delegation.map(x => x.label), c.company_delegation.map(x => x.n), { height: 200, color: css("--s7"), tipFmt: i => fmt(c.company_delegation[i].n) })
          + `<div style="margin-top:16px">${split(c.commercial_interest)}</div><div class="sub" style="margin-top:6px">Also interested in…</div>`,
        table: { rows: c.company_delegation.map(x => ({ ...x, pct: 0 })), cols: [{ key: "label", label: "People sent" }, { key: "n", label: "Companies", r: true, fmt }] },
        insight: ex ? `${fmt(ex.n)} attendees (${pc(ex.pct)}) said they'd consider exhibiting. Pass them to sales as warm leads.` : "" })}
    </div>`;
  }

  /* ------------------------------------------------------------ Journey */
  function journeyTab(d) {
    const j = d.journey;
    const stages = j.stages.map((s, i) => `<div class="stage ${s.n != null ? "live" : "off"}">
      <div class="stage-idx">STEP ${i + 1}</div><h4>${esc(s.stage)}</h4><div class="d">${esc(s.detail)}</div>
      <div class="n ${s.n == null ? "na" : ""} num">${s.n != null ? fmt(s.n) : "Not connected"}</div>
      <div class="src">${esc(s.source)}</div></div>`).join("");
    const ns = j.no_show;
    return intro("Customer journey", "First interaction → registration → attendance → engagement → return. Each step lights up as its data source is connected, showing where people drop out.")
    + `<div class="grid">
      ${card({ cls: "c12", title: "Journey funnel", sub: "Solid = live data · dashed = source still to connect", body: `<div class="funnel">${stages}</div>` })}
      ${ns ? card({ cls: "c6", title: `${fmt(ns.n)} registered but didn't attend`, sub: `${pc(ns.pct)} of registrants: a valuable retargeting audience`,
                    body: hbar(nid("c"), ns.countries), table: { rows: ns.countries } })
          + card({ cls: "c6", title: "No-show seniority", body: hbar(nid("c"), ns.seniority), table: { rows: ns.seniority } })
          + card({ cls: "c6", title: "No-show job functions", body: hbar(nid("c"), ns.job_function), table: { rows: ns.job_function } })
          + card({ cls: "c6", title: "No-show companies", body: tableHtml(ns.companies, [{ key: "label", label: "Company" }, { key: "n", label: "People", bar: true }]) })
        : pendingCard({ cls: "c12", title: "Registered but didn't attend", text: "About 1,724 LEX26 registrants didn't attend. Upload the badge-scan or attendance export with an Attended column (Yes/No) and this section builds itself:",
            bullets: ["Who were they, and what were their job levels?", "Where were they from?", "Which companies were they from?", "When did they register? Late registrants are more likely to drop out.", "What did they engage with? Needs Dotdigital and GA4.", "Why might they not have attended, and how do we retarget them?"],
            needs: ["Badge scans / attendance"] })}
    </div>`;
  }

  /* ------------------------------------------------------------ Gaps */
  function gapsTab(d) {
    return intro("Who are we missing?", "Where the audience is thin relative to the market, with the question each gap raises. Findings are generated from the live data, so they update as registrations change.")
    + `<div class="grid">${d.gaps.map(g => `<section class="card c6 gap-card">
        <div class="gap-type">${esc(g.type)} gap</div><h3>${esc(g.headline)}</h3>
        <div class="gap-rows">${g.rows.map(r => `<div class="gap-row"><span>${esc(r.label)}</span><b>${fmt(r.n)}</b><em>${esc(r.ratio)}</em></div>`).join("")}</div>
        <div class="opportunity"><strong>Opportunity</strong>${esc(g.opportunity)}</div></section>`).join("")}</div>`;
  }

  /* ------------------------------------------------------------ Compare */
  function compareTab() {
    const rows = state.compare || [];
    const col = r => {
      if (!r.has_data) return `<section class="card pending"><div class="cmp-region">${esc(r.region)}</div><h3 style="margin-top:4px">${esc(r.name)}</h3>
        <p style="color:var(--ink-2);margin:10px 0 14px">No data yet. Once the registration export is uploaded or the reg pool feed is connected, this column fills with the same measures as the others.</p>
        <button class="btn ghost" data-goto-sources>Add data</button></section>`;
      const line = (l, v) => `<div><span>${l}</span><b>${v}</b></div>`;
      return `<section class="card"><div class="cmp-head"><div class="cmp-region">${esc(r.region)}</div><span class="status ok">Live</span></div>
        <h3 style="margin-top:4px">${esc(r.name)}</h3>
        <div class="cmp-list">
          ${line("Attendees", fmt(r.total))}${line("Countries", fmt(r.countries))}${line("Companies", fmt(r.companies))}
          ${line("Senior level", pc(r.senior_pct))}${line("Buying power", pc(r.buying_power_pct))}${line("Buyers", pc(r.buyers_pct))}
          ${line("Largest market", `${esc(r.top_country)} · ${pc(r.top_country_pct)}`)}
          ${line("Registered in first 30 days", pc(r.first30_pct))}${line("Registered in final 7 days", pc(r.final7_pct))}
          ${line("Returning", r.returning_pct == null ? "Awaiting CRM" : pc(r.returning_pct))}
        </div>
        <div class="sub" style="margin-top:14px">Top 10 countries</div>
        <div class="chips" style="margin-top:6px">${r.top_countries.map(c => `<span class="chip">${esc(c)}</span>`).join("")}</div></section>`;
    };
    return intro("Compare the three shows", "Our European audience looks like this, North America like this, the Middle East like this. Same definitions, same measures, side by side.")
      + `<div class="compare-grid">${rows.map(col).join("")}</div>`;
  }
  function bindCompare() { $$("[data-goto-sources]").forEach(b => b.onclick = () => { state.tab = "sources"; renderTab(); }); }

  /* ------------------------------------------------------------ Sources */
  function sourcesTab() {
    const dict = state.dict, cov = state.data.coverage || [];
    const okIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6 9 17l-5-5"/></svg>`;
    const planIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`;
    const auto = dict.automated_shows;
    return intro("Data & sources", "Where the data lives, what's connected and automated, and the standard dictionary that makes the three shows comparable.")
    + `<div class="grid">
      ${card({ cls: "c12", title: "Three levels of reporting", body: `<div class="levels">
        <div class="level"><h4>Live dashboard</h4><p>What's happening now? This site, refreshed from the reg pool during campaign and show build-up.</p></div>
        <div class="level"><h4>Monthly customer insights</h4><p>What are we learning? Audience changes, new markets, content interests, registration behaviour, campaign performance.</p></div>
        <div class="level"><h4>Post-show insight report</h4><p>What did we learn? Print this dashboard to PDF after the show and feed it into the next edition's strategy.</p></div></div>` })}
      ${card({ cls: "c6", title: "Update the data", sub: "Upload a new registration export. Re-uploading the same people updates them; nobody is duplicated.",
        body: `<form id="uploadForm" class="form-row">
          <label>Show<select name="show_code">${state.shows.map(s => `<option value="${s.code}" ${s.code === state.show.code ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
          <label>Export file (.xlsx / .csv)<input type="file" name="file" accept=".xlsx,.xls,.csv" required></label>
          <button class="btn" type="submit">Upload</button></form><div class="msg" id="uploadMsg"></div>
          <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--grid)">
            <b style="font-size:13px">Automatic reg pool sync</b>
            <p class="sub" style="margin:4px 0 10px">${auto.length ? `Connected for ${auto.map(esc).join(", ")}. The scheduled job pulls fresh registrations automatically.` : "Not connected yet. Set REGPOOL_&lt;SHOW&gt;_URL (and a token) on Render and the scheduled job pulls registrations automatically, with no manual exports."}</p>
            ${auto.includes(state.show.code) ? `<button class="btn ghost" id="syncBtn">Sync ${esc(state.show.code)} now</button>` : ""}</div>` })}
      ${card({ cls: "c6", title: "Show dates", sub: "Used for the \"final 7 days\" and onsite windows",
        body: `<form method="post" action="/admin/show" class="form-row">
          <label>Show<select name="code" id="dateShow">${state.shows.map(s => `<option value="${s.code}" ${s.code === state.show.code ? "selected" : ""}>${esc(s.code)}</option>`).join("")}</select></label>
          <label>Opens<input type="date" name="start_date" value="${state.show.start_date || ""}"></label>
          <label>Closes<input type="date" name="end_date" value="${state.show.end_date || ""}"></label>
          <button class="btn ghost" type="submit">Save</button></form>
          <div style="margin-top:18px"><b style="font-size:13px">Recent updates</b><div id="runs" class="msg">Loading…</div></div>` })}
      ${card({ cls: "c6", title: "Where the data lives", sub: "Which systems feed the dashboard",
        body: tableHtml(dict.sources.map(s => ({ ...s, label: s.name })), [{ key: "name", label: "System" }, { key: "provides", label: "Provides" },
          { key: "status", label: "Status", fmt: v => v === "connected" ? `<span class="status ok">${okIcon}Connected</span>` : `<span class="status plan">${planIcon}Planned</span>` }]) })}
      ${card({ cls: "c6", title: `Field coverage: ${esc(state.show.code)}`, sub: "How complete each standard field is for this audience",
        body: cov.length ? tableHtml(cov.map(c => ({ label: c.label, n: Math.round(c.pct), pct: c.pct })), [{ key: "label", label: "Field" }, { key: "pct", label: "Filled", fmt: v => `<div class="bar-cell"><div class="b" style="width:${Math.round(v)}px;background:${v >= 90 ? css("--s3") : v >= 50 ? css("--s4") : css("--s8")}"></div><span>${pc(v)}</span></div>` }]) : `<p class="sub">No data yet.</p>` })}
      ${card({ cls: "c12", title: "Standard data dictionary", sub: "One vocabulary for all three shows. Visitor, Attendee and Delegate all map to Attendee, and every other field is normalised the same way.",
        body: tableHtml(dict.fields.map(f => ({ ...f, aliases: (dict.aliases[f.field] || []).join(" · ") })),
          [{ key: "label", label: "Field" }, { key: "definition", label: "Definition" }, { key: "aliases", label: "Accepted source columns", fmt: v => `<span style="color:var(--muted);font-size:12px">${esc(v)}</span>` }]) })}
    </div>`;
  }

  async function bindSources() {
    const form = $("#uploadForm");
    form.onsubmit = async e => {
      e.preventDefault();
      const msg = $("#uploadMsg"); msg.textContent = "Uploading and processing…";
      try {
        const r = await fetch("/api/ingest/upload", { method: "POST", body: new FormData(form) });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || "Upload failed");
        msg.textContent = `Done: ${fmt(j.rows)} rows read, ${fmt(j.inserted)} new, ${fmt(j.updated)} updated.`;
        await boot(form.show_code.value);
      } catch (err) { msg.textContent = err.message; }
    };
    const sync = $("#syncBtn");
    if (sync) sync.onclick = async () => {
      sync.disabled = true; sync.textContent = "Syncing…";
      const r = await fetch(`/api/ingest/sync/${state.show.code}`, { method: "POST" });
      sync.textContent = r.ok ? "Synced" : "Sync failed"; if (r.ok) boot(state.show.code);
    };
    $("#dateShow").onchange = e => {
      const s = state.shows.find(x => x.code === e.target.value);
      const f = e.target.form; f.start_date.value = s.start_date || ""; f.end_date.value = s.end_date || "";
    };
    const runs = await api("/api/ingest/runs");
    $("#runs").innerHTML = runs.length ? tableHtml(runs.slice(0, 6).map(r => ({ ...r, label: r.show })), [
      { key: "show", label: "Show" }, { key: "at", label: "When", fmt: v => ago(v) }, { key: "source", label: "Source", fmt: v => `<span style="font-size:12px">${esc(v.replace(/^local:|^upload:/, ""))}</span>` },
      { key: "inserted", label: "New", r: true, fmt }, { key: "updated", label: "Updated", r: true, fmt },
      { key: "status", label: "", fmt: v => v === "ok" ? `<span class="status ok">OK</span>` : `<span class="status plan">${esc(v)}</span>` }]) : "No updates yet.";
  }

  /* ------------------------------------------------------------ boot */
  async function load() {
    $("#main").innerHTML = `<div class="loading">Loading insights…</div>`;
    const [data, compare] = await Promise.all([
      api(`/api/shows/${state.show.code}/summary?segment=${state.segment}`),
      api(`/api/compare?segment=${state.segment === "exhibitors" ? "exhibitors" : "attendees"}`),
    ]);
    state.data = data; state.compare = compare;
    if (!data.meta.has_data) state.segment = "attendees";
    renderRegions(); renderHero(); renderTab();
  }
  function selectShow(code) {
    state.show = state.shows.find(s => s.code === code);
    try { localStorage.setItem("show", code); } catch (e) {}
    history.replaceState(null, "", `#${state.tab}`);
    load();
  }
  async function boot(code) {
    chartDefaults();
    [state.shows, state.dict] = await Promise.all([api("/api/shows"), api("/api/dictionary")]);
    let saved; try { saved = localStorage.getItem("show"); } catch (e) {}
    const pick = code || saved;
    state.show = state.shows.find(s => s.code === pick) || state.shows.find(s => s.records) || state.shows[0];
    await load();
  }

  $$("#tabs button").forEach(b => b.onclick = () => {
    state.tab = b.dataset.tab; history.replaceState(null, "", `#${state.tab}`); renderTab();
    window.scrollTo({ top: Math.min(window.scrollY, $("#tabs").offsetTop), behavior: "smooth" });
  });
  $("#themeBtn").onclick = () => {
    const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch (e) {}
    chartDefaults(); renderTab();
  };
  const hashTab = location.hash.slice(1);
  if ($(`#tabs [data-tab="${hashTab}"]`)) state.tab = hashTab;
  boot().catch(err => { $("#main").innerHTML = `<div class="card empty-state"><h2>Couldn't load the dashboard</h2><p>${esc(err.message)}</p></div>`; });
})();
