# AMOS: Agentic Market-Facing Operating System
## Campaign Planning Layer
A multi-agent workflow that converts a business objective into a structured campaign plan: enriched context, target cohorts, media plan, creative directions, and a risk-adjusted revenue forecast. Built for the Claude@Stanford Buildathon (April 2026).

**Sample output:** https://amos-campaign-planner.vercel.app

## What it does
**Input:** a business objective and a budget. Example: "Grow Taneira revenue during the festive period by 40%." The system also reads a pre-shared business context file (categories, cohorts, historical performance, brand values) so the plan is grounded in real business reality, not generic assumptions.

**Output:** a structured campaign brief including:
- Enriched objective with competitive and category context
- Target customer cohorts with growth vs. defend recommendations
- Channel-by-channel media plan per cohort
- Creative directions tailored to each channel and cohort
- Risk-adjusted revenue forecast with budget and cohort constraints flagged

## How it works
Five specialized agents run in sequence, each enriching the previous agent's output:

1. **Context agent:** reads the pre-shared business file, pulls competitive signals, customer trends, and industry data, and enriches the raw business objective into deeper strategic context.
2. **Cohort agent:** identifies which customer cohorts can deliver the target growth, flags cohorts to invest in versus cohorts to defend, and hands off to the media layer.
3. **Media agent:** identifies where each cohort is most active and responsive (e.g., Instagram, LinkedIn, CRM), and builds a channel-by-channel media plan.
4. **Creative agent:** uses competitor messaging, brand values, and the media plan to generate creative directions tailored to each channel and cohort (e.g., Reels for Instagram with specific messaging angles).
5. **Forecast agent:** models revenue delivery by cohort under the proposed media plan, and flags limitations (budget caps, cohort size constraints, dependency on new cohort onboarding).

The system is deliberately built for human-in-the-loop decision making, not full automation.

## Built with
- Claude (Anthropic) for the agent reasoning layer
- Claude Code for orchestration and code generation
- Python / PowerShell for local execution
- Vercel for the rendered sample output

## Context
Built as part of ongoing research at Stanford GSB on how market-facing functions (marketing, GTM, and growth) are being redesigned around agentic AI, supervised by Prof. Yuyan Wang. Full research overview: [The Agentic Market-Facing Operating System](https://medium.com/@mathurshobhika7/the-agentic-marketing-playbook-an-overview-d6a141e08b83).

## Status
Work in progress. The Campaign Planning Layer is the first of several layers planned. The current version runs locally via command line; the output is rendered to the static Vercel page linked above as a sample. Future iterations will expose an interactive input surface so operators can run the workflow directly from the browser.

