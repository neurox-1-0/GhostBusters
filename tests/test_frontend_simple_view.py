from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def render_frontend(payload: dict[str, object]) -> dict[str, object]:
    script_path = Path("static/app.js")
    node_script = f"""
const fs = require("fs");
const vm = require("vm");

function createNode(tag = "div", id = "") {{
  const node = {{
    id,
    tagName: tag.toUpperCase(),
    children: [],
    hidden: false,
    value: "",
    checked: false,
    style: {{}},
    dataset: {{}},
    textContent: "",
    innerHTML: "",
    href: "",
    target: "",
    rel: "",
    open: false,
    className: "",
    appendChild(child) {{ child.parentNode = this; this.children.push(child); return child; }},
    removeChild(child) {{ this.children = this.children.filter((item) => item !== child); child.parentNode = null; }},
    get firstChild() {{ return this.children[0] || null; }},
    addEventListener() {{}},
    setAttribute(name, value) {{ this[name] = value; }},
    scrollIntoView() {{}},
    querySelectorAll() {{ return []; }},
    classList: {{
      toggle(name, force) {{
        const classes = new Set((node.className || "").split(/\\s+/).filter(Boolean));
        const shouldAdd = force === undefined ? !classes.has(name) : Boolean(force);
        if (shouldAdd) classes.add(name); else classes.delete(name);
        node.className = [...classes].join(" ");
      }},
      add(name) {{
        const classes = new Set((node.className || "").split(/\\s+/).filter(Boolean));
        classes.add(name);
        node.className = [...classes].join(" ");
      }},
      remove(name) {{
        const classes = new Set((node.className || "").split(/\\s+/).filter(Boolean));
        classes.delete(name);
        node.className = [...classes].join(" ");
      }},
    }},
  }};
  return node;
}}

const elements = new Map();
const reviewButtons = ["approve", "modify", "request_evidence", "add_context", "reject"].map((action) => {{
  const button = createNode("button");
  button.dataset.reviewAction = action;
  button.className = {{
    approve: "button-primary",
    modify: "button-secondary",
    request_evidence: "button-warning",
    add_context: "button-secondary",
    reject: "button-danger",
  }}[action];
  return button;
}});
const cloudReviewButtons = ["approve", "request_evidence", "add_context", "reject"].map((action) => {{
  const button = createNode("button");
  button.dataset.cloudReviewAction = action;
  button.className = {{
    approve: "button-primary",
    request_evidence: "button-warning",
    add_context: "button-secondary",
    reject: "button-danger",
  }}[action];
  return button;
}});
const filterButtons = ["all", "high-confidence", "protected", "needs-context", "awaiting-review"].map((filter) => {{
  const button = createNode("button");
  button.dataset.huntFilter = filter;
  button.className = filter === "all" ? "filter-chip filter-chip-active" : "filter-chip";
  button.setAttribute("aria-pressed", String(filter === "all"));
  return button;
}});
const prFilterButtons = ["needs-attention", "all", "in-progress", "completed", "blocked"].map((filter) => {{
  const button = createNode("button");
  button.dataset.prFilter = filter;
  button.className = filter === "needs-attention" ? "filter-chip filter-chip-active" : "filter-chip";
  button.setAttribute("aria-pressed", String(filter === "needs-attention"));
  return button;
}});

const document = {{
  getElementById(id) {{
    if (!elements.has(id)) elements.set(id, createNode("div", id));
    return elements.get(id);
  }},
  createElement(tag) {{
    return createNode(tag);
  }},
  querySelectorAll(selector) {{
    if (selector === "[data-review-action]") return reviewButtons;
    if (selector === "[data-cloud-review-action]") return cloudReviewButtons;
    if (selector === "[data-hunt-filter]") return filterButtons;
    if (selector === "[data-pr-filter]") return prFilterButtons;
    return [];
  }},
}};

const storage = {{
  values: new Map(),
  getItem(key) {{ return this.values.has(key) ? this.values.get(key) : null; }},
  setItem(key, value) {{ this.values.set(key, String(value)); }},
  removeItem(key) {{ this.values.delete(key); }},
}};

const fetch = async (path) => {{
  const routes = {{
    "/health": {{ status: "ok" }},
    "/api/scenarios": {{ scenarios: ["safe"] }},
    "/api/reviews": {json.dumps(payload.get("api_reviews", []))},
    "/api/runs": {json.dumps(payload.get("api_runs", []))},
  }};
  return {{
    ok: true,
    json: async () => routes[path] || {{}},
    status: 200,
    statusText: "OK",
  }};
}};

const context = {{
  console,
  fetch,
  document,
  localStorage: storage,
  sessionStorage: storage,
  URL,
  window: {{
    location: {{ href: "http://localhost/", replace() {{}} }},
    setInterval() {{ return 1; }},
    clearInterval() {{}},
    setTimeout(callback) {{ callback(); return 1; }},
    scrollTo() {{}},
    scrollY: 0,
  }},
}};
context.window.document = document;
context.document = document;
context.globalThis = context;

const source = fs.readFileSync("{script_path.as_posix()}", "utf8");

function nodeText(node) {{
  if (!node) return "";
  const own = node.textContent || "";
  const childText = (node.children || []).map((child) => nodeText(child)).join(" ");
  return `${{own}} ${{childText}}`.trim();
}}

function collectNodes(node, predicate, output = []) {{
  if (!node) return output;
  if (predicate(node)) output.push(node);
  (node.children || []).forEach((child) => collectNodes(child, predicate, output));
  return output;
}}

(async () => {{
  vm.runInNewContext(source, context);
  await Promise.resolve();
  await Promise.resolve();
  const hooks = context.window.__ghostbustersTestHooks;
  hooks.state.run = {json.dumps(payload["run"])};
  hooks.state.visibleEvents = hooks.state.run ? (hooks.state.run.audit_events || []) : [];
  hooks.state.reviews = {json.dumps(payload.get("reviews", []))};
  hooks.state.prReviews = {json.dumps(payload.get("pr_reviews", []))};
  hooks.state.knownPrReviewIds = new Set({json.dumps(payload.get("known_pr_review_ids", []))});
  hooks.state.hunt = {json.dumps(payload.get("hunt"))};
  hooks.state.loading = {json.dumps(payload.get("loading", {
      "initial": False,
      "reviews": False,
      "cloudHunt": False,
      "run": False,
      "review": False,
      "assistant": False,
      "prReviews": False,
  }))};
  hooks.state.prReviewFilters = {{ ...hooks.state.prReviewFilters, ...{json.dumps(payload.get("pr_filters", {}))} }};
  hooks.state.prReviewError = {json.dumps(payload.get("pr_review_error", ""))};
  hooks.state.cloudHuntFilter = {json.dumps(payload.get("cloud_filter", "all"))};
  if ({json.dumps(payload.get("open_demo", False))}) hooks.openDemoModal();
  if ({json.dumps(payload.get("mode"))}) hooks.switchMode({json.dumps(payload.get("mode"))});
  hooks.renderAll();
  if ({json.dumps(payload.get("select_cloud_candidate_id"))}) {{
    const candidate = (hooks.state.hunt?.candidates || []).find((item) => item.candidate_id === {json.dumps(payload.get("select_cloud_candidate_id"))});
    if (candidate) hooks.selectCloudFinding(candidate, {json.dumps(payload.get("select_cloud_source", "cloud-hunt"))});
  }}
  if ({json.dumps(payload.get("select_cloud_case_id"))}) {{
    const reviewCase = (hooks.state.reviews || []).find((item) => item.id === {json.dumps(payload.get("select_cloud_case_id"))});
    if (reviewCase) hooks.selectCloudFinding(reviewCase.candidate, {json.dumps(payload.get("select_cloud_source", "approvals"))}, reviewCase);
  }}
  if ({json.dumps(payload.get("call_load_review_queue", False))}) {{
    await hooks.loadReviewQueue();
  }}
  if ({json.dumps(payload.get("call_load_pr_reviews", False))}) {{
    await hooks.loadPRReviews({{ preserveSelection: true, showNotice: {json.dumps(payload.get("show_pr_notice", False))} }});
  }}
  if ({json.dumps(payload.get("select_pr_run_id"))}) {{
    await hooks.openPrReviewById({json.dumps(payload.get("select_pr_run_id"))});
  }}
  if ({json.dumps(payload.get("back_to_pr_list", False))}) {{
    hooks.backToPrReviewList();
  }}

  const ids = [
    "source-kind", "source-repository", "source-pr", "source-title", "source-head", "source-base",
    "source-integration", "change-resource", "change-before", "change-after", "change-file",
    "change-cost-impact", "recommendation-title", "recommendation-policy", "recommendation-savings",
    "recommendation-annual-savings", "result-title", "result-view", "safety-summary",
    "trigger-source", "run-pill", "approval-pill", "evidence-count", "candidate-count",
    "pr-empty-state", "case-view", "demo-modal-backdrop", "technical-content", "technical-empty-state",
    "pr-review-list", "pr-pagination-summary", "pr-new-review-notice", "pr-new-review-text",
    "pr-timezone-note", "pr-review-error", "pr-filter-count-all", "pr-filter-count-needs-attention",
    "pr-filter-count-in-progress", "pr-filter-count-completed", "pr-filter-count-blocked",
    "case-status", "human-decision", "human-decision-technical", "human-decision-summary", "recommendation-summary", "evidence-source-card",
    "case-received-time", "case-updated-time", "case-recommendation-time", "case-decision-time", "case-result-time",
    "page-title", "overview-summary", "overview-pr-list", "overview-savings-list",
    "overview-repositories-list", "overview-repository-count", "setup-progress-list",
    "setup-progress-percent", "setup-progress-bar", "overview-approval-alerts",
    "overview-activity-list", "cloud-journey-list", "cloud-journey-state", "toast-region",
    "filter-count-all", "filter-count-high-confidence", "filter-count-protected",
    "filter-count-needs-context", "filter-count-awaiting-review",
    "cloud-finding-detail", "cloud-finding-path", "cloud-finding-title", "cloud-finding-context",
    "cloud-detail-provider", "cloud-detail-resource", "cloud-detail-type", "cloud-detail-environment",
    "cloud-detail-cost", "cloud-detail-savings", "cloud-detail-confidence", "cloud-detail-review-state",
    "cloud-detail-owner", "cloud-detail-project", "cloud-detail-dependencies", "cloud-detail-terraform",
    "cloud-detail-classification", "cloud-detail-recommendation", "cloud-detail-policy",
    "cloud-detail-human-required", "cloud-detail-classification-inline", "cloud-detail-flagged", "cloud-detail-caution",
    "cloud-human-title", "cloud-human-status", "cloud-human-technical", "cloud-human-guidance", "cloud-safety-notice",
    "cloud-technical-details", "cloud-detail-policy-state", "cloud-detail-review-id",
    "cloud-detail-run-id", "cloud-detail-provider-id", "cloud-detail-audit-ref",
    "cloud-back-button", "cloud-open-approval-button",
  ];
  const output = {{}};
  for (const id of ids) {{
    const node = elements.get(id) || createNode("div", id);
      output[id] = {{
        text: node.textContent,
        hidden: node.hidden,
        open: node.open,
        className: node.className,
        value: node.value,
        children: node.children.map((child) => nodeText(child) || child.href || child.className || ""),
        href: node.href,
      }};
    }}
    output.reviewButtons = reviewButtons.map((button) => ({{
      action: button.dataset.reviewAction,
      hidden: button.hidden,
      disabled: button.disabled,
      className: button.className,
    }}));
    output.cloudReviewButtons = cloudReviewButtons.map((button) => ({{
      action: button.dataset.cloudReviewAction,
      hidden: button.hidden,
      disabled: button.disabled,
      className: button.className,
    }}));
    output.selectedReviewContext = hooks.state.selectedReviewContext;
    output.queueCards = (elements.get("review-queue-list")?.children || []).map((child) => nodeText(child));
    output.cloudCards = (elements.get("candidate-list")?.children || []).map((child) => nodeText(child));
    output.cloudCardTags = collectNodes(elements.get("candidate-list"), (child) => (child.className || "").includes("status-badge")).map((child) => ({{ text: nodeText(child), className: child.className, tagName: child.tagName }}));
    output.cloudTables = collectNodes(elements.get("candidate-list"), (child) => child.tagName === "TABLE").map((child) => nodeText(child));
    output.queueTables = collectNodes(elements.get("review-queue-list"), (child) => child.tagName === "TABLE").map((child) => nodeText(child));
    output.filterChips = filterButtons.map((button) => ({{
      filter: button.dataset.huntFilter,
      tagName: button.tagName,
      className: button.className,
      ariaPressed: button["aria-pressed"],
    }}));
    output.prFilterChips = prFilterButtons.map((button) => ({{
      filter: button.dataset.prFilter,
      tagName: button.tagName,
      className: button.className,
      ariaPressed: button["aria-pressed"],
    }}));
    output.prTables = collectNodes(elements.get("pr-review-list"), (child) => child.tagName === "TABLE").map((child) => nodeText(child));
    output.prRows = (elements.get("pr-review-list")?.children || []).map((child) => nodeText(child));
    output.summaryCards = (elements.get("overview-summary")?.children || []).map((child) => nodeText(child) || child.className);
    output.overviewRows = (elements.get("overview-pr-list")?.children || []).map((child) => nodeText(child) || child.className);
    output.overviewSavings = (elements.get("overview-savings-list")?.children || []).map((child) => nodeText(child) || child.className);
    output.overviewRepos = (elements.get("overview-repositories-list")?.children || []).map((child) => nodeText(child) || child.className);
    output.overviewAlerts = (elements.get("overview-approval-alerts")?.children || []).map((child) => nodeText(child) || child.className);
    output.overviewActivity = (elements.get("overview-activity-list")?.children || []).map((child) => nodeText(child) || child.className);
    output.setupSteps = (elements.get("setup-progress-list")?.children || []).map((child) => ({{ text: nodeText(child), className: child.className }}));
    output.cloudJourney = (elements.get("cloud-journey-list")?.children || []).map((child) => ({{ text: nodeText(child), className: child.className }}));
    output.sourceLink = {{
      hidden: elements.get("source-pr-link")?.hidden ?? true,
      href: elements.get("source-pr-link")?.href || "",
    }};
  console.log(JSON.stringify(output));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""
    result = subprocess.run(
        ["node", "-"],
        input=node_script,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def sample_run(real_pr: bool = False, demo: bool = False) -> dict[str, object]:
    run = {
        "id": "11111111-1111-1111-1111-111111111111",
        "goal": "Reduce unnecessary cloud cost safely.",
        "scenario_name": "safe",
        "status": "pr_created" if real_pr else "pending_human_review",
        "created_at": "2026-07-26T00:00:00Z",
        "updated_at": "2026-07-26T00:05:00Z",
        "source_type": "manual_demo" if demo else "terraform_pr",
        "version": 1,
        "idempotency_key": "ui-test",
        "audit_events": [
            {"sequence_number": 1, "timestamp": "2026-07-26T00:00:00Z", "event_type": "run_created", "actor": "system", "summary": "Case opened", "details": {}},
            {"sequence_number": 2, "timestamp": "2026-07-26T00:00:10Z", "event_type": "terraform_parsed", "actor": "system", "summary": "Terraform diff parsed", "details": {}},
            {"sequence_number": 3, "timestamp": "2026-07-26T00:00:20Z", "event_type": "recommendation_produced", "actor": "agent", "summary": "Recommendation recorded", "details": {}},
        ],
        "human_reviews": [],
        "decision_record": {
            "goal": "Reduce unnecessary cloud cost safely.",
            "resource_id": "aws_instance.app",
            "preferred_action": "downsize",
            "confidence": {
                "evidence_completeness": 1.0,
                "evidence_reliability": 1.0,
                "evidence_freshness": 1.0,
                "conflict_penalty": 0.0,
                "policy_certainty": 1.0,
                "final_confidence": 0.91,
                "explanation": [],
            },
            "investigation_plan": {
                "goal": "Reduce unnecessary cloud cost safely.",
                "resource_id": "aws_instance.app",
                "questions": [],
                "selected_tools": ["pricing", "utilization", "dependencies"],
                "skipped_tools": [],
                "planning_notes": [],
            },
            "tool_executions": [],
            "evidence": [
                {
                    "source": "pricing",
                    "tool_name": "pricing",
                    "claim": "Pricing data was collected.",
                    "value": {"current_monthly_cost": 70, "proposed_monthly_cost": 140, "source": "test-pricing", "region": "us-east-1", "resource_type": "aws_instance", "pricing_model": "on_demand", "currency": "USD", "checked_at": "2026-07-26T00:00:20Z", "assumptions": ["test fixture"]},
                    "resource_id": "aws_instance.app",
                    "collected_at": "2026-07-26T00:00:20Z",
                    "freshness_status": "fresh",
                    "reliability": 1.0,
                    "metadata": {},
                    "source_mode": "live",
                },
                {
                    "source": "utilization",
                    "tool_name": "utilization",
                    "claim": "Utilization is low.",
                    "value": {"average_cpu_pct": 18, "peak_cpu_pct": 31},
                    "resource_id": "aws_instance.app",
                    "collected_at": "2026-07-26T00:00:21Z",
                    "freshness_status": "fresh",
                    "reliability": 1.0,
                    "metadata": {},
                },
                {
                    "source": "dependencies",
                    "tool_name": "dependencies",
                    "claim": "No active dependencies found.",
                    "value": {"active_downstream_dependencies": []},
                    "resource_id": "aws_instance.app",
                    "collected_at": "2026-07-26T00:00:22Z",
                    "freshness_status": "fresh",
                    "reliability": 1.0,
                    "metadata": {},
                },
            ],
            "conflicts": [],
            "missing_evidence": [],
            "alternatives": [
                {
                    "action": "downsize",
                    "description": "Downsize to m5.large",
                    "proposed_instance_type": "m5.large",
                    "estimated_monthly_cost": 70.0,
                    "estimated_monthly_savings": 70.0,
                    "estimated_annual_savings": 840.0,
                    "supporting_evidence": [],
                    "risks": [],
                    "assumptions": [],
                    "eligible": True,
                    "rejection_reasons": [],
                    "score": 0.98,
                }
            ],
            "verifier_findings": [
                {"check_name": "safety", "status": "passed", "severity": "low", "explanation": "Safe update", "evidence_sources": ["pricing"]},
            ],
            "policy_result": {
                "allowed": True,
                "status": "passed",
                "blocking_reasons": [],
                "warnings": [],
                "evaluated_rules": [],
                "requires_human_approval": True,
                "engine": "python_fallback",
                "policy_version": "1.0",
                "violations": [],
                "fallback_reason": None,
            },
            "final_status": "recommendation_ready",
            "final_summary": "Downsize to m5.large",
            "planning_mode": "deterministic_only",
            "objective_interpretation": None,
            "ai_decisions": [],
            "unresolved_questions": [],
            "human_question": None,
            "termination_reason": None,
        },
        "github_source": None if demo else {
            "repository": "demo/infra",
            "pull_request_number": 42,
            "pull_request_url": "https://github.test/demo/infra/pull/42",
            "pull_request_title": "Resize app",
            "author": "dev",
            "base_branch": "main",
            "base_sha": "base",
            "head_branch": "demo/real-remediation-test",
            "head_sha": "head",
            "changed_files": ["staging/main.tf"],
            "terraform_files": ["staging/main.tf"],
            "resource_changes": [
                {
                    "address": "aws_instance.app",
                    "provider": "aws",
                    "resource_type": "aws_instance",
                    "resource_name": "app",
                    "actions": ["update"],
                    "before": {"instance_type": "m5.large"},
                    "after": {"instance_type": "m5.xlarge"},
                    "changed_attributes": ["instance_type"],
                    "destructive": False,
                    "replacement": False,
                    "source_file": "staging/main.tf",
                }
            ],
            "provider": "aws",
            "environment": "staging",
            "parse_mode": "github_diff",
            "warnings": [],
            "unsupported_changes": [],
        },
        "mock_pr": None if real_pr else {
            "pr_number": 88,
            "repository": "demo/infra",
            "branch": "ghostbusters/remediation/pr-42-app",
            "base_branch": "demo/real-remediation-test",
            "title": "GhostBusters: Right-size app",
            "body": "Simulated remediation",
            "created_at": "2026-07-26T00:06:00Z",
            "status": "open",
            "resource_id": "aws_instance.app",
            "chosen_action": "downsize",
            "current_instance_type": "m5.xlarge",
            "proposed_instance_type": "m5.large",
            "terraform_patch_preview": '- instance_type = "m5.xlarge"\\n+ instance_type = "m5.large"',
            "monthly_savings": 70,
            "annual_savings": 840,
            "confidence": 0.91,
            "policy_summary": "Allowed with safety conditions",
            "evidence_summary": [],
            "human_approval_summary": "Awaiting approval",
        },
        "real_pr": None if not real_pr else {
            "repository": "demo/infra",
            "number": 77,
            "url": "https://github.test/demo/infra/pull/77",
            "branch": "ghostbusters/remediation/pr-42-app",
            "base_branch": "demo/real-remediation-test",
            "title": "GhostBusters: Right-size app",
            "created_at": "2026-07-26T00:06:00Z",
            "idempotency_key": "approval-42",
            "status": "open",
            "reused": False,
        },
        "error": None,
    }
    return run


def sample_cloud_candidate(
    candidate_id: str = "ghost-1",
    protected: bool = False,
    terraform: bool = True,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "resource": {
            "provider": "aws",
            "account_or_subscription_id": "123",
            "region_or_location": "us-east-1",
            "resource_id": "i-forgotten-test",
            "resource_name": "forgotten-test",
            "provider_resource_type": "ec2",
            "normalized_resource_type": "virtual_machine",
            "status": "running",
            "environment": "staging",
            "owner": "payments-team",
            "project": "migration-cleanup",
            "created_at": None,
            "age_days": 120,
            "tags": {},
            "infrastructure_as_code_managed": terraform,
            "terraform_address": "aws_instance.forgotten" if terraform else None,
            "estimated_monthly_cost": 120.0,
            "metadata": {},
        },
        "candidate_score": 0.95,
        "suspicion_level": "high",
        "signals": [
            {"signal_type": "low_utilization", "description": "CPU stayed below 5%.", "value": 0.05, "weight": 0.7, "supports_ghost_hypothesis": True, "evidence_source": "utilization"},
            {"signal_type": "old_resource", "description": "Resource is older than 90 days.", "value": 120, "weight": 0.4, "supports_ghost_hypothesis": True, "evidence_source": "inventory"},
            {"signal_type": "active_dependency" if protected else "dependency_check", "description": "One dependency still references this VM." if protected else "No active dependency was found.", "value": 1 if protected else 0, "weight": 0.4, "supports_ghost_hypothesis": False, "evidence_source": "dependencies"},
        ],
        "requires_investigation": True,
        "exclusion_reason": "active_dependency" if protected else None,
    }


def sample_cloud_hunt(candidate: dict[str, object] | None = None) -> dict[str, object]:
    candidate = candidate or sample_cloud_candidate()
    return {
        "id": "33333333-3333-3333-3333-333333333333",
        "trigger_source": "manual_cloud_hunt",
        "provider_scope": "multi_cloud",
        "inventory_source": "fixtures",
        "goal": "Find forgotten cloud resources",
        "started_at": "2026-07-26T00:00:00Z",
        "completed_at": "2026-07-26T00:03:00Z",
        "status": "completed",
        "resources_scanned": 1,
        "candidates_found": 1,
        "investigations_created": 1,
        "protected_resources": 1 if candidate.get("exclusion_reason") else 0,
        "errors": [],
        "planning_mode": "deterministic_only",
        "audit_events": [],
        "summary": {
            "total_resources": 1,
            "healthy_resources": 0,
            "candidates": 1,
            "high_confidence_candidates": 1,
            "protected_candidates": 1 if candidate.get("exclusion_reason") else 0,
            "needs_human_context": 0,
            "estimated_monthly_waste": 0.0 if candidate.get("exclusion_reason") else 120.0,
            "estimated_annual_waste": 0.0 if candidate.get("exclusion_reason") else 1440.0,
            "provider_breakdown": {},
        },
        "candidates": [candidate],
    }


def sample_cloud_review(
    candidate: dict[str, object] | None = None,
    status: str = "pending",
    policy_status: str = "passed",
) -> dict[str, object]:
    candidate = candidate or sample_cloud_candidate()
    resource = candidate["resource"]
    return {
        "id": "44444444-4444-4444-4444-444444444444",
        "source_type": "cloud_hunt",
        "source_reference": "33333333-3333-3333-3333-333333333333",
        "repository": None,
        "provider": resource["provider"],
        "resource_id": resource["resource_id"],
        "resource_name": resource["resource_name"],
        "recommendation": "stop_for_observation",
        "recommendation_reason": "CPU stayed below 5%. Resource is older than 90 days.",
        "confidence": candidate["candidate_score"],
        "risk_level": "medium",
        "estimated_monthly_savings": 120.0 if not candidate.get("exclusion_reason") else 0.0,
        "estimated_annual_savings": 1440.0 if not candidate.get("exclusion_reason") else 0.0,
        "policy_status": policy_status,
        "required_reviewer_role": "application_owner",
        "human_decision": None,
        "final_outcome": None,
        "created_at": "2026-07-26T00:00:00Z",
        "updated_at": "2026-07-26T00:05:00Z",
        "status": status,
        "candidate": candidate,
        "terraform_address": resource.get("terraform_address"),
        "simulated_pr": None,
        "audit_events": [],
    }


def pr_run(
    run_id: str,
    repository: str,
    pr_number: int,
    status: str = "pending_human_review",
    title: str = "Resize app",
    reviewer: str | None = None,
    savings: float = 70.0,
    updated_at: str = "2026-07-26T00:05:00Z",
) -> dict[str, object]:
    run = json.loads(json.dumps(sample_run()))
    run["id"] = run_id
    run["status"] = status
    run["created_at"] = "2026-07-26T00:00:00Z"
    run["updated_at"] = updated_at
    run["source_type"] = "terraform_pr"
    run["github_source"]["repository"] = repository
    run["github_source"]["pull_request_number"] = pr_number
    run["github_source"]["pull_request_title"] = title
    run["github_source"]["head_branch"] = f"feature/pr-{pr_number}"
    run["decision_record"]["alternatives"][0]["estimated_monthly_savings"] = savings
    run["decision_record"]["confidence"]["final_confidence"] = 0.7 + (min(savings, 100) / 500)
    run["mock_pr"]["monthly_savings"] = savings
    run["mock_pr"]["annual_savings"] = savings * 12
    run["pricing"] = {"available": True, "source": "scenario_fixture", "source_mode": "fixture"}
    if reviewer:
      run["human_reviews"] = [{"reviewer": reviewer, "action": "approve" if status in {"approved", "pr_created"} else "reject", "comment": None, "requested_sources": [], "modified_action": None, "human_context": None, "created_at": "2026-07-26T00:08:00Z"}]
    return run


def test_simple_view_renders_real_github_case_story_and_hides_invalid_actions() -> None:
    rendered = render_frontend({"run": sample_run(), "reviews": []})

    assert rendered["source-kind"]["text"] == "GitHub Pull Request"
    assert rendered["source-repository"]["text"] == "demo/infra"
    assert rendered["source-pr"]["text"] == "#42"
    assert rendered["source-title"]["text"] == "Resize app"
    assert rendered["source-head"]["text"] == "demo/real-remediation-test"
    assert rendered["source-base"]["text"] == "main"
    assert rendered["source-integration"]["text"] == "Real GitHub"
    assert rendered["change-resource"]["text"] == "aws_instance.app"
    assert rendered["change-before"]["text"] == "m5.large"
    assert rendered["change-after"]["text"] == "m5.xlarge"
    assert rendered["change-file"]["text"] == "staging/main.tf"
    assert rendered["change-cost-impact"]["text"] == "+$70/month"
    assert rendered["recommendation-title"]["text"] == "Downsize to m5.large"
    assert rendered["recommendation-policy"]["text"] == "Allowed with safety conditions"
    assert rendered["recommendation-savings"]["text"] == "$70/month"
    assert rendered["recommendation-annual-savings"]["text"] == "$840/year"
    assert rendered["evidence-count"]["text"] == "5 bullets"
    assert rendered["run-pill"]["text"] == "GitHub Integration: Real GitHub"
    assert rendered["case-status"]["text"] == "Awaiting Human Review"
    assert rendered["human-decision-summary"]["text"] == "Awaiting a reviewer"
    assert rendered["recommendation-summary"]["text"] == "Downsize to m5.large"
    assert rendered["sourceLink"]["hidden"] is False
    assert rendered["sourceLink"]["href"] == "https://github.test/demo/infra/pull/42"
    assert any(button["action"] == "add_context" and button["hidden"] for button in rendered["reviewButtons"])
    assert all("[object Object]" not in part for node in rendered.values() if isinstance(node, dict) for part in [node.get("text", ""), *node.get("children", [])])


def test_demo_and_result_states_are_clearly_labeled() -> None:
    demo_rendered = render_frontend({"run": sample_run(demo=True), "reviews": []})
    real_rendered = render_frontend({"run": sample_run(real_pr=True), "reviews": []})
    root = client.get("/").text

    assert demo_rendered["source-kind"]["text"] == "Controlled Demo"
    assert demo_rendered["source-integration"]["text"] == "Fixture-backed"
    assert demo_rendered["trigger-source"]["text"] == "Source: Controlled Demo"
    assert demo_rendered["approval-pill"]["text"] == "Demo Environment: Active"
    assert demo_rendered["evidence-source-card"]["hidden"] is False
    assert demo_rendered["result-title"]["text"] == "Awaiting Human Approval"
    assert "Approval creates a remediation pull request or approved remediation proposal only." in root
    assert "Open Technical Audit" in root

    assert real_rendered["result-title"]["text"] == "Real Remediation PR Created"
    assert any("Open in GitHub" in child for child in real_rendered["result-view"]["children"])
    assert real_rendered["source-integration"]["text"] == "Real GitHub"


def test_no_case_empty_states_and_demo_modal_are_separated_from_normal_review_flow() -> None:
    rendered = render_frontend({"run": None, "reviews": [], "hunt": None, "open_demo": True})
    root = client.get("/").text

    assert "Review objective" not in root
    assert "Prepared case" not in root
    assert rendered["pr-empty-state"]["hidden"] is False
    assert rendered["case-view"]["hidden"] is True
    assert "PR review history" in root
    assert "Needs Attention" in root
    assert any("No PR reviews yet" in row for row in rendered["prRows"])
    assert "Times shown in" in rendered["pr-timezone-note"]["text"]
    assert rendered["demo-modal-backdrop"]["hidden"] is False
    assert rendered["technical-content"]["hidden"] is True
    assert rendered["technical-empty-state"]["hidden"] is False
    assert "Demo scenario" in root
    assert "Demo objective" in root


def test_pr_reviews_list_shows_multiple_cases_with_readable_statuses_and_timestamps() -> None:
    runs = [
        pr_run("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "demo/api", 42, status="pending_human_review", savings=70),
        pr_run("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "demo/worker", 43, status="needs_more_evidence", title="Collect owner context", savings=25),
        pr_run("cccccccc-cccc-cccc-cccc-cccccccccccc", "demo/archive", 44, status="pr_created", reviewer="judge", savings=120),
    ]

    rendered = render_frontend({"run": None, "reviews": [], "pr_reviews": runs, "mode": "simple"})
    table_text = " ".join(rendered["prTables"])

    assert rendered["pr-empty-state"]["hidden"] is False
    assert rendered["case-view"]["hidden"] is True
    assert "demo/api" in table_text
    assert "demo/worker" in table_text
    assert "demo/archive" not in table_text
    assert "Awaiting Human Review" in table_text
    assert "More Evidence Required" in table_text
    assert "pending_human_review" not in table_text
    assert "needs_more_evidence" not in table_text
    assert "View Review" in table_text
    assert rendered["pr-filter-count-all"]["text"] == "3"
    assert rendered["pr-filter-count-needs-attention"]["text"] == "2"
    assert rendered["pr-filter-count-completed"]["text"] == "1"
    assert rendered["pr-pagination-summary"]["text"] == "Showing 1-2 of 2 reviews"


def test_pr_reviews_filters_search_sort_pagination_and_history_work() -> None:
    runs = [
        pr_run("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "demo/api", 42, status="pending_human_review", title="Resize api", savings=70, updated_at="2026-07-26T00:05:00Z"),
        pr_run("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "demo/worker", 43, status="blocked", title="Delete worker", savings=10, updated_at="2026-07-26T00:08:00Z"),
        pr_run("cccccccc-cccc-cccc-cccc-cccccccccccc", "demo/archive", 44, status="pr_created", reviewer="judge", title="Archive cleanup", savings=120, updated_at="2026-07-26T00:12:00Z"),
    ]

    all_rows = render_frontend({"run": None, "reviews": [], "pr_reviews": runs, "mode": "simple", "pr_filters": {"group": "all", "sort": "savings_desc", "pageSize": 2}})
    assert "demo/archive" in " ".join(all_rows["prTables"])
    assert all_rows["pr-pagination-summary"]["text"] == "Showing 1-2 of 3 reviews"

    searched = render_frontend({"run": None, "reviews": [], "pr_reviews": runs, "mode": "simple", "pr_filters": {"group": "all", "search": "worker"}})
    searched_text = " ".join(searched["prTables"])
    assert "demo/worker" in searched_text
    assert "demo/api" not in searched_text

    blocked = render_frontend({"run": None, "reviews": [], "pr_reviews": runs, "mode": "simple", "pr_filters": {"group": "blocked"}})
    assert "Policy Blocked" in " ".join(blocked["prTables"])
    assert blocked["pr-pagination-summary"]["text"] == "Showing 1-1 of 1 reviews"

    completed = render_frontend({"run": None, "reviews": [], "pr_reviews": runs, "mode": "simple", "pr_filters": {"group": "completed"}})
    assert "Remediation PR Created" in " ".join(completed["prTables"])
    assert "judge" in " ".join(completed["prTables"])


def test_pr_reviews_list_to_detail_back_and_new_review_notice_preserve_selection() -> None:
    first = pr_run("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "demo/api", 42)
    second = pr_run("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "demo/new", 45)

    selected = render_frontend({
        "run": None,
        "reviews": [],
        "pr_reviews": [first],
        "mode": "simple",
        "select_pr_run_id": first["id"],
    })

    assert selected["case-view"]["hidden"] is False
    assert selected["pr-empty-state"]["hidden"] is True
    assert selected["source-repository"]["text"] == "demo/api"
    assert selected["selectedReviewContext"]["source"] == "pr-reviews"
    assert "Received:" in selected["case-received-time"]["text"]
    assert "Last updated:" in selected["case-updated-time"]["text"]

    back = render_frontend({
        "run": first,
        "reviews": [],
        "pr_reviews": [first],
        "mode": "simple",
        "back_to_pr_list": True,
    })
    assert back["pr-empty-state"]["hidden"] is False
    assert back["case-view"]["hidden"] is True

    notice = render_frontend({
        "run": first,
        "reviews": [],
        "api_runs": [first, second],
        "known_pr_review_ids": [first["id"]],
        "mode": "simple",
        "call_load_pr_reviews": True,
        "show_pr_notice": True,
    })
    assert notice["case-view"]["hidden"] is False
    assert notice["source-repository"]["text"] == "demo/api"
    assert notice["pr-new-review-notice"]["hidden"] is False
    assert notice["pr-new-review-text"]["text"] == "1 new PR review available"


def test_pr_reviews_loading_and_error_states_render() -> None:
    loading = {
        "initial": False,
        "reviews": False,
        "prReviews": True,
        "cloudHunt": False,
        "run": False,
        "review": False,
        "assistant": False,
    }
    loading_view = render_frontend({"run": None, "reviews": [], "pr_reviews": [], "mode": "simple", "loading": loading})
    assert loading_view["prRows"]
    assert loading_view["pr-pagination-summary"]["text"] == "Loading reviews"

    error_view = render_frontend({"run": None, "reviews": [], "pr_reviews": [], "mode": "simple", "pr_review_error": "Failed to load PR reviews."})
    assert error_view["pr-review-error"]["hidden"] is False


def test_review_queue_and_cloud_hunt_views_remain_functional() -> None:
    reviews = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source_type": "terraform_pr",
            "source_reference": "https://github.test/demo/infra/pull/42",
            "repository": "demo/infra",
            "pull_request_number": 42,
            "head_branch": "demo/real-remediation-test",
            "base_branch": "main",
            "commit_sha": "head",
            "provider": None,
            "resource_id": "aws_instance.app",
            "resource_name": "aws_instance.app",
            "recommendation": "Downsize to m5.large",
            "recommendation_reason": "Rightsizing looks safe.",
            "confidence": 0.91,
            "risk_level": "low",
            "estimated_monthly_savings": 70.0,
            "estimated_annual_savings": 840.0,
            "policy_status": "passed",
            "required_reviewer_role": "application_owner",
            "human_decision": None,
            "final_outcome": None,
            "created_at": "2026-07-26T00:00:00Z",
            "updated_at": "2026-07-26T00:05:00Z",
            "waiver_expiry": None,
            "status": "pending",
            "candidate": None,
            "terraform_address": "aws_instance.app",
            "simulated_pr": None,
            "audit_events": [],
        }
    ]
    hunt = {
        "id": "33333333-3333-3333-3333-333333333333",
        "trigger_source": "manual_cloud_hunt",
        "provider_scope": "multi_cloud",
        "inventory_source": "fixtures",
        "goal": "Find forgotten cloud resources",
        "started_at": "2026-07-26T00:00:00Z",
        "completed_at": "2026-07-26T00:03:00Z",
        "status": "completed",
        "resources_scanned": 12,
        "candidates_found": 1,
        "investigations_created": 1,
        "protected_resources": 1,
        "errors": [],
        "planning_mode": "deterministic_only",
        "audit_events": [],
        "summary": {
            "total_resources": 12,
            "healthy_resources": 10,
            "candidates": 1,
            "high_confidence_candidates": 1,
            "protected_candidates": 1,
            "needs_human_context": 1,
            "estimated_monthly_waste": 180.0,
            "estimated_annual_waste": 2160.0,
            "provider_breakdown": {},
        },
        "candidates": [
            {
                "candidate_id": "ghost-1",
                "resource": {
                    "provider": "aws",
                    "account_or_subscription_id": "123",
                    "region_or_location": "us-east-1",
                    "resource_id": "i-123",
                    "resource_name": "unused-app",
                    "provider_resource_type": "ec2",
                    "normalized_resource_type": "virtual_machine",
                    "status": "running",
                    "environment": "staging",
                    "owner": None,
                    "project": None,
                    "created_at": None,
                    "age_days": 120,
                    "tags": {},
                    "infrastructure_as_code_managed": True,
                    "terraform_address": None,
                    "estimated_monthly_cost": 180.0,
                    "metadata": {},
                },
                "candidate_score": 0.91,
                "suspicion_level": "high",
                "signals": [
                    {"signal_type": "low_utilization", "description": "CPU stayed below 5%.", "value": 0.05, "weight": 0.7, "supports_ghost_hypothesis": True, "evidence_source": "utilization"},
                    {"signal_type": "active_dependency", "description": "One dependency still references this VM.", "value": 1, "weight": 0.4, "supports_ghost_hypothesis": False, "evidence_source": "dependencies"},
                ],
                "requires_investigation": True,
                "exclusion_reason": None,
            }
        ],
    }

    rendered = render_frontend({"run": sample_run(), "reviews": reviews, "hunt": hunt})

    assert rendered["candidate-count"]["text"] == "1 candidate"
    assert rendered["queueCards"]
    assert rendered["cloudCards"]
    assert rendered["queueTables"]
    assert rendered["cloudTables"]
    assert any("Review Decision" in card for card in rendered["queueCards"])


def test_review_queue_replaces_skeletons_after_async_load_finishes() -> None:
    api_reviews = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source_type": "terraform_pr",
            "repository": "demo/infra",
            "pull_request_number": 42,
            "resource_name": "aws_instance.app",
            "recommendation": "Downsize to m5.large",
            "recommendation_reason": "Rightsizing looks safe.",
            "confidence": 0.91,
            "estimated_monthly_savings": 70.0,
            "policy_status": "passed",
            "status": "pending_human_review",
        }
    ]

    rendered = render_frontend({
        "run": None,
        "reviews": [],
        "api_reviews": api_reviews,
        "mode": "review-queue",
        "call_load_review_queue": True,
    })

    assert rendered["queueCards"]
    assert any("demo/infra" in card for card in rendered["queueCards"])
    assert any("Review Decision" in card for card in rendered["queueCards"])
    assert all("skeleton" not in card for card in rendered["queueCards"])


def test_cloud_hunt_view_finding_opens_selected_detail_with_evidence_and_actions() -> None:
    candidate = sample_cloud_candidate()
    review = sample_cloud_review(candidate)
    rendered = render_frontend({
        "run": None,
        "reviews": [review],
        "hunt": sample_cloud_hunt(candidate),
        "mode": "cloud-hunt",
        "select_cloud_candidate_id": "ghost-1",
    })

    assert rendered["cloud-finding-detail"]["hidden"] is False
    assert rendered["cloud-finding-path"]["text"] == "Cloud Hunt -> forgotten-test"
    assert rendered["cloud-finding-title"]["text"] == "forgotten-test"
    assert rendered["cloud-detail-provider"]["text"] == "Aws"
    assert rendered["cloud-detail-resource"]["text"] == "forgotten-test"
    assert rendered["cloud-detail-type"]["text"] == "Virtual Machine"
    assert rendered["cloud-detail-environment"]["text"] == "staging"
    assert rendered["cloud-detail-cost"]["text"] == "$120"
    assert rendered["cloud-detail-savings"]["text"] == "$120/month"
    assert rendered["cloud-detail-confidence"]["text"] == "95%"
    assert rendered["cloud-detail-review-state"]["text"] == "Awaiting human review"
    assert "status-awaiting-review" in rendered["cloud-detail-review-state"]["className"]
    assert "status-high-confidence" in rendered["cloud-detail-classification"]["className"]
    assert "CPU stayed below 5%" in " ".join(rendered["cloud-detail-flagged"]["children"])
    assert "No active dependency" in " ".join(rendered["cloud-detail-caution"]["children"])
    assert rendered["cloud-detail-owner"]["text"] == "payments-team"
    assert rendered["cloud-detail-dependencies"]["text"] == "No active dependency was found."
    assert rendered["cloud-detail-recommendation"]["text"] == "Stop temporarily and observe"
    assert rendered["cloud-detail-recommendation"]["className"] == "recommendation-action-value"
    assert rendered["cloud-detail-policy"]["text"] == "Allowed with safety conditions"
    assert "status-allowed" in rendered["cloud-detail-policy"]["className"]
    assert rendered["cloud-detail-policy-state"]["text"] == "Allowed with safety conditions"
    assert rendered["cloud-detail-human-required"]["text"] == "Human review required"
    assert "status-awaiting-review" in rendered["cloud-detail-human-required"]["className"]
    assert rendered["cloud-detail-classification-inline"]["text"] == "High-confidence ghost resource"
    assert "status-high-confidence" in rendered["cloud-detail-classification-inline"]["className"]
    assert rendered["cloud-human-technical"]["hidden"] is True
    assert rendered["cloud-human-technical"]["text"] == ""
    assert "44444444-4444-4444-4444-444444444444" not in rendered["cloud-human-technical"]["text"]
    assert rendered["cloud-technical-details"]["open"] is False
    assert rendered["cloud-detail-review-id"]["text"] == "44444444-4444-4444-4444-444444444444"
    assert rendered["cloud-detail-run-id"]["text"] == "33333333-3333-3333-3333-333333333333"
    assert rendered["cloud-detail-provider-id"]["text"] == "i-forgotten-test"
    assert rendered["cloud-open-approval-button"]["hidden"] is False
    assert rendered["cloud-back-button"]["text"] == "Back to Cloud Hunt"
    visible_actions = {button["action"] for button in rendered["cloudReviewButtons"] if not button["hidden"]}
    assert {"approve", "reject", "request_evidence", "add_context"} <= visible_actions
    visible_classes = {button["action"]: button["className"] for button in rendered["cloudReviewButtons"] if not button["hidden"]}
    assert visible_classes["approve"] == "button-primary"
    assert visible_classes["reject"] == "button-danger"
    assert visible_classes["request_evidence"] == "button-warning"
    assert visible_classes["add_context"] == "button-secondary"
    assert rendered["selectedReviewContext"]["source"] == "cloud-hunt"
    assert rendered["selectedReviewContext"]["runId"] == review["id"]


def test_approvals_review_decision_opens_cloud_detail_and_preserves_source_context() -> None:
    candidate = sample_cloud_candidate(terraform=False)
    review = sample_cloud_review(candidate)
    rendered = render_frontend({
        "run": None,
        "reviews": [review],
        "hunt": sample_cloud_hunt(candidate),
        "mode": "review-queue",
        "select_cloud_case_id": review["id"],
        "select_cloud_source": "approvals",
    })

    assert rendered["cloud-finding-detail"]["hidden"] is False
    assert rendered["cloud-finding-path"]["text"] == "Approvals -> forgotten-test"
    assert rendered["cloud-back-button"]["text"] == "Back to Approvals"
    assert rendered["selectedReviewContext"]["source"] == "approvals"
    assert rendered["selectedReviewContext"]["runId"] == review["id"]
    assert rendered["cloud-safety-notice"]["text"] == "Approval records the remediation decision and prepares the next supported remediation step. GhostBusters does not apply Terraform, merge pull requests, or modify cloud resources directly."


def test_cloud_human_actions_hide_approval_for_protected_and_completed_cases() -> None:
    protected_candidate = sample_cloud_candidate(candidate_id="protected-1", protected=True)
    protected_review = sample_cloud_review(protected_candidate, policy_status="needs_human_context")
    protected = render_frontend({
        "run": None,
        "reviews": [protected_review],
        "hunt": sample_cloud_hunt(protected_candidate),
        "mode": "cloud-hunt",
        "select_cloud_candidate_id": "protected-1",
    })
    protected_actions = {button["action"]: button for button in protected["cloudReviewButtons"]}

    assert protected_actions["approve"]["hidden"] is True
    assert protected_actions["reject"]["hidden"] is False
    assert protected_actions["request_evidence"]["hidden"] is False
    assert protected_actions["add_context"]["hidden"] is False
    assert protected_actions["request_evidence"]["className"] == "button-warning"
    assert protected_actions["add_context"]["className"] == "button-secondary"
    assert protected_actions["reject"]["className"] == "button-danger"
    assert protected["cloud-human-status"]["text"] == "Pending human review"
    assert "status-awaiting-review" in protected["cloud-human-status"]["className"]
    assert protected["cloud-human-technical"]["hidden"] is True
    assert protected["cloud-human-technical"]["text"] == ""
    assert "Safe by design" not in protected["cloud-human-guidance"]["text"]

    completed_candidate = sample_cloud_candidate(candidate_id="done-1")
    completed_review = sample_cloud_review(completed_candidate, status="pr_created")
    completed = render_frontend({
        "run": None,
        "reviews": [completed_review],
        "hunt": sample_cloud_hunt(completed_candidate),
        "mode": "cloud-hunt",
        "select_cloud_candidate_id": "done-1",
    })

    assert all(button["hidden"] for button in completed["cloudReviewButtons"])


def test_overview_dashboard_uses_real_loaded_state_without_raw_enums() -> None:
    reviews = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "source_type": "terraform_pr",
            "repository": "demo/infra",
            "pull_request_number": 42,
            "resource_name": "aws_instance.app",
            "recommendation": "Downsize to m5.large",
            "recommendation_reason": "Rightsizing looks safe.",
            "confidence": 0.91,
            "estimated_monthly_savings": 70.0,
            "policy_status": "passed",
            "status": "pending_human_review",
        }
    ]

    rendered = render_frontend({"run": sample_run(), "reviews": reviews, "mode": "overview"})
    combined = " ".join(rendered["summaryCards"] + rendered["overviewRows"] + rendered["overviewAlerts"] + rendered["overviewActivity"])

    assert rendered["page-title"]["text"] == "Overview"
    assert rendered["setup-progress-percent"]["text"]
    assert any("Connect GitHub" in step["text"] for step in rendered["setupSteps"])
    assert any("Select repositories" in step["text"] and "progress-waiting" in step["className"] for step in rendered["setupSteps"])
    assert any("Open PR Reviews 2" in card for card in rendered["summaryCards"])
    assert any("Awaiting Approval 2" in card for card in rendered["summaryCards"])
    assert any("Potential Monthly Savings $140" in card for card in rendered["summaryCards"])
    assert any("demo/infra" in row and "Open PR Review" in row for row in rendered["overviewRows"])
    assert any("demo/infra" in row and "Connected" in row for row in rendered["overviewRepos"])
    assert any("Review Decision" in row for row in rendered["overviewAlerts"])
    assert "pending_human_review" not in combined
    assert "[object Object]" not in combined


def test_overview_and_cloud_hunt_show_skeleton_loading_states() -> None:
    loading = {
        "initial": False,
        "reviews": True,
        "cloudHunt": True,
        "run": False,
        "review": False,
        "assistant": False,
    }
    rendered = render_frontend({"run": None, "reviews": [], "hunt": None, "mode": "overview", "loading": loading})

    assert rendered["summaryCards"]
    assert all("skeleton" in card for card in rendered["summaryCards"])
    assert rendered["overviewRows"]
    assert all("skeleton" in row for row in rendered["overviewRows"])


def test_cloud_hunt_status_badges_and_filter_chips_are_semantic() -> None:
    hunt = {
        "id": "33333333-3333-3333-3333-333333333333",
        "trigger_source": "manual_cloud_hunt",
        "provider_scope": "multi_cloud",
        "inventory_source": "fixtures",
        "goal": "Find forgotten cloud resources",
        "started_at": "2026-07-26T00:00:00Z",
        "completed_at": "2026-07-26T00:03:00Z",
        "status": "completed",
        "resources_scanned": 3,
        "candidates_found": 3,
        "investigations_created": 2,
        "protected_resources": 1,
        "errors": [],
        "planning_mode": "deterministic_only",
        "audit_events": [],
        "summary": {
            "total_resources": 3,
            "healthy_resources": 0,
            "candidates": 3,
            "high_confidence_candidates": 1,
            "protected_candidates": 1,
            "needs_human_context": 2,
            "estimated_monthly_waste": 260.0,
            "estimated_annual_waste": 3120.0,
            "provider_breakdown": {},
        },
        "candidates": [
            {
                "candidate_id": "ghost-1",
                "resource": {
                    "provider": "aws",
                    "resource_name": "forgotten-test",
                    "normalized_resource_type": "virtual_machine",
                    "environment": "staging",
                    "estimated_monthly_cost": 120.0,
                },
                "candidate_score": 0.95,
                "signals": [{"description": "CPU stayed below 5%.", "supports_ghost_hypothesis": True}],
                "requires_investigation": True,
                "exclusion_reason": None,
            },
            {
                "candidate_id": "protected-1",
                "resource": {
                    "provider": "azure",
                    "resource_name": "prod-cache",
                    "normalized_resource_type": "database",
                    "environment": "production",
                    "estimated_monthly_cost": 90.0,
                },
                "candidate_score": 0.87,
                "signals": [{"description": "Production dependency found.", "supports_ghost_hypothesis": False}],
                "requires_investigation": True,
                "exclusion_reason": "active_dependency",
            },
            {
                "candidate_id": "context-1",
                "resource": {
                    "provider": "gcp",
                    "resource_name": "ownerless-ip",
                    "normalized_resource_type": "public_ip",
                    "environment": "dev",
                    "estimated_monthly_cost": 50.0,
                },
                "candidate_score": 0.62,
                "signals": [{"description": "Owner tag is missing.", "supports_ghost_hypothesis": True}],
                "requires_investigation": True,
                "exclusion_reason": None,
            },
        ],
    }

    rendered = render_frontend({"run": None, "reviews": [], "hunt": hunt, "mode": "cloud-hunt"})
    tags = rendered["cloudCardTags"]
    tag_text = " ".join(tag["text"] for tag in tags)
    tag_classes = " ".join(tag["className"] for tag in tags)
    card_text = " ".join(rendered["cloudCards"])

    assert "High-confidence ghost resource" in tag_text
    assert "Protected resource" in tag_text
    assert "Needs more context" in tag_text
    assert "Pending human review" in tag_text
    assert "status-high-confidence" in tag_classes
    assert "status-protected" in tag_classes
    assert "status-needs-context" in tag_classes
    assert "status-awaiting-review" in tag_classes
    assert all(tag["tagName"] == "SPAN" for tag in tags)
    assert "active_dependency" not in card_text
    assert "[object Object]" not in card_text
    assert rendered["cloudTables"]
    assert "Provider Resource Resource type Environment Monthly cost Potential savings Confidence Classification Review status Action" in rendered["cloudTables"][0]
    assert any("View Finding" in card for card in rendered["cloudCards"])
    assert "Open Review" not in card_text
    assert all(chip["tagName"] == "BUTTON" for chip in rendered["filterChips"])
    assert any(chip["filter"] == "all" and chip["ariaPressed"] == "true" and "filter-chip-active" in chip["className"] for chip in rendered["filterChips"])
    assert rendered["filter-count-all"]["text"] == "3"
    assert rendered["filter-count-high-confidence"]["text"] == "1"
    assert rendered["filter-count-protected"]["text"] == "1"
    assert rendered["filter-count-needs-context"]["text"] == "1"
    assert rendered["filter-count-awaiting-review"]["text"] == "2"
    assert any("Inventory loaded" in step["text"] and "progress-completed" in step["className"] for step in rendered["cloudJourney"])
    assert any("Human review" in step["text"] and "progress-human-action-required" in step["className"] for step in rendered["cloudJourney"])

    protected_only = render_frontend({"run": None, "reviews": [], "hunt": hunt, "mode": "cloud-hunt", "cloud_filter": "protected"})
    assert any(chip["filter"] == "protected" and chip["ariaPressed"] == "true" and "filter-chip-active" in chip["className"] for chip in protected_only["filterChips"])
    assert len(protected_only["cloudCards"]) == 1
    assert "Protected resource" in protected_only["cloudCards"][0]
