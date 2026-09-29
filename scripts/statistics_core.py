"""Binomial fixed-horizon calculations; callers must validate experimental design.

Counts must represent independent binary outcomes, not units sold or repeated
events. These functions do not establish randomization or causal identification.
"""
from __future__ import annotations

import math
from numbers import Integral
from typing import Sequence

import numpy as np
from scipy.stats import chisquare, norm


def _count(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{label}: требуется целое неотрицательное число")
    return int(value)


def _binomial(successes: int, trials: int) -> tuple[int, int]:
    successes, trials = _count(successes, "События"), _count(trials, "Показы")
    if trials < 1 or successes > trials:
        raise ValueError("Нужен положительный знаменатель и не больше одного события на наблюдение")
    return successes, trials


def _prob(value: float, label: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f"{label}: требуется число строго между 0 и 1")
    return float(value)


def _allocation(allocation: Sequence[float], arms: int) -> np.ndarray:
    result = np.asarray(allocation, dtype=float)
    if result.shape != (arms,) or not np.all(np.isfinite(result)) or np.any(result <= 0):
        raise ValueError("Доли трафика должны быть положительными числами для всех вариантов")
    if not math.isclose(float(result.sum()), 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("Сумма заявленных долей трафика должна равняться 1")
    return result / result.sum()


def sample_size(baseline: float, relative_mde: float, alpha: float = .05,
                power: float = .8, arms: int = 2,
                allocation: Sequence[float] | None = None) -> dict:
    """Normal-approximation planning for each treatment versus one control.

    MDE is a relative increase (0.1 means +10%). Familywise alpha uses
    Bonferroni for 1 or 2 comparisons. Arbitrary positive allocation is allowed.
    Expected successes/failures are also constrained to at least ten per arm.
    """
    baseline, alpha, power = (_prob(baseline, "Базовая конверсия"),
                              _prob(alpha, "Alpha"), _prob(power, "Мощность"))
    if power <= .5 or arms not in (2, 3) or isinstance(arms, bool):
        raise ValueError("Нужны мощность выше 0.5 и 2–3 группы")
    if not math.isfinite(relative_mde) or relative_mde <= 0:
        raise ValueError("Относительный MDE должен быть положительным")
    target = baseline * (1 + relative_mde)
    if target >= 1:
        raise ValueError("Базовая конверсия с MDE должна быть меньше 1")
    shares = _allocation(allocation if allocation is not None else [1 / arms] * arms, arms)
    adjusted = alpha / (arms - 1)
    za, zb = norm.isf(adjusted / 2), norm.ppf(power)
    totals = []
    for share in shares[1:]:
        ratio = share / shares[0]
        pooled = (baseline + ratio * target) / (1 + ratio)
        null_var = pooled * (1 - pooled) * (1 + 1 / ratio)
        alt_var = baseline * (1 - baseline) + target * (1 - target) / ratio
        control_n = ((za * math.sqrt(null_var) + zb * math.sqrt(alt_var)) /
                     (target - baseline)) ** 2
        totals.append(control_n / shares[0])
    probabilities = [baseline] + [target] * (arms - 1)
    totals.extend(10 / (min(p, 1 - p) * share) for p, share in zip(probabilities, shares))
    target_total = math.ceil(max(totals))
    per_arm = [math.ceil(target_total * float(share)) for share in shares]
    return {"per_arm": per_arm, "total": sum(per_arm), "allocation": shares.tolist(),
            "alpha_per_comparison": adjusted, "alpha": alpha, "power": power,
            "baseline": baseline, "relative_mde": relative_mde,
            "method": "normal_approximation_bonferroni"}


def wilson_interval(successes: int, trials: int, confidence: float = .95) -> tuple[float, float]:
    """Wilson score confidence interval, including zero/all successes."""
    successes, trials = _binomial(successes, trials)
    confidence = _prob(confidence, "Уровень доверия")
    z = float(norm.isf((1 - confidence) / 2))
    p, z2 = successes / trials, z * z
    denominator = 1 + z2 / trials
    center = (p + z2 / (2 * trials)) / denominator
    radius = z * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials**2)) / denominator
    return max(0., center - radius), min(1., center + radius)


def two_proportion_z(control_successes: int, control_trials: int,
                     variant_successes: int, variant_trials: int,
                     alpha: float = .05) -> dict:
    """Two-sided pooled z test; decline normal inference on sparse observations."""
    a, na = _binomial(control_successes, control_trials)
    b, nb = _binomial(variant_successes, variant_trials)
    alpha = _prob(alpha, "Alpha")
    if min(a, na - a, b, nb - b) < 10:
        return {"valid": False, "z": None, "p_value": None, "significant": False,
                "reason": "Для z-теста нужно минимум 10 событий и 10 несобытий в каждой группе"}
    pooled = (a + b) / (na + nb)
    z = (b / nb - a / na) / math.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb))
    p_value = float(2 * norm.sf(abs(z)))
    return {"valid": True, "z": z, "p_value": p_value,
            "significant": p_value < alpha, "reason": None}


