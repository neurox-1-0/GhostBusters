# GhostBusters Competition Demo Guide

## Setup

1. Install dependencies and start the API with `uvicorn app.main:app --reload`.
2. Open `http://127.0.0.1:8000` and register or use the local demo account shown by the environment.
3. Open **Demo Readiness** first. Confirm the data-mode labels, health checks, webhook readiness, and known warnings.

## Five-to-seven minute flow

1. **Safe recommendation (2 minutes):** open **PR Reviews**, start the `safe` fixture scenario, inspect the plan and evidence, then use **Approvals** to approve it. Show the remediation result and the pending or verified outcome link. Fixture-backed evidence is labeled in the UI.
2. **Conflicting evidence (2 minutes):** start `conflicting`. Show the business status and recent repository activity disagreeing, the confidence reduction, and the request for more evidence or human review.
3. **Safe fallback (1-2 minutes):** start `missing_evidence`. Show the failed evidence stage, bounded fallback, missing-evidence record, and safe escalation or abstention.
4. Finish in **Activity Log** and **Technical Audit** to show the shared correlation trail.

## Reset

From **Demo Readiness**, choose **Reset Demo Fixtures** and confirm. This reset is permission-protected and removes only demo workflow/run fixtures. Organization settings, members, integration configuration, and real organization data are preserved. The reset is recorded in Activity Log.

## Fallback and limitations

When AWS, GitHub, or Jira is unavailable, use the fixture scenarios and keep the source-mode badge visible. GhostBusters does not automatically apply Terraform, merge or close GitHub PRs, mutate Jira, approve changes, or create remediation PRs without the normal human approval flow.
