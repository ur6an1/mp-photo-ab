"""Reference-edit provider boundary; never retry a potentially billable request."""
from __future__ import annotations

import base64
from contextlib import ExitStack
from pathlib import Path
from typing import Protocol


class ImageProvider(Protocol):
    def edit(self, prompt: str, images: list[Path]) -> bytes: ...


class OpenAIProvider:
    def __init__(self, model: str = "gpt-image-1.5", client=None):
        if model != "gpt-image-1.5":
            raise ValueError("Эта версия проверена только для gpt-image-1.5.")
        if client is None:
            import os
            from openai import OpenAI
            if not os.environ.get("OPENAI_API_KEY"):
                raise ValueError("Для --run нужен OPENAI_API_KEY в окружении.")
            # Pin the official endpoint: environment overrides must not leak keys or images.
            client = OpenAI(base_url="https://api.openai.com/v1", max_retries=0, timeout=180)
        self.client = client
        self.model = model

    def edit(self, prompt: str, images: list[Path]) -> bytes:
        with ExitStack() as stack:
            files = [stack.enter_context(path.open("rb")) for path in images]
            response = self.client.images.edit(
                model=self.model, image=files, prompt=prompt, n=1,
                size="1024x1536", quality="medium", input_fidelity="high",
                output_format="png",
            )
        if not response.data or not response.data[0].b64_json:
            raise ValueError("Провайдер не вернул изображение; повтор автоматически запрещён.")
        return base64.b64decode(response.data[0].b64_json, validate=True)


def get_provider(name: str, model: str) -> ImageProvider:
    if name != "openai":
        raise ValueError("Поддерживается openai; адаптер fal пока не подключён.")
    return OpenAIProvider(model=model)
