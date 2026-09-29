# Statistical contract

Read before planning, analyzing, or interpreting a verdict. The calculations in
`scripts/statistics_core.py` are not a substitute for a valid experiment.

## Units and metrics

- Primary: orders / impressions. Secondary: clicks / impressions (CTR),
  cart events / clicks, and orders / clicks. Report denominators explicitly.
- Inputs must be **binary outcomes on independent units**, attributed to the
  same variant and window. Units sold, repeated cart actions, and order lines
  are not binary successes. Counts satisfying `successes <= trials` alone do
  not establish this contract.
- Repeated impressions from one person can be correlated. Randomizing users
  while analyzing unadjusted impression totals can understate uncertainty.
  Require verified independent-unit aggregation or a separate cluster-aware
  analysis; do not claim this script corrects clustering.
- Baseline is 14–30 days. Never substitute missing values with zero or infer
  variant orders by allocating SKU-wide orders according to clicks.

## Planning and stopping

- MDE is relative: `0.10` means +10%, not +10 percentage points. Baseline and
  baseline × (1 + MDE) must lie strictly between zero and one.
- `sample_size` uses the normal approximation for independent proportions,
  two-sided alpha 0.05 and power 0.8. With control A and treatment B, let
  `r = n_B / n_A`, `p_bar = (p_A + r*p_B)/(1+r)`. Then
  `n_A = [z_(1-alpha/2)*sqrt(p_bar*(1-p_bar)*(1+1/r)) +
  z_power*sqrt(p_A*(1-p_A)+p_B*(1-p_B)/r)]² / (p_B-p_A)²`.
- For two challengers use alpha / 2 for each control comparison (Bonferroni).
  Respect the predeclared allocation; take the largest required total across
  comparisons and round each arm up. Also require at least ten expected
  successes and failures per arm. This is approximate planning, not exact power.
- Calculate CTR and orders/impressions requirements separately; use the larger
  per-arm target. CTR power does not establish power to detect order uplift.
- Fix dates, allocation, MDE, exclusions, and outcomes before launch. At least
  seven complete days; the CLI rounds randomized horizons to whole weeks.
  Keep price, advertising, and availability stable and avoid promotions.
- No early efficacy decisions or optional extension after observing results.
  A low-traffic completed experiment is inconclusive; plan a **new** experiment
  with its full required sample, not merely the old sample deficit. Interim
  figures are descriptive/quality checks, never permission to stop on significance.

## Inference actually implemented

- Each rate gets a Wilson score 95% interval, including zero/all-success cases.
- The two-proportion z-test is two-sided with pooled variance. It declines
  inference if either arm has fewer than ten successes or ten failures.
- Relative uplift is `p_B/p_A - 1`. Its conservative approximate interval uses
  two Wilson intervals at confidence `1 - alpha/2`, then `[L_B/U_A-1,
  U_B/L_A-1]`. Alpha is already Bonferroni-adjusted across challengers. These
  intervals are deliberately wider and are **not exact-coverage** intervals.
- If the observed control has zero successes, relative uplift and its interval
  are undefined. Show absolute rates; never invent a percentage uplift.
- Bayesian P(B>A) uses independent Beta(1,1) priors and posterior shapes
  `(successes+1, trials-successes+1)`. A seeded 200,000-draw Monte Carlo estimate
  includes simulation standard error and a Wilson Monte Carlo interval.
  All draws agreeing gives estimated 0 or 1, **not certainty**: show MC bounds.
  MC error is numerical uncertainty, not a replacement for posterior uncertainty.
- Practical equivalence requires the entire adjusted uplift interval within
  the predeclared ±MDE and a usable normal test. `p > .05` does **not** establish
  equivalence. Explain “разницы нет” as no practically important difference
  within that margin, never mathematical equality.

## Validity gates

- SRM uses Pearson chi-square goodness-of-fit against the **predeclared**
  randomized allocation, threshold 0.001. Expected counts must each be ≥5;
  otherwise SRM is unassessable, not passed.
- SRM needs counts of assignment units corresponding to the allocation. Raw
  repeated impressions are not automatically assignment counts. The CLI uses
  the `impressions` column, so it is applicable only when its units satisfy
  that requirement. Otherwise obtain suitable aggregation; do not run a causal
  verdict from this export. SRM failure invalidates inference; more traffic is
  not a repair. Sequential tests do not have a randomized SRM interpretation.
- Advertising, price, or out-of-stock flags block a causal verdict. Investigate
  and restart cleanly; never delete inconvenient days after seeing their results.
- Mark the first three calendar days as novelty without excluding them from
  the primary analysis. Novelty labels do not correct bias or seasonal effects.
- Sequential whole-week alternation balances weekdays, not confounders. Treat
  it as exploratory and require randomized confirmation, regardless of p-values.

## Verdict and multi-arm scope

Only valid, complete, sufficiently sampled randomized tests can establish a
winner or equivalence. Winner requires significant z-test and an uplift interval
strictly on the winning side of zero. Bayesian probability is supporting context,
not a second route around validity or fixed-horizon gates.

The current plan preregisters challenger-versus-control comparisons only. With
two challengers it can establish that control beats both, or that both are
practically equivalent to control. It does not establish a unique challenger
winner by ranking their observed rates; use a new head-to-head confirmation.
Equivalence to control does not imply challenger-to-challenger equivalence.

An invalid or inconclusive experiment belongs to “недостаточно данных” with a
clear reason. Supply remaining N/M only when mathematically meaningful and
authorized by the fixed plan; otherwise say a new correctly designed test is
needed. Do not fabricate a finite number of additional observations guaranteed
to resolve an observed ambiguity.

## Primary references (checked 2026-09-29)

- [NIST: Wilson score intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
- [NIST: normal-approximation sample-size derivation](https://www.itl.nist.gov/div898/handbook/prc/section2/prc242.htm)
  (one-proportion derivation; the two-arm variance formula is stated above).
- [SciPy: Pearson goodness-of-fit and assumptions](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chisquare.html).
- [SciPy: beta distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.beta.html).
