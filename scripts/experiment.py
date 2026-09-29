#!/usr/bin/env python3
"""Local six-phase experiment CLI; no seller-account mutations."""
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
from datetime import date, timedelta
from pathlib import Path

from data_io import (COUNTS, FLAGS, InputError, finite_number, fingerprint,
                     iso_date, load_json, read_daily, validate_brief,
                     validate_hypotheses, write_json, write_text)
from statistics_core import (compare_proportions, sample_size, srm, wilson_interval)

SKILL = Path(__file__).resolve().parents[1]


def experiment_inputs(folder: Path):
    brief = validate_brief(load_json(folder / "brief.json"), folder)
    hypotheses = validate_hypotheses(load_json(folder / "hypotheses.json"))
    return brief, hypotheses


def brief_command(args):
    brief = validate_brief(load_json(args.input), args.input.resolve().parent)
    day = iso_date(args.date).isoformat()
    folder = args.root.expanduser().resolve() / brief["sku"] / day
    if folder.exists():
        raise InputError("Эксперимент с этим артикулом и датой уже существует; не перезаписываю.")
    folder.mkdir(parents=True)
    write_json(folder / "brief.json", brief)
    print(f"Бриф сохранён: {folder / 'brief.json'}")
    if brief["baseline"] is None:
        print("Для плана нужны показы, клики, корзины и заказы за 14–30 дней; отсутствующие данные не заменены нулями.")


def hypotheses_command(args):
    if (args.experiment / "plan.json").exists():
        raise InputError("План уже зафиксирован; гипотезы в нём менять нельзя.")
    brief = validate_brief(load_json(args.experiment / "brief.json"), args.experiment)
    items = validate_hypotheses(load_json(args.input))
    write_json(args.experiment / "hypotheses.json", items)
    print("Гипотезы ранжированы по среднему ICE. Контроль — текущее главное фото.")
    if brief["marketplace"] == "Wildberries" and sum(x["selected"] for x in items) > 1:
        print("Для встроенного теста WB оставь только один выбранный вариант; два допустимы лишь в другом подтверждённом дизайне.")


