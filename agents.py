# agents.py
# All 5 agent functions for the AMOS campaign planning pipeline.
# Brand-agnostic: reads brand context, cohorts, and channels from the input file.
# Agent 3 calls the Claude API (claude-sonnet-4-5); Agents 1, 2, 4, 5 are deterministic.

import re
import json

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("[WARNING] 'anthropic' package not installed. Run: pip install anthropic")
    print("[WARNING] Agent 3 will use templated fallback routes.")

from data_loader import parse_pct, parse_currency


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — OBJECTIVE INTAKE
# ═══════════════════════════════════════════════════════════════════════════════

def agent1_objective_intake(raw_input: str, biz: dict) -> dict:
    """Parse user objective string. Falls back to biz sheet values when not parseable.
    Brand-agnostic: finds campaign-period revenue and budget by flexible label match."""

    # Extract target growth % from the raw input string
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', raw_input)
    if m:
        target_growth_pct = float(m.group(1))
    else:
        # Fall back to biz sheet value
        fallback = parse_pct(biz.get('Baseline campaign conversion lift (%)'))
        target_growth_pct = (fallback * 100) if fallback else 40.0

    brand_name = str(biz.get('Brand name', 'Unknown')).strip()
    timeframe  = str(biz.get('Target timeframe', '')).strip()
    currency   = str(biz.get('Currency', 'USD ($)')).strip()

    # Currency symbol + unit for display formatting
    currency_symbol, currency_unit = _parse_currency_field(currency)

    # Campaign-period revenue: match any biz key containing "period revenue" or "season revenue"
    # Examples: "Total Diwali-period revenue (₹ Cr)", "Total Fall-season revenue ($M)"
    current_period_revenue = 0.0
    for key, val in biz.items():
        key_lower = str(key).lower()
        if ('period revenue' in key_lower or 'season revenue' in key_lower):
            parsed = parse_currency(val)
            if parsed:
                current_period_revenue = parsed
                break

    # Baseline growth from biz sheet "Current YoY growth baseline" — extract the %
    baseline_raw = str(biz.get('Current YoY growth baseline', '15%'))
    bm = re.search(r'(\d+(?:\.\d+)?)\s*%', baseline_raw)
    baseline_growth_pct = float(bm.group(1)) if bm else 15.0

    target_uplift = current_period_revenue * (target_growth_pct / 100.0)

    return {
        "raw_objective":            raw_input,
        "brand_name":               brand_name,
        "target_growth_pct":        target_growth_pct,
        "timeframe":                timeframe,
        "baseline_growth_pct":      baseline_growth_pct,
        "current_period_revenue":   current_period_revenue,
        "target_uplift":            target_uplift,
        "currency_symbol":          currency_symbol,
        "currency_unit":            currency_unit,
    }


def _parse_currency_field(currency_str: str) -> tuple:
    """Parse Currency biz field into (symbol, unit) tuple.
    'USD ($)' → ('$', 'M').  'INR (₹)' → ('₹', 'Cr').  Default: ('$', 'M')."""
    s = currency_str.upper()
    if 'INR' in s or '₹' in currency_str:
        return ('₹', 'Cr')
    return ('$', 'M')


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — CONTEXT & STRATEGY
# ═══════════════════════════════════════════════════════════════════════════════

