from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_serves_agent_console() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "GhostBusters" in response.text
    assert "PR Reviews" in response.text
    assert "Approvals" in response.text
    assert "Technical Audit" in response.text
    assert 'id="simple-view"' in response.text
    assert 'id="technical-view" hidden' in response.text
    assert 'id="overview-view"' in response.text
    assert 'id="overview-summary"' in response.text
    assert 'id="setup-progress-list"' in response.text
    assert 'id="overview-repositories-list"' in response.text
    assert 'id="cloud-journey-list"' in response.text
    assert 'id="overview-view-button"' in response.text
    assert "/static/app.js?v=judge-v6" in response.text
    assert "/static/styles.css?v=judge-v6" in response.text
    assert "Open Source PR" in response.text
    assert "Launch Demo" in response.text
    assert "Why GhostBusters recommends this" in response.text
    assert "Approval creates a remediation pull request or approved remediation proposal only." in response.text
    assert "Open Technical Audit" in response.text
    assert "Cloud Hunt" in response.text
    assert "Ask GhostBusters" in response.text
    assert "Settings" in response.text
    assert "Help" in response.text
    assert "Search reviews, resources, repositories" not in response.text
    assert "It cannot approve actions or modify infrastructure" in response.text
    assert "[object Object]" not in response.text


def test_root_explains_objective_and_entry_modes_accurately() -> None:
    response = client.get("/")

    assert "No review selected." in response.text
    assert "Open a case from Approvals" in response.text
    assert "Demo Mode uses prepared fixture data" in response.text
    assert "Demo scenario" in response.text
    assert "Demo objective" in response.text
    assert "Review objective" not in response.text
    assert "Prepared case" not in response.text
    assert "High-level goal" not in response.text
    assert "chatbot" not in response.text.lower()


def test_css_asset_served() -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--bg" in response.text
    assert "--page-background" in response.text
    assert "--surface-background" in response.text
    assert "--elevated-card-background" in response.text
    assert "--brand-teal" in response.text
    assert "--ai-purple" in response.text
    assert "--success-green" in response.text
    assert "--warning-amber" in response.text
    assert "--blocked-red" in response.text
    assert "--neutral-slate" in response.text
    assert "--button-radius" in response.text
    assert "--radius" in response.text
    assert ".sidebar" in response.text
    assert ".summary-card" in response.text
    assert ".progress-checklist" in response.text
    assert ".featured-card" in response.text
    assert ".recent-table" in response.text
    assert ".data-table" in response.text
    assert ".skeleton" in response.text
    assert ".toast" in response.text
    assert ".filter-chip" in response.text
    assert ".filter-chip-active" in response.text
    assert ".status-badge" in response.text
    assert ".status-high-confidence" in response.text
    assert ".status-protected" in response.text
    assert ".status-needs-context" in response.text
    assert ".status-awaiting-review" in response.text
    assert ".status-blocked" in response.text
    assert ".status-allowed" in response.text
    assert ".button-primary" in response.text
    assert ".button-danger" in response.text
    assert ".button-warning" in response.text
    assert ".review-actions .button-warning { border-color: var(--amber); background: var(--amber); color: #fff; }" in response.text
    assert ".review-actions .button-secondary" in response.text
    assert ".technical-details-card" in response.text
    assert ".decision-panel { display: grid; grid-template-columns: minmax(260px, 0.42fr) minmax(0, 0.58fr); gap: 1.5rem; align-items: start; border-left: 0; }" in response.text
    assert ".human-decision-card { padding: 1.5rem; background: var(--elevated-card-background); }" in response.text
    assert ".review-actions button { width: 100%; max-width: none; flex-basis: 100%; }" in response.text
    assert "border-left: 5px solid var(--amber)" not in response.text
    assert "Technical IDs are available below." not in client.get("/static/app.js").text
    assert ".cloud-recommendation-card" in response.text
    assert "border-left: 4px solid var(--teal)" in response.text
    assert "border-radius: var(--card-radius)" in response.text
    assert ".cloud-detail-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1rem; align-items: stretch; }" in response.text
    assert ".cloud-detail-layout { grid-template-columns: 1fr; }" in response.text
    assert ".recommendation-card { border-top: 5px solid var(--teal); background: var(--navy); color: #fff; }" not in response.text
    assert ".cloud-recommendation-card { border: 0; border-top: 5px solid var(--teal); }" not in response.text
    assert "prefers-reduced-motion" in response.text
    assert ".stage-list" in response.text
    assert "max-width: 1500px" not in response.text


def test_frontend_typography_system_is_explicit() -> None:
    html = client.get("/").text
    css = client.get("/static/styles.css").text
    script = client.get("/static/app.js").text

    assert "Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" in css
    assert '--font-family-primary: "Plus Jakarta Sans", Inter, ui-sans-serif, system-ui' in css
    assert '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' in css
    assert "--font-family-mono: ui-monospace" in css
    assert 'id="page-title" class="page-title"' in html
    assert "metric-value" in css
    assert '"metric-value"' in script
    assert "table-heading" in css
    assert '"table-heading"' in script
    assert ".technical-value" in css
    assert "technicalLabels" in script
    assert 'font-family: var(--font-family-primary)' in css
    assert "prefers-reduced-motion" in css


def test_frontend_font_weights_stay_within_required_set() -> None:
    css = client.get("/static/styles.css").text
    weights = {int(match) for match in re.findall(r"font-weight:\s*(\d+)", css)}

    assert weights
    assert weights <= {400, 500, 600, 700}


def test_frontend_text_roles_and_labels_remain_accessible() -> None:
    html = client.get("/").text
    css = client.get("/static/styles.css").text
    script = client.get("/static/app.js").text

    assert "--text-sm: 0.875rem" in css
    assert "font-size: var(--text-sm)" in css
    assert ".status-badge" in css
    assert "line-height: 1.2" in css
    assert "Open Review" not in html + script
    assert "View Finding" in script
    assert "Review Decision" in script
    assert 'id="cloud-finding-detail" hidden role="dialog" aria-modal="true"' in html
    assert "position: fixed" in css
    assert "z-index: 2147483000" in css
    assert "Approve Recommendation" in html + script
    assert "Request More Evidence" in html
    assert "Start Cloud Hunt" in html
    assert "Ask GhostBusters" in html
    assert "Send Review Update" in html + script
    assert ">Submit<" not in html


def test_javascript_asset_served() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "fetch" in response.text
    assert "stageDefinitions" in response.text
    assert "safeObject" in response.text
    assert "ensureCompatibleDom" in response.text
    assert "assistantSuggestions" in response.text
    assert "renderOverview" in response.text
    assert "renderSetupProgress" in response.text
    assert "renderCloudJourney" in response.text
    assert "withButtonState" in response.text
    assert "showToast" in response.text
    assert "renderSkeletonList" in response.text
    assert "Deterministic fallback" in response.text
    assert "Deterministic Safety Policy" in response.text
    assert "More Evidence Required" in response.text
    assert "AI-assisted planning" in response.text
    assert "Prepared fixtures are backing this demo case." in response.text
    assert "[object Object]" not in response.text
