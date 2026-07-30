# GhostBusters — NeuroX Phase 2 Presenter Notes

## Suggested opening
“GhostBusters is a controlled autonomous FinOps agent. It does not blindly optimize cloud resources. It turns a goal into an evidence-led investigation, branches when conditions change, and gives people the final authority to act.”

## Demonstration rule
Be accurate about data source mode. If a live GitHub/AWS/Jira integration is not configured, say that the fixture is a controlled demonstration input. Do not claim a cloud mutation, Terraform apply, or real pricing when it did not happen.

## High-value talking points
- Slide 4: Explain the actual branch conditions: production, destructive action, missing evidence, active dependencies, conflicts, and human context.
- Slide 6: Point out that the planner records why it selected or skipped each registered tool.
- Slide 8: This is the strongest answer to “why is this not a fixed pipeline?” Run the conflicting and missing-evidence scenarios live.
- Slide 9: Autonomy is bounded by verifier, policy, RBAC, and a required human decision.
- Slide 10: Open Technical Audit and Activity Log. Show a real correlation trail rather than just describing it.

## Likely judge questions
1. **What makes this autonomous?** The goal-driven planner chooses a relevant subset of tools, changes course based on evidence and safety signals, retries bounded external calls, and can request information or abstain.
2. **How does it choose tools?** The plan considers the goal, Terraform change, environment, and registered capabilities. For example, GitHub terms select PR context/ownership/reviews; AWS terms select inventory, CloudWatch, tags, and pricing.
3. **How does it recover?** It records unavailable evidence, uses bounded retry/backoff, lowers confidence, and safely requests evidence or abstains instead of fabricating results.
4. **Where is the human in the loop?** A reviewer can approve, reject, modify, request evidence, add context, waive, revoke, and reopen. Remediation always requires approval.
5. **Can it change infrastructure?** No Terraform apply or cloud mutation occurs. Real GitHub PR creation is opt-in, guarded, and still goes through normal engineering/CI/CD deployment.
