let games = [];
let uniqueGames = [];
let selectedId = null;
let reviewGame = null;
let reviewErrors = [];
let currentErrorIndex = 0;
let pendingErrorId = null;
let marksCache = [];
let profileCache = {};
let embeddedOfficialRunning = false;
let embeddedOfficialBody = null;
let reviewWebviewReady = false;
let reviewWebviewTarget = "";
let learningNoteEditingErrorId = null;
let learningNoteDirty = false;

const OFFICIAL_URL = "https://mjai.ekyu.moe/zh-cn.html";
const THEME_STORAGE_KEY = "mortalcoach.theme";
const UPDATE_DISMISS_KEY = "mortalcoach.dismissedUpdateTag";
const RELEASES_API_URL = "https://api.github.com/repos/NingYiwu94/MortalCoach/releases/latest";
const $ = (id) => document.getElementById(id);

function getAppTheme() {
  return localStorage.getItem(THEME_STORAGE_KEY) === "light" ? "light" : "dark";
}

function applyAppTheme(theme = getAppTheme()) {
  const normalized = theme === "light" ? "light" : "dark";
  localStorage.setItem(THEME_STORAGE_KEY, normalized);
  document.documentElement.classList.toggle("theme-light", normalized === "light");
  document.documentElement.classList.toggle("theme-dark", normalized === "dark");
  document.body.classList.toggle("theme-light", normalized === "light");
  document.body.classList.toggle("theme-dark", normalized === "dark");
  if ($("themeInput")) $("themeInput").value = normalized;
  syncReviewTheme();
}

function buildKillerReviewUrl(gameId) {
  const theme = getAppTheme();
  return `/killer/?data=/api/games/${gameId}/killer-data&showMortal=1&embed=1&theme=${theme}`;
}

function syncReviewTheme() {
  const frame = $("reviewWebview");
  if (!frame) return;
  const theme = getAppTheme();
  try {
    frame.contentWindow?.MM?.setMortalCoachTheme?.(theme);
    frame.contentWindow?.setMortalCoachTheme?.(theme);
    frame.contentWindow?.postMessage?.({ type: "mortalcoach-theme", theme }, "*");
  } catch (error) {
    // Cross-window theme sync is best-effort; URL parameter still applies on reload.
  }
}

function parseVersionParts(version) {
  return String(version || "")
    .trim()
    .replace(/^v/i, "")
    .split(/[.-]/)
    .map((part) => {
      const value = Number.parseInt(part, 10);
      return Number.isFinite(value) ? value : 0;
    });
}

function compareVersions(left, right) {
  const a = parseVersionParts(left);
  const b = parseVersionParts(right);
  const length = Math.max(a.length, b.length, 3);
  for (let i = 0; i < length; i += 1) {
    const delta = (a[i] || 0) - (b[i] || 0);
    if (delta !== 0) return delta;
  }
  return 0;
}

function getReleaseDownloadUrl(release) {
  const assets = Array.isArray(release?.assets) ? release.assets : [];
  const installer = assets.find((asset) => /MortalCoach-Setup-.*\.exe$/i.test(asset.name || ""));
  return installer?.browser_download_url || release?.html_url || "https://github.com/NingYiwu94/MortalCoach/releases/latest";
}

function hideUpdateNotice() {
  $("updateNotice")?.classList.add("hidden");
}

function showUpdateNotice({ currentVersion, latestVersion, downloadUrl, releaseUrl }) {
  const notice = $("updateNotice");
  if (!notice) return;
  $("updateNoticeText").textContent = `当前 ${currentVersion}，最新 ${latestVersion}。`;
  notice.dataset.downloadUrl = downloadUrl || releaseUrl || "";
  notice.dataset.releaseTag = latestVersion || "";
  notice.classList.remove("hidden");
}

