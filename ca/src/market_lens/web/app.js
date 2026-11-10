const state = { signal: "all", platform: "all", sort: "volume", q: "", markets: [], page: 1, pageSize: 50, job: null, timer: null };
const $ = (selector) => document.querySelector(selector);
const fmtNumber = (value) => value == null ? "—" : new Intl.NumberFormat("en", { notation: value >= 1000000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
const fmtPct = (value) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const fmtDate = (value) => { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date); };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const signalNames = { large_probability_move: "概率快速变化", volume_spike: "成交量异常", probability_unavailable: "概率不可用", probability_comparison_unsupported: "非二元市场", market_not_open: "非开放" };

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok && response.status !== 409) throw new Error(data.error || `HTTP ${response.status}`);
  return { status: response.status, data };
}

async function loadMarkets() {
  const params = new URLSearchParams({ platform: state.platform, signal: state.signal, sort: state.sort, q: state.q });
  const { data } = await api(`/api/markets?${params}`);
  state.markets = data.markets || [];
  renderMarkets();
  await loadHealth();
}

async function loadHealth() {
  const { data } = await api("/api/health");
  const date = data.latest_capture;
  $("#updated-at").textContent = date ? `同步于 ${fmtDate(date)}` : "尚未同步";
  $("#stat-time").textContent = date ? fmtDate(date) : "—";
  $("#sync-health").textContent = date ? "数据已保存至本地" : "等待首次同步";
}

function renderMarkets() {
  const total = state.markets.length;
  const alerts = state.markets.filter((item) => item.anomaly_flags.length).length;
  const moving = state.markets.filter((item) => item.probability_change != null).length;
  $("#stat-total").textContent = fmtNumber(total);
  $("#stat-alerts").textContent = fmtNumber(alerts);
  $("#stat-moving").textContent = fmtNumber(moving);
  $("#result-count").textContent = `${total} 个市场`;
  $("#footer-count").textContent = `${total} 条记录`;
  const pageCount = Math.max(1, Math.ceil(total / state.pageSize));
  state.page = Math.min(state.page, pageCount);
  $("#page-status").textContent = `${state.page} / ${pageCount}`;
  $("#prev-page").disabled = state.page <= 1;
  $("#next-page").disabled = state.page >= pageCount;
  if (!total) {
    $("#market-rows").innerHTML = '<tr><td colspan="8" class="empty-state">没有匹配的市场。可以调整筛选，或先同步市场数据。</td></tr>';
    return;
  }
  const start = (state.page - 1) * state.pageSize;
  $("#market-rows").innerHTML = state.markets.slice(start, start + state.pageSize).map((item) => {
    const market = item.market;
    const change = item.probability_change;
    const changeClass = change == null ? "none" : change > 0 ? "up" : change < 0 ? "down" : "none";
    const changeText = change == null ? "—" : `${change > 0 ? "+" : ""}${(change * 100).toFixed(1)} pp`;
    const tags = item.anomaly_flags.length ? item.anomaly_flags.map((flag) => `<span class="signal-tag">${escapeHtml(signalNames[flag] || flag)}</span>`).join("") : '<span class="signal-tag neutral">正常</span>';
    return `<tr data-platform="${escapeHtml(market.platform)}" data-id="${escapeHtml(market.market_id)}"><td><div class="market-title">${escapeHtml(market.title)}</div><div class="market-id">${escapeHtml(market.market_id)}</div></td><td><span class="platform-badge ${market.platform === "kalshi" ? "kalshi" : ""}"><i></i>${market.platform === "kalshi" ? "Kalshi" : "Polymarket"}</span></td><td><span class="probability">${fmtPct(market.probability)}</span><span class="basis">${escapeHtml(market.probability_basis || "无有效报价")}</span></td><td><span class="change ${changeClass}">${changeText}</span></td><td class="volume-cell">${fmtNumber(market.volume)}</td><td class="end-cell">${fmtDate(market.end_time)}</td><td><div class="signal-list">${tags}</div></td><td class="row-chevron">›</td></tr>`;
  }).join("");
  document.querySelectorAll("#market-rows tr[data-id]").forEach((row) => row.addEventListener("click", () => openDetail(row.dataset.platform, row.dataset.id)));
}