def build_plan(brief: dict, hypotheses: list[dict], settings: dict, start: date) -> dict:
    if not isinstance(settings, dict):
        raise InputError("Настройки плана должны быть JSON-объектом.")
    baseline = brief["baseline"]
    if not baseline or baseline["impressions"] == 0 or baseline["clicks"] == 0 or baseline["orders"] == 0:
        raise InputError("Для мощности CTR и заказов нужен ненулевой baseline. Собери данные; выдумывать конверсию нельзя.")
    selected = [x["id"] for x in hypotheses if x["selected"]]
    variants = ["control", *selected]
    mode = settings.get("mode")
    if mode not in {"randomized", "sequential"}:
        raise InputError("mode: randomized или sequential.")
    for field, message in {
        "stability_confirmed": "Подтверди фиксацию цены, рекламы и наличие остатков.",
        "non_promo_confirmed": "Проверь даты: нельзя начинать в акцию или праздник.",
        "product_review_confirmed": "Сначала проверь сохранность товара и читаемость кандидата на 180 px.",
        "metrics_contract_confirmed": "Подтверди одинаковую атрибуцию и бинарные события на вариант, не агрегат всего SKU.",
    }.items():
        if settings.get(field) is not True:
            raise InputError(message)
    if mode == "randomized":
        if settings.get("native_test_confirmed") is not True or not str(settings.get("native_test_evidence", "")).strip():
            raise InputError("Подтверди наличие рандомизированного теста в своём кабинете и укажи источник подтверждения.")
        if settings.get("independent_units_confirmed") is not True:
            raise InputError("Для z-test нужны независимые единицы: повторные показы одному покупателю могут занизить неопределённость.")
        if settings.get("srm_assignment_units_confirmed") is not True:
            raise InputError("Подтверди, что показы соответствуют единицам рандомизации; иначе SRM по показам некорректен.")
        if brief["marketplace"] == "Wildberries" and len(selected) != 1:
            raise InputError("Встроенный A/B WB: контроль + один вариант.")
    daily = finite_number(settings.get("daily_impressions"), "Суточный трафик именно теста", 1, 10**12)
    mde_ctr = finite_number(settings.get("mde_ctr"), "Относительный MDE CTR", .0001, .99)
    mde_orders = finite_number(settings.get("mde_orders"), "Относительный MDE заказов", .0001, .99)
    allocation = settings.get("allocation", [1 / len(variants)] * len(variants))
    n_ctr = sample_size(baseline["clicks"] / baseline["impressions"], mde_ctr,
                        arms=len(variants), allocation=allocation)
    n_orders = sample_size(baseline["orders"] / baseline["impressions"], mde_orders,
                           arms=len(variants), allocation=allocation)
    per_arm = [max(a, b) for a, b in zip(n_ctr["per_arm"], n_orders["per_arm"])]
    if mode == "randomized":
        days = max(7, math.ceil(max(n / (daily * share) for n, share in zip(per_arm, allocation))))
        days = math.ceil(days / 7) * 7
    else:
        # Whole-week alternating periods balance weekdays, not unobserved confounding.
        if any(abs(x - 1 / len(variants)) > 1e-8 for x in allocation):
            raise InputError("Для последовательного дизайна используй равные доли недельных периодов.")
        cycles = max(1, math.ceil(max(per_arm) / (7 * daily)))
        days = cycles * len(variants) * 7
    if days > 3660:
        raise InputError("Расчёт превышает 10 лет: измени MDE или выбери товар с достаточным трафиком.")
    try:
        end = start + timedelta(days=days - 1)
    except OverflowError as exc:
        raise InputError("Дата окончания вне допустимого календарного диапазона.") from exc
    return {
        "schema_version": 1, "mode": mode, "variants": variants,
        "allocation": allocation, "start": start.isoformat(), "end": end.isoformat(),
        "days": days, "daily_impressions": daily, "primary_metric": "orders_per_impression",
        "mde_ctr": mde_ctr, "mde_orders": mde_orders, "alpha": .05, "power": .8,
        "alpha_per_comparison": .05 / (len(variants) - 1), "srm_alpha": .001,
        "novelty_days": 3, "sample_ctr": n_ctr, "sample_orders": n_orders,
        "per_arm_target": per_arm, "settings": settings,
        "brief_hash": fingerprint(brief), "hypotheses_hash": fingerprint(hypotheses),
        "limitations": (["Последовательный тест не доказывает причинный эффект; SRM неприменим."]
                        if mode == "sequential" else []),
    }


def render_plan(plan: dict) -> str:
    targets = "\n".join(f"- {v}: минимум {n:,} показов".replace(",", " ")
                        for v, n in zip(plan["variants"], plan["per_arm_target"]))
    mode = "Рандомизированный" if plan["mode"] == "randomized" else "Последовательный — низкая достоверность"
    schedule = "Одновременно; доли: " + ", ".join(f"{v} {p:.1%}" for v, p in zip(plan["variants"], plan["allocation"]))
    if plan["mode"] == "sequential":
        schedule = "Чередуй целые недели: " + " → ".join(plan["variants"]) + "; повторяй цикл до даты окончания."
    warning = "\n".join(plan["limitations"]) or "Проверь фактический сплит и независимость единиц в кабинете."
    return (SKILL / "assets/plan-template.md").read_text().format(
        start=plan["start"], end=plan["end"], days=plan["days"], mode=mode,
        targets=targets, schedule=schedule, warning=warning,
        mde_ctr=f"{plan['mde_ctr']:.1%}", mde_orders=f"{plan['mde_orders']:.1%}")


def plan_command(args):
    brief, hypotheses = experiment_inputs(args.experiment)
    plan = build_plan(brief, hypotheses, load_json(args.settings), iso_date(args.start))
    if any((args.experiment / name).exists() for name in ("plan.json", "plan.md")):
        raise InputError("План уже зафиксирован. Новый дизайн — новый эксперимент.")
    write_json(args.experiment / "plan.json", plan)
    write_text(args.experiment / "plan.md", render_plan(plan))
    print(f"План: {plan['start']} — {plan['end']}; {plan['days']} полных дней. См. plan.md.")
    if plan["mode"] == "randomized" and brief["marketplace"] == "Wildberries" and plan["days"] > 56:
        print("Срок близок к лимиту WB или превышает его: проверь лимит в кабинете; не объединяй перезапущенные тесты как один.")


