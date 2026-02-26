"""
rag/rag_search.py — Поиск по индексу Решения №85.

Используется агентами для получения релевантных разделов
из Решения 85 по семантическому запросу.

Пример использования:
    from app.rag.rag_search import search_decision85

    results = search_decision85("дизайн перекрёстное исследование отмывочный период")
    for r in results:
        print(r["section"], r["text"][:200])
"""

import os
from typing import List, Dict, Optional

import chromadb


# Путь к ChromaDB по умолчанию
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "chroma_db"
)
DEFAULT_COLLECTION = "decision_85"

# Кэш клиента — не создаём новый при каждом вызове
_client_cache = {}


def _get_collection(
    db_path: str = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION,
):
    """Получает коллекцию ChromaDB (с кэшированием клиента)."""
    cache_key = f"{db_path}:{collection_name}"

    if cache_key not in _client_cache:
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"ChromaDB не найдена: {db_path}. "
                f"Запустите: python -m app.rag.rag_index --input data/Решение85.docx"
            )

        from app.rag._embeddings import SimpleRuEmbedding

        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_collection(
            name=collection_name,
            embedding_function=SimpleRuEmbedding(),
        )
        _client_cache[cache_key] = collection

    return _client_cache[cache_key]


def search_decision85(
    query: str,
    n_results: int = 5,
    db_path: str = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION,
) -> List[Dict]:
    """
    Семантический поиск по Решению 85.

    Args:
        query: Поисковый запрос на русском языке.
                Примеры:
                - "дизайн перекрёстное исследование"
                - "границы биоэквивалентности высоковариабельные"
                - "отмывочный период"
                - "количество субъектов минимум"
                - "натощак после еды приём препарата"

        n_results: Количество результатов (по умолчанию 5)
        db_path: Путь к ChromaDB
        collection_name: Имя коллекции

    Returns:
        Список словарей:
        [
            {
                "id": "r85_0042",
                "section": "1. Дизайн исследования",
                "text": "15. Стандартный дизайн предполагает...",
                "distance": 0.32,  # чем меньше, тем лучше
            },
            ...
        ]
    """
    try:
        collection = _get_collection(db_path, collection_name)
    except FileNotFoundError as e:
        print(f"⚠️  {e}")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )

    # Собираем результаты
    output = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            output.append({
                "id": doc_id,
                "section": results["metadatas"][0][i].get("section", ""),
                "text": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })

    return output


def search_and_format(
    query: str,
    n_results: int = 5,
    max_total_chars: int = 6000,
    db_path: str = DEFAULT_DB_PATH,
) -> str:
    """
    Поиск + форматирование для вставки в промпт LLM.

    Возвращает текст в формате:
    === Раздел: 1. Дизайн исследования ===
    15. Стандартный дизайн предполагает...
    ---
    === Раздел: 11. Лекарственные препараты с высокой вариабельностью ===
    ...

    Args:
        query: Поисковый запрос
        n_results: Количество результатов
        max_total_chars: Максимум символов в ответе
        db_path: Путь к ChromaDB

    Returns:
        Форматированный текст для промпта
    """
    results = search_decision85(query, n_results, db_path)

    if not results:
        return "(Релевантные разделы Решения 85 не найдены)"

    parts = []
    total_chars = 0

    for r in results:
        text = r["text"]
        # Обрезаем если слишком длинный
        if total_chars + len(text) > max_total_chars:
            remaining = max_total_chars - total_chars
            if remaining > 200:
                text = text[:remaining] + "..."
            else:
                break

        section_header = f"=== Решение 85, раздел: {r['section']} ==="
        parts.append(f"{section_header}\n{text}")
        total_chars += len(text) + len(section_header)

    return "\n---\n".join(parts)


def get_design_context(
    cv_intra: Optional[float] = None,
    t_half: Optional[float] = None,
    is_hvd: bool = False,
    is_nti: bool = False,
    release_type: str = "immediate",
) -> str:
    """
    Получает контекст из Решения 85 для Design Agent.

    Формирует несколько запросов в зависимости от параметров
    и объединяет результаты.

    Args:
        cv_intra: Коэффициент вариабельности
        t_half: Период полувыведения (часы)
        is_hvd: Высоковариабельный препарат
        is_nti: Узкий терапевтический индекс
        release_type: Тип высвобождения

    Returns:
        Форматированный контекст для промпта
    """
    queries = ["дизайн исследования биоэквивалентности перекрестное"]

    if is_hvd or (cv_intra and cv_intra >= 30):
        queries.append("высокая вариабельность лекарственные препараты масштабирование границ")

    if is_nti:
        queries.append("узкий терапевтический диапазон границы биоэквивалентности")

    if t_half and t_half > 24:
        queries.append("параллельный дизайн длительный период полувыведения")

    if release_type in ("modified", "delayed"):
        queries.append("модифицированное высвобождение натощак после еды")

    queries.append("отмывочный период количество субъектов минимум")

    # Собираем уникальные результаты
    all_results = []
    seen_ids = set()

    for q in queries:
        results = search_decision85(q, n_results=3)
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                all_results.append(r)

    # Форматируем
    if not all_results:
        return "(Контекст из Решения 85 не найден)"

    parts = []
    total_chars = 0
    max_chars = 8000

    for r in all_results:
        text = r["text"]
        if total_chars + len(text) > max_chars:
            break
        header = f"=== Решение 85: {r['section']} ==="
        parts.append(f"{header}\n{text}")
        total_chars += len(text) + len(header)

    return "\n---\n".join(parts)