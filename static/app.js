const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const KIND_ZH = {
  verb: "动词", noun: "名词", adjective: "形容词", adverb: "副词", preposition: "介词",
  conjunction: "连词", pronoun: "代词", article: "冠词", particle: "小品词", numeral: "数词", other: "",
};
const GROUP_TITLE = { verb: "变位", noun: "变格", adjective: "变格与比较" };
const PLAY_ICON = '<svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 4V5L7 9H3Zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4ZM14 3.23v2.06A7 7 0 0 1 14 18.7v2.06A9 9 0 0 0 14 3.23Z"/></svg>';

let aiEnabled = false;
let lookupSeq = 0;
let lastDictHash = "#/"; // 从翻译页切回时回到之前查的词

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, {
      ...opts,
      headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new Error("连不上词典程序。请先启动词典服务（macOS 双击 start.command，Windows 双击 start.bat），并保持窗口开着。");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `请求失败 (${res.status})`);
  return data;
}

/* ---------- 小组件 ---------- */

const levelBadge = (lv) =>
  lv ? `<span class="badge lv-${esc(lv)}" title="欧洲语言共同参考框架等级">${esc(lv)}</span>`
     : `<span class="badge lv-none" title="网站未标注等级">未分级</span>`;

function lemmaHtml(lemma) {
  const m = /^(der|die|das)\s+(.+)$/i.exec(lemma);
  if (!m) return esc(lemma);
  const art = m[1].toLowerCase();
  return `<span class="art ${art}">${esc(m[1])}</span>${esc(m[2])}`;
}

const playBtn = (url) =>
  url ? `<button class="play" data-audio="${esc(url)}" title="朗读">${PLAY_ICON}</button>` : "";

const COPY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 1H6a2 2 0 0 0-2 2v13h2V3h10V1Zm3 4H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2Zm0 16h-9V7h9v14Z"/></svg>';
const COPIED_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.5 16.2 5.3 12l-1.4 1.4 5.6 5.6L21 7.5l-1.4-1.4L9.5 16.2Z"/></svg>';
// 复制的是词头（名词带冠词）；可分动词去掉分隔点：auf·stehen → aufstehen
const copyBtn = (word) =>
  `<button class="copy-btn" data-copy="${esc(word.replace(/·/g, ""))}" title="复制单词" aria-label="复制单词">${COPY_ICON}</button>`;

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // 个别环境不允许访问剪贴板时的备用方法
    const t = document.createElement("textarea");
    t.value = text;
    document.body.append(t);
    t.select();
    document.execCommand("copy");
    t.remove();
  }
}

function tagsHtml(tags, kind) {
  const list = [...tags];
  if (kind && KIND_ZH[kind] && !list.includes(KIND_ZH[kind])) list.unshift(KIND_ZH[kind]);
  return list.map((t) => `<span class="tag">${esc(t)}</span>`).join("");
}

function examplesHtml(examples) {
  return `<ul class="examples">${examples.map((e) => `
    <li><div class="de">${esc(e.de)}</div>
    ${e.zh ? `<div class="tr">${esc(e.zh)}<span class="ai">AI</span></div>` : ""}
    ${e.en ? `<div class="tr">${esc(e.en)}</div>` : ""}</li>`).join("")}</ul>`;
}

function valencyHtml(v) {
  if (!v) return "";
  const parts = v.replace(/^\(|\)$/g, "").split(",").map((s) => s.trim()).filter(Boolean);
  return `<div class="valency" title="常见搭配（支配的格 / 介词）">${parts.map((p) => `<span>${esc(p)}</span>`).join("")}</div>`;
}

/* ---------- 释义卡片（含 AI 中文） ---------- */

function meaningCard(id, info) {
  const en = info.english?.length ? `<div class="en-line"><b>EN</b>${esc(info.english.slice(0, 12).join(", "))}</div>` : "";
  const site = info.chinese_site?.length ? `<div class="site-zh">网站中文：${esc(info.chinese_site.join("，"))}</div>` : "";
  return `<div class="card"><h2>释义</h2>
    <div id="${id}-zh">${aiEnabled ? '<div class="skeleton" style="width:60%"></div><div class="skeleton" style="width:40%"></div>' : ""}</div>
    ${en}${site}${valencyHtml(info.valency)}</div>
    <div id="${id}-usage"></div>`;
}

