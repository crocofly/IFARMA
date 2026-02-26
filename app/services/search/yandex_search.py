"""
services/search/yandex_search.py — Клиент Yandex Search API.

Используется для поиска информации об организациях (адрес, индекс, телефон)
через генеративный поиск Yandex (YandexGPT + Search).

Настройки в .env:
  YANDEX_FOLDER_ID=b1gu1ltnmnr8bb3urac0
  YANDEX_API_KEY=AQVN26wwT2Zb42hKxt_1lCpLBXCddAxKJw_TgN6S
"""

import os
import requests
from typing import Dict, Optional


YANDEX_GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"


def search_organization_info(
    org_name: str,
    country: str = "Россия",
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Ищет юридический адрес, индекс и телефон организации
    через Yandex Generative Search API.

    Включает retry с паузой при тоймауте (Yandex GenSearch
    может тоймаутить при нескольких запросах подряд).

    Returns:
        dict с ключами: name, country, address, postal_code, phone,
                        raw_answer, sources
    """
    import time

    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        print("⚠️  YANDEX_FOLDER_ID или YANDEX_API_KEY не заданы в .env")
        return _empty_result(org_name, country)

    query = (
        f"Юридический адрес и контактный телефон организации «{org_name}», {country}. "
        f"Нужны ТОЧНЫЕ данные с официального сайта компании или из реестра юридических лиц. "
        f"Ответь строго в формате:\n"
        f"Юридический адрес: [полный адрес с индексом]\n"
        f"Телефон: [все известные номера через запятую в формате +7 (xxx) xxx-xx-xx]\n"
        f"Если данные не найдены, напиши 'не найдено'."
    )

    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folderId": folder_id,
        "searchType": "SEARCH_TYPE_RU",
        "fixMisspell": True,
    }

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    # Retry до 3 раз с паузой (Yandex GenSearch тоймаутит при частых запросах)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                YANDEX_GEN_SEARCH_URL,
                headers=headers,
                json=body,
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    data = data[0] if data else {}
                break  # Успех — выходим из цикла
            elif resp.status_code == 429:
                # Rate limit — ждём подольше
                print(f"  ⚠️ Yandex Search: rate limit (429), пауза {attempt * 3}с...")
                time.sleep(attempt * 3)
                continue
            else:
                print(f"❌ Yandex Search API: HTTP {resp.status_code}")
                print(f"   {resp.text[:300]}")
                return _empty_result(org_name, country)

        except requests.exceptions.ReadTimeout:
            if attempt < max_retries:
                print(f"  ⚠️ Yandex Search: тоймаут для «{org_name}», повтор {attempt}/{max_retries} через {attempt * 2}с...")
                time.sleep(attempt * 2)
                continue
            else:
                print(f"  ❌ Yandex Search: тоймаут для «{org_name}» после {max_retries} попыток")
                return _empty_result(org_name, country)

        except requests.exceptions.RequestException as e:
            print(f"❌ Yandex Search API ошибка: {e}")
            return _empty_result(org_name, country)
    else:
        # Все retry исчерпаны
        return _empty_result(org_name, country)

    # Парсим ответ
    answer_text = data.get("message", {}).get("content", "")
    sources = []
    for src in data.get("sources", []):
        if src.get("used"):
            sources.append(src.get("url", ""))

    result = {
        "name": org_name,
        "country": country,
        "address": "",
        "postal_code": "",
        "phone": "",
        "raw_answer": answer_text,
        "sources": sources,
    }

    # Извлекаем структурированные данные из текста ответа
    # Yandex может отвечать в разных форматах:
    # 1) "Адрес: ..." / "Индекс: ..." / "Телефон: ..."
    # 2) "**Юридический адрес**: 305022, г. Курск..." (markdown)
    import re

    # Очищаем markdown и сноски
    clean = answer_text.replace("**", "").strip()
    clean = re.sub(r'\[\d+\]', '', clean)  # убираем [1], [2] и т.д.

    for line in clean.split("\n"):
        line_stripped = line.strip()
        line_lower = line_stripped.lower()

        # Адрес
        if any(k in line_lower for k in ["юридический адрес", "адрес:"]):
            # Берём всё после двоеточия
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val:
                    result["address"] = val

        # Индекс
        elif any(k in line_lower for k in ["почтовый индекс", "индекс:"]):
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val:
                    result["postal_code"] = val

        # Телефон
        elif any(k in line_lower for k in ["контактн", "телефон"]):
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val:
                    result["phone"] = val

    # Если индекс не извлёкся — пробуем из адреса
    if not result["postal_code"] and result["address"]:
        m = re.search(r'\b(\d{6})\b', result["address"])
        if m:
            result["postal_code"] = m.group(1)

    # Если адрес всё ещё пустой — пробуем найти 6-значный индекс + текст после
    if not result["address"] and answer_text:
        m = re.search(r'(\d{6}[,.]?\s*[^.\[\]]+)', clean)
        if m:
            result["address"] = m.group(1).strip().rstrip(".")

    return result


def format_sponsor_field(org_info: Dict[str, str]) -> str:
    """
    Форматирует данные об организации для вставки в синопсис Row 2.

    Формат:
      ООО «Фармстандарт», Россия
      123456, г. Москва, ул. Примерная, д. 1
      Телефон: +7 (495) 123-45-67
    """
    import re
    lines = []

    # Название + страна
    lines.append(f"{org_info['name']}, {org_info['country']}")

    # Индекс, адрес
    postal = org_info.get("postal_code", "")
    address = org_info.get("address", "")

    if postal and postal != "не найдено":
        if address and not address.startswith(postal):
            if re.match(r'^\d{6}', address):
                lines.append(address)
            else:
                lines.append(f"{postal}, {address}")
        elif address:
            lines.append(address)
        else:
            lines.append(postal)
    elif address and address != "не найдено":
        lines.append(address)

    # Телефон
    phone = org_info.get("phone", "")
    if phone and phone != "не найдено":
        lines.append(f"Телефон: {phone}")

    return "\n".join(lines)


def _empty_result(org_name: str, country: str) -> Dict[str, str]:
    """Пустой результат при ошибке."""
    return {
        "name": org_name,
        "country": country,
        "address": "",
        "postal_code": "",
        "phone": "",
        "raw_answer": "",
        "sources": [],
    }


def search_reference_drug_info(
    inn_ru: str,
    ref_drug_name: str,
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Ищет информацию о референтном препарате по МНН через Yandex GenSearch.

    Ищет на сайтах GRLS, ЕАЭС реестра:
      - лекарственная форма
      - дозировка
      - производитель (название + страна)
      - условия хранения

    Args:
        inn_ru: МНН на русском, например "тенофовира алафенамид"
        ref_drug_name: торговое название, например "Вемлиди®"

    Returns:
        dict с ключами: name, dosage_form, dosage, manufacturer,
                        manufacturer_country, storage, raw_answer, sources
    """
    import re

    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        print("⚠️  YANDEX_FOLDER_ID или YANDEX_API_KEY не заданы")
        return _empty_ref_result(ref_drug_name)

    query = (
        f"Найди информацию о лекарственном препарате {ref_drug_name} "
        f"(МНН: {inn_ru}) в государственном реестре лекарственных средств России. "
        f"Ответь строго в формате:\n"
        f"Лекарственная форма: ...\n"
        f"Дозировка: ...\n"
        f"Производитель: ...\n"
        f"Страна производителя: ...\n"
        f"Условия хранения: ...\n"
        f"Если информация недоступна, напиши 'не найдено'."
    )

    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folderId": folder_id,
        "searchType": "SEARCH_TYPE_RU",
        "fixMisspell": True,
    }

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            YANDEX_GEN_SEARCH_URL,
            headers=headers,
            json=body,
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                data = data[0] if data else {}
        else:
            print(f"❌ Yandex Search API: HTTP {resp.status_code}")
            return _empty_ref_result(ref_drug_name)

    except requests.exceptions.RequestException as e:
        print(f"❌ Yandex Search API ошибка: {e}")
        return _empty_ref_result(ref_drug_name)

    answer_text = data.get("message", {}).get("content", "")
    sources = [s.get("url") for s in data.get("sources", []) if s.get("used")]

    result = {
        "name": ref_drug_name,
        "dosage_form": "",
        "dosage": "",
        "manufacturer": "",
        "manufacturer_country": "",
        "storage": "",
        "raw_answer": answer_text,
        "sources": sources,
    }

    # Очищаем markdown и сноски
    clean = answer_text.replace("**", "").strip()
    clean = re.sub(r'\[\d+\]', '', clean)

    for line in clean.split("\n"):
        line_stripped = line.strip()
        line_lower = line_stripped.lower()

        if any(k in line_lower for k in ["лекарственная форма", "форма выпуска"]):
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val and val.lower() != "не найдено":
                    result["dosage_form"] = val

        elif line_lower.startswith("дозировка") or line_lower.startswith("доза"):
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val and val.lower() != "не найдено":
                    result["dosage"] = val

        elif "производител" in line_lower and "страна" not in line_lower:
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val and val.lower() != "не найдено":
                    result["manufacturer"] = val

        elif "страна" in line_lower:
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val and val.lower() != "не найдено":
                    result["manufacturer_country"] = val

        elif "хранени" in line_lower or "условия" in line_lower:
            if ":" in line_stripped:
                val = line_stripped.split(":", 1)[1].strip().rstrip(".")
                if val and val.lower() != "не найдено":
                    result["storage"] = val

    return result


