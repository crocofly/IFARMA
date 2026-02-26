"""
services/search/protocol_search.py — Поиск существующих протоколов БЭ.

Ищет через Yandex GenSearch на ClinicalTrials.gov и PubMed
существующие протоколы исследований биоэквивалентности
с тем же МНН. Если находит — извлекает дизайн, CVintra,
размер выборки, режим приёма.

Приоритет:
1. ClinicalTrials.gov — структурированные данные о дизайне
2. PubMed — статьи с результатами, CVintra

Если не нашли → агенты рассчитают всё самостоятельно.
"""

import os
import re
import requests
from typing import Dict, Optional, List


YANDEX_GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"


def lookup_inn_english(
    inn_ru: str,
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """
    Находит английское название МНН по русскому через Yandex.

    Примеры:
        "тенофовира алафенамид" → "tenofovir alafenamide"
        "амлодипин" → "amlodipine"

    Returns:
        Английское МНН или пустая строка
    """
    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        return ""

    query = (
        f"Как называется МНН (международное непатентованное название) "
        f"'{inn_ru}' на английском языке? "
        f"Ответь одним словом/фразой (только INN на английском)."
    )

    answer = _call_yandex_ru(query, folder_id, api_key)
    if not answer:
        return ""

    # Извлекаем английское название — первое слово/фразу латиницей
    match = re.search(r'[a-zA-Z][a-zA-Z\s\-]+[a-zA-Z]', answer)
    if match:
        return match.group(0).strip().lower()

    return ""


def _call_yandex_ru(query: str, folder_id: str, api_key: str) -> str:
    """Вызов Yandex GenSearch API (русскоязычный поиск)."""
    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folder_id": folder_id,
        "fixMisspell": True,
    }
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(YANDEX_GEN_SEARCH_URL, json=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            message = data.get("message", {})
            if isinstance(message, list):
                message = message[0] if message else {}
            if isinstance(message, dict):
                content = message.get("content", "")
                return content if isinstance(content, str) else ""
        return ""
    except Exception:
        return ""


def search_existing_protocols(
    inn_ru: str,
    inn_en: str = "",
    ref_drug_name: str = "",
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict:
    """
    Ищет существующие протоколы БЭ через Yandex GenSearch.

    Шаг 1: Ищем на ClinicalTrials.gov
    Шаг 2: Ищем на PubMed
    Шаг 3: Парсим результаты → дизайн, CVintra, выборка

    Args:
        inn_ru: МНН на русском ("тенофовира алафенамид")
        inn_en: МНН на английском ("tenofovir alafenamide") — для PubMed
        ref_drug_name: торговое название референта ("Вемлиди®")

    Returns:
        dict с ключами:
            found: bool
            source: "clinicaltrials" | "pubmed" | None
            design_type: str | None  (e.g. "2x2_crossover", "replicate_4_period")
            n_periods: int | None
            n_subjects: int | None
            cv_intra: float | None
            intake_mode: str | None  ("fasting", "fed", "both")
            nct_id: str | None  (номер NCT)
            study_title: str | None
            raw_text: str
    """
    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        return _empty_result()

    # Шаг 1: Ищем на ClinicalTrials.gov
    ct_result = _search_clinicaltrials(inn_ru, inn_en, ref_drug_name, folder_id, api_key)
    if ct_result.get("found"):
        return ct_result

    # Шаг 2: Ищем на PubMed
    pubmed_result = _search_pubmed(inn_ru, inn_en, folder_id, api_key)
    if pubmed_result.get("found"):
        return pubmed_result

    return _empty_result()


def _search_clinicaltrials(
    inn_ru: str,
    inn_en: str,
    ref_drug_name: str,
    folder_id: str,
    api_key: str,
) -> Dict:
    """Ищет протоколы БЭ на ClinicalTrials.gov."""
    # Используем английское название если есть, иначе русское
    search_term = inn_en if inn_en else inn_ru

    query = (
        f"Найди на ClinicalTrials.gov исследования биоэквивалентности (bioequivalence) "
        f"для {search_term}. "
        f"Для каждого найденного исследования укажи:\n"
        f"NCT номер: ...\n"
        f"Название: ...\n"
        f"Дизайн: (crossover / parallel / replicate)\n"
        f"Количество периодов: ...\n"
        f"Количество добровольцев: ...\n"
        f"Режим приёма: (fasting / fed / fasting and fed)\n"
        f"Статус: (completed / recruiting / etc)\n"
        f"Если исследований не найдено, напиши 'Не найдено'."
    )

    answer = _call_yandex(query, folder_id, api_key)
    if not answer:
        return _empty_result()

    return _parse_ct_response(answer)


def _search_pubmed(
    inn_ru: str,
    inn_en: str,
    folder_id: str,
    api_key: str,
) -> Dict:
    """Ищет статьи о БЭ-исследованиях на PubMed."""
    search_term = inn_en if inn_en else inn_ru

    query = (
        f"Найди на PubMed статьи об исследованиях биоэквивалентности (bioequivalence study) "
        f"для {search_term}. "
        f"Для каждой статьи укажи:\n"
        f"PMID: ...\n"
        f"Название статьи: ...\n"
        f"Дизайн исследования: ...\n"
        f"CVintra (коэффициент вариации): ...\n"
        f"Количество добровольцев: ...\n"
        f"Режим приёма: (fasting / fed)\n"
        f"Если статей не найдено, напиши 'Не найдено'."
    )

    answer = _call_yandex(query, folder_id, api_key)
    if not answer:
        return _empty_result()

    return _parse_pubmed_response(answer)


def _call_yandex(query: str, folder_id: str, api_key: str) -> str:
    """Вызов Yandex GenSearch API."""
    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folder_id": folder_id,
        
        "fixMisspell": True,
    }

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            YANDEX_GEN_SEARCH_URL,
            json=body,
            headers=headers,
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
            message = data.get("message", {})
            if isinstance(message, list):
                message = message[0] if message else {}
            if isinstance(message, dict):
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            parts.append(str(item.get("content", item.get("text", ""))))
                        elif isinstance(item, str):
                            parts.append(item)
                    return " ".join(parts)
            return ""
        else:
            return ""
    except Exception as e:
        print(f"⚠️  Yandex Search (protocol): {e}")
        return ""


def _parse_ct_response(text: str) -> Dict:
    """Парсит ответ поиска ClinicalTrials.gov."""
    result = _empty_result()
    text_lower = text.lower()

    # Проверяем наличие результатов
    if "не найдено" in text_lower or "no results" in text_lower:
        return result

    # Проверяем что это действительно исследование БЭ
    # (не оригинальное Phase 1-3 исследование)
    be_keywords = [
        "bioequivalence", "биоэквивалент", "generic",
        "crossover", "перекрестн", "replicate", "репликат",
        "reference product", "test product",
    ]
    is_be_study = any(kw in text_lower for kw in be_keywords)

    # NCT номер
    nct_match = re.search(r'NCT\d{6,10}', text, re.IGNORECASE)
    if nct_match:
        result["nct_id"] = nct_match.group(0).upper()
        # Помечаем как найденный ТОЛЬКО если это БЭ-исследование
        result["found"] = is_be_study
        result["source"] = "clinicaltrials"

    if not is_be_study:
        return result

    # Дизайн
    design = _extract_design(text)
    if design:
        result["design_type"] = design["type"]
        result["n_periods"] = design["periods"]

    # Количество добровольцев
    n_match = re.search(
        r'(?:количество\s+добровольцев|subjects?|participants?|enrollment)[:\s]*(\d+)',
        text, re.IGNORECASE
    )
    if n_match:
        result["n_subjects"] = int(n_match.group(1))

    # Режим приёма
    intake = _extract_intake(text)
    if intake:
        result["intake_mode"] = intake

    result["raw_text"] = text[:1000]
    return result


def _parse_pubmed_response(text: str) -> Dict:
    """Парсит ответ поиска PubMed."""
    result = _empty_result()
    text_lower = text.lower()

    if "не найдено" in text_lower or "no results" in text_lower:
        return result

    # PMID
    pmid_match = re.search(r'PMID[:\s]*(\d+)', text, re.IGNORECASE)
    if pmid_match:
        result["found"] = True
        result["source"] = "pubmed"
        result["nct_id"] = f"PMID:{pmid_match.group(1)}"

    # CVintra
    cv_match = re.search(
        r'(?:CVintra|CV|coefficient\s+of\s+variation)[:\s]*(\d+(?:\.\d+)?)\s*%?',
        text, re.IGNORECASE
    )
    if cv_match:
        result["cv_intra"] = float(cv_match.group(1))
        if not result["found"]:
            result["found"] = True
            result["source"] = "pubmed"

    # Дизайн
    design = _extract_design(text)
    if design:
        result["design_type"] = design["type"]
        result["n_periods"] = design["periods"]

    # Количество добровольцев
    n_match = re.search(
        r'(?:subjects?|participants?|volunteers?|добровольц)[:\s]*(\d+)',
        text, re.IGNORECASE
    )
    if n_match:
        result["n_subjects"] = int(n_match.group(1))

    # Режим приёма
    intake = _extract_intake(text)
    if intake:
        result["intake_mode"] = intake

    result["raw_text"] = text[:1000]
    return result


def _extract_design(text: str) -> Optional[Dict]:
    """Извлекает тип дизайна из текста."""
    text_lower = text.lower()

    # Полный репликативный 4 периода
    if any(k in text_lower for k in [
        "4-period", "4 period", "full replicate", "trtr", "2x2x4",
        "4 периода", "полный репликативный", "четырехпериодн",
    ]):
        return {"type": "replicate_4_period", "periods": 4}

    # Частичный репликативный 3 периода
    if any(k in text_lower for k in [
        "3-period", "3 period", "partial replicate", "trt/rtr", "2x2x3",
        "3 периода", "частичный репликативный", "трехпериодн",
    ]):
        return {"type": "replicate_3_period", "periods": 3}

    # Параллельный
    if any(k in text_lower for k in [
        "parallel", "параллельн",
    ]):
        return {"type": "parallel", "periods": 1}

    # Стандартный перекрёстный 2×2
    if any(k in text_lower for k in [
        "crossover", "cross-over", "2x2", "2-period", "2 period",
        "перекрестн", "двухпериодн",
    ]):
        return {"type": "2x2_crossover", "periods": 2}

    return None


def _extract_intake(text: str) -> Optional[str]:
    """Извлекает режим приёма из текста."""
    text_lower = text.lower()

    if any(k in text_lower for k in ["fasting and fed", "fed and fasting",
                                       "натощак и после еды"]):
        return "both"
    if any(k in text_lower for k in ["fed", "after meal", "with food",
                                       "после еды", "с пищей", "во время еды"]):
        return "fed"
    if any(k in text_lower for k in ["fasting", "натощак"]):
        return "fasting"

    return None


def _empty_result() -> Dict:
    """Пустой результат."""
    return {
        "found": False,
        "source": None,
        "design_type": None,
        "n_periods": None,
        "n_subjects": None,
        "cv_intra": None,
        "intake_mode": None,
        "nct_id": None,
        "study_title": None,
        "raw_text": "",
    }