async function loadGloss(id, info) {
  const zhEl = $(`#${id}-zh`);
  if (!aiEnabled) {
    zhEl.innerHTML = `<p class="muted">在右上角的 <a href="#" data-open-settings>设置</a> 中添加 DeepSeek 密钥后，这里会显示中文释义和用法。</p>`;
    return;
  }
  const seq = lookupSeq;
  try {
    const g = await api("/api/gloss", {
      method: "POST",
      body: JSON.stringify({
        lemma: info.lemma, kind: info.kind, tags: info.tags || [], english: info.english || [],
        definitions: info.definitions || [], definition: info.definition || "",
      }),
    });
    if (seq !== lookupSeq) return;
    zhEl.innerHTML = `<ol class="senses">${(g.senses || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ol>`;
    const parts = [];
    if (g.usage?.length) parts.push(`<div class="card"><h2>用法</h2><ul class="usage">${g.usage.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></div>`);
    if (g.examples?.length) parts.push(`<div class="card"><h2>常用例句</h2>${examplesHtml(g.examples)}</div>`);
    $(`#${id}-usage`).innerHTML = parts.join("");
  } catch (e) {
    if (seq === lookupSeq) zhEl.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

/* ---------- 变位 / 变格表 ---------- */

function tablesCard(data) {
  if (!data.groups?.length) return "";
  const tabs = data.groups.map((g, i) => `<button data-g="${i}" class="${i ? "" : "active"}">${esc(g.title)}</button>`).join("");
  return `<div class="card" id="tables-card"><h2>${GROUP_TITLE[data.kind] || "词形变化"}</h2>
    ${data.groups.length > 1 ? `<div class="tabs">${tabs}</div>` : ""}
    <div class="tables" id="tables">${groupHtml(data.groups[0])}</div></div>`;
}

// “Trinkwassern/Trinkwässern” 这样的两种写法中间没有空格，要允许在 / 后换行
// 只处理文字里的 /，不能碰到 </u> 这样的标签
const breakAfterSlash = (s) => s.replace(/\/(?![^<]*>)/g, "/<wbr>");

function groupHtml(g) {
  return g.tables.map((t) => `<div class="tbl">${t.title ? `<h3>${esc(t.title)}</h3>` : ""}<table>
    ${t.rows.map((r) => r.length > 1
      ? `<tr><td class="p">${r[0]}</td><td class="w">${breakAfterSlash(r.slice(1).join(" "))}</td></tr>`
      : `<tr><td class="w">${breakAfterSlash(r[0])}</td></tr>`).join("")}
    </table></div>`).join("");
}

/* ---------- 渲染结果 ---------- */

function renderDetail(res) {
  const d = res.result;
  const ex = d.examples?.length ? d.examples : d.example ? [d.example] : [];
  let html = `<div class="card">
      ${res.note ? `<div class="notice">${esc(res.note)}</div>` : ""}
      <div class="head-card">
        <div class="head-info">
          <div class="head-top">${levelBadge(d.level)}${tagsHtml(d.tags, d.kind)}</div>
          <div class="lemma-row"><div class="lemma">${lemmaHtml(d.lemma)}</div>${playBtn(d.audio)}${copyBtn(d.lemma)}</div>
          ${d.forms ? `<div class="forms">${d.forms}</div>` : ""}
          ${d.ipa ? `<div class="ipa">${esc(d.ipa)}</div>` : ""}
          ${d.notes ? `<div class="notes">${esc(d.notes)}</div>` : ""}
        </div>
        ${aiEnabled ? `<figure class="pic" id="pic"><div class="pic-box"><div class="pic-loading"></div></div></figure>` : ""}
      </div>
    </div>`;
  html += meaningCard("m0", d);
  html += tablesCard(d);
  if (d.usages?.length) html += `<div class="card"><h2>介词搭配</h2><ul class="usage">${d.usages.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></div>`;
  if (ex.length) html += `<div class="card"><h2>例句</h2>${examplesHtml(ex)}</div>`;
  if (d.definitions?.length) html += `<div class="card"><details><summary>德语释义（${d.definitions.length}）</summary><ul class="defs">${d.definitions.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details></div>`;
  html += relatedHtml(res.related);
  $("#result").innerHTML = html;

  const tabsEl = $("#tables-card .tabs");
  if (tabsEl) tabsEl.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-g]");
    if (!b) return;
    tabsEl.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    $("#tables").innerHTML = groupHtml(d.groups[+b.dataset.g]);
  });
  const info = { ...d, lemma: d.lemma.replace(/^(der|die|das)\s+/i, "") };
  loadGloss("m0", info);
  loadPicture(info);
}

