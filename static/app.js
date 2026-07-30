const state = {
  run: null,
  outcome: null,
  overview: null,
  workspace: null,
  demoReadiness: null,
  scenarios: [],
  demoScenarios: [],
  visibleEvents: [],
  animationTimer: null,
  paused: false,
  skipAnimation: false,
  selectedReviewAction: null,
  selectedCloudReviewAction: null,
  prReviews: [],
  prReviewsServerPaged: false,
  prReviewTotal: 0,
  prReviewCounts: { all: 0, "needs-attention": 0, "in-progress": 0, completed: 0, blocked: 0 },
  prReviewFilters: {
    group: "needs-attention",
    search: "",
    repository: "",
    status: "",
    recommendation: "",
    reviewer: "",
    dateRange: "all",
    sort: "updated_desc",
    page: 1,
    pageSize: 20,
  },
  prReviewListScrollTop: 0,
  knownPrReviewIds: new Set(),
  newPrReviewCount: 0,
  prReviewError: "",
  hunt: null,
  hunts: [],
  selectedCloudHuntId: null,
  cloudHuntServerPaged: false,
  cloudHuntTotal: 0,
  cloudHuntPage: 1,
  cloudHuntPageSize: 20,
  cloudHuntFilters: { status: "", provider: "", search: "", sort: "newest" },
  cloudHuntError: "",
  goals: [],
  selectedGoal: null,
  goalDraft: null,
  goalSelectedRepositories: [],
  goalCreationStage: "idle",
  goalEvents: [],
  goalTab: "outcome",
  goalPollTimer: null,
  goalPollFailures: 0,
  goalStartInFlight: false,
  goalValidationInFlight: false,
  awsConfig: null,
  awsValidation: null,
  githubConfig: null,
  githubValidation: null,
  jiraConfig: null,
  jiraValidation: null,
  cloudSchedules: [],
  reviews: [],
  selectedReviewContext: null,
  assistantContext: "product_help",
  cloudHuntFilter: "all",
  loading: {
    initial: true,
    reviews: false,
    prReviews: false,
    cloudHunt: false,
    cloudHunts: false,
    run: false,
    review: false,
    assistant: false,
  },
  activeMode: "overview",
  currentUser: null,
  authMode: "signin",
  authRequired: false,
  invitationToken: null,
  invitationPreview: null,
  members: [],
  invitations: [],
  activity: { items: [], total: 0, page: 1, pageSize: 25, hasNext: false, error: "", filters: { category: "", actorType: "", action: "", result: "", targetType: "", search: "", dateRange: "all", createdFrom: "", createdTo: "", sort: "created_at_desc" } },
};

const stageDefinitions = [
  { id: "received", title: "PR received", description: "Terraform pull request captured.", matches: ["run_created", "goal_received"] },
  { id: "parsed", title: "Terraform change parsed", description: "Resource and configuration change identified.", matches: ["terraform_parsed"] },
  { id: "planned", title: "Investigation planned", description: "Questions and evidence sources selected.", matches: ["investigation_plan_created", "tool_selected"] },
  { id: "evidence", title: "Evidence collected", description: "Cost, usage, dependency, and activity evidence gathered.", prefix: ["tool_", "external_call_", "alternative_evidence_"] },
  { id: "recommended", title: "Recommendation produced", description: "GhostOps selected the safest cost action.", matches: ["conflicts_detected", "verifier_completed", "alternatives_generated", "recommendation_produced"], prefix: ["policy_"] },
  { id: "human", title: "Human review", description: "A reviewer confirms, rejects, or requests more context.", matches: ["human_review_received", "additional_evidence_requested", "human_context_added", "workflow_resumed", "preferred_action_modified"] },
  { id: "remediation", title: "Remediation PR", description: "A simulated or real remediation pull request is recorded.", matches: ["mock_pr_created", "real_pr_created"] },
];

const cloudJourneyDefinitions = [
  { id: "inventory", title: "Inventory loaded", matches: ["cloud_hunt_started", "inventory_loaded", "provider_inventory_loaded"] },
  { id: "evaluated", title: "Resources evaluated", matches: ["resources_evaluated", "resource_evaluated"], prefix: ["cloud_resource_", "candidate_signal_"] },
  { id: "risks", title: "Risks checked", matches: ["risks_checked", "dependencies_checked", "policy_checked"], prefix: ["policy_", "protection_"] },
  { id: "classified", title: "Candidates classified", matches: ["candidates_classified", "cloud_hunt_completed", "candidate_created"] },
  { id: "human", title: "Human review", matches: ["human_review_received", "additional_evidence_requested"] },
  { id: "proposal", title: "Remediation proposal", matches: ["mock_pr_created", "real_pr_created", "remediation_proposed"] },
];

const toolNames = ["pricing", "utilization", "jira", "git_activity", "dependencies"];
const $ = (id) => document.getElementById(id);
const on = (id, eventName, handler) => {
  const node = $(id);
  if (!node) return;
  node.addEventListener(eventName, handler);
};
const uiVersion = "auth-v1";
const requiredElementIds = [
  "api-pill",
  "auth-modal-backdrop",
  "auth-message",
  "settings-view",
  "settings-view-button",
  "active-members-table",
  "pending-invitations-table",
  "invite-modal-backdrop",
  "overview-view",
  "overview-view-button",
  "overview-summary",
  "overview-pr-list",
  "overview-savings-list",
  "overview-repositories-list",
  "setup-progress-list",
  "setup-progress-bar",
  "overview-approval-alerts",
  "overview-activity-list",
  "cloud-journey-list",
  "toast-region",
  "page-title",
  "simple-view",
  "technical-view",
  "pr-empty-state",
  "pr-review-list",
  "pr-search-input",
  "pr-repository-filter",
  "pr-status-filter",
  "pr-recommendation-filter",
  "pr-reviewer-filter",
  "pr-date-filter",
  "pr-sort-select",
  "pr-page-size-select",
  "pr-pagination-summary",
  "pr-new-review-notice",
  "pr-new-review-text",
  "pr-notice-refresh-button",
  "pr-review-error",
  "pr-retry-button",
  "pr-prev-page-button",
  "pr-next-page-button",
  "pr-filter-count-all",
  "pr-filter-count-needs-attention",
  "pr-filter-count-in-progress",
  "pr-filter-count-completed",
  "pr-filter-count-blocked",
  "pr-timezone-note",
  "back-pr-list-button",
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
  "case-received-time",
  "case-updated-time",
  "case-recommendation-time",
  "case-decision-time",
  "case-result-time",
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
  console.error(`GhostOps UI could not start because these elements are missing: ${missing.join(", ")}`);
  return false;
}

function portalCloudFindingDialog() {
  const dialog = $("cloud-finding-detail");
  if (!dialog || !document.body || dialog.parentNode === document.body) return;
  document.body.appendChild(dialog);
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
  const technicalLabels = new Set([
    "Base branch",
    "Engine",
    "Event type",
    "Head SHA",
    "Idempotency key",
    "Model",
    "Policy engine",
    "Pull request",
    "Real remediation URL",
    "Repository",
    "Resource",
    "Resource ID",
    "Run ID",
    "Scenario fixture",
    "Source file",
    "Terraform actions",
    "Tool",
    "Trigger source",
    "Version",
  ]);
  entries.forEach(([label, value]) => {
    const row = el("div");
    append(row, el("dt", null, label), el("dd", technicalLabels.has(label) ? "technical-value" : null, value));
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
    groq_primary: "Groq-assisted planning",
    // Earlier persisted runs used gemini_primary as the generic primary-mode
    // identifier. Groq is this deployment's primary planner.
    gemini_primary: "Groq-assisted planning",
    gemini_fallback_model: "Gemini fallback planning",
    mock_gemini: "Mock AI planning",
    deterministic_fallback: "Deterministic fallback",
    deterministic_only: "Deterministic safety policy",
  }[mode] || "Not recorded";
}

function validationModeLabel(mode) {
  return {
    groq_assisted: "Groq-assisted validation",
    gemini_assisted: "Groq-assisted validation",
  }[mode] || "Deterministic validation";
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
    remediation_pr_created: "Remediation PR Created",
    remediation_proposal_prepared: "Remediation Proposal Prepared",
    approval_revoked: "Approval Revoked",
    reopened: "Case Reopened",
    failed_safely: "Failed safely",
    rejected: "Recommendation Rejected",
    approved: "Approved",
    blocked: "Blocked by policy",
    keep: "No change recommended",
    abstained: "No recommendation",
    canceled: "Canceled safely",
  }[status] || labelFor(status || "no_case");
}

function pricingForRun(run) {
  if (run?.pricing && typeof run.pricing === "object") return run.pricing;
  const item = (run?.decision_record?.evidence || []).find((candidate) => candidate.source === "pricing");
  if (!item || item.freshness_status === "unavailable") return { available: false, source: "unavailable", source_mode: "unavailable", reason: "Live pricing evidence was not available for this change." };
  if (isDemoRun(run) && item.source_mode !== "live" && item.source_mode !== "verified_cached") return { available: true, source: "scenario_fixture", source_mode: "fixture", ...item.value };
  if (item.source_mode !== "live" && item.source_mode !== "verified_cached") return { available: false, source: "unavailable", source_mode: "unavailable", reason: "Live pricing evidence was not available for this change." };
  const value = item.value || {};
  const required = ["source", "region", "resource_type", "pricing_model", "checked_at", "assumptions", "currency"];
  if (required.some((field) => value[field] === undefined || value[field] === null || value[field] === "" || Array.isArray(value[field]) && !value[field].length)) return { available: false, source: "unavailable", source_mode: "unavailable", reason: "Live pricing evidence was not available for this change." };
  return { available: true, source: item.source, source_mode: item.source_mode, ...value };
}

function pricingAmountLabel(value, suffix = "") {
  return value === null || value === undefined || !Number.isFinite(Number(value)) ? "Cost estimate unavailable" : `${money(value)}${suffix}`;
}

function pricingAvailable(run) {
  const pricing = pricingForRun(run);
  return Boolean(pricing.available) || isDemoRun(run);
}

function cloudCandidatePrimaryStatus(candidate) {
  if (!candidate) return { key: "neutral", label: "No action required", className: "status-neutral" };
  if (candidate.exclusion_reason) return { key: "protected", label: "Protected resource", className: "status-protected", icon: "i" };
  if (candidate.candidate_score >= 0.8) return { key: "high-confidence", label: "High-confidence ghost resource", className: "status-high-confidence", icon: "✓" };
  if (candidate.requires_investigation) return { key: "needs-context", label: "Needs more context", className: "status-needs-context", icon: "!" };
  return { key: "neutral", label: "No action required", className: "status-neutral" };
}

function reviewStateStatus(status) {
  return {
    pending: { key: "awaiting-review", label: "Pending human review", className: "status-awaiting-review" },
    pending_human_review: { key: "awaiting-review", label: "Pending human review", className: "status-awaiting-review" },
    needs_more_evidence: { key: "needs-context", label: "Needs more context", className: "status-needs-context" },
    blocked: { key: "blocked", label: "Blocked by policy", className: "status-blocked" },
    approved: { key: "approved", label: "Remediation approved", className: "status-approved" },
    pr_created: { key: "pr-created", label: "Remediation PR created", className: "status-pr-created" },
    remediation_pr_created: { key: "pr-created", label: "Remediation PR created", className: "status-pr-created" },
    remediation_proposal_prepared: { key: "approved", label: "Remediation proposal prepared", className: "status-approved" },
    approval_revoked: { key: "blocked", label: "Approval revoked", className: "status-blocked" },
    reopened: { key: "awaiting-review", label: "Case reopened", className: "status-awaiting-review" },
    keep: { key: "neutral", label: "No action required", className: "status-neutral" },
    rejected: { key: "blocked", label: "Blocked by policy", className: "status-blocked" },
  }[status] || { key: "awaiting-review", label: "Pending human review", className: "status-awaiting-review" };
}

function statusBadge(status) {
  const badge = el("span", `status-badge ${status.className}`);
  badge.setAttribute("title", status.label);
  badge.setAttribute("aria-label", status.label);
  badge.textContent = status.icon ? `${status.icon} ${status.label}` : status.label;
  return badge;
}

function setStatusBadge(id, status) {
  const node = $(id);
  if (!node) return;
  node.className = `status-badge ${status.className}`;
  node.setAttribute("title", status.label);
  node.setAttribute("aria-label", status.label);
  node.textContent = status.icon ? `${status.icon} ${status.label}` : status.label;
}

function policyStatusMeta(status) {
  const label = policyStatusLabel(status);
  if (status === "blocked") return { key: "blocked", label, className: "status-blocked" };
  if (status === "needs_human_context") return { key: "needs-context", label, className: "status-needs-context" };
  if (status === "passed") return { key: "allowed", label, className: "status-allowed" };
  return { key: "neutral", label, className: "status-neutral" };
}

function humanReviewStatusMeta(caseItem) {
  if (!caseItem) return { key: "neutral", label: "No approval case found", className: "status-neutral" };
  return { key: "awaiting-review", label: "Human review required", className: "status-awaiting-review" };
}

function decisionStatusMeta(status, label) {
  if (status === "pending_human_review" || status === "pending") return { key: "awaiting-review", label: label || "Pending human review", className: "status-awaiting-review" };
  if (status === "needs_more_evidence" || status === "abstained") return { key: "needs-context", label: label || "More evidence required", className: "status-needs-context" };
  if (status === "blocked" || status === "rejected" || status === "approval_revoked" || status === "failed_safely") return { key: "blocked", label: label || runStatusLabel(status), className: "status-blocked" };
  if (status === "approved") return { key: "approved", label: label || "Approved", className: "status-approved" };
  if (status === "pr_created" || status === "remediation_pr_created") return { key: "pr-created", label: label || "Remediation PR created", className: "status-pr-created" };
  if (status === "remediation_proposal_prepared") return { key: "approved", label: label || "Remediation proposal prepared", className: "status-approved" };
  if (status === "reopened") return { key: "awaiting-review", label: label || "Case reopened", className: "status-awaiting-review" };
  return { key: "neutral", label: label || "Not made", className: "status-neutral" };
}

function progressStep(title, description, stateName, index, actionLabel = null, actionHandler = null) {
  const stateClass = String(stateName).replaceAll(" ", "-");
  const item = el("li", `progress-step progress-${stateClass}`);
  item.setAttribute("aria-label", `${title}: ${labelFor(stateName)}`);
  const marker = el("span", "progress-marker");
  marker.setAttribute("aria-hidden", "true");
  marker.textContent = stateName === "completed" ? "✓" : String(index + 1);
  const copy = el("div", "progress-copy");
  append(copy, el("span", "progress-state", labelFor(stateName)), el("strong", null, title), el("small", null, description));
  append(item, marker, copy);
  if (actionLabel && actionHandler) {
    const action = el("button", "secondary compact", actionLabel);
    action.type = "button";
    action.addEventListener("click", actionHandler);
    item.appendChild(action);
  }
  return item;
}

