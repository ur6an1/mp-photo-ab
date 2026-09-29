"""Render a two-column mobile feed for manual product-fidelity review."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def preview(control: Path, variants: list[Path], competitors: list[Path], output: Path):
    from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps
    if not variants:
        raise ValueError("Нужен хотя бы один вариант.")
    items = [("Контроль", control)]
    items += [(f"Вариант {index}", value) for index, value in enumerate(variants, 1)]
    items += [(f"Конкурент {index}", value) for index, value in enumerate(competitors, 1)]
    font = None
    for name in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, 13)
            break
        except OSError:
            continue
    if font is None:
        raise ValueError("Не найден шрифт с кириллицей (Arial или DejaVu Sans).")
    width, tile_height, gap = 180, 268, 8
    canvas = Image.new("RGB", (width * 2 + gap * 3, ((len(items) + 1) // 2) * (tile_height + gap) + gap), "#eeeeee")
    draw = ImageDraw.Draw(canvas)
    for index, (label, path) in enumerate(items):
        left = gap + (index % 2) * (width + gap)
        top = gap + (index // 2) * (tile_height + gap)
        draw.rectangle((left, top, left + width - 1, top + tile_height - 1), fill="white")
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source)
            if source.info.get("icc_profile"):
                from io import BytesIO
                source = ImageCms.profileToProfile(source, ImageCms.ImageCmsProfile(BytesIO(source.info["icc_profile"])),
                                                  ImageCms.createProfile("sRGB"), outputMode="RGB")
            picture = ImageOps.contain(source.convert("RGB"), (width, 240), Image.Resampling.LANCZOS)
            canvas.paste(picture, (left + (width - picture.width) // 2, top + (240 - picture.height) // 2))
        draw.text((left + 6, top + 246), label, font=font, fill="#171717")
    with output.open("xb") as handle:
        canvas.save(handle, format="JPEG", quality=95,
                    icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())


class RussianParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Ошибка параметров: проверь обязательные аргументы и --help.\n")


def main(argv=None):
    parser = RussianParser(description="Превью выдачи: две колонки, карточки шириной 180 px.", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Показать справку и выйти")
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--variants", type=Path, nargs="+", required=True)
    parser.add_argument("--competitors", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        preview(args.control, args.variants, args.competitors, args.output)
    except Exception:
        print("Не удалось создать превью: проверь изображения, шрифт и новый путь результата.", file=sys.stderr)
        return 2
    print("Превью сохранено: проверь читаемость при масштабе 100%, затем соответствие реальному товару.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