async function openUpdateDownload() {
  const notice = $("updateNotice");
  const url = notice?.dataset.downloadUrl;
  if (!url) return;
  if (window.mortalCoachElectron?.openExternal) {
    await window.mortalCoachElectron.openExternal(url);
  } else {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

function dismissUpdateNotice() {
  const tag = $("updateNotice")?.dataset.releaseTag;
  if (tag) localStorage.setItem(UPDATE_DISMISS_KEY, tag);
  hideUpdateNotice();
}

async function checkForUpdates() {
  if (!window.mortalCoachElectron?.getVersion) return;
  const currentVersion = await window.mortalCoachElectron.getVersion();
  const release = await fetch(RELEASES_API_URL, { cache: "no-store" }).then((res) => {
    if (!res.ok) throw new Error(`GitHub Release check failed: ${res.status}`);
    return res.json();
  });
  if (release?.draft || release?.prerelease || !release?.tag_name) return;
  const latestVersion = String(release.tag_name).replace(/^v/i, "");
  if (compareVersions(latestVersion, currentVersion) <= 0) return;
  if (localStorage.getItem(UPDATE_DISMISS_KEY) === latestVersion) return;
  showUpdateNotice({
    currentVersion,
    latestVersion,
    downloadUrl: getReleaseDownloadUrl(release),
    releaseUrl: release.html_url,
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function fmt(num, digits = 1) {
  const value = Number(num || 0);
  return Number.isFinite(value) ? value.toFixed(digits) : "--";
}

function pct(num, digits = 1) {
  const value = Number(num);
  return Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "--";
}

const MAJSOUL_RANK_DELTA_4 = [15, 5, -5, -15];
const MAJSOUL_MODE_DELTA_4 = {
  16: [120, 60, 0, 0],
  15: [60, 30, 0, 0],
  12: [110, 55, 0, 0],
  11: [55, 30, 0, 0],
  9: [80, 40, 0, 0],
  8: [40, 20, 0, 0],
};

function stableLevelLabel(rank, mode) {
  const rates = Array.isArray(rank?.rank_rates) ? rank.rank_rates : [];
  const scores = Array.isArray(rank?.rank_avg_score) ? rank.rank_avg_score : [];
  const deltas = MAJSOUL_MODE_DELTA_4[Number(mode)];
  if (!deltas || rates.length < 4 || scores.length < 4 || !Number(rates[3])) return "";
  const expected = scores.slice(0, 4).reduce((sum, score, idx) => {
    const point = Math.ceil((Number(score) - 25000) / 1000 + MAJSOUL_RANK_DELTA_4[idx]) + deltas[idx];
    return sum + point * Number(rates[idx] || 0);
  }, 0);
  const stable = expected / (Number(rates[3]) * 15) - 10;
  if (!Number.isFinite(stable)) return "";
  return stable >= 4 ? `圣${(stable - 3).toFixed(2)}` : `豪${stable.toFixed(2)}`;
}

function polarPoint(cx, cy, radius, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(rad),
    y: cy + radius * Math.sin(rad),
  };
}

function pieSlicePath(cx, cy, radius, startAngle, endAngle) {
  const start = polarPoint(cx, cy, radius, startAngle);
  const end = polarPoint(cx, cy, radius, endAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)} Z`;
}

function renderRankPieSvg(rates, labels, colors) {
  const total = rates.reduce((sum, item) => sum + Math.max(0, Number(item || 0)), 0) || 1;
  const cx = 180;
  const cy = 112;
  const radius = 72;
  let angle = -90;
  const slices = [];
  const callouts = [];
  rates.forEach((rawRate, idx) => {
    const rate = Math.max(0, Number(rawRate || 0));
    if (!rate) return;
    const sweep = (rate / total) * 360;
    const start = angle;
    const end = angle + sweep;
    const mid = start + sweep / 2;
    const inner = polarPoint(cx, cy, 43, mid);
    const edge = polarPoint(cx, cy, radius + 2, mid);
    const elbow = polarPoint(cx, cy, radius + 22, mid);
    const rightSide = Math.cos((mid * Math.PI) / 180) >= 0;
    const labelX = rightSide ? 272 : 88;
    const lineEndX = rightSide ? labelX - 14 : labelX + 14;
    const anchor = rightSide ? "start" : "end";
    const percent = `${(rate * 100).toFixed(2)}%`;
    slices.push(`
      <path d="${pieSlicePath(cx, cy, radius, start, end)}" fill="${colors[idx]}"></path>
      <text class="rank-pie-inner-label" x="${inner.x.toFixed(2)}" y="${inner.y.toFixed(2)}">${percent}</text>
    `);
    callouts.push(`
      <path class="rank-pie-line" d="M ${edge.x.toFixed(2)} ${edge.y.toFixed(2)} L ${elbow.x.toFixed(2)} ${elbow.y.toFixed(2)} L ${lineEndX.toFixed(2)} ${elbow.y.toFixed(2)}" stroke="${colors[idx]}"></path>
      <text class="rank-pie-outer-label" x="${labelX}" y="${(elbow.y + 4).toFixed(2)}" text-anchor="${anchor}" fill="${colors[idx]}">${labels[idx]} ${percent}</text>
    `);
    angle = end;
  });
  return `
    <svg class="rank-pie-svg" viewBox="0 0 360 224" role="img" aria-label="排名饼图">
      <g>${slices.join("")}</g>
      <g>${callouts.join("")}</g>
    </svg>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function actionText(action) {
  if (!action) return "";
  if (typeof action === "string") return action;
  if (action.type === "text") return action.text || "";
  if (action.type === "dahai") return `打 ${action.pai}`;
  if (action.type === "reach") return "立直";
  if (action.type === "hora") return "和牌";
  if (action.type === "none") return "跳过";
  return action.type || "";
}

function normalizeLearningStatus(status) {
  return status === "mastered" ? "mastered" : "new";
}

function gamePlatformKey(game) {
  const text = `${game.platform || ""} ${game.source || ""} ${game.original_url || ""} ${game.result_url || ""}`.toLowerCase();
  if (text.includes("tenhou.net") || text.includes("tenhou") || text.includes("天凤") || text.includes("天鳳")) return "tenhou";
  if (text.includes("maj-soul") || text.includes("mahjongsoul") || text.includes("majsoul") || text.includes("雀魂")) return "majsoul";
  return "majsoul";
}

function gameKey(game) {
  return `${game.original_url || game.source || game.id}::${game.model_tag || ""}`;
}

function uniqueByPaipu(items) {
  const map = new Map();
  for (const game of items) {
    const key = gameKey(game);
    const prev = map.get(key);
    if (!prev || String(game.created_at) > String(prev.created_at)) map.set(key, game);
  }
  return [...map.values()].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

async function loadGames() {
  games = await api("/api/games");
  uniqueGames = uniqueByPaipu(games);
  $("countLabel").textContent = `${uniqueGames.length} 份`;
  $("libraryCount").textContent = `${uniqueGames.length} 份`;
  $("totalGames").textContent = String(uniqueGames.length);
  renderLibrary();
  updateTrendVisibility();
}

async function loadMarks() {
  marksCache = await api("/api/marks");
  $("marksCount").textContent = `${marksCache.length} 条`;
  $("markedTotal").textContent = String(marksCache.length);
  renderMarks();
}

async function loadProfile() {
  profileCache = await api("/api/profile");
  if ($("profileMajsoulInput")) $("profileMajsoulInput").value = profileCache.majsoul_id || "";
  if ($("profileTenhouInput")) $("profileTenhouInput").value = profileCache.tenhou_id || "";
  renderMajsoulStats(profileCache.majsoul_stats, profileCache.majsoul_stats_updated_at);
}

async function saveProfile() {
  profileCache = await api("/api/profile", {
    method: "POST",
    body: JSON.stringify({
      display_name: profileCache.display_name || "",
      majsoul_id: $("profileMajsoulInput").value,
      tenhou_id: $("profileTenhouInput").value,
      goals: profileCache.goals || "",
    }),
  });
  $("profileSaveStatus").textContent = "已保存训练档案";
  renderMajsoulStats(profileCache.majsoul_stats, profileCache.majsoul_stats_updated_at);
}

async function syncMajsoulStats() {
  $("profileSaveStatus").textContent = "正在同步雀魂公开统计...";
  profileCache = await api("/api/profile/majsoul-sync", {
    method: "POST",
    body: JSON.stringify({ majsoul_id: $("profileMajsoulInput").value }),
  });
  $("profileMajsoulInput").value = profileCache.majsoul_id || "";
  $("profileSaveStatus").textContent = "已同步雀魂公开统计";
  renderMajsoulStats(profileCache.majsoul_stats, profileCache.majsoul_stats_updated_at);
}

function renderMajsoulStats(stats, updatedAt = "") {
  const box = $("majsoulStatsBox");
  if (!box) return;
  if (!stats) {
    box.innerHTML = `<div class="empty-mini">填写雀魂昵称后，可以同步雀魂牌谱屋公开统计。MortalCoach 会先展示样本最多的一个段位场，避免首页信息过载。</div>`;
    return;
  }
  const player = stats.player || {};
  const modes = (Array.isArray(stats.modes) && stats.modes.length
    ? stats.modes
    : [{
        label: stats.mode_label || "四麻段位",
        room: "段位场",
        wind: "",
        rank: stats.rank || {},
        extended: stats.extended || {},
      }])
    .filter((mode) => Number(mode.extended?.count ?? mode.rank?.count ?? 0) > 0);
  if (!modes.length) {
    box.innerHTML = `
      <div class="majsoul-stats-head">
        <div>
          <strong>${escapeHtml(player.nickname || "已同步账号")}</strong>
          <span>${escapeHtml(stats.level_text || "")}</span>
        </div>
        <span>${updatedAt ? `同步于 ${escapeHtml(updatedAt)}` : "已同步"}</span>
      </div>
      <div class="empty-mini">当前没有可展示的公开段位场样本。</div>
    `;
    return;
  }
  const mainMode = modes
    .slice()
    .sort((a, b) => Number(b.extended?.count ?? b.rank?.count ?? 0) - Number(a.extended?.count ?? a.rank?.count ?? 0))[0];
  const rank = mainMode.rank || {};
  const ext = mainMode.extended || {};
  const rankRates = rank.rank_rates || [];
  const recordCount = Number(mainMode.record_count ?? rank.count ?? ext.record_count ?? ext.count ?? 0);
  const stableLabel = mainMode.stable_level?.label || rank.stable_level?.label || stableLevelLabel(rank, mainMode.mode || stats.mode);
  const pieRates = [0, 1, 2, 3].map((idx) => Math.max(0, Number(rankRates[idx] || 0)));
  const pieColors = ["#28a745", "#17a2b8", "#6c757d", "#dc3545"];
  const statItems = [
    ["记录场数", recordCount || "--"],
    ["平均顺位", fmt(rank.avg_rank, 3)],
    ["安定段位", stableLabel || "--"],
    ["和牌率", pct(ext["和牌率"], 2)],
    ["放铳率", pct(ext["放铳率"], 2)],
    ["默听率", pct(ext["默听率"], 2)],
    ["副露率", pct(ext["副露率"], 2)],
    ["立直率", pct(ext["立直率"], 2)],
    ["自摸率", pct(ext["自摸率"], 2)],
    ["流局率", pct(ext["流局率"], 2)],
    ["流听率", pct(ext["流听率"], 2)],
    ["被飞率", pct(rank.negative_rate, 2)],
    ["平均打点", ext["平均打点"] ?? "--"],
    ["平均铳点", ext["平均铳点"] ?? "--"],
    ["和了巡数", fmt(ext["和了巡数"], 3)],
  ];
  const rankLabels = ["一位", "二位", "三位", "四位"];
  box.innerHTML = `
    <div class="majsoul-stats-head">
      <div>
        <strong>${escapeHtml(player.nickname || "")}</strong>
        <span>${escapeHtml(stats.level_text || "")} · 当前主要场次：${escapeHtml(mainMode.label || "")}</span>
      </div>
      <span>${updatedAt ? `同步于 ${escapeHtml(updatedAt)}` : "已同步"}</span>
    </div>
    <div class="majsoul-focus-card">
      <div class="majsoul-mode-title">
        <strong class="majsoul-mode-badge">${escapeHtml(mainMode.label || "")}</strong>
        <span>${escapeHtml(mainMode.room || "")}${mainMode.wind ? ` · ${escapeHtml(mainMode.wind)}` : ""}</span>
      </div>
      <div class="majsoul-focus-layout">
        <div class="majsoul-stat-grid compact">
          ${statItems.map(([label, value]) => `<div><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
        </div>
        <div class="rank-pie-card" aria-label="累计战绩排名分布">
          ${renderRankPieSvg(pieRates, rankLabels, pieColors)}
        </div>
      </div>
      <p class="majsoul-source-note">数据来自雀魂牌谱屋公开牌谱。记录场数按该段位场真实牌谱数统计，攻守指标沿用牌谱屋公开统计口径。</p>
    </div>
  `;
}

function showView(viewId) {
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  $(viewId).classList.remove("hidden");
  document.body.classList.toggle("review-mode", viewId === "reviewView");
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === viewId);
  });
  if (viewId === "mistakesView") loadMarks().catch((err) => alert(err.message));
  if (viewId === "reviewView") {
    requestAnimationFrame(() => {
      sizeReviewWebview();
      syncOfficialError().catch(() => {});
    });
  }
}

function showProfileTab(tab) {
  const normalized = tab === "tenhou" ? "tenhou" : "majsoul";
  document.querySelectorAll(".profile-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.profileTab === normalized);
  });
  $("majsoulProfilePane")?.classList.toggle("hidden", normalized !== "majsoul");
  $("tenhouProfilePane")?.classList.toggle("hidden", normalized !== "tenhou");
  updateTrendVisibility();
}

function getActiveProfileTab() {
  return document.querySelector(".profile-tab.active")?.dataset.profileTab || "majsoul";
}

function updateTrendVisibility() {
  const isMajsoul = getActiveProfileTab() === "majsoul";
  $("trendPanel")?.classList.toggle("hidden", !isMajsoul);
  if (isMajsoul) {
    drawTrend();
  } else {
    if ($("countLabel")) $("countLabel").textContent = "";
    if ($("avgRating")) $("avgRating").textContent = "--";
    if ($("totalGames")) $("totalGames").textContent = "0";
    if ($("markedTotal")) $("markedTotal").textContent = "0";
  }
}

function renderLibrary() {
  const box = $("libraryList");
  box.innerHTML = "";
  const query = ($("librarySearchInput")?.value || "").trim().toLowerCase();
  const sort = $("librarySortInput")?.value || "created_desc";
  const platform = $("libraryPlatformInput")?.value || "majsoul";
  let items = [...uniqueGames];
  if (query) {
    items = items.filter((game) => `${game.title || ""} ${game.source || ""} ${game.original_url || ""} ${game.tags || ""}`.toLowerCase().includes(query));
  }
  if (platform) {
    items = items.filter((game) => gamePlatformKey(game) === platform);
  }
  const sorters = {
    created_desc: (a, b) => String(b.created_at).localeCompare(String(a.created_at)),
    rating_desc: (a, b) => Number(b.rating_percent || 0) - Number(a.rating_percent || 0),
    errors_desc: (a, b) => Number(b.error_count || 0) - Number(a.error_count || 0),
    max_gap_desc: (a, b) => Number(b.max_q_gap || 0) - Number(a.max_q_gap || 0),
  };
  items.sort(sorters[sort] || sorters.created_desc);
  if (!uniqueGames.length) {
    box.innerHTML = `<div class="empty-state">还没有分析过的牌谱。回到总览页粘贴牌谱链接开始第一份复盘。</div>`;
    return;
  }
  if (!items.length) {
    box.innerHTML = `<div class="empty-state">没有匹配的牌谱。</div>`;
    return;
  }
  for (const game of items) {
    const card = document.createElement("article");
    card.className = "library-card";
    card.innerHTML = `
      <div>
        <button class="library-card-title title-edit-trigger" type="button" title="点击重命名牌谱">${escapeHtml(game.title)}</button>
        <div class="library-card-meta">
          ${escapeHtml(game.created_at)} · ${escapeHtml(game.model_tag || "Mortal")}
          · 一致率 ${fmt(game.match_rate * 100)}% · 已提取错误 ${game.error_count}
        </div>
      </div>
      <div class="library-card-score">${fmt(game.rating_percent)}</div>
      <div class="library-actions">
        <button class="small-btn review-btn" type="button">复盘</button>
        <button class="small-btn delete-btn" type="button">删除</button>
      </div>
    `;
    card.querySelector(".title-edit-trigger").onclick = (event) => {
      event.stopPropagation();
      startInlineRename(event.currentTarget, game);
    };
    card.querySelector(".review-btn").onclick = (event) => {
      event.stopPropagation();
      openGameReview(game.id, 9999);
    };
    card.querySelector(".delete-btn").onclick = (event) => {
      event.stopPropagation();
      deleteGame(game).catch((err) => alert(err.message));
    };
    box.appendChild(card);
  }
}

function startInlineRename(titleButton, game) {
  const input = document.createElement("input");
  input.className = "library-title-input";
  input.value = game.title || "";
  input.setAttribute("aria-label", "牌谱名称");
  titleButton.replaceWith(input);
  input.focus();
  input.select();

  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const title = input.value.trim();
    if (!save || title === (game.title || "")) {
      renderLibrary();
      return;
    }
    if (!title) {
      alert("牌谱名称不能为空。");
      renderLibrary();
      return;
    }
    input.disabled = true;
    try {
      await renameGame(game, title);
    } catch (err) {
      alert(err.message);
      renderLibrary();
    }
  };

  input.onkeydown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      finish(true);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
    }
  };
  input.onblur = () => finish(true);
}

async function renameGame(game, title) {
  if (!title) {
    alert("牌谱名称不能为空。");
    return;
  }
  const related = games.filter((item) => gameKey(item) === gameKey(game));
  const ids = related.length ? related.map((item) => item.id) : [game.id];
  for (const id of ids) {
    await api(`/api/games/${id}/title`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  }
  if (reviewGame && ids.some((id) => Number(id) === Number(reviewGame.id))) {
    reviewGame.title = title;
    $("reviewTitle").textContent = title;
  }
  await loadGames();
}

async function deleteGame(game) {
  const related = games.filter((item) => gameKey(item) === gameKey(game));
  const deleteCount = Math.max(related.length, 1);
  const confirmed = confirm(`确定删除这份牌谱吗？\n\n${game.title || "未命名牌谱"}\n\n将删除 ${deleteCount} 条同谱记录，关联的错误、错题收藏和复盘笔记也会一起删除。`);
  if (!confirmed) return;
  const ids = related.length ? related.map((item) => item.id) : [game.id];
  for (const id of ids) {
    const result = await api(`/api/games/${id}`, { method: "DELETE" });
    if (!result.ok) throw new Error(`删除失败：牌谱记录 ${id} 不存在或已经被删除。`);
  }
  if (reviewGame && Number(reviewGame.id) === Number(game.id)) {
    reviewGame = null;
    reviewErrors = [];
    reviewWebviewReady = false;
    reviewWebviewTarget = "";
    showView("libraryView");
  }
  await Promise.all([loadGames(), loadMarks()]);
}

async function openGameReview(gameId, limit = 9999, errorId = null) {
  selectedId = gameId;
  currentErrorIndex = 0;
  pendingErrorId = errorId;
  $("reviewLimitInput").value = String(limit);
  showView("reviewView");
  await loadReviewData(gameId, limit);
}

async function loadReviewData(gameId, limit) {
  preserveLearningDraft();
  const data = await api(`/api/games/${gameId}/review-data?limit=${limit}&order=chronological`);
  reviewGame = data.game;
  reviewErrors = data.errors || [];
  if (pendingErrorId) {
    const targetIndex = reviewErrors.findIndex((err) => Number(err.error_id) === Number(pendingErrorId));
    if (targetIndex >= 0) currentErrorIndex = targetIndex;
    pendingErrorId = null;
  }
  currentErrorIndex = Math.min(currentErrorIndex, Math.max(0, reviewErrors.length - 1));
  $("reviewTitle").textContent = reviewGame.title;
  $("reviewMeta").textContent = `rating ${fmt(reviewGame.rating_percent)} · ${reviewGame.model_tag || "Mortal"} · 一致率 ${fmt(reviewGame.match_rate * 100)}% · ${reviewGame.created_at}`;
  renderReviewErrors();
  updateBoard(reviewErrors[currentErrorIndex] || null);
  renderInspector(reviewErrors[currentErrorIndex] || null);
  if (reviewGame.raw_json?.has_killer_data) {
    showKillerReviewBoard();
  } else {
    showLocalReviewBoard();
  }
}

function showKillerReviewBoard() {
  const officialPanel = document.querySelector(".official-review-panel");
  const localGrid = document.querySelector(".review-grid");
  const webview = $("reviewWebview");
  const fallback = $("reviewBrowserFallback");
  const target = buildKillerReviewUrl(reviewGame.id);
  if (localGrid) localGrid.style.display = "none";
  if (officialPanel) officialPanel.classList.remove("hidden");
  if (fallback) fallback.classList.add("hidden");
  if (!webview) {
    if (fallback) {
      fallback.classList.remove("hidden");
      fallback.textContent = "当前环境不支持内嵌棋盘复盘窗口。";
    }
    return;
  }
  sizeReviewWebview();
  webview.classList.remove("hidden");
  if (reviewWebviewTarget !== target) {
    reviewWebviewReady = false;
    reviewWebviewTarget = target;
    webview.src = target;
  } else {
    reviewWebviewReady = true;
    syncOfficialError().catch(() => {});
  }
}

function sizeReviewWebview() {
  const panel = document.querySelector(".official-review-panel");
  const webview = $("reviewWebview");
  if (!panel || !webview || panel.classList.contains("hidden")) return;
  const top = panel.getBoundingClientRect().top;
  const height = Math.max(560, window.innerHeight - top - 14);
  panel.style.height = `${height}px`;
  panel.style.minHeight = "0";
  panel.style.overflow = "hidden";
  webview.style.position = "absolute";
  webview.style.left = "0";
  webview.style.top = "0";
  webview.style.right = "0";
  webview.style.bottom = "0";
  webview.style.width = "100%";
  webview.style.height = "100%";
  webview.style.minHeight = "0";
  webview.style.display = "block";
}

function showLocalReviewBoard() {
  const officialPanel = document.querySelector(".official-review-panel");
  const localGrid = document.querySelector(".review-grid");
  const webview = $("reviewWebview");
  reviewWebviewReady = false;
  reviewWebviewTarget = "";
  if (webview) webview.src = "about:blank";
  if (officialPanel) officialPanel.classList.add("hidden");
  if (localGrid) localGrid.style.display = "block";
}

function renderReviewErrors() {
  const jump = $("errorJumpInput");
  jump.innerHTML = "";
  if (!reviewErrors.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "暂无可复盘错误";
    jump.appendChild(option);
    $("markCurrentBtn").disabled = true;
    $("markCurrentBtn").textContent = "加入错题库";
    updateBoard(null);
    return;
  }
  reviewErrors.forEach((err, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `#${index + 1} ${err.round} ${err.junme ?? "?"}巡 Q差 ${fmt(err.q_gap, 3)}`;
    jump.appendChild(option);
  });
  jump.value = String(currentErrorIndex);
  syncMarkButton();
}

function setCurrentError(index) {
  if (!reviewErrors.length) return;
  preserveLearningDraft();
  currentErrorIndex = Math.max(0, Math.min(reviewErrors.length - 1, index));
  renderReviewErrors();
  updateBoard(reviewErrors[currentErrorIndex]);
  renderInspector(reviewErrors[currentErrorIndex]);
  syncOfficialError();
}

function updateCurrentErrorFromEmbedded(index) {
  if (!reviewErrors.length) return;
  const nextIndex = Math.max(0, Math.min(reviewErrors.length - 1, Number(index)));
  if (nextIndex === currentErrorIndex) return;
  preserveLearningDraft();
  currentErrorIndex = nextIndex;
  renderReviewErrors();
  updateBoard(reviewErrors[currentErrorIndex]);
  renderInspector(reviewErrors[currentErrorIndex]);
}

function handleEmbeddedReviewPosition(data) {
  if (!reviewGame || !reviewErrors.length || !data?.has_mortal_eval) return;
  const kyokuIndex = Number(data.kyoku_index ?? data.hand);
  const entryIndex = Number(data.entry_index);
  if (!Number.isInteger(kyokuIndex) || !Number.isInteger(entryIndex)) return;
  const index = reviewErrors.findIndex((err) => (
    Number(err.kyoku_index ?? 0) === kyokuIndex &&
    Number(err.entry_index ?? -1) === entryIndex
  ));
  if (index >= 0) updateCurrentErrorFromEmbedded(index);
}

function jumpRound(delta) {
  if (!reviewErrors.length) return;
  const current = reviewErrors[currentErrorIndex]?.round;
  let index = currentErrorIndex;
  while (index + delta >= 0 && index + delta < reviewErrors.length) {
    index += delta;
    if (reviewErrors[index].round !== current) {
      setCurrentError(index);
      return;
    }
  }
  setCurrentError(index);
}

function handleBoardNav(action) {
  if (action === "prevError" || action === "prevTurn" || action === "back") setCurrentError(currentErrorIndex - 1);
  if (action === "nextError" || action === "nextTurn" || action === "forward") setCurrentError(currentErrorIndex + 1);
  if (action === "prevRound") jumpRound(-1);
  if (action === "nextRound") jumpRound(1);
}

function updateBoard(err) {
  $("boardHand").innerHTML = "";
  $("candidateRows").innerHTML = "";
  if (!err) {
    $("boardRound").textContent = "--";
    $("boardGap").textContent = "Q差 --";
    $("boardRemain").textContent = "剩余 --";
    $("playerChoice").textContent = "--";
    $("mortalChoice").textContent = "--";
    $("boardErrorTitle").textContent = "选择一个错误开始复盘";
    $("boardErrorDesc").textContent = "这里会根据官方分析结果重建每一手的手牌、实际选择、Mortal 推荐和候选 Q/P。";
    return;
  }

  const state = err.state || {};
  const handTiles = state.hand_tiles?.length ? state.hand_tiles : fallbackTiles(err);
  for (const tile of handTiles) {
    const tileEl = createTileElement(tile);
    if (state.tsumo_tiles?.includes(tile)) tileEl.classList.add("tsumo-tile");
    $("boardHand").appendChild(tileEl);
  }

  $("boardRound").textContent = `${err.round} · ${err.junme ?? "?"} 巡`;
  $("boardGap").textContent = `Q差 ${fmt(err.q_gap, 3)}`;
  $("boardRemain").textContent = `剩余 ${err.tiles_left ?? "--"}`;
  renderChoice("playerChoice", actionText(err.actual));
  renderChoice("mortalChoice", actionText(err.expected));
  $("boardErrorTitle").textContent = `#${currentErrorIndex + 1} ${err.round} 第 ${err.junme ?? "?"} 巡`;
  $("boardErrorDesc").textContent = `你的选择是「${actionText(err.actual)}」，Mortal 推荐「${actionText(err.expected)}」。候选表已显示每个操作的 Q 值与 P 概率。`;

  const candidates = err.candidates || [err.best_detail, err.actual_detail].filter(Boolean);
  candidates.slice(0, 12).forEach((item, index) => {
    const row = document.createElement("tr");
    row.className = index === 0 ? "best-row" : "";
    if (index + 1 === Number(err.actual_rank)) row.classList.add("actual-row");
    row.appendChild(renderActionCell(item.action || `候选 ${index + 1}`));
    const qCell = document.createElement("td");
    qCell.textContent = fmt(item.q_value, 3);
    const pCell = document.createElement("td");
    pCell.textContent = fmt(item.prob, 2);
    row.appendChild(qCell);
    row.appendChild(pCell);
    $("candidateRows").appendChild(row);
  });
}

function renderActionCell(action) {
  const cell = document.createElement("td");
  cell.className = "candidate-action";
  const text = String(action || "");
  const tileMatch = text.match(/[1-9][万筒索]|东|南|西|北|白|发|中/);
  const label = document.createElement("span");
  label.textContent = tileMatch ? text.replace(tileMatch[0], "").trim() || "打" : text;
  cell.appendChild(label);
  if (tileMatch) cell.appendChild(createTileElement(tileMatch[0]));
  return cell;
}

function renderChoice(id, text) {
  const box = $(id);
  box.innerHTML = "";
  const action = String(text || "--");
  const tileMatch = action.match(/[1-9][万筒索]|东|南|西|北|白|发|中/);
  const label = document.createElement("span");
  label.className = "choice-action";
  label.textContent = tileMatch ? action.replace(tileMatch[0], "").trim() || "打" : action;
  box.appendChild(label);
  if (tileMatch) box.appendChild(createTileElement(tileMatch[0]));
}

function syncMarkButton() {
  const btn = $("markCurrentBtn");
  const err = reviewErrors[currentErrorIndex];
  if (!btn) return;
  btn.disabled = !err?.error_id;
  btn.classList.toggle("marked", Boolean(err?.marked));
  btn.textContent = err?.marked ? "移出错题库" : "加入错题库";
}

function showLearningSavedFeedback() {
  const btn = $("saveLearningBtn");
  const noteInput = $("learningNoteInput");
  const status = $("learningSaveStatus");
  if (status) status.textContent = "备注已修改";
  if (noteInput) {
    noteInput.classList.remove("note-saved-flash");
    void noteInput.offsetWidth;
    noteInput.classList.add("note-saved-flash");
  }
  if (!btn) return;
  btn.classList.remove("save-feedback");
  void btn.offsetWidth;
  btn.classList.add("save-feedback");
  btn.textContent = "已修改";
  window.setTimeout(() => {
    btn.classList.remove("save-feedback");
    btn.textContent = "修改备注";
  }, 1200);
}

function renderInspector(err) {
  if (!$("inspectorRank")) return;
  const noteInput = $("learningNoteInput");
  if (!err) {
    $("inspectorRank").textContent = "--";
    $("inspectorTitle").textContent = "选择一个错误开始复盘";
    $("inspectorMeta").textContent = "Top5 / Top10 只是复盘范围，棋盘仍然是主视角。";
    $("inspectorQGap").textContent = "--";
    $("inspectorActualRank").textContent = "--";
    $("inspectorReviewCount").textContent = "0";
    $("inspectorActual").textContent = "--";
    $("inspectorExpected").textContent = "--";
    $("learningStatusInput").value = "new";
    if (noteInput) noteInput.value = "";
    learningNoteEditingErrorId = null;
    learningNoteDirty = false;
    $("learningSaveStatus").textContent = "";
    return;
  }
  const errorId = Number(err.error_id || 0);
  const shouldKeepDraft = (
    noteInput &&
    learningNoteDirty &&
    learningNoteEditingErrorId === errorId &&
    document.activeElement === noteInput
  );
  $("inspectorRank").textContent = `#${currentErrorIndex + 1}`;
  $("inspectorTitle").textContent = `${err.round} · ${err.junme ?? "?"} 巡`;
  $("inspectorMeta").textContent = `剩余 ${err.tiles_left ?? "--"} · ${err.marked ? "已加入错题库" : "未收藏"}`;
  $("inspectorQGap").textContent = fmt(err.q_gap, 3);
  $("inspectorActualRank").textContent = String(err.actual_rank ?? "--");
  $("inspectorReviewCount").textContent = String(err.review_count ?? 0);
  $("inspectorActual").textContent = actionText(err.actual) || "--";
  $("inspectorExpected").textContent = actionText(err.expected) || "--";
  $("learningStatusInput").value = normalizeLearningStatus(err.learning_status);
  if (noteInput && !shouldKeepDraft) {
    noteInput.value = err.user_note || "";
    learningNoteEditingErrorId = errorId;
    learningNoteDirty = false;
  }
  if (!learningNoteDirty) {
    $("learningSaveStatus").textContent = err.last_reviewed_at ? `上次复盘：${err.last_reviewed_at}` : "";
  }
}

async function saveCurrentLearning(extra = {}) {
  const err = reviewErrors[currentErrorIndex];
  if (!err?.error_id) return;
  const noteInput = $("learningNoteInput");
  const updated = await api(`/api/errors/${err.error_id}/learning`, {
    method: "POST",
    body: JSON.stringify({
      note: noteInput?.value || "",
      status: normalizeLearningStatus($("learningStatusInput")?.value),
      ...extra,
    }),
  });
  Object.assign(err, updated);
  learningNoteEditingErrorId = Number(updated.error_id || err.error_id || 0);
  learningNoteDirty = false;
  renderInspector(err);
  syncMarkButton();
  showLearningSavedFeedback();
}

function preserveLearningDraft() {
  const err = reviewErrors[currentErrorIndex];
  const noteInput = $("learningNoteInput");
  if (!err?.error_id || !noteInput || !learningNoteDirty) return;
  if (learningNoteEditingErrorId !== Number(err.error_id)) return;
  err.user_note = noteInput.value;
}

function createTileElement(tile) {
  const span = document.createElement("span");
  const parsed = parseTileLabel(tile);
  span.className = `tile tile-${parsed.kind}`;
  span.dataset.tile = tile;
  if (parsed.kind === "m") {
    span.innerHTML = `<span class="tile-face man-face"><b>${escapeHtml(parsed.cn)}</b><i>萬</i></span>`;
  } else if (parsed.kind === "p") {
    span.appendChild(renderPinFace(parsed.value));
  } else if (parsed.kind === "s") {
    span.appendChild(renderSouFace(parsed.value));
  } else {
    span.innerHTML = `<span class="tile-face honor-face honor-${parsed.main}"><b>${escapeHtml(parsed.main)}</b></span>`;
  }
  span.title = tile;
  return span;
}

function parseTileLabel(tile) {
  const text = String(tile || "");
  const match = text.match(/^([1-9])([万筒索])$/);
  if (match) {
    const suitName = { "万": "m", "筒": "p", "索": "s" }[match[2]];
    const cn = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"][Number(match[1])];
    return { kind: suitName, main: match[1], value: Number(match[1]), suit: match[2], cn };
  }
  return { kind: "honor", main: text.slice(0, 1) || "?", suit: "" };
}

function renderPinFace(value) {
  const wrap = document.createElement("span");
  wrap.className = `tile-face pin-face pin-${value}`;
  for (let i = 0; i < value; i += 1) {
    const pip = document.createElement("span");
    pip.className = `pip pip-${i + 1}`;
    wrap.appendChild(pip);
  }
  return wrap;
}

function renderSouFace(value) {
  const wrap = document.createElement("span");
  wrap.className = `tile-face sou-face sou-${value}`;
  for (let i = 0; i < value; i += 1) {
    const bamboo = document.createElement("span");
    bamboo.className = `bamboo bamboo-${i + 1}`;
    bamboo.innerHTML = "<i></i><i></i>";
    wrap.appendChild(bamboo);
  }
  return wrap;
}

function fallbackTiles(err) {
  const text = `${actionText(err.actual)} ${actionText(err.expected)}`;
  const tiles = Array.from(text.matchAll(/[1-9][万筒索]|东|南|西|北|白|发|中/g)).map((m) => m[0]);
  return tiles.length ? tiles : ["一", "二", "三", "四", "五", "六", "七", "八", "九", "中", "发", "白", "东"];
}

function extractTileLabel(text) {
  const value = String(text || "");
  const patterns = [
    /0[萬万m]/,
    /0[筒饼餅p]/,
    /0[索条條s]/,
    /[1-9][萬万m]/,
    /[1-9][筒饼餅p]/,
    /[1-9][索条條s]/,
    /[1-9][mps]/i,
    /[東东南西北白發发中]/,
  ];
  for (const pattern of patterns) {
    const match = value.match(pattern);
    if (match) return match[0];
  }
  return "";
}

function tileCodeFromLabel(tile) {
  const text = String(tile || "").trim();
  let match = text.match(/([0-9])\s*([mps])/i);
  if (match) return `${match[1]}${match[2].toLowerCase()}`;
  match = text.match(/([0-9])\s*([萬万])/);
  if (match) return `${match[1]}m`;
  match = text.match(/([0-9])\s*([筒饼餅])/);
  if (match) return `${match[1]}p`;
  match = text.match(/([0-9])\s*([索条條])/);
  if (match) return `${match[1]}s`;
  const honor = text.match(/[東东南西北白發发中]/)?.[0];
  return {
    "東": "1z",
    "东": "1z",
    "南": "2z",
    "西": "3z",
    "北": "4z",
    "白": "5z",
    "發": "6z",
    "发": "6z",
    "中": "7z",
  }[honor] || "";
}

function renderActionCell(action) {
  const cell = document.createElement("td");
  cell.className = "candidate-action";
  const text = actionText(action);
  const tile = extractTileLabel(text);
  const label = document.createElement("span");
  label.textContent = tile ? text.replace(tile, "").trim() || "打" : text;
  cell.appendChild(label);
  if (tile) cell.appendChild(createTileElement(tile));
  return cell;
}

function renderChoice(id, text) {
  const box = $(id);
  box.innerHTML = "";
  const action = String(text || "--");
  const tile = extractTileLabel(action);
  const label = document.createElement("span");
  label.className = "choice-action";
  label.textContent = tile ? action.replace(tile, "").trim() || "打" : action;
  box.appendChild(label);
  if (tile) box.appendChild(createTileElement(tile));
}

function createTileElement(tile) {
  const span = document.createElement("span");
  const code = tileCodeFromLabel(tile);
  span.className = "tile svg-tile";
  span.dataset.tile = tile;
  span.title = tile;
  if (!code) {
    span.classList.add("tile-fallback");
    span.textContent = String(tile || "?");
    return span;
  }
  const img = document.createElement("img");
  img.src = `/killer/media/Regular_shortnames/${code}.svg`;
  img.alt = String(tile || code);
  img.draggable = false;
  span.appendChild(img);
  return span;
}

function renderMarks() {
  const box = $("marksList");
  box.innerHTML = "";
  if (!marksCache.length) {
    box.innerHTML = `<div class="empty-state">还没有收藏错题。进入某张牌谱的 Top 错误，把值得复盘的选择加入错题库。</div>`;
    return;
  }
  for (const err of marksCache) {
    const card = document.createElement("article");
    card.className = "error-card";
    card.innerHTML = `
      <button class="error-main" type="button">
        <span>
          <strong>${escapeHtml(err.game_title)} · ${escapeHtml(err.round)} · ${err.junme ?? "?"} 巡</strong>
          <small>实际：${escapeHtml(actionText(err.actual))} · Mortal：${escapeHtml(actionText(err.expected))}</small>
        </span>
        <b>Q差 ${fmt(err.q_gap, 3)}</b>
      </button>
      <div class="error-actions">
        <span>rating ${fmt(err.rating_percent)} · 收藏于 ${escapeHtml(err.marked_at)}</span>
        <button class="mark-btn marked" type="button">移出错题库</button>
      </div>
    `;
    card.querySelector(".error-main").onclick = () => openGameReview(err.game_id, 9999, err.error_id);
    card.querySelector(".mark-btn").onclick = async () => {
      await api(`/api/errors/${err.error_id}/mark`, { method: "POST", body: "{}" });
      await loadMarks();
      if (reviewGame) await loadReviewData(reviewGame.id, Number($("reviewLimitInput").value));
    };
    box.appendChild(card);
  }
}

function drawTrend() {
  const canvas = $("trendCanvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fbfcfd";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#d8dee4";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 24 + i * ((h - 52) / 4);
    ctx.beginPath();
    ctx.moveTo(44, y);
    ctx.lineTo(w - 18, y);
    ctx.stroke();
    ctx.fillStyle = "#66727f";
    ctx.font = "12px Segoe UI";
    ctx.fillText(String(100 - i * 25), 12, y + 4);
  }
  const trendGames = uniqueGames.filter((g) => Number(g.rating_percent) > 0);
  const avg = trendGames.reduce((sum, item) => sum + Number(item.rating_percent || 0), 0) / (trendGames.length || 1);
  $("avgRating").textContent = trendGames.length ? fmt(avg) : "--";
  if (!trendGames.length) {
    ctx.fillStyle = "#66727f";
    ctx.font = "15px Segoe UI";
    ctx.fillText("分析第一份牌谱后，这里会显示 rating 趋势。", 48, 140);
    return;
  }
  const pts = trendGames.map((g, idx) => {
    const x = trendGames.length === 1 ? w / 2 : 50 + idx * ((w - 84) / (trendGames.length - 1));
    const y = 24 + (100 - Math.max(0, Math.min(100, Number(g.rating_percent)))) * ((h - 52) / 100);
    return { x, y, game: g };
  });
  ctx.strokeStyle = "#1f8a70";
  ctx.lineWidth = 3;
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  ctx.stroke();
  for (const p of pts) {
    ctx.fillStyle = p.game.id === selectedId ? "#b42318" : "#1f8a70";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
    ctx.fill();
    const label = fmt(p.game.rating_percent, 1);
    ctx.font = "700 12px Segoe UI";
    const textWidth = ctx.measureText(label).width;
    const labelX = Math.max(8, Math.min(w - textWidth - 8, p.x - textWidth / 2));
    const labelY = Math.max(16, p.y - 12);
    ctx.fillStyle = "#17444a";
    ctx.fillText(label, labelX, labelY);
  }
}

async function startOfficialReview() {
  const raw = $("mainInput").value.trim();
  if (!raw) {
    alert("先粘贴雀魂或天凤牌谱链接。");
    return;
  }
  const body = {
    title: makeAutoTitle(raw),
    source: raw,
    platform: raw.includes("maj-soul") || raw.includes("mahjongsoul") ? "majsoul" : "tenhou",
    tags: "",
    notes: "",
    model_tag: $("modelInput").value,
    ui_mode: "killerducky",
    input: raw,
  };
  const existing = await api("/api/official/find", {
    method: "POST",
    body: JSON.stringify({ input: raw, model_tag: body.model_tag, ui_mode: body.ui_mode }),
  });
  if (existing.found && existing.game) {
    $("officialStatus").textContent = "已找到这份牌谱的历史分析，直接打开保存结果。";
    await loadGames();
    await openGameReview(existing.game.id, 9999);
    return;
  }
  if (window.mortalCoachElectron?.enabled) {
    await startEmbeddedOfficialReview(body);
    return;
  }
  await api("/api/official/start", { method: "POST", body: JSON.stringify(body) });
  await loadOfficialStatus();
}

function makeAutoTitle(raw) {
  const now = new Date().toLocaleString();
  if (raw.includes("maj-soul") || raw.includes("mahjongsoul") || raw.includes("雀魂")) return `雀魂复盘 ${now}`;
  if (raw.includes("tenhou.net")) return `天凤复盘 ${now}`;
  return `Mortal 复盘 ${now}`;
}

async function startEmbeddedOfficialReview(body) {
  embeddedOfficialRunning = true;
  embeddedOfficialBody = body;
  const workspace = $("officialWorkspace");
  const webview = $("officialWebview");
  const status = $("embeddedOfficialStatus");
  workspace.classList.remove("hidden");
  workspace.classList.add("auto-submitting");
  $("officialStatus").textContent = "正在内嵌官方 Mortal 窗口中提交...";
  status.textContent = "正在打开官方 Mortal。";
  webview.src = OFFICIAL_URL;
  const revealTimer = setTimeout(() => {
    workspace.classList.remove("auto-submitting");
    status.textContent = "如果官方验证没有自动通过，请在当前窗口中完成验证。";
  }, 5000);
  try {
    await waitForWebviewEvent(webview, "dom-ready", 60000);
    status.textContent = "正在填写官方 Mortal 表单。";
    await fillOfficialWebviewForm(webview, body);
    status.textContent = "等待官方验证完成。";
    await waitForOfficialSubmitEnabled(webview, status);
    status.textContent = "正在提交官方 Mortal，等待分析结果。";
    await webview.executeJavaScript("document.querySelector('form[name=reviewForm] button[type=submit]').click()");
    const result = await waitForOfficialResult(webview, status);
    clearTimeout(revealTimer);
    workspace.classList.remove("auto-submitting");
    status.textContent = "结果已生成，正在保存到本地复盘库。";
    const id = await saveEmbeddedOfficialResult(body, result);
    $("mainInput").value = "";
    await loadGames();
    await loadMarks();
    await openGameReview(id, 9999);
    status.textContent = "官方 Mortal 结果已保存。";
    $("officialStatus").textContent = "官方 Mortal 结果已保存。";
  } finally {
    embeddedOfficialRunning = false;
    clearTimeout(revealTimer);
    workspace.classList.remove("auto-submitting");
  }
}

function waitForWebviewEvent(webview, eventName, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      webview.removeEventListener(eventName, onEvent);
      reject(new Error(`等待官方窗口 ${eventName} 超时。`));
    }, timeoutMs);
    function onEvent() {
      clearTimeout(timer);
      webview.removeEventListener(eventName, onEvent);
      resolve();
    }
    webview.addEventListener(eventName, onEvent);
  });
}

