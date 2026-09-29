# Experiment contract and commands

Use Python 3.11+ with `requirements.txt` in an isolated environment. CLI scripts: `experiment.py`, `generate.py`, `thumbnail_preview.py`. Other Python files are import-only helpers. All examples below run locally; no account upload or paid generation is implied.

## Artifacts and immutability

Put data in a working directory outside the installed skill: `experiments/<sku>/<YYYY-MM-DD>/`.
`brief.json`, `hypotheses.json`, `plan.json` and `plan.md` are write-once. `plan.json` is the machine-readable preregistration paired with `plan.md`, including hashes of brief/hypotheses. Do not manually change a live test. A new design requires a new experiment date/folder; intermediate QA analyses may use `--output` without making a winner decision.
`analysis.json`, `report.md` and `daily-metrics.csv` are output artifacts. `generation.json` exists only for an actual paid batch; dry-run prints JSON without writing anything. An interrupted paid batch is not automatically retried.
Each analysis also stores an immutable `ANALYSIS_NAME-data.csv` snapshot bound by `data_hash`. Reports verify it. Interim `--output` analyses do not populate the final `daily-metrics.csv`; conflicting final data are never silently reused or overwritten.
Source photos must remain available at their normalized absolute paths; preserve original controls and chosen variants. A file hash is not proof that a plan was registered before exposure; keep the plan before launching in the cabinet.

## Brief JSON

Required fields: `sku` (path-safe identifier), `marketplace` (`Wildberries` or `Ozon`), `category`, `audience`, `usps` (1–3 verified Russian strings), `price_segment`, `current_image`, `reference_images` (nonempty real SKU photos), `competitor_images` ([] or 3–5 files), `baseline`.
Paths in an input brief are relative to that JSON file or absolute; saved paths are absolute. Do not place keys or personal buyer data in a brief.
Baseline is either null (unknown: brief can be saved, planning cannot proceed) or `{days, impressions, clicks, cart, orders}` for 14–30 complete days. Counts must be actual matching funnel events. A zero-event baseline cannot support a relative-MDE plan; collect a pilot rather than invent a rate.
The [sample](../assets/samples/brief.json) is illustrative, not live seller data. Replace both image paths with real files before using it. The end-to-end test creates synthetic images in an isolated temporary directory; no fake product reference is shipped as a seller asset.

## Hypothesis JSON

A list of 4–6 objects:

```json
{"id":"B","variable":"background","change":"Светло-серый фон вместо белого; остальное без изменений","rationale":"Гипотеза из playbook: проверить отделение товара от фона; конкуренты ещё не предоставлены","target_metric":"ctr","ice":{"impact":3,"confidence":2,"ease":5},"risks":["Фон может не соответствовать категории площадки","Генерация может исказить цвет товара"],"selected":true}
```

`variable`: exactly one of `background`, `composition`, `light`, `infographic`, `badge`. The agent must inspect the natural-language change and actual pixels; an enum cannot prove only one variable changed.
`target_metric`: `ctr`, `cart_per_click`, `orders_per_click`, `orders_per_impression`. The hypothesis may target CTR, but the experiment decision remains orders/impressions. ICE ranking uses the arithmetic mean. Select 1–2 hypotheses, native WB exactly one. A candidate is not a separate hypothesis/arm.

## Plan settings

These confirmations are supplied only after discussing/checking their substance with the seller; never auto-fill true to pass validation.

```json
{
  "mode": "randomized",
  "daily_impressions": 10000,
  "allocation": [0.5, 0.5],
  "mde_ctr": 0.15,
  "mde_orders": 0.30,
  "stability_confirmed": true,
  "non_promo_confirmed": true,
  "product_review_confirmed": true,
  "metrics_contract_confirmed": true,
  "independent_units_confirmed": true,
  "srm_assignment_units_confirmed": true,
  "native_test_confirmed": true,
  "native_test_evidence": "Учебный пример; замени фактическим подтверждением из своего кабинета"
}
```

MDE is relative: 0.15 means +15%, not +15 percentage points. Daily traffic is the total traffic that enters this test, not all SKU impressions (native WB may use a visitor subset). Allocation order is control, then selected hypotheses in ranked order; verify `plan.json`.
`srm_assignment_units_confirmed` means impressions correspond to randomized assignment units, not repeated post-assignment exposures. If not, request actual assignment counts and a compatible design; this CLI cannot establish SRM from the incompatible export.
`mode: sequential` uses whole-week blocks in variant order, repeated equally, and does not require native-test/independence confirmations. It cannot establish a causal winner with binomial tests. SRM is not applied to its temporal traffic.
If the required horizon exceeds a platform limit, do not silently stitch restarted experiments. Reconsider MDE/traffic or use an eligible design. Dates need promotion/holiday checks and a full-day launch.

## Daily input: CSV, XLSX or manual rows

Required header:

```csv
date,variant,impressions,clicks,cart,orders,advertising_changed,out_of_stock,price_changed
2026-09-01,control,5000,500,160,50,false,false,false
2026-09-01,B,5000,550,170,60,false,false,false
```

Use ISO dates, integer counts, `control` or the selected hypothesis id, explicit `true/false` (or 1/0) flags. A manually entered table is saved with this same header. CSV is UTF-8 with comma delimiter; XLSX reads the first sheet, no formulas. Export mappings must be confirmed before normalization; incompatible headers produce an error rather than an inferred mapping.
CTR = clicks/impressions; cart CR = cart/clicks; order CR = orders/clicks; primary = orders/impressions. Counts are binary events on compatible attributed units, not quantities sold. Orders may bypass cart; `orders <= cart` is not assumed. Clicks <= impressions; cart and orders <= clicks. If a vendor defines them differently, do not force the data into this model.
In a randomized test include every variant for every full day, even zero-traffic rows. In a sequential test include only the scheduled variant for each day. Duplicate rows, unknown variants, partial/future days, missing days, blank counts/flags and negative counts are rejected. Do not invent zeros for missing exports.
Wait for attribution to mature. Never distribute aggregate SKU orders/cart among variants by traffic share; request a compatible export or report that the primary outcome is unavailable.

## Local command sequence

```bash
python scripts/experiment.py brief --input /work/brief-input.json --root /work/experiments --date 2026-09-29
python scripts/experiment.py hypotheses --experiment /work/experiments/DEMO-001/2026-09-29 --input /work/hypotheses-input.json
python scripts/generate.py --experiment /work/experiments/DEMO-001/2026-09-29 --dry-run
python scripts/thumbnail_preview.py --control /work/control.jpg --variants /work/candidate.jpg --output /work/preview.jpg
python scripts/experiment.py plan --experiment /work/experiments/DEMO-001/2026-09-29 --settings /work/settings.json --start 2026-10-05
python scripts/experiment.py analyze --experiment /work/experiments/DEMO-001/2026-09-29 --input /work/daily.csv --as-of 2026-11-01
python scripts/experiment.py report --experiment /work/experiments/DEMO-001/2026-09-29 --next-test 'Проверить масштаб товара, сохранив фон'
```

Illustrative paths/dates only; use the actual fixed horizon from your plan. The as-of date itself is excluded. `analyze` exit 3 means blocked inference, but its JSON can still produce an honest report. An inconclusive valid result exits 0: successful analysis is not the same as a winner. Errors exit 2; failed/uncertain generation exits 3. Existing output files are not silently overwritten.
`report` appends a deduplicated summary to the experiment root's `learnings.md`. «Продолжить» on a blocked/completed inconclusive experiment means a repaired new design, not optional prolongation. Keep the counterexample and limitations in category history.