function responsiveTable(columns, rows, emptyMessage) {
  const table = el("table", "data-table");
  const thead = el("thead");
  const headRow = el("tr");
  columns.forEach((column) => {
    const thClass = ["table-heading", column.priority ? `priority-${column.priority}` : ""].filter(Boolean).join(" ");
    const th = el("th", thClass, column.label);
    th.scope = "col";
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  const tbody = el("tbody");
  if (!rows.length) {
    const row = el("tr", "empty-row");
    const cell = el("td", null, emptyMessage);
    cell.colSpan = columns.length;
    row.appendChild(cell);
    tbody.appendChild(row);
  }
  rows.forEach((rowData) => {
    const row = el("tr");
    columns.forEach((column) => {
      const cell = el("td", column.priority ? `priority-${column.priority}` : null);
      cell.setAttribute("data-label", column.label);
      const value = typeof column.render === "function" ? column.render(rowData) : rowData[column.key];
      if (value && typeof value === "object" && "tagName" in value) cell.appendChild(value);
      else cell.textContent = formatValue(value);
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });
  append(table, thead, tbody);
  return table;
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
  const pricing = pricingForRun(run);
  if (!pricing.available) return "Cost estimate unavailable";
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
  const csrf = state.currentUser?.csrf_token;
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || `${response.status} ${response.statusText}`;
    const error = new Error(typeof detail === "string" ? detail : prettyValue(detail));
    error.status = response.status;
    error.endpoint = path;
    throw error;
  }
  return payload;
}

async function loadCurrentUser({ showAuthOnFailure = false } = {}) {
  try {
    state.currentUser = await api("/api/auth/me");
    state.authRequired = false;
    closeAuthModal();
    renderIdentity();
    return state.currentUser;
  } catch (error) {
    state.currentUser = null;
    state.authRequired = true;
    if (showAuthOnFailure) {
      openAuthModal("signin");
      setMessage("auth-message", "Sign in or create a workspace to continue.");
    }
    return null;
  }
}

function setMessage(id, message, success = false) {
  const node = $(id);
  node.textContent = message || "";
  node.style.color = success ? "var(--green)" : "var(--red)";
}

function hasPermission(permission) {
  if (!state.currentUser) return true;
  return Boolean(state.currentUser?.permissions?.includes(permission));
}

function roleLabel() {
  return state.currentUser?.role_label || "Reviewer";
}

function userDisplayName() {
  return state.currentUser?.user?.display_name || "Not signed in";
}

function userEmail() {
  return state.currentUser?.user?.email || "";
}

function organizationName() {
  return state.currentUser?.organization?.name || "No organization selected";
}

function renderIdentity() {
  const initials = userDisplayName().split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "GB";
  const authenticated = Boolean(state.currentUser?.authenticated);
  const appShell = typeof document.querySelector === "function" ? document.querySelector(".app-shell") : null;
  if (appShell) appShell.hidden = !authenticated;
  const authScreen = $("auth-modal-backdrop");
  if (authScreen) authScreen.hidden = authenticated;
  if ($("user-initials")) $("user-initials").textContent = initials;
  if ($("user-display-name")) $("user-display-name").textContent = userDisplayName();
  if ($("user-role-org")) $("user-role-org").textContent = `${roleLabel()} · ${organizationName()}`;
  if ($("sign-out-button")) {
    $("sign-out-button").hidden = !authenticated;
    $("sign-out-button").disabled = !authenticated;
  }
  if ($("settings-view-button")) $("settings-view-button").hidden = authenticated && !hasPermission("members.read");
  if ($("activity-view-button")) $("activity-view-button").hidden = authenticated && !hasPermission("activity.read");
  [["reviewer-identity-name", userDisplayName()], ["reviewer-identity-detail", `${roleLabel()} · ${userEmail()}`], ["cloud-reviewer-identity-name", userDisplayName()], ["cloud-reviewer-identity-detail", `${roleLabel()} · ${userEmail()}`]].forEach(([id, value]) => {
    if ($(id)) $(id).textContent = value;
  });
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
  if (error?.status === 409) {
    if (/email already registered|organization already exists|registration conflict/i.test(message)) return message;
    return "This case changed while you were deciding. Refresh the case and try again.";
  }
  if (/traceback|stack|exception|file "/i.test(message)) return fallback;
  return message.length > 180 ? `${message.slice(0, 177)}...` : message;
}

function withTimeout(promise, timeoutMs, message = "Request timed out.") {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = window.setTimeout(() => {
      const error = new Error(message);
      error.code = "TIMEOUT";
      reject(error);
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => window.clearTimeout(timer));
}

function normalizeGoalResponse(payload) {
  if (!payload || typeof payload !== "object" || !payload.id) {
    const error = new Error("The investigation returned an invalid response.");
    error.code = "MALFORMED_RESPONSE";
    throw error;
  }
  return {
    ...payload,
    goal: payload.goal || payload.title || "Untitled goal",
    scope: payload.scope || "Workspace scope",
    status: payload.status || "created",
    data_source_mode: payload.data_source_mode || "Connected evidence",
    created_at: payload.created_at || new Date().toISOString(),
    updated_at: payload.updated_at || payload.created_at || new Date().toISOString(),
    current_stage: payload.current_stage || payload.current_step || "waiting",
    planning_mode: payload.goal_planning_mode || payload.planning_mode || payload.decision_record?.planning_mode || "deterministic_only",
    execution_mode: payload.execution_mode || "Not available",
    findings: Array.isArray(payload.findings) ? payload.findings : (payload.decision_record?.verifier_findings || []),
    evidence: Array.isArray(payload.evidence) ? payload.evidence : (payload.evidence_summaries || payload.decision_record?.evidence || []),
    recommendation: payload.recommendation || payload.decision_record?.preferred_alternative || null,
    approval_required: payload.approval_required ?? payload.status === "pending_human_review",
    linked_pr_review_id: payload.linked_pr_review_id || null,
    linked_cloud_hunt_id: payload.linked_cloud_hunt_id || null,
    linked_approval_id: payload.linked_approval_id || null,
    version: payload.version || null,
  };
}

function goalErrorMessage(error) {
  if (error?.code === "TIMEOUT") return "The investigation did not start. Retry.";
  if (error?.status === 401) return "Authentication required.";
  if (error?.status === 403) return "You do not have permission to start this investigation.";
  if (error?.status === 409) return "This goal conflicts with a newer workspace state or safety policy.";
  if (error?.status === 422) return error.message || "This goal is not valid for a safe investigation.";
  if (error?.status === 429) return "Goal requests are temporarily rate limited. Retry shortly.";
  if (error?.status >= 500) return "The investigation service is temporarily unavailable. Retry.";
  if (error?.code === "MALFORMED_RESPONSE") return "The investigation returned an invalid response. Retry.";
  return "The investigation could not start. Retry.";
}

function logGoalDiagnostic(message, error) {
  const hostname = typeof window !== "undefined" ? window.location?.hostname : "";
  if (["localhost", "127.0.0.1"].includes(hostname)) console.debug(`[GhostOps Goals] ${message}`, { endpoint: error?.endpoint, status: error?.status, code: error?.code });
}

function showGoalError(error) {
  logGoalDiagnostic("Goal start failed", error);
  const message = $("goal-message");
  $("goal-confirm-button")?.parentNode?.parentNode?.appendChild(message);
  setMessage("goal-message", goalErrorMessage(error));
  const retry = $("goal-retry-button");
  if (retry) {
    $("goal-confirm-button")?.parentNode?.appendChild(retry);
    retry.hidden = false;
  }
  if ($("goal-edit-button")) $("goal-edit-button").textContent = "Return to goal form";
}

function stopGoalPolling() {
  if (state.goalPollTimer) window.clearTimeout(state.goalPollTimer);
  state.goalPollTimer = null;
  state.goalPollFailures = 0;
}

function beginGoalPolling(goalId) {
  if (state.goalPollTimer) window.clearTimeout(state.goalPollTimer);
  state.goalPollTimer = null;
  const terminal = ["completed", "approved", "pr_created", "remediation_pr_created", "failed_safely", "canceled", "blocked", "pending_human_review", "needs_more_evidence", "rejected", "abstained", "keep"];
  if (terminal.includes(state.selectedGoal?.status)) return;
  state.goalPollTimer = window.setTimeout(() => {
    if (state.selectedGoal?.id === goalId) void selectGoal(goalId, false);
  }, Math.min(15000, 3000 * (2 ** state.goalPollFailures)));
}

function decisionIdempotencyKey(caseId, action) {
  const random = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${caseId}:${action}:${random}`;
}

function approvalPermissionFor(action) {
  return {
    approve: "approvals.decide",
    reject: "approvals.reject",
    revoke_approval: "approvals.revoke",
    reopen_case: "approvals.reopen",
    request_evidence: "approvals.request_evidence",
    add_context: "approvals.add_context",
    add_follow_up_context: "approvals.add_context",
    modify: "approvals.modify",
  }[action] || "approvals.decide";
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

function userTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "browser timezone";
}

function parseTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function exactTimestamp(value) {
  const date = parseTime(value);
  if (!date) return "Not recorded";
  return `${date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" })} ${userTimezone()}`;
}

function relativeTime(value) {
  const date = parseTime(value);
  if (!date) return "Not recorded";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const units = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, amount] of units) {
    if (Math.abs(seconds) >= amount) return formatter.format(Math.round(seconds / amount), unit);
  }
  return formatter.format(seconds, "second");
}

function timestampNode(value, label = "Updated") {
  const node = el("span", "timestamp-value", relativeTime(value));
  const date = parseTime(value);
  const timezone = state.currentUser?.organization?.timezone;
  let exact = exactTimestamp(value);
  if (date && timezone) {
    try { exact = `${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium", timeZone: timezone }).format(date)} ${timezone}`; } catch { /* fall back to browser time */ }
  }
  node.title = exact;
  node.setAttribute("aria-label", `${label}: ${exact}`);
  return node;
}

function latestReviewer(run) {
  const latest = run?.human_reviews?.[run.human_reviews.length - 1];
  return latest?.reviewer || "Unassigned";
}

function latestDecisionTime(run) {
  return run?.human_reviews?.[run.human_reviews.length - 1]?.created_at || null;
}

function recommendationCompletedTime(run) {
  return (run?.audit_events || []).find((event) => event.event_type === "recommendation_produced")?.timestamp || run?.updated_at || null;
}

function resultTime(run) {
  if (!run) return null;
  if (run.real_pr?.created_at) return run.real_pr.created_at;
  if (run.mock_pr?.created_at) return run.mock_pr.created_at;
  if (["rejected", "approved", "needs_more_evidence"].includes(run.status)) return latestDecisionTime(run);
  return null;
}

function prChangeSummary(run) {
  const change = currentResourceChange(run);
  const before = change?.before?.instance_type || change?.before?.machine_type || change?.before?.size || run?.mock_pr?.current_instance_type || "Current";
  const after = change?.after?.instance_type || change?.after?.machine_type || change?.after?.size || run?.mock_pr?.proposed_instance_type || "Proposed";
  if (before !== "Current" || after !== "Proposed") return `${before} -> ${after}`;
  return change?.address || run?.decision_record?.resource_id || "Terraform change";
}

function prReviewSummary(run) {
  if (run?.repository && !run.decision_record && Object.prototype.hasOwnProperty.call(run, "savings")) {
    const summarySavings = run.pricing && !run.pricing.available ? null : (run.savings === null || run.savings === undefined ? null : Number(run.savings));
    return { ...run, case_status: run.status, recommendation_key: run.recommendation || "not_recorded", recommendation: recommendationLabel(run.recommendation), estimated_monthly_savings: summarySavings, confidence: Number(run.confidence || 0), terraform_resource: run.change || "Not recorded", change_summary: run.change_summary || "Terraform review", received_at: run.received_at || null, updated_at: run.updated_at || null, reviewer: run.reviewer || "Unassigned", branch: run.branch || "Not recorded", title: run.title || "Terraform review", source_type: run.source_type || "terraform_pr" };
  }
  const decision = run?.decision_record;
  const preferred = (decision?.alternatives || []).find((item) => item.action === decision.preferred_action);
  const change = currentResourceChange(run);
  const source = run?.github_source;
  const latestReview = run?.human_reviews?.[run.human_reviews.length - 1];
  const pricing = pricingForRun(run);
  const savings = pricingAvailable(run) ? Number(preferred?.estimated_monthly_savings ?? run?.mock_pr?.monthly_savings ?? 0) : null;
  return {
    id: run.id,
    source_type: run.source_type,
    repository: source?.repository || run?.mock_pr?.repository || "Demo review",
    pull_request_number: source?.pull_request_number || run?.mock_pr?.pr_number || null,
    title: source?.pull_request_title || run?.mock_pr?.title || selectedCaseTitle(run),
    branch: source?.head_branch || run?.mock_pr?.branch || "Not recorded",
    base_branch: source?.base_branch || run?.mock_pr?.base_branch || "Not recorded",
    terraform_resource: change?.address || decision?.resource_id || run?.mock_pr?.resource_id || "Not recorded",
    change_summary: prChangeSummary(run),
    recommendation: plainRecommendationTitle(run),
    recommendation_key: decision?.preferred_action || run?.mock_pr?.chosen_action || "not_recorded",
    estimated_monthly_savings: savings,
    pricing,
    confidence: Number(decision?.confidence?.final_confidence || run?.mock_pr?.confidence || 0),
    risk: riskLevel(decision, preferred),
    policy_status: decision?.policy_result?.status || "not_recorded",
    case_status: run.status,
    reviewer: latestReviewer(run),
    created_at: run.created_at,
    updated_at: run.updated_at,
    received_at: run.created_at,
    recommendation_completed_at: recommendationCompletedTime(run),
    entered_review_queue_at: run.status === "pending_human_review" ? run.updated_at : null,
    decided_at: latestReview?.created_at || null,
    remediation_pr_created_at: run.real_pr?.created_at || run.mock_pr?.created_at || null,
    run,
  };
}

function prReviewRows() {
  const rows = state.prReviews
    .filter((run) => ["terraform_pr", "manual_demo"].includes(run.source_type))
    .map(prReviewSummary);
  if (state.run?.id && ["terraform_pr", "manual_demo"].includes(state.run.source_type) && !rows.some((item) => item.id === state.run.id)) {
    rows.unshift(prReviewSummary(state.run));
  }
  return rows;
}

function prStatusMeta(status) {
  return {
    created: { label: "Investigating", className: "status-in-progress" },
    planning: { label: "Investigating", className: "status-in-progress" },
    investigating: { label: "Investigating", className: "status-in-progress" },
    verifying: { label: "Recommendation Processing", className: "status-in-progress" },
    pending_human_review: { label: "Awaiting Human Review", className: "status-awaiting-review" },
    needs_more_evidence: { label: "More Evidence Required", className: "status-needs-context" },
    abstained: { label: "Recommendation Ready", className: "status-allowed" },
    keep: { label: "Recommendation Ready", className: "status-allowed" },
    approved: { label: "Approved", className: "status-approved" },
    rejected: { label: "Rejected", className: "status-blocked" },
    blocked: { label: "Policy Blocked", className: "status-blocked" },
    pr_created: { label: "Remediation PR Created", className: "status-pr-created" },
    remediation_pr_created: { label: "Remediation PR Created", className: "status-pr-created" },
    approval_revoked: { label: "Approval Revoked", className: "status-warning" },
    reopened: { label: "Reopened", className: "status-awaiting-review" },
    remediation_proposal_prepared: { label: "Recommendation Ready", className: "status-allowed" },
    completed: { label: "Completed", className: "status-completed" },
    failed_safely: { label: "Failed Safely", className: "status-neutral" },
  }[status] || { label: runStatusLabel(status), className: "status-neutral" };
}

function prStatusBadge(status) {
  const meta = prStatusMeta(status);
  return statusBadge({ key: status, label: meta.label, className: meta.className });
}

function prReviewGroup(row) {
  if (["pending_human_review", "needs_more_evidence", "abstained", "keep"].includes(row.case_status)) return "needs-attention";
  if (["created", "planning", "investigating", "verifying"].includes(row.case_status)) return "in-progress";
  if (["approved", "rejected", "approval_revoked", "pr_created", "remediation_pr_created", "remediation_proposal_prepared", "completed"].includes(row.case_status)) return "completed";
  if (["blocked", "failed_safely"].includes(row.case_status)) return "blocked";
  return "all";
}

function riskRank(risk) {
  return { Critical: 5, High: 4, Medium: 3, Low: 2, Info: 1 }[labelFor(risk)] || 0;
}

function rowMatchesDateFilter(row) {
  const filter = state.prReviewFilters.dateRange;
  if (filter === "all") return true;
  if (filter === "completed") return prReviewGroup(row) === "completed";
  if (filter === "approved") return row.case_status === "approved";
  if (filter === "rejected") return row.case_status === "rejected";
  if (filter === "pr_created") return row.case_status === "pr_created";
  const created = parseTime(row.created_at);
  if (!created) return false;
  const ageMs = Date.now() - created.getTime();
  if (filter === "today") return new Date().toDateString() === created.toDateString();
  if (filter === "7d") return ageMs <= 7 * 86400000;
  if (filter === "30d") return ageMs <= 30 * 86400000;
  return true;
}

function filteredPrReviewRows() {
  const filters = state.prReviewFilters;
  if (state.prReviewsServerPaged) return prReviewRows();
  const search = filters.search.trim().toLowerCase();
  return prReviewRows().filter((row) => {
    const groupMatch = filters.group === "all" || prReviewGroup(row) === filters.group;
    const haystack = [row.repository, row.pull_request_number ? `#${row.pull_request_number}` : "", row.title, row.branch, row.base_branch, row.terraform_resource, row.recommendation, row.reviewer].join(" ").toLowerCase();
    return groupMatch &&
      (!search || haystack.includes(search)) &&
      (!filters.repository || row.repository === filters.repository) &&
      (!filters.status || row.case_status === filters.status) &&
      (!filters.recommendation || row.recommendation_key === filters.recommendation) &&
      (!filters.reviewer || row.reviewer === filters.reviewer) &&
      rowMatchesDateFilter(row);
  }).sort((a, b) => {
    if (filters.sort === "newest") return (parseTime(b.created_at)?.getTime() || 0) - (parseTime(a.created_at)?.getTime() || 0);
    if (filters.sort === "oldest") return (parseTime(a.created_at)?.getTime() || 0) - (parseTime(b.created_at)?.getTime() || 0);
    if (filters.sort === "savings_desc") return b.estimated_monthly_savings - a.estimated_monthly_savings;
    if (filters.sort === "risk_desc") return riskRank(b.risk) - riskRank(a.risk);
    if (filters.sort === "confidence_desc") return b.confidence - a.confidence;
    return (parseTime(b.updated_at)?.getTime() || 0) - (parseTime(a.updated_at)?.getTime() || 0);
  });
}

function updateSelectOptions(selectId, values, current, allLabel, format = (value) => value) {
  const select = $(selectId);
  if (!select) return;
  const nextValues = [...new Set(values.filter(Boolean))].sort();
  const previous = select.value || current || "";
  clear(select);
  const all = el("option", null, allLabel);
  all.value = "";
  select.appendChild(all);
  nextValues.forEach((value) => {
    const option = el("option", null, format(value));
    option.value = value;
    select.appendChild(option);
  });
  select.value = nextValues.includes(previous) ? previous : "";
}

function renderPrFilterCounts(rows) {
  const counts = { all: rows.length, "needs-attention": 0, "in-progress": 0, completed: 0, blocked: 0 };
  rows.forEach((row) => {
    const group = prReviewGroup(row);
    if (counts[group] !== undefined) counts[group] += 1;
  });
  Object.entries(counts).forEach(([key, count]) => {
    const node = $(`pr-filter-count-${key}`);
    if (node) node.textContent = String(count);
  });
  document.querySelectorAll("[data-pr-filter]").forEach((chip) => {
    const active = chip.dataset.prFilter === state.prReviewFilters.group;
    chip.classList.toggle("filter-chip-active", active);
    chip.setAttribute("aria-pressed", String(active));
  });
}

function clearPrFilters() {
  state.prReviewFilters = { ...state.prReviewFilters, group: "needs-attention", search: "", repository: "", status: "", recommendation: "", reviewer: "", dateRange: "all", sort: "updated_desc", page: 1 };
  ["pr-search-input", "pr-repository-filter", "pr-status-filter", "pr-recommendation-filter", "pr-reviewer-filter"].forEach((id) => { if ($(id)) $(id).value = ""; });
  $("pr-date-filter").value = "all";
  $("pr-sort-select").value = "updated_desc";
  if (state.prReviewsServerPaged) loadPRReviews({ preserveSelection: true });
  else renderPRReviewList();
}

function openPrReviewDetail(runOrRow) {
  const run = runOrRow.run || runOrRow;
  state.prReviewListScrollTop = window.scrollY || 0;
  state.run = run;
  state.outcome = null;
  state.selectedReviewContext = { source: "pr-reviews", type: "terraform_pr", runId: run.id };
  localStorage.setItem("ghostbusters:lastRunId", run.id);
  state.visibleEvents = run.audit_events || [];
  startAnimation(true);
  switchMode("simple");
  loadOutcomeForRun();
  showToast("Review loaded", "Opened PR review details.", "success");
}

async function openPrReviewById(runId) {
  const cached = state.prReviews.find((run) => run.id === runId);
  if (cached && !state.prReviewsServerPaged) return openPrReviewDetail(cached);
  const run = await api(`/api/runs/${runId}`);
  openPrReviewDetail(run);
}

function backToPrReviewList() {
  state.run = null;
  state.selectedReviewContext = null;
  closeReviewForm();
  renderAll();
  switchMode("simple");
  window.scrollTo({ top: state.prReviewListScrollTop || 0, behavior: "smooth" });
}

function renderPRReviewList() {
  const node = $("pr-review-list");
  if (!node) return;
  $("pr-timezone-note").textContent = `Times shown in ${userTimezone()}`;
  $("pr-review-error").hidden = !state.prReviewError;
  const notice = $("pr-new-review-notice");
  notice.hidden = state.newPrReviewCount < 1;
  $("pr-new-review-text").textContent = `${state.newPrReviewCount} new PR review${state.newPrReviewCount === 1 ? "" : "s"} available`;
  const allRows = prReviewRows();
  renderPrFilterCounts(allRows);
  updateSelectOptions("pr-repository-filter", allRows.map((row) => row.repository), state.prReviewFilters.repository, "All repositories");
  updateSelectOptions("pr-status-filter", allRows.map((row) => row.case_status), state.prReviewFilters.status, "All statuses", (value) => prStatusMeta(value).label);
  updateSelectOptions("pr-recommendation-filter", allRows.map((row) => row.recommendation_key), state.prReviewFilters.recommendation, "All recommendations", recommendationLabel);
  updateSelectOptions("pr-reviewer-filter", allRows.map((row) => row.reviewer), state.prReviewFilters.reviewer, "All reviewers");
  if (state.loading.prReviews) {
    renderSkeletonList(node, 5);
    $("pr-pagination-summary").textContent = "Loading reviews";
    return;
  }
  clear(node);
  const rows = filteredPrReviewRows();
  const pageSize = Number(state.prReviewFilters.pageSize || 20);
  const totalPages = state.prReviewsServerPaged ? Math.max(1, Math.ceil(state.prReviewTotal / pageSize)) : Math.max(1, Math.ceil(rows.length / pageSize));
  state.prReviewFilters.page = Math.min(Math.max(1, state.prReviewFilters.page), totalPages);
  const start = (state.prReviewFilters.page - 1) * pageSize;
  const pageRows = state.prReviewsServerPaged ? rows : rows.slice(start, start + pageSize);
  const columns = [
    { label: "Repository", render: (row) => append(el("div"), el("strong", "row-title", row.repository), el("span", "row-meta", row.branch)) },
    { label: "Pull Request", render: (row) => append(el("div"), el("strong", "row-title", row.pull_request_number ? `#${row.pull_request_number}` : "Prepared demo"), el("span", "row-meta", row.title)) },
    { label: "Change Summary", priority: "tablet", render: (row) => append(el("div"), el("span", null, row.change_summary), el("span", "row-meta", row.terraform_resource)) },
    { label: "Recommendation", priority: "tablet", render: (row) => row.recommendation },
    { label: "Potential Savings", priority: "mobile", render: (row) => row.estimated_monthly_savings === null ? "Cost estimate unavailable" : `${money(row.estimated_monthly_savings)}/month` },
    { label: "Risk", priority: "mobile", render: (row) => row.risk },
    { label: "Status", render: (row) => prStatusBadge(row.case_status) },
    { label: "Reviewer", priority: "tablet", render: (row) => row.reviewer },
    { label: "Updated", render: (row) => append(el("div"), timestampNode(row.updated_at, "Updated"), el("span", "row-meta", `Received ${relativeTime(row.received_at)}`)) },
    { label: "Action", render: (row) => {
      const button = el("button", "secondary compact", "View Review");
      button.type = "button";
      button.setAttribute("aria-label", `View review for ${row.repository} ${row.pull_request_number ? `PR #${row.pull_request_number}` : row.title}`);
      button.addEventListener("click", () => openPrReviewById(row.id));
      return button;
    } },
  ];
  if (!allRows.length) {
    const empty = el("div", "empty-state-inline");
    append(empty, el("h3", null, "No PR reviews yet"), el("p", "muted", "Terraform pull-request reviews will appear here after GitHub sends a supported webhook."));
    const actions = el("div", "empty-actions");
    const refresh = el("button", "secondary", "Refresh Reviews");
    refresh.type = "button";
    refresh.addEventListener("click", () => loadPRReviews({ preserveSelection: true }));
    const setup = el("button", "secondary", "View Integration Setup");
    setup.type = "button";
    setup.addEventListener("click", () => switchMode("overview"));
    append(actions, refresh, setup);
    append(empty, actions);
    node.appendChild(empty);
  } else if (!pageRows.length) {
    const empty = el("div", "empty-state-inline");
    const clearButton = el("button", "secondary", "Clear Filters");
    clearButton.type = "button";
    clearButton.addEventListener("click", clearPrFilters);
    append(empty, el("h3", null, "No reviews match these filters"), clearButton);
    node.appendChild(empty);
  } else {
    node.appendChild(responsiveTable(columns, pageRows, "No reviews match these filters."));
  }
  const totalRows = state.prReviewsServerPaged ? state.prReviewTotal : rows.length;
  $("pr-pagination-summary").textContent = totalRows
    ? `Showing ${start + 1}-${Math.min(start + pageSize, totalRows)} of ${totalRows} reviews`
    : "0 reviews";
  $("pr-prev-page-button").disabled = state.prReviewFilters.page <= 1;
  $("pr-next-page-button").disabled = state.prReviewFilters.page >= totalPages;
}

async function loadInitial() {
  state.loading.initial = true;
  renderAll();
  try {
    const [health, scenarios] = await Promise.all([api("/health"), api("/api/scenarios")]);
    $("api-pill").textContent = `System Online: ${health.status === "ok" ? "Yes" : labelFor(health.status)}`;
    state.scenarios = scenarios.scenarios || [];
    state.demoScenarios = state.scenarios.filter((scenario) => demoScenarioLabels[scenario]);
    const url = new URL(window.location.href);
    const invitationToken = url.searchParams.get("token");
    if (window.location.pathname.includes("/invitations/accept") && invitationToken) {
      await loadInvitationPreview(invitationToken);
    } else {
      await loadCurrentUser({ showAuthOnFailure: true });
    }
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
  loadPRReviews();
  loadReviewQueue();
  loadCloudHunts();
  loadGoals();
  loadMembers();
  loadActivity();
  loadOverview();
  renderAll();
}

async function loadInvitationPreview(token) {
  state.invitationToken = token;
  try {
    state.invitationPreview = await api(`/api/invitations/validate?token=${encodeURIComponent(token)}`);
    openAuthModal("accept");
    renderInvitationPreview();
  } catch (error) {
    state.invitationPreview = { valid: false, message: friendlyError(error, "Invitation is invalid.") };
    openAuthModal("accept");
    renderInvitationPreview();
  }
}

function openAuthModal(mode = "signin") {
  const switching = state.authMode !== mode && !$("auth-modal-backdrop")?.hidden;
  state.authMode = mode;
  const appShell = document.querySelector(".app-shell");
  if (appShell) appShell.hidden = true;
  if ($("auth-modal-backdrop")) $("auth-modal-backdrop").hidden = false;
  renderAuthModal(switching);
}

function closeAuthModal() {
  const authenticated = Boolean(state.currentUser?.authenticated);
  if ($("auth-modal-backdrop")) $("auth-modal-backdrop").hidden = authenticated;
  const appShell = document.querySelector(".app-shell");
  if (appShell) appShell.hidden = !authenticated;
}

function renderAuthModal(switching = false) {
  const accepting = state.authMode === "accept";
  const signin = state.authMode !== "register" && !accepting;
  if ($("signin-form")) {
    $("signin-form").hidden = !signin;
    $("signin-form").classList.toggle("auth-form-active", signin);
  }
  if ($("register-form")) {
    $("register-form").hidden = signin || accepting;
    $("register-form").classList.toggle("auth-form-active", !signin && !accepting);
  }
  if ($("accept-invitation-form")) {
    $("accept-invitation-form").hidden = !accepting;
    $("accept-invitation-form").classList.toggle("auth-form-active", accepting);
  }
  if ($("auth-modal-title")) $("auth-modal-title").textContent = accepting ? "Accept invitation" : signin ? "Sign in to GhostOps" : "Create a workspace";
  if ($("auth-modal-kicker")) $("auth-modal-kicker").textContent = accepting ? "Invitation" : signin ? "Workspace access" : "New workspace";
  if (switching) setMessage("auth-message", "");
}

function renderInvitationPreview() {
  const node = $("invite-accept-summary");
  if (!node) return;
  clear(node);
  const preview = state.invitationPreview;
  if (!preview?.valid) {
    append(node, el("strong", null, "Invitation unavailable"), el("span", "muted", preview?.message || "This invitation cannot be accepted."));
    $("accept-submit-button").disabled = true;
    return;
  }
  $("accept-submit-button").disabled = false;
  append(
    node,
    el("span", "muted", "You've been invited to join"),
    el("strong", null, preview.organization_name),
    dataList([
      ["Assigned role", preview.role_label],
      ["Invited email", preview.email],
      ["Approval permission", preview.approval_permission_enabled ? "Enabled" : "Disabled"],
      ["Expires", exactTimestamp(preview.expires_at)],
    ])
  );
}

async function submitSignin(event) {
  event.preventDefault();
  setMessage("auth-message", "Signing in...", true);
  try {
    state.currentUser = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: $("signin-email").value, password: $("signin-password").value }),
    });
    if (state.invitationToken) {
      state.currentUser = await api("/api/invitations/accept", {
        method: "POST",
        body: JSON.stringify({ token: state.invitationToken }),
      });
      state.invitationToken = null;
      state.invitationPreview = null;
    }
    closeAuthModal();
    renderAll();
    await Promise.all([loadPRReviews(), loadReviewQueue()]);
    showToast("Signed in", `Welcome back, ${userDisplayName()}.`, "success");
  } catch (error) {
    setMessage("auth-message", friendlyError(error, "Sign in failed."));
  }
}

async function submitRegister(event) {
  event.preventDefault();
  setMessage("auth-message", "Creating workspace...", true);
  try {
    const registered = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        display_name: $("register-name").value,
        email: $("register-email").value,
        password: $("register-password").value,
        organization_name: $("register-organization").value,
        timezone: $("register-timezone").value || "UTC",
      }),
    });
    state.currentUser = registered;
    await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => ({}));
    state.currentUser = null;
    if ($("signin-email")) $("signin-email").value = $("register-email").value;
    openAuthModal("signin");
    setMessage("auth-message", "Workspace created. Sign in with your credentials to enter.", true);
    showToast("Workspace created", "Sign in to enter your workspace.", "success");
  } catch (error) {
    setMessage("auth-message", friendlyError(error, "Workspace creation failed."));
  }
}

async function submitAcceptInvitation(event) {
  event.preventDefault();
  if (!state.invitationToken) return setMessage("auth-message", "Invitation token is missing.");
  setMessage("auth-message", "Accepting invitation...", true);
  try {
    state.currentUser = await api("/api/invitations/accept", {
      method: "POST",
      body: JSON.stringify({
        token: state.invitationToken,
        display_name: $("accept-display-name").value || null,
        password: $("accept-password").value || null,
        confirm_password: $("accept-confirm-password").value || null,
      }),
    });
    closeAuthModal();
    renderAll();
    await Promise.all([loadPRReviews(), loadReviewQueue(), loadMembers()]);
    showToast("Invitation accepted", `Welcome to ${organizationName()}.`, "success");
  } catch (error) {
    setMessage("auth-message", friendlyError(error, "Invitation could not be accepted."));
  }
}

function invitationStatusLabel(status) {
  return labelFor(status || "pending");
}

function roleValueLabel(role) {
  return {
    OWNER: "Owner",
    ADMIN: "Admin",
    REVIEWER: "Reviewer",
    VIEWER: "Viewer",
  }[role] || labelFor(role);
}

async function loadMembers() {
  if (!state.currentUser?.authenticated || !hasPermission("members.read")) return;
  try {
    const [members, invitations] = await Promise.all([api("/api/members"), api("/api/invitations")]);
    state.members = members;
    state.invitations = invitations;
    renderMembers();
    setMessage("members-message", "");
  } catch (error) {
    const message = error?.status === 401 ? "Reviewer details are unavailable. Retry." : friendlyError(error, "Members are unavailable. Retry.");
    setMessage("members-message", message);
    showToast("Member details unavailable", message, "error");
  }
}