async function fillOfficialWebviewForm(webview, body) {
  await webview.executeJavaScript(`
    (() => {
      const input = document.querySelector('input[name="log-url"]');
      if (!input) throw new Error('没有找到官方牌谱输入框');
      input.value = ${JSON.stringify(body.input)};
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      const engine = document.querySelector('select[name="engine"]');
      if (engine) {
        engine.value = 'mortal';
        engine.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const model = document.querySelector('select[name="mortal-model-tag"]');
      if (model) {
        model.value = ${JSON.stringify(body.model_tag || "4.1b")};
        model.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const ui = document.querySelector('select[name="ui"]');
      if (ui) {
        const option = Array.from(ui.options).find((item) => {
          const text = String(item.textContent || item.value || '').toLowerCase();
          return text.includes('killerducky') || text.includes('board') || item.value === 'killerducky';
        });
        if (option) {
          ui.value = option.value;
          ui.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (ui.value !== 'killerducky') {
          throw new Error('官方界面没有切换到 KillerDucky 棋盘版，已停止提交以避免保存 Classic。');
        }
      }
      const lang = document.querySelector('select[name="lang"]');
      if (lang) {
        const option = Array.from(lang.options).find((item) => {
          const text = String(item.textContent || item.value || '').toLowerCase();
          return text.includes('简体') || text.includes('zh') || text.includes('cn');
        });
        if (option) lang.value = option.value;
        lang.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const rating = document.querySelector('input[name="show-rating"]');
      if (rating) {
        rating.checked = true;
        rating.dispatchEvent(new Event('change', { bubbles: true }));
      }
      return true;
    })();
  `);
  await injectOfficialExtractor(webview);
}

