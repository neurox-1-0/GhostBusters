const state = {
  run: null,
  scenarios: [],
  demoScenarios: [],
  visibleEvents: [],
  animationTimer: null,
  paused: false,
  skipAnimation: false,
  selectedReviewAction: null,
  hunt: null,
  reviews: [],
  selectedReviewContext: null,
  assistantContext: "product_help",
  loading: {
    initial: true,
    reviews: false,
    cloudHunt: false,
    run: false,
    review: false,
    assistant: false,
  },
  activeMode: "overview",
};

const stageDefinitions = [
  { id: "detected", title: "Detected", description: "Terraform pull-request change captured.", matches: ["run_created", "goal_received", "terraform_parsed"] },
  { id: "investigated", title: "Investigated", description: "Cost, usage, dependency, and activity evidence gathered.", matches: ["investigation_plan_created", "tool_selected"], prefix: ["tool_", "external_call_", "alternative_evidence_"] },
  { id: "recommended", title: "Recommended", description: "GhostBusters selected the safest cost action.", matches: ["conflicts_detected", "verifier_completed", "alternatives_generated", "recommendation_produced"], prefix: ["policy_"] },
  { id: "human", title: "Human Review", description: "A reviewer confirms, rejects, or requests more context.", matches: ["human_review_received", "additional_evidence_requested", "human_context_added", "workflow_resumed", "preferred_action_modified"] },
  { id: "remediation", title: "Remediation PR", description: "A simulated or real remediation pull request is recorded.", matches: ["mock_pr_created", "real_pr_created"] },
];

const toolNames = ["pricing", "utilization", "jira", "git_activity", "dependencies"];
const $ = (id) => document.getElementById(id);
const uiVersion = "judge-v6";
const requiredElementIds = [
  "api-pill",
  "overview-view",
  "overview-view-button",
  "overview-summary",
  "overview-pr-list",
  "overview-savings-list",
  "overview-approval-alerts",
  "overview-activity-list",
  "toast-region",
  "page-title",
  "simple-view",
  "technical-view",
  "pr-empty-state",
  "case-view",
  "stage-list",
  "recommendation-title",
  "important-alternatives",
  "evidence-summary-view",
  "resilience-summary",
  "review-form",
  "result-view",
  "planning-badge",
  "planning-note",
  "change-resource",
  "source-title",
  "recommendation-annual-savings",
  "evidence-mode-badge",
  "demo-modal-backdrop",
  "demo-scenario-select",
  "case-status",
  "human-decision-summary",
  "recommendation-summary",
  "technical-content",
  "technical-empty-state",
  "assistant-backdrop",
  "assistant-question-input",
  "assistant-answer",
];

const demoScenarioLabels = {
  safe: "Safe optimization",
  conflicting: "Conflicting evidence",
  dependency: "Active dependency",
  destructive: "Destructive change",
  missing_evidence: "Missing evidence",
};

function ensureCompatibleDom() {
  const missing = requiredElementIds.filter((id) => !$(id));
  if (!missing.length) return true;
  const reloadKey = `ghostbusters:ui-reload:${uiVersion}`;
  if (!sessionStorage.getItem(reloadKey)) {
    sessionStorage.setItem(reloadKey, "attempted");
    const url = new URL(window.location.href);
    url.searchParams.set("ui", uiVersion);
    window.location.replace(url.toString());
    return false;
  }
  console.error(`GhostBusters UI could not start because these elements are missing: ${missing.join(", ")}`);
  return false;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function safeObject(value, seen = new WeakSet()) {
  if (value === null || value === undefined) return value;
  if (Array.isArray(value)) return value.map((item) => safeObject(item, seen));
  if (typeof value !== "object") return value;
  if (seen.has(value)) return "[Circular]";
  seen.add(value);
  const output = {};
  Object.entries(value).forEach(([key, item]) => { output[key] = safeObject(item, seen); });
  seen.delete(value);
  return output;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(", ") : "None";
  if (typeof value === "object") return JSON.stringify(safeObject(value));
  return String(value);
}

function prettyValue(value) {
  if (value === null || value === undefined) return "Not recorded";
  if (typeof value === "object") return JSON.stringify(safeObject(value), null, 2);
  return formatValue(value);
}

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = formatValue(content);
  return node;
}

function append(parent, ...children) {
  children.filter(Boolean).forEach((child) => parent.appendChild(child));
  return parent;
}

function dataList(entries) {
  const list = el("dl", "data-list");
  entries.forEach(([label, value]) => {
    const row = el("div");
    append(row, el("dt", null, label), el("dd", null, value));
    list.appendChild(row);
  });
  return list;
}

function rawDetails(label, value) {
  const details = el("details", "raw-details");
  const pre = el("pre");
  pre.textContent = prettyValue(value);
  append(details, el("summary", null, label), pre);
  return details;
}

