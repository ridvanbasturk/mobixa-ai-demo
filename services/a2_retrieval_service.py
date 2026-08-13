"""A2 için basit, deterministik yerel bilgi getirme (retrieval) katmanı.

Bilinçli olarak Bedrock Knowledge Bases, vektör veritabanı, OpenSearch veya
embedding tabanlı bir servis KULLANMAZ — bu bir PoC'dir ve saydam, sözcük
temelli (lexical) bir eşleştirme yapar. Bu modül, ileride gerçek bir RAG
sistemiyle (ör. Bedrock Knowledge Bases) değiştirilebilecek şekilde model
çağrısından tamamen bağımsızdır.

Yalnızca status == "approved" olan kayıtlar getirilebilir.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

MIN_RELEVANCE_SCORE = 1.0
DEFAULT_TOP_K = 3

_TURKISH_UPPER_TO_LOWER = str.maketrans(
    {"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"}
)

_STOPWORDS = {
    "ve", "ile", "bir", "bu", "şu", "için", "ne", "nasıl", "mi", "mı", "mu", "mü",
    "var", "yok", "kaç", "olan", "gibi", "de", "da", "ki", "mu?", "mi?",
}

_TOKEN_PATTERN = re.compile(r"[a-zçğıöşü0-9]+")

_MIN_PREFIX_MATCH = 4

_EN_STOPWORDS = {
    "and", "the", "a", "an", "for", "how", "do", "does", "is", "are", "i",
    "to", "of", "in", "on", "my", "what", "can", "no", "not", "it", "this",
    "that", "with",
}


def load_knowledge_base(path: Path) -> List[Dict]:
    """Bilgi tabanı JSON dosyasını okur."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_turkish(text: str) -> str:
    """Türkçe büyük harfleri doğru şekilde küçük harfe çevirir (İ→i, I→ı vb.)."""
    return (text or "").translate(_TURKISH_UPPER_TO_LOWER).lower()


def tokenize(text: str, language: str = "tr") -> List[str]:
    """Metni normalize edip anlamlı kelime köklerine (token) ayırır.

    `language="tr"` (varsayılan) Türkçe-farkındalıklı büyük/küçük harf
    dönüşümü ve TR stopword listesini kullanır (mevcut davranış, DEĞİŞMEZ).
    `language="en"` düz küçük harfe çevirme ve küçük bir EN stopword
    listesi kullanır; eşleştirme algoritması (prefix match) aynı kalır.
    """
    if language == "en":
        normalized = (text or "").lower()
        stopwords = _EN_STOPWORDS
    else:
        normalized = normalize_turkish(text)
        stopwords = _STOPWORDS
    tokens = _TOKEN_PATTERN.findall(normalized)
    return [t for t in tokens if t not in stopwords and len(t) >= 2]


def _tokens_match(a: str, b: str, min_prefix: int = _MIN_PREFIX_MATCH) -> bool:
    """İki token'ın eşleşip eşleşmediğini kontrol eder.

    Türkçe eklerden (şifremi/şifre gibi) kaynaklanan farkları tolere etmek
    için tam eşitlik yerine ortak önek (prefix) karşılaştırması kullanılır.
    """
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < min_prefix:
        return False
    return a[:min_prefix] == b[:min_prefix]


def _count_matches(query_tokens: List[str], target_tokens: List[str]) -> int:
    count = 0
    for qt in query_tokens:
        if any(_tokens_match(qt, tt) for tt in target_tokens):
            count += 1
    return count


def score_entry(query_tokens: List[str], entry: Dict, language: str = "tr") -> float:
    """Bir kayıt için başlık/ürün alanı/içerik ağırlıklı sözcük örtüşme puanı hesaplar."""
    title_tokens = tokenize(entry.get("title", ""), language)
    content_tokens = tokenize(entry.get("content", ""), language)
    area_tokens = tokenize((entry.get("product_area", "") or "").replace("_", " "), language)

    score = 0.0
    score += 2.0 * _count_matches(query_tokens, title_tokens)
    score += 1.5 * _count_matches(query_tokens, area_tokens)
    score += 1.0 * _count_matches(query_tokens, content_tokens)
    return score


def retrieve_relevant_entries(
    question: str,
    kb_entries: List[Dict],
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_RELEVANCE_SCORE,
    language: str = "tr",
) -> Tuple[List[Dict], bool]:
    """Onaylı kayıtlar arasından soruyla en alakalı olanları getirir.

    Döndürülen ikili: (puanlı kayıt listesi, yeterli_alaka_var_mı).
    Hiçbir kayıt eşik değere ulaşmazsa boş liste ve False döner — bu durumda
    modele hiçbir kaynak bağlamı verilmemelidir. `language` yalnızca
    tokenize/normalize kurallarını seçer (varsayılan "tr", mevcut davranış
    DEĞİŞMEZ); hangi bilgi tabanı dosyasının yükleneceğine çağıran taraf
    karar verir.
    """
    approved = [e for e in kb_entries if e.get("status") == "approved"]
    query_tokens = tokenize(question, language)

    scored = []
    for entry in approved:
        s = score_entry(query_tokens, entry, language)
        if s > 0:
            scored.append((s, entry))
    scored.sort(key=lambda item: item[0], reverse=True)

    if not scored or scored[0][0] < min_score:
        return [], False

    top = scored[:top_k]
    results = [{**entry, "score": round(score, 2)} for score, entry in top]
    return results, True