async function injectOfficialExtractor(webview) {
  await webview.executeJavaScript(`
    (() => {
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const textOf = (node) => String(node?.innerText || node?.value || node?.getAttribute?.('aria-label') || '').trim();
    const allControls = () => Array.from(document.querySelectorAll('button, input[type="button"], a'));
    const findControl = (pattern) => allControls().find((node) => pattern.test(textOf(node)));
    const findPrevError = () => findControl(/上一错误|上一錯誤|Previous error|Prev error/i);
    const findNextError = () => findControl(/下一错误|下一錯誤|Next error/i);

    window.__mortalCoachIsResultReady = () => {
      const text = document.body ? document.body.innerText : '';
      const classic = text.includes('mjai-reviewer') && Boolean(document.querySelector('details, .collapse, table'));
      const board = /玩家/.test(text) && /Mortal/.test(text) && /操作/.test(text) && /\\bQ\\b/.test(text) && /\\bP\\b/.test(text);
      const boardByControls = Boolean(findPrevError() && findNextError() && /Mortal/.test(text));
      return { ready: Boolean(classic || board || boardByControls), classic, board: Boolean(board || boardByControls) };
    };

    function extractRating(text) {
      const rating = (() => {
        const patterns = [
          /^rating\\s*\\n\\s*([0-9]+(?:\\.[0-9]+)?)\\s*$/im,
          /\\brating\\b[^0-9]{0,80}([0-9]+(?:\\.[0-9]+)?)/i,
          /评分[^0-9]{0,80}([0-9]+(?:\\.[0-9]+)?)/i
        ];
        for (const pattern of patterns) {
          const match = text.match(pattern);
          if (match) {
            const value = Number(match[1]);
            if (Number.isFinite(value) && value >= 0 && value <= 100) return value;
          }
        }
        return null;
      })();
      return rating;
    }

    function extractMatchRate(text) {
      const matchRate = (() => {
        const match = text.match(/(\\d+)\\s*\\/\\s*(\\d+)\\s*=\\s*([0-9]+(?:\\.[0-9]+)?)%/);
        if (!match) return { total_matches: 0, total_reviewed: 0 };
        return { total_matches: Number(match[1]), total_reviewed: Number(match[2]) };
      })();
      return matchRate;
    }

    function extractCandidateRows() {
      const table = Array.from(document.querySelectorAll('table')).find((item) => {
        const text = item.innerText || '';
        return /操作/.test(text) && /\\bQ\\b/.test(text) && /\\bP\\b/.test(text);
      });
      const rows = [];
      if (table) {
        for (const tr of Array.from(table.querySelectorAll('tr'))) {
          const cells = Array.from(tr.querySelectorAll('td, th')).map((cell) => textOf(cell)).filter(Boolean);
          if (cells.length < 2 || /操作|action/i.test(cells[0])) continue;
          const q = Number(String(cells[1]).match(/-?\\d+(?:\\.\\d+)?/)?.[0]);
          const p = Number(String(cells[2] || '').match(/-?\\d+(?:\\.\\d+)?/)?.[0]);
          if (Number.isFinite(q)) rows.push({ action: cells[0], q_value: q, prob: Number.isFinite(p) ? p : null });
        }
        if (rows.length) return rows;
      }

      const lines = (document.body?.innerText || '').split(/\\n+/).map((line) => line.trim()).filter(Boolean);
      let start = lines.findIndex((line, idx) => /操作/.test(line) && lines[idx + 1] === 'Q');
      if (start < 0) start = lines.findIndex((line) => /^操作\\s+Q\\s+P$/i.test(line));
      if (start >= 0 && lines[start + 1] === 'Q' && lines[start + 2] === 'P') {
        for (let i = start + 3; i + 2 < lines.length; i += 3) {
          if (/上一局|下一局|上一错误|下一错误|选项|关于|玩家|Mortal/.test(lines[i])) break;
          const q = Number(String(lines[i + 1]).match(/-?\\d+(?:\\.\\d+)?/)?.[0]);
          const p = Number(String(lines[i + 2]).match(/-?\\d+(?:\\.\\d+)?/)?.[0]);
          if (!Number.isFinite(q)) break;
          rows.push({ action: lines[i], q_value: q, prob: Number.isFinite(p) ? p : null });
        }
        if (rows.length) return rows;
      }
      const from = Math.max(0, start + 1);
      for (let i = from; i < lines.length; i += 1) {
        const line = lines[i];
        if (/上一局|下一局|上一错误|下一错误|选项|关于|玩家|Mortal/.test(line)) break;
        const match = line.match(/^(.+?)\\s+(-?\\d+(?:\\.\\d+)?)\\s+(-?\\d+(?:\\.\\d+)?)$/);
        if (match) rows.push({ action: match[1].trim(), q_value: Number(match[2]), prob: Number(match[3]) });
      }
      return rows;
    }

    function extractPlayerAction(text) {
      const match = text.match(/玩家\\s*\\n\\s*([^\\n]+)\\s*\\n\\s*Mortal\\s*\\n\\s*([^\\n]+)/);
      if (!match) return { actual: '', expected: '' };
      return { actual: match[1].trim(), expected: match[2].trim() };
    }

    function scrapeCurrentError(index) {
      const text = document.body ? document.body.innerText : '';
      const candidates = extractCandidateRows();
      if (!candidates.length) return null;
      const choice = extractPlayerAction(text);
      let actualRank = candidates.findIndex((row) => choice.actual && (row.action.includes(choice.actual) || choice.actual.includes(row.action)));
      if (actualRank < 0 && candidates.length > 1) actualRank = 1;
      if (actualRank < 0) actualRank = 0;
      const best = candidates[0];
      const actual = candidates[actualRank] || candidates[0];
      const gap = Number(best.q_value) - Number(actual.q_value);
      if (!Number.isFinite(gap) || gap <= 0) return null;
      const roundMatch = text.match(/([东南西北]\\s*\\d(?:-\\d)?(?:\\s*\\+\\d+)?|[ESWN]\\d(?:\\.\\d)?)/);
      const remainMatch = text.match(/x\\s*(\\d+)|剩余\\s*(\\d+)|餘\\s*(\\d+)/);
      return {
        kyoku_index: 0,
        entry_index: index,
        round: roundMatch ? roundMatch[1].replace(/\\s+/g, '') : '?',
        junme: null,
        tiles_left: remainMatch ? Number(remainMatch[1] || remainMatch[2] || remainMatch[3]) : null,
        shanten: null,
        q_gap: gap,
        actual_rank: actualRank + 1,
        candidate_count: candidates.length,
        expected: { type: 'text', text: choice.expected || best.action },
        actual: { type: 'text', text: choice.actual || actual.action },
        best_detail: best,
        actual_detail: actual,
        candidates,
        state: { summary_text: text.slice(0, 500) }
      };
    }

    window.__mortalCoachCollectKillerDuckyErrors = async (maxCount = 80) => {
      const prev = findPrevError();
      const next = findNextError();
      if (!prev || !next) return [];
      for (let i = 0; i < 160; i += 1) prev.click();
      await sleep(120);
      const errors = [];
      const seen = new Set();
      for (let i = 0; i < maxCount; i += 1) {
        const item = scrapeCurrentError(i);
        if (item) {
          const key = [item.round, item.tiles_left, item.actual?.text, item.expected?.text, item.q_gap.toFixed(3)].join('|');
          if (seen.has(key) && errors.length > 0) break;
          seen.add(key);
          errors.push(item);
        }
        next.click();
        await sleep(90);
      }
      errors.sort((a, b) => (Number(b.q_gap) - Number(a.q_gap)) || (Number(b.actual_rank) - Number(a.actual_rank)));
      return errors;
    };

    window.__mortalCoachExtractResult = async () => {
      const text = document.body ? document.body.innerText : '';
      const matchRate = extractMatchRate(text);
      const errors = [];
      return { rating_percent: extractRating(text), total_matches: matchRate.total_matches, total_reviewed: matchRate.total_reviewed, errors };
    };
    true;
    })();
  `);
}