function labelFor(value) {
  if (value === "terraform_pr") return "Terraform PR";
  return String(value || "Not recorded").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusClass(value) {
  return `status-${String(value || "unknown").replaceAll(" ", "_").toLowerCase()}`;
}

function money(value) {
  if (value === null || value === undefined) return "Not recorded";
  return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function percentage(value) {
  if (value === null || value === undefined) return "Not recorded";
  return `${Math.round(Number(value) * 100)}%`;
}

function recommendationLabel(action) {
  return {
    request_evidence: "More Evidence Required",
    downsize: "Downsize to a safer lower-cost size",
    schedule: "Schedule non-critical usage",
    keep: "Keep resource unchanged",
    stop_for_observation: "Stop temporarily and observe",
    request_owner_confirmation: "Confirm owner before action",
    release_unused_ip: "Release unused public IP",
    abstain: "No change recommended",
    blocked: "Blocked by policy",
  }[action] || labelFor(action);
}

function policyStatusLabel(status) {
  return {
    needs_human_context: "More Evidence Required",
    passed: "Allowed with safety conditions",
    blocked: "Blocked by policy",
  }[status] || labelFor(status);
}

function policyEngineLabel(engine) {
  return {
    python_fallback: "Deterministic Safety Policy",
    python: "Deterministic Safety Policy",
    conftest: "Conftest policy engine",
  }[engine] || "Not recorded";
}

function planningModeLabel(mode) {
  return {
    gemini_primary: "AI-assisted planning",
    gemini_fallback_model: "AI fallback planning",
    mock_gemini: "Mock AI planning",
    deterministic_fallback: "Deterministic fallback",
    deterministic_only: "Deterministic safety policy",
  }[mode] || "Not recorded";
}

function runStatusLabel(status) {
  return {
    created: "Case created",
    planning: "Investigating",
    investigating: "Investigating",
    verifying: "Investigating",
    pending_human_review: "Awaiting Human Review",
    needs_more_evidence: "More Evidence Required",
    pr_created: "Remediation PR Created",
    failed_safely: "Failed safely",
    rejected: "Recommendation Rejected",
    approved: "Approved",
    blocked: "Blocked by policy",
    keep: "No change recommended",
    abstained: "No recommendation",
  }[status] || labelFor(status || "no_case");
}

function githubIntegrationLabel(run) {
  if (run?.github_source) return "Real GitHub";
  return "Ready for GitHub webhooks";
}

function integrationLabel(run) {
  return run?.github_source ? "Real GitHub" : run ? "Fixture-backed" : "Not available";
}

function sourceKindLabel(run) {
  return run?.github_source ? "GitHub Pull Request" : run ? "Controlled Demo" : "No case loaded";
}

function currentResourceChange(run) {
  return run?.github_source?.resource_changes?.[0] || null;
}

function currentConfiguration(run) {
  const resource = currentResourceChange(run);
  return resource?.before?.instance_type || run?.mock_pr?.current_instance_type || "Not available";
}

function proposedConfiguration(run) {
  const resource = currentResourceChange(run);
  const preferred = preferredAlternative();
  return resource?.after?.instance_type || preferred?.proposed_instance_type || run?.mock_pr?.proposed_instance_type || "Not available";
}

function changeTypeLabel(resource) {
  if (!resource) return "Not available";
  if (resource.destructive || resource.replacement) return "High-risk change";
  if ((resource.actions || []).includes("create")) return "Resource creation";
  if ((resource.actions || []).includes("delete")) return "Resource deletion";
  return "Safe update";
}

function estimatedCostImpact(run) {
  const pricing = evidenceValue("pricing");
  if (!pricing) return "Not available";
  const delta = Number(pricing.proposed_monthly_cost || 0) - Number(pricing.current_monthly_cost || 0);
  if (delta === 0) return "$0/month";
  return `${delta > 0 ? "+" : "-"}${money(Math.abs(delta)).replace("$", "$")}/month`;
}

function plainRecommendationTitle(run) {
  const preferred = preferredAlternative();
  const decision = run?.decision_record;
  if (!decision) return "Waiting for review";
  if (decision.policy_result?.status === "blocked") return "Blocked by Production Policy";
  if (decision.policy_result?.status === "needs_human_context" || run?.status === "needs_more_evidence") return "More Evidence Required";
  if (preferred?.action === "keep") return `Keep ${currentConfiguration(run)}`;
  if (preferred?.action === "downsize" && preferred.proposed_instance_type) return `Downsize to ${preferred.proposed_instance_type}`;
  return recommendationLabel(decision.preferred_action);
}

function fallbackText(value, fallback = "Not available") {
  return value === null || value === undefined || value === "" ? fallback : formatValue(value);
}

function selectedCaseTitle(run) {
  if (!run) return "Terraform PR Reviews";
  if (run.github_source) return `PR #${run.github_source.pull_request_number}: ${run.github_source.pull_request_title || "Terraform review"}`;
  return `${demoScenarioLabels[run.scenario_name] || labelFor(run.scenario_name)} demo case`;
}

function isDemoRun(run) {
  return run?.source_type === "manual_demo";
}

function hasSelectedCase() {
  return Boolean(state.run);
}

function selectedAssistantCaseId(context = state.assistantContext) {
  if (["pr_review", "technical_audit"].includes(context) && state.run?.id) return state.run.id;
  if (["cloud_hunt", "approvals"].includes(context) && state.selectedReviewContext?.runId) return state.selectedReviewContext.runId;
  if (state.run?.id && context !== "product_help") return state.run.id;
  return null;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || `${response.status} ${response.statusText}`;
    throw new Error(typeof detail === "string" ? detail : prettyValue(detail));
  }
  return payload;
}

function setMessage(id, message, success = false) {
  const node = $(id);
  node.textContent = message || "";
  node.style.color = success ? "var(--green)" : "var(--red)";
}

function showToast(title, detail = "", type = "success") {
  const region = $("toast-region");
  if (!region) return;
  const toast = el("div", `toast ${type}`);
  toast.setAttribute("role", "status");
  append(toast, el("strong", null, title), detail ? el("span", null, detail) : null);
  region.appendChild(toast);
  const timer = typeof window.setTimeout === "function" ? window.setTimeout.bind(window) : null;
  if (!timer) return;
  timer(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 4200);
}

function friendlyError(error, fallback = "Request failed. Try again.") {
  const message = error?.message || fallback;
  if (/traceback|stack|exception|file "/i.test(message)) return fallback;
  return message.length > 180 ? `${message.slice(0, 177)}...` : message;
}

async function withButtonState(buttonId, loadingLabel, work, successLabel = null) {
  const button = $(buttonId);
  const original = button.textContent;
  button.disabled = true;
  button.classList.add("is-loading");
  button.textContent = loadingLabel;
  try {
    const result = await work();
    if (successLabel) {
      button.textContent = successLabel;
      window.setTimeout(() => { button.textContent = original; }, 900);
    }
    return result;
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    if (!successLabel) button.textContent = original;
  }
}

function renderSkeletonList(node, count = 3) {
  clear(node);
  for (let index = 0; index < count; index += 1) node.appendChild(el("div", "skeleton"));
}

async function loadInitial() {
  state.loading.initial = true;
  renderAll();
  try {
    const [health, scenarios] = await Promise.all([api("/health"), api("/api/scenarios")]);
    $("api-pill").textContent = `System Online: ${health.status === "ok" ? "Yes" : labelFor(health.status)}`;
    state.scenarios = scenarios.scenarios || [];
    state.demoScenarios = state.scenarios.filter((scenario) => demoScenarioLabels[scenario]);
    renderScenarioOptions();
    setMessage("ui-message", "Ready for incoming reviews.", true);
  } catch (error) {
    $("api-pill").textContent = "System Online: No";
    const message = friendlyError(error, "API unavailable. Check the server and retry.");
    setMessage("ui-message", message);
    showToast("API unavailable", message, "error");
  } finally {
    state.loading.initial = false;
  }
  loadReviewQueue();
  renderAll();
}

async function loadReviewQueue() {
  state.loading.reviews = true;
  renderOverview();
  renderReviewQueue();
  try {
    state.reviews = await api("/api/reviews");
    renderReviewQueue();
  } catch (error) {
    const message = friendlyError(error, "Failed to load approval queue.");
    setMessage("cloud-hunt-message", message);
    showToast("Review load failed", message, "error");
  } finally {
    state.loading.reviews = false;
    renderOverview();
  }
}

async function startCloudHunt() {
  return withButtonState("start-cloud-hunt-button", "Scanning...", async () => {
    state.loading.cloudHunt = true;
    renderCloudHunt();
    setMessage("cloud-hunt-message", "Scanning fixture inventory...", true);
    state.hunt = await api("/api/cloud/hunts", { method: "POST", body: JSON.stringify({ provider_scope: $("cloud-provider-scope").value, inventory_source: "fixtures" }) });
    await loadReviewQueue();
    renderCloudHunt();
    setMessage("cloud-hunt-message", "Cloud Hunt completed. No cloud resource was changed.", true);
    showToast("Cloud Hunt completed", "No cloud resource was changed.", "success");
  }, "Scan complete").catch((error) => {
    const message = friendlyError(error, "Failed to complete Cloud Hunt.");
    setMessage("cloud-hunt-message", message);
    showToast("Cloud Hunt failed", message, "error");
  }).finally(() => {
    state.loading.cloudHunt = false;
    renderCloudHunt();
  });
}

function renderScenarioOptions() {
  const select = $("demo-scenario-select");
  clear(select);
  state.demoScenarios.forEach((scenario) => {
    const option = el("option", null, demoScenarioLabels[scenario] || scenario);
    option.value = scenario;
    select.appendChild(option);
  });
}

async function startRun() {
  return withButtonState("start-button", "Running demo...", async () => {
    state.loading.run = true;
    setMessage("demo-message", "Starting demo...", true);
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        goal: $("goal-input").value,
        scenario_name: $("demo-scenario-select").value,
        idempotency_key: `ui-${Date.now()}`,
      }),
    });
    state.run = run;
    state.selectedReviewContext = { source: "demo", runId: run.id };
    localStorage.setItem("ghostbusters:lastRunId", run.id);
    state.skipAnimation = $("skip-animation").checked;
    closeDemoModal();
    startAnimation();
    switchMode("simple");
    setMessage("ui-message", "Demo case loaded.", true);
    showToast("Demo started", "Prepared review evidence is loaded.", "success");
  }, "Demo loaded").catch((error) => {
    const message = friendlyError(error, "Failed to start demo.");
    setMessage("demo-message", message);
    showToast("Demo failed", message, "error");
  }).finally(() => {
    state.loading.run = false;
    renderOverview();
  });
}

async function refreshRun() {
  const runId = state.run?.id || localStorage.getItem("ghostbusters:lastRunId");
  if (!runId) {
    loadReviewQueue();
    return setMessage("ui-message", "Reviews refreshed.");
  }
  return withButtonState(state.activeMode === "overview" ? "overview-refresh-button" : "refresh-button", "Refreshing...", async () => {
    state.run = await api(`/api/runs/${runId}`);
    startAnimation(true);
    setMessage("ui-message", "Current review refreshed.", true);
    showToast("Review loaded", "Current case data refreshed.", "success");
  }).catch((error) => {
    const message = friendlyError(error, "Failed to load review.");
    setMessage("ui-message", message);
    showToast("Review load failed", message, "error");
  });
}

async function resetDemo() {
  try {
    await api("/api/reset", { method: "POST", body: "{}" });
    window.clearInterval(state.animationTimer);
    state.run = null;
    state.selectedReviewContext = null;
    state.visibleEvents = [];
    localStorage.removeItem("ghostbusters:lastRunId");
    closeReviewForm();
    closeDemoModal();
    renderAll();
    setMessage("ui-message", "Demo reset.", true);
    showToast("Demo reset", "Workspace returned to an empty review state.", "success");
  } catch (error) {
    const message = friendlyError(error, "Failed to reset demo.");
    setMessage("ui-message", message);
    showToast("Reset failed", message, "error");
  }
}

function openDemoModal() {
  $("demo-modal-backdrop").hidden = false;
  setMessage("demo-message", "");
}

function closeDemoModal() {
  $("demo-modal-backdrop").hidden = true;
}

function startAnimation(showAll = false) {
  window.clearInterval(state.animationTimer);
  const events = state.run?.audit_events || [];
  state.visibleEvents = state.skipAnimation || showAll ? [...events] : [];
  renderAll();
  if (state.visibleEvents.length === events.length) return;
  state.animationTimer = window.setInterval(() => {
    if (state.paused) return;
    const next = events[state.visibleEvents.length];
    if (!next) {
      window.clearInterval(state.animationTimer);
      renderAll();
      return;
    }
    state.visibleEvents.push(next);
    renderAll();
  }, 420);
}

function stageForEvent(event) {
  return stageDefinitions.find((stage) =>
    stage.matches?.includes(event.event_type) || stage.prefix?.some((prefix) => event.event_type.startsWith(prefix))
  );
}

