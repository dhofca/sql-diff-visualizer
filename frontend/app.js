"use strict";

const STATUS = {
  added: { mark: "+", fg: "#1a7f37", bg: "#dafbe1", label: "dodane" },
  removed: { mark: "−", fg: "#cf222e", bg: "#ffebe9", label: "usunięte" },
  modified: { mark: "~", fg: "#9a6700", bg: "#fff8c5", label: "zmienione" },
  unchanged: { mark: "", fg: "#1f2328", bg: null, label: "bez zmian" },
};
const KIND_LABEL = {
  table: "tabela", column: "kolumna", index: "indeks", fk: "klucz obcy", view: "widok",
  trigger: "trigger", procedure: "procedura", function: "funkcja", event: "event", group: "grupa",
};
const SUMMARY_LABEL = {
  table: "Tabele", column: "Kolumny", index: "Indeksy", fk: "Klucze obce", view: "Widoki",
  trigger: "Triggery", procedure: "Procedury", function: "Funkcje", event: "Eventy",
};
const FIELD_LABEL = {
  type: "typ", nullable: "null", default: "default", extra: "extra", charset: "charset",
  collation: "collation", comment: "komentarz", kind: "rodzaj", columns: "kolumny",
  references: "referencja", on_delete: "ON DELETE", on_update: "ON UPDATE", definition: "definicja",
};
const ENV = { old: "PROD", new: "PREPROD" };
const LEGEND = { added: "dodane na preprod", removed: "usunięte na preprod", modified: "zmienione" };
const DEFINITION_KINDS = new Set(["view", "trigger", "procedure", "function", "event"]);

const FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const MUTED = "#656d76";
const LINK = "#c8ccd2";
const ROW = 24;
const GAP = 40;
const PAD = 24;
const HEADER = 78;
const MAX_DETAIL = 110;

let data = null;
let collapsed = new Set();
let selectedKey = null;

const $ = (sel) => document.querySelector(sel);
const measure = document.createElement("canvas").getContext("2d");

function textWidth(text, size, weight = 400) {
  measure.font = `${weight} ${size}px ${FONT_FAMILY}`;
  return measure.measureText(text).width;
}

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  for (const c of children.flat()) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

/* ---------- upload ---------- */

const form = $("#upload");

function refreshUpload() {
  form.querySelectorAll(".drop").forEach((drop) => {
    const file = drop.querySelector("input").files[0];
    drop.classList.toggle("filled", Boolean(file));
    drop.querySelector(".drop-file").textContent = file ? file.name : "Upuść plik .sql lub kliknij";
  });
  $("#compare").disabled = [...form.querySelectorAll("input[type=file]")].some((i) => !i.files.length);
}

form.querySelectorAll(".drop").forEach((drop) => {
  const input = drop.querySelector("input");
  input.addEventListener("change", refreshUpload);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragover"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      input.files = e.dataTransfer.files;
      refreshUpload();
    }
  });
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#error").hidden = true;
  $("#compare").disabled = true;
  $("#compare").textContent = "Porównuję…";
  try {
    const res = await fetch("api/diff", { method: "POST", body: new FormData(form) });
    const body = await res.json();
    if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
    data = body;
    selectedKey = null;
    initCollapsed();
    showWarnings();
    showSummary();
    $("#result").hidden = false;
    render();
    showDetails(null);
  } catch (err) {
    $("#error").textContent = `Błąd: ${err.message}`;
    $("#error").hidden = false;
  } finally {
    $("#compare").textContent = "Porównaj";
    refreshUpload();
  }
});

/* ---------- state ---------- */

function walk(node, fn, depth = 0) {
  fn(node, depth);
  node.children.forEach((c) => walk(c, fn, depth + 1));
}

function initCollapsed() {
  collapsed = new Set();
  walk(data.tree, (n) => {
    if (!n.children.length || n.key === "schema") return;
    if (n.status === "unchanged" || (n.kind === "table" && n.status !== "modified")) collapsed.add(n.key);
  });
}

function filterTree(node, onlyChanges, query) {
  const selfMatch = Boolean(query) && node.kind !== "group" && node.name.toLowerCase().includes(query);
  const childQuery = selfMatch ? "" : query;
  const children = node.children.map((c) => filterTree(c, onlyChanges, childQuery)).filter(Boolean);
  const isRoot = node.key === "schema";
  if (!isRoot && onlyChanges && node.status === "unchanged") return null;
  if (!isRoot && query && !selfMatch && !children.length) return null;
  return { ...node, children, total: node.children.length, match: selfMatch };
}