async function waitForOfficialSubmitEnabled(webview, status) {
  const deadline = Date.now() + 5 * 60 * 1000;
  while (Date.now() < deadline) {
    const enabled = await tryExecuteWebview(webview, `
      (() => {
        const btn = document.querySelector('form[name="reviewForm"] button[type="submit"]');
        return Boolean(btn && !btn.disabled);
      })();
    `);
    if (enabled) return;
    status.textContent = "等待官方验证完成。如果看到验证框，请在当前窗口中完成。";
    await sleep(1000);
  }
  throw new Error("官方 Mortal 的提交按钮 5 分钟内没有启用。");
}

async function waitForOfficialResult(webview, status) {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    await injectOfficialExtractor(webview);
    const result = await tryExecuteWebview(webview, `
      (async () => {
        const text = document.body ? document.body.innerText : '';
        const ready = window.__mortalCoachIsResultReady?.() || { ready: false };
        const done = Boolean(ready.ready);
        return {
          done,
          text,
          html: document.documentElement.outerHTML,
          url: location.href,
          killer_json: done ? await (async () => {
            try {
              const dataPath = new URL(location.href).searchParams.get('data');
              if (!dataPath) return null;
              const response = await fetch(dataPath);
              if (!response.ok) return null;
              return await response.json();
            } catch (error) {
              return null;
            }
          })() : null,
          snapshot: done ? await window.__mortalCoachExtractResult?.() : null
        };
      })();
    `);
    if (result?.done) return result;
    status.textContent = "官方 Mortal 正在分析中，结果生成后会自动保存。";
    await sleep(2000);
  }
  throw new Error("官方 Mortal 15 分钟内没有生成结果。");
}