function renderStages() {
  const list = $("stage-list");
  clear(list);
  const visible = state.visibleEvents;
  const allEvents = state.run?.audit_events || [];
  let lastCompleted = -1;
  stageDefinitions.forEach((stage, index) => {
    if (visible.some((event) => stageForEvent(event)?.id === stage.id)) lastCompleted = index;
  });
  stageDefinitions.forEach((stage, index) => {
    const events = visible.filter((event) => stageForEvent(event)?.id === stage.id);
    const allStageEvents = allEvents.filter((event) => stageForEvent(event)?.id === stage.id);
    let stageState = "pending";
    if (events.length && events.length === allStageEvents.length) stageState = "complete";
    if (index === lastCompleted && visible.length < allEvents.length) stageState = "active";
    if (stage.id === "recommended" && state.run?.status === "blocked") stageState = "blocked";
    if (["human", "recommended"].includes(stage.id) && ["needs_more_evidence", "abstained"].includes(state.run?.status)) stageState = "warning";
    if (stage.id === "remediation" && state.run?.status === "pr_created") stageState = "complete";
    const item = el("li", `stage ${stageState}`);
    const stageStatusLabel = { pending: "Waiting", active: "Current", complete: "Complete", warning: "Needs attention", blocked: "Blocked" }[stageState];
    append(item, el("span", "stage-number", index + 1), el("strong", null, stage.title), el("p", null, stage.description), el("span", "stage-status", stageStatusLabel));
    list.appendChild(item);
  });
  renderCurrentAction(visible[visible.length - 1]);
}

function renderCurrentAction(event) {
  if (!event) {
    $("current-action").textContent = "No case loaded";
    $("current-reason").textContent = "Open a review from Approvals or launch a demo.";
    $("current-output").textContent = "Waiting";
    $("current-next").textContent = "Open Approvals";
    return;
  }
  const stage = stageForEvent(event);
  $("current-action").textContent = event.summary || labelFor(event.event_type);
  $("current-reason").textContent = stage?.description || "This action is part of the recorded workflow.";
  $("current-output").textContent = conciseEventResult(event);
  $("current-next").textContent = nextStageText(stage?.id);
}

function conciseEventResult(event) {
  const details = event.details || {};
  if (details.status) return `Status: ${labelFor(details.status)}`;
  if (details.allowed !== undefined) return details.allowed ? "Policy allowed review." : "Policy blocked remediation.";
  if (details.failure_category) return `Failed safely: ${labelFor(details.failure_category)}`;
  return event.summary || "Recorded";
}

function nextStageText(stageId) {
  const index = stageDefinitions.findIndex((stage) => stage.id === stageId);
  if (index >= 0 && index < stageDefinitions.length - 1) return stageDefinitions[index + 1].title;
  return finalOutcome(state.run);
}

function evidenceItem(source) {
  return (state.run?.decision_record?.evidence || []).find((item) => item.source === source);
}

function evidenceValue(source) {
  return evidenceItem(source)?.value;
}

function preferredAlternative() {
  const decision = state.run?.decision_record;
  return (decision?.alternatives || []).find((item) => item.action === decision.preferred_action);
}

function evidenceSummary(source, item) {
  if (!item || item.freshness_status === "unavailable" || item.value === null) {
    return { title: labelFor(source), detail: "Evidence unavailable", conclusion: item?.claim || "Source did not return evidence" };
  }
  const value = item.value;
  if (source === "pricing") return { title: "Pricing", detail: `Current option costs ${money(value.current_monthly_cost)}/month`, conclusion: `Recommended option costs ${money(value.proposed_monthly_cost)}/month` };
  if (source === "utilization") {
    const headroom = Number(value.peak_cpu_pct) < 60;
    return { title: "Utilization", detail: `Average CPU is ${formatValue(value.average_cpu_pct)}%`, conclusion: `Peak CPU is ${formatValue(value.peak_cpu_pct)}%` };
  }
  if (source === "jira") return { title: "Jira", detail: `${formatValue(value.issue_key)} is ${labelFor(value.status)}`, conclusion: String(value.status).toLowerCase() === "completed" ? "Project appears completed" : "Project remains active or under review" };
  if (source === "git_activity") return { title: "Git activity", detail: `${formatValue(value.recent_commit_count)} recent commits were found`, conclusion: `Last commit was ${formatValue(value.days_since_last_commit)} days ago` };
  if (source === "dependencies") {
    const dependencies = value.active_downstream_dependencies || value.blocking_services || [];
    return { title: "Dependencies", detail: dependencies.length ? `Active dependencies: ${formatValue(dependencies)}` : "No active dependencies were found", conclusion: dependencies.length ? "Automatic remediation may be unsafe" : "No dependency blocker was found" };
  }
  return { title: labelFor(source), detail: item.claim, conclusion: formatValue(value) };
}

function renderEvidenceSummary() {
  const node = $("evidence-summary-view");
  clear(node);
  const evidence = state.run?.decision_record?.evidence || [];
  const badge = $("evidence-mode-badge");
  badge.hidden = state.run?.source_type !== "manual_demo";
  const bullets = [];
  evidence.filter((item) => toolNames.includes(item.source)).forEach((item) => {
    const summary = evidenceSummary(item.source, item);
    bullets.push(summary.detail);
    bullets.push(summary.conclusion);
  });
  const uniqueBullets = bullets.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index).slice(0, 5);
  $("evidence-count").textContent = `${uniqueBullets.length} bullet${uniqueBullets.length === 1 ? "" : "s"}`;
  if (!uniqueBullets.length) {
    node.appendChild(el("p", "muted", state.run ? "Evidence is still being gathered." : "Evidence bullets appear after a review starts."));
  } else {
    uniqueBullets.forEach((text) => {
      const signal = el("div", "signal");
      append(signal, el("strong", null, text));
      node.appendChild(signal);
    });
  }
  const findings = state.run?.decision_record?.verifier_findings || [];
  const passed = findings.filter((item) => item.status === "passed").length;
  const warnings = findings.filter((item) => item.status === "warning").length;
  const failed = findings.filter((item) => item.status === "failed").length;
  const checkSummary = findings.length ? `${findings.length} safety checks completed: ${passed} passed, ${warnings} warnings, ${failed} failed.` : "No safety checks recorded yet.";
  const policy = state.run?.decision_record?.policy_result;
  $("safety-summary").textContent = policy ? `${checkSummary} ${policySummary(policy)}` : checkSummary;
  const calls = (state.run?.decision_record?.tool_executions || []).filter((item) => item.external_call);
  const incidents = calls.filter((item) => !item.external_call.success || item.external_call.attempts > 1);
  $("resilience-summary").textContent = !calls.length
    ? "No external evidence calls recorded yet."
    : incidents.length
      ? `${incidents.length} evidence call${incidents.length === 1 ? " required" : "s required"} retry or safe fallback handling.`
      : "All external evidence calls succeeded on the first attempt.";
}

function recommendationReason(decision, preferred) {
  const highConflicts = (decision?.conflicts || []).filter((item) => item.severity === "high");
  if (highConflicts.length) return `${highConflicts.length} high-risk conflict${highConflicts.length === 1 ? " remains" : "s remain"}: ${highConflicts.map((item) => item.explanation).join(" ")}`;
  if (decision?.missing_evidence?.length) return `GhostBusters needs more evidence before it can recommend a safe remediation.`;
  return preferred?.description || decision?.final_summary || "No recommendation recorded.";
}

function riskLevel(decision, preferred) {
  const severities = [...(decision?.conflicts || []).map((item) => item.severity), ...(decision?.verifier_findings || []).filter((item) => item.status !== "passed").map((item) => item.severity)];
  const order = ["info", "low", "medium", "high", "critical"];
  if (preferred?.risks?.length && !severities.length) return "Medium";
  return labelFor(severities.sort((a, b) => order.indexOf(b) - order.indexOf(a))[0] || "low");
}

function nextHumanAction(run) {
  if (!run) return "Start a review";
  if (run.status === "pending_human_review") return "Approve, modify, request evidence, or reject";
  if (run.status === "needs_more_evidence") return "Add business context or request updated evidence";
  if (run.status === "blocked") return "Add context where supported; approval is unavailable";
  if (run.status === "pr_created") return "Review the remediation pull request";
  if (run.status === "rejected") return "Review closed by human rejection";
  return "Review the recorded outcome";
}

function renderRecommendation() {
  const decision = state.run?.decision_record;
  const preferred = preferredAlternative();
  $("recommendation-title").textContent = plainRecommendationTitle(state.run);
  $("recommendation-reason").textContent = decision ? recommendationReason(decision, preferred) : "The recommendation will appear here after GhostBusters completes its investigation.";
  $("recommendation-confidence").textContent = percentage(decision?.confidence?.final_confidence);
  $("recommendation-risk").textContent = decision ? riskLevel(decision, preferred) : "--";
  $("recommendation-policy").textContent = decision ? policyStatusLabel(decision.policy_result?.status) : "--";
  $("recommendation-policy-technical").textContent = "";
  $("recommendation-savings").textContent = preferred ? `${money(preferred.estimated_monthly_savings)}/month` : "--";
  $("recommendation-annual-savings").textContent = preferred ? `${money(preferred.estimated_annual_savings)}/year` : "--";
  $("recommendation-next").textContent = nextHumanAction(state.run);
  const alternativesNode = $("important-alternatives");
  clear(alternativesNode);
  const alternatives = (decision?.alternatives || []).filter((item) => item.action !== decision.preferred_action).slice(0, 2);
  alternatives.forEach((item) => {
    const note = el("div", "alternative-note");
    const reason = item.eligible
      ? item.description
      : item.rejection_reasons?.[0] || item.risks?.[0] || "Not eligible under current evidence.";
    append(note, el("strong", null, `${recommendationLabel(item.action)} - ${item.eligible ? "eligible" : "rejected"}`), el("span", null, reason));
    alternativesNode.appendChild(note);
  });
}