def agent2_context_strategy(parsed_obj: dict, data: dict) -> dict:
    """Load all context sheets. Apply composite scoring. Label and rank cohorts."""

    cohorts    = data["cohorts"]
    brand_name = parsed_obj.get("brand_name", "the brand")

    growth_score_map    = {"Low": 1, "Medium": 2, "High": 3}
    intensity_score_map = {"Low": 3, "Medium": 2, "High": 1}  # inverted: lower fight = higher score

    strategic_direction = []
    for cohort in cohorts:
        rev_pct   = cohort.get("revenue_pct") or 0.0
        growth    = cohort.get("growth_potential", "Medium")
        intensity = cohort.get("competitive_intensity", "Medium")

        contribution_score = rev_pct * 100
        g_score = growth_score_map.get(growth, 2)
        i_score = intensity_score_map.get(intensity, 2)
        # Weights: revenue contribution (60%), competitive position (10×), growth ceiling (13×).
        composite = contribution_score * 0.6 + g_score * 13 + i_score * 10

        # DEFEND: dominant revenue share + near-saturation growth
        if rev_pct >= 0.40 and growth == "Low":
            label = "DEFEND"
            reasoning = (
                f"Largest revenue block ({rev_pct * 100:.1f}%) with Low growth potential — "
                f"this cohort is near saturation. {intensity} competitive intensity means "
                f"{brand_name} has a strong position here. Protect the base; don't over-invest "
                f"for marginal gains."
            )
        else:
            label = "INVEST FOR GROWTH"
            reasoning = (
                f"{rev_pct * 100:.1f}% revenue share with {growth} growth potential and "
                f"{intensity} competitive intensity. There is room to grow this cohort — "
                f"invest in acquisition and conversion to expand its contribution."
            )

        strategic_direction.append({
            "cohort_name":     cohort["cohort_name"],
            "rank":            0,          # assigned after sort
            "label":           label,
            "composite_score": round(composite, 1),
            "reasoning":       reasoning,
            "insight_quoted":  cohort.get("insight", ""),
        })

    # Sort: DEFEND cohorts first (protect the base), then INVEST cohorts by revenue_pct descending.
    def _sort_key(sd):
        cohort = next((c for c in cohorts if c["cohort_name"] == sd["cohort_name"]), {})
        defend_priority = 0 if sd["label"] == "DEFEND" else 1
        revenue = -(cohort.get("revenue_pct") or 0)  # negate for descending
        return (defend_priority, revenue)

    strategic_direction.sort(key=_sort_key)
    for i, sd in enumerate(strategic_direction):
        sd["rank"] = i + 1

    return {
        "business_context":     data["biz"],
        "cohorts":              data["cohorts"],
        "brand_guidelines":     data["brand"],
        "industry_trends":      data["trends"],
        "historic_sales":       data["historic"],
        "competitive_landscape": data["competitors"],
        "strategic_direction":  strategic_direction,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — CREATIVE DIRECTOR  (Claude API)
# ═══════════════════════════════════════════════════════════════════════════════

def agent3_creative_director(
    strategic_direction: list, brand: dict, cohorts: list, biz: dict, api_key: str
) -> list:
    """2 creative routes per cohort via Claude API (claude-sonnet-4-5).
    Falls back to templated routes if key missing or calls fail.
    Never crashes — the demo always completes end-to-end."""

    cohort_lookup    = {c["cohort_name"]: c for c in cohorts}
    brand_name       = str(biz.get("Brand name", "the brand")).strip()
    brand_sys_prompt = _build_brand_system_prompt(brand, brand_name)

    results             = []
    total_calls         = 0
    total_input_tokens  = 0
    total_output_tokens = 0

    for sd in strategic_direction:
        cohort_name = sd["cohort_name"]
        label       = sd["label"]
        cohort_data = cohort_lookup.get(cohort_name, {})

        if api_key and ANTHROPIC_AVAILABLE:
            routes, calls_made, in_tok, out_tok = _call_claude_api(
                api_key, brand_sys_prompt, sd, cohort_data
            )
            total_calls         += calls_made
            total_input_tokens  += in_tok
            total_output_tokens += out_tok
        else:
            routes      = _templated_routes(label, cohort_data, brand)
            calls_made  = 0
            in_tok      = 0
            out_tok     = 0

        results.append({
            "cohort_name":    cohort_name,
            "label":          label,
            "api_calls_made": calls_made,
            "in_tokens":      in_tok,
            "out_tokens":     out_tok,
            "routes":         routes,
        })

    # Store run totals for the print function to display at the end of Agent 3's section
    results.append({
        "_totals": True,
        "total_calls":        total_calls,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
    })

    return results


def _build_brand_system_prompt(brand: dict, brand_name: str = "the brand") -> str:
    tone      = brand.get("Tone of voice", "")
    dos       = brand.get("Messaging do's", "")
    donts     = brand.get("Messaging don'ts", "")
    vocab     = brand.get("Approved vocabulary", "")
    banned    = brand.get("Off-limits vocabulary", "")
    archetype = brand.get("Brand archetype", "")
    promise   = brand.get("Core promise", "")

    return (
        f"You are the creative director for {brand_name}.\n"
        f"BRAND ESSENCE: {promise}\n\n"
        f"BRAND ARCHETYPE: {archetype}\n"
        f"TONE OF VOICE: {tone}\n\n"
        f"MESSAGING DOs: {dos}\n"
        f"MESSAGING DON'Ts: {donts}\n\n"
        f"APPROVED VOCABULARY (use freely): {vocab}\n"
        f"OFF-LIMITS WORDS (never appear in output): {banned}\n\n"
        f"You must respond ONLY with valid JSON. No markdown fences, no preamble, "
        f"no explanation outside the JSON object."
    )


def _build_cohort_prompt(sd: dict, cohort_data: dict) -> str:
    return (
        f"Create exactly 2 creative routes for the following customer cohort.\n\n"
        f"COHORT: {sd['cohort_name']}\n"
        f"CAMPAIGN STRATEGY: {sd['label']}\n"
        f"CUSTOMER INSIGHT: {sd['insight_quoted']}\n"
        f"PRODUCT PREFERENCE: {cohort_data.get('product_preference', 'N/A')}\n"
        f"STRATEGIC REASONING: {sd['reasoning']}\n\n"
        f"Each route must have:\n"
        f"- name: a short memorable campaign route name (3-5 words)\n"
        f"- concept: one sentence — the campaign idea\n"
        f"- rationale: 2-3 sentences — why this works for this specific cohort\n"
        f"- vocab_used: list of 2-4 approved vocabulary words used\n"
        f"- off_limits_check: \"passed\" (confirm no off-limits words appear)\n\n"
        f"Respond with ONLY this JSON structure:\n"
        f'{{"routes": [{{"name": "...", "concept": "...", "rationale": "...", '
        f'"vocab_used": ["...", "..."], "off_limits_check": "passed"}}, '
        f'{{"name": "...", "concept": "...", "rationale": "...", '
        f'"vocab_used": ["...", "..."], "off_limits_check": "passed"}}]}}'
    )


def _call_claude_api(api_key: str, system_prompt: str, sd: dict, cohort_data: dict):
    """Call Claude API once for one cohort. Returns (routes, calls_made, in_tokens, out_tokens).
    Retries once on JSON parse failure. Falls back gracefully on API errors."""
    client        = anthropic.Anthropic(api_key=api_key)
    cohort_prompt = _build_cohort_prompt(sd, cohort_data)
    cohort_name   = sd["cohort_name"]

    for attempt in range(2):
        try:
            prompt = cohort_prompt
            if attempt == 1:
                prompt += "\n\nCRITICAL: Respond with ONLY valid JSON. No markdown, no backticks, no extra text."

            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=600,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text   = response.content[0].text.strip()
            in_tokens  = response.usage.input_tokens
            out_tokens = response.usage.output_tokens

            # Strip markdown fences if the model added them anyway
            raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r'\s*```$', '', raw_text)

            parsed = json.loads(raw_text)
            routes = []
            for r in parsed.get("routes", []):
                vocab = r.get("vocab_used", [])
                routes.append({
                    "route_name":      r.get("name", "Unnamed Route"),
                    "concept":         r.get("concept", ""),
                    "rationale":       r.get("rationale", ""),
                    "vocab_used":      vocab,
                    "compliance_note": (
                        f"Uses: {', '.join(vocab)}. "
                        f"Off-limits check: {r.get('off_limits_check', 'passed')}."
                    ),
                })

            return routes, 1, in_tokens, out_tokens

        except json.JSONDecodeError:
            if attempt == 0:
                continue  # retry with tighter instruction
            print(f"  [WARNING] JSON parse failed for {cohort_name} after retry — using fallback]")
            return _templated_routes(sd["label"], cohort_data, {}), 1, 0, 0

        except Exception as e:
            err_type = type(e).__name__
            print(f"  [WARNING] {err_type} for {cohort_name}: {e} — using fallback]")
            return _templated_routes(sd["label"], cohort_data, {}), 0, 0, 0

    return _templated_routes(sd["label"], cohort_data, {}), 0, 0, 0