def rates(counts: dict) -> dict:
    output = {}
    for name, numerator, denominator in (
        ("ctr", "clicks", "impressions"), ("cart_per_click", "cart", "clicks"),
        ("orders_per_click", "orders", "clicks"), ("orders_per_impression", "orders", "impressions"),
    ):
        n = counts[denominator]
        output[name] = {"rate": counts[numerator] / n if n else None,
                        "ci95": list(wilson_interval(counts[numerator], n)) if n else None}
    return output


def analyze_data(plan: dict, rows: list[dict], as_of: date) -> dict:
    variants = plan["variants"]
    start, end = iso_date(plan["start"]), iso_date(plan["end"])
    last_full = min(end, as_of - timedelta(days=1))
    if last_full < start:
        raise InputError("Ещё нет ни одного полного дня теста.")
    expected = set()
    for offset in range((last_full - start).days + 1):
        day = (start + timedelta(days=offset)).isoformat()
        active = variants if plan["mode"] == "randomized" else [variants[(offset // 7) % len(variants)]]
        expected.update((day, v) for v in active)
    actual = {(row["date"], row["variant"]) for row in rows}
    if expected != actual:
        raise InputError("Дни/варианты не совпадают с планом: нужны все полные дни, включая нулевые строки; без будущих и лишних дат.")
    totals = {v: dict.fromkeys(COUNTS, 0) for v in variants}
    anomalies, novelty = [], []
    for row in rows:
        for key in COUNTS:
            totals[row["variant"]][key] += row[key]
        flags = [key for key in FLAGS if row[key]]
        if flags:
            anomalies.append({"date": row["date"], "variant": row["variant"], "flags": flags})
        if (iso_date(row["date"]) - start).days < plan["novelty_days"]:
            novelty.append({"date": row["date"], "variant": row["variant"]})
    observed = [totals[v]["impressions"] for v in variants]
    split = srm(observed, plan["allocation"], alpha=plan["srm_alpha"]) if plan["mode"] == "randomized" else None
    blockers = []
    if plan["mode"] != "randomized":
        blockers.append("Последовательное чередование не отделяет эффект фото от времени и внешних факторов; нужен рандомизированный тест.")
    if split is not None and (not split["valid"] or split["mismatch"]):
        blockers.append("SRM: сплит не прошёл проверку; тест невалиден, простое продолжение не исправляет причину.")
    if anomalies:
        blockers.append("Есть изменения рекламы/цены или отсутствие остатков; дни не удалены задним числом, нужен разбор и новый чистый тест.")
    comparisons = {}
    control = totals["control"]
    for variant in variants[1:]:
        counts = totals[variant]
        if control["impressions"] and counts["impressions"]:
            comparisons[variant] = compare_proportions(
                control["orders"], control["impressions"], counts["orders"], counts["impressions"],
                relative_mde=plan["mde_orders"], alpha=plan["alpha_per_comparison"])
    remaining = [max(0, target - count) for target, count in zip(plan["per_arm_target"], observed)]
    completed_days = (last_full - start).days + 1
    more_days = max(0, plan["days"] - completed_days)
    if any(remaining):
        more_days = max(more_days, math.ceil(max(n / (plan["daily_impressions"] * p)
                                               for n, p in zip(remaining, plan["allocation"]))))
    horizon_complete = last_full == end
    enough = not any(remaining)
    result = {
        "schema_version": 1, "plan_hash": fingerprint(plan), "data_hash": fingerprint(rows),
        "as_of": as_of.isoformat(), "last_full_day": last_full.isoformat(),
        "totals": totals, "metrics": {v: rates(totals[v]) for v in variants},
        "comparisons": comparisons, "srm": split, "anomalies": anomalies, "novelty": novelty,
        "blockers": blockers, "horizon_complete": horizon_complete,
        "remaining_impressions": sum(remaining), "remaining_days": more_days,
        "verdict_type": "insufficient", "decision": "продолжить", "winner": None,
        "method_note": "Основная метрика — заказы/показы; интервалы и тесты требуют независимых бинарных наблюдений.",
    }
    if blockers:
        result.update(remaining_impressions=None, remaining_days=None,
                      verdict="недостаточно данных — тест невалиден для причинного вывода; нужен новый корректный тест")
        return result
    if not horizon_complete:
        result["verdict"] = f"недостаточно данных — нужно ещё {sum(remaining)} показов / {more_days} дней"
        return result
    if not enough:
        result.update(verdict="недостаточно данных — нужен новый тест с полной заново рассчитанной выборкой",
                      remaining_impressions=None, remaining_days=None)
        result["blockers"].append("Фиксированный срок закончился. Не продлевай его после просмотра результата; новый тест планируй отдельно.")
        return result
    # A unique winner must beat EVERY rival, not merely the common control.
    # Multi-arm ties require a fresh head-to-head experiment, not post-hoc ranking.
    winner = None
    winner_comparison = None
    if len(variants) == 2 and comparisons:
        item = comparisons[variants[1]]
        interval = item["relative_uplift"]["ci"]
        if item["z_test"]["valid"] and item["z_test"]["significant"] and interval and interval[0] > 0:
            winner, winner_comparison = variants[1], item
        elif item["z_test"]["valid"] and item["z_test"]["significant"] and interval and interval[1] < 0:
            b = totals[variants[1]]
            reverse = compare_proportions(b["orders"], b["impressions"], control["orders"], control["impressions"],
                                          relative_mde=plan["mde_orders"], alpha=plan["alpha_per_comparison"])
            if reverse["relative_uplift"]["ci"]:
                winner, winner_comparison = "control", reverse
    elif len(variants) == 3 and len(comparisons) == 2:
        # Only a control superior to both challengers is identifiable without an
        # additional pre-registered challenger-vs-challenger comparison.
        if all(x["z_test"]["valid"] and x["z_test"]["significant"] and
               x["relative_uplift"]["ci"] and x["relative_uplift"]["ci"][1] < 0
               for x in comparisons.values()):
            best = max(variants[1:], key=lambda v: totals[v]["orders"] / totals[v]["impressions"])
            b = totals[best]
            reverse = compare_proportions(b["orders"], b["impressions"], control["orders"], control["impressions"],
                                          relative_mde=plan["mde_orders"], alpha=plan["alpha_per_comparison"])
            if reverse["relative_uplift"]["ci"]:
                winner, winner_comparison = "control", reverse
    if winner:
        uplift = winner_comparison["relative_uplift"]
        low, high = uplift["ci"]
        result.update(verdict_type="winner", winner=winner,
                      decision="откатить" if winner == "control" else "внедрить",
                      verdict=f"победитель {winner}, uplift {uplift['uplift']:+.1%} [{low:+.1%}; {high:+.1%}]",
                      winner_comparison=winner_comparison)
    elif len(comparisons) == len(variants) - 1 and all(x["equivalent"] for x in comparisons.values()):
        result.update(verdict_type="equivalent", verdict="разницы нет", decision="откатить")
        result["method_note"] += f" Практическая эквивалентность к контролю в пределах ±{plan['mde_orders']:.1%}, не математическое равенство."
    else:
        result.update(verdict="недостаточно данных — нужен новый тест с заранее выбранными MDE и сроком",
                      remaining_impressions=None, remaining_days=None)
    return result


def analyze_command(args):
    brief, hypotheses = experiment_inputs(args.experiment)
    plan = load_json(args.experiment / "plan.json")
    if fingerprint(brief) != plan["brief_hash"] or fingerprint(hypotheses) != plan["hypotheses_hash"]:
        raise InputError("После планирования изменены бриф или гипотезы; анализ остановлен.")
    rows = read_daily(args.input)
    result = analyze_data(plan, rows, iso_date(args.as_of))
    output = args.output or args.experiment / "analysis.json"
    snapshot = output.with_name(output.stem + "-data.csv")
    if output.exists() or snapshot.exists():
        raise InputError("Анализ или его снимок данных уже существует; выбери новый путь --output.")
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["date", "variant", *COUNTS, *FLAGS])
    writer.writeheader()
    writer.writerows(rows)
    result["data_file"] = str(snapshot.resolve())
    normalized = args.experiment / "daily-metrics.csv"
    if args.output is None and normalized.exists() and fingerprint(read_daily(normalized)) != result["data_hash"]:
        raise InputError("Сохранённые daily-metrics.csv отличаются от входа; используй отдельный --output для новой версии анализа.")
    write_text(snapshot, stream.getvalue())
    write_json(output, result)
    if args.output is None and not normalized.exists():
        write_text(normalized, stream.getvalue())
    print(result["verdict"])
    for message in result["blockers"]:
        print(message)
    return 3 if result["blockers"] else 0


def percent(value):
    return "нет данных" if value is None else f"{value:.2%}"


def report_command(args):
    brief, hypotheses = experiment_inputs(args.experiment)
    plan = load_json(args.experiment / "plan.json")
    analysis = load_json(args.analysis or args.experiment / "analysis.json")
    if analysis["plan_hash"] != fingerprint(plan) or fingerprint(brief) != plan["brief_hash"] or fingerprint(hypotheses) != plan["hypotheses_hash"]:
        raise InputError("Отчёт не соответствует зафиксированному плану и брифу.")
    if fingerprint(read_daily(Path(analysis["data_file"]))) != analysis["data_hash"]:
        raise InputError("Снимок данных изменился после анализа; отчёт остановлен.")
    lines = ["| Вариант | Показы | Клики | Корзины | Заказы | CTR | Корзина/клики | Заказы/клики | Заказы/показы |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for variant in plan["variants"]:
        counts, metrics = analysis["totals"][variant], analysis["metrics"][variant]
        lines.append("| " + " | ".join([variant, *(str(counts[k]) for k in COUNTS),
                     *(percent(metrics[k]["rate"]) for k in ("ctr", "cart_per_click", "orders_per_click", "orders_per_impression"))]) + " |")
    evidence = []
    for variant, item in analysis["comparisons"].items():
        p = item["z_test"]["p_value"]
        bayes = item["bayesian"]
        evidence.append(f"- {variant} против контроля: z-test p={p if p is not None else 'неприменим'}; "
                        f"P(B>A)≈{bayes['probability']:.6f}; prior Beta(1,1), погрешность MC={bayes['mc_standard_error']:.3g}; "
                        f"интервал вычислительной погрешности [{bayes['mc_interval'][0]:.8f}; {bayes['mc_interval'][1]:.8f}]. "
                        "Округлённые 0/1 не означают абсолютную уверенность.")
    for variant in plan["variants"]:
        metric = analysis["metrics"][variant]["orders_per_impression"]
        ci = metric["ci95"]
        evidence.append(f"- {variant}, Wilson 95% для заказов/показов: " + (f"[{percent(ci[0])}; {percent(ci[1])}]." if ci else "нет данных."))
    evidence.append("- Интервал uplift: консервативное отношение Wilson-интервалов; для двух сравнений учтена поправка Bonferroni.")
    if analysis["srm"] is not None:
        evidence.append(f"- SRM: p={analysis['srm']['p_value']}; порог 0.001.")
    else:
        evidence.append("- SRM неприменим: последовательное чередование периодов.")
    tested = "\n".join(f"- {x['id']}: {x['change']}. Обоснование: {x['rationale']}" for x in hypotheses if x["selected"])
    limitations = analysis["blockers"] + [analysis["method_note"],
        "Первые 3 дня помечены novelty, но включены в основной анализ; исключение задним числом не выполнялось.",
        "Внедрение или откат — рекомендация; кабинет площадки не изменён."]
    content = (SKILL / "assets/report-template.md").read_text().format(
        sku=brief["sku"], hypothesis=tested, dates=f"{plan['start']} — {analysis['last_full_day']}",
        metrics="\n".join(lines), statistics="\n".join(evidence), verdict=analysis["verdict"],
        decision=analysis["decision"], limitations="\n".join(f"- {x}" for x in limitations), next_test=args.next_test)
    write_text(args.output or args.experiment / "report.md", content)
    root = args.experiment.resolve().parent.parent
    if root == SKILL or SKILL in root.parents:
        raise InputError("Историю экспериментов храни вне установленного скилла.")
    learnings = root / "learnings.md"
    if learnings.is_symlink():
        raise InputError("История не должна быть символической ссылкой.")
    existing = learnings.read_text() if learnings.exists() else (SKILL / "assets/learnings-template.md").read_text()
    marker = f"<!-- experiment:{fingerprint({'path': str(args.experiment.resolve()), 'data': analysis['data_hash']})} -->"
    if marker not in existing:
        evidence_level = "валидный рандомизированный тест" if analysis["verdict_type"] != "insufficient" else "гипотеза; причинный вывод не подтверждён"
        entry = f"\n{marker}\n## {brief['category']} · {brief['sku']} · {plan['start']}\n\n{tested}\n\n- Уровень: {evidence_level}.\n- Результат: {analysis['verdict']}.\n- Следующий тест: {args.next_test}\n- Не переносить на другие категории без проверки.\n"
        write_text(learnings, existing + entry, replace=learnings.exists())
    print("Отчёт и история категории сохранены. Кабинет площадки не изменён.")


class SellerParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Ошибка аргументов. Проверь команду через --help.\n")


def main(argv=None):
    parser = SellerParser(description="Фото WB/Ozon: бриф, гипотезы, план, анализ и отчёт. Генерация: generate.py; превью: thumbnail_preview.py.")
    commands = parser.add_subparsers(dest="command", required=True)
    brief = commands.add_parser("brief", help="Сохранить подтверждённый бриф")
    brief.add_argument("--input", type=Path, required=True, help="JSON брифа")
    brief.add_argument("--root", type=Path, default=Path("experiments"), help="Папка экспериментов вне скилла")
    brief.add_argument("--date", default=date.today().isoformat(), help="Дата папки ГГГГ-ММ-ДД")
    brief.set_defaults(func=brief_command)
    hypotheses = commands.add_parser("hypotheses", help="Проверить и ранжировать 4–6 гипотез")
    hypotheses.add_argument("--input", type=Path, required=True, help="JSON гипотез")
    hypotheses.set_defaults(func=hypotheses_command)
    plan = commands.add_parser("plan", help="Зафиксировать выборку, срок и условия")
    plan.add_argument("--settings", type=Path, required=True, help="Подтверждённые настройки JSON")
    plan.add_argument("--start", required=True, help="Первый полный день, ГГГГ-ММ-ДД")
    plan.set_defaults(func=plan_command)
    analyze = commands.add_parser("analyze", help="Анализ дневного CSV/XLSX")
    analyze.add_argument("--input", type=Path, required=True, help="Нормализованный CSV/XLSX")
    analyze.add_argument("--as-of", default=date.today().isoformat(), help="Дата анализа; этот день не включается")
    analyze.add_argument("--output", type=Path, help="Отдельный JSON для промежуточного контроля качества")
    analyze.set_defaults(func=analyze_command)
    report = commands.add_parser("report", help="Создать отчёт и обновить историю категории")
    report.add_argument("--analysis", type=Path, help="Файл анализа, по умолчанию analysis.json")
    report.add_argument("--output", type=Path, help="Отдельный путь отчёта")
    report.add_argument("--next-test", required=True, help="Следующая гипотеза на русском; не запускается автоматически")
    report.set_defaults(func=report_command)
    for command in (hypotheses, plan, analyze, report):
        command.add_argument("--experiment", type=Path, required=True, help="Папка эксперимента")
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except (InputError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError):
        print("Ошибка структуры или доступа к файлу. Проверь контракт входных данных; исходные данные не исправлены автоматически.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