async function loadPRReviews({ preserveSelection = true, showNotice = false } = {}) {
  state.loading.prReviews = true;
  renderPRReviewList();
  try {
    const filters = state.prReviewFilters;
    const params = typeof URLSearchParams === "function" ? new URLSearchParams({ source_type: "terraform_pr", group: filters.group, page: String(filters.page), page_size: String(filters.pageSize), sort: filters.sort }) : null;
    if (params && filters.status) params.set("status", filters.status);
    if (params && filters.repository) params.set("repository", filters.repository);
    if (params && filters.reviewer) params.set("reviewer", filters.reviewer);
    if (params && filters.search.trim()) params.set("search", filters.search.trim());
    if (filters.dateRange !== "all") {
      const days = filters.dateRange === "today" ? 1 : Number(filters.dateRange.replace("d", ""));
      if (params && Number.isFinite(days)) params.set("created_from", new Date(Date.now() - days * 86400000).toISOString());
    }
    const previousTotal = state.prReviewTotal || 0;
    const payload = await api(params ? `/api/runs?${params.toString()}` : "/api/runs");
    const serverPaged = !Array.isArray(payload) && Array.isArray(payload.items);
    const runs = serverPaged ? payload.items : (Array.isArray(payload) ? payload : (await api("/api/runs")));
    state.prReviewsServerPaged = serverPaged;
    state.prReviewTotal = serverPaged ? payload.total : runs.length;
    state.prReviewError = "";
    const previousIds = state.knownPrReviewIds;
    const nextIds = new Set((runs || []).filter((run) => ["terraform_pr", "manual_demo"].includes(run.source_type)).map((run) => run.id));
    const newIds = [...nextIds].filter((id) => previousIds.size && !previousIds.has(id) && id !== state.run?.id);
    state.prReviews = runs || [];
    state.knownPrReviewIds = nextIds;
    const countDelta = serverPaged && previousTotal ? (payload.total - previousTotal) : Math.max(0, runs.length - previousIds.size);
    const hasIncomingReviews = newIds.length > 0 || runs.length > previousIds.size || (showNotice && state.run && runs.length > 1);
    state.newPrReviewCount = showNotice && preserveSelection && state.run && hasIncomingReviews ? Math.max(1, newIds.length, countDelta) : 0;
    if (state.currentUser?.authenticated && $("ui-message")?.textContent === "Authentication required.") setMessage("ui-message", "");
    setMessage("pr-auxiliary-message", "");
    if ($("pr-auxiliary-retry-button")) $("pr-auxiliary-retry-button").hidden = true;
    // Keep the full selected run untouched. List refreshes must not disturb an open
    // case or any unsent decision form state.
    renderPRReviewList();
  } catch (error) {
    if (error?.status === 401) {
      state.authRequired = true;
      state.currentUser = null;
      renderIdentity();
      openAuthModal("signin");
      setMessage("ui-message", "Authentication required.");
      state.prReviewError = "";
      return;
    }
    const message = friendlyError(error, "Failed to load PR reviews.");
    state.prReviewError = message;
    setMessage("ui-message", message);
    const errorNode = $("pr-review-error");
    if (errorNode) errorNode.hidden = false;
    showToast("PR review load failed", message, "error");
  } finally {
    state.loading.prReviews = false;
    renderPRReviewList();
    renderOverview();
  }
}

async function loadGoals() {
  try {
    state.goals = await api("/api/goals");
    if (state.selectedGoal && !state.goals.some((goal) => goal.id === state.selectedGoal.id)) state.selectedGoal = null;
    renderGoalList();
  } catch (error) { setMessage("goal-message", friendlyError(error, "Failed to load goals.")); }
}

function openGoalsHome() {
  stopGoalPolling();
  state.selectedGoal = null;
  state.goalEvents = [];
  state.goalCreationStage = "idle";
  switchMode("goals");
  renderGoalExecution();
  void loadGoals();
}

async function loadOutcomeForRun() {
  if (!state.run) return;
  try { const data = await api("/api/outcomes"); state.outcome = (data.items || []).find((item) => item.case_id === state.run.id) || null; renderOutcomeVerification(); } catch { state.outcome = null; }
}
function renderOutcomeVerification() {
  const panel = $("outcome-verification-panel"); if (!panel) return;
  const eligible = ["pr_created", "remediation_pr_created", "approved"].includes(state.run?.status) && (state.run?.real_pr || state.run?.mock_pr);
  panel.hidden = !eligible; if (!eligible) return;
  const item = state.outcome; $("outcome-prediction").textContent = item ? money(item.prediction_snapshot?.predicted_monthly_savings) + "/month" : "Not recorded";
  $("outcome-deployment").textContent = item?.deployment_confirmed_at ? "Confirmed" : "Not confirmed";
  $("outcome-status").textContent = item ? labelFor(item.verification_status) : "Not started";
  const observed = item?.savings_variance?.observed_monthly_savings; $("outcome-observed").textContent = observed === null || observed === undefined ? "Not verified" : money(observed) + "/month";
  $("outcome-conclusion").textContent = item?.conclusion || "Savings remain unverified until deployment and post-change evidence are available.";
  $("outcome-start-button").hidden = Boolean(item); $("outcome-deploy-button").hidden = !item || Boolean(item.deployment_confirmed_at); $("outcome-human-button").hidden = item?.verification_status !== "regression_detected";
}
async function startOutcomeVerification() { try { state.outcome = await api(`/api/runs/${state.run.id}/outcome-verification`, { method: "POST", body: JSON.stringify({ idempotency_key: `outcome-${state.run.id}` }) }); renderOutcomeVerification(); } catch (error) { showToast("Verification unavailable", friendlyError(error), "error"); } }
async function confirmOutcomeDeployment() { try { state.outcome = await api(`/api/outcomes/${state.outcome.id}/deployment-confirmation`, { method: "POST", body: JSON.stringify({ expected_version: state.outcome.version, idempotency_key: `deploy-${state.outcome.id}` }) }); renderOutcomeVerification(); } catch (error) { showToast("Deployment confirmation failed", friendlyError(error), "error"); } }
async function refreshOutcomeEvidence() { if (!state.outcome) return; try { state.outcome = await api(`/api/outcomes/${state.outcome.id}/refresh`, { method: "POST", body: JSON.stringify({ expected_version: state.outcome.version, idempotency_key: `refresh-${state.outcome.id}` }) }); renderOutcomeVerification(); } catch (error) { showToast("Evidence refresh failed", friendlyError(error), "error"); } }

async function loadAWSConfig() {
  try { state.awsConfig = await api("/api/integrations/aws/config"); renderAWSConfig(); } catch (error) { setMessage("aws-message", friendlyError(error, "AWS settings unavailable.")); }
}

async function loadGitHubConfig() {
  try { state.githubConfig = await api("/api/integrations/github/config"); renderGitHubConfig(); renderGoalRepositoryScope(); } catch (error) { setMessage("github-message", friendlyError(error, "GitHub settings unavailable.")); }
}

function renderGitHubConfig() {
  const config = state.githubConfig; if (!config || !$("github-enabled-select")) return;
  bindGitHubConnectButton();
  $("github-enabled-select").value = String(Boolean(config.enabled));
  $("github-installation-input").value = config.installation_identity || "";
  $("github-repositories-input").value = (config.allowed_repositories || []).join(",");
  $("github-last-checked").textContent = config.last_validated ? exactTimestamp(config.last_validated) : "Not checked";
  $("github-permission-warnings").textContent = config.last_failure_summary || "None recorded";
  if ($("github-installation-id")) $("github-installation-id").textContent = config.installation_id || "Not connected";
  if ($("github-account-id")) $("github-account-id").textContent = config.account_login ? `${config.account_login}${config.account_type ? ` (${config.account_type})` : ""}` : config.installation_identity || "Not connected";
  if ($("github-repository-list")) $("github-repository-list").textContent = (config.connected_repositories || []).map((item) => item.full_name).join(", ") || "None connected";
  const connected = Boolean(config.installation_id);
  if ($("github-connected-state")) $("github-connected-state").hidden = !connected;
  if ($("github-disconnected-state")) $("github-disconnected-state").hidden = connected;
  const validationWarning = connected && config.last_failure_summary;
  setStatusBadge("github-connection-status", { label: connected ? (validationWarning ? "Connected with warning" : "Connected") : "Not connected", className: connected ? (validationWarning ? "status-warning" : "status-approved") : "status-neutral" });
  renderRepositorySettings();
  const editable = hasPermission("integrations.github.manage"); $("github-save-button").hidden = !editable; $("github-enabled-select").disabled = !editable; $("github-installation-input").readOnly = !editable; $("github-repositories-input").readOnly = !editable;
}

function bindGitHubConnectButton() {
  const githubConnectButton = document.getElementById("github-connect-button");
  if (!githubConnectButton || githubConnectButton.dataset.githubConnectBound === "true") return;
  githubConnectButton.dataset.githubConnectBound = "true";
  githubConnectButton.addEventListener("click", (event) => {
    event.preventDefault();
    if (githubConnectButton.disabled) return;
    githubConnectButton.disabled = true;
    githubConnectButton.textContent = "Connecting…";
    try {
      window.location.assign("/api/integrations/github/connect");
    } catch (error) {
      githubConnectButton.disabled = false;
      githubConnectButton.textContent = "Connect GitHub";
      setMessage("github-message", friendlyError(error, "GitHub connection could not be started."));
    }
  });
}
async function manageGitHubRepositories() { try { const result = await api("/api/integrations/github/repositories"); state.githubConfig = await api("/api/integrations/github/config"); renderGitHubConfig(); setMessage("github-message", `${result.count || 0} repositories available from the GitHub installation.`, true); } catch (error) { setMessage("github-message", friendlyError(error, "Repositories could not be loaded.")); } }
async function disconnectGitHub() { if (!window.confirm("Disconnect the GitHub App from this workspace? Historical reviews and audit records will remain.")) return; try { state.githubConfig = await api("/api/integrations/github/disconnect", { method: "POST", body: "{}" }); renderGitHubConfig(); setMessage("github-message", "GitHub disconnected. Historical reviews remain available.", true); } catch (error) { setMessage("github-message", friendlyError(error, "GitHub could not be disconnected.")); } }

async function saveGitHubConfig() {
  try { state.githubConfig = await api("/api/integrations/github/config", { method: "PATCH", body: JSON.stringify({ enabled: $("github-enabled-select").value === "true", installation_identity: $("github-installation-input").value.trim() || null, allowed_repositories: $("github-repositories-input").value.split(",").map((item) => item.trim()).filter(Boolean) }) }); renderGitHubConfig(); setMessage("github-message", "GitHub settings saved. Token material was not stored.", true); } catch (error) { setMessage("github-message", friendlyError(error, "GitHub settings could not be saved.")); }
}

async function validateGitHubConnection() {
  return withButtonState("github-validate-button", "Validating...", async () => {
    state.githubValidation = await api("/api/integrations/github/validate", { method: "POST", body: "{}" });
    const result = state.githubValidation;
    state.githubConfig = await api("/api/integrations/github/config");
    renderGitHubConfig();
    if (!result.connected && state.githubConfig.installation_id) setMessage("github-message", "Validation failed; showing last known repository access.");
    else setMessage("github-message", result.connected ? "GitHub identity validated for read-only context." : "GitHub validation failed safely.", result.connected);
  }, "Validated").catch((error) => setMessage("github-message", friendlyError(error, "GitHub validation failed.")));
}

async function loadJiraConfig() {
  try { state.jiraConfig = await api("/api/integrations/jira/config"); renderJiraConfig(); } catch (error) { setMessage("jira-message", friendlyError(error, "Jira settings unavailable.")); }
}
function renderJiraConfig() {
  const config = state.jiraConfig || {}; const validation = state.jiraValidation || {};
  if ($("jira-enabled-select")) $("jira-enabled-select").value = String(Boolean(config.enabled));
  if ($("jira-base-url-input")) $("jira-base-url-input").value = config.base_url || "";
  if ($("jira-projects-input")) $("jira-projects-input").value = (config.allowed_projects || []).join(", ");
  if ($("jira-connection-status")) { $("jira-connection-status").textContent = validation.connected ? "Connected" : config.last_validated ? "Unavailable" : "Not checked"; }
  if ($("jira-account-id")) $("jira-account-id").textContent = validation.account_identity || "Not checked";
  if ($("jira-project-list")) $("jira-project-list").textContent = (validation.accessible_projects || []).join(", ") || "Not checked";
  if ($("jira-last-checked")) $("jira-last-checked").textContent = config.last_validated ? exactTimestamp(config.last_validated) : "Not checked";
  if ($("jira-permission-warnings")) $("jira-permission-warnings").textContent = (validation.permission_warnings || []).join("; ") || "None recorded";
  const editable = hasPermission("integrations.jira.manage"); if ($("jira-save-button")) $("jira-save-button").hidden = !editable; if ($("jira-enabled-select")) $("jira-enabled-select").disabled = !editable; if ($("jira-base-url-input")) $("jira-base-url-input").readOnly = !editable; if ($("jira-projects-input")) $("jira-projects-input").readOnly = !editable;
}
async function saveJiraConfig() {
  try { state.jiraConfig = await api("/api/integrations/jira/config", { method: "PATCH", body: JSON.stringify({ enabled: $("jira-enabled-select").value === "true", base_url: $("jira-base-url-input").value.trim() || null, allowed_projects: $("jira-projects-input").value.split(",").map((item) => item.trim()).filter(Boolean) }) }); renderJiraConfig(); setMessage("jira-message", "Jira settings saved. Token material remains server-side.", true); } catch (error) { setMessage("jira-message", friendlyError(error, "Jira settings could not be saved.")); }
}
async function validateJiraConnection() {
  return withButtonState("jira-validate-button", "Validating...", async () => {
    const result = await api("/api/integrations/jira/validate", { method: "POST", body: "{}" }); state.jiraValidation = result; state.jiraConfig = await api("/api/integrations/jira/config"); renderJiraConfig(); setMessage("jira-message", result.connected ? "Jira identity validated for read-only context." : "Jira validation failed safely.", result.connected);
  }, "Validated").catch((error) => setMessage("jira-message", friendlyError(error, "Jira validation failed.")));
}

async function loadCloudSchedules() {
  try { state.cloudSchedules = await api("/api/cloud/schedules"); renderCloudSchedules(); } catch (error) { setMessage("schedule-message", friendlyError(error, "Cloud Hunt schedules unavailable.")); }
}
async function loadWorkspaceSettings() { try { state.workspace = await api("/api/workspace"); renderWorkspaceSettings(); } catch (error) { setMessage("workspace-message", friendlyError(error, "Workspace settings unavailable.")); } }
async function loadDemoReadiness() { try { state.demoReadiness = await api("/api/demo/readiness"); renderDemoReadiness(); } catch (error) { state.demoReadiness = { known_warnings: [friendlyError(error, "Demo readiness unavailable.")] }; renderDemoReadiness(); } }
function renderDemoReadiness() { const data = state.demoReadiness; if (!data) return; const summary = $("demo-readiness-summary"); clear(summary); [["Authentication", data.authentication?.authenticated ? "Authenticated" : "Demo session"], ["Pending approvals", data.pending_approvals ?? 0], ["Scheduler", data.scheduler?.enabled ? "Enabled" : "Disabled"], ["Recent successful run", data.recent_successful_run ? labelFor(data.recent_successful_run.status) : "None"]].forEach(([label, value]) => summary.appendChild(append(el("article", "panel summary-card"), el("span", null, label), el("strong", "metric-value", String(value))))); const health = $("demo-readiness-health"); clear(health); [data.health && `Database: ${labelFor(data.health.database)}`, data.health && `Redis: ${labelFor(data.health.redis)}`, data.github_webhook && `GitHub webhook: ${data.github_webhook.signature_ready ? "Signature ready" : "Signature not configured"}`, data.data_modes && `Fixtures: ${data.data_modes.fixtures_available ? "Available and labeled" : "Unavailable"}`, data.scheduler && `Scheduler: ${data.scheduler.schedule_count} schedules · ${data.scheduler.redis_coordination ? "distributed coordination" : "single-process coordination"}`, data.scheduler?.enabled === false && "Scheduled execution is disabled in this deployment. Manual Run Now remains available."].filter(Boolean).forEach((text) => health.appendChild(el("p", "row-detail", text))); const integrations = $("demo-readiness-integrations"); clear(integrations); Object.entries(data.integrations || {}).forEach(([name, item]) => integrations.appendChild(el("p", "row-detail", `${labelFor(name)}: ${labelFor(item.status)}${item.warnings?.length ? ` · ${item.warnings.join("; ")}` : ""}`))); const warnings = $("demo-readiness-warnings"); clear(warnings); (data.known_warnings || []).forEach((warning) => warnings.appendChild(el("p", "row-detail", warning))); if (!(data.known_warnings || []).length) warnings.appendChild(el("p", "muted", "No known warnings recorded.")); }
function renderWorkspaceSettings() {
  const item = state.workspace; if (!item) return; const organization = item.organization || {};
  $("workspace-name-input").value = organization.name || ""; $("workspace-timezone-input").value = organization.timezone || "UTC"; $("workspace-id-input").value = organization.id || "Not recorded"; $("workspace-created-input").value = exactTimestamp(organization.created_at); $("workspace-settings-status").textContent = "Functional";
  const editable = hasPermission("workspace.manage"); $("workspace-save-button").hidden = !editable; $("workspace-name-input").readOnly = !editable; $("workspace-timezone-input").readOnly = !editable;
}
async function saveWorkspaceSettings() { try { state.workspace = await api("/api/workspace", { method: "PATCH", body: JSON.stringify({ name: $("workspace-name-input").value.trim(), timezone: $("workspace-timezone-input").value.trim(), expected_version: state.workspace.version }) }); renderWorkspaceSettings(); setMessage("workspace-message", "Workspace settings saved.", true); } catch (error) { setMessage("workspace-message", friendlyError(error, "Workspace settings could not be saved.")); await loadWorkspaceSettings(); } }
function renderRolesAccess() {
  const node = $("roles-access-list"); if (!node) return; clear(node); const roles = { OWNER: ["Workspace management", "Members and roles", "Integrations", "Approvals", "Activity and audit"], ADMIN: ["Members and roles", "Integrations", "Approvals", "Activity and audit"], REVIEWER: ["PR Reviews", "Cloud Hunt read", "Approvals when granted", "Activity and audit"], VIEWER: ["Read-only workspace", "PR Reviews read", "Cloud Hunt read", "Overview read"] };
  Object.entries(roles).forEach(([role, permissions]) => node.appendChild(el("p", "row-detail", `${roleValueLabel(role)}: ${permissions.join(", ")}`)));
}
function renderPoliciesSettings() { const node = $("policies-settings-list"); if (!node) return; clear(node); ["Production protection: Functional", "Destructive-action block: Functional", "Mandatory human approval: Functional", "Evidence freshness threshold: Functional", "Confidence threshold: Functional", "Policy editing: Disabled until a safe policy editor is available"].forEach((item) => node.appendChild(el("p", "row-detail", item))); }
function renderSecuritySettings() { const node = $("security-settings-list"); if (!node) return; clear(node); ["Session security: Functional", "Invitation expiry: Configured server-side", "Webhook signatures: Validated when configured", "Secrets: Kept in server environment; never displayed", "Audit and Activity Log: View in workspace navigation"].forEach((item) => node.appendChild(el("p", "row-detail", item))); }
function renderRepositorySettings() { const node = $("repositories-settings-list"); if (!node) return; clear(node); const config = state.githubConfig || {}; node.appendChild(el("p", "row-detail", `Allowlist: ${(config.allowed_repositories || []).join(", ") || "All configured repositories"}`)); node.appendChild(el("p", "row-detail", `Validation: ${state.githubValidation?.connected ? "Connected" : config.last_validated ? "Unavailable" : "Not checked"}`)); node.appendChild(el("p", "row-detail", `Last sync: ${exactTimestamp(config.last_successful_collection)}`)); }
function renderCloudSchedules() {
  const node = $("schedule-list"); if (!node) return; clear(node);
  if (!state.cloudSchedules.length) { node.appendChild(el("p", "muted", "No Cloud Hunt schedules yet.")); return; }
  const manageable = hasPermission("cloud_hunts.schedule.manage"); $("schedule-create-button").hidden = !manageable;
  state.cloudSchedules.forEach((schedule) => {
    const row = el("div", "list-row");
    append(row, el("strong", null, schedule.name), el("span", "muted", `${labelFor(schedule.provider_scope)} · ${labelFor(schedule.recurrence)} · ${schedule.timezone}`), timestampNode(schedule.next_run, "Next run"));
    const toggle = el("button", "secondary compact", schedule.enabled ? "Disable" : "Enable"); toggle.addEventListener("click", async () => { try { await api(`/api/cloud/schedules/${schedule.id}/enabled`, { method: "POST", body: JSON.stringify({ enabled: !schedule.enabled, expected_version: schedule.version }) }); await loadCloudSchedules(); } catch (error) { setMessage("schedule-message", friendlyError(error, "Schedule update failed.")); } });
    const run = el("button", "secondary compact", "Run Now"); run.addEventListener("click", async () => { try { await api(`/api/cloud/schedules/${schedule.id}/run-now`, { method: "POST", body: "{}" }); await loadCloudSchedules(); setMessage("schedule-message", "Cloud Hunt started from schedule.", true); } catch (error) { setMessage("schedule-message", friendlyError(error, "Scheduled hunt could not start.")); } });
    toggle.hidden = !manageable; run.hidden = !manageable; append(row, toggle, run); node.appendChild(row);
  });
}
async function createCloudSchedule() {
  try { await api("/api/cloud/schedules", { method: "POST", body: JSON.stringify({ name: $("schedule-name-input").value.trim(), provider_scope: $("schedule-provider-select").value, inventory_source: $("schedule-source-select").value, recurrence: $("schedule-recurrence-select").value, timezone: $("schedule-timezone-input").value.trim() || "UTC", hour: Number($("schedule-hour-input").value), minute: Number($("schedule-minute-input").value) }) }); await loadCloudSchedules(); setMessage("schedule-message", "Cloud Hunt schedule created.", true); } catch (error) { setMessage("schedule-message", friendlyError(error, "Schedule could not be created.")); }
}

async function collectGitHubContext() {
  if (!state.run?.id) return;
  return withButtonState("collect-github-context-button", "Collecting...", async () => {
    state.run = await api(`/api/runs/${state.run.id}/github-context`, { method: "POST", body: "{}" });
    renderAll();
    setMessage("ui-message", "Read-only GitHub context collected.", true);
  }, "Collected").catch((error) => showToast("GitHub context failed", friendlyError(error), "error"));
}

function renderAWSConfig() {
  const config = state.awsConfig; if (!config || !$("aws-enabled-select")) return;
  $("aws-enabled-select").value = String(Boolean(config.enabled));
  $("aws-regions-input").value = (config.regions || []).join(",");
  $("aws-lookback-input").value = config.cloudwatch_lookback_days || 14;
  const status = config.connection_status || "not_connected";
  const statusLabels = { not_connected: "Not connected", onboarding_pending: "Setup in progress", connected: "Connected", failed: "Connection needs attention" };
  setStatusBadge("aws-connection-status", { label: statusLabels[status] || "Not checked", className: status === "connected" ? "status-approved" : status === "failed" ? "status-blocked" : "status-neutral" });
  $("aws-account-id").textContent = config.account_id || (status === "onboarding_pending" ? "Awaiting AWS setup" : "Not connected");
  $("aws-last-checked").textContent = config.last_validated ? exactTimestamp(config.last_validated) : "Not checked";
  $("aws-last-success").textContent = config.last_successful_collection ? exactTimestamp(config.last_successful_collection) : "Not recorded";
  $("aws-permission-warnings").textContent = config.last_failure_summary || "None recorded";
  const editable = hasPermission("integrations.aws.manage"); $("aws-save-button").hidden = !editable; $("aws-connect-button").hidden = !editable; $("aws-connect-button").disabled = !editable; $("aws-enabled-select").disabled = !editable; $("aws-regions-input").readOnly = !editable; $("aws-lookback-input").readOnly = !editable; $("aws-validate-button").disabled = !hasPermission("integrations.aws.read");
}

async function saveAWSConfig() {
  try { state.awsConfig = await api("/api/integrations/aws/config", { method: "PATCH", body: JSON.stringify({ enabled: $("aws-enabled-select").value === "true", regions: $("aws-regions-input").value.split(",").map((item) => item.trim()).filter(Boolean), cloudwatch_lookback_days: Number($("aws-lookback-input").value) }) }); renderAWSConfig(); setMessage("aws-message", "AWS settings saved. No credentials were stored.", true); } catch (error) { setMessage("aws-message", friendlyError(error, "AWS settings could not be saved.")); }
}