/* ---------- rendering ---------- */

function fmt(field, value) {
  if (field === "nullable") return value ? "NULL" : "NOT NULL";
  return value === null || value === undefined || value === "" ? "∅" : String(value);
}

function detailText(n) {
  if (n.kind === "group") return n.total ? `(${n.total})` : "";
  if (DEFINITION_KINDS.has(n.kind)) return n.status === "modified" ? "definicja zmieniona" : "";
  let text;
  if (n.changes) {
    text = n.changes.map((c) => `${FIELD_LABEL[c.field] || c.field}: ${fmt(c.field, c.before)} → ${fmt(c.field, c.after)}`).join("; ");
  } else if (n.kind === "table") {
    text = "";
  } else {
    text = n.status === "removed" ? n.before : n.after;
  }
  return text && text.length > MAX_DETAIL ? text.slice(0, MAX_DETAIL - 1) + "…" : text || "";
}

function labelOf(d) {
  const n = d.data;
  const weight = n.kind === "table" || n.kind === "group" ? 600 : 400;
  const mark = STATUS[n.status].mark;
  const title = (mark ? mark + " " : "") + n.name;
  const detail = detailText(n);
  const width = textWidth(title, 13, weight) + (detail ? 8 + textWidth(detail, 12) : 0);
  return { title, detail, weight, width };
}