async function saveEmbeddedOfficialResult(body, result) {
  const snapshot = result.snapshot || {};
  const rating = snapshot.rating_percent ?? extractRatingPercent(result.text);
  const data = await api("/api/import-official", {
    method: "POST",
    body: JSON.stringify({
      title: body.title,
      source: result.url,
      original_url: body.input,
      result_url: result.url,
      model_tag: body.model_tag,
      ui_mode: body.ui_mode,
      tags: body.tags,
      notes: `${body.notes || ""}\n\nOriginal paipu: ${body.input}`.trim(),
      rating_percent: rating ?? "",
      total_reviewed: snapshot.total_reviewed ?? 0,
      total_matches: snapshot.total_matches ?? 0,
      errors: snapshot.errors || [],
      killer_json: result.killer_json || null,
      html: result.html,
    }),
  });
  return data.id;
}

async function saveCurrentOfficialWorkspace() {
  const webview = $("officialWebview");
  if (!webview || typeof webview.executeJavaScript !== "function") {
    throw new Error("当前环境不能读取官方窗口。");
  }
  const body = embeddedOfficialBody || {
    title: makeAutoTitle($("mainInput").value || "Mortal 复盘"),
    source: $("mainInput").value.trim(),
    platform: $("mainInput").value.includes("maj-soul") || $("mainInput").value.includes("mahjongsoul") ? "majsoul" : "tenhou",
    tags: "",
    notes: "Manually saved from embedded official window",
    model_tag: $("modelInput").value,
    ui_mode: "killerducky",
    input: $("mainInput").value.trim(),
  };
  if (!body.input) throw new Error("缺少原始牌谱链接，无法保存当前官方结果。");
  await injectOfficialExtractor(webview);
  const result = await tryExecuteWebview(webview, `
    (async () => {
      const ready = window.__mortalCoachIsResultReady?.() || { ready: false };
      const text = document.body ? document.body.innerText : '';
      return {
        done: Boolean(ready.ready),
        text,
        html: document.documentElement.outerHTML,
        url: location.href,
        killer_json: await (async () => {
          try {
            const dataPath = new URL(location.href).searchParams.get('data');
            if (!dataPath) return null;
            const response = await fetch(dataPath);
            if (!response.ok) return null;
            return await response.json();
          } catch (error) {
            return null;
          }
        })(),
        snapshot: await window.__mortalCoachExtractResult?.()
      };
    })();
  `);
  if (!result?.done) throw new Error("还没有检测到官方棋盘结果，请等棋盘和 Q/P 表出现后再保存。");
  const id = await saveEmbeddedOfficialResult(body, result);
  await loadGames();
  await loadMarks();
  await openGameReview(id, 9999);
  $("officialWorkspace").classList.add("hidden");
  $("officialStatus").textContent = "已保存当前官方 Mortal 棋盘结果。";
}