async function validateAWSConnection() {
  return withButtonState("aws-validate-button", "Validating...", async () => {
    state.awsValidation = await api("/api/integrations/aws/validate", { method: "POST", body: "{}" });
    const result = state.awsValidation;
    setStatusBadge("aws-connection-status", { label: result.connected ? "Connected" : "Unavailable", className: result.connected ? "status-approved" : "status-blocked" });
    $("aws-account-id").textContent = result.account_id || "Not available";
    $("aws-last-checked").textContent = exactTimestamp(result.checked_at);
    $("aws-permission-warnings").textContent = [...(result.permission_warnings || []), ...(result.missing_permissions || [])].join("; ") || "None recorded";
    setMessage("aws-message", result.connected ? "AWS identity validated. Real collection remains read-only." : "AWS validation failed safely. Fixture mode was not used.", result.connected);
  }, "Validated").catch((error) => setMessage("aws-message", friendlyError(error, "AWS validation failed.")));
}

async function connectAWSAccount() {
  const button = $("aws-connect-button");
  if (!button || button.disabled) return;
  button.disabled = true;
  const originalLabel = button.textContent;
  button.textContent = "Opening AWS...";
  try { window.location.assign("/api/integrations/aws/connect"); }
  catch (error) {
    button.disabled = false;
    button.textContent = originalLabel;
    setMessage("aws-message", friendlyError(error, "AWS setup could not be opened."));
  }
}

async function selectGoal(goalId, switchToView = true, seed = null) {
  if (state.goalPollTimer) window.clearTimeout(state.goalPollTimer);
  state.goalPollTimer = null;
  const summary = seed || state.goals.find((goal) => String(goal.id) === String(goalId));
  if (summary) {
    state.selectedGoal = normalizeGoalResponse(summary);
    state.goalEvents = [];
    state.goalTab = "plan";
    localStorage.setItem("ghostbusters:lastGoalId", goalId);
    if (switchToView) switchMode("goals");
    renderGoalExecution();
  }
  try {
    const [goal, events] = await withTimeout(Promise.all([
      api(`/api/goals/${goalId}`),
      api(`/api/goals/${goalId}/events`),
    ]), 10000, "Goal progress is temporarily unavailable.");
    state.selectedGoal = normalizeGoalResponse(goal);
    state.goalEvents = Array.isArray(events) ? events : [];
    state.goalPollFailures = 0;
    state.goalTab = ["completed", "approved", "pr_created", "remediation_pr_created"].includes(state.selectedGoal.status) ? "outcome" : "plan";
    localStorage.setItem("ghostbusters:lastGoalId", goalId);
    if (switchToView) switchMode("goals");
    renderGoalExecution();
    beginGoalPolling(goalId);
    return state.selectedGoal;
  } catch (error) {
    state.goalPollFailures += 1;
    logGoalDiagnostic("Goal progress refresh failed", error);
    setMessage("goal-message", "Live updates temporarily unavailable. Showing last known state.");
    if ($("goal-retry-button")) $("goal-retry-button").hidden = false;
    renderGoalExecution();
    if (state.selectedGoal?.id === goalId) beginGoalPolling(goalId);
    return null;
  }
}

async function refreshGoalJourney() { return state.selectedGoal ? selectGoal(state.selectedGoal.id, false) : loadGoals(); }

async function retryGoalAction() {
  if (state.selectedGoal) return refreshGoalJourney();
  return confirmGoal();
}

async function startGoal() {
  if (state.goalValidationInFlight) return;
  state.goalValidationInFlight = true;
  $("goal-create-panel")?.appendChild($("goal-message"));
  if ($("goal-edit-button")) $("goal-edit-button").textContent = "Edit Goal";
  const goal = $("goal-input").value.trim();
  if ($("goal-retry-button")) $("goal-retry-button").hidden = true;
  if (goal.length < 12) { state.goalValidationInFlight = false; return setMessage("goal-message", "This goal is too broad to execute safely. Add an outcome, scope, or safety boundary."); }
  if (/delete all|destroy everything|make everything cheaper/i.test(goal)) { state.goalValidationInFlight = false; return setMessage("goal-message", "This goal is too broad to execute safely. Try: Identify avoidable production cloud spending without making infrastructure changes."); }
  let validation;
  try {
    validation = await withButtonState("goal-start-button", "Groq is reviewing the goal...", () => withTimeout(api("/api/goals/validate", { method: "POST", body: JSON.stringify({ goal, scope: $("goal-scope-input").value || "Workspace scope", repositories: selectedGoalRepositories(), require_approval: true, constraints: ["No direct infrastructure mutation", "Human approval required"] }) }), 10000, "Goal validation timed out."));
  } catch (error) {
    setMessage("goal-message", error?.status === 503 ? "Goal analysis is temporarily unavailable. Retry once." : goalErrorMessage(error));
    return;
  } finally {
    state.goalValidationInFlight = false;
  }
  if (validation.status === "needs_revision" && Array.isArray(validation.clarification_questions) && validation.clarification_questions.length) return showGoalClarifications(goal, validation);
  if (validation.status !== "accepted") return setMessage("goal-message", validation.reason || "This goal needs revision before it can start.");
  state.goalDraft = { goal: validation.normalized_goal || goal, scope: $("goal-scope-input").value || "Workspace scope", repositories: selectedGoalRepositories(), validation, idempotencyKey: `goal:${Date.now()}:${Math.random().toString(16).slice(2)}` };
  state.goalCreationStage = "confirm";
  $("goal-confirmed-objective").textContent = state.goalDraft.goal;
  $("goal-confirmed-scope").textContent = `${state.goalDraft.scope} · ${validationModeLabel(validation.validation_mode)}`;
  $("goal-interpretation-panel").hidden = false;
  $("goal-create-panel").hidden = true;
  setMessage("goal-message", "Goal understood. Review the investigation boundary before starting.", true);
}

function showGoalClarifications(goal, validation) {
  state.goalClarification = { goal, validation, answers: {}, round: validation.clarification_round || 0 };
  $("goal-create-panel").hidden = true;
  $("goal-clarification-panel").hidden = false;
  $("goal-clarification-reason").textContent = validation.reason || "A few details are needed before planning.";
  $("goal-clarification-progress").textContent = `${validation.clarification_questions.length} details needed before GhostOps can plan safely`;
  const questions = $("goal-clarification-questions"); questions.replaceChildren();
  validation.clarification_questions.forEach((question) => {
    const card = el("article", "goal-finding-card clarification-question-card"); append(card, el("h3", "card-title clarification-question-title", question.question), el("p", "muted clarification-question-help", question.why_needed || "This affects safe planning."));
    (question.options || []).forEach((option) => { const label = el("label", `clarification-option-card${option.recommended ? " is-recommended" : ""}`); const input = document.createElement("input"); input.type = question.answer_type === "multiple_choice" ? "checkbox" : "radio"; input.name = `clarification-${question.id}`; input.value = option.value; input.checked = Boolean(option.recommended); input.addEventListener("change", () => { state.goalClarification.answers[question.id] = input.value === "other" || input.value === "custom" ? "" : input.value; label.closest(".clarification-question-card").querySelectorAll(".clarification-option-card").forEach((node) => node.classList.toggle("is-selected", node.querySelector("input").checked)); renderClarificationOther(question, card, input.value); }); const text = el("span", "clarification-option-label", option.label); label.append(input, text); if (option.recommended) label.appendChild(el("span", "clarification-recommended-badge", "Recommended")); card.appendChild(label); if (option.recommended) state.goalClarification.answers[question.id] = option.value; });
    if (question.answer_type === "text") renderClarificationOther(question, card, "text"); questions.appendChild(card);
  });
}

function renderClarificationOther(question, card, value) {
  card.querySelector(".goal-clarification-other")?.remove();
  if (!["other", "custom", "text"].includes(value)) return;
  const input = document.createElement("input"); input.className = "goal-clarification-other"; input.placeholder = question.placeholder || "Provide details"; input.addEventListener("input", () => { state.goalClarification.answers[question.id] = input.value.trim(); }); card.appendChild(input);
}

async function continueGoalClarifications() {
  const draft = state.goalClarification; if (!draft) return;
  const missing = draft.validation.clarification_questions.filter((q) => q.required && !draft.answers[q.id]);
  if (missing.length) { $("goal-clarification-reason").textContent = "Answer each required detail before continuing."; return; }
  let validation;
  try {
    validation = await withButtonState("goal-clarification-continue-button", "Reviewing answers…", () => withTimeout(api("/api/goals/validate", { method: "POST", body: JSON.stringify({ goal: draft.goal, scope: $("goal-scope-input").value || "Workspace scope", repositories: selectedGoalRepositories(), require_approval: true, clarification_answers: draft.answers, clarification_round: Math.min(draft.round + 1, 2), previous_normalized_goal: draft.validation.normalized_goal || draft.goal, previous_clarification_questions: draft.validation.clarification_questions || [] }) }), 10000, "Goal revalidation timed out."));
  } catch (error) {
    $("goal-clarification-reason").textContent = goalErrorMessage(error);
    return;
  }
  if (validation.status === "needs_revision" && validation.clarification_questions?.length) return showGoalClarifications(draft.goal, validation);
  if (validation.status !== "accepted") { $("goal-clarification-reason").textContent = validation.reason || "Goal needs revision. Edit the original goal and try again."; return; }
  validation.clarification_answers = draft.answers;
  state.goalDraft = { goal: validation.normalized_goal || draft.goal, scope: $("goal-scope-input").value || "Workspace scope", repositories: selectedGoalRepositories(), validation, idempotencyKey: `goal:${Date.now()}:${Math.random().toString(16).slice(2)}` };
  state.goalCreationStage = "confirm";
  $("goal-clarification-panel").hidden = true;
  $("goal-confirmed-objective").textContent = state.goalDraft.goal;
  $("goal-confirmed-scope").textContent = `${state.goalDraft.scope} · ${planningModeLabel(validation.validation_mode || "deterministic")}`;
  $("goal-interpretation-panel").hidden = false;
  $("goal-interpretation-panel").scrollIntoView?.({ block: "start", behavior: "smooth" });
  $("goal-confirm-button").focus?.();
}

async function confirmGoal() {
  if (!state.goalDraft || state.goalStartInFlight) return;
  state.goalStartInFlight = true;
  if ($("goal-retry-button")) $("goal-retry-button").hidden = true;
  try {
    await withButtonState("goal-confirm-button", "Starting investigation…", async () => {
    const created = normalizeGoalResponse(await withTimeout(api("/api/goals", { method: "POST", body: JSON.stringify({ goal: state.goalDraft.goal, scope: state.goalDraft.scope, repositories: state.goalDraft.repositories, scenario_name: "safe", constraints: { validation: state.goalDraft.validation, repositories: state.goalDraft.repositories }, data_source_mode: "Connected evidence", idempotency_key: state.goalDraft.idempotencyKey }) }), 15000, "The investigation did not start. Retry."));
    state.goalCreationStage = "started";
    const initialGoal = { ...created, status: "created", current_stage: "goal_received" };
    state.selectedGoal = initialGoal;
    state.goalEvents = [];
    state.goalTab = "plan";
    localStorage.setItem("ghostbusters:lastGoalId", created.id);
    switchMode("goals");
    renderGoalExecution();
    $("goal-agent-state").textContent = "Interpreting scope";
    $("goal-agent-narration").textContent = "Goal received. Selecting the safest investigation path…";
    $("goal-current-action").textContent = "Interpreting scope";
    setMessage("goal-message", "Goal received. Interpreting scope…", true);
    void selectGoal(created.id, false, initialGoal).then((loaded) => {
      if (loaded && state.selectedGoal?.id === created.id) setMessage("goal-message", "Investigation is live. Evidence updates will appear here.", true);
    });
    });
  } catch (error) {
    showGoalError(error);
  } finally {
    state.goalStartInFlight = false;
  }
}

function editGoalDraft() {
  state.goalCreationStage = "idle";
  $("goal-interpretation-panel").hidden = true;
  $("goal-create-panel").hidden = false;
  $("goal-create-panel")?.appendChild($("goal-message"));
  if ($("goal-retry-button")) $("goal-retry-button").hidden = true;
  $("goal-edit-button").textContent = "Edit Goal";
  $("goal-input").focus?.();
}

async function cancelSelectedGoal() {
  if (!state.selectedGoal) return;
  try { state.selectedGoal = await api(`/api/goals/${state.selectedGoal.id}/cancel`, { method: "POST", body: "{}" }); state.goalEvents = await api(`/api/goals/${state.selectedGoal.id}/events`); renderGoalExecution(); showToast("Goal canceled safely", "No Terraform, GitHub, or cloud mutation was performed.", "success"); }
  catch (error) { showToast("Cancel failed", friendlyError(error), "error"); }
}

async function retrySelectedGoalEvidence() {
  if (!state.selectedGoal) return;
  return withButtonState("goal-retry-evidence-button", "Retrying evidence...", async () => {
    const key = `goal-evidence:${state.selectedGoal.id}:${Date.now()}`;
    state.selectedGoal = normalizeGoalResponse(await api(`/api/goals/${state.selectedGoal.id}/retry-evidence`, { method: "POST", body: JSON.stringify({ idempotency_key: key }) }));
    state.goalEvents = await api(`/api/goals/${state.selectedGoal.id}/events`);
    renderGoalExecution();
    setMessage("goal-message", "Evidence collection retried. Showing the latest recorded state.", true);
  }).catch((error) => setMessage("goal-message", goalErrorMessage(error)));
}

function goalEventClass(event) { if (["failed_safely", "tool_failed"].includes(event.event_type)) return "goal-failed"; if (["human_review_required", "conflict_detected", "policy_evaluated"].includes(event.event_type)) return "goal-warning"; if (["tool_started", "step_started"].includes(event.event_type)) return "goal-running"; return "goal-completed"; }

function goalStatusMeta(status) {
  const meta = { completed: ["Completed", "status-approved"], approved: ["Awaiting remediation", "status-approved"], pending_human_review: ["Awaiting human review", "status-awaiting-review"], needs_more_evidence: ["More evidence required", "status-warning"], failed_safely: ["Failed safely", "status-blocked"], canceled: ["Canceled safely", "status-neutral"], blocked: ["Policy blocked", "status-blocked"] }[status];
  return meta || [runStatusLabel(status), "status-in-progress"];
}

