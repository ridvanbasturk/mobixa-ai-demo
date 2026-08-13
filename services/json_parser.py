"""Model çıktısından JSON çıkarma ve onarma.

Sırasıyla dener: json.loads -> markdown temizleme -> ilk/son parantez
çıkarma -> json_repair -> (çağıran taraf pydantic doğrulaması yapar).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class JsonParseResult:
    success: bool
    data: Optional[dict]
    method: Optional[str]
    error: Optional[str]


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    fence_pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    match = re.match(fence_pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_outer_braces(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def parse_model_json(raw_text: str) -> JsonParseResult:
    """Ham model çıktısını adım adım JSON'a çevirmeye çalışır."""
    if raw_text is None or not raw_text.strip():
        return JsonParseResult(False, None, None, "Model boş yanıt döndürdü")

    # 1. Doğrudan json.loads
    try:
        return JsonParseResult(True, json.loads(raw_text), "json.loads", None)
    except json.JSONDecodeError:
        pass

    # 2. Markdown kod bloklarını temizle
    cleaned = _strip_markdown_fences(raw_text)
    try:
        return JsonParseResult(True, json.loads(cleaned), "markdown_strip", None)
    except json.JSONDecodeError:
        pass

    # 3. İlk { ile son } arasını çıkar
    extracted = _extract_outer_braces(cleaned)
    if extracted:
        try:
            return JsonParseResult(True, json.loads(extracted), "brace_extraction", None)
        except json.JSONDecodeError:
            pass
    else:
        extracted = cleaned

    # 4. json_repair ile onarmayı dene
    try:
        from json_repair import repair_json

        repaired = repair_json(extracted)
        data = json.loads(repaired)
        if isinstance(data, dict):
            return JsonParseResult(True, data, "json_repair", None)
        return JsonParseResult(False, None, None, "json_repair geçerli bir nesne döndürmedi")
    except Exception as exc:  # noqa: BLE001 - onarım her türlü hatada başarısız sayılır
        return JsonParseResult(False, None, None, f"JSON onarılamadı: {exc}")