def format_ref_drug_description(ref_info: Dict[str, str]) -> str:
    """
    Форматирует описание референтного препарата для вставки в синопсис.

    Формат: Вемлиди®, таблетки, покрытые плёночной оболочкой, 25 мг
            (Gilead Sciences Ireland UC, Ирландия)
    """
    parts = [ref_info["name"]]

    if ref_info.get("dosage_form"):
        parts.append(ref_info["dosage_form"])

    if ref_info.get("dosage"):
        parts.append(ref_info["dosage"])

    text = ", ".join(parts)

    # Производитель в скобках
    if ref_info.get("manufacturer"):
        mfr = ref_info["manufacturer"]
        if ref_info.get("manufacturer_country"):
            mfr += f", {ref_info['manufacturer_country']}"
        text += f" ({mfr})"

    return text


def _empty_ref_result(ref_drug_name: str) -> Dict[str, str]:
    """Пустой результат для референтного препарата."""
    return {
        "name": ref_drug_name,
        "dosage_form": "",
        "dosage": "",
        "manufacturer": "",
        "manufacturer_country": "",
        "storage": "",
        "raw_answer": "",
        "sources": [],
    }


def search_intake_mode(
    ref_drug_name: str,
    inn_ru: str,
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """
    Определяет режим приёма препарата (натощак / после еды / оба)
    из инструкции по медицинскому применению референтного препарата.

    Ищет через Yandex GenSearch в инструкции по применению:
    - «принимать во время еды» / «с пищей» → fed
    - «натощак» / «за час до еды» → fasting
    - «независимо от приёма пищи» → fasting (стандарт для БЭ)
    - «натощак и после еды» (модифицированное высвобождение) → both

    Args:
        ref_drug_name: торговое название, например "Вемлиди®"
        inn_ru: МНН на русском, например "тенофовира алафенамид"

    Returns:
        dict с ключами:
            mode: "fasting" | "fed" | "both"
            raw_text: исходный текст из инструкции
            source: "yandex_search" | "default"
    """
    import re

    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        print("⚠️  YANDEX_FOLDER_ID/API_KEY не заданы — режим приёма по умолчанию")
        return {"mode": "fasting", "raw_text": "", "source": "default"}

    query = (
        f"Найди в инструкции по медицинскому применению препарата {ref_drug_name} "
        f"(МНН: {inn_ru}) информацию о том, как принимать препарат: "
        f"натощак, во время еды или после еды. "
        f"Процитируй точную фразу из раздела «Способ применения и дозы» инструкции."
    )

    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folderId": folder_id,
        "searchType": "SEARCH_TYPE_RU",
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
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            # GenSearch может вернуть массив — берём первый элемент
            if isinstance(data, list):
                data = data[0] if data else {}
        else:
            print(f"⚠️  Yandex Search (intake mode): HTTP {resp.status_code}")
            return {"mode": "fasting", "raw_text": "", "source": "default"}
    except Exception as e:
        print(f"⚠️  Yandex Search ошибка (intake mode): {e}")
        return {"mode": "fasting", "raw_text": "", "source": "default"}

    # Извлекаем текст ответа (тот же формат что в search_organization_info)
    answer_text = ""
    try:
        message = data.get("message", {})
        if isinstance(message, list):
            message = message[0] if message else {}
        if isinstance(message, dict):
            answer_text = message.get("content", "")
        if isinstance(answer_text, list):
            # content может быть списком объектов
            parts = []
            for item in answer_text:
                if isinstance(item, dict):
                    parts.append(str(item.get("content", item.get("text", ""))))
                elif isinstance(item, str):
                    parts.append(item)
            answer_text = " ".join(parts)
    except Exception as e:
        print(f"⚠️  Парсинг ответа (intake mode): {e}")
        answer_text = str(data)[:1000]

    if not answer_text:
        return {"mode": "fasting", "raw_text": "", "source": "default"}

    answer_lower = answer_text.lower()

    # ── Определяем режим по ключевым фразам ──

    # Признаки «после еды» / «во время еды» / «с пищей»
    fed_markers = [
        "во время еды", "с пищей", "после еды", "вместе с пищей",
        "одновременно с пищей", "во время приема пищи",
        "принимать с едой", "рекомендуется принимать с пищей",
        "следует принимать с пищей", "принимают во время еды",
    ]

    # Признаки «натощак» / «до еды»
    fasting_markers = [
        "натощак", "за 1 час до еды", "за час до еды",
        "за 30 минут до еды", "за 30 мин до еды",
        "до приема пищи", "не менее чем за",
    ]

    # Признаки «независимо от приёма пищи»
    independent_markers = [
        "независимо от приема пищи", "независимо от приёма пищи",
        "вне зависимости от приема пищи", "вне зависимости от еды",
    ]

    # Признаки «оба варианта» (модифицированное высвобождение)
    both_markers = [
        "натощак и после еды", "натощак и с пищей",
    ]

    has_fed = any(m in answer_lower for m in fed_markers)
    has_fasting = any(m in answer_lower for m in fasting_markers)
    has_independent = any(m in answer_lower for m in independent_markers)
    has_both = any(m in answer_lower for m in both_markers)

    # Логика определения
    if has_both:
        mode = "both"
    elif has_fed and not has_fasting:
        mode = "fed"
    elif has_fasting and not has_fed:
        mode = "fasting"
    elif has_independent:
        # «Независимо от приёма пищи» → для БЭ стандарт натощак
        mode = "fasting"
    elif has_fed and has_fasting:
        # Оба упоминаются — возможно модифицированное высвобождение
        mode = "both"
    else:
        # Не определено → натощак (стандарт БЭ)
        mode = "fasting"

    mode_label = {"fasting": "натощак", "fed": "после еды", "both": "натощак и после еды"}
    print(f"💊 Режим приёма ({ref_drug_name}): {mode_label.get(mode, mode)}")

    return {
        "mode": mode,
        "raw_text": answer_text[:500],
        "source": "yandex_search",
    }