def _templated_routes(label: str, cohort_data: dict, brand: dict) -> list:
    """Deterministic fallback routes. Clearly labelled [TEMPLATED FALLBACK].
    Brand-neutral concepts that lean on whatever Approved Vocabulary the brand
    provides. The real creative work happens via the Claude API path; this is
    a graceful failure mode so the demo always completes end-to-end."""
    insight    = cohort_data.get("insight", "")
    insight_snippet = insight[:80] + "..." if len(insight) > 80 else insight

    vocab_raw   = brand.get("Approved vocabulary", "heritage, craft, tradition, occasion")
    vocab_words = [w.strip() for w in str(vocab_raw).split(",")][:2]

    if label == "DEFEND":
        return [
            {
                "route_name":      "[TEMPLATED FALLBACK] The Loyalty Spotlight",
                "concept":         "Celebrate the customers who keep coming back, and the craft they keep choosing.",
                "rationale":       (
                    f"{insight_snippet} This route reinforces the existing relationship "
                    f"by spotlighting brand provenance and the loyalty already in place. "
                    f"Deepens trust without urgency framing."
                ),
                "vocab_used":      vocab_words,
                "compliance_note": "Templated fallback, no API call made.",
            },
            {
                "route_name":      "[TEMPLATED FALLBACK] The Continuing Story",
                "concept":         "Position each repeat purchase as a continuation of a story already underway.",
                "rationale":       (
                    "Speaks to the occasion-wear ritual of existing loyalists. "
                    "Reinforces purchase cadence through narrative and identity, "
                    "not discount or scarcity."
                ),
                "vocab_used":      vocab_words,
                "compliance_note": "Templated fallback, no API call made.",
            },
        ]
    else:  # INVEST FOR GROWTH
        return [
            {
                "route_name":      "[TEMPLATED FALLBACK] The First Encounter",
                "concept":         "Introduce the brand through the craft and care that defines it.",
                "rationale":       (
                    f"{insight_snippet} Acquisition-angled route that lowers the entry "
                    f"barrier through credibility cues. Positions the brand as the "
                    f"natural first choice for the occasion."
                ),
                "vocab_used":      vocab_words,
                "compliance_note": "Templated fallback, no API call made.",
            },
            {
                "route_name":      "[TEMPLATED FALLBACK] Roots and Reach",
                "concept":         "Bridge what the customer already values with what the brand offers.",
                "rationale":       (
                    "Bridges the cohort's existing values with brand proposition. "
                    "Resonates with cohorts seeking expression without rigidity. "
                    "Anchors in craft, not trend."
                ),
                "vocab_used":      vocab_words,
                "compliance_note": "Templated fallback, no API call made.",
            },
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — MEDIA PLANNER
# ═══════════════════════════════════════════════════════════════════════════════

def agent4_media_planner(
    strategic_direction: list, channels: list, cohorts: list, assumptions: dict
) -> list:
    """Pick 2–3 best-fit channels per cohort. Allocate budget proportional to
    effectiveness multiplier. Budget per cohort always sums to 100%.
    Computes absolute budget per cohort and per channel from the media pool."""

    # Media pool = total budget × media share (from Assumptions sheet)
    total_budget = assumptions["total_campaign_budget"]["value"]
    media_share  = assumptions.get("media_budget_share", {}).get("value", 0.70)
    media_pool   = total_budget * media_share       # e.g. 6 × 0.70 = 4.2 ($M) or 50 × 0.70 = 35 (Cr)

    # Rank → cohort media allocation %
    cohort_rank_alloc = {1: 0.40, 2: 0.35, 3: 0.15, 4: 0.10}

    # Channel name → full channel dict (for cost_per_customer_reached lookup)
    channel_lookup = {ch["channel_name"]: ch for ch in channels}

    results = []

    for sd in strategic_direction:
        cohort_name = sd["cohort_name"]

        # Filter channels that list this cohort as best-fit
        matching = [
            ch for ch in channels
            if _cohort_matches(cohort_name, ch.get("best_fit_cohort", ""))
            and ch.get("effectiveness_multiplier") is not None
        ]

        # Sort by effectiveness descending, take top 3
        matching.sort(key=lambda c: c["effectiveness_multiplier"], reverse=True)
        selected = matching[:3]

        # Fallback: if fewer than 2 channels match, use top channels globally
        if len(selected) < 2:
            fallback = sorted(
                [c for c in channels if c.get("effectiveness_multiplier") is not None],
                key=lambda c: c["effectiveness_multiplier"],
                reverse=True,
            )
            selected = fallback[:3]

        # Budget allocation: proportional to effectiveness multiplier
        budget_alloc = _allocate_budget(selected)

        # Absolute cohort media budget
        rank          = sd["rank"]
        cohort_media  = media_pool * cohort_rank_alloc.get(rank, 0.10)

        channel_results = []
        for ch, pct in zip(selected, budget_alloc):
            raw_ch = channel_lookup.get(ch["channel_name"], {})
            channel_results.append({
                "channel_name":              ch["channel_name"],
                "reasoning":                 _channel_reasoning(ch, cohort_name, sd["label"]),
                "budget_pct":                pct,
                "effectiveness_multiplier":  ch["effectiveness_multiplier"],
                "measurability":             ch.get("measurability", "N/A"),
                "channel_budget":            round(cohort_media * pct / 100, 3),
                "cost_per_customer_reached": raw_ch.get("cost_per_customer_reached"),
            })

        weighted_eff = sum(
            ch["effectiveness_multiplier"] * (pct / 100)
            for ch, pct in zip(selected, budget_alloc)
        )

        results.append({
            "cohort_name":            cohort_name,
            "label":                  sd["label"],
            "rank":                   rank,
            "channels":               channel_results,
            "weighted_effectiveness": round(weighted_eff, 3),
            "cohort_media_budget":    round(cohort_media, 3),
            "media_pool":             round(media_pool, 3),
        })

    return results


def _cohort_matches(cohort_name: str, best_fit: str) -> bool:
    """True if cohort_name appears (substring) in any comma-separated entry of best_fit."""
    if not best_fit:
        return False
    # Remove parenthetical qualifiers like '(metro)'
    clean_fit    = re.sub(r'\s*\([^)]*\)', '', best_fit)
    clean_cohort = re.sub(r'\s*\([^)]*\)', '', cohort_name)
    parts = [p.strip() for p in clean_fit.split(',')]
    return any(
        clean_cohort.lower() in p.lower() or p.lower() in clean_cohort.lower()
        for p in parts
    )


def _allocate_budget(channels: list) -> list:
    """Proportional to effectiveness multiplier. Returns list of ints summing to 100."""
    if not channels:
        return []
    effs  = [ch["effectiveness_multiplier"] for ch in channels]
    total = sum(effs)
    raw   = [e / total * 100 for e in effs]
    rounded = [int(r) for r in raw]
    remainder = 100 - sum(rounded)
    if remainder != 0:
        # Add remainder to the channel with the largest fractional part
        fractions = [(r - int(r), i) for i, r in enumerate(raw)]
        fractions.sort(reverse=True)
        for _, idx in fractions[:abs(remainder)]:
            rounded[idx] += (1 if remainder > 0 else -1)
    return rounded


def _channel_reasoning(ch: dict, cohort_name: str, label: str) -> str:
    eff   = ch.get("effectiveness_multiplier", 1.0)
    meas  = ch.get("measurability", "")
    conv  = ch.get("conversion_lift", "")
    return (
        f"Effectiveness {eff:.2f}x ({meas} attribution). "
        f"Expected lift: {conv}. "
        f"Strong fit for {cohort_name} ({label} strategy)."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — IMPACT FORECASTER
# ═══════════════════════════════════════════════════════════════════════════════

def agent5_forecaster(
    creative_briefs: list,
    media_plans: list,
    assumptions: dict,
    parsed_obj: dict,
    cohorts: list,
) -> dict:
    """Calculate uplift per cohort using assumptions from the xlsx.
    Formula: Cohort Size × Reachable Share × AOV × Conversion Lift × Channel Effectiveness.
    Applies risk adjustment; compares to target; emits verdict.

    Currency-aware: budgets are in major units (₹ Cr or $M); CPC and AOV are in
    minor units (₹ or $). The conversion factor (10M for INR Cr, 1M for USD M) is
    derived from the Currency field on the Business Context sheet."""

    # Filter out the _totals sentinel that agent3 appends to its return list
    creative_briefs = [b for b in creative_briefs if not b.get("_totals")]

    cohort_lookup = {c["cohort_name"]: c for c in cohorts}
    media_lookup  = {m["cohort_name"]: m for m in media_plans}

    # Pull assumption values (all live from xlsx via assumptions dict)
    conv_lift   = assumptions["baseline_conversion_lift_expected"]["value"]
    risk_adj    = assumptions["risk_adjustment"]["value"]

    # Currency conversion factor: budget unit → CPC/AOV unit
    # INR Cr → ₹ : 10,000,000 (one crore = 10 million)
    # USD $M → $ : 1,000,000 (one million = 1 million)
    currency_unit = parsed_obj.get("currency_unit", "M")
    if currency_unit == "Cr":
        unit_factor = 10_000_000  # 1 crore = 10 million rupees
    else:
        unit_factor = 1_000_000   # 1 million = 1 million dollars

    # Build cohort reach assumption lookup dynamically.
    # The data_loader normalizes any cohort name to a snake_case key like
    # 'reach_classic_repeat'. We do the same here to match.
    def _reach_key_for(cohort_name: str) -> str:
        norm = re.sub(r'[^a-z0-9]+', '_', cohort_name.lower()).strip('_')
        return f"reach_{norm}"

    cohort_forecasts = []
    for brief in creative_briefs:
        cohort_name = brief["cohort_name"]
        cohort      = cohort_lookup.get(cohort_name, {})
        media       = media_lookup.get(cohort_name, {})

        cohort_size  = cohort.get("size") or 0
        aov          = cohort.get("aov") or 0
        weighted_eff = media.get("weighted_effectiveness", 1.0)

        # Reachable share from assumptions (kept for reference display, not used in math)
        reach_key       = _reach_key_for(cohort_name)
        reachable_share = (
            assumptions[reach_key]["value"]
            if reach_key in assumptions
            else 0.70
        )

        # BUDGET-DRIVEN REACH (replaces assumption-based reach)
        # Step 1: per-channel reach = channel_budget × unit_factor ÷ cost_per_customer_reached
        channel_reach_breakdown = []
        sum_raw_reach = 0
        for ch in media.get("channels", []):
            budget = ch.get("channel_budget", 0) or 0
            cpc    = ch.get("cost_per_customer_reached") or None
            if cpc and cpc > 0:
                ch_reach = int(budget * unit_factor / cpc)
            else:
                ch_reach = 0
            sum_raw_reach += ch_reach
            channel_reach_breakdown.append({
                "channel_name":  ch["channel_name"],
                "budget":        budget,
                "budget_pct":    ch.get("budget_pct", 0),
                "cpc":           cpc,
                "channel_reach": ch_reach,
            })

        # Step 2: 20% de-duplication haircut (cross-channel overlap)
        deduped_reach = int(sum_raw_reach * 0.80)

        # Step 3: cap at cohort size
        final_reach = min(deduped_reach, cohort_size)

        # Step 4: label constraint
        if deduped_reach >= cohort_size:
            reach_pct   = 100.0
            reach_label = (
                f"COHORT-LIMITED: can reach 100% of cohort — "
                f"budget exceeds what's needed"
            )
        else:
            reach_pct   = deduped_reach / cohort_size * 100 if cohort_size else 0
            reach_label = (
                f"BUDGET-LIMITED: reaching {reach_pct:.0f}% of cohort — "
                f"need more media budget to go further"
            )

        # Uplift formula: reach × AOV × conversion lift × channel effectiveness
        # Result is in minor units (₹ or $); convert to major units (Cr or M)
        uplift_minor = final_reach * aov * conv_lift * weighted_eff
        uplift_major = uplift_minor / unit_factor

        cohort_forecasts.append({
            "cohort_name":             cohort_name,
            "rank":                    media.get("rank", "?"),
            "cohort_size":             cohort_size,
            "reachable_share":         reachable_share,
            "cohort_media_budget":     media.get("cohort_media_budget", 0),
            "media_pool":              media.get("media_pool", 0),
            "channel_reach_breakdown": channel_reach_breakdown,
            "sum_raw_reach":           sum_raw_reach,
            "deduped_reach":           deduped_reach,
            "final_reach":             final_reach,
            "reach_label":             reach_label,
            "reach_pct":               reach_pct,
            "aov":                     int(aov),
            "conversion_lift":         conv_lift,
            "weighted_eff":            weighted_eff,
            "uplift":                  round(uplift_major, 2),
        })

    total_uplift     = sum(cf["uplift"] for cf in cohort_forecasts)
    risk_adjusted    = total_uplift * (1 + risk_adj)
    target_uplift    = parsed_obj["target_uplift"]
    gap_pct          = (risk_adjusted - target_uplift) / target_uplift * 100 if target_uplift else 0

    verdict = (
        f"ON TRACK WITH {gap_pct:.1f}% BUFFER"
        if gap_pct >= 0
        else f"SHORT BY {abs(gap_pct):.1f}%"
    )

    return {
        "assumptions_used":     assumptions,
        "cohort_forecasts":     cohort_forecasts,
        "total_uplift":         round(total_uplift, 2),
        "risk_adjusted_uplift": round(risk_adjusted, 2),
        "target_uplift":        round(target_uplift, 2),
        "gap_pct":              round(gap_pct, 1),
        "verdict":              verdict,
    }
