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
  return {{
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
    appendChild(child) {{ this.children.push(child); return child; }},
    removeChild(child) {{ this.children = this.children.filter((item) => item !== child); }},
    get firstChild() {{ return this.children[0] || null; }},
    addEventListener() {{}},
    setAttribute(name, value) {{ this[name] = value; }},
    scrollIntoView() {{}},
    querySelectorAll() {{ return []; }},
    classList: {{ toggle() {{}}, add() {{}}, remove() {{}} }},
  }};
}}

const elements = new Map();
const reviewButtons = ["approve", "modify", "request_evidence", "add_context", "reject"].map((action) => {{
  const button = createNode("button");
  button.dataset.reviewAction = action;
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
    "/api/reviews": [],
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
    scrollTo() {{}},
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

(async () => {{
  vm.runInNewContext(source, context);
  await Promise.resolve();
  await Promise.resolve();
  const hooks = context.window.__ghostbustersTestHooks;
  hooks.state.run = {json.dumps(payload["run"])};
  hooks.state.visibleEvents = hooks.state.run ? (hooks.state.run.audit_events || []) : [];
  hooks.state.reviews = {json.dumps(payload.get("reviews", []))};
  hooks.state.hunt = {json.dumps(payload.get("hunt"))};
  if ({json.dumps(payload.get("open_demo", False))}) hooks.openDemoModal();
  if ({json.dumps(payload.get("mode"))}) hooks.switchMode({json.dumps(payload.get("mode"))});
  hooks.renderAll();

  const ids = [
    "source-kind", "source-repository", "source-pr", "source-title", "source-head", "source-base",
    "source-integration", "change-resource", "change-before", "change-after", "change-file",
    "change-cost-impact", "recommendation-title", "recommendation-policy", "recommendation-savings",
    "recommendation-annual-savings", "result-title", "result-view", "safety-summary",
    "trigger-source", "run-pill", "approval-pill", "evidence-count", "candidate-count",
    "pr-empty-state", "case-view", "demo-modal-backdrop", "technical-content", "technical-empty-state",
    "case-status", "human-decision-summary", "recommendation-summary", "evidence-source-card",
  ];
  const output = {{}};
  for (const id of ids) {{
    const node = elements.get(id) || createNode("div", id);
      output[id] = {{
        text: node.textContent,
        hidden: node.hidden,
        children: node.children.map((child) => nodeText(child) || child.href || child.className || ""),
        href: node.href,
      }};
    }}
    output.reviewButtons = reviewButtons.map((button) => ({{
      action: button.dataset.reviewAction,
      hidden: button.hidden,
      disabled: button.disabled,
    }}));
    output.queueCards = (elements.get("review-queue-list")?.children || []).map((child) => nodeText(child));
    output.cloudCards = (elements.get("candidate-list")?.children || []).map((child) => nodeText(child));
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
                    "value": {"current_monthly_cost": 70, "proposed_monthly_cost": 140},
                    "resource_id": "aws_instance.app",
                    "collected_at": "2026-07-26T00:00:20Z",
                    "freshness_status": "fresh",
                    "reliability": 1.0,
                    "metadata": {},
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
    assert "Approval creates a remediation pull request only." in root
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
    assert rendered["demo-modal-backdrop"]["hidden"] is False
    assert rendered["technical-content"]["hidden"] is True
    assert rendered["technical-empty-state"]["hidden"] is False
    assert "Demo scenario" in root
    assert "Demo objective" in root


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
    assert any("Open Review" in card for card in rendered["queueCards"])