function renderPlanningStatus() {
  const mode = state.run?.decision_record?.planning_mode || "deterministic_only";
  $("planning-badge").textContent = isDemoRun(state.run) ? "Demo Case" : "GitHub Review";
  if (mode === "gemini_primary" || mode === "gemini_fallback_model") {
    $("planning-note").textContent = "AI-assisted planning was used for this case. Deterministic safety checks remained in control.";
  } else if (mode === "mock_gemini") {
    $("planning-note").textContent = "Mock AI planning was used for demonstration only.";
  } else if (mode === "deterministic_fallback") {
    $("planning-note").textContent = "AI planning was unavailable, so GhostBusters continued with deterministic review logic.";
  } else {
    $("planning-note").textContent = isDemoRun(state.run) ? "Prepared fixtures are backing this demo case." : "";
  }
}

function allowedReviewActions(status) {
  if (status === "pending_human_review") return ["approve", "modify", "request_evidence", "reject"];
  if (status === "needs_more_evidence") return ["add_context", "request_evidence", "reject"];
  if (status === "abstained") return ["add_context", "request_evidence"];
  if (status === "blocked" || status === "keep" || status === "failed_safely") return ["add_context"];
  return [];
}

function renderHumanControls() {
  const status = state.run?.status;
  const allowed = allowedReviewActions(status);
  const human = humanDecision(state.run);
  $("human-decision").textContent = human.label;
  $("human-decision-technical").textContent = human.technical;
  document.querySelectorAll("[data-review-action]").forEach((button) => {
    const visible = allowed.includes(button.dataset.reviewAction);
    button.hidden = !visible;
    button.disabled = !visible;
  });
  const humanQuestion = state.run?.decision_record?.human_question;
  $("review-guidance").textContent = humanQuestion
    ? humanQuestion
    : !state.run
    ? "Start a review to see the actions permitted by this case."
    : status === "blocked"
      ? "This case is blocked. Approval and remediation controls are unavailable."
      : status === "needs_more_evidence"
        ? "The recommendation is not ready for approval. Add context or request missing evidence."
        : status === "pending_human_review"
          ? "A human reviewer can decide whether GhostBusters should create a remediation pull request."
        : allowed.length ? "Human input can refine the recorded decision." : "No further review action is available in this state.";
  if (state.selectedReviewAction && !allowed.includes(state.selectedReviewAction)) closeReviewForm();
}

function humanDecision(run) {
  const latest = run?.human_reviews?.[run.human_reviews.length - 1];
  if (!latest) {
    return {
      label: run?.status === "pending_human_review" ? "Awaiting a reviewer" : "Not made",
      technical: "No review recorded",
    };
  }
  const reviewer = latest.reviewer || "reviewer";
  const labels = {
    approve: `Approved by ${reviewer}`,
    reject: `Rejected by ${reviewer}`,
    request_evidence: `More evidence requested by ${reviewer}`,
    add_context: `Context added by ${reviewer}`,
    modify: `Recommendation modified by ${reviewer}`,
  };
  return { label: labels[latest.action] || labelFor(latest.action), technical: `Review action: ${latest.action}` };
}

function selectReviewAction(action) {
  state.selectedReviewAction = action;
  $("review-form").hidden = false;
  $("review-form-title").textContent = labelFor(action);
  $("sources-field").hidden = action !== "request_evidence";
  $("context-field").hidden = action !== "add_context";
  $("modify-field").hidden = action !== "modify";
  $("submit-review-button").textContent = action === "approve" ? "Approve Remediation" : action === "reject" ? "Confirm rejection" : "Submit";
  $("review-form").scrollIntoView({ block: "nearest" });
}

function closeReviewForm() {
  state.selectedReviewAction = null;
  $("review-form").hidden = true;
}

async function submitSelectedReview() {
  const action = state.selectedReviewAction;
  if (!action || !state.run) return;
  const payload = { action, reviewer: $("reviewer-input").value || "judge", comment: $("comment-input").value || null };
  if (action === "request_evidence") payload.requested_sources = $("requested-sources").value.split(",").map((item) => item.trim()).filter(Boolean);
  if (action === "add_context") payload.human_context = $("human-context").value || null;
  if (action === "modify") payload.modified_action = $("modified-action").value || null;
  return withButtonState("submit-review-button", action === "approve" ? "Creating PR..." : "Submitting...", async () => {
    state.loading.review = true;
    state.run = await api(`/api/runs/${state.run.id}/review`, { method: "POST", body: JSON.stringify(payload) });
    closeReviewForm();
    startAnimation(true);
    setMessage("review-message", `${labelFor(action)} accepted by the backend.`, true);
    showToast(action === "approve" ? "Remediation PR created" : "Approval recorded", `${labelFor(action)} accepted by the backend.`, "success");
  }, "Recorded").catch((error) => {
    const message = friendlyError(error, "Failed to record approval.");
    setMessage("review-message", message);
    showToast("Approval failed", message, "error");
  }).finally(() => {
    state.loading.review = false;
    renderOverview();
  });
}

function finalOutcome(run) {
  return {
    pr_created: run?.real_pr ? "Real Remediation PR Created" : "Simulated Remediation PR Created",
    rejected: "Recommendation Rejected",
    needs_more_evidence: "More Evidence Requested",
    blocked: "Blocked by Policy",
    failed_safely: "Remediation PR Creation Failed Safely",
    pending_human_review: "Awaiting Human Approval",
    abstained: "More Evidence Required",
    keep: "No change recommended",
  }[run?.status] || "Awaiting Human Approval";
}

function renderResult() {
  const node = $("result-view");
  clear(node);
  $("result-title").textContent = finalOutcome(state.run);
  node.appendChild(el("div", "result-state", finalOutcome(state.run)));
  const real = state.run?.real_pr;
  if (real?.url) {
    const summary = el("div", "pr-summary");
    [["Result", "Real remediation pull request"], ["PR", `#${real.number}`], ["Remediation branch", real.branch], ["Target branch", real.base_branch], ["Repository", real.repository]].forEach(([label, value]) => { const item = el("div"); append(item, el("span", null, label), el("strong", null, value)); summary.appendChild(item); });
    const link = el("a", "github-link", "Open in GitHub"); link.href = real.url; link.target = "_blank"; link.rel = "noopener noreferrer";
    append(node, summary, link);
    return;
  }
  const pr = state.run?.mock_pr;
  if (!pr) {
    node.appendChild(el("p", "muted", state.run ? "No remediation pull request has been created." : "Start a review to see the final workflow outcome."));
    return;
  }
  const layout = el("div", "result-grid");
  const summary = el("div", "pr-summary");
  [["PR", `#${pr.pr_number}`], ["Action", recommendationLabel(pr.chosen_action)], ["Remediation branch", pr.branch], ["Savings", `${money(pr.monthly_savings)}/month | ${money(pr.annual_savings)}/year`], ["Current configuration", pr.current_instance_type], ["Recommended configuration", pr.proposed_instance_type]].forEach(([label, value]) => {
    const item = el("div"); append(item, el("span", null, label), el("strong", null, value)); summary.appendChild(item);
  });
  const diff = el("pre"); diff.textContent = pr.terraform_patch_preview || "Not recorded";
  append(layout, summary, diff); node.appendChild(layout);
  node.appendChild(el("p", "muted", "Simulated remediation PR. No GitHub change was made."));
}

function renderSource() {
  const run = state.run;
  const source = run?.github_source;
  const change = currentResourceChange(run);
  const sourceLink = $("source-pr-link");
  $("start-title").textContent = selectedCaseTitle(run);
  $("case-badge").textContent = isDemoRun(run) ? "Demo Case" : "PR Review";
  $("source-kind").textContent = sourceKindLabel(run);
  $("source-repository").textContent = source?.repository || "Not available";
  $("source-pr").textContent = source ? `#${source.pull_request_number}` : "Prepared scenario";
  $("source-title").textContent = source?.pull_request_title || (run ? demoScenarioLabels[run.scenario_name] || labelFor(run.scenario_name) : "Not available");
  $("source-head").textContent = source?.head_branch || "Not available";
  $("source-base").textContent = source?.base_branch || "Not available";
  $("source-integration").textContent = integrationLabel(run);
  sourceLink.hidden = !source?.pull_request_url;
  sourceLink.href = source?.pull_request_url || "#";
  $("change-resource").textContent = change?.address || run?.decision_record?.resource_id || "Not available";
  $("change-before").textContent = currentConfiguration(run);
  $("change-after").textContent = proposedConfiguration(run);
  $("change-provider").textContent = change?.provider || source?.provider || "Not available";
  $("change-file").textContent = change?.source_file || source?.terraform_files?.[0] || "Not available";
  $("change-environment").textContent = source?.environment || change?.environment || "Not available";
  $("change-type").textContent = changeTypeLabel(change);
  $("change-cost-impact").textContent = estimatedCostImpact(run);
  $("change-impact-badge").textContent = run ? estimatedCostImpact(run) : "No change loaded";
}

