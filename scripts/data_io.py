"""Strict, local experiment input and artifact handling."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path

COUNTS = ("impressions", "clicks", "cart", "orders")
FLAGS = ("advertising_changed", "out_of_stock", "price_changed")
VARIABLES = {"background", "composition", "light", "infographic", "badge"}


class InputError(ValueError):
    """An actionable input error safe to display to the seller."""


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, OSError) as exc:
        raise InputError("Не удалось прочитать JSON: проверь путь и формат файла.") from exc


def write_json(path: Path, value, *, replace: bool = False):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    write_text(path, text, replace=replace)


def write_text(path: Path, text: str, *, replace: bool = False):
    if path.is_symlink():
        raise InputError("Запись через символическую ссылку запрещена.")
    try:
        with path.open("w" if replace else "x", encoding="utf-8") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise InputError(f"Файл {path.name} уже существует: исходный эксперимент не перезаписываю.") from exc


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def iso_date(value) -> date:
    try:
        parsed = date.fromisoformat(str(value))
        if parsed.isoformat() != str(value):
            raise ValueError()
        return parsed
    except (TypeError, ValueError) as exc:
        raise InputError("Дата должна быть в формате ГГГГ-ММ-ДД.") from exc


def finite_number(value, label: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise InputError(f"{label}: нужно число.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{label}: нужно число.") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise InputError(f"{label}: допустимо от {low} до {high}.")
    return result


def integer(value, label: str) -> int:
    number = finite_number(value, label, 0, 10**12)
    if int(number) != number:
        raise InputError(f"{label}: нужно целое число.")
    return int(number)


def validate_counts(row: dict) -> dict:
    result = {key: integer(row.get(key), key) for key in COUNTS}
    if result["clicks"] > result["impressions"]:
        raise InputError("Кликов больше показов: проверь единицы и окно атрибуции.")
    if max(result["cart"], result["orders"]) > result["clicks"]:
        raise InputError("Корзин или заказов больше кликов: нужен согласованный бинарный счёт событий, не число единиц товара.")
    return result


def image_path(value, base: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError("Укажи локальный путь к изображению.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        raise InputError("Изображение не найдено: приложи текущее фото и реальные референсы товара.")
    return str(path.resolve())


def validate_brief(value, base: Path) -> dict:
    if not isinstance(value, dict):
        raise InputError("Бриф должен быть JSON-объектом.")
    result = dict(value)
    required = ("sku", "marketplace", "category", "audience", "price_segment")
    missing = [key for key in required if not isinstance(value.get(key), str) or not value[key].strip()]
    if missing:
        raise InputError("Заполни бриф: " + ", ".join(missing))
    if not re.fullmatch(r"[A-Za-z0-9А-Яа-яЁё_-]{1,80}", value["sku"]):
        raise InputError("Артикул: 1–80 букв, цифр, дефисов или подчёркиваний; без путей.")
    if value["marketplace"] not in {"Wildberries", "Ozon"}:
        raise InputError("Площадка: Wildberries или Ozon.")
    usps = value.get("usps")
    if not isinstance(usps, list) or not 1 <= len(usps) <= 3 or any(not isinstance(x, str) or not x.strip() for x in usps):
        raise InputError("Добавь 1–3 подтверждённых УТП.")
    refs = value.get("reference_images")
    if not isinstance(refs, list) or not refs:
        raise InputError("Обязательно приложи хотя бы одно реальное референс-фото товара.")
    result["current_image"] = image_path(value.get("current_image"), base)
    result["reference_images"] = [image_path(x, base) for x in refs]
    rivals = value.get("competitor_images", [])
    if not isinstance(rivals, list) or (rivals and not 3 <= len(rivals) <= 5):
        raise InputError("Скрины конкурентов: либо нет, либо 3–5 изображений.")
    result["competitor_images"] = [image_path(x, base) for x in rivals]
    baseline = value.get("baseline")
    if baseline is not None:
        if not isinstance(baseline, dict):
            raise InputError("Baseline должен быть объектом или null, если данных нет.")
        days = integer(baseline.get("days"), "Дни baseline")
        if not 14 <= days <= 30:
            raise InputError("Нужен baseline за 14–30 дней.")
        result["baseline"] = {"days": days, **validate_counts(baseline)}
    else:
        result["baseline"] = None
    return result


def validate_hypotheses(value) -> list[dict]:
    if not isinstance(value, list) or not 4 <= len(value) <= 6:
        raise InputError("Нужно 4–6 гипотез.")
    ids = set()
    for item in value:
        if not isinstance(item, dict):
            raise InputError("Каждая гипотеза должна быть объектом.")
        key = item.get("id", "")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", key) or key == "control" or key in ids:
            raise InputError("У гипотез нужны уникальные безопасные id; control зарезервирован.")
        ids.add(key)
        if item.get("variable") not in VARIABLES:
            raise InputError("Укажи ровно одну переменную: background, composition, light, infographic или badge.")
        for field in ("change", "rationale", "target_metric"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise InputError(f"В гипотезе не заполнено: {field}.")
        if item["target_metric"] not in {"ctr", "cart_per_click", "orders_per_click", "orders_per_impression"}:
            raise InputError("Неизвестная целевая метрика гипотезы.")
        if not isinstance(item.get("risks"), list) or not item["risks"] or any(not isinstance(x, str) or not x.strip() for x in item["risks"]):
            raise InputError("Укажи риски площадки и искажения товара.")
        ice = item.get("ice")
        if not isinstance(ice, dict):
            raise InputError("Нужны ICE-оценки impact, confidence, ease.")
        for field in ("impact", "confidence", "ease"):
            finite_number(ice.get(field), "ICE", 1, 5)
        if type(item.get("selected")) is not bool:
            raise InputError("selected должен быть true или false.")
        item["ice_score"] = round(sum(float(ice[k]) for k in ("impact", "confidence", "ease")) / 3, 3)
    if not 1 <= sum(x["selected"] for x in value) <= 2:
        raise InputError("Выбери 1–2 гипотезы, не больше.")
    return sorted(value, key=lambda x: (-x["ice_score"], x["id"]))


def boolean(value, name: str) -> bool:
    if value in (True, 1, "1", "true", "True"):
        return True
    if value in (False, 0, "0", "false", "False"):
        return False
    raise InputError(f"{name}: нужно явно указать true/false или 1/0, не оставлять пустым.")


def read_daily(path: Path) -> list[dict]:
    """Read a normalized export; never guess vendor column semantics."""
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise InputError("Заголовок CSV пуст или названия столбцов повторяются.")
            raw = list(reader)
            if any(None in row for row in raw):
                raise InputError("В CSV есть лишние значения без названий столбцов.")
    elif path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            values = list(workbook.active.values)
            if not values:
                raise InputError("Таблица пуста.")
            headers = list(values[0])
            if len(headers) != len(set(headers)):
                raise InputError("Названия столбцов повторяются.")
            raw = [dict(zip(headers, row)) for row in values[1:] if any(x is not None for x in row)]
        finally:
            workbook.close()
    else:
        raise InputError("Используй CSV или XLSX.")
    if not raw:
        raise InputError("Нет дневных данных.")
    result, seen = [], set()
    required = {"date", "variant", *COUNTS, *FLAGS}
    for row in raw:
        if not required.issubset(row):
            raise InputError("Нужны столбцы: " + ", ".join(sorted(required)))
        day = row["date"]
        if hasattr(day, "date"):
            day = day.date().isoformat()
        else:
            day = str(day)
        iso_date(day)
        variant = row["variant"]
        if not isinstance(variant, str) or not variant.strip():
            raise InputError("Не указан вариант.")
        key = (day, variant)
        if key in seen:
            raise InputError("Повтор даты и варианта: объедини непересекающиеся источники до импорта.")
        seen.add(key)
        result.append({"date": day, "variant": variant, **validate_counts(row),
                       **{flag: boolean(row[flag], flag) for flag in FLAGS}})
    return sorted(result, key=lambda x: (x["date"], x["variant"]))
