const state = {
  findings: [],
  exportPayload: {},
  enabledRulePacks: [],
};

const REQUEST_TIMEOUT_MS = 5000;

const byId = (id) => document.getElementById(id);
const requestSignal = () => AbortSignal.timeout(REQUEST_TIMEOUT_MS);

async function loadJson(path) {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    signal: requestSignal(),
  });
  if (!response.ok) {
    throw new Error(`dashboard request failed: ${path}`);
  }
  return response.json();
}

async function sendJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal: requestSignal(),
  });
  if (!response.ok) {
    throw new Error(`dashboard request failed: ${path}`);
  }
  return response.json();
}

function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = String(value);
  }
}

function renderStatus(status) {
  setText("indexState", status.index_fresh ? "Fresh" : "Needs index");
  setText("findingCount", status.finding_count);
  setText("gitState", status.git_status);
}

function precisionLabel(value) {
  if (value === null || value === undefined) {
    return "precision n/a";
  }
  return `precision ${Math.round(value * 100)}%`;
}

function findingBadges(finding) {
  const badges = document.createElement("div");
  badges.className = "finding-badges";
  const tier = finding.confidence_tier || "heuristic";
  const tierChip = document.createElement("span");
  tierChip.className = `chip chip-tier chip-tier-${tier}`;
  tierChip.textContent = tier;
  badges.append(tierChip);
  const language = finding.provenance && finding.provenance.language;
  if (language) {
    const langChip = document.createElement("span");
    langChip.className = "chip chip-lang";
    langChip.textContent = language;
    badges.append(langChip);
  }
  const precisionChip = document.createElement("span");
  precisionChip.className = "chip chip-precision";
  precisionChip.textContent = precisionLabel(finding.acceptance_precision);
  badges.append(precisionChip);
  return badges;
}

function renderFindings(payload) {
  state.findings = payload.findings || [];
  const list = byId("findingsList");
  if (!list) {
    return;
  }
  list.replaceChildren();
  if (state.findings.length === 0) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "No findings in the current report.";
    list.append(empty);
    return;
  }
  state.findings.forEach((finding, index) => {
    const button = document.createElement("button");
    button.className = "finding-button";
    button.type = "button";
    button.textContent = finding.rule_id;
    const meta = document.createElement("div");
    meta.className = "finding-meta";
    meta.textContent = `${finding.file_path} · ${finding.severity} · ${finding.status}`;
    button.append(meta, findingBadges(finding));
    button.onclick = () => selectFinding(index);
    list.append(button);
  });
  selectFinding(0);
}

function selectFinding(index) {
  const finding = state.findings[index];
  const detail = byId("findingDetail");
  if (!finding || !detail) {
    return;
  }
  document.querySelectorAll(".finding-button").forEach((button, buttonIndex) => {
    button.classList.toggle("is-active", buttonIndex === index);
  });
  detail.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = finding.rule_id;
  const file = document.createElement("p");
  file.textContent = finding.file_path;
  const action = document.createElement("p");
  action.textContent = finding.suggested_action || "Inspect evidence before editing.";
  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `Severity ${finding.severity}; confidence ${finding.confidence}`;
  detail.append(title, file, action, meta, findingBadges(finding));
}

function renderProgress(progress) {
  setText("openCount", progress.open_count);
  setText("resolvedCount", progress.resolved_count);
  const trend = byId("progressTrend");
  if (!trend) {
    return;
  }
  trend.replaceChildren();
  const rows = [
    ["Open", progress.open_count],
    ["Resolved", progress.resolved_count],
    ["Regressed", progress.regressed_count],
  ];
  const maxValue = Math.max(1, ...rows.map((row) => row[1]));
  rows.forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "trend-row";
    const name = document.createElement("span");
    name.textContent = label;
    const track = document.createElement("div");
    track.className = "trend-track";
    const bar = document.createElement("div");
    bar.className = "trend-bar";
    bar.style.width = `${Math.max(4, (value / maxValue) * 100)}%`;
    const count = document.createElement("strong");
    count.textContent = String(value);
    track.append(bar);
    row.append(name, track, count);
    trend.append(row);
  });
}

function renderRules(payload) {
  const rules = byId("ruleConfig");
  if (!rules) {
    return;
  }
  state.enabledRulePacks = payload.enabled_rule_packs || [];
  rules.replaceChildren();
  state.enabledRulePacks.forEach((pack) => {
    const item = ruleItem(pack, true);
    rules.append(item);
  });
  (payload.disabled_rule_packs || []).forEach((pack) => {
    const item = ruleItem(pack, false);
    rules.append(item);
  });
}

function ruleItem(pack, enabled) {
  const item = document.createElement("div");
  item.className = "rule-item";
  const label = document.createElement("span");
  label.textContent = pack;
  const button = document.createElement("button");
  button.className = "rule-toggle";
  button.type = "button";
  button.textContent = enabled ? "Disable" : "Enable";
  button.onclick = () => updateRulePack(pack, !enabled);
  item.append(label, button);
  return item;
}

async function updateRulePack(pack, enabled) {
  const current = new Set(state.enabledRulePacks);
  if (enabled) {
    current.add(pack);
  } else {
    current.delete(pack);
  }
  const payload = await sendJson("/api/rules", {
    enabled_rule_packs: Array.from(current).sort(),
  });
  renderRules(payload);
}

function renderExport(payload) {
  state.exportPayload = payload;
  const button = byId("exportJson");
  if (!button) {
    return;
  }
  button.onclick = () => {
    const blob = new Blob([JSON.stringify(state.exportPayload, null, 2)], {
      type: "application/json",
    });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = "codescent-dashboard-export.json";
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  };
}

async function bootDashboard() {
  const [status, findings, progress, rules, report, exports] = await Promise.all([
    loadJson("/api/status"),
    loadJson("/api/findings"),
    loadJson("/api/progress"),
    loadJson("/api/rules"),
    loadJson("/api/reports"),
    loadJson("/api/exports"),
  ]);
  renderStatus(status);
  renderFindings(findings);
  renderProgress(progress);
  renderRules(rules);
  renderExport({ report, exports });
}

bootDashboard().catch((error) => {
  const strip = byId("statusStrip");
  if (strip) {
    strip.textContent = error.message;
  }
});