function renderStatus() {
  const run = state.run;
  $("run-pill").textContent = `GitHub Integration: ${githubIntegrationLabel(run)}`;
  $("api-pill").textContent = $("api-pill").textContent || "System Online: Yes";
  $("approval-pill").textContent = "Demo Environment: Active";
  $("demo-pill-chip").hidden = !isDemoRun(run);
  $("technical-run-id").textContent = `Run ID: ${run?.id || "not recorded"}`;
  $("trigger-source").textContent = run?.github_source ? "Source: GitHub Pull Request" : run ? "Source: Controlled Demo" : "Webhook not yet received or no demo case started.";
  $("case-status").textContent = runStatusLabel(run?.status);
  $("human-decision-summary").textContent = humanDecision(run).label;
  $("recommendation-summary").textContent = plainRecommendationTitle(run);
  $("evidence-source-card").hidden = !isDemoRun(run);
}

function renderAudit() {
  const node = $("audit-view"); clear(node);
  const events = state.run?.audit_events || [];
  $("audit-count").textContent = `${events.length} events`;
  if (!events.length) return node.appendChild(el("p", "muted", "No audit events yet."));
  events.forEach((event) => {
    const row = el("div", "audit-row");
    const details = el("details", "raw-details");
    append(details, el("summary", null, "Inspect"), dataList([["Timestamp", event.timestamp], ["Actor", event.actor], ["Event type", event.event_type], ["Interpretation", event.summary], ["Next stage", nextStageText(stageForEvent(event)?.id)]]), rawDetails("Input and output", event.details || {}));
    append(row, el("span", "audit-sequence", event.sequence_number), el("strong", null, labelFor(event.event_type)), el("span", null, event.summary), details);
    node.appendChild(row);
  });
}

function renderPlan() {
  const node = $("plan-view"); clear(node);
  const plan = state.run?.decision_record?.investigation_plan;
  if (!plan) return node.appendChild(el("p", "muted", "No investigation plan yet."));
  append(node, dataList([["Objective", plan.goal], ["Resource", plan.resource_id], ["Selected tools", plan.selected_tools], ["Skipped tools", plan.skipped_tools]]), rawDetails("Planning notes", plan.planning_notes));
  const grid = el("div", "technical-grid");
  (plan.questions || []).forEach((question) => {
    const card = el("article", `info-card ${statusClass(question.status)}`);
    append(card, el("h3", null, question.question), dataList([["Required sources", question.required_evidence_sources], ["Status", question.status], ["Resolution", question.resolution_summary]]));
    grid.appendChild(card);
  });
  node.appendChild(grid);
}

function renderTools() {
  const node = $("tool-panel"); clear(node);
  const plan = state.run?.decision_record?.investigation_plan || {};
  const records = state.run?.decision_record?.tool_executions || [];
  toolNames.forEach((name) => {
    const record = records.find((item) => item.tool_name === name);
    const skipped = (plan.skipped_tools || []).includes(name);
    const card = el("article", `info-card ${statusClass(record?.status || (skipped ? "skipped" : "unknown"))}`);
    append(card, el("h3", null, labelFor(name)), dataList([["Status", record?.status || (skipped ? "skipped" : "Not recorded")], ["Why selected", record?.selected_because], ["Input", record?.input_summary], ["Output", record?.output_summary], ["Error", record?.error], ["Attempts", record?.external_call?.attempts], ["Elapsed", record?.external_call ? `${record.external_call.elapsed_ms} ms` : null]]));
    if (record?.external_call) card.appendChild(rawDetails("External call record", record.external_call));
    node.appendChild(card);
  });
}

function renderTerraform() {
  const node = $("terraform-view"); clear(node);
  const decision = state.run?.decision_record;
  const pricing = evidenceValue("pricing") || {};
  const preferred = preferredAlternative() || {};
  append(node, dataList([["Resource ID", decision?.resource_id], ["Environment", "Not recorded in run response"], ["Terraform actions", "Not recorded in run response"], ["Destructive flag", "Not recorded in run response"], ["Current instance type", state.run?.mock_pr?.current_instance_type], ["Proposed instance type", preferred.proposed_instance_type], ["Current monthly cost", money(pricing.current_monthly_cost)], ["Proposed monthly cost", money(pricing.proposed_monthly_cost)]]));
  if (state.run?.mock_pr?.terraform_patch_preview) { const pre = el("pre"); pre.textContent = state.run.mock_pr.terraform_patch_preview; node.appendChild(pre); }
}

function renderEvidence() {
  const node = $("evidence-view"); clear(node);
  const evidence = state.run?.decision_record?.evidence || [];
  if (!evidence.length) return node.appendChild(el("p", "muted", "No evidence collected yet."));
  evidence.forEach((item) => {
    const card = el("article", `info-card ${statusClass(item.freshness_status)}`);
    append(card, el("h3", null, labelFor(item.source)), dataList([["Claim", item.claim], ["Value", item.value], ["Freshness", item.freshness_status], ["Reliability", item.reliability], ["Resource ID", item.resource_id]]), rawDetails("Metadata", item.metadata || {}));
    node.appendChild(card);
  });
}

function renderConflicts() {
  const conflictNode = $("conflicts-view"); const missingNode = $("missing-view"); clear(conflictNode); clear(missingNode);
  conflictNode.appendChild(el("h3", null, "Conflicts")); missingNode.appendChild(el("h3", null, "Missing evidence"));
  const conflicts = state.run?.decision_record?.conflicts || [];
  const missing = state.run?.decision_record?.missing_evidence || [];
  if (!conflicts.length) conflictNode.appendChild(el("p", "muted", "No conflicts detected."));
  conflicts.forEach((item) => conflictNode.appendChild(append(el("article", `info-card ${statusClass(item.severity)}`), dataList([["Claim", item.claim], ["Sources", item.sources], ["Values", item.values], ["Severity", item.severity], ["Explanation", item.explanation]]))));
  if (!missing.length) missingNode.appendChild(el("p", "muted", "No missing evidence."));
  missing.forEach((item) => missingNode.appendChild(append(el("article", `info-card ${item.critical ? "status-critical" : "status-warning"}`), dataList([["Source", item.source], ["Claim needed", item.claim_needed], ["Critical", item.critical], ["Impact", item.impact]]))));
}

function renderAlternatives() {
  const node = $("alternatives-view"); clear(node);
  const decision = state.run?.decision_record;
  (decision?.alternatives || []).forEach((item) => {
    const card = el("article", `info-card ${item.action === decision.preferred_action ? "preferred" : ""}`);
    append(card, el("h3", null, `${labelFor(item.action)}${item.action === decision.preferred_action ? " - preferred" : ""}`), dataList([["Description", item.description], ["Eligible", item.eligible], ["Score", Number(item.score).toFixed(2)], ["Monthly cost", money(item.estimated_monthly_cost)], ["Monthly savings", money(item.estimated_monthly_savings)], ["Annual savings", money(item.estimated_annual_savings)], ["Supporting evidence", item.supporting_evidence], ["Risks", item.risks], ["Assumptions", item.assumptions], ["Rejection reasons", item.rejection_reasons]]));
    node.appendChild(card);
  });
  if (!decision?.alternatives?.length) node.appendChild(el("p", "muted", "Not recorded"));
}

function renderVerifier() {
  const node = $("verifier-view"); clear(node);
  const findings = state.run?.decision_record?.verifier_findings || [];
  findings.forEach((item) => node.appendChild(append(el("article", `info-card ${statusClass(item.status)}`), el("h3", null, labelFor(item.check_name)), dataList([["Status", item.status], ["Severity", item.severity], ["Explanation", item.explanation], ["Evidence sources", item.evidence_sources]]))));
  if (!findings.length) node.appendChild(el("p", "muted", "Not recorded"));
}

function policySummary(policy) {
  if (!policy) return "Not recorded";
  if (policy.fallback_reason) return `Deterministic Python fallback used safely: ${policy.fallback_reason}`;
  if (!policy.allowed) return policy.blocking_reasons?.[0] || "Policy blocked remediation.";
  return policy.requires_human_approval ? "Policy allows review only after human approval." : "Policy allowed this outcome.";
}

function renderPolicy() {
  const node = $("policy-view"); clear(node);
  const policy = state.run?.decision_record?.policy_result;
  if (!policy) return node.appendChild(el("p", "muted", "Not recorded"));
  append(node, dataList([["Result", policySummary(policy)], ["Engine", policy.engine], ["Version", policy.policy_version], ["Allowed", policy.allowed], ["Status", policy.status], ["Human approval required", policy.requires_human_approval], ["Blocking reasons", policy.blocking_reasons], ["Warnings", policy.warnings], ["Evaluated rules", policy.evaluated_rules], ["Fallback reason", policy.fallback_reason]]), rawDetails("Structured violations", policy.violations || []));
}