function render() {
  const onlyChanges = $("#only-changes").checked;
  const query = $("#search").value.trim().toLowerCase();
  const visible = filterTree(data.tree, onlyChanges, query);
  const root = d3.hierarchy(visible, (d) => (!query && collapsed.has(d.key)) || !d.children.length ? null : d.children);

  const isTopGroup = (d) => d.depth === 1 && d.data.kind === "group";
  d3.tree().nodeSize([ROW, 1]).separation((a, b) => {
    if (a.parent !== b.parent) return 1.25;
    return isTopGroup(a) !== isTopGroup(b) ? 2 : 1;
  })(root);

  // The schema root exists only to give D3 a single root; it is not drawn.
  const nodes = root.descendants().filter((d) => d.depth > 0);
  nodes.forEach((d) => { d.label = labelOf(d); });

  const maxWidthAtDepth = [];
  nodes.forEach((d) => { maxWidthAtDepth[d.depth] = Math.max(maxWidthAtDepth[d.depth] || 0, d.label.width); });
  const depthX = [0, PAD];
  for (let i = 2; i < maxWidthAtDepth.length; i++) depthX[i] = depthX[i - 1] + 10 + maxWidthAtDepth[i - 1] + 8 + GAP;

  const minX = d3.min(nodes, (d) => d.x) ?? 0;
  const maxX = d3.max(nodes, (d) => d.x) ?? 0;
  nodes.forEach((d) => { d.px = depthX[d.depth]; d.py = d.x - minX + HEADER + PAD; });

  const contentWidth = (d3.max(nodes, (d) => d.px + 10 + d.label.width + 8) ?? 0) + PAD;
  const width = Math.max(contentWidth, 720);
  const height = Math.max(maxX - minX + HEADER + PAD * 2, HEADER + PAD * 2 + 40);

  const container = $("#canvas");
  container.innerHTML = "";
  const svg = d3.select(container).append("svg")
    .attr("xmlns", "http://www.w3.org/2000/svg")
    .attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`)
    .attr("font-family", FONT_FAMILY);

  svg.append("rect").attr("width", width).attr("height", height).attr("fill", "#ffffff");
  drawHeader(svg, onlyChanges, query);

  svg.append("g").selectAll("path").data(root.links().filter((l) => l.source.depth > 0)).join("path")
    .attr("fill", "none")
    .attr("stroke", (l) => (l.target.data.status === "unchanged" ? LINK : STATUS[l.target.data.status].fg))
    .attr("stroke-opacity", (l) => (l.target.data.status === "unchanged" ? 1 : 0.45))
    .attr("stroke-width", 1.2)
    .attr("d", (l) => {
      const sx = l.source.px + 10 + l.source.label.width + 8;
      const tx = l.target.px - 5;
      const mx = (sx + tx) / 2;
      return `M${sx},${l.source.py}C${mx},${l.source.py} ${mx},${l.target.py} ${tx},${l.target.py}`;
    });

  const node = svg.append("g").selectAll("g").data(nodes).join("g")
    .attr("class", "tree-node")
    .attr("transform", (d) => `translate(${d.px},${d.py})`);

  node.each(function (d) {
    const g = d3.select(this);
    const n = d.data;
    const st = STATUS[n.status];
    const hasHidden = n.children.length > 0 && !d.children;
    const toggle = g.append("g").on("click", (e) => { e.stopPropagation(); toggleNode(n); });
    toggle.append("circle").attr("r", 10).attr("fill", "transparent");
    toggle.append("circle").attr("r", 4.5)
      .attr("fill", hasHidden ? (n.status === "unchanged" ? MUTED : st.fg) : "#ffffff")
      .attr("stroke", n.status === "unchanged" ? MUTED : st.fg)
      .attr("stroke-width", 1.5);

    const label = g.append("g").attr("transform", "translate(10,0)").on("click", () => selectNode(n));
    const bg = label.append("rect")
      .attr("x", -4).attr("y", -10).attr("rx", 3)
      .attr("width", d.label.width + 8).attr("height", 20)
      .attr("fill", st.bg || "transparent");
    if (isTopGroup(d)) bg.attr("stroke", n.status === "unchanged" ? MUTED : st.fg).attr("stroke-dasharray", "3 2");
    if (n.match) bg.attr("stroke", "#0b5cad").attr("stroke-width", 1.5).attr("stroke-dasharray", null);
    if (n.key === selectedKey) bg.attr("stroke", "#1f2328").attr("stroke-width", 1.5).attr("data-selected", "1");

    const text = label.append("text").attr("dy", "0.35em").attr("font-size", 13);
    text.append("tspan").attr("fill", st.fg).attr("font-weight", d.label.weight).text(d.label.title);
    if (d.label.detail) {
      text.append("tspan").attr("dx", 8).attr("font-size", 12)
        .attr("fill", n.status === "unchanged" ? MUTED : st.fg).attr("fill-opacity", n.status === "unchanged" ? 1 : 0.85)
        .text(d.label.detail);
    }
    label.append("title").text([n.name, n.status === "removed" ? n.before : n.after].filter(Boolean).join("\n"));
  });

  if (!nodes.length) {
    svg.append("text").attr("x", PAD).attr("y", HEADER + PAD + 20).attr("fill", MUTED).attr("font-size", 13)
      .text(query ? "Brak wyników dla wyszukiwanej frazy." : "Brak różnic w strukturze.");
  }
}

function drawHeader(svg, onlyChanges, query) {
  const g = svg.append("g").attr("transform", `translate(${PAD},${PAD + 4})`);
  g.append("text").attr("font-size", 15).attr("font-weight", 600).attr("fill", "#1f2328")
    .text(`Diff struktury: ${ENV.old} (${data.files.old})  →  ${ENV.new} (${data.files.new})`);
  const filters = [onlyChanges ? "tylko zmiany" : "wszystkie elementy", query ? `filtr: "${query}"` : null].filter(Boolean);
  g.append("text").attr("y", 20).attr("font-size", 12).attr("fill", MUTED)
    .text(`${summaryText()}  ·  ${filters.join(", ")}`);
  let x = 0;
  for (const key of ["added", "removed", "modified"]) {
    const st = STATUS[key];
    const item = g.append("g").attr("transform", `translate(${x},34)`);
    item.append("rect").attr("width", 14).attr("height", 14).attr("rx", 3).attr("fill", st.bg).attr("stroke", st.fg);
    const label = `${st.mark} ${LEGEND[key]}`;
    item.append("text").attr("x", 20).attr("y", 11).attr("font-size", 12).attr("fill", st.fg).text(label);
    x += 20 + textWidth(label, 12) + 22;
  }
}

function summaryText() {
  const parts = [];
  for (const [kind, label] of Object.entries(SUMMARY_LABEL)) {
    const c = data.summary[kind];
    if (!c) continue;
    const changes = [["added", "+"], ["removed", "−"], ["modified", "~"]].filter(([s]) => c[s]).map(([s, m]) => `${m}${c[s]}`);
    if (changes.length) parts.push(`${label} ${changes.join(" ")}`);
  }
  return parts.length ? parts.join(" · ") : "Brak różnic";
}

/* ---------- interaction ---------- */

function toggleNode(n) {
  if (!n.children.length) return;
  collapsed.has(n.key) ? collapsed.delete(n.key) : collapsed.add(n.key);
  render();
}

function findNode(key, node = data.tree) {
  if (node.key === key) return node;
  for (const child of node.children) {
    const found = findNode(key, child);
    if (found) return found;
  }
  return null;
}

function selectNode(n) {
  selectedKey = n.key;
  render();
  // Rendered nodes are filtered copies; the panel needs the full, unfiltered node.
  showDetails(findNode(n.key));
}

function showDetails(n) {
  const panel = $("#details");
  panel.innerHTML = "";
  if (!n) {
    panel.append(h("p", { class: "muted" }, "Kliknij element drzewa, aby zobaczyć szczegóły. Kliknij kółko, aby zwinąć lub rozwinąć gałąź."));
    return;
  }
  panel.append(
    h("div", { class: "kind" }, KIND_LABEL[n.kind] || n.kind),
    h("h2", {}, n.name),
    h("span", { class: `badge ${n.status}` }, STATUS[n.status].label),
  );
  if (n.kind === "group") {
    const counts = d3.rollup(n.children, (v) => v.length, (c) => c.status);
    panel.append(h("p", {}, [...counts].map(([s, c]) => `${STATUS[s].label}: ${c}`).join(", ")));
    return;
  }
  const isDefinition = DEFINITION_KINDS.has(n.kind);
  if (n.changes && !isDefinition) {
    panel.append(h("table", {},
      h("tr", {}, h("th", {}, "pole"), h("th", {}, ENV.old), h("th", {}, ENV.new)),
      n.changes.map((c) => h("tr", {},
        h("td", {}, FIELD_LABEL[c.field] || c.field),
        h("td", { class: "before" }, fmt(c.field, c.before)),
        h("td", { class: "after" }, fmt(c.field, c.after)))),
    ));
  }
  if (n.kind === "table") {
    panel.append(columnList(n));
    return;
  }
  if (n.before !== undefined && (n.status !== "unchanged" || isDefinition)) {
    panel.append(h("h3", {}, ENV.old), h("pre", { class: "before" }, n.before || "∅"));
  }
  if (n.after !== undefined && n.status !== "removed") {
    panel.append(h("h3", {}, n.status === "unchanged" ? "Definicja" : ENV.new), h("pre", { class: "after" }, n.after || "∅"));
  }
}

function columnList(table) {
  const columns = table.children.find((c) => c.key === `${table.key}/columns`)?.children || [];
  const definition = (c) => {
    if (c.status === "modified") return [h("div", { class: "before" }, c.before), h("div", { class: "after" }, c.after)];
    return c.status === "removed" ? c.before : c.after;
  };
  return h("div", {},
    h("h3", {}, `Kolumny (${columns.length})`),
    h("table", { class: "columns" },
      columns.map((c) => h("tr", { class: `row-${c.status}` },
        h("td", { class: "mark" }, STATUS[c.status].mark),
        h("td", { class: "name" }, c.name),
        h("td", { class: "def" }, definition(c))))));
}

function showWarnings() {
  const box = $("#warnings");
  const items = [
    ...data.warnings.old.map((w) => `${ENV.old}: ${w}`),
    ...data.warnings.new.map((w) => `${ENV.new}: ${w}`),
  ];
  box.hidden = !items.length;
  box.innerHTML = "";
  if (items.length) box.append(h("strong", {}, "Ostrzeżenia parsera"), h("ul", {}, items.map((i) => h("li", {}, i))));
}

function showSummary() {
  const box = $("#summary");
  box.innerHTML = "";
  for (const [kind, label] of Object.entries(SUMMARY_LABEL)) {
    const c = data.summary[kind];
    if (!c) continue;
    const total = Object.values(c).reduce((a, b) => a + b, 0);
    box.append(h("span", { class: "summary-item" }, h("b", {}, label), h("span", { class: "total" }, total),
      ...[["added", "+"], ["removed", "−"], ["modified", "~"]]
        .filter(([s]) => c[s])
        .map(([s, m]) => h("span", { class: `count-badge ${s}`, title: STATUS[s].label }, `${m}${c[s]}`))));
  }
}

function exportSvg() {
  const svg = $("#canvas svg").cloneNode(true);
  svg.querySelectorAll("[data-selected]").forEach((el) => {
    el.removeAttribute("stroke");
    el.removeAttribute("data-selected");
  });
  const source = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob([source], { type: "image/svg+xml;charset=utf-8" }));
  const a = h("a", { href: url, download: `schema-diff_prod-vs-preprod_${new Date().toISOString().slice(0, 10)}.svg` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("#only-changes").addEventListener("change", render);
$("#search").addEventListener("input", render);
$("#expand").addEventListener("click", () => { collapsed.clear(); render(); });
$("#collapse").addEventListener("click", () => {
  walk(data.tree, (n, depth) => { if (n.children.length && depth >= 1) collapsed.add(n.key); });
  render();
});
$("#export").addEventListener("click", exportSvg);