/* ---------- 配图 ---------- */

async function loadPicture(info) {
  const fig = $("#pic");
  if (!fig) return;
  const seq = lookupSeq;
  const body = JSON.stringify({ lemma: info.lemma, kind: info.kind, english: (info.english || []).slice(0, 6) });
  // 第一次查的词，搜索和挑选照片要等一阵，先显示 emoji，照片到了再替换
  let settled = false;
  api("/api/image/emoji", { method: "POST", body }).then((q) => {
    if (!settled && seq === lookupSeq && q.emoji) fig.innerHTML = `<div class="pic-box pic-emoji">${esc(q.emoji)}</div>`;
  }).catch(() => {});
  let r;
  try {
    r = await api("/api/image", { method: "POST", body });
  } catch {
    settled = true;
    if (seq === lookupSeq) fig.remove();
    return;
  }
  settled = true;
  if (seq !== lookupSeq) return;
  let i = 0;
  const emoji = () => {
    fig.innerHTML = r.emoji ? `<div class="pic-box pic-emoji">${esc(r.emoji)}</div>` : "";
    if (!r.emoji) fig.remove();
  };
  const show = () => {
    const im = r.images[i];
    fig.innerHTML = `<div class="pic-box">
        <img src="/api/thumb?url=${encodeURIComponent(im.thumb)}" alt="${esc(info.lemma)}" loading="lazy">
        ${r.images.length > 1 ? `<button class="pic-next" title="换一张">换一张</button>` : ""}
      </div>
      <figcaption><a href="${esc(im.link)}" target="_blank" rel="noopener">${esc(im.creator)}${im.license ? ` · ${esc(im.license)}` : ""}</a></figcaption>`;
    const img = fig.querySelector("img");
    img.onload = () => img.classList.add("loaded");
    img.onerror = () => { r.images.splice(i, 1); if (r.images.length) { i %= r.images.length; show(); } else emoji(); };
    const next = fig.querySelector(".pic-next");
    if (next) next.onclick = () => { i = (i + 1) % r.images.length; show(); };
  };
  if (r.images?.length) show(); else emoji();
}

function renderList(res) {
  const entries = res.result.entries;
  let html = res.note ? `<div class="notice">${esc(res.note)}</div>` : "";
  entries.forEach((e, i) => {
    html += `<div class="card">
      <div class="head-top">${levelBadge(e.level)}${tagsHtml(e.tags, e.kind)}</div>
      <div class="entry-head"><div class="lemma">${esc(e.lemma)}</div>${copyBtn(e.lemma)}${e.ipa ? `<span class="ipa">${esc(e.ipa)}</span>` : ""}</div>
      ${e.forms ? `<div class="forms">${e.forms}</div>` : ""}
      ${e.definition ? `<p class="muted">${esc(e.definition)}</p>` : ""}
      ${e.example ? examplesHtml([e.example]) : ""}
    </div>`;
    html += meaningCard(`m${i}`, e);
  });
  html += relatedHtml(res.related);
  $("#result").innerHTML = html;
  entries.forEach((e, i) => loadGloss(`m${i}`, e));
}

function relatedHtml(list) {
  if (!list?.length) return "";
  return `<div class="card"><h2>相关词</h2><div class="related">${list.map((e) =>
    `<button class="chip" data-${e.link?.startsWith("/") ? "path" : "word"}="${esc(e.link?.startsWith("/") ? e.link : e.lemma)}">
      ${e.level ? `<span class="lv lv-${esc(e.level)} badge">${esc(e.level)}</span>` : ""}${esc(e.lemma)}</button>`).join("")}</div></div>`;
}

function renderZh(res) {
  const rows = res.result.candidates.map((c) => `
    <button class="cand" data-word="${esc(c.de.replace(/^(der|die|das)\s+/i, ""))}">
      <div class="cand-main"><span class="cand-de">${lemmaHtml(c.de)}</span>${c.pos ? `<span class="tag">${esc(c.pos)}</span>` : ""}</div>
      <div class="cand-zh">${esc(c.zh)}</div>
      ${c.note ? `<div class="cand-note">${esc(c.note)}</div>` : ""}
      <svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>
    </button>`).join("");
  const src = res.result.src === "en" ? "英语" : "中文";
  $("#result").innerHTML = `<div class="card"><h2>${src}“<span class="q">${esc(res.query)}</span>” 的德语说法</h2>
    <div class="cands">${rows}</div><p class="muted">点击单词查看变位、冠词和用法 · 候选词由 AI 提供</p></div>`;
}