function renderResilience() {
  const node = $("resilience-view"); clear(node);
  const calls = (state.run?.decision_record?.tool_executions || []).filter((item) => item.external_call);
  const incidents = calls.filter((item) => !item.external_call.success || item.external_call.attempts > 1 || item.external_call.retry_exhausted);
  if (calls.length && !incidents.length) node.appendChild(el("p", "muted", "All external evidence calls succeeded on the first attempt."));
  if (!calls.length) node.appendChild(el("p", "muted", "No retry was needed."));
  incidents.forEach((item) => node.appendChild(append(el("article", `info-card ${statusClass(item.status)}`), el("h3", null, labelFor(item.tool_name)), dataList([["Attempts", item.external_call.attempts], ["Succeeded", item.external_call.success], ["Retries exhausted", item.external_call.retry_exhausted], ["Failure", item.external_call.failure_category], ["Safe message", item.external_call.safe_message]]), rawDetails("Retry events", item.external_call.events))));
}

function renderHistory() {
  const node = $("history-view"); clear(node);
  const reviews = state.run?.human_reviews || [];
  reviews.forEach((item) => node.appendChild(append(el("article", "info-card"), dataList([["Reviewer", item.reviewer], ["Action", item.action], ["Comment", item.comment], ["Requested sources", item.requested_sources], ["Modified action", item.modified_action], ["Human context", item.human_context], ["Created", item.created_at]]))));
  if (!reviews.length) node.appendChild(el("p", "muted", "No human intervention recorded."));
}

function renderImpact() {
  const node = $("impact-view"); clear(node);
  const pricing = evidenceValue("pricing") || {};
  const preferred = preferredAlternative() || {};
  node.appendChild(dataList([["Current monthly cost", money(pricing.current_monthly_cost)], ["Proposed monthly cost", money(pricing.proposed_monthly_cost || preferred.estimated_monthly_cost)], ["Monthly savings", money(preferred.estimated_monthly_savings)], ["Annual savings", money(preferred.estimated_annual_savings)], ["Confidence", percentage(state.run?.decision_record?.confidence?.final_confidence)], ["Risk", preferred.risks], ["Run status", state.run?.status]]));
}

function renderRuntime() {
  const node = $("runtime-view"); clear(node);
  node.appendChild(dataList([["Run ID", state.run?.id], ["Version", state.run?.version], ["Scenario fixture", state.run?.scenario_name], ["Trigger source", state.run?.source_type], ["Repository", state.run?.github_source?.repository], ["Pull request", state.run?.github_source?.pull_request_number], ["Head SHA", state.run?.github_source?.head_sha], ["Idempotency key", state.run?.idempotency_key], ["Policy engine", state.run?.decision_record?.policy_result?.engine], ["Real remediation URL", state.run?.real_pr?.url]]));
}

function renderTechnical() {
  $("technical-empty-state").hidden = hasSelectedCase();
  $("technical-content").hidden = !hasSelectedCase();
  if (!hasSelectedCase()) return;
  renderAudit(); renderAIDecisions(); renderPlan(); renderTools(); renderTerraform(); renderEvidence(); renderConflicts(); renderAlternatives(); renderVerifier(); renderPolicy(); renderResilience(); renderHistory(); renderImpact(); renderRuntime();
}

function renderAIDecisions() {
  const node = $("ai-decisions-view"); clear(node);
  const decisions = state.run?.decision_record?.ai_decisions || [];
  if (!decisions.length) return node.appendChild(el("p", "muted", "No AI planning decisions recorded."));
  decisions.forEach((item) => {
    const action = item.proposed_action;
    const card = el("article", `info-card ${item.accepted ? "status-completed" : "status-failed"}`);
    append(card, el("h3", null, `${labelFor(item.purpose)} - ${item.accepted ? "accepted" : "rejected"}`), dataList([
      ["Model", item.model], ["Planning mode", planningModeLabel(item.planning_mode)], ["Action", action?.action], ["Tool", action?.tool_name], ["Reason", action?.reason], ["Question", action?.question_being_answered], ["Expected information", action?.expected_information], ["Validation", item.validation_result], ["Latency", item.latency_ms === null ? null : `${item.latency_ms} ms`], ["Fallback reason", item.fallback_reason], ["Error category", item.error_category],
    ]), rawDetails("Usage metadata", item.usage_metadata || {}));
    node.appendChild(card);
  });
}

function reviewSavings(item) {
  return Number(item?.estimated_monthly_savings || 0);
}

function currentRunSavings() {
  const preferred = preferredAlternative();
  return Number(preferred?.estimated_monthly_savings || state.run?.mock_pr?.monthly_savings || 0);
}

function overviewReviews() {
  const rows = [...state.reviews];
  if (state.run?.id && !rows.some((item) => item.id === state.run.id)) {
    rows.unshift({
      id: state.run.id,
      source_type: state.run.source_type || "terraform_pr",
      repository: state.run.github_source?.repository || state.run.mock_pr?.repository || "Demo review",
      pull_request_number: state.run.github_source?.pull_request_number || state.run.mock_pr?.pr_number,
      resource_name: state.run.decision_record?.resource_id,
      recommendation: plainRecommendationTitle(state.run),
      recommendation_reason: recommendationReason(state.run.decision_record, preferredAlternative()),
      confidence: state.run.decision_record?.confidence?.final_confidence,
      estimated_monthly_savings: currentRunSavings(),
      policy_status: state.run.decision_record?.policy_result?.status,
      status: state.run.status,
    });
  }
  return rows;
}

function renderOverviewSummary() {
  const node = $("overview-summary");
  if (!node) return;
  clear(node);
  if (state.loading.initial || state.loading.reviews) return renderSkeletonList(node, 4);
  const rows = overviewReviews();
  const openPrs = rows.filter((item) => item.source_type === "terraform_pr" || item.repository).length;
  const cloudFindings = state.hunt?.summary?.candidates ?? rows.filter((item) => item.source_type === "cloud_hunt").length;
  const awaitingApproval = rows.filter((item) => ["pending", "pending_human_review", "needs_more_evidence", "abstained"].includes(item.status)).length;
  const savings = state.hunt?.summary?.estimated_monthly_waste ?? rows.reduce((total, item) => total + reviewSavings(item), 0);
  [
    ["Open PR Reviews", openPrs || "0", rows.length ? "Reviews with recorded context" : "No reviews loaded yet", "teal"],
    ["Cloud Hunt Findings", cloudFindings || "0", state.hunt ? "From the latest inventory scan" : "Run Cloud Hunt to populate", "green"],
    ["Awaiting Approval", awaitingApproval || "0", awaitingApproval ? "Needs human attention" : "No approval alerts", "amber"],
    ["Potential Monthly Savings", savings ? money(savings) : "Not recorded", savings ? "Based on available evidence" : "Unavailable until evidence exists", "blue"],
  ].forEach(([label, value, helper, tone]) => {
    const card = el("article", "panel summary-card");
    card.dataset.tone = tone;
    append(card, el("span", null, label), el("strong", null, value), el("small", null, helper));
    node.appendChild(card);
  });
}

function renderOverviewRows() {
  const reviewNode = $("overview-pr-list");
  const alertsNode = $("overview-approval-alerts");
  if (!reviewNode || !alertsNode) return;
  if (state.loading.reviews) {
    renderSkeletonList(reviewNode, 3);
    renderSkeletonList(alertsNode, 2);
    return;
  }
  clear(reviewNode);
  clear(alertsNode);
  const rows = overviewReviews();
  const prRows = rows.filter((item) => item.source_type === "terraform_pr" || item.repository).slice(0, 5);
  if (!prRows.length) reviewNode.appendChild(el("p", "muted", "No PR reviews are loaded yet."));
  prRows.forEach((item) => {
    const row = el("article", "compact-row");
    const open = el("button", "secondary compact", "Open");
    open.type = "button";
    open.addEventListener("click", async () => {
      if (item.id) {
        state.run = await api(`/api/runs/${item.id}`);
        state.selectedReviewContext = { source: "overview", type: "terraform_pr", runId: item.id };
        startAnimation(true);
      }
      switchMode("simple");
      showToast("Review loaded", "Opened PR review details.", "success");
    });
    append(
      row,
      append(el("div"), el("strong", "row-title", item.repository || "Terraform review"), el("span", "row-meta", item.pull_request_number ? `PR #${item.pull_request_number}` : "Pull request not recorded"), el("span", "row-detail", item.resource_name || "Terraform change not recorded")),
      append(el("div", "row-metric"), el("span", null, "Recommendation"), el("strong", null, item.recommendation || "Not recorded")),
      append(el("div", "row-state"), el("span", null, "Status"), el("strong", null, runStatusLabel(item.status))),
      open
    );
    reviewNode.appendChild(row);
  });
  const alerts = rows.filter((item) => ["pending", "pending_human_review", "needs_more_evidence", "abstained"].includes(item.status)).slice(0, 4);
  if (!alerts.length) alertsNode.appendChild(el("p", "muted", "No cases currently require human approval."));
  alerts.forEach((item) => {
    const row = el("article", "alert-row");
    const open = el("button", "secondary compact", "Open Review");
    open.type = "button";
    open.addEventListener("click", () => switchMode("review-queue"));
    append(
      row,
      append(el("div"), el("strong", "row-title", item.resource_name || item.repository || "Review case"), el("span", "row-meta", policyStatusLabel(item.policy_status)), el("span", "row-detail", item.recommendation_reason || "Human approval is required before remediation.")),
      open
    );
    alertsNode.appendChild(row);
  });
}