function goalDuration(run) {
  const start = parseTime(run?.created_at); const end = parseTime(run?.updated_at);
  if (!start || !end) return "Not recorded";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return "Less than a minute";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} minute${Math.floor(seconds / 60) === 1 ? "" : "s"}`;
  return `${Math.floor(seconds / 3600)} hour${Math.floor(seconds / 3600) === 1 ? "" : "s"}`;
}

function goalSourceLabel(run) {
  if (run?.data_source_mode === "Not connected") return "Not connected";
  if (run?.execution_mode === "connected_read_only") return "Connected evidence";
  return state.currentUser?.demo_mode ? "Demo evidence (labeled)" : "Not collected";
}

function goalStageIndex(run) {
  const states = goalRoadmapStates(run, state.goalEvents);
  const current = states.findIndex((item) => item !== "complete");
  return current < 0 ? states.length - 1 : current;
}

function goalRoadmapStates(run, events) {
  const eventTypes = new Set((events || []).map((event) => event.event_type));
  const has = (...types) => types.some((type) => eventTypes.has(type));
  const attempts = run.tool_attempts || [];
  const toolRunning = attempts.some((attempt) => attempt.status === "running");
  const toolCompleted = attempts.some((attempt) => attempt.status === "completed");
  const terminal = ["completed", "approved", "pr_created", "remediation_pr_created", "rejected", "canceled", "abstained"].includes(run.status);
  if (run.status === "abstained") {
    return ["complete", "complete", "complete", "complete", "complete", "warning", "waiting"];
  }
  return [
    has("goal_received", "scope_resolved") ? "complete" : run.status === "created" ? "active" : "waiting",
    has("gemini_planning_completed", "plan_validated", "plan_created") ? "complete" : has("gemini_planning_started") ? "active" : "waiting",
    run.status === "needs_more_evidence" ? "warning" : toolRunning || run.status === "investigating" ? "active" : toolCompleted ? "complete" : "waiting",
    has("evidence_threshold_evaluated", "alternatives_compared") ? "complete" : toolCompleted ? "active" : "waiting",
    has("policy_evaluated") ? "complete" : has("evidence_threshold_evaluated") ? "active" : "waiting",
    has("recommendation_created", "recommendation_prepared") ? "complete" : has("policy_evaluated") ? "active" : "waiting",
    run.status === "pending_human_review" ? "warning" : terminal && has("human_review_required", "approval_requested") ? "complete" : has("recommendation_created", "recommendation_prepared") ? "active" : "waiting",
  ];
}

function renderGoalList() {
  const node = $("goal-list"); if (!node) return;
  clear(node);
  const goals = state.goals || [];
  $("goal-list-count").textContent = `${goals.length} goal${goals.length === 1 ? "" : "s"}`;
  $("goal-list-empty").hidden = Boolean(goals.length);
  goals.forEach((goal) => {
    const [label, className] = goalStatusMeta(goal.status);
    const card = el("article", "goal-card");
    const button = el("button", "secondary compact", "Open Goal"); button.type = "button"; button.addEventListener("click", () => selectGoal(goal.id));
    append(card, append(el("div", "goal-card-heading"), el("span", "goal-card-icon", "G"), el("span", `status-badge ${className}`, label)), el("h3", "goal-card-title", goal.goal || "Untitled goal"), el("p", "goal-card-scope", goal.scope || "Workspace scope"), append(el("div", "goal-card-meta"), el("span", null, "Connected evidence"), timestampNode(goal.updated_at, "Updated")), append(el("div", "goal-card-footer"), el("span", "muted", `Current stage: ${goal.status === "pending_human_review" ? "Human review" : label}`), button));
    node.appendChild(card);
  });
}

function renderGoalExecution() {
  if (!$("goal-execution-panel")) return;
  const run = state.selectedGoal;
  $("goal-execution-panel").hidden = !run;
  $("goal-list-panel").hidden = Boolean(run);
  $("goal-back-list-button").hidden = !run;
  $("goal-create-panel").hidden = Boolean(run) || state.goalCreationStage === "confirm";
  $("goal-interpretation-panel").hidden = Boolean(run) || state.goalCreationStage !== "confirm";
  if (!run) return;
  $("goal-summary-title").textContent = run.goal;
  setStatusBadge("goal-summary-status", { label: runStatusLabel(run.status), className: ["failed_safely", "canceled", "blocked"].includes(run.status) ? "status-blocked" : run.status === "pending_human_review" ? "status-awaiting-review" : "status-approved" });
  $("goal-summary-scope").textContent = run.scope || "Workspace scope";
  $("goal-summary-elapsed").textContent = goalDuration(run);
  $("goal-summary-planning").textContent = planningModeLabel(run.goal_planning_mode || run.original_plan?.planning_mode || run.planning_mode || "deterministic_only");
  $("goal-summary-source").textContent = goalSourceLabel(run);
  $("goal-cancel-button").hidden = ["canceled", "failed_safely", "approved", "pr_created", "remediation_pr_created", "needs_more_evidence"].includes(run.status);
  $("goal-retry-evidence-button").hidden = run.status !== "needs_more_evidence";
  $("goal-agent-state").textContent = run.status === "created" ? "Starting" : run.status === "pending_human_review" ? "Waiting for human approval" : run.status === "needs_more_evidence" ? "Evidence needed" : run.status === "abstained" ? "No recommendation" : ["failed_safely", "blocked"].includes(run.status) ? "Stopped safely" : ["completed", "approved", "pr_created", "remediation_pr_created"].includes(run.status) ? "Investigation complete" : "Collecting and comparing evidence";
  $("goal-agent-narration").textContent = run.status === "created" ? "Goal received. Interpreting goal and scope." : run.status === "pending_human_review" ? "GhostOps has stopped before remediation. A human decision is required." : run.stop_reason || "Evidence is being connected to the goal and safety boundaries.";
  $("goal-agent-mark").className = `goal-agent-mark ${["pending_human_review", "abstained"].includes(run.status) ? "waiting" : ["failed_safely", "blocked"].includes(run.status) ? "failed" : ["completed", "approved", "pr_created", "remediation_pr_created"].includes(run.status) ? "complete" : "active"}`;
  const journey = $("goal-journey-list"); clear(journey);
  const stages = ["Understand goal", "Choose investigation path", "Collect evidence", "Compare alternatives", "Verify safety policy", "Prepare recommendation", "Human approval"];
  const roadmapStates = goalRoadmapStates(run, state.goalEvents);
  stages.forEach((stage, index) => { const currentState = roadmapStates[index] || "waiting"; const stateLabel = currentState === "complete" ? "Completed" : currentState === "warning" ? (run.status === "abstained" ? "No recommendation" : "Evidence needed") : currentState === "failed" ? "Stopped safely" : currentState === "active" ? "Running" : "Waiting"; const item = el("li", `goal-map-node ${currentState}`); append(item, el("span", "goal-map-number", currentState === "complete" ? "✓" : String(index + 1)), el("strong", null, stage), el("small", null, stateLabel)); if (index < stages.length - 1) item.appendChild(el("span", "goal-map-connector")); journey.appendChild(item); });
  const latest = [...(state.goalEvents || [])].reverse().find((event) => event.tool || event.input_summary || event.output_summary) || state.goalEvents.at(-1);
  $("goal-current-action").textContent = latest?.label || (run.status === "created" ? "Interpreting goal and scope" : state.goalEvents.length ? runStatusLabel(run.status) : "Interpreting goal and scope");
  $("goal-current-tool").textContent = latest?.tool || "Planner and policy";
  $("goal-current-reason").textContent = latest?.reason || latest?.summary || "Recorded by the execution plan.";
  $("goal-current-input").textContent = latest?.input_summary || "Sanitized execution context";
  $("goal-current-attempt").textContent = latest?.attempt_number || "1";
  $("goal-current-output").textContent = latest?.output_summary || latest?.summary || "Recorded output";
  $("goal-current-impact").textContent = latest?.decision_impact || run.stop_reason || "No infrastructure mutation was performed.";
  document.querySelectorAll("[data-goal-tab]").forEach((button) => button.classList.toggle("filter-chip-active", button.dataset.goalTab === state.goalTab));
  renderGoalTab();
}

function goalDestinationActions(run) {
  const actions = el("div", "start-actions");
  if (run.linked_pr_review_id) {
    const button = el("button", "secondary compact", "Open PR Review"); button.type = "button";
    button.addEventListener("click", () => openPrReviewById(run.linked_pr_review_id).catch((error) => setMessage("goal-message", friendlyError(error, "PR Review is unavailable.")))); actions.appendChild(button);
  }
  if (run.linked_cloud_hunt_id) {
    const button = el("button", "secondary compact", "Open Cloud Hunt Finding"); button.type = "button";
    button.addEventListener("click", async () => { try { state.hunt = await api(`/api/cloud/hunts/${run.linked_cloud_hunt_id}`); state.selectedCloudHuntId = state.hunt.id; switchMode("cloud-hunt"); renderCloudHunt(); } catch (error) { setMessage("goal-message", friendlyError(error, "Cloud Hunt run is unavailable.")); } }); actions.appendChild(button);
  }
  if (run.linked_approval_id || run.status === "pending_human_review") {
    const button = el("button", "secondary compact", "Open Approval"); button.type = "button";
    button.addEventListener("click", () => { switchMode("review-queue"); loadReviewQueue(); }); actions.appendChild(button);
  }
  return actions.childNodes.length ? actions : null;
}

function renderGoalTab() {
  const node = $("goal-tab-content"); clear(node); const run = state.selectedGoal; if (!run) return;
  if (state.goalTab === "outcome") {
    const decision = run.decision_record; const findings = run.findings || [];
    const hero = el("div", "goal-outcome-hero"); const heroCopy = el("div");
    append(heroCopy, el("p", "kicker", "Investigation outcome"), el("h3", null, run.status === "needs_more_evidence" ? "More evidence is required" : ["pending_human_review"].includes(run.status) ? "Human review is the next step" : runStatusLabel(run.status)), el("p", null, run.stop_reason || decision?.final_summary || "No outcome has been recorded yet."));
    append(hero, el("span", "goal-outcome-icon", "✓"), heroCopy);
    const metrics = el("div", "goal-outcome-metrics");
    [[findings.length, "Findings"], [run.evidence?.length || 0, "Evidence sources"], [0, "Automatic changes"]].forEach(([value, label]) => { const metric = el("div"); append(metric, el("strong", null, String(value)), el("span", null, label)); metrics.appendChild(metric); });
    const missingAction = run.missing_evidence?.length
      ? `Collect or confirm ${run.missing_evidence.join(", ")} before any recommendation is considered.`
      : "Review the recorded evidence and safety checks.";
    append(node, hero, metrics, el("h3", "card-title", "Recommended next action"), el("p", "goal-next-action", run.status === "needs_more_evidence" ? missingAction : run.status === "pending_human_review" ? "Review the recommendation and approve, reject, or request more evidence." : "Review the recorded evidence and safety checks."), run.missing_evidence?.length ? dataList(run.missing_evidence.map((item) => ["Missing evidence", item])) : null, goalDestinationActions(run)); return;
  }
  if (state.goalTab === "findings") { const findings = run.findings || []; if (!findings.length) return node.appendChild(el("p", "muted", run.status === "needs_more_evidence" ? "No finding was produced because verified evidence is still required." : "No findings recorded yet.")); findings.forEach((item) => { const card = el("article", "goal-finding-card"); append(card, el("span", "status-badge status-warning", labelFor(item.severity || "info")), el("h3", null, labelFor(item.check_name || item.title || "Finding")), el("p", null, item.explanation || item.summary || "No explanation recorded."), dataList([["Status", labelFor(item.status || "not available")], ["Evidence", item.evidence_sources || "Not collected"]]), goalDestinationActions(run)); node.appendChild(card); }); return; }
  if (state.goalTab === "technical") { const details = el("details", "goal-technical-trace"); const summary = el("summary", null, `Technical Trace (${state.goalEvents.length})`); details.appendChild(summary); details.appendChild(responsiveTable([{ label: "Time", render: (event) => timestampNode(event.timestamp, "Event") }, { label: "Stage", render: (event) => labelFor(event.stage || "Not available") }, { label: "Event", render: (event) => event.label || labelFor(event.event_type) }, { label: "Result", render: (event) => event.status || event.summary || "Recorded" }], state.goalEvents, "No technical events recorded.")); node.appendChild(details); return; }
  if (state.goalTab === "evidence") { node.appendChild(responsiveTable([{ label: "Source", render: (item) => labelFor(item.source) }, { label: "Summary", render: (item) => item.value_summary || item.claim || "Not collected" }, { label: "Freshness", render: (item) => labelFor(item.freshness || item.freshness_status || "unknown") }, { label: "Reliability", render: (item) => item.reliability || "Not available" }, { label: "Impact", render: (item) => item.effect_on_decision || "Not assessed" }], run.evidence || [], "No verified evidence has been collected.")); return; }
  if (state.goalTab === "plan") {
    const attempts = run.tool_attempts || [];
    const decisions = (run.plan_revisions || []).filter((item) => item.kind === "next_action");
    const planMode = run.goal_planning_mode || run.original_plan?.planning_mode || run.planning_mode;
    append(node, el("h3", "card-title", ["groq_primary", "gemini_primary"].includes(planMode) ? "Groq-guided live plan" : planMode === "gemini_fallback_model" ? "AI fallback live plan" : "Evidence-guided live plan"), el("p", "muted", "Each next step is chosen from recorded evidence and limitations. Only allowlisted read-only tools can run."));
    if (!attempts.length && !decisions.length) node.appendChild(el("p", "goal-next-action", "Next decision pending evidence. GhostOps has not run an evidence tool yet."));
    const entries = [];
    decisions.forEach((decision, index) => entries.push({ type: "decision", index, item: decision }));
    attempts.forEach((attempt, index) => entries.push({ type: "attempt", index, item: attempt }));
    entries.sort((left, right) => left.index - right.index || (left.type === "decision" ? -1 : 1));
    entries.forEach((entry) => {
      if (entry.type === "decision") {
        const decision = entry.item;
        const accepted = decision.accepted !== false;
        const mode = planningModeLabel(decision.planning_mode || "deterministic_fallback");
        const card = el("article", `goal-finding-card goal-agent-decision ${accepted ? "goal-agent-decision-accepted" : "goal-agent-decision-rejected"}`);
        append(card, el("span", `status-badge ${accepted ? "status-in-progress" : "status-warning"}`, accepted ? "Agent decision" : "Proposal rejected"), el("h3", null, `${entry.index + 1}. Decide next step`), el("p", null, decision.reason || "The agent evaluated the recorded investigation context."), dataList([["Selected tool", labelFor(decision.tool_name || "No tool")], ["Question", decision.question_being_answered || "Not recorded"], ["Expected evidence", decision.expected_information || "Not recorded"], ["Safety check", decision.validation_result || "Not recorded"], ["Planning mode", mode]]));
        if (decision.fallback_from) card.appendChild(el("p", "goal-next-action", "The original proposal did not pass the bounded safety check, so GhostOps used the next registered read-only collector."));
        node.appendChild(card);
        return;
      }
      const attempt = entry.item; const status = attempt.status || "pending"; const tone = status === "completed" ? "status-approved" : status === "running" ? "status-in-progress" : status === "failed" ? "status-blocked" : "status-neutral"; const card = el("article", `goal-finding-card goal-live-step goal-live-step-${status}`); append(card, el("span", `status-badge ${tone}`, status === "failed" ? "Failed safely" : labelFor(status)), el("h3", null, `${entry.index + 1}. ${labelFor(attempt.tool_name || "Evidence step")}`), el("p", null, attempt.selected_because || "Selected from the recorded investigation context."), dataList([["Expected evidence", attempt.expected_evidence || "Verified evidence or an explicit limitation."], ["Result", attempt.output_summary || attempt.error || "Awaiting result"], ["Attempt", attempt.attempt_number || 1]])); node.appendChild(card);
    });
    if (["investigating", "needs_more_evidence"].includes(run.status)) node.appendChild(el("p", "goal-next-action", run.status === "needs_more_evidence" ? "Evidence is insufficient for a recommendation. The next decision is waiting for additional evidence or human context." : "Next decision pending the latest evidence response."));
    const revisions = (run.plan_revisions || []).filter((item) => item.kind !== "next_action");
    if (revisions.length) { node.appendChild(el("h3", "card-title", "Plan revisions")); revisions.forEach((revision) => node.appendChild(el("p", "goal-next-action", revision.reason || "Plan revised from new evidence."))); }
    return;
  }
  if (state.goalTab === "alternatives") { node.appendChild(responsiveTable([{ label: "Action", render: (item) => recommendationLabel(item.action) }, { label: "Savings", render: (item) => money(item.estimated_monthly_savings) }, { label: "Eligible", render: (item) => item.eligible ? "Eligible" : "Not eligible" }, { label: "Reason", render: (item) => item.ineligible_reason || item.reason || "Recorded comparison" }], run.decision_record?.alternatives || [], "No alternatives recorded.")); return; }
  const policy = run.decision_record?.policy_result; append(node, el("p", null, `Passed checks: ${(policy?.evaluated_rules || []).join(", ") || "Not recorded"}`), el("p", null, `Warnings: ${(policy?.warnings || []).join("; ") || "None recorded"}`), el("p", null, `Blocks: ${(policy?.blocking_reasons || []).join("; ") || "None recorded"}`), el("p", null, `Mandatory human approval: ${policy?.requires_human_approval ? "Yes" : "No"}`), el("p", null, `Stop reason: ${run.stop_reason || "Not recorded"}`));
}

async function refreshPRReviews() {
  return withButtonState("refresh-button", "Refreshing...", () => loadPRReviews({ preserveSelection: true, showNotice: true }), "Updated");
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
    const auxiliaryMessage = error?.status === 401 ? "Approval metadata unavailable." : message;
    const target = state.activeMode === "simple" ? "pr-auxiliary-message" : "cloud-hunt-message";
    setMessage(target, auxiliaryMessage);
    if (state.activeMode === "simple" && $("pr-auxiliary-retry-button")) $("pr-auxiliary-retry-button").hidden = false;
    showToast("Review load failed", message, "error");
  } finally {
    state.loading.reviews = false;
    renderReviewQueue();
    renderOverview();
  }
}

function cloudRunStatusLabel(status) {
  return ({ created: "Queued", queued: "Queued", scanning: "Running", running: "Running", completed: "Completed", completed_with_warnings: "Completed with Warnings", failed: "Failed Safely", failed_safely: "Failed Safely", canceled: "Canceled" })[status] || "Queued";
}

function cloudRunDuration(run) {
  const duration = run.duration_seconds ?? (run.completed_at && run.started_at ? (new Date(run.completed_at) - new Date(run.started_at)) / 1000 : null);
  if (duration == null || Number.isNaN(duration)) return "Not completed";
  const seconds = Math.max(0, Math.round(duration));
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

async function loadCloudHunts() {
  state.loading.cloudHunts = true;
  state.cloudHuntError = "";
  renderCloudRunHistory();
  try {
    const filters = state.cloudHuntFilters;
    const params = new URLSearchParams({ page: String(state.cloudHuntPage), page_size: String(state.cloudHuntPageSize), sort: filters.sort });
    if (filters.status) params.set("status", filters.status);
    if (filters.provider) params.set("provider", filters.provider);
    if (filters.search.trim()) params.set("search", filters.search.trim());
    const payload = await api(`/api/cloud/hunts?${params}`);
    state.hunts = payload.items || [];
    state.cloudHuntTotal = payload.total || 0;
    state.cloudHuntServerPaged = true;
  } catch (error) {
    state.cloudHuntError = friendlyError(error, "Failed to load Cloud Hunt history.");
  } finally {
    state.loading.cloudHunts = false;
    renderCloudRunHistory();
  }
}

async function selectCloudHunt(runId) {
  try {
    state.loading.cloudHunt = true;
    state.selectedCloudHuntId = runId;
    state.hunt = await api(`/api/cloud/hunts/${runId}`);
    renderCloudRunHistory();
    renderCloudHunt();
  } catch (error) {
    state.cloudHuntError = friendlyError(error, "Failed to load Cloud Hunt run.");
    showToast("Run unavailable", state.cloudHuntError, "error");
  } finally {
    state.loading.cloudHunt = false;
    renderCloudRunHistory();
    renderCloudHunt();
  }
}

function backToCloudRunHistory() {
  state.selectedCloudHuntId = null;
  state.hunt = null;
  state.selectedReviewContext = null;
  renderCloudRunHistory();
  renderCloudHunt();
}

function renderCloudRunHistory() {
  const node = $("cloud-run-history-list");
  if (!node) return;
  clear(node);
  const detail = Boolean(state.selectedCloudHuntId);
  $("cloud-run-history").hidden = detail;
  $("cloud-run-detail-meta").hidden = !detail;
  if (state.loading.cloudHunts) return renderSkeletonList(node, 3);
  if (state.cloudHuntError) {
    const retry = el("button", "secondary", "Retry"); retry.type = "button"; retry.addEventListener("click", loadCloudHunts);
    append(node, el("p", "message", state.cloudHuntError), retry); return;
  }
  if (!state.hunts.length) { node.appendChild(el("p", "muted", "No Cloud Hunt runs have been recorded yet.")); return; }
  const columns = [
    { label: "Run", priority: "mobile", render: (run) => run.run_number || "Cloud Hunt run" },
    { label: "Provider scope", render: (run) => labelFor(run.provider_scope) },
    { label: "Started by", priority: "tablet", render: (run) => run.started_by || "System" },
    { label: "Started", render: (run) => timestampNode(run.started_at, "Started") },
    { label: "Duration", priority: "tablet", render: cloudRunDuration },
    { label: "Resources", priority: "tablet", render: (run) => run.resources_scanned },
    { label: "Candidates", render: (run) => run.candidates_found },
    { label: "Waste", priority: "tablet", render: (run) => money(run.estimated_monthly_waste) },
    { label: "Status", render: (run) => statusBadge({ label: cloudRunStatusLabel(run.status), className: run.status === "failed" ? "status-blocked" : run.status === "completed" ? "status-approved" : "status-awaiting-review" }) },
    { label: "Action", render: (run) => { const button = el("button", "secondary compact", "View Run"); button.type = "button"; button.addEventListener("click", () => selectCloudHunt(run.id)); return button; } },
  ];
  node.appendChild(responsiveTable(columns, state.hunts, "No Cloud Hunt runs match these filters."));
  const total = state.cloudHuntTotal || state.hunts.length;
  const start = (state.cloudHuntPage - 1) * state.cloudHuntPageSize;
  $("cloud-run-pagination-summary").textContent = total ? `Showing ${start + 1}-${Math.min(start + state.hunts.length, total)} of ${total} runs` : "0 runs";
  $("cloud-run-prev-button").disabled = state.cloudHuntPage <= 1;
  $("cloud-run-next-button").disabled = start + state.hunts.length >= total;
}

function renderCloudRunDetailMeta() {
  const run = state.hunt;
  if (!run || !state.selectedCloudHuntId) return;
  $("cloud-run-detail-title").textContent = run.run_number || `Cloud Hunt ${String(run.id).slice(0, 8).toUpperCase()}`;
  $("cloud-run-provider-scope").textContent = labelFor(run.provider_scope);
  $("cloud-run-started-by").textContent = run.started_by_display_name || "System";
  $("cloud-run-started-at").replaceChildren(timestampNode(run.started_at, "Started"));
  $("cloud-run-completed-at").replaceChildren(run.completed_at ? timestampNode(run.completed_at, "Completed") : el("span", null, "Not completed"));
  $("cloud-run-duration").textContent = cloudRunDuration(run);
  $("cloud-run-data-source").textContent = run.data_source_mode || "Fixture-backed";
}

async function startCloudHunt() {
  return withButtonState("start-cloud-hunt-button", "Scanning...", async () => {
    state.loading.cloudHunt = true;
    renderCloudHunt();
    setMessage("cloud-hunt-message", "Scanning fixture inventory...", true);
    state.hunt = await api("/api/cloud/hunts", { method: "POST", body: JSON.stringify({ provider_scope: $("cloud-provider-scope").value, inventory_source: $("cloud-data-source").value }) });
    state.selectedCloudHuntId = state.hunt.id;
    await loadCloudHunts();
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
    state.outcome = null;
    state.selectedReviewContext = { source: "demo", runId: run.id };
    localStorage.setItem("ghostbusters:lastRunId", run.id);
    state.skipAnimation = $("skip-animation").checked;
    closeDemoModal();
    startAnimation();
    switchMode("simple");
    loadOutcomeForRun();
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
  if (state.activeMode === "overview") return withButtonState("overview-refresh-button", "Refreshing...", async () => { await loadOverview(); showToast("Dashboard refreshed", "Summary data reloaded without starting work.", "success"); });
  await loadPRReviews({ preserveSelection: true, showNotice: true });
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
  if (!window.confirm("Reset only demo fixtures and demo runs for this organization? Real integration settings and organization data are preserved.")) return;
  try {
    await api("/api/demo/reset", { method: "POST", body: JSON.stringify({ confirm: true }) });
    window.clearInterval(state.animationTimer);
    state.run = null;
    state.selectedReviewContext = null;
    state.visibleEvents = [];
    state.demoReadiness = null;
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
  if (decision?.missing_evidence?.length) return `GhostOps needs more evidence before it can recommend a safe remediation.`;
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
  $("recommendation-reason").textContent = decision ? recommendationReason(decision, preferred) : "The recommendation will appear here after GhostOps completes its investigation.";
  $("recommendation-confidence").textContent = percentage(decision?.confidence?.final_confidence);
  $("recommendation-risk").textContent = decision ? riskLevel(decision, preferred) : "--";
  $("recommendation-policy").textContent = decision ? policyStatusLabel(decision.policy_result?.status) : "--";
  $("recommendation-policy-technical").textContent = "";
  const pricing = pricingForRun(state.run);
  $("recommendation-savings").textContent = preferred && pricingAvailable(state.run) ? `${money(preferred.estimated_monthly_savings)}/month` : "Cost estimate unavailable";
  $("recommendation-annual-savings").textContent = preferred && pricingAvailable(state.run) ? `${money(preferred.estimated_annual_savings)}/year` : "Cost estimate unavailable";
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
    $("planning-note").textContent = "AI planning was unavailable, so GhostOps continued with deterministic review logic.";
  } else {
    $("planning-note").textContent = isDemoRun(state.run) ? "Prepared fixtures are backing this demo case." : "";
  }
}

function allowedReviewActions(status) {
  if (status === "pending_human_review") return ["approve", "modify", "request_evidence", "reject"];
  if (status === "needs_more_evidence") return ["add_context", "request_evidence", "reject"];
  if (status === "abstained") return ["add_context", "request_evidence"];
  if (status === "blocked" || status === "keep" || status === "failed_safely") return ["add_context"];
  if (status === "approved" || status === "pr_created" || status === "remediation_pr_created") return ["revoke_approval", "add_follow_up_context"];
  if (status === "rejected" || status === "approval_revoked") return ["reopen_case", "add_follow_up_context"];
  if (status === "reopened") return ["add_follow_up_context", "request_evidence", "reject"];
  return [];
}

async function loadOverview() {
  if (!hasPermission("overview.read")) return;
  const node = $("overview-summary"); if (node) renderSkeletonList(node, 4);
  try { state.overview = await api("/api/overview?date_range=30d"); renderOverview(); } catch (error) { state.overview = { partial_data: true, warnings: [friendlyError(error, "Overview could not be loaded.")] }; renderOverview(); }
}

function activityExactTimestamp(value) {
  const date = parseTime(value);
  if (!date) return "Not recorded";
  const timezone = state.activity.timezone || state.currentUser?.organization?.timezone || userTimezone();
  try { return `${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium", timeZone: timezone }).format(date)} ${timezone}`; }
  catch { return exactTimestamp(value); }
}

function activityQuery() {
  const filters = state.activity.filters;
  const params = new URLSearchParams({ page: String(state.activity.page), page_size: String(state.activity.pageSize), sort: filters.sort });
  if (filters.category) params.set("category", filters.category);
  if (filters.actorType) params.set("actor_type", filters.actorType);
  if (filters.action.trim()) params.set("action", filters.action.trim());
  if (filters.result) params.set("result", filters.result);
  if (filters.targetType) params.set("target_type", filters.targetType);
  if (filters.search.trim()) params.set("search", filters.search.trim());
  if (filters.dateRange === "custom") {
    if (filters.createdFrom) params.set("created_from", new Date(filters.createdFrom).toISOString());
    if (filters.createdTo) params.set("created_to", new Date(filters.createdTo).toISOString());
  } else if (filters.dateRange !== "all") {
    const days = filters.dateRange === "today" ? 1 : Number(filters.dateRange.replace("d", ""));
    params.set("created_from", new Date(Date.now() - days * 86400000).toISOString());
  }
  if (source === "pricing" && !pricingForRun(state.run).available) return { title: "Pricing", detail: "Cost estimate unavailable", conclusion: "Live pricing evidence was not available for this change." };
  return params;
}

function activityActionLabel(action) { return labelFor(action || "activity"); }