function loadOfficialReviewFrame() {
  if (!reviewGame) return;
  const webview = $("reviewWebview");
  const fallback = $("reviewBrowserFallback");
  if (!isBoardReviewGame()) {
    reviewWebviewReady = false;
    reviewWebviewTarget = "";
    if (webview) {
      webview.classList.add("hidden");
      webview.src = "about:blank";
    }
    if (fallback) {
      fallback.classList.remove("hidden");
      fallback.innerHTML = `
        <div class="board-required">
          <h3>这份结果是 Classic 页面</h3>
          <p>当前保存的官方结果不是你要的棋盘复盘界面。请用同一牌谱重新生成 KillerDucky 棋盘版结果；生成后会自动保存并进入棋盘版复盘。</p>
          <button id="generateBoardReviewBtn" type="button">生成官方棋盘版复盘</button>
        </div>
      `;
      const generateBtn = document.getElementById("generateBoardReviewBtn");
      if (generateBtn) generateBtn.onclick = () => generateBoardReview().catch((err) => alert(err.message));
    }
    return;
  }
  const target = buildKillerReviewUrl(reviewGame.id);
  if (!webview) {
    if (fallback) fallback.classList.remove("hidden");
    return;
  }
  if (fallback) fallback.classList.add("hidden");
  webview.classList.remove("hidden");
  sizeReviewWebview();
  if (reviewWebviewTarget !== target) {
    reviewWebviewReady = false;
    reviewWebviewTarget = target;
    webview.src = target;
  } else {
    reviewWebviewReady = true;
    syncOfficialError().catch(() => {});
  }
}

function isBoardReviewGame() {
  return reviewGame?.raw_json?.ui_mode === "killerducky" && !reviewGame?.raw_json?.is_classic_html;
}

async function switchToExistingBoardReview(limit) {
  if (isBoardReviewGame() || !reviewGame?.original_url) return false;
  const existing = await api("/api/official/find", {
    method: "POST",
    body: JSON.stringify({
      input: reviewGame.original_url,
      model_tag: reviewGame.model_tag || "4.1b",
      ui_mode: "killerducky",
    }),
  });
  if (existing.found && existing.game && existing.game.id !== reviewGame.id) {
    await openGameReview(existing.game.id, limit);
    return true;
  }
  return false;
}

async function generateBoardReview() {
  if (!reviewGame?.original_url) {
    throw new Error("这条记录缺少原始牌谱链接，无法重新生成棋盘版。");
  }
  const body = {
    title: `${reviewGame.title || "Mortal 复盘"} 棋盘版`,
    source: reviewGame.original_url,
    platform: reviewGame.original_url.includes("maj-soul") || reviewGame.original_url.includes("mahjongsoul") ? "majsoul" : "tenhou",
    tags: reviewGame.tags || "",
    notes: "Generated from MortalCoach review page",
    model_tag: reviewGame.model_tag || "4.1b",
    ui_mode: "killerducky",
    input: reviewGame.original_url,
  };
  if (window.mortalCoachElectron?.enabled) {
    await startEmbeddedOfficialReview(body);
    return;
  }
  await api("/api/official/start", { method: "POST", body: JSON.stringify(body) });
  await loadOfficialStatus();
}

async function decorateOfficialReview() {
  const webview = $("reviewWebview");
  if (!webview || typeof webview.executeJavaScript !== "function") return;
  await tryExecuteWebview(webview, `
    (() => {
      if (window.__mortalCoachBridgeInstalled) return true;
      window.__mortalCoachBridgeInstalled = true;
      const style = document.createElement('style');
      style.textContent = \`
        .mortalcoach-focus {
          outline: 4px solid #f59e0b !important;
          outline-offset: 4px !important;
          box-shadow: 0 0 0 8px rgba(245, 158, 11, .18) !important;
        }
        .mortalcoach-badge {
          position: sticky;
          top: 8px;
          z-index: 99999;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          margin: 8px 0;
          padding: 8px 10px;
          border-radius: 6px;
          background: #f59e0b;
          color: #111827;
          font: 700 13px/1.2 system-ui, sans-serif;
        }
      \`;
      document.head.appendChild(style);
      window.__mortalCoachGoToError = (entryIndex, label) => {
        const entries = Array.from(document.querySelectorAll(
          'details.collapse.entry[data-mark-red], details.entry[data-mark-red], details[data-mark-red]'
        ));
        document.querySelectorAll('.mortalcoach-focus').forEach((node) => node.classList.remove('mortalcoach-focus'));
        document.querySelectorAll('.mortalcoach-badge').forEach((node) => node.remove());
        if (entries.length) {
          const target = entries[Math.max(0, Math.min(entries.length - 1, Number(entryIndex) || 0))];
          target.open = true;
          target.classList.add('mortalcoach-focus');
          const badge = document.createElement('div');
          badge.className = 'mortalcoach-badge';
          badge.textContent = label || 'MortalCoach Top 错误';
          target.prepend(badge);
          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return { mode: 'details', count: entries.length };
        }

        const controls = Array.from(document.querySelectorAll('button, input[type="button"], a'));
        const textOf = (node) => String(node.innerText || node.value || node.getAttribute('aria-label') || '').trim();
        const previous = controls.find((node) => /上一错误|Previous error|Prev error/i.test(textOf(node)));
        const next = controls.find((node) => /下一错误|Next error/i.test(textOf(node)));
        if (previous && next) {
          for (let i = 0; i < 160; i += 1) previous.click();
          const steps = Math.max(0, Math.min(160, Number(entryIndex) || 0));
          for (let i = 0; i < steps; i += 1) next.click();
          return { mode: 'buttons', count: steps };
        }
        return { mode: 'none', count: 0 };
      };
      return true;
    })();
  `);
}

async function injectOfficialTopOverlay(webview) {
  const errors = (reviewErrors || []).map((err, index) => ({
    index,
    kyoku_index: Number(err.kyoku_index ?? 0),
    entry_index: Number(err.entry_index ?? index),
    round: err.round || "?",
    junme: err.junme ?? "",
    q_gap: Number(err.q_gap || 0),
    actual: actionText(err.actual),
    expected: actionText(err.expected),
    marked: Boolean(err.marked),
  }));
  await tryExecuteWebview(webview, `
    (() => {
      const errors = ${JSON.stringify(errors)};
      let root = document.getElementById('mortalcoach-top-overlay');
      if (!root) {
        const style = document.createElement('style');
        style.textContent = \`
          #mortalcoach-top-overlay {
            position: fixed;
            left: 16px;
            top: 16px;
            z-index: 2147483647;
            display: grid;
            grid-template-columns: auto auto minmax(220px, 360px) auto auto;
            gap: 8px;
            align-items: center;
            padding: 10px;
            border: 1px solid rgba(125, 211, 199, .45);
            border-radius: 8px;
            background: rgba(4, 40, 45, .94);
            color: #ecfeff;
            box-shadow: 0 14px 34px rgba(0, 0, 0, .28);
            font: 700 13px/1.2 system-ui, "Microsoft YaHei", sans-serif;
            backdrop-filter: blur(10px);
          }
          #mortalcoach-top-overlay select,
          #mortalcoach-top-overlay button {
            min-height: 34px;
            border: 1px solid rgba(125, 211, 199, .35);
            border-radius: 6px;
            background: #f7fbfb;
            color: #102a2d;
            font: inherit;
          }
          #mortalcoach-top-overlay button {
            padding: 0 10px;
            background: #1f8a70;
            color: white;
            cursor: pointer;
          }
          #mortalcoach-top-overlay .mc-empty {
            grid-column: 1 / -1;
            color: #9cc9cc;
            font-weight: 600;
          }
        \`;
        document.head.appendChild(style);
        root = document.createElement('div');
        root.id = 'mortalcoach-top-overlay';
        document.body.appendChild(root);
      }

      const format = (num) => Number(num || 0).toFixed(3);
      let current = 0;
      const visibleErrors = (limit) => {
        if (limit === '5') return errors.slice(0, 5);
        if (limit === '10') return errors.slice(0, 10);
        return errors;
      };
      const go = (items, index) => {
        if (!items.length) return;
        current = Math.max(0, Math.min(items.length - 1, index));
        const err = items[current];
        const label = \`MortalCoach #\${err.index + 1} \${err.round} Q差 \${format(err.q_gap)}\`;
        const jumped = window.MM?.jumpToMortalEval?.(err.kyoku_index || 0, err.entry_index);
        if (!jumped?.ok) window.__mortalCoachGoToError?.(err.entry_index, label);
      };
      const render = () => {
        if (!errors.length) {
          root.innerHTML = '<span class="mc-empty">MortalCoach：暂无可解析 Top 错误；仍可使用官方上一错误/下一错误。</span>';
          return;
        }
        root.innerHTML = \`
          <strong>Top 错误</strong>
          <select id="mc-top-limit">
            <option value="all">全部</option>
            <option value="5">Top 5</option>
            <option value="10">Top 10</option>
          </select>
          <select id="mc-top-jump"></select>
          <button id="mc-top-prev" type="button">上一条</button>
          <button id="mc-top-next" type="button">下一条</button>
        \`;
        const limit = root.querySelector('#mc-top-limit');
        const jump = root.querySelector('#mc-top-jump');
        const rebuildJump = () => {
          const items = visibleErrors(limit.value);
          jump.innerHTML = '';
          items.forEach((err, idx) => {
            const option = document.createElement('option');
            option.value = String(idx);
            option.textContent = \`#\${err.index + 1} \${err.round} Q差 \${format(err.q_gap)}：\${err.actual || '?'} -> \${err.expected || '?'}\`;
            jump.appendChild(option);
          });
          current = 0;
          go(items, current);
        };
        limit.onchange = rebuildJump;
        jump.onchange = () => go(visibleErrors(limit.value), Number(jump.value || 0));
        root.querySelector('#mc-top-prev').onclick = () => {
          const items = visibleErrors(limit.value);
          go(items, current - 1);
          jump.value = String(current);
        };
        root.querySelector('#mc-top-next').onclick = () => {
          const items = visibleErrors(limit.value);
          go(items, current + 1);
          jump.value = String(current);
        };
        rebuildJump();
      };
      render();
      return true;
    })();
  `);
}

