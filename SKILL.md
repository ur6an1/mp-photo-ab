---
name: mp-photo-ab
description: >-
  Generate reference-based main-photo candidates for marketplace sellers, plan controlled experiments, and analyze daily results honestly. Trigger for главное фото, A/B-тест, карточка WB/Ozon, CTR, инфографика, or interpreting photo-test exports. Do not trigger for unrelated design, product invention, ad-budget management, full listing SEO, or automatic seller-account changes.
---

# Marketplace photo experiments

Use English for code and technical artifacts; speak Russian, informal «ты», in all seller-facing questions, hypotheses, prompts shown to sellers, plans and reports. Translate technical errors before presenting them.
Do not invent missing inputs, current marketplace rules, costs or test conclusions. Paid generation and marketplace publication are separate actions; this skill never changes seller accounts.

## Routing

Identify the current phase and reuse its experiment folder. Load only the references needed now. Read `experiments/learnings.md` for this category before drafting hypotheses; preserve failed and inconclusive experiments.

### 1. Brief

Read [experiment-contract.md](references/experiment-contract.md). Ask for category, SKU, audience, 1–3 verified USPs, price segment, current main photo and mandatory real product reference(s). Competitor screenshots are optional (3–5); request baseline impressions/clicks/cart/orders for 14–30 days. Ask only for what is missing; unknown baseline is null, not zero.
Store with `scripts/experiment.py brief --input brief-input.json --root experiments --date YYYY-MM-DD`, producing `experiments/SKU/YYYY-MM-DD/brief.json`. Keep experiments outside the installed skill. CLI paths in brief resolve relative to its input JSON.

### 2. Hypotheses

Read [seller-playbook.md](references/seller-playbook.md) and the relevant marketplace section of [marketplace-image-rules.md](references/marketplace-image-rules.md).
Draft 4–6 hypotheses in Russian, exactly one changed variable each, with category/competitor rationale, target metric, ICE 1–5 and both compliance and product-truth risks. Treat playbook claims as hypotheses.
Validate/rank using `scripts/experiment.py hypotheses --experiment EXP --input hypotheses-input.json`. Select control + 1–2 challengers; native WB allows only one challenger. A selected hypothesis gets multiple candidates but only one approved candidate becomes an arm.

### 3. Generate and inspect

Read [image-providers.md](references/image-providers.md). Run `scripts/generate.py --experiment EXP --dry-run` first; it prints prompts without API calls, keys or spending. Recipes live in [recipes.json](assets/prompt-recipes/recipes.json).
Use image-edit/reference with real SKU photos, never text-only product invention. Keep color, shape, logo and included items unchanged; alter only the selected background/composition/light/infographic/badge variable. Keep useful control context; do not send competitors as product references.
Actual generation needs explicit seller authorization and `--run`, a sourced full-batch cost estimate and budget (see `--help`). CLI flag is not authorization by itself. Do not retry an uncertain paid request automatically.
Generate 2–3 candidates for each selected hypothesis. Inspect every candidate against real references; reject product drift, invented copy or extra changed variables. No automatic identity guarantee.
Run `scripts/thumbnail_preview.py --control FILE --variants FILE... --competitors FILE... --output FILE`; omit competitors if absent. Review the two-column 180 px tiles with the seller before selecting candidates.
Use verified marketplace rules, sRGB and the same export treatment for control/challengers. Ozon rule gaps require current official evidence or seller-provided cabinet requirements before claiming upload readiness.

### 4. Plan

Read [statistics.md](references/statistics.md), the contract and platform A/B availability. Verify availability in this seller's cabinet; do not infer it from another account or third-party automation.
Freeze settings with `scripts/experiment.py plan --experiment EXP --settings settings.json --start YYYY-MM-DD`. It writes immutable `plan.json` plus seller-facing `plan.md`.
Compute CTR and orders/impressions sample needs at alpha .05, power .8, relative MDE and actual test traffic; use the larger target. Require at least 7 full days, rounded to whole weeks. Do not launch into promotions/holidays; hold price, advertising and stock stable.
Native test unavailable: plan explicit whole-week alternating periods, label low credibility, and never turn temporal comparisons into a causal winner. SRM applies to randomized assignment counts only, not arbitrary sequential traffic.
Clarify the counting unit/attribution. Repeated buyer impressions or multi-order counts can invalidate a binomial test. Without compatible variant-specific outcomes, report the limitation instead of allocating aggregate orders proportionally.

### 5. Analyze

Accept CSV/XLSX or manually recorded daily rows using the contract. Map seller export columns explicitly; never guess funnel denominators. Orders/cart may not be available by arm in a platform export: ask, do not fabricate.
Run `scripts/experiment.py analyze --experiment EXP --input daily.csv --as-of YYYY-MM-DD`. The as-of day is excluded as incomplete. Wait for order attribution to mature before final analysis.
Report CTR, cart/clicks, orders/clicks and primary orders/impressions; Wilson 95% intervals, two-proportion z-test, Beta(1,1) posterior P(B>A), relative uplift interval and SRM. Bayes is supplementary, not an alternative threshold to fish for a winner.
Mark the first 3 days novelty without dropping them. Flag advertising/price changes and out-of-stock; no retrospective cherry-picking. Check fixed horizon and required per-arm sample before decisions; do not repeatedly peek to stop early.
Use exactly three verdict classes: winner with uplift/CI, practical equivalence («разницы нет»), or insufficient evidence. Invalid tests belong to insufficient evidence with cause; N/M is undefined when more traffic cannot repair the design. A completed inconclusive test requires a new preplanned experiment, not indefinite optional stopping.

### 6. Report and learn

Run `scripts/experiment.py report --experiment EXP --next-test 'Одна следующая проверяемая гипотеза'`. Uses [report-template.md](assets/report-template.md), writes `report.md` and appends a deduplicated category finding to `experiments/learnings.md`.
Keep the sequence: hypothesis → treatment → numbers → verdict → implement/rollback/continue → next test. For invalid or inconclusive results, «продолжить» means repair/replan research, not keep a contaminated test running.
Never claim a universal category pattern from one SKU. Reports recommend an action; they do not execute it.

## Execution and checks

Python 3.11+, dependencies in `requirements.txt`; use an isolated virtual environment. Entrypoints expose `--help`; exits: 0 successful processing (not necessarily winner), 2 bad input, 3 blocked inference/external failure. Helpers are imported, not separate CLI commands.
Run `python -m unittest discover -s tests -v` from this skill directory. Samples are synthetic; [brief.json](assets/samples/brief.json) requires your real image paths. Never use its illustrative metrics as a seller baseline.
Validate skill packaging with the installed `skill-creator/scripts/quick_validate.py`. Mock generation does not prove a live provider call; disclose that distinction.