def posterior_probability(control_successes: int, control_trials: int,
                          variant_successes: int, variant_trials: int,
                          draws: int = 200_000, seed: int = 42) -> dict:
    """Seeded Monte Carlo P(p_variant > p_control), independent Beta(1,1) priors.

    MC uncertainty is reported separately; it is not inferential uncertainty.
    Wilson bounds avoid reporting perfect certainty when all draws agree.
    """
    a, na = _binomial(control_successes, control_trials)
    b, nb = _binomial(variant_successes, variant_trials)
    draws = _count(draws, "Число симуляций")
    if draws < 10_000 or draws > 5_000_000:
        raise ValueError("Число симуляций должно быть от 10000 до 5000000")
    seed = _count(seed, "Seed")
    rng = np.random.default_rng(seed)
    wins = int(np.count_nonzero(rng.beta(b + 1, nb - b + 1, draws) >
                                rng.beta(a + 1, na - a + 1, draws)))
    probability = wins / draws
    return {"probability": probability,
            "mc_standard_error": math.sqrt(probability * (1 - probability) / draws),
            "mc_interval": list(wilson_interval(wins, draws)), "draws": draws,
            "seed": seed, "prior": "Beta(1,1)", "method": "seeded_monte_carlo"}


def srm(observed: Sequence[int], allocation: Sequence[float], alpha: float = .001) -> dict:
    """Pearson goodness-of-fit SRM against predeclared randomized allocation."""
    if len(observed) not in (2, 3):
        raise ValueError("SRM ожидает 2–3 группы")
    counts = np.array([_count(x, "Трафик") for x in observed], dtype=float)
    shares = _allocation(allocation, len(observed))
    alpha = _prob(alpha, "Alpha SRM")
    expected = counts.sum() * shares
    if np.any(expected < 5):
        return {"valid": False, "mismatch": None, "p_value": None,
                "reason": "Недостаточно трафика для проверки SRM"}
    statistic, p_value = chisquare(counts, f_exp=expected)
    return {"valid": True, "mismatch": bool(p_value < alpha),
            "p_value": float(p_value), "statistic": float(statistic),
            "alpha": alpha, "expected": expected.tolist(), "reason": None}


def relative_uplift_interval(control_successes: int, control_trials: int,
                             variant_successes: int, variant_trials: int,
                             alpha: float = .05) -> dict:
    """Conservative ratio bounds using Bonferroni-paired Wilson intervals.

    Uses two (1-alpha/2) marginal Wilson intervals and their endpoint ratios.
    Coverage is approximate, as for Wilson itself. Zero observed control means
    relative uplift is undefined: report absolute rates, never invent a ratio.
    """
    a, na = _binomial(control_successes, control_trials)
    b, nb = _binomial(variant_successes, variant_trials)
    alpha = _prob(alpha, "Alpha")
    if a == 0:
        return {"uplift": None, "ci": None, "reason": "При нуле событий в контроле относительный uplift не определён"}
    la, ua = wilson_interval(a, na, 1 - alpha / 2)
    lb, ub = wilson_interval(b, nb, 1 - alpha / 2)
    return {"uplift": (b / nb) / (a / na) - 1,
            "ci": [lb / ua - 1, ub / la - 1], "reason": None,
            "method": "bonferroni_wilson_ratio", "confidence": 1 - alpha}


def compare_proportions(control_successes: int, control_trials: int,
                        variant_successes: int, variant_trials: int,
                        relative_mde: float, alpha: float = .05) -> dict:
    """Combine descriptive/inferential outputs, without deciding test validity.

    Caller supplies familywise-adjusted alpha and checks design, horizon, SRM,
    sample targets, anomalies, and independent binary data before any verdict.
    """
    if not math.isfinite(relative_mde) or relative_mde <= 0:
        raise ValueError("Относительный MDE должен быть положительным")
    args = (control_successes, control_trials, variant_successes, variant_trials)
    z = two_proportion_z(*args, alpha=alpha)
    uplift = relative_uplift_interval(*args, alpha=alpha)
    ci = uplift["ci"]
    return {"control_rate": control_successes / control_trials,
            "variant_rate": variant_successes / variant_trials,
            "control_ci": list(wilson_interval(control_successes, control_trials)),
            "variant_ci": list(wilson_interval(variant_successes, variant_trials)),
            "z_test": z, "bayesian": posterior_probability(*args), "relative_uplift": uplift,
            "equivalent": bool(z["valid"] and ci is not None and
                               ci[0] > -relative_mde and ci[1] < relative_mde)}