function renderActivityLog() {
  const list = $("activity-list");
  if (!list) return;
  clear(list);
  const data = state.activity;
  $("activity-timezone").textContent = `Timezone: ${data.timezone || state.currentUser?.organization?.timezone || userTimezone()}`;
  $("activity-pagination-summary").textContent = data.total ? `Showing ${(data.page - 1) * data.pageSize + 1}-${Math.min(data.page * data.pageSize, data.total)} of ${data.total} events` : "0 events";
  $("activity-prev-button").disabled = data.page <= 1;
  $("activity-next-button").disabled = !data.hasNext;
  $("activity-page-size").value = String(data.pageSize);
  document.querySelectorAll("[data-activity-category]").forEach((button) => {
    const active = button.dataset.activityCategory === data.filters.category;
    button.classList.toggle("filter-chip-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (data.loading) { renderSkeletonList(list, 6); return; }
  if (data.error) { const error = el("div", "empty-state", data.error); const retry = el("button", "secondary compact", "Retry"); retry.type = "button"; retry.addEventListener("click", loadActivity); append(error, retry); list.appendChild(error); return; }
  if (!data.items.length) { list.appendChild(el("div", "empty-state", data.filters.category || data.filters.search ? "No activity matches these filters." : "No activity recorded yet.")); return; }
  const rows = data.items.map((item) => ({ ...item, timestamp: append(el("div"), el("strong", null, activityExactTimestamp(item.created_at)), el("small", "row-meta", relativeTime(item.created_at))) }));
  list.appendChild(responsiveTable([
    { label: "Timestamp", render: (item) => item.timestamp },
    { label: "Actor", render: (item) => append(el("div"), el("strong", "row-title", item.actor_display_name), el("small", "row-meta", item.actor_type)) },
    { label: "Role or actor type", render: (item) => item.actor_role_snapshot || item.actor_type },
    { label: "Action", render: (item) => activityActionLabel(item.action) },
    { label: "Target", render: (item) => item.target_display_name || item.target_id || "Workspace" },
    { label: "Category", render: (item) => el("span", "status-badge status-neutral", item.category) },
    { label: "Result", render: (item) => el("span", `status-badge ${item.result === "success" ? "status-completed" : "status-warning"}`, labelFor(item.result)) },
    { label: "Details", render: (item) => { const button = el("button", "secondary compact", "View details"); button.type = "button"; button.addEventListener("click", () => openActivityDetails(item)); return button; } },
  ], rows, "No activity matches these filters."));
}

async function loadActivity() {
  if (!state.currentUser?.authenticated || !hasPermission("activity.read")) return;
  const data = state.activity;
  data.loading = true; data.error = ""; renderActivityLog();
  try {
    const payload = await api(`/api/activity?${activityQuery().toString()}`);
    data.items = payload.items || []; data.total = payload.total || 0; data.page = payload.page || 1; data.pageSize = payload.page_size || data.pageSize; data.hasNext = Boolean(payload.has_next); data.timezone = payload.timezone;
  } catch (error) { data.error = friendlyError(error, "Activity Log could not be loaded."); }
  data.loading = false; renderActivityLog();
}

function openActivityDetails(item) {
  const existing = $("activity-details-dialog"); existing?.remove();
  const backdrop = el("div", "modal-backdrop"); backdrop.id = "activity-details-dialog";
  const dialog = el("section", "demo-modal activity-details-drawer"); dialog.setAttribute("role", "dialog"); dialog.setAttribute("aria-modal", "true");
  const close = el("button", "icon-button", "×"); close.type = "button"; close.setAttribute("aria-label", "Close activity details"); close.addEventListener("click", () => backdrop.remove());
  append(dialog, append(el("div", "section-heading"), append(el("div"), el("p", "kicker", "Activity details"), el("h2", "section-title", activityActionLabel(item.action)), close)), dataList([
    ["Exact time", activityExactTimestamp(item.created_at)], ["Actor", `${item.actor_display_name} (${item.actor_type})`], ["Role snapshot", item.actor_role_snapshot || item.actor_type], ["Action", activityActionLabel(item.action)], ["Target", item.target_display_name || item.target_id], ["Result", labelFor(item.result)], ["Summary", item.summary], ["Previous state", item.metadata?.previous_state], ["Resulting state", item.metadata?.resulting_state], ["Reason/comment", item.metadata?.reason || item.metadata?.comment], ["Correlation ID", item.correlation_id], ["Related case", item.related_case_id], ["Related run", item.related_run_id], ["Metadata", item.metadata],
  ]));
  if (item.related_case_id || item.related_run_id) { const links = el("div", "start-actions"); if (item.related_run_id) { const link = el("button", "secondary compact", "Open PR Review"); link.type = "button"; link.addEventListener("click", () => { backdrop.remove(); state.run = state.prReviews.find((run) => run.id === item.related_run_id) || null; switchMode("simple"); }); links.appendChild(link); } else if (item.related_case_id) { const link = el("button", "secondary compact", "Open Cloud Hunt case"); link.type = "button"; link.addEventListener("click", async () => { try { const itemCase = await api(`/api/reviews/${item.related_case_id}`); if (itemCase.source_reference) await selectCloudHunt(itemCase.source_reference); backdrop.remove(); } catch (error) { showToast("Case unavailable", friendlyError(error), "error"); } }); links.appendChild(link); } if (item.related_run_id) { const audit = el("button", "secondary compact", "Open Technical Audit"); audit.type = "button"; audit.addEventListener("click", () => { backdrop.remove(); state.run = state.prReviews.find((run) => run.id === item.related_run_id) || null; switchMode("technical"); }); links.appendChild(audit); } dialog.appendChild(links); }
  backdrop.appendChild(dialog); document.body.appendChild(backdrop); close.focus?.();
}

function renderHumanControls() {
  const status = state.run?.status;
  const allowed = allowedReviewActions(status).filter((action) => hasPermission(approvalPermissionFor(action)));
  const human = humanDecision(state.run);
  setStatusBadge("human-decision", decisionStatusMeta(status, human.label));
  $("human-decision-technical").hidden = true;
  $("human-decision-technical").textContent = "";
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
          ? hasPermission("approvals.decide") ? "A human reviewer can decide whether GhostOps should create a remediation pull request." : "You have read-only access. You do not have permission to approve this case."
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
    revoke_approval: `Approval revoked by ${reviewer}`,
    reopen_case: `Case reopened by ${reviewer}`,
    add_follow_up_context: `Follow-up context added by ${reviewer}`,
  };
  return { label: labels[latest.action] || labelFor(latest.action), technical: `Review action: ${latest.action}` };
}

function selectReviewAction(action) {
  state.selectedReviewAction = action;
  $("review-form").hidden = false;
  $("review-form-title").textContent = labelFor(action);
  $("sources-field").hidden = action !== "request_evidence";
  $("context-field").hidden = !(action === "add_context" || action === "add_follow_up_context");
  $("modify-field").hidden = action !== "modify";
  $("comment-input").placeholder = ["reject", "revoke_approval", "reopen_case", "modify"].includes(action) ? "Required reason" : "Optional review comment";
  $("submit-review-button").textContent = action === "approve" ? "Approve Recommendation" : action === "reject" ? "Confirm Rejection" : action === "revoke_approval" ? "Revoke Approval" : action === "reopen_case" ? "Reopen Case" : "Send Review Update";
  $("review-form").scrollIntoView({ block: "nearest" });
}

function closeReviewForm() {
  state.selectedReviewAction = null;
  $("review-form").hidden = true;
}

async function submitSelectedReview() {
  const action = state.selectedReviewAction;
  if (!action || !state.run) return;
  const payload = { action, comment: $("comment-input").value || null, expected_version: state.run.version, idempotency_key: decisionIdempotencyKey(state.run.id, action) };
  if (action === "request_evidence") payload.requested_sources = $("requested-sources").value.split(",").map((item) => item.trim()).filter(Boolean);
  if (action === "add_context" || action === "add_follow_up_context") payload.human_context = $("human-context").value || null;
  if (action === "modify") payload.modified_action = $("modified-action").value || null;
  return withButtonState("submit-review-button", action === "approve" ? "Creating PR..." : "Saving review...", async () => {
    state.loading.review = true;
    state.run = await api(`/api/runs/${state.run.id}/review`, { method: "POST", body: JSON.stringify(payload) });
    closeReviewForm();
    startAnimation(true);
    setMessage("review-message", `${labelFor(action)} accepted by the backend.`, true);
    const remediation = state.run.remediation_result;
    const title = action === "approve" && remediation?.created ? "Remediation PR created" : action === "approve" ? "Remediation proposal prepared" : "Decision recorded";
    showToast(title, `Correlation ${state.run.correlation_id || "recorded"}.`, "success");
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
    remediation_pr_created: "Remediation PR Created",
    remediation_proposal_prepared: "Remediation Proposal Prepared",
    approval_revoked: "Approval Revoked",
    reopened: "Case Reopened",
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
  $("case-received-time").textContent = `Received: ${run ? exactTimestamp(run.created_at) : "Not recorded"}`;
  $("case-updated-time").textContent = `Last updated: ${run ? relativeTime(run.updated_at) : "Not recorded"}`;
  $("case-updated-time").title = run ? exactTimestamp(run.updated_at) : "";
  $("case-recommendation-time").textContent = `Recommendation completed: ${run ? exactTimestamp(recommendationCompletedTime(run)) : "Not recorded"}`;
  const decisionAt = latestDecisionTime(run);
  $("case-decision-time").textContent = `Decision: ${decisionAt ? exactTimestamp(decisionAt) : "Not recorded"}`;
  const finalAt = resultTime(run);
  $("case-result-time").textContent = `Result: ${finalAt ? exactTimestamp(finalAt) : "Not recorded"}`;
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
  const pricing = pricingForRun(state.run);
  const preferred = preferredAlternative() || {};
  append(node, dataList([["Resource ID", decision?.resource_id], ["Environment", "Not recorded in run response"], ["Terraform actions", "Not recorded in run response"], ["Destructive flag", "Not recorded in run response"], ["Current instance type", state.run?.mock_pr?.current_instance_type], ["Proposed instance type", preferred.proposed_instance_type], ["Current monthly cost", pricing.available ? money(pricing.current_monthly_cost) : "Cost estimate unavailable"], ["Proposed monthly cost", pricing.available ? money(pricing.proposed_monthly_cost) : "Cost estimate unavailable"], ["Pricing source", pricing.available ? pricing.source : "unavailable"], ["Pricing mode", pricing.available ? pricing.source_mode : "unavailable"], ["Assumptions", pricing.assumptions || "Live pricing evidence was not available for this change."], ["Excluded costs", pricing.excluded_costs]]));
  if (state.run?.mock_pr?.terraform_patch_preview) { const pre = el("pre"); pre.textContent = state.run.mock_pr.terraform_patch_preview; node.appendChild(pre); }
}

function renderEvidence() {
  const node = $("evidence-view"); clear(node);
  const evidence = state.run?.decision_record?.evidence || [];
  if (!evidence.length) return node.appendChild(el("p", "muted", "No evidence collected yet."));
  evidence.forEach((item) => {
    const card = el("article", `info-card ${statusClass(item.freshness_status)}`);
    const value = item.source === "pricing" && !pricingForRun(state.run).available ? "Live pricing evidence was not available for this change." : item.value;
    append(card, el("h3", null, labelFor(item.source)), dataList([["Claim", item.claim], ["Value", value], ["Freshness", item.freshness_status], ["Reliability", item.reliability], ["Source mode", item.source_mode || "Not recorded"], ["Resource ID", item.resource_id]]), rawDetails("Metadata", item.metadata || {}));
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
    const showPricing = pricingAvailable(state.run);
    append(card, el("h3", null, `${labelFor(item.action)}${item.action === decision.preferred_action ? " - preferred" : ""}`), dataList([["Description", item.description], ["Eligible", item.eligible], ["Score", Number(item.score).toFixed(2)], ["Monthly cost", showPricing ? money(item.estimated_monthly_cost) : "Cost estimate unavailable"], ["Monthly savings", showPricing ? money(item.estimated_monthly_savings) : "Cost estimate unavailable"], ["Annual savings", showPricing ? money(item.estimated_annual_savings) : "Cost estimate unavailable"], ["Supporting evidence", item.supporting_evidence], ["Risks", item.risks], ["Assumptions", item.assumptions], ["Rejection reasons", item.rejection_reasons]]));
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
  const pricing = pricingForRun(state.run);
  const preferred = preferredAlternative() || {};
  const showPricing = pricingAvailable(state.run);
  node.appendChild(dataList([["Current monthly cost", showPricing ? money(pricing.current_monthly_cost) : "Cost estimate unavailable"], ["Proposed monthly cost", showPricing ? money(pricing.proposed_monthly_cost || preferred.estimated_monthly_cost) : "Cost estimate unavailable"], ["Monthly savings", showPricing ? money(preferred.estimated_monthly_savings) : "Cost estimate unavailable"], ["Annual savings", showPricing ? money(preferred.estimated_annual_savings) : "Cost estimate unavailable"], ["Pricing source", pricing.available ? pricing.source : "unavailable"], ["Pricing mode", pricing.available ? pricing.source_mode : "unavailable"], ["Assumptions", pricing.assumptions || "Live pricing evidence was not available for this change."], ["Excluded costs", pricing.excluded_costs], ["Confidence", percentage(state.run?.decision_record?.confidence?.final_confidence)], ["Risk", preferred.risks], ["Run status", state.run?.status]]));
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

function connectedRepositories() {
  const repos = new Set();
  (state.githubConfig?.connected_repositories || []).forEach((item) => { if (item?.full_name) repos.add(item.full_name); });
  (state.githubConfig?.allowed_repositories || []).forEach((item) => { if (item) repos.add(item); });
  state.reviews.forEach((item) => { if (item.repository) repos.add(item.repository); });
  if (state.run?.github_source?.repository) repos.add(state.run.github_source.repository);
  if (state.run?.mock_pr?.repository) repos.add(state.run.mock_pr.repository);
  return [...repos];
}

function selectedGoalRepositories() {
  return [...new Set(state.goalSelectedRepositories || [])].filter(Boolean);
}

function renderGoalRepositoryScope() {
  const container = $("goal-repositories-input");
  const help = $("goal-repositories-help");
  if (!container || !help) return;
  const selected = new Set(selectedGoalRepositories());
  const repositories = connectedRepositories().sort((left, right) => left.localeCompare(right));
  container.replaceChildren();
  repositories.forEach((repository) => {
    const option = el("label", "goal-repository-option");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = repository;
    input.checked = selected.has(repository);
    option.classList.toggle("is-selected", input.checked);
    input.addEventListener("change", () => {
      const next = new Set(selectedGoalRepositories());
      if (input.checked) next.add(repository);
      else next.delete(repository);
      state.goalSelectedRepositories = [...next];
      option.classList.toggle("is-selected", input.checked);
    });
    option.append(input, el("span", "goal-repository-option-label", repository));
    container.appendChild(option);
  });
  if (!repositories.length) container.appendChild(el("p", "muted", "No connected repositories available."));
  container.classList.toggle("is-empty", repositories.length === 0);
  help.textContent = repositories.length
    ? "Choose the repositories GhostOps may inspect. Leave none selected for an AWS-only investigation."
    : "No GitHub repositories are connected. You can still run an AWS-only investigation.";
}

function setupSteps() {
  const health = state.overview?.integration_health || {};
  const github = health.github || {};
  const aws = health.aws || {};
  const githubConnected = github.status === "connected";
  const awsConnected = aws.status === "connected";
  const repositoryCount = Number(github.repository_count || 0);
  const activeGoals = Number(state.overview?.metrics?.active_goals || 0);
  const hasRecordedWork = activeGoals > 0 || Number(state.overview?.metrics?.pr_reviews_in_progress || 0) > 0 || Number(state.overview?.metrics?.cloud_hunt_runs_in_progress || 0) > 0;
  return [
    { title: "Workspace access", description: state.currentUser?.authenticated ? `Signed in to ${organizationName()}.` : "Sign in to access workspace data.", state: state.currentUser?.authenticated ? "completed" : "waiting" },
    { title: "Connect GitHub", description: githubConnected ? "GitHub connection is validated for this workspace." : "Connect and validate the GitHub App in Settings.", state: githubConnected ? "completed" : "waiting", action: "Open Settings", handler: () => switchMode("settings") },
    { title: "Select repositories", description: repositoryCount ? `${repositoryCount} allowed repositor${repositoryCount === 1 ? "y" : "ies"} configured.` : "Select an allowlisted repository in GitHub settings.", state: repositoryCount ? "completed" : "waiting", action: "Open Settings", handler: () => switchMode("settings") },
    { title: "Connect AWS", description: awsConnected ? `${aws.region_count || 0} allowed region${Number(aws.region_count || 0) === 1 ? "" : "s"} configured.` : "Enable and validate read-only AWS access in Settings.", state: awsConnected ? "completed" : "waiting", action: "Open Settings", handler: () => switchMode("settings") },
    { title: "Start an investigation", description: hasRecordedWork ? "Organization-scoped workflow activity is recorded." : "Review a scoped goal or run Cloud Hunt after integrations are ready.", state: hasRecordedWork ? "completed" : "waiting", action: "Open Goals", handler: () => switchMode("goals") },
  ];
}

function renderSetupProgress() {
  const node = $("setup-progress-list");
  if (!node) return;
  clear(node);
  const steps = setupSteps();
  const completed = steps.filter((step) => step.state === "completed").length;
  const percent = Math.round((completed / steps.length) * 100);
  $("setup-progress-percent").textContent = `${percent}% complete`;
  $("setup-progress-bar").style.width = `${percent}%`;
  const activeIndex = steps.findIndex((step) => step.state !== "completed");
  steps.forEach((step, index) => {
    const isActive = index === activeIndex && step.state !== "completed";
    node.appendChild(progressStep(step.title, step.description, isActive ? "running" : step.state, index, isActive ? step.action : null, isActive ? step.handler : null));
  });
}

function renderOverviewSummary() {
  const node = $("overview-summary");
  if (!node) return;
  clear(node);
  if (state.loading.initial || state.loading.reviews) return renderSkeletonList(node, 4);
  const metrics = state.overview?.metrics || {};
  if (state.overview) {
    [["PR reviews needing attention", metrics.pr_reviews_needing_attention ?? 0, "Organization-scoped active reviews", "amber"], ["PR reviews in progress", metrics.pr_reviews_in_progress ?? 0, "Analysis still underway", "teal"], ["Pending approvals", metrics.pending_approvals ?? 0, "Authenticated human decisions needed", "amber"], ["Active Cloud Hunt findings", metrics.active_cloud_hunt_findings ?? 0, "Unresolved findings", "green"], ["Predicted monthly savings", metrics.predicted_monthly_savings ? money(metrics.predicted_monthly_savings) : "Unavailable", "Prediction only; not verified savings", "blue"], ["Verified monthly savings", metrics.verified_monthly_savings ? money(metrics.verified_monthly_savings) : "Unavailable", "Evidence-backed outcomes only", "green"]].forEach(([label, value, helper, tone]) => { const card = el("article", "panel summary-card"); card.dataset.tone = tone; append(card, el("span", null, label), el("strong", "metric-value", value), el("small", null, helper)); node.appendChild(card); });
    return;
  }
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
    append(card, el("span", null, label), el("strong", "metric-value", value), el("small", null, helper));
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
  if (state.overview) {
    const attention = state.overview.needs_attention || [];
    attention.forEach((item) => { const row = el("article", "alert-row"); const open = el("button", "secondary compact", "Open"); open.type = "button"; open.addEventListener("click", () => switchMode(item.link === "/approvals" ? "review-queue" : "simple")); append(row, append(el("div"), el("strong", "row-title", item.title || "Review item"), el("span", "row-meta", `${labelFor(item.source_type)} · ${runStatusLabel(item.status)}`)), open); alertsNode.appendChild(row); });
    if (!attention.length) alertsNode.appendChild(el("p", "muted", "No cases currently require attention."));
    const opportunities = state.overview.top_opportunities || [];
    opportunities.forEach((item) => { const row = el("article", "compact-row"); append(row, append(el("div"), el("strong", "row-title", item.title), el("span", "row-meta", `${labelFor(item.source_type)} · ${runStatusLabel(item.status)} · ${labelFor(item.data_source_mode)}`)), el("strong", "metric-value-sm", money(item.estimated_monthly_savings) + "/month")); reviewNode.appendChild(row); });
    if (!opportunities.length) reviewNode.appendChild(el("p", "muted", "No supported opportunities are available."));
    return;
  }
  const rows = overviewReviews();
  const prRows = rows.filter((item) => item.source_type === "terraform_pr" || item.repository).slice(0, 5);
  const reviewColumns = [
    { label: "Repository", render: (item) => append(el("div"), el("strong", "row-title", item.repository || "Terraform review"), el("span", "row-meta", item.pull_request_number ? `PR #${item.pull_request_number}` : "Pull request not recorded")) },
    { label: "Terraform change", priority: "tablet", render: (item) => item.resource_name || "Not recorded" },
    { label: "Recommendation", priority: "tablet", render: (item) => item.recommendation || "Not recorded" },
    { label: "Status", render: (item) => runStatusLabel(item.status) },
    { label: "Savings", priority: "mobile", render: (item) => `${money(item.estimated_monthly_savings)}/month` },
    { label: "Action", render: (item) => {
      const open = el("button", "secondary compact", "Open PR Review");
      open.type = "button";
      open.setAttribute("aria-label", `Open review for ${item.repository || item.resource_name || "case"}`);
      open.addEventListener("click", async () => {
        if (item.id) {
          state.run = await api(`/api/runs/${item.id}`);
          state.selectedReviewContext = { source: "overview", type: "terraform_pr", runId: item.id };
          startAnimation(true);
        }
        switchMode("simple");
        showToast("Review loaded", "Opened PR review details.", "success");
      });
      return open;
    } },
  ];
  reviewNode.appendChild(responsiveTable(reviewColumns, prRows, "No PR reviews are loaded yet."));
  const alerts = rows.filter((item) => ["pending", "pending_human_review", "needs_more_evidence", "abstained"].includes(item.status)).slice(0, 4);
  if (!alerts.length) alertsNode.appendChild(el("p", "muted", "No cases currently require human approval."));
  alerts.forEach((item) => {
    const row = el("article", "alert-row");
    const open = el("button", "secondary compact", "Review Decision");
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
  if (state.overview) { node.appendChild(el("p", "muted", "Top opportunities are shown in Needs Attention and ranked from supported estimates.")); return; }
  const candidates = [...(state.hunt?.candidates || [])].sort((a, b) => Number(b.resource?.estimated_monthly_cost || 0) - Number(a.resource?.estimated_monthly_cost || 0)).slice(0, 4);
  if (!candidates.length) return node.appendChild(el("p", "muted", "Run Cloud Hunt to surface highest-value opportunities."));
  candidates.forEach((candidate) => {
    const resource = candidate.resource || {};
    const row = el("article", "featured-card");
    const primaryStatus = cloudCandidatePrimaryStatus(candidate);
    append(
      row,
      el("span", "repo-avatar", labelFor(resource.provider).slice(0, 2).toUpperCase()),
      append(el("div"), el("strong", "row-title", resource.resource_name || "Cloud resource"), el("span", "row-meta", `${labelFor(resource.provider)} ${labelFor(resource.normalized_resource_type)}`)),
      append(el("div", "row-metric"), el("span", null, "Potential savings"), el("strong", "metric-value-sm", `${money(resource.estimated_monthly_cost)}/month`)),
      statusBadge(primaryStatus)
    );
    node.appendChild(row);
  });
}

function renderOverviewRepositories() {
  const node = $("overview-repositories-list");
  if (!node) return;
  clear(node);
  const repos = connectedRepositories();
  $("overview-repository-count").textContent = `${repos.length} repo${repos.length === 1 ? "" : "s"}`;
  if (!repos.length) return node.appendChild(el("p", "muted", "No connected repositories are visible yet."));
  repos.slice(0, 5).forEach((repo) => {
    const related = overviewReviews().filter((item) => item.repository === repo).length;
    const row = el("article", "compact-row repo-row");
    append(row, el("span", "repo-avatar", repo.split("/").map((part) => part[0]).join("").slice(0, 2).toUpperCase()), append(el("div"), el("strong", "row-title", repo), el("span", "row-meta", `${related} review${related === 1 ? "" : "s"} recorded`)), el("span", "status-badge status-approved", "Connected"));
    node.appendChild(row);
  });
}

function renderOverviewActivity() {
  const node = $("overview-activity-list");
  if (!node) return;
  clear(node);
  const events = state.overview?.recent_activity || (state.run?.audit_events || []).slice(-5).reverse();
  $("overview-activity-count").textContent = `${events.length} event${events.length === 1 ? "" : "s"}`;
  const columns = [
    { label: "Activity", render: (event) => event.summary || labelFor(event.action || event.event_type) },
    { label: "Target", priority: "tablet", render: (event) => event.target || "Workspace" },
    { label: "Actor", priority: "mobile", render: (event) => event.actor || labelFor(event.actor_type) },
    { label: "Recorded", priority: "mobile", render: (event) => timestampNode(event.created_at || event.timestamp, "Activity") },
  ];
  node.appendChild(responsiveTable(columns, events, "Waiting for the first review workflow."));
}

function renderOverviewIntegrations() {
  const node = $("overview-integrations-list"); if (!node) return; clear(node); const items = Object.entries(state.overview?.integration_health || {});
  if (!items.length) return node.appendChild(el("p", "muted", "No integration health is visible for this account."));
  items.forEach(([name, item]) => { const row = el("div", "compact-row"); append(row, el("strong", null, labelFor(name)), statusBadge({ label: labelFor(item.status), className: item.status === "connected" ? "status-approved" : item.status === "unavailable" ? "status-blocked" : "status-neutral" }), el("small", "row-meta", `${item.permission_warning_count || 0} permission warnings`)); node.appendChild(row); });
}
function renderOverviewSchedules() {
  const node = $("overview-schedules-list"); if (!node) return; clear(node); const schedules = state.overview?.scheduled_hunts;
  if (!schedules) return node.appendChild(el("p", "muted", "Schedule access is not available."));
  append(node, el("p", "row-detail", `${schedules.enabled} enabled · ${schedules.failed} failed`), el("p", "row-detail", schedules.next ? `Next: ${exactTimestamp(schedules.next)}` : "No upcoming scheduled hunt"), el("p", "row-detail", schedules.last ? `Last: ${exactTimestamp(schedules.last)}` : "No scheduled hunt has run yet"));
}
function renderOverviewOutcomes() {
  const node = $("overview-outcomes-list"); if (!node) return; clear(node); const summary = state.overview?.outcome_summary;
  if (!summary) return node.appendChild(el("p", "muted", "Outcome verification data is unavailable or not yet recorded."));
  [["Verified success", summary.verified_success], ["Verified partial", summary.verified_partial], ["Pending", summary.pending], ["Insufficient evidence", summary.insufficient_evidence], ["Regressions", summary.regressions]].forEach(([label, value]) => { const card = el("article", "summary-card compact-summary"); append(card, el("span", null, label), el("strong", null, String(value))); node.appendChild(card); });
}

function renderOverview() {
  renderSetupProgress();
  renderOverviewSummary();
  renderOverviewRows();
  renderOverviewSavings();
  renderOverviewRepositories();
  renderOverviewActivity();
  renderOverviewIntegrations(); renderOverviewSchedules(); renderOverviewOutcomes();
}

function renderMembers() {
  const summary = $("members-summary");
  const activeNode = $("active-members-table");
  const inviteNode = $("pending-invitations-table");
  if (!summary || !activeNode || !inviteNode) return;
  if ($("invite-member-button")) $("invite-member-button").hidden = !hasPermission("members.invite");
  clear(summary);
  clear(activeNode);
  clear(inviteNode);
  const activeMembers = state.members.filter((item) => item.membership?.status === "active");
  const pending = state.invitations.filter((item) => item.status === "PENDING");
  const reviewers = activeMembers.filter((item) => item.membership?.role === "REVIEWER").length;
  [
    ["Active Members", activeMembers.length, "Can access this workspace"],
    ["Pending Invitations", pending.length, "Awaiting acceptance"],
    ["Reviewers", reviewers, "Reviewer role members"],
  ].forEach(([label, value, helper]) => {
    summary.appendChild(append(el("article", "panel summary-card"), el("span", null, label), el("strong", "metric-value", value), el("small", null, helper)));
  });
  const memberColumns = [
    { label: "Member", render: (item) => append(el("div"), el("strong", "row-title", `${item.user?.display_name || "Unknown"}${item.user?.id === state.currentUser?.user?.id ? " (You)" : ""}`), el("span", "row-meta", item.user?.email || "No email")) },
    { label: "Role", priority: "tablet", render: (item) => roleValueLabel(item.membership?.role) },
    { label: "Approval Permission", priority: "tablet", render: (item) => item.membership?.approval_permission_enabled ? "Enabled" : "Disabled" },
    { label: "Status", render: (item) => statusBadge({ label: labelFor(item.membership?.status), className: item.membership?.status === "active" ? "status-approved" : "status-neutral" }) },
    { label: "Joined", priority: "mobile", render: (item) => item.membership?.joined_at ? exactTimestamp(item.membership.joined_at) : "Not recorded" },
    { label: "Last Active", priority: "mobile", render: (item) => item.user?.last_login_at ? exactTimestamp(item.user.last_login_at) : "Not recorded" },
    { label: "Action", render: (item) => memberActions(item) },
  ];
  activeNode.appendChild(responsiveTable(memberColumns, state.members, "No members found."));
  const invitationColumns = [
    { label: "Email", render: (item) => item.email },
    { label: "Assigned Role", priority: "tablet", render: (item) => item.role_label || roleValueLabel(item.assigned_role) },
    { label: "Approval Permission", priority: "tablet", render: (item) => item.approval_permission_enabled ? "Enabled" : "Disabled" },
    { label: "Invited By", priority: "mobile", render: (item) => item.invited_by || "Unknown" },
    { label: "Created", priority: "mobile", render: (item) => exactTimestamp(item.created_at) },
    { label: "Expires", priority: "mobile", render: (item) => exactTimestamp(item.expires_at) },
    { label: "Status", render: (item) => statusBadge({ label: invitationStatusLabel(item.status), className: item.status === "PENDING" ? "status-awaiting-review" : item.status === "ACCEPTED" ? "status-approved" : "status-neutral" }) },
    { label: "Action", render: (item) => invitationActions(item) },
  ];
  inviteNode.appendChild(responsiveTable(invitationColumns, state.invitations, "No invitations found."));
}

function invitationActions(item) {
  const wrap = el("div", "queue-actions");
  if (!hasPermission("members.invite") && !hasPermission("members.cancel_invitation")) return el("span", "muted", "Read-only");
  if (item.development_invitation_link) {
    const copy = el("button", "secondary compact", "Copy Link");
    copy.type = "button";
    copy.addEventListener("click", () => copyInvitationLink(item.development_invitation_link));
    wrap.appendChild(copy);
  }
  if (item.status === "PENDING" || item.status === "EXPIRED") {
    const resend = el("button", "secondary compact", "Resend");
    resend.type = "button";
    resend.addEventListener("click", () => resendInvitation(item.id));
    wrap.appendChild(resend);
  }
  if (item.status === "PENDING") {
    const cancel = el("button", "secondary compact", "Cancel");
    cancel.type = "button";
    cancel.addEventListener("click", () => cancelInvitation(item.id));
    wrap.appendChild(cancel);
  }
  return wrap;
}

function memberActions(item) {
  if (!hasPermission("members.manage_roles") && !hasPermission("members.disable")) return el("span", "muted", "Read-only");
  const wrap = el("div", "queue-actions");
  if (hasPermission("members.manage_roles")) { const select = el("select", "compact-select"); ["ADMIN", "REVIEWER", "VIEWER"].forEach((role) => { const option = el("option", null, roleValueLabel(role)); option.value = role; option.selected = item.membership?.role === role; select.appendChild(option); }); select.addEventListener("change", async () => { try { await api(`/api/members/${item.membership.id}`, { method: "PATCH", body: JSON.stringify({ role: select.value }) }); await loadMembers(); } catch (error) { showToast("Role update failed", friendlyError(error), "error"); } }); wrap.appendChild(select); }
  if (hasPermission("members.disable") && item.membership?.user_id !== state.currentUser?.user?.id) { const button = el("button", "secondary compact", item.membership?.status === "active" ? "Disable" : "Enable"); button.addEventListener("click", async () => { try { await api(`/api/members/${item.membership.id}/${item.membership.status === "active" ? "disable" : "reactivate"}`, { method: "POST", body: "{}" }); await loadMembers(); } catch (error) { showToast("Member update failed", friendlyError(error), "error"); } }); wrap.appendChild(button); }
  return wrap;
}

function openInviteModal() {
  $("invite-modal-backdrop").hidden = false;
  $("invite-development-link").hidden = true;
  clear($("invite-development-link"));
  setMessage("invite-message", "");
}

function closeInviteModal() {
  $("invite-modal-backdrop").hidden = true;
}

async function submitInvite() {
  setMessage("invite-message", "Creating invitation...", true);
  try {
    const response = await api("/api/invitations", {
      method: "POST",
      body: JSON.stringify({
        email: $("invite-email-input").value,
        role: $("invite-role-select").value,
        approval_permission_enabled: $("invite-approval-checkbox").checked,
        note: $("invite-note-input").value || null,
      }),
    });
    showDevelopmentLink(response.development_invitation_link);
    setMessage("invite-message", "Development invitation link created.", true);
    await loadMembers();
  } catch (error) {
    setMessage("invite-message", friendlyError(error, "Failed to create invitation."));
  }
}

function showDevelopmentLink(link) {
  const node = $("invite-development-link");
  clear(node);
  node.hidden = !link;
  if (!link) return;
  const input = el("input");
  input.value = link;
  input.readOnly = true;
  const copy = el("button", "secondary compact", "Copy Link");
  copy.type = "button";
  copy.addEventListener("click", () => copyInvitationLink(link));
  append(node, el("strong", null, "Development invitation link"), input, copy);
}

async function copyInvitationLink(link) {
  if (navigator.clipboard) await navigator.clipboard.writeText(link);
  showToast("Invitation link copied", "Share it with the invited employee.", "success");
}

async function resendInvitation(id) {
  try {
    const response = await api(`/api/invitations/${id}/resend`, { method: "POST", body: "{}" });
    if (response.development_invitation_link) showDevelopmentLink(response.development_invitation_link);
    await loadMembers();
    showToast("Invitation resent", "A new secure invitation link was generated.", "success");
  } catch (error) {
    showToast("Resend failed", friendlyError(error), "error");
  }
}

async function cancelInvitation(id) {
  try {
    await api(`/api/invitations/${id}/cancel`, { method: "POST", body: "{}" });
    await loadMembers();
    showToast("Invitation canceled", "The invitation link is no longer valid.", "success");
  } catch (error) {
    showToast("Cancel failed", friendlyError(error), "error");
  }
}

function renderAll() {
  $("pr-empty-state").hidden = hasSelectedCase();
  $("case-view").hidden = !hasSelectedCase();
  renderIdentity();
  renderAssistantTriggers();
  renderStatus(); renderSource(); renderGitHubContext(); renderJiraContext(); renderPlanningStatus(); renderStages(); renderRecommendation(); renderEvidenceSummary(); renderHumanControls(); renderResult(); renderOutcomeVerification(); renderTechnical();
  renderPRReviewList(); renderCloudRunHistory(); renderCloudHunt(); renderGoalRepositoryScope(); renderGoalList(); renderGoalExecution(); renderReviewQueue(); renderOverview(); renderMembers(); renderActivityLog();
}

function renderGitHubContext() {
  const panel = $("github-context-panel"); if (!panel) return;
  const context = state.run?.github_context;
  panel.hidden = !state.run?.github_source;
  if (!state.run?.github_source) return;
  const source = state.run.github_source;
  $("github-context-pr").textContent = `#${source.pull_request_number || "?"}`;
  $("github-context-commits").textContent = context ? String(context.commit_activity?.recent_commit_count ?? "0") : "Not collected";
  $("github-context-reviews").textContent = context ? `${(context.reviews || []).length} recorded` : "Not collected";
  $("github-context-codeowners").textContent = context?.codeowners_available ? "Available" : context ? "Unknown" : "Not collected";
  $("github-context-summary").textContent = context ? `${context.pr?.title || "Pull request context"} · ${context.repository_default_branch || "default branch not recorded"} · Source mode: ${context.source_mode || "real_github"}` : "Context is collected read-only from the configured GitHub source.";
  const ownership = $("github-context-ownership"); clear(ownership);
  (context?.ownership || []).forEach((item) => ownership.appendChild(el("p", "muted", `${item.path}: ${item.owners?.join(", ") || "Unknown owner"} (${item.matched_pattern || "no matching pattern"})`)));
}

function renderJiraContext() {
  const panel = $("jira-context-panel"); if (!panel) return;
  const context = state.run?.jira_context;
  panel.hidden = !context;
  if (!context) return;
  $("jira-context-project").textContent = context.project_key || "Not recorded";
  $("jira-context-issue").textContent = context.issue_key || "Not recorded";
  $("jira-context-status").textContent = context.issue?.status || "Not recorded";
  $("jira-context-owner").textContent = context.ownership?.owner || "Unknown";
  $("jira-context-summary").textContent = `Source mode: ${context.source_mode || "Real Jira"}. Activity reliability: ${Math.round(Number(context.activity?.reliability || 0) * 100)}%.`;
  const signals = $("jira-context-signals"); clear(signals);
  (context.signals || []).forEach((signal) => signals.appendChild(el("span", "status-badge status-warning", labelFor(signal.type || "signal"))));
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
    goals: ["Orchestration", "Autonomous Goals"],
    "cloud-hunt": ["Discovery", "Cloud Hunt"],
    "review-queue": ["Human control", "Approvals"],
    technical: ["Audit", "Technical Audit"],
    activity: ["Workspace", "Activity Log"],
    settings: ["Settings", "Members"],
    "demo-readiness": ["Competition Demo", "Demo Readiness"],
  };
  ["overview", "simple", "goals", "cloud-hunt", "review-queue", "technical", "activity", "settings", "demo-readiness"].forEach((item) => {
    const view = item === "simple" ? "simple-view" : `${item}-view`;
    const button = item === "simple" ? "simple-view-button" : `${item}-view-button`;
    const viewNode = $(view); const buttonNode = $(button);
    if (!viewNode || !buttonNode) return;
    viewNode.hidden = item !== mode;
    buttonNode.classList.toggle("active", item === mode);
    buttonNode.setAttribute("aria-pressed", String(item === mode));
  });
  state.activeMode = mode;
  if (mode === "settings") { loadMembers(); loadWorkspaceSettings(); renderRolesAccess(); renderPoliciesSettings(); renderSecuritySettings(); renderRepositorySettings(); }
  if (mode === "settings") loadAWSConfig();
  if (mode === "settings") { loadGitHubConfig(); loadJiraConfig(); loadCloudSchedules(); }
  if (mode === "goals") loadGitHubConfig();
  if (mode === "activity") loadActivity();
  if (mode === "overview") loadOverview();
  if (mode === "demo-readiness") loadDemoReadiness();
  $("page-kicker").textContent = titles[mode]?.[0] || "Workspace";
  $("page-title").textContent = titles[mode]?.[1] || "Overview";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function switchView(technical) { switchMode(technical ? "technical" : "simple"); }

function cloudReviewStatusForCandidate(candidate) {
  if (candidate?.review_status) return reviewStateStatus(candidate.review_status);
  if (candidate?.exclusion_reason) return null;
  return reviewStateStatus("pending_human_review");
}

function cloudCaseForCandidate(candidate) {
  if (!candidate) return null;
  const resource = candidate.resource || {};
  const selectedRunId = state.selectedReviewContext?.source === "approvals" ? null : state.hunt?.id;
  return (state.reviews || []).find((item) =>
    item.source_type === "cloud_hunt" && (!selectedRunId || item.source_reference === selectedRunId) && (
      item.id === state.selectedReviewContext?.runId ||
      item.candidate?.candidate_id === candidate.candidate_id ||
      item.resource_id === resource.resource_id ||
      item.resource_name === resource.resource_name
    )
  ) || null;
}

function selectedCloudCase() {
  const context = state.selectedReviewContext;
  if (context?.type !== "cloud_hunt") return null;
  return (state.reviews || []).find((item) =>
    item.id === context.runId ||
    item.candidate?.candidate_id === context.candidateId ||
    item.resource_id === context.resourceId
  ) || null;
}

function selectedCloudCandidate() {
  const context = state.selectedReviewContext;
  if (context?.type !== "cloud_hunt") return null;
  const fromCase = selectedCloudCase()?.candidate;
  if (fromCase?.resource) return fromCase;
  return (state.hunt?.candidates || []).find((candidate) =>
    candidate.candidate_id === context.candidateId ||
    candidate.resource?.resource_id === context.resourceId
  ) || null;
}

function updateBrowserCaseState(context) {
  if (typeof window === "undefined" || !window.history?.replaceState) return;
  const token = context?.runId || context?.candidateId || context?.resourceId;
  if (!token) return;
  window.history.replaceState(null, "", `#cloud-hunt/${encodeURIComponent(token)}`);
}

function selectCloudFinding(candidate, source = "cloud-hunt", caseItem = null) {
  const resource = candidate?.resource || caseItem?.candidate?.resource || {};
  const reviewCase = caseItem || cloudCaseForCandidate(candidate);
  state.selectedReviewContext = {
    source,
    type: "cloud_hunt",
    runId: reviewCase?.id || null,
    candidateId: candidate?.candidate_id || reviewCase?.candidate?.candidate_id || null,
    resourceId: resource.resource_id || reviewCase?.resource_id || null,
    resourceName: resource.resource_name || reviewCase?.resource_name || "Cloud resource",
  };
  closeCloudReviewForm();
  updateBrowserCaseState(state.selectedReviewContext);
  switchMode("cloud-hunt");
  renderCloudHunt();
  $("cloud-finding-detail")?.focus?.();
}

function backFromCloudFinding() {
  const source = state.selectedReviewContext?.source;
  state.selectedReviewContext = null;
  closeCloudReviewForm();
  renderCloudHunt();
  if (source === "approvals") {
    switchMode("review-queue");
    return;
  }
  switchMode("cloud-hunt");
}

function signalList(candidate, supports) {
  return (candidate?.signals || []).filter((signal) => Boolean(signal.supports_ghost_hypothesis) === supports);
}

function dependencySummary(candidate) {
  const dependencies = (candidate?.signals || [])
    .filter((signal) => /dependency/i.test(signal.signal_type || signal.description || ""))
    .map((signal) => signal.description);
  return dependencies.length ? dependencies.join("; ") : "No dependency signal recorded";
}

function cloudCaseStatus(caseItem, candidate) {
  if (caseItem) return reviewStateStatus(caseItem.status);
  return cloudReviewStatusForCandidate(candidate) || { key: "neutral", label: "No action required", className: "status-neutral" };
}

function isCloudProtected(candidate, caseItem) {
  if (candidate?.exclusion_reason) return true;
  if (caseItem?.policy_status === "blocked") return true;
  return (candidate?.signals || []).some((signal) => ["active_dependency", "production_resource"].includes(signal.signal_type));
}

function cloudAllowedReviewActions(caseItem, candidate) {
  if (!caseItem) return [];
  const status = caseItem.status;
  const protectedResource = isCloudProtected(candidate, caseItem);
  if (["blocked", "protected", "waived", "completed"].includes(status)) return [];
  if (["approved", "pr_created", "remediation_pr_created", "remediation_proposal_prepared"].includes(status)) return ["revoke_approval", "add_follow_up_context"];
  if (["rejected", "approval_revoked"].includes(status)) return ["reopen_case", "add_follow_up_context"];
  if (status === "reopened") return ["add_follow_up_context", "request_evidence", "reject"];
  if (caseItem.policy_status === "blocked") return [];
  if (protectedResource) return status === "needs_more_evidence" ? ["request_evidence", "add_context", "reject"] : ["request_evidence", "add_context", "reject"];
  if (status === "needs_more_evidence") return ["request_evidence", "add_context", "reject"];
  if (status === "pending" || status === "pending_human_review") return ["approve", "request_evidence", "reject", "add_context"];
  return [];
}

function renderSignalBullets(nodeId, items, emptyMessage) {
  const node = $(nodeId);
  clear(node);
  const caution = /caution/i.test(nodeId);
  if (!items.length) {
    node.appendChild(el("p", "muted", emptyMessage));
    return;
  }
  items.forEach((signal) => {
    const danger = ["active_dependency", "production_resource"].includes(signal.signal_type);
    const item = el("div", `signal ${danger ? "signal-danger" : caution ? "signal-warning" : "signal-info"}`);
    append(item, el("strong", null, labelFor(signal.signal_type || "Signal")), el("span", null, signal.description || formatValue(signal.value)));
    node.appendChild(item);
  });
}

function cloudHuntFilterCounts(candidates) {
  return candidates.reduce((counts, candidate) => {
    const primary = cloudCandidatePrimaryStatus(candidate);
    const review = cloudReviewStatusForCandidate(candidate);
    counts.all += 1;
    if (primary.key === "high-confidence") counts["high-confidence"] += 1;
    if (primary.key === "protected") counts.protected += 1;
    if (primary.key === "needs-context") counts["needs-context"] += 1;
    if (review?.key === "awaiting-review") counts["awaiting-review"] += 1;
    return counts;
  }, { all: 0, "high-confidence": 0, protected: 0, "needs-context": 0, "awaiting-review": 0 });
}

function renderCloudHuntFilterChips(candidates = []) {
  const counts = cloudHuntFilterCounts(candidates);
  Object.entries(counts).forEach(([key, count]) => {
    const countNode = $(`filter-count-${key}`);
    if (countNode) countNode.textContent = String(count);
  });
  document.querySelectorAll("[data-hunt-filter]").forEach((chip) => {
    const active = chip.dataset.huntFilter === state.cloudHuntFilter;
    chip.classList.toggle("filter-chip-active", active);
    chip.setAttribute("aria-pressed", String(active));
  });
}

function candidateMatchesCloudFilter(candidate) {
  const filter = state.cloudHuntFilter || "all";
  if (filter === "all") return true;
  const primary = cloudCandidatePrimaryStatus(candidate);
  const review = cloudReviewStatusForCandidate(candidate);
  if (filter === "high-confidence") return primary.key === "high-confidence";
  if (filter === "protected") return primary.key === "protected";
  if (filter === "needs-context") return primary.key === "needs-context";
  if (filter === "awaiting-review") return review?.key === "awaiting-review";
  return true;
}

function journeyEventMatches(event, definition) {
  const type = event.event_type || "";
  return definition.matches?.includes(type) || definition.prefix?.some((prefix) => type.startsWith(prefix));
}

function cloudJourneyStageState(definition, index, events, hunt) {
  if (!hunt) return "waiting";
  if (hunt.status === "failed") return index === 0 ? "failed" : "waiting";
  if (events.some((event) => journeyEventMatches(event, definition))) return "completed";
  if (hunt.status === "completed") {
    if (["inventory", "evaluated", "risks", "classified"].includes(definition.id)) return "completed";
    if (definition.id === "human" && (hunt.summary?.needs_human_context || 0) > 0) return "human action required";
    return "waiting";
  }
  if (definition.id === "inventory") return "running";
  return "waiting";
}

function renderCloudJourney() {
  const node = $("cloud-journey-list");
  if (!node) return;
  clear(node);
  const hunt = state.hunt;
  const events = hunt?.audit_events || [];
  $("cloud-journey-state").textContent = hunt ? runStatusLabel(hunt.status) : "Waiting";
  const descriptions = {
    inventory: "Provider inventory is loaded from the configured source.",
    evaluated: "Resources are evaluated for usage, age, and ownership signals.",
    risks: "Dependencies, protection signals, and policy constraints are checked.",
    classified: "Candidates are classified into reviewable states.",
    human: "Reviewers decide whether remediation is appropriate.",
    proposal: "A remediation proposal can be prepared after approval.",
  };
  cloudJourneyDefinitions.forEach((definition, index) => {
    const stateName = cloudJourneyStageState(definition, index, events, hunt);
    node.appendChild(progressStep(definition.title, descriptions[definition.id], stateName, index));
  });
}

function renderCloudFindingDetail() {
  const panel = $("cloud-finding-detail");
  if (!panel) return;
  const candidate = selectedCloudCandidate();
  const caseItem = selectedCloudCase() || cloudCaseForCandidate(candidate);
  panel.hidden = !candidate && !caseItem;
  if (panel.hidden) return;
  const resource = candidate?.resource || caseItem?.candidate?.resource || {};
  const status = cloudCaseStatus(caseItem, candidate);
  const primary = cloudCandidatePrimaryStatus(candidate || caseItem?.candidate);
  const policyMeta = policyStatusMeta(caseItem?.policy_status || (candidate?.exclusion_reason ? "needs_human_context" : "passed"));
  const source = state.selectedReviewContext?.source === "approvals" ? "Approvals" : "Cloud Hunt";
  const resourceName = resource.resource_name || caseItem?.resource_name || "Cloud resource";
  const managedByTerraform = Boolean(resource.infrastructure_as_code_managed && resource.terraform_address);
  $("cloud-finding-path").textContent = source === "Approvals" ? `Approvals -> ${resourceName}` : `Cloud Hunt -> ${resourceName}`;
  $("cloud-finding-title").textContent = resourceName;
  $("cloud-finding-context").textContent = source === "Approvals" ? "Review the selected approval case without returning to the generic Cloud Hunt list." : "Inspect this finding before opening a human approval decision.";
  $("cloud-back-button").textContent = source === "Approvals" ? "Back to Approvals" : "Back to Cloud Hunt";
  $("cloud-detail-provider").textContent = labelFor(resource.provider || caseItem?.provider);
  $("cloud-detail-resource").textContent = resourceName;
  $("cloud-detail-type").textContent = labelFor(resource.normalized_resource_type || resource.provider_resource_type);
  $("cloud-detail-environment").textContent = resource.environment || "Not recorded";
  $("cloud-detail-cost").textContent = money(resource.estimated_monthly_cost);
  $("cloud-detail-savings").textContent = caseItem?.estimated_monthly_savings ? `${money(caseItem.estimated_monthly_savings)}/month` : candidate?.exclusion_reason ? "Not available" : `${money(resource.estimated_monthly_cost)}/month`;
  $("cloud-detail-confidence").textContent = percentage(candidate?.candidate_score ?? caseItem?.confidence);
  setStatusBadge("cloud-detail-classification", { ...primary, icon: null });
  setStatusBadge("cloud-detail-review-state", { ...status, icon: null, label: status.key === "awaiting-review" ? "Awaiting human review" : status.label });
  $("cloud-detail-owner").textContent = resource.owner || "Owner not recorded";
  $("cloud-detail-project").textContent = resource.project || "Project not recorded";
  $("cloud-detail-dependencies").textContent = dependencySummary(candidate || caseItem?.candidate);
  $("cloud-detail-terraform").textContent = resource.terraform_address || caseItem?.terraform_address || "No Terraform repository mapping";
  $("cloud-detail-recommendation").textContent = recommendationLabel(caseItem?.recommendation || (candidate?.exclusion_reason ? "keep" : "request_owner_confirmation"));
  $("cloud-detail-recommendation").className = "recommendation-action-value";
  setStatusBadge("cloud-detail-policy", policyMeta);
  $("cloud-detail-policy-state").textContent = policyMeta.label;
  setStatusBadge("cloud-detail-human-required", humanReviewStatusMeta(caseItem));
  setStatusBadge("cloud-detail-classification-inline", { ...primary, icon: null });
  $("cloud-detail-review-id").textContent = caseItem?.id || "No review case is linked";
  $("cloud-detail-run-id").textContent = state.hunt?.id || caseItem?.source_reference || "Not recorded";
  $("cloud-detail-provider-id").textContent = resource.resource_id || caseItem?.resource_id || "Not recorded";
  $("cloud-detail-audit-ref").textContent = caseItem?.source_reference || state.hunt?.trigger_source || "Not recorded";
  const recurrence = caseItem?.recurrence || {};
  $("cloud-detail-first-seen").textContent = recurrence.first_seen ? exactTimestamp(recurrence.first_seen) : "Not recorded";
  $("cloud-detail-last-seen").textContent = recurrence.last_seen ? exactTimestamp(recurrence.last_seen) : "Not recorded";
  $("cloud-detail-times-detected").textContent = recurrence.times_detected ?? "Not recorded";
  $("cloud-detail-latest-classification").textContent = recurrence.latest_classification ? labelFor(recurrence.latest_classification) : "Not recorded";
  $("cloud-detail-latest-decision").textContent = recurrence.latest_decision_state ? labelFor(recurrence.latest_decision_state) : "Not recorded";
  renderSignalBullets("cloud-detail-flagged", signalList(candidate || caseItem?.candidate, true), "No positive waste signals were recorded.");
  renderSignalBullets("cloud-detail-caution", signalList(candidate || caseItem?.candidate, false), "No caution signals were recorded.");
  $("cloud-open-approval-button").hidden = !(caseItem && ["pending", "pending_human_review", "needs_more_evidence"].includes(caseItem.status));
  $("cloud-human-title").textContent = caseItem ? status.label === "Pending human review" ? "Awaiting human review" : status.label : "Finding detail";
  setStatusBadge("cloud-human-status", decisionStatusMeta(caseItem?.status, caseItem?.human_decision ? labelFor(caseItem.human_decision) : caseItem ? status.label : "No approval case"));
  $("cloud-human-technical").hidden = true;
  $("cloud-human-technical").textContent = "";
  $("cloud-human-guidance").textContent = !caseItem
    ? "This finding can be inspected, but no human approval case is currently linked."
    : isCloudProtected(candidate, caseItem)
      ? "Approval is unavailable because this resource has protection or dependency signals. A reviewer can request more evidence, add context, or reject the recommendation."
      : caseItem.status === "needs_more_evidence"
        ? "Approval is unavailable until missing evidence or owner context is resolved."
        : cloudAllowedReviewActions(caseItem, candidate).length
          ? "Choose a decision action for this Cloud Hunt approval case."
          : "No further human action is available for this case.";
  $("cloud-safety-notice").textContent = managedByTerraform
    ? "Approval creates a remediation pull request or approved remediation proposal only. GhostOps does not apply Terraform, merge pull requests, or modify cloud resources directly."
    : "Approval records the remediation decision and prepares the next supported remediation step. GhostOps does not apply Terraform, merge pull requests, or modify cloud resources directly.";
  renderCloudHumanControls(caseItem, candidate);
}

function renderCloudHumanControls(caseItem, candidate) {
  const allowed = cloudAllowedReviewActions(caseItem, candidate).filter((action) => hasPermission(approvalPermissionFor(action)));
  document.querySelectorAll("[data-cloud-review-action]").forEach((button) => {
    const visible = allowed.includes(button.dataset.cloudReviewAction);
    button.hidden = !visible;
    button.disabled = !visible;
  });
  if (state.selectedCloudReviewAction && !allowed.includes(state.selectedCloudReviewAction)) closeCloudReviewForm();
}

function selectCloudReviewAction(action) {
  state.selectedCloudReviewAction = action;
  $("cloud-review-form").hidden = false;
  $("cloud-review-form-title").textContent = labelFor(action);
  $("cloud-sources-field").hidden = action !== "request_evidence";
  $("cloud-context-field").hidden = !(action === "add_context" || action === "add_follow_up_context");
  $("cloud-comment-input").placeholder = ["reject", "revoke_approval", "reopen_case", "modify"].includes(action) ? "Required reason" : "Optional decision note";
  $("cloud-submit-review-button").textContent = action === "approve" ? "Approve Recommendation" : action === "reject" ? "Confirm Rejection" : action === "revoke_approval" ? "Revoke Approval" : action === "reopen_case" ? "Reopen Case" : "Send Decision Update";
  $("cloud-review-form").scrollIntoView({ block: "nearest" });
}

function closeCloudReviewForm() {
  state.selectedCloudReviewAction = null;
  const form = $("cloud-review-form");
  if (form) form.hidden = true;
}

async function submitSelectedCloudReview() {
  const action = state.selectedCloudReviewAction;
  const caseItem = selectedCloudCase();
  if (!action || !caseItem) return;
  const payload = { action, comment: $("cloud-comment-input").value || null, expected_version: caseItem.version, idempotency_key: decisionIdempotencyKey(caseItem.id, action) };
  if (action === "request_evidence") payload.requested_sources = $("cloud-requested-sources").value.split(",").map((item) => item.trim()).filter(Boolean);
  if (action === "add_context" || action === "add_follow_up_context") payload.human_context = $("cloud-human-context").value || null;
  return withButtonState("cloud-submit-review-button", action === "approve" ? "Recording approval..." : "Saving decision...", async () => {
    const updated = await api(`/api/reviews/${caseItem.id}/action`, { method: "POST", body: JSON.stringify(payload) });
    state.reviews = state.reviews.map((item) => item.id === updated.id ? updated : item);
    state.selectedReviewContext = {
      ...state.selectedReviewContext,
      runId: updated.id,
      candidateId: updated.candidate?.candidate_id || state.selectedReviewContext?.candidateId,
      resourceId: updated.resource_id || state.selectedReviewContext?.resourceId,
      resourceName: updated.resource_name || state.selectedReviewContext?.resourceName,
    };
    closeCloudReviewForm();
    renderCloudHunt();
    renderReviewQueue();
    renderOverview();
    const title = action === "approve" && updated.remediation_result?.created ? "Remediation PR created" : action === "approve" ? "Remediation proposal prepared" : "Decision recorded";
    showToast(title, `Correlation ${updated.correlation_id || "recorded"}.`, "success");
  }, "Recorded").catch((error) => {
    const message = friendlyError(error, "Failed to record cloud decision.");
    setMessage("cloud-review-message", message);
    showToast("Decision failed", message, "error");
  });
}

function renderCloudHunt() {
  const summary = $("cloud-hunt-summary");
  if (!summary) return;
  renderCloudRunDetailMeta();
  if ($("cloud-data-source-badge")) $("cloud-data-source-badge").textContent = state.hunt?.data_source_mode || "Fixture-backed";
  clear(summary);
  renderCloudJourney();
  renderCloudFindingDetail();
  if (state.loading.cloudHunt) {
    renderSkeletonList(summary, 6);
    renderSkeletonList($("candidate-list"), 4);
    $("candidate-count").textContent = "Scanning";
    return;
  }
  const data = state.hunt?.summary;
  if (!data) {
    renderCloudHuntFilterChips([]);
    summary.appendChild(el("p", "muted", "No cloud-hunt scan has been run yet."));
    $("candidate-count").textContent = "0 candidates";
    const list = $("candidate-list");
    clear(list);
    list.appendChild(el("p", "muted", "No cloud-hunt candidates to review yet."));
    return;
  }
  [["Provider scope", labelFor(state.hunt.provider_scope)], ["Resources scanned", data.total_resources], ["Candidates found", data.candidates], ["Protected resources", data.protected_candidates], ["Pending human reviews", data.needs_human_context], ["Monthly waste", money(data.estimated_monthly_waste)]].forEach(([label, value]) => {
    const card = el("article", "panel hunt-metric");
    append(card, el("span", null, label), el("strong", "metric-value-sm", value));
    summary.appendChild(card);
  });
  $("candidate-count").textContent = `${data.candidates} candidate${data.candidates === 1 ? "" : "s"}`;
  const list = $("candidate-list"); clear(list);
  const allCandidates = state.hunt.candidates || [];
  renderCloudHuntFilterChips(allCandidates);
  const candidates = allCandidates.filter(candidateMatchesCloudFilter);
  const columns = [
    { label: "Provider", priority: "mobile", render: (candidate) => labelFor(candidate.resource?.provider) },
    { label: "Resource", render: (candidate) => candidate.resource?.resource_name || "Cloud resource" },
    { label: "Resource type", priority: "tablet", render: (candidate) => labelFor(candidate.resource?.normalized_resource_type) },
    { label: "Environment", priority: "mobile", render: (candidate) => candidate.resource?.environment || "Not recorded" },
    { label: "Monthly cost", priority: "mobile", render: (candidate) => money(candidate.resource?.estimated_monthly_cost) },
    { label: "Potential savings", render: (candidate) => candidate.exclusion_reason ? "Not available" : `${money(candidate.resource?.estimated_monthly_cost)}/month` },
    { label: "Confidence", render: (candidate) => percentage(candidate.candidate_score) },
    { label: "Classification", render: (candidate) => statusBadge(cloudCandidatePrimaryStatus(candidate)) },
    { label: "Review status", render: (candidate) => {
      const reviewStatus = cloudCaseStatus(cloudCaseForCandidate(candidate), candidate);
      return reviewStatus ? statusBadge(reviewStatus) : statusBadge({ label: "No Action", className: "status-neutral" });
    } },
    { label: "Action", render: (candidate) => {
      const viewFinding = el("button", "secondary compact", "View Finding");
      viewFinding.type = "button";
      viewFinding.setAttribute("aria-label", `View finding for ${candidate.resource?.resource_name || "cloud resource"}`);
      viewFinding.addEventListener("click", () => selectCloudFinding(candidate, "cloud-hunt"));
      return viewFinding;
    } },
  ];
  list.appendChild(responsiveTable(columns, candidates, "No cloud-hunt candidates match the selected filters."));
  renderCloudFindingDetail();
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
  const columns = [
    { label: "Source", priority: "mobile", render: (item) => labelFor(item.source_type) },
    { label: "Resource or repository", render: (item) => item.source_type === "terraform_pr" ? item.repository || item.resource_name || "Review case" : item.resource_name || item.repository || "Review case" },
    { label: "Recommendation", priority: "tablet", render: (item) => item.recommendation || "Not recorded" },
    { label: "Confidence", render: (item) => percentage(item.confidence) },
    { label: "Savings", priority: "mobile", render: (item) => `${money(item.estimated_monthly_savings)}/month` },
    { label: "Policy status", render: (item) => policyStatusLabel(item.policy_status) },
    { label: "Current state", render: (item) => statusBadge(reviewStateStatus(item.status)) },
    { label: "Updated", priority: "tablet", render: (item) => item.updated_at || item.created_at || "Not recorded" },
    { label: "Action", render: (item) => {
      const open = el("button", "secondary compact", "Review Decision");
      open.type = "button";
      open.setAttribute("aria-label", `Review decision for ${item.resource_name || item.repository || "case"}`);
      if (item.source_type === "terraform_pr") {
        open.addEventListener("click", async () => {
          state.run = await api(`/api/runs/${item.id}`);
          state.selectedReviewContext = { source: "approvals", type: "terraform_pr", runId: item.id };
          startAnimation(true);
          switchMode("simple");
          $("human-title")?.scrollIntoView({ block: "start" });
        });
      } else {
        open.addEventListener("click", () => {
          selectCloudFinding(item.candidate, "approvals", item);
        });
      }
      return open;
    } },
  ];
  node.appendChild(responsiveTable(columns, state.reviews, "No review cases are waiting right now."));
}

const assistantSuggestions = {
  pr_review: ["Why do you recommend this?", "Which evidence affected confidence?", "What happens if I approve?", "Were any conflicts detected?", "Did GhostOps change anything?"],
  cloud_hunt: ["Why was this resource flagged?", "Why is this resource protected?", "What evidence is missing?", "What action is being recommended?"],
  approvals: ["Why is this waiting for approval?", "What are the safety conditions?", "What happens after approval?"],
  technical_audit: ["Which tools were selected and why?", "Were retries used?", "Which policy rules were evaluated?", "What evidence was missing?"],
  product_help: ["What is PR Reviews?", "What is Cloud Hunt?", "What is Approvals?", "Does GhostOps run Terraform?"],
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
    loadReviewQueue,
    loadPRReviews,
    loadGoals,
    selectGoal,
    renderGoalExecution,
    renderGoalTab,
    confirmGoal,
    normalizeGoalResponse,
    goalErrorMessage,
    withTimeout,
    openPrReviewById,
    backToPrReviewList,
    selectCloudFinding,
    selectedCloudCandidate,
    selectedCloudCase,
    cloudAllowedReviewActions,
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
  on("start-button", "click", startRun);
  on("auth-register-link", "click", () => openAuthModal("register"));
  on("auth-signin-link", "click", () => openAuthModal("signin"));
  on("accept-signin-link", "click", () => openAuthModal("signin"));
  on("signin-form", "submit", submitSignin);
  on("register-form", "submit", submitRegister);
  on("accept-invitation-form", "submit", submitAcceptInvitation);
  on("overview-view-button", "click", () => switchMode("overview"));
  on("settings-view-button", "click", () => switchMode("settings"));
  on("demo-readiness-view-button", "click", () => switchMode("demo-readiness"));
  on("demo-readiness-refresh-button", "click", loadDemoReadiness);
  on("demo-reset-button", "click", resetDemo);
  on("overview-launch-demo-button", "click", openDemoModal);
  on("overview-refresh-button", "click", refreshRun);
  on("overview-open-prs-button", "click", () => switchMode("simple"));
  on("back-pr-list-button", "click", backToPrReviewList);
  on("overview-open-approvals-button", "click", () => { switchMode("review-queue"); loadReviewQueue(); });
  on("overview-open-cloud-button", "click", () => switchMode("cloud-hunt"));
  on("refresh-button", "click", refreshPRReviews);
  on("case-refresh-button", "click", refreshRun);
  on("launch-demo-button", "click", openDemoModal);
  on("case-launch-demo-button", "click", openDemoModal);
  on("cancel-demo-button", "click", closeDemoModal);
  on("close-demo-button", "click", closeDemoModal);
  on("open-approvals-button", "click", () => switchMode("review-queue"));
  on("technical-open-approvals-button", "click", () => switchMode("review-queue"));
  on("pause-button", "click", () => { state.paused = !state.paused; $("pause-button").textContent = state.paused ? "Resume" : "Pause"; });
  on("skip-animation", "change", (event) => { state.skipAnimation = event.target.checked; if (state.run && state.skipAnimation) startAnimation(true); });
  on("simple-view-button", "click", () => switchView(false));
  on("goals-view-button", "click", openGoalsHome);
  on("cloud-hunt-view-button", "click", () => switchMode("cloud-hunt"));
  on("review-queue-view-button", "click", () => { switchMode("review-queue"); loadReviewQueue(); });
  on("technical-view-button", "click", () => switchView(true));
  on("activity-view-button", "click", () => { switchMode("activity"); loadActivity(); });
  on("activity-refresh-button", "click", loadActivity);
  document.querySelectorAll("[data-activity-category]").forEach((filter) => filter.addEventListener("click", () => { state.activity.filters.category = filter.dataset.activityCategory || ""; state.activity.page = 1; loadActivity(); }));
  on("activity-actor-type", "change", (event) => { state.activity.filters.actorType = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-result-filter", "change", (event) => { state.activity.filters.result = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-target-filter", "change", (event) => { state.activity.filters.targetType = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-sort-filter", "change", (event) => { state.activity.filters.sort = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-date-range", "change", (event) => { state.activity.filters.dateRange = event.target.value; $("activity-custom-dates").hidden = event.target.value !== "custom"; state.activity.page = 1; loadActivity(); });
  on("activity-created-from", "change", (event) => { state.activity.filters.createdFrom = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-created-to", "change", (event) => { state.activity.filters.createdTo = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-page-size", "change", (event) => { state.activity.pageSize = Number(event.target.value); state.activity.page = 1; loadActivity(); });
  on("activity-action-filter", "change", (event) => { state.activity.filters.action = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-search-input", "change", (event) => { state.activity.filters.search = event.target.value; state.activity.page = 1; loadActivity(); });
  on("activity-prev-button", "click", () => { state.activity.page = Math.max(1, state.activity.page - 1); loadActivity(); });
  on("activity-next-button", "click", () => { if (state.activity.hasNext) { state.activity.page += 1; loadActivity(); } });
  on("open-technical-button", "click", () => switchView(true));
  document.querySelectorAll("[data-review-action]").forEach((button) => button.addEventListener("click", () => selectReviewAction(button.dataset.reviewAction)));
  on("submit-review-button", "click", submitSelectedReview);
  on("cancel-review-button", "click", closeReviewForm);
  on("start-cloud-hunt-button", "click", startCloudHunt);
  on("goal-start-button", "click", startGoal);
  on("goal-confirm-button", "click", confirmGoal);
  on("goal-clarification-continue-button", "click", () => continueGoalClarifications().catch((error) => setMessage("goal-message", goalErrorMessage(error))));
  on("goal-clarification-recommended-button", "click", () => { document.querySelectorAll("#goal-clarification-questions input[type=radio]:checked").forEach((input) => input.dispatchEvent(new Event("change"))); });
  on("goal-clarification-edit-button", "click", () => { $("goal-clarification-panel").hidden = true; $("goal-create-panel").hidden = false; });
  on("goal-clarification-cancel-button", "click", () => { $("goal-clarification-panel").hidden = true; $("goal-create-panel").hidden = false; state.goalClarification = null; });
  on("goal-retry-button", "click", retryGoalAction);
  on("goal-edit-button", "click", editGoalDraft);
  on("goal-back-list-button", "click", () => { stopGoalPolling(); state.selectedGoal = null; state.goalEvents = []; state.goalCreationStage = "idle"; renderAll(); });
  on("goal-workspace-back-button", "click", () => { stopGoalPolling(); state.selectedGoal = null; state.goalEvents = []; state.goalCreationStage = "idle"; renderAll(); });
  on("goal-refresh-button", "click", refreshGoalJourney);
  on("goal-cancel-button", "click", cancelSelectedGoal);
  on("goal-retry-evidence-button", "click", retrySelectedGoalEvidence);
  on("goal-skip-button", "click", () => { state.goalReplayPaused = false; renderGoalExecution(); });
  on("goal-pause-button", "click", () => { state.goalReplayPaused = !state.goalReplayPaused; $("goal-pause-button").textContent = state.goalReplayPaused ? "Resume Replay" : "Pause Replay"; });
  document.querySelectorAll("[data-goal-tab]").forEach((button) => button.addEventListener("click", () => { state.goalTab = button.dataset.goalTab || "outcome"; renderGoalExecution(); }));
  on("cloud-new-run-button", "click", () => { state.selectedCloudHuntId = null; state.hunt = null; renderCloudRunHistory(); renderCloudHunt(); $("cloud-hunt-start-panel")?.scrollIntoView({ block: "start" }); });
  on("cloud-run-back-button", "click", backToCloudRunHistory);
  on("cloud-run-status-filter", "change", (event) => { state.cloudHuntFilters.status = event.target.value; state.cloudHuntPage = 1; loadCloudHunts(); });
  on("cloud-run-provider-filter", "change", (event) => { state.cloudHuntFilters.provider = event.target.value; state.cloudHuntPage = 1; loadCloudHunts(); });
  on("cloud-run-sort-filter", "change", (event) => { state.cloudHuntFilters.sort = event.target.value; state.cloudHuntPage = 1; loadCloudHunts(); });
  on("cloud-run-search-input", "change", (event) => { state.cloudHuntFilters.search = event.target.value; state.cloudHuntPage = 1; loadCloudHunts(); });
  on("cloud-run-page-size", "change", (event) => { state.cloudHuntPageSize = Number(event.target.value); state.cloudHuntPage = 1; loadCloudHunts(); });
  on("cloud-run-prev-button", "click", () => { state.cloudHuntPage = Math.max(1, state.cloudHuntPage - 1); loadCloudHunts(); });
  on("cloud-run-next-button", "click", () => { if (!$("cloud-run-next-button").disabled) { state.cloudHuntPage += 1; loadCloudHunts(); } });
  on("refresh-review-queue-button", "click", loadReviewQueue);
  on("refresh-members-button", "click", loadMembers);
  on("aws-save-button", "click", saveAWSConfig);
  on("aws-connect-button", "click", connectAWSAccount);
  on("aws-validate-button", "click", validateAWSConnection);
  on("github-save-button", "click", saveGitHubConfig);
  on("github-validate-button", "click", validateGitHubConnection);
  bindGitHubConnectButton();
  on("github-manage-repositories-button", "click", manageGitHubRepositories);
  on("github-disconnect-button", "click", disconnectGitHub);
  on("jira-save-button", "click", saveJiraConfig);
  on("jira-validate-button", "click", validateJiraConnection);
  on("schedule-create-button", "click", createCloudSchedule);
  on("workspace-save-button", "click", saveWorkspaceSettings);
  on("outcome-start-button", "click", startOutcomeVerification);
  on("outcome-deploy-button", "click", confirmOutcomeDeployment);
  on("outcome-refresh-button", "click", refreshOutcomeEvidence);
  on("collect-github-context-button", "click", collectGitHubContext);
  on("invite-member-button", "click", openInviteModal);
  on("invite-close-button", "click", closeInviteModal);
  on("invite-cancel-button", "click", closeInviteModal);
  on("send-invite-button", "click", submitInvite);
  on("cloud-back-button", "click", backFromCloudFinding);
  on("cloud-finding-detail", "click", (event) => {
    if (event.target.id === "cloud-finding-detail") backFromCloudFinding();
  });
  on("cloud-open-approval-button", "click", () => {
    state.selectedReviewContext = { ...state.selectedReviewContext, source: "approvals" };
    renderCloudHunt();
    $("cloud-human-decision").scrollIntoView({ block: "start" });
  });
  document.querySelectorAll("[data-cloud-review-action]").forEach((button) => button.addEventListener("click", () => selectCloudReviewAction(button.dataset.cloudReviewAction)));
  on("cloud-submit-review-button", "click", submitSelectedCloudReview);
  on("cloud-cancel-review-button", "click", closeCloudReviewForm);
  on("ask-case-button", "click", () => openAssistant("pr_review"));
  on("ask-cloud-button", "click", () => openAssistant("cloud_hunt"));
  on("ask-approvals-button", "click", () => openAssistant("approvals"));
  on("ask-technical-button", "click", () => openAssistant("technical_audit"));
  on("ask-global-button", "click", () => openAssistant("product_help"));
  on("notification-button", "click", () => showToast("No new notifications", "This workspace has no notification feed configured.", "success"));
  on("sign-out-button", "click", async () => {
    await api("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => ({}));
    state.currentUser = null;
    state.run = null;
    state.reviews = [];
    state.prReviews = [];
    state.hunt = null;
    localStorage.removeItem("ghostbusters:lastRunId");
    openAuthModal("signin");
    setMessage("auth-message", "Signed out.", true);
    window.setTimeout(() => setMessage("auth-message", ""), 5000);
  });
  on("assistant-close-button", "click", closeAssistant);
  on("assistant-clear-button", "click", () => { $("assistant-question-input").value = ""; clear($("assistant-answer")); setMessage("assistant-message", ""); });
  on("assistant-ask-button", "click", askAssistant);
  on("assistant-question-input", "keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) askAssistant();
    if (event.key === "Escape") closeAssistant();
  });
  if (typeof document.addEventListener === "function") {
    document.addEventListener("keydown", (event) => {
      const cloudFindingDetail = $("cloud-finding-detail");
      if (event.key === "Escape" && cloudFindingDetail && !cloudFindingDetail.hidden) backFromCloudFinding();
    });
  }
  on("assistant-backdrop", "click", (event) => { if (event.target.id === "assistant-backdrop") closeAssistant(); });
  on("pr-notice-refresh-button", "click", () => { state.newPrReviewCount = 0; loadPRReviews({ preserveSelection: true }); });
  on("pr-retry-button", "click", () => loadPRReviews({ preserveSelection: true }));
  on("pr-auxiliary-retry-button", "click", loadReviewQueue);
  on("pr-search-input", "input", (event) => {
    state.prReviewFilters.search = event.target.value;
    state.prReviewFilters.page = 1;
    window.clearTimeout(state.prSearchTimer);
    state.prSearchTimer = window.setTimeout(() => state.prReviewsServerPaged ? loadPRReviews({ preserveSelection: true }) : renderPRReviewList(), 180);
  });
  [
    ["pr-repository-filter", "repository"],
    ["pr-status-filter", "status"],
    ["pr-recommendation-filter", "recommendation"],
    ["pr-reviewer-filter", "reviewer"],
    ["pr-date-filter", "dateRange"],
    ["pr-sort-select", "sort"],
    ["pr-page-size-select", "pageSize"],
  ].forEach(([id, key]) => {
    on(id, "change", (event) => {
      state.prReviewFilters[key] = event.target.value;
      state.prReviewFilters.page = 1;
      if (state.prReviewsServerPaged) loadPRReviews({ preserveSelection: true });
      else renderPRReviewList();
    });
  });
  on("pr-prev-page-button", "click", () => {
    state.prReviewFilters.page = Math.max(1, state.prReviewFilters.page - 1);
    if (state.prReviewsServerPaged) loadPRReviews({ preserveSelection: true });
    else renderPRReviewList();
  });
  on("pr-next-page-button", "click", () => {
    state.prReviewFilters.page += 1;
    if (state.prReviewsServerPaged) loadPRReviews({ preserveSelection: true });
    else renderPRReviewList();
  });
  document.querySelectorAll("[data-pr-filter]").forEach((filter) => filter.addEventListener("click", () => {
    state.prReviewFilters.group = filter.dataset.prFilter || "needs-attention";
    state.prReviewFilters.page = 1;
    if (state.prReviewsServerPaged) loadPRReviews({ preserveSelection: true });
    else renderPRReviewList();
  }));
  document.querySelectorAll("[data-hunt-filter]").forEach((filter) => filter.addEventListener("click", () => {
    state.cloudHuntFilter = filter.dataset.huntFilter || "all";
    renderCloudHunt();
  }));
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
  portalCloudFindingDialog();
  bindEvents();
  loadInitial();
}