async function refreshMarkets() {
  const button = $("#refresh-button");
  button.disabled = true;
  button.querySelector(".button-icon").classList.add("spin");
  $("#sync-health").textContent = "正在从公开 API 采集…";
  try {
    const { data } = await api("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ limit: 100 }) });
    if (data.status === "running") {
      state.job = data.id;
      pollRefresh();
      return;
    }
  } catch (error) {
    showToast(`同步失败：${error.message}`);
    button.disabled = false;
    button.querySelector(".button-icon").classList.remove("spin");
  }
}

function pollRefresh() {
  clearTimeout(state.timer);
  state.timer = setTimeout(async () => {
    try {
      const { data } = await api(`/api/refresh/status?job=${encodeURIComponent(state.job)}`);
      if (data.status === "running") { pollRefresh(); return; }
      $("#refresh-button").disabled = false;
      $("#refresh-button .button-icon").classList.remove("spin");
      const counts = Object.entries(data.provider_counts || {}).map(([name, count]) => `${name}: ${count}`).join(" · ");
      const errors = data.provider_errors || [];
      $("#provider-errors").hidden = errors.length === 0;
      $("#provider-errors").textContent = errors.map((item) => `${item.provider}: ${item.error}`).join(" | ");
      if (data.status === "failed") showToast(`采集失败：${data.error}`);
      else showToast(errors.length ? `部分完成 ${counts}` : `同步完成 ${counts}`);
      await loadMarkets();
    } catch (error) {
      $("#refresh-button").disabled = false;
      $("#refresh-button .button-icon").classList.remove("spin");
      showToast(`读取同步状态失败：${error.message}`);
    }
  }, 900);
}

async function openDetail(platform, id) {
  const { data } = await api(`/api/markets/${encodeURIComponent(platform)}/${encodeURIComponent(id)}`);
  const analysis = data.analysis;
  const market = analysis.market;
  const history = data.history || [];
  const historyRows = history.length ? `<div class="history-list"><div class="history-row"><span>采集时间</span><span>YES 概率</span><span>成交量</span></div>${history.map((point) => `<div class="history-row"><span>${fmtDate(point.captured_at)}</span><span>${fmtPct(point.probability)}</span><span>${fmtNumber(point.volume)}</span></div>`).join("")}</div>` : '<p class="intro-copy">暂无快照历史，下一次同步后开始记录比较数据。</p>';
  const evidence = analysis.evidence.length ? `<ul class="evidence-list">${analysis.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : '<p class="intro-copy">当前没有触发额外信号。</p>';
  $("#drawer-content").innerHTML = `<h2 class="detail-title">${escapeHtml(market.title)}</h2><div class="detail-meta"><span class="platform-badge ${platform === "kalshi" ? "kalshi" : ""}"><i></i>${platform === "kalshi" ? "Kalshi" : "Polymarket"}</span><span class="market-id">${escapeHtml(market.market_id)}</span></div><div class="detail-stat-grid"><div class="detail-stat"><label>YES 概率</label><strong>${fmtPct(market.probability)}</strong></div><div class="detail-stat"><label>概率变化</label><strong>${analysis.probability_change == null ? "—" : `${analysis.probability_change > 0 ? "+" : ""}${(analysis.probability_change * 100).toFixed(1)} pp`}</strong></div><div class="detail-stat"><label>报告成交量</label><strong>${fmtNumber(market.volume)}</strong></div><div class="detail-stat"><label>流动性</label><strong>${fmtNumber(market.liquidity)}</strong></div></div><h3 class="detail-section-title">规则证据</h3>${evidence}<h3 class="detail-section-title">快照历史</h3>${historyRows}${market.url ? `<a class="external-link" href="${escapeHtml(market.url)}" target="_blank" rel="noreferrer">在 ${platform === "kalshi" ? "Kalshi" : "Polymarket"} 查看市场 ↗</a>` : ""}`;
  $("#detail-drawer").classList.add("open");
  $("#detail-drawer").setAttribute("aria-hidden", "false");
  $("#drawer-backdrop").classList.add("open");
}

function closeDetail() { $("#detail-drawer").classList.remove("open"); $("#detail-drawer").setAttribute("aria-hidden", "true"); $("#drawer-backdrop").classList.remove("open"); }
let toastTimer;
function showToast(message) { const toast = $("#toast"); toast.textContent = message; toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("show"), 3200); }

let searchTimer;
$("#search").addEventListener("input", (event) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.q = event.target.value; state.page = 1; loadMarkets().catch((error) => showToast(error.message)); }, 180); });
$("#platform").addEventListener("change", (event) => { state.platform = event.target.value; state.page = 1; loadMarkets().catch((error) => showToast(error.message)); });
$("#sort").addEventListener("change", (event) => { state.sort = event.target.value; state.page = 1; loadMarkets().catch((error) => showToast(error.message)); });
document.querySelectorAll("[data-signal]").forEach((button) => button.addEventListener("click", () => { document.querySelector(".segment.active").classList.remove("active"); button.classList.add("active"); state.signal = button.dataset.signal; state.page = 1; loadMarkets().catch((error) => showToast(error.message)); }));
$("#prev-page").addEventListener("click", () => { state.page -= 1; renderMarkets(); });
$("#next-page").addEventListener("click", () => { state.page += 1; renderMarkets(); });
$("#refresh-button").addEventListener("click", refreshMarkets);
$("#close-drawer").addEventListener("click", closeDetail);
$("#drawer-backdrop").addEventListener("click", closeDetail);
document.addEventListener("keydown", (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("#search").focus(); } if (event.key === "Escape") closeDetail(); });
Promise.all([loadMarkets(), loadHealth()]).catch((error) => showToast(`连接后端失败：${error.message}`));
