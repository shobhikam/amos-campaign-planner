# AMOS: Agentic Market-Facing Operating System
## Campaign Planning Layer

A multi-agent workflow that converts a business objective into a structured campaign plan: strategic context, ranked customer cohorts, brand-compliant creative, a media allocation plan, and a risk-adjusted revenue forecast. Built for the Claude@Stanford Buildathon (April 2026).

Sample output: [amos-campaign-planner.vercel.app](https://amos-campaign-planner.vercel.app)
Research overview: [The Agentic Market-Facing Operating System](https://medium.com/@mathurshobhika7/the-agentic-marketing-playbook-an-overview-d6a141e08b83)

## What it does

**Input:** a business objective. Example: "Grow Okhiya Fall 2026 launch revenue by 15%." The system reads a pre-shared business context spreadsheet (cohorts, channels, brand guidelines, historical performance, industry trends, competitive landscape, model assumptions) so the plan is grounded in real business reality, not generic assumptions.

**Output:** a structured campaign brief including:

* Enriched objective with cohort-level revenue targets
* Strategic direction with growth vs. defend recommendations per cohort
* Two creative routes per cohort, generated via the Claude API and checked against brand vocabulary
* Channel-by-channel media plan with effectiveness multipliers and budget allocation
* Risk-adjusted revenue forecast where every number traces back to a specific cell in the input spreadsheet

## How it works

Five specialized agents run in sequence, each enriching the previous agent's output:

1. **Objective Intake.** Parses the raw business objective. Extracts target growth, timeframe, currency, and budget envelope. Resolves the period revenue against historical baselines.
2. **Context & Strategy.** Loads brand guidelines, cohort data, channel assumptions, industry trends, and competitive landscape. Applies a composite scoring model to rank cohorts and assigns each a strategic label (DEFEND or INVEST FOR GROWTH).
3. **Human checkpoint.** The pipeline pauses. No creative is generated, no budget is allocated, no forecast is computed until the operator approves the strategic direction. The agents surface reasoning; the human owns the decision.
4. **Creative Director.** Powered by Claude Sonnet 4.5. Generates two creative routes per cohort, grounded in brand archetype, tone of voice, approved vocabulary, and off-limits words. Falls back to templated routes if the API is unavailable, so the demo always completes end-to-end.
5. **Media Planner.** Selects best-fit channels per cohort based on the channel assumptions sheet. Allocates budget proportional to channel effectiveness. Computes weighted effectiveness per cohort.
6. **Impact Forecaster.** Models budget-driven reach per channel using cost-per-customer-reached. Applies a de-duplication haircut, caps reach at cohort size, and computes uplift using the formula: Reach × AOV × Conversion Lift × Channel Effectiveness. Sums across cohorts, applies a risk adjustment, and emits a verdict against the target.

The system is deliberately built for human-in-the-loop decision making, not full automation.

## How to run

Requires Python 3.10+, an Anthropic API key, and the Python package `openpyxl`.

```bash
pip install openpyxl anthropic
echo "your-api-key-here" > api_key.txt
python main.py AMOS_Okhiya_Mock_Data_Input.xlsx
```

The pipeline reads brand context, cohorts, channels, and assumptions from the spreadsheet. To run it on a different brand, edit the input file (or create your own following the same sheet schema) and pass it as the argument. The code is brand-agnostic and currency-aware (USD and INR supported).

## Built with

* **Claude Sonnet 4.5** for the creative agent (Agent 3)
* **Python** for the deterministic agents (1, 2, 4, 5) and orchestration via `main.py`
* **openpyxl** to read the structured input spreadsheet
* **Vercel** for the rendered sample output linked above
* Built using **Claude Code** at the Anthropic Claude@Stanford Buildathon

## Context

Built as part of ongoing research at Stanford GSB on how market-facing functions (marketing, GTM, and growth) are being redesigned around agentic AI, supervised by Prof. Yuyan Wang. Full research overview: [The Agentic Market-Facing Operating System](https://medium.com/@mathurshobhika7/the-agentic-marketing-playbook-an-overview-d6a141e08b83).

## Status

Work in progress. The Campaign Planning Layer is the first of several layers planned. The current version runs locally via command line; the output is rendered to the static Vercel page linked above as a sample. Future iterations will expose an interactive input surface so operators can run the workflow directly from the browser.