function renderOverviewSavings() {
  const node = $("overview-savings-list");
  if (!node) return;
  if (state.loading.cloudHunt) return renderSkeletonList(node, 3);
  clear(node);
  const candidates = [...(state.hunt?.candidates || [])].sort((a, b) => Number(b.resource?.estimated_monthly_cost || 0) - Number(a.resource?.estimated_monthly_cost || 0)).slice(0, 4);
  if (!candidates.length) return node.appendChild(el("p", "muted", "Run Cloud Hunt to surface highest-value opportunities."));
  candidates.forEach((candidate) => {
    const resource = candidate.resource || {};
    const row = el("article", "compact-row");
    append(
      row,
      append(el("div"), el("strong", "row-title", resource.resource_name || "Cloud resource"), el("span", "row-meta", `${labelFor(resource.provider)} | ${labelFor(resource.normalized_resource_type)}`), el("span", "row-detail", candidate.exclusion_reason ? "Protected by context" : "Candidate for review")),
      append(el("div", "row-metric"), el("span", null, "Monthly cost"), el("strong", null, money(resource.estimated_monthly_cost))),
      append(el("div", "row-state"), el("span", null, "Confidence"), el("strong", null, percentage(candidate.candidate_score))),
      el("span", `signal-tag ${candidate.exclusion_reason ? "info" : candidate.candidate_score >= 0.8 ? "success" : "warning"}`, candidate.exclusion_reason ? "Protected" : candidate.requires_investigation ? "Needs context" : "Awaiting approval")
    );
    node.appendChild(row);
  });
}

function renderOverviewActivity() {
  const node = $("overview-activity-list");
  if (!node) return;
  clear(node);
  const events = (state.run?.audit_events || []).slice(-5).reverse();
  $("overview-activity-count").textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;
  if (!events.length) {
    ["PR analyzed", "Evidence gathered", "Recommendation produced", "Approval recorded", "Remediation PR created"].forEach((item) => {
      const li = el("li");
      append(li, el("strong", null, item), el("span", null, "Waiting for the first review workflow."));
      node.appendChild(li);
    });
    return;
  }
  events.forEach((event) => {
    const li = el("li");
    append(li, el("strong", null, event.summary || labelFor(event.event_type)), el("span", null, labelFor(event.event_type)));
    node.appendChild(li);
  });
}

function renderOverview() {
  renderOverviewSummary();
  renderOverviewRows();
  renderOverviewSavings();
  renderOverviewActivity();
}

function renderAll() {
  $("pr-empty-state").hidden = hasSelectedCase();
  $("case-view").hidden = !hasSelectedCase();
  renderAssistantTriggers();
  renderStatus(); renderSource(); renderPlanningStatus(); renderStages(); renderRecommendation(); renderEvidenceSummary(); renderHumanControls(); renderResult(); renderTechnical();
  renderCloudHunt(); renderReviewQueue(); renderOverview();
}

function renderAssistantTriggers() {
  $("ask-global-button").hidden = false;
  $("ask-case-button").hidden = !hasSelectedCase();
  $("ask-technical-button").hidden = !hasSelectedCase();
  $("ask-cloud-button").hidden = !(state.hunt || state.selectedReviewContext?.type === "cloud_hunt");
  $("ask-approvals-button").hidden = !state.reviews.length;
}