function renderPhrase(res) {
  const p = res.result;
  let html = `<div class="card">
      <div class="head-top">${levelBadge(p.level)}<span class="tag">短语</span></div>
      <div class="lemma">${esc(res.query)}</div>
      <div class="phrase-zh">${esc(p.translation)}</div>
      <p class="muted">词典中没有收录这个短语，以下讲解由 AI 提供。</p>
    </div>`;
  if (p.usage?.length) html += `<div class="card"><h2>用法</h2><ul class="usage">${p.usage.map((u) => `<li>${esc(u)}</li>`).join("")}</ul></div>`;
  if (p.words?.length) html += `<div class="card"><h2>逐词拆解</h2><div class="cands">${p.words.map((w) => `
    <button class="cand" data-word="${esc(w.de)}">
      <div class="cand-main"><span class="cand-de">${esc(w.form || w.de)}</span>${w.form && w.form !== w.de ? `<span class="tag">原形 ${esc(w.de)}</span>` : ""}</div>
      <div class="cand-zh">${esc(w.zh)}</div>
      ${w.note ? `<div class="cand-note">${esc(w.note)}</div>` : ""}
      <svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>
    </button>`).join("")}</div><p class="muted">点击单词查看完整词条</p></div>`;
  if (p.examples?.length) html += `<div class="card"><h2>例句</h2>${examplesHtml(p.examples)}</div>`;
  $("#result").innerHTML = html;
}

