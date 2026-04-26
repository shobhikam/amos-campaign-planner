# main.py
# Entry point for the AMOS 5-Agent Campaign Planning Pipeline.
# Brand-agnostic: works for any input file matching the AMOS sheet schema.
# Run: python main.py <input.xlsx>     (defaults to AMOS_Okhiya_Mock_Data_Input.xlsx)

import sys
from pathlib import Path

from data_loader import load_all_data
from agents import (
    agent1_objective_intake,
    agent2_context_strategy,
    agent3_creative_director,
    agent4_media_planner,
    agent5_forecaster,
)


# ─── API KEY ─────────────────────────────────────────────────────────────────

def load_api_key():
    """Read API key from api_key.txt in the current folder. Returns None if missing."""
    key_file = Path("api_key.txt")
    if not key_file.exists():
        return None
    key = key_file.read_text(encoding="utf-8").strip()
    return key if key else None


# ─── PRINT HELPERS ───────────────────────────────────────────────────────────

_WIDTH = 66


def _box(title: str):
    inner  = f"  {title}  "
    pad_total = _WIDTH - len(inner)
    pad_l  = " " * (pad_total // 2)
    pad_r  = " " * (pad_total - pad_total // 2)
    print(f"\n╔{'═' * _WIDTH}╗")
    print(f"║{pad_l}{inner}{pad_r}║")
    print(f"╚{'═' * _WIDTH}╝\n")


def _div():
    print("─" * _WIDTH)


def _money(amount: float, parsed_obj: dict, decimals: int = 1) -> str:
    """Format a money amount as '${amount}M' (USD) or '₹{amount} Cr' (INR).
    Reads currency_symbol and currency_unit from parsed_obj (set by Agent 1)."""
    sym = parsed_obj.get("currency_symbol", "$")
    unit = parsed_obj.get("currency_unit", "M")
    if unit == "Cr":
        return f"{sym}{amount:.{decimals}f} Cr"
    return f"{sym}{amount:.{decimals}f}M"


def _money_per_customer(amount, parsed_obj: dict) -> str:
    """Format a per-customer cost (CPC) as ${amount} (USD minor unit) or ₹{amount} (INR minor unit)."""
    if amount is None:
        return "N/A"
    sym = parsed_obj.get("currency_symbol", "$")
    return f"{sym}{int(amount)}"


# ─── AGENT 1 PRINT ───────────────────────────────────────────────────────────

def print_agent1_output(o: dict):
    _box("AGENT 1 — OBJECTIVE INTAKE")
    print(f"  Brand:                {o['brand_name']}")
    print(f"  Raw input:            {o['raw_objective']}")
    print(f"  Target growth:        {o['target_growth_pct']:.0f}%")
    print(f"  Timeframe:            {o['timeframe']}")
    print(f"  Baseline growth:      {o['baseline_growth_pct']:.0f}% organic")
    print(f"  Current period rev:   {_money(o['current_period_revenue'], o)}")
    print(f"  Target uplift:        {_money(o['target_uplift'], o)}  "
          f"({o['target_growth_pct']:.0f}% × {_money(o['current_period_revenue'], o)})")


# ─── AGENT 2 PRINT ───────────────────────────────────────────────────────────

def print_agent2_output(strategy: dict):
    _box("AGENT 2 — CONTEXT & STRATEGY")
    print("STRATEGIC DIRECTION — COHORT RANKINGS")
    _div()

    # Build cohort lookup for display metadata
    cohort_meta = {c["cohort_name"]: c for c in strategy["cohorts"]}

    for sd in strategy["strategic_direction"]:
        c    = cohort_meta.get(sd["cohort_name"], {})
        rev  = c.get("revenue_pct")
        grow = c.get("growth_potential", "?")
        comp = c.get("competitive_intensity", "?")
        rev_str = f"{rev * 100:.1f}%" if rev is not None else "?"

        label_tag = f"[{sd['label']}]"
        print(f"#{sd['rank']}  {sd['cohort_name'].upper():<38} {label_tag}")
        print(f"    Revenue share: {rev_str} | Growth potential: {grow} | Competition: {comp}")
        print(f"    Composite score: {sd['composite_score']}")

        insight = sd["insight_quoted"]
        if len(insight) > 120:
            insight = insight[:117] + "..."
        print(f"    Insight: \"{insight}\"")
        print(f"    → Reasoning: {sd['reasoning']}")
        print()


# ─── AGENT 3 PRINT ───────────────────────────────────────────────────────────

def print_agent3_output(creative_briefs: list):
    _box("AGENT 3 — CREATIVE DIRECTOR  [powered by Claude API]")

    # Separate data entries from the totals sentinel
    totals = next((b for b in creative_briefs if b.get("_totals")), {})
    briefs = [b for b in creative_briefs if not b.get("_totals")]

    for brief in briefs:
        label_hint = "retention-angled" if brief["label"] == "DEFEND" else "acquisition-angled"
        print(f"COHORT: {brief['cohort_name']} | Strategy: {brief['label']} ({label_hint})")

        # Show API call info if a real call was made
        if brief["api_calls_made"] > 0 and brief["in_tokens"] > 0:
            cost = (brief["in_tokens"] * 3.0 + brief["out_tokens"] * 15.0) / 1_000_000
            print(f"[API call: claude-sonnet-4-5 | "
                  f"{brief['in_tokens']:,} in + {brief['out_tokens']:,} out tokens | "
                  f"${cost:.3f}]")
        else:
            print("[Using templated fallback — no API call]")

        _div()

        for i, route in enumerate(brief["routes"], 1):
            name = route["route_name"]
            print(f"  Route {i} — \"{name}\"")
            print(f"    Concept:    {route['concept']}")
            print(f"    Rationale:  {route['rationale']}")
            print(f"    Compliance: {route['compliance_note']}")
        print()

    # Run-level API summary
    total_calls = totals.get("total_calls", 0)
    if total_calls > 0:
        in_tok  = totals.get("total_input_tokens", 0)
        out_tok = totals.get("total_output_tokens", 0)
        cost    = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
        print(f"[API calls this run: {total_calls} | est. cost: ${cost:.3f}]")
    else:
        print("[API calls this run: 0 | using templated fallback]")


# ─── AGENT 4 PRINT ───────────────────────────────────────────────────────────

def print_agent4_output(media_plans: list):
    _box("AGENT 4 — MEDIA PLANNER")

    for plan in media_plans:
        print(f"COHORT: {plan['cohort_name']} | Strategy: {plan['label']}")
        _div()
        print(f"  Selected channels (best-fit = {plan['cohort_name']}):")

        for i, ch in enumerate(plan["channels"], 1):
            print(f"  {i}. {ch['channel_name']:<32} — Effectiveness: "
                  f"{ch['effectiveness_multiplier']:.2f}x | "
                  f"{ch['measurability']} | {ch['budget_pct']}% budget")
            print(f"     Reasoning: {ch['reasoning']}")

        # Weighted effectiveness breakdown
        parts = " + ".join(
            f"{ch['effectiveness_multiplier']:.2f}×{ch['budget_pct'] / 100:.2f}"
            for ch in plan["channels"]
        )
        total_budget = sum(ch["budget_pct"] for ch in plan["channels"])
        print(f"\n  Weighted channel effectiveness: ({parts}) = {plan['weighted_effectiveness']:.3f}x")
        print(f"  [Budget allocation sums to: {total_budget}%]")
        print()


# ─── AGENT 5 PRINT ───────────────────────────────────────────────────────────

def print_agent5_output(forecast: dict, parsed_obj: dict, input_filename: str):
    _box("AGENT 5 — IMPACT FORECASTER")
    assumptions = forecast["assumptions_used"]

    print("=== FORECAST ASSUMPTIONS (CFO-INTERROGATABLE) ===")
    print(f"  All values read live from {input_filename}")
    print("  Edit the sheet to change the model — no code changes required.")
    print()
    print("  [Assumptions & Model Settings sheet]")

    def _arow(key):
        a = assumptions.get(key)
        if not a:
            return
        v    = a["value"]
        row  = a["row"]
        lbl  = a["label"]
        # Format value
        if isinstance(v, float) and key not in ("total_campaign_budget",
                                                  "creative_production_share",
                                                  "media_budget_share"):
            v_str = f"{v * 100:.1f}%"
        elif key == "attribution_window_days":
            v_str = f"{v} days"
        elif key == "total_campaign_budget":
            v_str = _money(v, parsed_obj)
        else:
            v_str = str(v)
        print(f"  Row {row:2d}  {lbl:<48} {v_str}")

    _arow("baseline_conversion_lift_low")
    _arow("baseline_conversion_lift_expected")
    _arow("baseline_conversion_lift_high")
    _arow("organic_baseline_growth_rate")
    _arow("risk_adjustment")
    _arow("attribution_window_days")

    print()
    print("  [Cohort reach assumptions — reference only, computed from budget below]")
    # Cohort reach assumption keys are now dynamically derived; show all of them
    for key in sorted(assumptions.keys()):
        if key.startswith("reach_"):
            _arow(key)

    print()
    print("  [Budget envelope]")
    total_budget   = assumptions.get("total_campaign_budget", {}).get("value") or 0
    creative_share = assumptions.get("creative_production_share", {}).get("value") or 0
    media_share    = assumptions.get("media_budget_share", {}).get("value") or 0
    creative_amt   = total_budget * creative_share
    media_amt      = total_budget * media_share
    _arow("total_campaign_budget")
    a_cp = assumptions.get("creative_production_share")
    if a_cp:
        print(f"  Row {a_cp['row']:2d}  {a_cp['label']:<48} "
              f"{creative_share * 100:.0f}%  → {_money(creative_amt, parsed_obj, 2)} creative")
    a_mb = assumptions.get("media_budget_share")
    if a_mb:
        print(f"  Row {a_mb['row']:2d}  {a_mb['label']:<48} "
              f"{media_share * 100:.0f}%  → {_money(media_amt, parsed_obj, 2)} media pool")

    print()
    print("=== BUDGET → REACH → UPLIFT CHAIN ===")
    print()

    for cf in forecast["cohort_forecasts"]:
        cohort_media = cf.get("cohort_media_budget", 0)
        pool         = cf.get("media_pool", media_amt)
        rank_pct     = round(cohort_media / pool * 100) if pool else 0

        print(f"COHORT: {cf['cohort_name']} | Rank #{cf.get('rank', '?')}")
        print(f"  Media allocated to cohort:    {_money(cohort_media, parsed_obj, 2)}"
              f"   ({rank_pct}% of {_money(pool, parsed_obj, 2)} media pool)")
        print()

        breakdown = cf.get("channel_reach_breakdown", [])
        if breakdown:
            unit_col = parsed_obj.get("currency_symbol", "$") + " " + parsed_obj.get("currency_unit", "M")
            print(f"  {'Channel':<32} {'Bgt%':>4}  {unit_col:>7}  {'CPC':>6}  {'Reach':>12}")
            print(f"  {'─' * 68}")
            for ch in breakdown:
                cpc_str   = _money_per_customer(ch['cpc'], parsed_obj)
                reach_str = f"{ch['channel_reach']:>12,}"
                amt_str   = _money(ch['budget'], parsed_obj, 2)
                print(f"  {ch['channel_name']:<32} {ch['budget_pct']:>3}%  "
                      f"{amt_str:>7}  {cpc_str:>6}  {reach_str}")
            print(f"  {'─' * 68}")
            sum_raw   = cf.get("sum_raw_reach", 0)
            deduped   = cf.get("deduped_reach", 0)
            print(f"  {'Sum of channel reach:':<55} {sum_raw:>12,}")
            print(f"  {'De-duplication haircut (-20%):':<55} {sum_raw - deduped:>12,}")
            print(f"  {'Unique customers reachable:':<55} {deduped:>12,}")

        print()
        cohort_size = cf['cohort_size']
        final_reach = cf['final_reach']
        print(f"  Cohort size: {cohort_size:,}")
        reach_label = cf.get("reach_label", "")
        print(f"  ► {reach_label}")
        print(f"  → Final reach: {final_reach:,} customers")
        print()

        cpc_aov = _money_per_customer(int(cf['aov']), parsed_obj)
        uplift_str = _money(cf['uplift'], parsed_obj, 2)
        uplift_line = (f"  Uplift: {final_reach:,} × {cpc_aov} × "
                       f"{cf['conversion_lift'] * 100:.1f}% × {cf['weighted_eff']:.3f}x"
                       f" = {uplift_str}")
        print(uplift_line)
        print()

    risk_pct = assumptions["risk_adjustment"]["value"] * 100
    _div()
    print(f"  Total projected uplift:       {_money(forecast['total_uplift'], parsed_obj, 2)}")
    print(f"  After risk adjustment ({risk_pct:.0f}%): {_money(forecast['risk_adjusted_uplift'], parsed_obj, 2)}")
    _div()
    print(f"  Target uplift (from objective): {_money(forecast['target_uplift'], parsed_obj, 2)}")
    print(f"  Projected (risk-adjusted):      {_money(forecast['risk_adjusted_uplift'], parsed_obj, 2)}")
    print()
    print(f"  Verdict:  {forecast['verdict']}")


# ─── FINAL BRIEF ─────────────────────────────────────────────────────────────

def print_campaign_brief(
    parsed_obj: dict,
    strategy: dict,
    creative_briefs: list,
    media_plans: list,
    forecast: dict,
):
    brand_upper   = parsed_obj["brand_name"].upper()
    occasion      = strategy["business_context"].get("Occasion / Campaign", "Campaign")
    title         = f"FINAL CAMPAIGN BRIEF — {brand_upper} {occasion.upper()}"
    _box(title)

    # Find budget field by flexible label match (works for "($M)" or "(₹ Cr)")
    biz = strategy["business_context"]
    budget_val = None
    for k, v in biz.items():
        if "campaign budget envelope" in str(k).lower():
            budget_val = v
            break
    budget_str = _money(float(budget_val), parsed_obj, 1) if budget_val else "N/A"

    print(f"  Brand:          {parsed_obj['brand_name']}")
    print(f"  Objective:      {parsed_obj['raw_objective']}")
    print(f"  Timeframe:      {parsed_obj['timeframe']}")
    print(f"  Budget:         {budget_str}")
    print()

    print("STRATEGIC DIRECTION:")
    for sd in strategy["strategic_direction"]:
        print(f"  #{sd['rank']} {sd['cohort_name']:<38} [{sd['label']}]")
    print()

    print("CREATIVE ROUTES:")
    creative_briefs = [b for b in creative_briefs if not b.get("_totals")]
    for brief in creative_briefs:
        api_marker = "" if brief["api_calls_made"] > 0 else " [templated]"
        print(f"  {brief['cohort_name']} ({brief['label']}){api_marker}:")
        for route in brief["routes"]:
            name = route["route_name"].replace("[TEMPLATED FALLBACK] ", "")
            print(f"    • \"{name}\": {route['concept']}")
    print()

    print("MEDIA ALLOCATION:")
    for plan in media_plans:
        channels_str = "  |  ".join(
            f"{ch['channel_name']} ({ch['budget_pct']}%)"
            for ch in plan["channels"]
        )
        print(f"  {plan['cohort_name']}:")
        print(f"    {channels_str}")
        print(f"    Weighted effectiveness: {plan['weighted_effectiveness']:.3f}x")
    print()

    print("FORECAST:")
    _div()
    print(f"  Target uplift (from objective):   {_money(forecast['target_uplift'], parsed_obj, 2)}")
    print(f"  Projected uplift (risk-adjusted): {_money(forecast['risk_adjusted_uplift'], parsed_obj, 2)}")
    print()
    print(f"  ╔{'═' * 50}╗")
    verdict_pad = " " * ((50 - len(forecast['verdict']) - 4) // 2)
    print(f"  ║  {verdict_pad}{forecast['verdict']}{verdict_pad}  ║")
    print(f"  ╚{'═' * 50}╝")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # ── 0. Parse input file from CLI args (default to Okhiya) ────────────────
    if len(sys.argv) > 1:
        input_filename = sys.argv[1]
    else:
        input_filename = "AMOS_Okhiya_Mock_Data_Input.xlsx"

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print(f"\nLoading {input_filename} ...")
    try:
        data = load_all_data(input_filename)
    except FileNotFoundError:
        print(f"[ERROR] {input_filename} not found in current directory.")
        sys.exit(1)

    api_key = load_api_key()
    if api_key:
        print("[Claude API: connected]")
    else:
        print("[Claude API: no key found — using templated fallback for Agent 3]")

    # ── 2. Agent 1 — Objective Intake ─────────────────────────────────────────
    raw = input("\nEnter business objective: ").strip()
    parsed_obj = agent1_objective_intake(raw, data["biz"])
    print_agent1_output(parsed_obj)

    # ── 3. Agent 2 — Context & Strategy ──────────────────────────────────────
    strategy = agent2_context_strategy(parsed_obj, data)
    print_agent2_output(strategy)

    # ══ HUMAN CHECKPOINT ══════════════════════════════════════════════════════
    input("\n  ► Press Enter to approve strategic direction and continue...\n")
    # ══════════════════════════════════════════════════════════════════════════

    # ── 4. Agent 3 — Creative Director (Claude API) ───────────────────────────
    creative_briefs = agent3_creative_director(
        strategy["strategic_direction"],
        data["brand"],
        data["cohorts"],
        data["biz"],
        api_key,
    )
    print_agent3_output(creative_briefs)

    # ── 5. Agent 4 — Media Planner ────────────────────────────────────────────
    media_plans = agent4_media_planner(
        strategy["strategic_direction"],
        data["channels"],
        data["cohorts"],
        data["assumptions"],
    )
    print_agent4_output(media_plans)

    # ── 6. Agent 5 — Impact Forecaster ───────────────────────────────────────
    forecast = agent5_forecaster(
        creative_briefs,
        media_plans,
        data["assumptions"],
        parsed_obj,
        data["cohorts"],
    )
    print_agent5_output(forecast, parsed_obj, input_filename)

    # ── 7. Final Campaign Brief ───────────────────────────────────────────────
    print_campaign_brief(parsed_obj, strategy, creative_briefs, media_plans, forecast)


if __name__ == "__main__":
    main()