function switchMode(mode) {
  const titles = {
    overview: ["Workspace", "Overview"],
    simple: ["Reviews", "PR Reviews"],
    "cloud-hunt": ["Discovery", "Cloud Hunt"],
    "review-queue": ["Human control", "Approvals"],
    technical: ["Audit", "Technical Audit"],
  };
  ["overview", "simple", "cloud-hunt", "review-queue", "technical"].forEach((item) => {
    const view = item === "simple" ? "simple-view" : `${item}-view`;
    const button = item === "simple" ? "simple-view-button" : `${item}-view-button`;
    $(view).hidden = item !== mode;
    $(button).classList.toggle("active", item === mode);
    $(button).setAttribute("aria-pressed", String(item === mode));
  });
  state.activeMode = mode;
  $("page-kicker").textContent = titles[mode]?.[0] || "Workspace";
  $("page-title").textContent = titles[mode]?.[1] || "Overview";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function switchView(technical) { switchMode(technical ? "technical" : "simple"); }

function renderCloudHunt() {
  const summary = $("cloud-hunt-summary");
  if (!summary) return;
  clear(summary);
  if (state.loading.cloudHunt) {
    renderSkeletonList(summary, 6);
    renderSkeletonList($("candidate-list"), 4);
    $("candidate-count").textContent = "Scanning";
    return;
  }
  const data = state.hunt?.summary;
  if (!data) {
    summary.appendChild(el("p", "muted", "No cloud-hunt scan has been run yet."));
    $("candidate-count").textContent = "0 candidates";
    const list = $("candidate-list");
    clear(list);
    list.appendChild(el("p", "muted", "No cloud-hunt candidates to review yet."));
    return;
  }
  [["Provider scope", labelFor(state.hunt.provider_scope)], ["Resources scanned", data.total_resources], ["Candidates found", data.candidates], ["Protected resources", data.protected_candidates], ["Pending human reviews", data.needs_human_context], ["Monthly waste", money(data.estimated_monthly_waste)]].forEach(([label, value]) => {
    const card = el("article", "panel hunt-metric");
    append(card, el("span", null, label), el("strong", null, value));
    summary.appendChild(card);
  });
  $("candidate-count").textContent = `${data.candidates} candidate${data.candidates === 1 ? "" : "s"}`;
  const list = $("candidate-list"); clear(list);
  const activeFilters = new Set([...document.querySelectorAll("[data-hunt-filter]")].filter((item) => item.checked).map((item) => item.dataset.huntFilter));
  const candidates = (state.hunt.candidates || []).filter((candidate) => {
    if (!activeFilters.size) return true;
    if (activeFilters.has("high-confidence") && candidate.candidate_score >= 0.8 && !candidate.exclusion_reason) return true;
    if (activeFilters.has("needs-context") && candidate.requires_investigation && !candidate.exclusion_reason) return true;
    if (activeFilters.has("protected") && candidate.exclusion_reason) return true;
    if (activeFilters.has("awaiting-approval") && !candidate.exclusion_reason) return true;
    return false;
  });
  candidates.forEach((candidate) => {
    const resource = candidate.resource;
    const card = el("article", "candidate-card");
    const supporting = candidate.signals.filter((signal) => signal.supports_ghost_hypothesis).slice(0, 5).map((signal) => signal.description);
    const protective = candidate.signals.filter((signal) => !signal.supports_ghost_hypothesis).map((signal) => signal.description);
    const tags = el("div", "tag-row");
    const candidateTag = el("span", `signal-tag ${candidate.exclusion_reason ? "info" : candidate.candidate_score >= 0.8 ? "success" : "warning"}`);
    candidateTag.textContent = candidate.exclusion_reason
      ? "Protected resource"
      : candidate.candidate_score >= 0.8
        ? "High-confidence ghost resource"
        : candidate.requires_investigation
          ? "Needs more context"
          : "Suspicious candidate";
    tags.appendChild(candidateTag);
    append(card, el("p", "kicker", `${labelFor(resource.provider)} | ${labelFor(resource.normalized_resource_type)}`), el("h3", null, resource.resource_name), tags, dataList([["Environment", resource.environment], ["Monthly cost", money(resource.estimated_monthly_cost)], ["Confidence", percentage(candidate.candidate_score)], ["Current state", candidate.exclusion_reason || "Pending human review"]]), el("strong", "candidate-heading", "Why GhostBusters flagged it"));
    supporting.forEach((item) => card.appendChild(el("p", "candidate-signal", item)));
    if (protective.length) { card.appendChild(el("strong", "candidate-heading", "Why GhostBusters is cautious")); protective.forEach((item) => card.appendChild(el("p", "candidate-protection", item))); }
    list.appendChild(card);
  });
  if (!candidates.length) list.appendChild(el("p", "muted", "No cloud-hunt candidates match the selected filters."));
}

async function actOnCloudCase(id, action) {
  try {
    await api(`/api/reviews/${id}/action`, { method: "POST", body: JSON.stringify({ action, reviewer: "demo-reviewer", comment: action === "reject" ? "Demo review decision" : null }) });
    await loadReviewQueue();
  } catch (error) { setMessage("cloud-hunt-message", error.message); }
}

function renderReviewQueue() {
  const node = $("review-queue-list");
  if (!node) return;
  clear(node);
  if (state.loading.reviews) return renderSkeletonList(node, 4);
  if (!state.reviews.length) return node.appendChild(el("p", "muted", "No review cases are waiting right now."));
  state.reviews.forEach((item) => {
    const card = el("article", "queue-card");
    const heading = item.source_type === "terraform_pr"
      ? item.repository || "Terraform review"
      : item.provider ? labelFor(item.provider) : "Cloud Hunt";
    append(card, el("p", "kicker", labelFor(item.source_type)), el("h3", null, heading), dataList([["Resource", item.resource_name], ["Recommendation", item.recommendation], ["Confidence", percentage(item.confidence)], ["Savings", `${money(item.estimated_monthly_savings)}/month`], ["Policy status", policyStatusLabel(item.policy_status)], ["Current state", runStatusLabel(item.status)]]), el("p", "queue-reason", item.recommendation_reason));
    const actions = el("div", "queue-actions");
    const open = el("button", "secondary", "Open Review");
    if (item.source_type === "terraform_pr") {
      open.addEventListener("click", async () => {
        state.run = await api(`/api/runs/${item.id}`);
        state.selectedReviewContext = { source: "approvals", type: "terraform_pr", runId: item.id };
        startAnimation(true);
        switchMode("simple");
      });
    } else {
      open.addEventListener("click", () => {
        state.selectedReviewContext = { source: "approvals", type: item.source_type, runId: item.id };
        switchMode("cloud-hunt");
      });
    }
    actions.appendChild(open);
    card.appendChild(actions);
    node.appendChild(card);
  });
}

const assistantSuggestions = {
  pr_review: ["Why do you recommend this?", "Which evidence affected confidence?", "What happens if I approve?", "Were any conflicts detected?", "Did GhostBusters change anything?"],
  cloud_hunt: ["Why was this resource flagged?", "Why is this resource protected?", "What evidence is missing?", "What action is being recommended?"],
  approvals: ["Why is this waiting for approval?", "What are the safety conditions?", "What happens after approval?"],
  technical_audit: ["Which tools were selected and why?", "Were retries used?", "Which policy rules were evaluated?", "What evidence was missing?"],
  product_help: ["What is PR Reviews?", "What is Cloud Hunt?", "What is Approvals?", "Does GhostBusters run Terraform?"],
};

function assistantContextLabel(context) {
  const caseId = selectedAssistantCaseId(context);
  if (context === "pr_review") return caseId ? `Current PR case: ${caseId}` : "PR Reviews";
  if (context === "cloud_hunt") return caseId ? `Current Cloud Hunt case: ${caseId}` : "Cloud Hunt";
  if (context === "approvals") return caseId ? `Current approval case: ${caseId}` : "Approvals";
  if (context === "technical_audit") return caseId ? `Technical Audit case: ${caseId}` : "Technical Audit";
  return "Product help";
}

function openAssistant(context) {
  state.assistantContext = context || "product_help";
  $("assistant-backdrop").hidden = false;
  $("assistant-context-label").textContent = assistantContextLabel(state.assistantContext);
  setMessage("assistant-message", "");
  renderAssistantSuggestions();
  $("assistant-question-input").focus();
}

function closeAssistant() {
  $("assistant-backdrop").hidden = true;
}

function renderAssistantSuggestions() {
  const node = $("assistant-suggestions");
  clear(node);
  (assistantSuggestions[state.assistantContext] || assistantSuggestions.product_help).forEach((question) => {
    const button = el("button", "secondary compact", question);
    button.type = "button";
    button.addEventListener("click", () => {
      $("assistant-question-input").value = question;
      askAssistant();
    });
    node.appendChild(button);
  });
}

async function askAssistant() {
  const question = $("assistant-question-input").value.trim();
  if (!question) return setMessage("assistant-message", "Enter a question first.");
  return withButtonState("assistant-ask-button", "Generating explanation...", async () => {
    state.loading.assistant = true;
    setMessage("assistant-message", "Reading recorded data...", true);
    const caseId = selectedAssistantCaseId();
    const payload = { question, context: state.assistantContext };
    if (caseId) payload.case_id = caseId;
    const response = await api("/api/assistant/ask", { method: "POST", body: JSON.stringify(payload) });
    renderAssistantAnswer(response);
    setMessage("assistant-message", "", true);
  }).catch((error) => {
    clear($("assistant-answer"));
    const message = friendlyError(error, "Assistant unavailable. Try again.");
    setMessage("assistant-message", message);
    showToast("Assistant unavailable", message, "error");
  }).finally(() => {
    state.loading.assistant = false;
  });
}

function renderAssistantAnswer(response) {
  const node = $("assistant-answer");
  clear(node);
  const tagRow = el("div", "tag-row");
  const typeTag = el("span", "signal-tag info", labelFor(response.answer_type));
  const providerTag = el("span", `signal-tag ${response.fallback_used ? "warning" : "success"}`, response.fallback_used ? "Deterministic fallback" : labelFor(response.provider));
  append(tagRow, typeTag, providerTag);
  append(node, tagRow, el("p", "assistant-answer-text", response.answer || "That information is not available in the current case."));
  if (response.evidence_sources?.length) {
    const sources = el("div", "assistant-source-row");
    response.evidence_sources.forEach((source) => sources.appendChild(el("span", "context-label", labelFor(source))));
    node.appendChild(sources);
  }
  if (response.supporting_sections?.length) {
    node.appendChild(el("p", "muted", `Supporting sections: ${response.supporting_sections.map(labelFor).join(", ")}`));
  }
  if (response.limitations?.length) {
    node.appendChild(el("p", "muted", `Limitations: ${response.limitations.map(formatValue).join("; ")}`));
  }
}

if (typeof window !== "undefined") {
  window.__ghostbustersTestHooks = {
    state,
    renderAll,
    renderCloudHunt,
    renderReviewQueue,
    renderTechnical,
    openDemoModal,
    closeDemoModal,
    switchMode,
    allowedReviewActions,
    humanDecision,
    currentConfiguration,
    proposedConfiguration,
    changeTypeLabel,
    estimatedCostImpact,
    plainRecommendationTitle,
    policyStatusLabel,
    runStatusLabel,
    openAssistant,
    renderAssistantAnswer,
  };
}

function bindEvents() {
  $("start-button").addEventListener("click", startRun);
  $("overview-view-button").addEventListener("click", () => switchMode("overview"));
  $("overview-launch-demo-button").addEventListener("click", openDemoModal);
  $("overview-refresh-button").addEventListener("click", refreshRun);
  $("overview-open-prs-button").addEventListener("click", () => switchMode("simple"));
  $("overview-open-approvals-button").addEventListener("click", () => { switchMode("review-queue"); loadReviewQueue(); });
  $("overview-open-cloud-button").addEventListener("click", () => switchMode("cloud-hunt"));
  $("refresh-button").addEventListener("click", refreshRun);
  $("case-refresh-button").addEventListener("click", refreshRun);
  $("launch-demo-button").addEventListener("click", openDemoModal);
  $("case-launch-demo-button").addEventListener("click", openDemoModal);
  $("cancel-demo-button").addEventListener("click", closeDemoModal);
  $("close-demo-button").addEventListener("click", closeDemoModal);
  $("open-approvals-button").addEventListener("click", () => switchMode("review-queue"));
  $("technical-open-approvals-button").addEventListener("click", () => switchMode("review-queue"));
  $("pause-button").addEventListener("click", () => { state.paused = !state.paused; $("pause-button").textContent = state.paused ? "Resume" : "Pause"; });
  $("skip-animation").addEventListener("change", (event) => { state.skipAnimation = event.target.checked; if (state.run && state.skipAnimation) startAnimation(true); });
  $("simple-view-button").addEventListener("click", () => switchView(false));
  $("cloud-hunt-view-button").addEventListener("click", () => switchMode("cloud-hunt"));
  $("review-queue-view-button").addEventListener("click", () => { switchMode("review-queue"); loadReviewQueue(); });
  $("technical-view-button").addEventListener("click", () => switchView(true));
  $("open-technical-button").addEventListener("click", () => switchView(true));
  document.querySelectorAll("[data-review-action]").forEach((button) => button.addEventListener("click", () => selectReviewAction(button.dataset.reviewAction)));
  $("submit-review-button").addEventListener("click", submitSelectedReview);
  $("cancel-review-button").addEventListener("click", closeReviewForm);
  $("start-cloud-hunt-button").addEventListener("click", startCloudHunt);
  $("refresh-review-queue-button").addEventListener("click", loadReviewQueue);
  $("ask-case-button").addEventListener("click", () => openAssistant("pr_review"));
  $("ask-cloud-button").addEventListener("click", () => openAssistant("cloud_hunt"));
  $("ask-approvals-button").addEventListener("click", () => openAssistant("approvals"));
  $("ask-technical-button").addEventListener("click", () => openAssistant("technical_audit"));
  $("ask-global-button").addEventListener("click", () => openAssistant("product_help"));
  $("notification-button").addEventListener("click", () => showToast("No new notifications", "This workspace has no notification feed configured.", "success"));
  $("assistant-close-button").addEventListener("click", closeAssistant);
  $("assistant-clear-button").addEventListener("click", () => { $("assistant-question-input").value = ""; clear($("assistant-answer")); setMessage("assistant-message", ""); });
  $("assistant-ask-button").addEventListener("click", askAssistant);
  $("assistant-question-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) askAssistant();
    if (event.key === "Escape") closeAssistant();
  });
  $("assistant-backdrop").addEventListener("click", (event) => { if (event.target.id === "assistant-backdrop") closeAssistant(); });
  document.querySelectorAll("[data-hunt-filter]").forEach((filter) => filter.addEventListener("change", renderCloudHunt));
  document.querySelectorAll(".audit-section").forEach((section) => {
    section.addEventListener("toggle", () => {
      if (!section.open) return;
      document.querySelectorAll(".audit-section").forEach((other) => {
        if (other !== section) other.open = false;
      });
    });
  });
}

if (ensureCompatibleDom()) {
  bindEvents();
  loadInitial();
}