function render(res) {
  document.body.classList.add("has-result");
  $("#history").hidden = true;
  if (res.result.type === "detail") renderDetail(res);
  else if (res.result.type === "list") renderList(res);
  else if (res.result.type === "foreign") renderZh(res);
  else if (res.result.type === "phrase") renderPhrase(res);
  else $("#result").innerHTML = `<div class="empty"><div class="big">没有找到 “${esc(res.query)}”</div>
    检查拼写，或试试输入原形。${aiEnabled ? "" : "（在设置中添加 DeepSeek 密钥后可自动识别变形词）"}</div>`;
  // 像 kind、gift、hand 这种德英同形的小写词，按德语查到后，给出“当作英语查”的入口
  if (aiEnabled && res.result.type !== "foreign" && /^[a-z][a-z' -]*$/.test(res.query || "")) {
    $("#result").insertAdjacentHTML("beforeend",
      `<p class="switch-lang">想查的是英语？<a href="#/en/${encodeURIComponent(res.query)}">把 “${esc(res.query)}” 当作英语查德语 →</a></p>`);
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------- 查词 ---------- */

async function lookup(word, path, lang = "") {
  const seq = ++lookupSeq;
  document.body.classList.add("has-result");
  $("#history").hidden = true;
  $("#setup-banner")?.remove();
  $("#result").innerHTML = '<div class="spinner"></div>';
  try {
    const res = path ? await api(`/api/open?path=${encodeURIComponent(path)}`)
                     : await api(`/api/lookup?q=${encodeURIComponent(word)}&lang=${lang}`);
    if (seq !== lookupSeq) return;
    render(res);
  } catch (e) {
    if (seq === lookupSeq) $("#result").innerHTML = `<div class="empty"><div class="big">出错了</div>${esc(e.message)}</div>`;
  }
}

// 程序填入单词时，光标要跟着移到词尾（否则可能还画在输入框为空时的位置）
function setQuery(word) {
  const q = $("#q");
  q.value = word;
  if (document.activeElement === q) q.setSelectionRange(word.length, word.length);
}

function go(word) {
  word = word.trim();
  if (!word) return;
  setQuery(word);
  const h = `#/w/${encodeURIComponent(word)}`;
  if (location.hash === h) lookup(word); else location.hash = h;
}

async function showHome() {
  lookupSeq++;
  document.body.classList.remove("has-result");
  $("#result").innerHTML = "";
  $("#q").value = "";
  const h = $("#history");
  h.hidden = false;
  $("#setup-banner")?.remove();
  if (!aiEnabled) h.insertAdjacentHTML("afterend",
    `<p class="setup-banner" id="setup-banner">还没有添加 DeepSeek 密钥，中文释义、翻译等功能暂不可用。<button data-open-settings>去设置</button></p>`);
  try {
    const list = await api("/api/history");
    h.innerHTML = list.length
      ? `<span class="label">最近查询</span>${list.map((x) => `<button class="chip" data-word="${esc(x.word)}">${x.level ? `<span class="badge lv lv-${esc(x.level)}">${esc(x.level)}</span>` : ""}${esc(x.word)}</button>`).join("")}<button class="link-btn" id="clear-history">清除</button>`
      : "";
  } catch { h.innerHTML = ""; }
}

function route() {
  const hash = location.hash;
  if (hash.startsWith("#/translate")) return switchTab("translate", false);
  if (hash.startsWith("#/ask")) return switchTab("ask", false);
  switchTab("dict", false);
  lastDictHash = hash || "#/";
  let m = /^#\/w\/(.+)$/.exec(hash);
  if (m) { const w = decodeURIComponent(m[1]); setQuery(w); return lookup(w); }
  m = /^#\/en\/(.+)$/.exec(hash);
  if (m) { const w = decodeURIComponent(m[1]); setQuery(w); return lookup(w, null, "en"); }
  m = /^#\/p\/(.+)$/.exec(hash);
  if (m) return lookup(null, decodeURIComponent(m[1]));
  showHome();
}

function switchTab(tab, push = true) {
  const seg = $(".segmented");
  const changed = seg.dataset.active !== tab;
  seg.dataset.active = tab;
  seg.querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("#tab-dict").hidden = tab !== "dict";
  $("#tab-translate").hidden = tab !== "translate";
  $("#tab-ask").hidden = tab !== "ask";
  if (changed) {
    const el = $(`#tab-${tab}`);
    el.classList.remove("entering");
    void el.offsetWidth; // 重新触发淡入动画
    el.classList.add("entering");
  }
  if (push) location.hash = tab === "dict" ? lastDictHash : `#/${tab}`;
  if (tab === "translate") setTimeout(() => $("#tr-input").focus(), 0);
  if (tab === "ask") setTimeout(() => $("#ask-input").focus(), 0);
}

/* ---------- 翻译 ---------- */

async function translate() {
  const text = $("#tr-input").value.trim();
  if (!text) return;
  const btn = $("#tr-btn");
  btn.disabled = true; btn.textContent = "翻译中…";
  $("#tr-result").innerHTML = '<div class="card"><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:55%"></div></div>';
  try {
    const r = await api("/api/translate", { method: "POST", body: JSON.stringify({ text }) });
    const dir = r.target === "de" ? "→ 德语" : "→ 中文";
    $("#tr-result").innerHTML = `<div class="card"><div class="tr-meta">${dir}</div><div class="tr-text">${esc(r.translation)}</div></div>
      ${r.notes?.length ? `<div class="card"><h2>要点</h2><ul class="usage">${r.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : ""}`;
  } catch (e) {
    $("#tr-result").innerHTML = `<div class="card"><p class="error">${esc(e.message)}</p></div>`;
  } finally {
    btn.disabled = false; btn.textContent = "翻译";
  }
}

/* ---------- 问 AI ---------- */

const ASK_STORE = "ask-messages";
let askMessages = [];
let askAbort = null;

// 把 AI 回答的 Markdown 转成 HTML：所有文字先转义，只生成下面这些固定标签
function mdInline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
}

function mdTableRow(line, tag) {
  const cells = line.trim().replace(/^\||\|$/g, "").split("|");
  return `<tr>${cells.map((c) => `<${tag}>${mdInline(c.trim())}</${tag}>`).join("")}</tr>`;
}

function renderMarkdown(src) {
  const lines = src.split("\n");
  const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l || "") && (l || "").includes("-") && (l || "").includes("|");
  let html = "", i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      const code = [];
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) code.push(lines[i]);
      i++;
      html += `<pre><code>${esc(code.join("\n"))}</code></pre>`;
    } else if (line.includes("|") && isTableSep(lines[i + 1])) {
      let rows = mdTableRow(line, "th");
      for (i += 2; i < lines.length && lines[i].includes("|"); i++) rows += mdTableRow(lines[i], "td");
      html += `<div class="ask-table-wrap"><table>${rows}</table></div>`;
    } else if (/^#{1,6}\s/.test(line)) {
      html += `<h4>${mdInline(line.replace(/^#+\s*/, ""))}</h4>`;
      i++;
    } else if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      html += "<hr>";
      i++;
    } else if (/^\s*>/.test(line)) {
      const quote = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) quote.push(mdInline(lines[i].replace(/^\s*>\s?/, "")));
      html += `<blockquote>${quote.join("<br>")}</blockquote>`;
    } else if (/^\s*([-*+]|\d+\.)\s/.test(line)) {
      const tag = /^\s*\d+\./.test(line) ? "ol" : "ul";
      const items = [];
      for (; i < lines.length && /^\s*([-*+]|\d+\.)\s/.test(lines[i]); i++) items.push(`<li>${mdInline(lines[i].replace(/^\s*([-*+]|\d+\.)\s/, ""))}</li>`);
      html += `<${tag}>${items.join("")}</${tag}>`;
    } else if (!line.trim()) {
      i++;
    } else {
      const para = [];
      for (; i < lines.length && lines[i].trim() && !/^(\s*```|#{1,6}\s|\s*>|\s*([-*+]|\d+\.)\s)/.test(lines[i]) && !(lines[i].includes("|") && isTableSep(lines[i + 1])); i++) para.push(mdInline(lines[i]));
      if (!para.length) { html += `<p>${mdInline(lines[i])}</p>`; i++; } else html += `<p>${para.join("<br>")}</p>`;
    }
  }
  return html;
}

function askMessageHtml(m) {
  return m.role === "user"
    ? `<div class="ask-msg user">${esc(m.content)}</div>`
    : `<div class="ask-msg assistant">${renderMarkdown(m.content)}</div>`;
}

function askRender() {
  $("#ask-messages").innerHTML = askMessages.map(askMessageHtml).join("");
  const chatting = askMessages.length > 0;
  $("#tab-ask").classList.toggle("chatting", chatting);
  $("#ask-new").hidden = !chatting;
}

function askSave() {
  try { localStorage.setItem(ASK_STORE, JSON.stringify(askMessages.slice(-100))); } catch {}
}

function askSetBusy(busy) {
  const btn = $("#ask-send");
  btn.textContent = busy ? "停止" : "发送";
  btn.classList.toggle("is-stop", busy);
}

const askNearBottom = () => innerHeight + scrollY >= document.documentElement.scrollHeight - 120;
const askScrollDown = () => window.scrollTo(0, document.documentElement.scrollHeight);

async function askSend(text) {
  text = text.trim();
  if (!text || askAbort) return;
  $("#ask-input").value = "";
  askAutosize();
  askMessages.push({ role: "user", content: text });
  askRender();
  askScrollDown();
  const box = document.createElement("div");
  box.className = "ask-msg assistant";
  box.innerHTML = '<span class="muted">思考中…</span><span class="ask-cursor"></span>';
  $("#ask-messages").append(box);
  askScrollDown();

  const controller = new AbortController();
  askAbort = controller;
  askSetBusy(true);
  let answer = "";
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: askMessages }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `请求失败 (${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      answer += decoder.decode(value, { stream: true });
      const follow = askNearBottom();
      box.innerHTML = renderMarkdown(answer) + '<span class="ask-cursor"></span>';
      if (follow) askScrollDown();
    }
    if (!answer) throw new Error("DeepSeek 没有返回内容，请重试");
  } catch (e) {
    if (e.name !== "AbortError") {
      // 出错时不把这一问留在上下文里，把问题放回输入框方便重试
      if (!answer) {
        askMessages.pop();
        $("#ask-input").value = text;
        askAutosize();
        askRender();
        const message = /fetch|network/i.test(e.message) ? "连不上词典程序，请确认程序在运行。" : e.message;
        $("#ask-messages").insertAdjacentHTML("beforeend", `<div class="ask-msg error">${esc(message)}</div>`);
      }
    } else if (!answer) {
      askMessages.pop();
      $("#ask-input").value = text;
      askAutosize();
      askRender();
    }
  } finally {
    if (askMessages.at(-1)?.role === "user" && answer) askMessages.push({ role: "assistant", content: answer });
    if (answer) box.innerHTML = renderMarkdown(answer);
    askAbort = null;
    askSetBusy(false);
    askSave();
  }
}

function askAutosize() {
  const t = $("#ask-input");
  t.style.height = "auto";
  t.style.height = `${t.scrollHeight}px`;
}

try { askMessages = JSON.parse(localStorage.getItem(ASK_STORE)) || []; } catch { askMessages = []; }
askRender();

$("#ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  if (askAbort) askAbort.abort(); else askSend($("#ask-input").value);
});
$("#ask-input").addEventListener("input", askAutosize);
$("#ask-input").addEventListener("keydown", (e) => {
  // isComposing：用输入法打中文时，按回车是选字，不能发送
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    if (!askAbort) askSend($("#ask-input").value);
  }
});
$("#ask-suggestions").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (b) askSend(b.textContent);
});
$("#ask-new").addEventListener("click", () => {
  if (askAbort) askAbort.abort();
  askMessages = [];
  askSave();
  askRender();
  $("#ask-input").focus();
});

// 模型切换：列表实时来自 DeepSeek，所选模型只用于“问 AI”
let modelCurrent = "";

function modelMenuClose() {
  $("#model-menu").hidden = true;
  $("#model-btn").setAttribute("aria-expanded", "false");
}

function modelMenuRender(models) {
  $("#model-menu").innerHTML = models.map((m) =>
    `<button type="button" class="model-item${m === modelCurrent ? " active" : ""}" role="option" data-model="${esc(m)}">
      <span>${esc(m)}</span><span class="check">✓</span></button>`).join("");
}

async function modelMenuOpen() {
  const menu = $("#model-menu");
  menu.innerHTML = '<div class="model-note">正在获取模型列表…</div>';
  menu.hidden = false;
  $("#model-btn").setAttribute("aria-expanded", "true");
  try {
    const r = await api("/api/ask/models");
    modelCurrent = r.current;
    $("#model-name").textContent = modelCurrent;
    modelMenuRender(r.models);
  } catch (e) {
    menu.innerHTML = `<div class="model-note">${esc(e.message)}</div>`;
  }
}

$("#model-btn").addEventListener("click", () => {
  if ($("#model-menu").hidden) modelMenuOpen(); else modelMenuClose();
});
$("#model-menu").addEventListener("click", async (e) => {
  const item = e.target.closest("[data-model]");
  if (!item) return;
  try {
    const r = await api("/api/ask/model", { method: "POST", body: JSON.stringify({ model: item.dataset.model }) });
    modelCurrent = r.current;
    $("#model-name").textContent = modelCurrent;
    modelMenuClose();
  } catch (err) {
    $("#model-menu").innerHTML = `<div class="model-note">${esc(err.message)}</div>`;
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".model-picker")) modelMenuClose();
});

/* ---------- 输入联想 ---------- */

const SEARCH_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.96 12.06l4.24 4.24a1 1 0 0 1-1.42 1.42l-4.24-4.24A7.5 7.5 0 1 1 10.5 3Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Z"/></svg>';
const sug = { items: [], active: -1, seq: 0, timer: 0 };

function hideSuggest() {
  $("#suggest").hidden = true;
  sug.active = -1;
}

function renderSuggest() {
  const box = $("#suggest");
  const q = $("#q").value.trim();
  if (!sug.items.length || document.activeElement !== $("#q")) return hideSuggest();
  box.innerHTML = sug.items.map((w, i) => {
    // 输入部分正常显示，补全部分加粗（苹果搜索的做法）
    const n = w.toLowerCase().startsWith(q.toLowerCase()) ? q.length : 0;
    return `<div class="sug-row${i === sug.active ? " active" : ""}" role="option" data-i="${i}">
      ${SEARCH_ICON}<span>${esc(w.slice(0, n))}<b>${esc(w.slice(n))}</b></span></div>`;
  }).join("");
  box.hidden = false;
}

function updateSuggest() {
  clearTimeout(sug.timer);
  const q = $("#q").value.trim();
  if (!q || /[一-鿿\s]/.test(q)) { sug.items = []; return hideSuggest(); }
  sug.timer = setTimeout(async () => {
    const seq = ++sug.seq;
    try {
      const items = await api(`/api/suggest?q=${encodeURIComponent(q)}`);
      if (seq !== sug.seq) return;
      sug.items = items;
      sug.active = -1;
      renderSuggest();
    } catch { hideSuggest(); }
  }, 60);
}

$("#q").addEventListener("input", updateSuggest);
$("#q").addEventListener("focus", () => { if (sug.items.length) renderSuggest(); });
$("#q").addEventListener("blur", () => setTimeout(hideSuggest, 100));
$("#q").addEventListener("keydown", (e) => {
  if ($("#suggest").hidden) return;
  const n = sug.items.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    sug.active = e.key === "ArrowDown" ? (sug.active + 1) % n : (sug.active - 1 + n) % n;
    renderSuggest();
  } else if (e.key === "Enter" && sug.active >= 0) {
    e.preventDefault();
    const w = sug.items[sug.active];
    hideSuggest(); sug.items = [];
    go(w);
  } else if (e.key === "Escape") {
    hideSuggest();
  }
});
// 用 mousedown 防止输入框先失去焦点导致列表消失
$("#suggest").addEventListener("mousedown", (e) => {
  e.preventDefault();
  const row = e.target.closest(".sug-row");
  if (!row) return;
  const w = sug.items[+row.dataset.i];
  hideSuggest(); sug.items = [];
  go(w);
});
$("#suggest").addEventListener("mousemove", (e) => {
  const row = e.target.closest(".sug-row");
  if (row && +row.dataset.i !== sug.active) { sug.active = +row.dataset.i; renderSuggest(); }
});

/* ---------- 事件 ---------- */

$("#search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  hideSuggest(); sug.items = [];
  go($("#q").value);
});
// ä ö ü ß 按钮：把字母插入 data-target 指定的输入框的光标处
document.querySelectorAll(".umlauts").forEach((group) => group.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const q = document.getElementById(group.dataset.target);
  if (b.classList.contains("clear-btn")) {
    q.value = "";
    q.focus();
  } else {
    const s = q.selectionStart ?? q.value.length, t = q.selectionEnd ?? s;
    q.value = q.value.slice(0, s) + b.textContent + q.value.slice(t);
    q.focus(); q.setSelectionRange(s + 1, s + 1);
  }
  q.dispatchEvent(new Event("input", { bubbles: true })); // 触发输入联想、输入框自动增高
}));
$(".segmented").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tab]");
  if (b) switchTab(b.dataset.tab);
});
$("#tr-btn").addEventListener("click", translate);
$("#tr-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) translate(); });

document.addEventListener("click", async (e) => {
  const copy = e.target.closest(".copy-btn");
  if (copy) {
    await copyText(copy.dataset.copy);
    copy.innerHTML = COPIED_ICON;
    copy.classList.add("copied");
    copy.title = "已复制";
    clearTimeout(copy._timer);
    copy._timer = setTimeout(() => {
      copy.innerHTML = COPY_ICON;
      copy.classList.remove("copied");
      copy.title = "复制单词";
    }, 1500);
    return;
  }
  const chip = e.target.closest("[data-word],[data-path]");
  if (chip && !chip.matches("button.play")) {
    if (chip.dataset.path) location.hash = `#/p/${encodeURIComponent(chip.dataset.path)}`;
    else go(chip.dataset.word);
    return;
  }
  if (e.target.closest("#clear-history")) { await api("/api/history", { method: "DELETE" }); showHome(); return; }
  const play = e.target.closest("button.play");
  if (play) {
    const player = $("#player");
    player.src = `/api/audio?url=${encodeURIComponent(play.dataset.audio)}`;
    play.classList.add("playing");
    player.onended = player.onerror = () => play.classList.remove("playing");
    player.play().catch(() => play.classList.remove("playing"));
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
    e.preventDefault(); switchTab("dict"); $("#q").focus(); $("#q").select();
  }
});

window.addEventListener("hashchange", route);
/* ---------- 设置（API 密钥） ---------- */

let keyMasked = "";

function updateSettingsHint() {
  $("#settings-btn").classList.toggle("attention", !aiEnabled);
}

function openSettings() {
  $("#key-state").textContent = keyMasked ? `当前密钥：${keyMasked}（重新填写可替换）` : "尚未设置";
  $("#key-input").value = "";
  $("#key-msg").textContent = "";
  $("#settings").showModal();
  $("#key-input").focus();
}

$("#settings-btn").addEventListener("click", openSettings);
$("#settings-cancel").addEventListener("click", () => $("#settings").close());
$("#settings").addEventListener("click", (e) => { if (e.target === $("#settings")) $("#settings").close(); });
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-open-settings]")) { e.preventDefault(); openSettings(); }
});
$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#key-save");
  btn.disabled = true; btn.textContent = "验证中…";
  $("#key-msg").textContent = "";
  try {
    const r = await api("/api/settings/key", { method: "POST", body: JSON.stringify({ api_key: $("#key-input").value }) });
    aiEnabled = r.ai; keyMasked = r.key;
    updateSettingsHint();
    $("#settings").close();
    route();
  } catch (err) {
    $("#key-msg").textContent = err.message;
  } finally {
    btn.disabled = false; btn.textContent = "保存";
  }
});

api("/api/status").then((s) => {
  aiEnabled = s.ai; keyMasked = s.key || ""; updateSettingsHint();
  if (s.askModel) { modelCurrent = s.askModel; $("#model-name").textContent = s.askModel; }
  if (s.version) {
    $("#app-version").textContent = ` · v${s.version}`;
    $("#settings-version").textContent = `v${s.version}`;
  }
})
  .catch(() => {}).finally(route);