async function syncOfficialError() {
  const frame = $("reviewWebview");
  const err = reviewErrors[currentErrorIndex];
  if (!frame || !reviewWebviewReady || !err) return false;
  const label = `MortalCoach #${currentErrorIndex + 1} ${err.round} ${err.junme ?? "?"}巡 · Q差 ${fmt(err.q_gap, 3)}`;
  const kyokuIndex = Number(err.kyoku_index ?? 0);
  const entryIndex = Number(err.entry_index ?? currentErrorIndex);
  try {
    const win = frame.contentWindow;
    win?.MM?.fitToMortalCoach?.();
    const jumped = win?.MM?.jumpToMortalEval?.(kyokuIndex, entryIndex);
    if (!jumped?.ok) win?.__mortalCoachGoToError?.(entryIndex, label);
    win?.dispatchEvent?.(new Event("resize"));
    return Boolean(jumped?.ok);
  } catch (error) {
    console.warn("MortalCoach failed to sync embedded KillerDucky frame", error);
    return false;
  }
}

function openOfficialResult() {
  if (!reviewGame) return;
  const workspace = $("officialWorkspace");
  const webview = $("officialWebview");
  const status = $("embeddedOfficialStatus");
  workspace.classList.remove("hidden");
  workspace.classList.remove("auto-submitting");
  status.textContent = "正在打开已保存的官方分析结果。";
  const target = reviewGame.result_url || `/api/games/${reviewGame.id}/saved-html`;
  if (window.mortalCoachElectron?.enabled) webview.src = target;
  else window.open(target, "_blank", "noreferrer");
}

async function loadOfficialStatus() {
  if (embeddedOfficialRunning) return;
  const status = await api("/api/official/status");
  const box = $("officialStatus");
  const btn = $("officialBtn");
  btn.disabled = Boolean(status.running);
  if (status.running) {
    box.textContent = status.message || "官方 Mortal 自动分析运行中...";
    btn.textContent = "官方分析运行中...";
    return;
  }
  btn.textContent = "开始 Mortal 分析并保存";
  box.textContent = status.message || "尚未运行官方 Mortal 自动分析。";
  if (status.ok && status.game_id) {
    await loadGames();
    await openGameReview(status.game_id, 9999);
  }
}

async function tryExecuteWebview(webview, script) {
  try {
    return await webview.executeJavaScript(script);
  } catch (_) {
    return null;
  }
}

function extractRatingPercent(text) {
  const patterns = [
    /^rating\s*\n\s*([0-9]+(?:\.[0-9]+)?)\s*$/im,
    /\brating\b[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)/i,
    /评分[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)/i,
  ];
  for (const pattern of patterns) {
    const match = String(text || "").match(pattern);
    if (!match) continue;
    const value = Number(match[1]);
    if (Number.isFinite(value) && value >= 0 && value <= 100) return value;
  }
  return null;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

$("refreshBtn").onclick = () => Promise.all([loadGames(), loadMarks(), loadProfile()]).catch((err) => alert(err.message));
if ($("openUpdateBtn")) $("openUpdateBtn").onclick = () => openUpdateDownload().catch((err) => alert(err.message));
if ($("dismissUpdateBtn")) $("dismissUpdateBtn").onclick = dismissUpdateNotice;
$("officialBtn").onclick = () => startOfficialReview().catch((err) => alert(err.message));
$("saveProfileBtn").onclick = () => saveProfile().catch((err) => alert(err.message));
if ($("saveTenhouProfileBtn")) $("saveTenhouProfileBtn").onclick = () => saveProfile().catch((err) => alert(err.message));
if ($("syncMajsoulBtn")) $("syncMajsoulBtn").onclick = () => syncMajsoulStats().catch((err) => alert(err.message));
$("backToLibraryBtn").onclick = () => showView("libraryView");
$("errorJumpInput").onchange = () => setCurrentError(Number($("errorJumpInput").value || 0));
$("markCurrentBtn").onclick = async () => {
  const err = reviewErrors[currentErrorIndex];
  if (!err?.error_id || !reviewGame) return;
  const wasMarked = Boolean(err.marked);
  await api(`/api/errors/${err.error_id}/mark`, { method: "POST", body: "{}" });
  await loadReviewData(reviewGame.id, Number($("reviewLimitInput").value));
  await loadMarks();
  const btn = $("markCurrentBtn");
  if (btn) {
    btn.classList.remove("save-feedback");
    void btn.offsetWidth;
    btn.classList.add("save-feedback");
  }
  if ($("learningSaveStatus")) $("learningSaveStatus").textContent = wasMarked ? "已移出错题库" : "已加入错题库";
};
$("saveLearningBtn").onclick = () => saveCurrentLearning().catch((err) => alert(err.message));
if ($("learningNoteInput")) {
  $("learningNoteInput").addEventListener("focus", () => {
    const err = reviewErrors[currentErrorIndex];
    learningNoteEditingErrorId = Number(err?.error_id || 0);
  });
  $("learningNoteInput").addEventListener("input", () => {
    const err = reviewErrors[currentErrorIndex];
    learningNoteEditingErrorId = Number(err?.error_id || 0);
    learningNoteDirty = true;
    if (err?.error_id) err.user_note = $("learningNoteInput").value;
    if ($("learningSaveStatus")) $("learningSaveStatus").textContent = "有未保存修改";
  });
}
$("reviewLimitInput").onchange = () => {
  if (reviewGame) {
    currentErrorIndex = 0;
    loadReviewData(reviewGame.id, Number($("reviewLimitInput").value)).catch((err) => alert(err.message));
  }
};
$("closeOfficialWorkspace").onclick = () => {
  $("officialWorkspace").classList.remove("auto-submitting");
  $("officialWorkspace").classList.add("hidden");
};
$("saveOfficialWorkspaceBtn").onclick = () => saveCurrentOfficialWorkspace().catch((err) => alert(err.message));
if ($("themeInput")) {
  $("themeInput").onchange = () => {
    applyAppTheme($("themeInput").value);
    if (reviewGame?.id && reviewWebviewTarget) {
      const target = buildKillerReviewUrl(reviewGame.id);
      if (target !== reviewWebviewTarget) {
        reviewWebviewReady = false;
        reviewWebviewTarget = target;
        $("reviewWebview").src = target;
      }
    }
  };
}
document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.onclick = () => showView(btn.dataset.view);
});
$("librarySearchInput").oninput = renderLibrary;
$("librarySortInput").onchange = renderLibrary;
if ($("libraryPlatformInput")) $("libraryPlatformInput").onchange = renderLibrary;
document.querySelectorAll(".profile-tab").forEach((button) => {
  button.onclick = () => showProfileTab(button.dataset.profileTab);
});
document.querySelectorAll("[data-nav]").forEach((btn) => {
  btn.onclick = () => handleBoardNav(btn.dataset.nav);
});
const reviewWebview = $("reviewWebview");
if (reviewWebview && typeof reviewWebview.addEventListener === "function") {
  reviewWebview.addEventListener("load", async () => {
    reviewWebviewReady = true;
    sizeReviewWebview();
    syncReviewTheme();
    reviewWebview.contentWindow?.MM?.fitToMortalCoach?.();
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await sleep(attempt === 0 ? 250 : 300);
      sizeReviewWebview();
      syncReviewTheme();
      reviewWebview.contentWindow?.MM?.fitToMortalCoach?.();
      if (await syncOfficialError()) break;
    }
  });
}

window.addEventListener("resize", () => {
  if (document.body.classList.contains("review-mode")) {
    sizeReviewWebview();
    $("reviewWebview")?.contentWindow?.MM?.fitToMortalCoach?.();
  }
});

window.addEventListener("message", (event) => {
  if (event.data?.type === "mortalcoach-position") {
    handleEmbeddedReviewPosition(event.data);
  }
});

window.addEventListener("keydown", (event) => {
  if (!document.body.classList.contains("review-mode")) return;
  const tag = event.target?.tagName?.toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    setCurrentError(currentErrorIndex - 1);
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    setCurrentError(currentErrorIndex + 1);
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    handleBoardNav("prevRound");
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    handleBoardNav("nextRound");
  }
});

applyAppTheme();
Promise.all([loadGames(), loadMarks(), loadProfile()]).catch((err) => alert(err.message));
loadOfficialStatus().catch((err) => ($("officialStatus").textContent = err.message));
checkForUpdates().catch(() => {});
setInterval(() => loadOfficialStatus().catch(() => {}), 3000);
