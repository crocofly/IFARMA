"""
rag/_embeddings.py — Кастомная embedding-функция для русского текста.

Работает полностью оффлайн, без скачивания моделей.
Использует TF-IDF подход с хеш-трюком для фиксированной размерности.

Качество хуже нейросетевых эмбеддингов, но:
- Не требует интернета
- Не требует GPU
- Работает мгновенно
- Достаточно для поиска по структурированному документу (Решение 85)
"""

import hashlib
import math
import re
from typing import List

from chromadb.api.types import EmbeddingFunction, Documents, Embeddings


# Размерность вектора
EMBEDDING_DIM = 384

# Русские стоп-слова (минимальный набор)
STOP_WORDS_RU = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а",
    "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же",
    "вы", "за", "бы", "по", "только", "её", "ее", "мне", "было", "вот",
    "от", "меня", "ещё", "еще", "нет", "о", "из", "ему", "при", "для",
    "до", "или", "этот", "эта", "это", "их", "они", "быть", "этого",
    "об", "более", "может", "между", "должен", "также", "который",
    "которая", "которое", "которые", "которого", "которых", "которым",
    "после", "перед", "через", "если", "когда", "чем", "том", "тем",
    "этом", "всех", "может", "быть", "является", "следует", "необходимо",
    "каждый", "каждого", "каждой", "одного", "двух", "трех", "четырех",
    "либо", "того", "иных", "иные", "иной", "случае", "менее", "составляет",
}


def _tokenize(text: str) -> List[str]:
    """Токенизация: lowercase + split по не-буквам + убираем стоп-слова."""
    text = text.lower()
    # Оставляем кириллицу, латиницу, цифры
    tokens = re.findall(r'[а-яёa-z0-9]+', text)
    # Убираем стоп-слова и короткие токены
    return [t for t in tokens if t not in STOP_WORDS_RU and len(t) > 1]


def _hash_token(token: str, dim: int = EMBEDDING_DIM) -> int:
    """Хеш токена → индекс в векторе."""
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h, 16) % dim


def _ngrams(tokens: List[str], n: int = 2) -> List[str]:
    """Генерирует n-граммы из токенов."""
    result = list(tokens)  # unigrams
    for i in range(len(tokens) - n + 1):
        result.append("_".join(tokens[i:i + n]))
    return result


def _embed_text(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Создаёт TF-IDF-подобный вектор фиксированной размерности.

    Алгоритм:
    1. Токенизация + стоп-слова
    2. Uni/bi-граммы
    3. Хеш-трюк: каждый токен → индекс в векторе
    4. TF-подобные веса (log frequency)
    5. L2-нормализация
    """
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * dim

    # Uni + bi-граммы
    features = _ngrams(tokens, n=2)

    # Подсчёт частот
    freq = {}
    for f in features:
        freq[f] = freq.get(f, 0) + 1

    # Хеш-трюк → вектор
    vec = [0.0] * dim
    for token, count in freq.items():
        idx = _hash_token(token, dim)
        # log TF weighting
        weight = 1.0 + math.log(count)
        # Знак из второго хеша (для уменьшения коллизий)
        sign_hash = hashlib.sha1(token.encode("utf-8")).hexdigest()
        sign = 1.0 if int(sign_hash[0], 16) >= 8 else -1.0
        vec[idx] += sign * weight

    # L2-нормализация
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]

    return vec


class SimpleRuEmbedding(EmbeddingFunction):
    """
    Кастомная embedding функция для ChromaDB.
    Работает оффлайн, поддерживает русский текст.
    """

    def __init__(self):
        pass

    def __call__(self, input: Documents) -> Embeddings:
        return [_embed_text(doc) for doc in input]