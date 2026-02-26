"""
utils/drug_info_parser.py — Парсер инструкции к препарату.

По названию референтного препарата:
1. Ищет инструкцию на vidal.ru / rlsnet.ru / etabl.ru
2. Парсит: вспомогательные вещества, условия хранения, состав, РУ ЛП, производитель
3. Возвращает dict с полями для подстановки в синопсис

Без LLM — регулярные выражения на структурированном HTML.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class DrugInfo:
    """Информация из инструкции к препарату."""
    drug_name: str = ""              # "Вемлиди®"
    inn: str = ""                     # "тенофовира алафенамид"
    dosage_form: str = ""             # "таблетки, покрытые плёночной оболочкой"
    dosage: str = ""                  # "25 мг"

    # Состав
    active_substance: str = ""        # "тенофовира алафенамида фумарат 28,04 мг"
    excipients: str = ""              # "лактозы моногидрат, целлюлоза микрокристаллическая, ..."
    excipients_coating: str = ""      # "поливиниловый спирт, титана диоксид, ..."
    composition_full: str = ""        # Полный состав на 1 таблетку

    # Условия
    storage_conditions: str = ""      # "При температуре не выше 30°С"
    shelf_life: str = ""              # "3 года"

    # Производитель и регистрация
    manufacturer: str = ""            # "Гилеад Сайенсиз Айелэнд ЮСи, Ирландия"
    ru_number: str = ""               # "004357" или полный "ЛП-№(004357)-(РГ-RU)"

    # Показания и пол
    indications: str = ""             # "Лечение хронического гепатита В..."
    suggested_sex: str = "males_only" # males_only / females_only / both

    # Режим приёма (из раздела «Способ применения»)
    suggested_intake: str = ""        # "fasting" / "fed" / "" (не определено)

    # Источник
    source_url: str = ""


def parse_drug_info_from_text(text: str, drug_name: str = "") -> DrugInfo:
    """
    Извлекает информацию из текста инструкции к препарату.

    Args:
        text: Текст страницы (plain text из HTML)
        drug_name: Название препарата для контекста

    Returns:
        DrugInfo с заполненными полями
    """
    info = DrugInfo(drug_name=drug_name)

    # ── Вспомогательные вещества ──
    # Паттерн: "Вспомогательные вещества:" или "вспомогательные вещества:"
    excip_patterns = [
        # etabl.ru формат (точка перед "Оболочка") — САМЫЙ СПЕЦИФИЧНЫЙ, первый
        r'[Вв]спомогательные\s+вещества\s*:\s*(?:ядро\s+таблетки\s*:\s*)?([^.]+\.?\s*[Оо]болочка\s+таблетки[^.]+)',
        # vidal.ru / rlsnet.ru формат (всё через ;)
        r'[Вв]спомогательные\s+вещества[:\s]*([^.]+(?:\.[^А-ЯA-Z\d])*)',
        # Минимальный fallback
        r'[Вв]спомогательные\s+вещества\s*:\s*(?:ядро\s+таблетки\s*:\s*)?([^.]+)',
    ]
    for pat in excip_patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            # Чистим от лишнего
            raw = re.sub(r'\s+', ' ', raw)

            # Ищем оболочку — может быть через ";", через ".", через ","
            coating_match = re.search(
                r'[;.,]\s*(?:[Оо]болочка\s+таблетки|[Сс]остав\s+(?:плёночной\s+|пленочной\s+)?оболочки|Опадрай)[:\s]*(.+)',
                raw, re.IGNORECASE
            )
            if coating_match:
                info.excipients_coating = coating_match.group(1).strip().rstrip('.')
                info.excipients = raw[:coating_match.start()].strip().rstrip(',;.')
            else:
                info.excipients = raw.rstrip('.')

            # Убираем "ядро таблетки:" prefix
            info.excipients = re.sub(r'^ядро\s+таблетки\s*:\s*', '', info.excipients, flags=re.IGNORECASE)

            # Убираем trailing мусор (номера страниц, разделы и т.д.)
            info.excipients = _clean_trailing(info.excipients)
            if info.excipients_coating:
                info.excipients_coating = _clean_trailing(info.excipients_coating)
            break

    # ── Действующее вещество (состав) ──
    active_patterns = [
        r'[Дд]ействующее\s+вещество[:\s]*([^\n.]+)',
        r'тенофовира\s+алафенамида?\s+(?:фумарат\s+)?[\d,]+\s*мг[^.]*',
        r'1\s+таб(?:летка|\.)\s*\n?\s*([^\n]+\d+\s*мг)',
    ]
    for pat in active_patterns:
        m = re.search(pat, text)
        if m:
            info.active_substance = m.group(1).strip() if m.lastindex else m.group(0).strip()
            info.active_substance = _clean_trailing(info.active_substance)
            break

    # ── Условия хранения ──
    storage_patterns = [
        r'[Уу]словия\s+хранения[:\s]*([^\n.]+(?:°[СC][^\n.]*)?)',
        r'[Хх]ранить[^.]*?при\s+температуре\s+не\s+выше\s+(\d+)\s*°[СC]',
        r'[Тт]емпература\s+хранения[:\s]*(?:от\s+\d+\s+до\s+)?(\d+)\s*°[СC]',
        r'при\s+температуре\s+не\s+выше\s+(\d+)\s*°[СC]',
    ]
    for pat in storage_patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if re.match(r'^\d+$', raw):
                info.storage_conditions = f"При температуре не выше {raw}°С"
            else:
                raw = re.sub(r'[Хх]ранить\s+в\s+недоступном\s+для\s+детей\s+месте[.,]\s*', '', raw)
                info.storage_conditions = raw.strip().rstrip('.')
                if info.storage_conditions and info.storage_conditions[0].islower():
                    info.storage_conditions = info.storage_conditions[0].upper() + info.storage_conditions[1:]
            info.storage_conditions = _clean_trailing(info.storage_conditions)
            break

    # Fallback: ищем "от X до Y °С"
    if not info.storage_conditions:
        m = re.search(r'от\s+(\d+)\s+до\s+(\d+)\s*°[СC]', text)
        if m:
            info.storage_conditions = f"При температуре от {m.group(1)} до {m.group(2)}°С"

    # ── РУ ЛП ──
    ru_patterns = [
        r'РУ[:\s]*(?:ЛП-)?[№#]?\s*\(?\s*(\d{5,7})\s*\)?',
        r'ЛП-[№#]\s*\(?\s*(\d{5,7})\s*\)?',
        r'ЛП-(\d{5,7})',
        r'Регистрационн[а-я]*\s+удостоверени[а-я]*[:\s]*(?:ЛП-)?[№#]?\s*\(?\s*(\d{5,7})',
    ]
    for pat in ru_patterns:
        m = re.search(pat, text)
        if m:
            info.ru_number = m.group(1)
            break

    # ── Производитель ──
    prod_patterns = [
        r'[Пп]роизвод(?:итель|ство)[:\s]*([^\n]+)',
        r'[Пп]роизведено[:\s]*([^\n]+)',
    ]
    for pat in prod_patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            # Берём первого производителя
            raw = re.split(r'\s+или\s+', raw)[0]
            raw = raw.rstrip('.')
            if len(raw) > 10:  # Не мусор
                info.manufacturer = _clean_trailing(raw)
                break

    # ── Лекарственная форма ──
    form_patterns = [
        r'[Лл]екарственная\s+форма[:\s]*([^\n]+)',
        r'[Тт]аблетки,?\s+покрытые\s+(?:плёночной\s+)?оболочкой',
    ]
    for pat in form_patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip() if m.lastindex else m.group(0).strip()
            info.dosage_form = raw.rstrip('.')
            break

    # ── Дозировка ──
    dose_patterns = [
        r'[Дд]озировка[:\s]*([^\n]+)',
        r'(\d+\s*мг)\s*:\s*\d+\s*шт',
    ]
    for pat in dose_patterns:
        m = re.search(pat, text)
        if m:
            info.dosage = m.group(1).strip().rstrip('.')
            break

    # ── Показания к применению ──
    indication_patterns = [
        # "Показания препарата Вемлиди®\n Лечение хронического..."
        r'[Пп]оказания[^.:\n]*?(?:препарата[^.:\n]*)?\s*\n\s*([А-Я][^\n]+(?:\n(?![А-Я][а-я]+(?:ое|ая|ие)?\s)[^\n]+)*)',
        # "Показания к применению: Лечение..."
        r'[Пп]оказания\s+(?:к\s+применению|активных\s+веществ)[^:]*?:\s*([^\n]+(?:\n(?![А-Я][а-я]+[:\s])[^\n]+)*)',
        # "Показания: Лечение..."
        r'[Пп]оказания[:\s]+([А-Я][^\n]+)',
    ]
    for pat in indication_patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            raw = re.sub(r'\s+', ' ', raw)
            # Обрезаем до первого заголовка следующей секции
            raw = re.split(r'\s*(?:Режим дозирования|Противопоказания|Способ применения|Побочные)', raw)[0]
            info.indications = raw.strip().rstrip('.')
            break

    # ── Определение пола для БЭ-исследования ──
    info.suggested_sex = _determine_sex(info.indications, text)

    # ── Определение режима приёма (натощак / после еды) ──
    info.suggested_intake = _determine_intake(text)

    # ── Полный состав ──
    if info.active_substance or info.excipients:
        parts = []
        if info.active_substance:
            parts.append(f"Действующее вещество: {info.active_substance}")
        if info.excipients:
            exc = info.excipients
            if info.excipients_coating:
                exc += f"; оболочка таблетки: {info.excipients_coating}"
            parts.append(f"Вспомогательные вещества: {exc}")
        info.composition_full = "\n".join(parts)

    return info


def _determine_sex(indications: str, full_text: str = "") -> str:
    """
    Определяет пол добровольцев для БЭ-исследования.

    Логика:
    1. Показания ТОЛЬКО для женщин (контрацепция, эндометриоз...) → females_only
    2. Показания ТОЛЬКО для мужчин (простатит, ЭД...) → males_only
    3. Тератогенность (категория X, REMS) → females_only
       НО: "противопоказан при беременности" — это НЕ тератогенность!
       Почти все препараты противопоказаны при беременности.
    4. Иначе → males_only (дефолт по ГОСТ)

    ВАЖНО: Тератогенность определяется по СПЕЦИФИЧНЫМ маркерам,
    а НЕ по общим фразам типа "противопоказан при беременности".

    Returns:
        "males_only", "females_only", или "both"
    """
    if not indications and not full_text:
        return "males_only"

    text = (indications or "").lower()
    full = (full_text or "").lower()

    # ── Шаг 1: Показания ТОЛЬКО для женщин ──
    # Ищем ТОЛЬКО в показаниях (text), не во всём тексте инструкции
    female_only_keywords = [
        r'контрацепци',
        r'противозачаточн',
        r'менструальн',
        r'дисменоре',
        r'аменоре',
        r'эндометриоз',
        r'мастопати',
        r'климакс',
        r'менопауз',
        r'постменопауз',
        r'вульвовагинальн',
        r'вагинальн\w+\s+(?:инфекц|кандидоз|дисбиоз)',
        r'миом\w+\s+матки',
        r'рак\w*\s+(?:молочной\s+железы|яичник|шейки\s+матки|эндометри)',
        r'бесплоди\w+\s+(?:у\s+)?женщин',
        r'(?:индукци|стимуляци)\w+\s+овуляции',
        r'эстроген\w*\s+(?:недостаточност|дефицит|замещен)',
        r'прогестерон\w*\s+недостаточност',
    ]

    for pat in female_only_keywords:
        if re.search(pat, text):
            return "females_only"

    # ── Шаг 2: Показания ТОЛЬКО для мужчин ──
    male_only_keywords = [
        r'простатит',
        r'аденом\w+\s+простаты',
        r'гиперплази\w+\s+предстательной',
        r'эректильн\w+\s+дисфункци',
        r'импотенци',
        r'рак\w*\s+предстательной',
        r'рак\w*\s+простаты',
        r'бесплоди\w+\s+(?:у\s+)?мужчин',
        r'тестостерон\w*\s+недостаточност',
        r'гипогонадизм',
    ]

    for pat in male_only_keywords:
        if re.search(pat, text):
            return "males_only"

    # ── Шаг 3: Тератогенность (СТРОГИЕ маркеры) ──
    # ТОЛЬКО специфичные признаки настоящих тератогенов:
    # - Категория X по FDA (не просто "противопоказан при беременности")
    # - Программа REMS / iPLEDGE
    # - Прямое указание на тератогенный эффект в показаниях
    # НЕ СЧИТАЕМ тератогенными:
    # - "противопоказан при беременности" (есть у 90% препаратов)
    # - "тест на беременность" (стандартная предосторожность)
    # - "два метода контрацепции" (может быть рекомендацией, не требованием)
    strict_teratogen_patterns = [
        r'категория\s+[xXхХ]\s+(?:по\s+)?(?:FDA|ФДА)',
        r'категория\s+действия\s+на\s+плод\s*[:\-–—]\s*[xXхХ]',
        r'программ\w+\s+(?:предотвращения|профилактики)\s+беременност\w+\s+\w+\s+обязательн',
        r'rems\b',
        r'ipledge',
        r'(?:доказанн|подтверждённ|установленн)\w+\s+тератоген',
        r'тератогенн\w+\s+(?:эффект|действи|свойств)',
    ]

    for pat in strict_teratogen_patterns:
        if re.search(pat, full):
            return "females_only"

    # Дефолт: мужчины (стандарт для БЭ по ГОСТ)
    return "males_only"


def _clean_trailing(s: str) -> str:
    """Убирает trailing мусор из распарсенной строки."""
    # Убираем номера секций, заголовки следующих разделов
    s = re.sub(r'\s*\d+\s+шт\.?\s*[-–].*$', '', s)
    s = re.sub(r'\s*Клинико-.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Фармак.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Описание\s+лекарств.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Показания.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Противопоказания.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Форма\s+выпуска.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Условия\s+отпуска.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Срок\s+годности.*$', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s*Хранить\s+в\s+недоступном.*$', '', s, flags=re.IGNORECASE)
    return s.strip()



def _determine_intake(text: str) -> str:
    """
    Определяет режим приёма препарата из текста инструкции.

    Returns:
        "fasting", "fed", или "" (не определено)
    """
    if not text:
        return ""

    t = text.lower()

    # Ищем раздел «Способ применения» или «Режим дозирования»
    section = ""
    for marker in [
        r'способ\s+применения\s+и\s+дозы?\s*[:\.]?\s*',
        r'режим\s+дозирования\s*[:\.]?\s*',
        r'способ\s+применения\s*[:\.]?\s*',
    ]:
        m = re.search(marker, t)
        if m:
            section = t[m.end():m.end() + 2000]
            break

    search_text = section if section else t

    # ── Шаг 1: "Независимо от приёма пищи" → fasting (стандарт БЭ) ──
    # Если препарат можно принимать и натощак и с едой,
    # БЭ стандартно проводится натощак
    independent_patterns = [
        r'независимо\s+от\s+(?:при[её]ма\s+)?пищи',
        r'вне\s+зависимости\s+от\s+(?:при[её]ма\s+)?пищи',
        r'без?\s+связи\s+с\s+(?:при[её]мом\s+)?пищ',
        r'с\s+пищей\s+или\s+без',
        r'без\s+пищи\s+или\s+с\s+пищей',
        r'с\s+едой\s+или\s+без',
        r'(?:can\s+be\s+taken\s+)?with\s+or\s+without\s+food',
        r'regardless\s+of\s+(?:food|meal)',
        r'irrespective\s+of\s+(?:food|meal)',
    ]
    for pat in independent_patterns:
        if re.search(pat, search_text):
            return "fasting"

    # ── Шаг 2: "С пищей" / "во время еды" → fed ──
    fed_patterns = [
        r'во\s+время\s+(?:при[её]ма\s+)?(?:высококалорийн|еды|пищи)',
        r'с\s+(?:высококалорийн|пищ|едой)',
        r'после\s+(?:при[её]ма\s+)?(?:высококалорийн|еды|пищи)',
        r'вместе\s+с\s+(?:едой|пищей)',
        r'одновременно\s+с\s+(?:едой|пищей)',
        r'принимать?\s+с\s+(?:пищей|едой)',
        r'перорально\s+с\s+(?:пищей|едой)',
        r'в\s+сутки\s+с\s+(?:пищей|едой)',
    ]

    # ── Шаг 3: "Натощак" → fasting ──
    fasting_patterns = [
        r'натощак',
        r'до\s+(?:приёма\s+)?(?:еды|пищи)',
        r'за\s+\d+\s*(?:мин|час).*?до\s+(?:еды|пищи)',
        r'на\s+(?:пустой|голодный)\s+желудок',
    ]

    for pat in fed_patterns:
        if re.search(pat, search_text):
            return "fed"

    for pat in fasting_patterns:
        if re.search(pat, search_text):
            return "fasting"

    return ""


def drug_info_to_dict(info: DrugInfo) -> Dict[str, str]:
    """Конвертирует DrugInfo в dict для подстановки в синопсис."""
    excipients_full = info.excipients
    if info.excipients_coating:
        excipients_full += f"; оболочка таблетки: {info.excipients_coating}"

    return {
        "ref_excipients": excipients_full,
        "ref_storage_conditions": info.storage_conditions,
        "ref_composition": info.composition_full,
        "ref_manufacturer": info.manufacturer,
        "ref_ru_number": info.ru_number,
        "ref_active_substance": info.active_substance,
        "ref_dosage_form": info.dosage_form,
        "ref_dosage": info.dosage,
        "ref_indications": info.indications,
        "suggested_sex": info.suggested_sex,
        "suggested_intake": info.suggested_intake,
    }


# ── Поиск и fetch (async-обёртка) ──

async def fetch_drug_info(
    drug_name: str,
    inn: str = "",
    dosage: str = "",
) -> DrugInfo:
    """
    Ищет и парсит инструкцию к препарату из интернета.

    Стратегия (в порядке приоритета):
    1. vidal.ru по торговому названию (транслитерация)
    2. vidal.ru по английскому названию (если латиница в названии)
    3. vidal.ru по МНН
    4. vidal.ru поиск по сайту
    5. rlsnet.ru поиск
    """
    import aiohttp

    clean_name = re.sub(r'[®™©]', '', drug_name).strip()
    clean_name_lower = clean_name.lower()

    # Формируем список URL для поиска
    urls_to_try = []

    # 1. Vidal по транслитерации торгового названия
    vidal_slug = _transliterate(clean_name_lower)
    urls_to_try.append(f"https://www.vidal.ru/drugs/{vidal_slug}")

    # 2. Если название — кириллица, пробуем варианты окончаний
    #    "эриведж" → "erivedzh" не работает, но "erivedge" может
    if any('\u0400' <= c <= '\u04ff' for c in clean_name_lower):
        # Попробуем убрать/заменить проблемные окончания
        alt_slugs = set()
        slug = vidal_slug
        # "zh" → "ge" (эриведж → erivedge)
        if slug.endswith('zh'):
            alt_slugs.add(slug[:-2] + 'ge')
            alt_slugs.add(slug[:-2] + 'j')
        # "ks" → "x", "ts" → "c"
        alt_slugs.add(slug.replace('ks', 'x'))
        alt_slugs.add(slug.replace('ts', 'c'))
        for alt in alt_slugs:
            if alt != vidal_slug:
                urls_to_try.append(f"https://www.vidal.ru/drugs/{alt}")

    # 3. Vidal по МНН
    if inn:
        inn_clean = re.sub(r'[®™©]', '', inn).strip().lower()
        inn_words = inn_clean.split()
        # Первое слово МНН
        inn_slug = _transliterate(inn_words[0])
        if inn_slug != vidal_slug:
            urls_to_try.append(f"https://www.vidal.ru/drugs/{inn_slug}")
        # Полное МНН через дефис
        if len(inn_words) > 1:
            full_slug = _transliterate("-".join(inn_words[:2]))
            urls_to_try.append(f"https://www.vidal.ru/drugs/{full_slug}")

    # 4. Поиск по сайту vidal
    urls_to_try.append(
        f"https://www.vidal.ru/search?t=all&q={clean_name.replace(' ', '+')}"
    )

    # 5. Vidal по МНН (molecule page — часто содержит полную ФК)
    if inn:
        inn_slug = _transliterate(inn.strip().lower().split()[0])
        urls_to_try.append(f"https://www.vidal.ru/drugs/molecule/{inn_slug}")

    # 6. Medi.ru — полная инструкция с фармакокинетикой
    urls_to_try.append(
        f"https://medi.ru/instrukciya/{_transliterate(clean_name_lower)}/"
    )
    if inn:
        inn_slug_full = _transliterate(inn.strip().lower().replace(' ', '-'))
        urls_to_try.append(f"https://medi.ru/instrukciya/{inn_slug_full}/")

    # 7. RLS по МНН (active-substance — содержит полную ФК)
    if inn:
        inn_en = ""
        try:
            from inn_utils import resolve_inn_en
            inn_en = resolve_inn_en(inn)
        except ImportError:
            try:
                from app.utils.inn_utils import resolve_inn_en
                inn_en = resolve_inn_en(inn)
            except ImportError:
                pass
        if inn_en:
            inn_en_slug = inn_en.lower().replace(' ', '-')
            urls_to_try.append(
                f"https://www.rlsnet.ru/active-substance/{inn_en_slug}"
            )

    # 8. ГРЛС (Государственный реестр лекарственных средств)
    if inn:
        inn_encoded = inn.replace(' ', '+')
        urls_to_try.append(
            f"https://grls.rosminzdrav.ru/Grls_View_v2.aspx?routingGuid=&t=&q={inn_encoded}"
        )
    urls_to_try.append(
        f"https://grls.rosminzdrav.ru/Grls_View_v2.aspx?routingGuid=&t=&q={clean_name.replace(' ', '+')}"
    )

    # 6. RLS
    urls_to_try.append(
        f"https://www.rlsnet.ru/search?query={clean_name.replace(' ', '+')}"
    )

    # 6. Etabl.ru по торговому названию
    urls_to_try.append(
        f"https://etabl.ru/search/?query={clean_name.replace(' ', '+')}"
    )

    # 7. Etabl.ru по МНН
    if inn:
        inn_clean = re.sub(r'[®™©]', '', inn).strip()
        urls_to_try.append(
            f"https://etabl.ru/search/?query={inn_clean.replace(' ', '+')}"
        )

    best_info = DrugInfo(drug_name=drug_name)

    async with aiohttp.ClientSession() as session:
        for url in urls_to_try:
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                    allow_redirects=True,
                ) as resp:
                    print(f"    → {url} → HTTP {resp.status}")
                    if resp.status != 200:
                        continue

                    text = await resp.text()

                    # Если это страница поиска — извлекаем ссылку
                    if '/search' in url:
                        if 'vidal.ru' in url:
                            drug_links = re.findall(
                                r'href="(/drugs/[a-z0-9_-]+)"', text, re.IGNORECASE
                            )
                            seen = set()
                            for link in drug_links:
                                if link not in seen and '/drugs/' in link:
                                    seen.add(link)
                                    drug_url = f"https://www.vidal.ru{link}"
                                    print(f"      → Найдена ссылка: {drug_url}")
                                    try:
                                        async with session.get(
                                            drug_url,
                                            timeout=aiohttp.ClientTimeout(total=15),
                                            headers={"User-Agent": "Mozilla/5.0 (Macintosh)"},
                                            allow_redirects=True,
                                        ) as dr:
                                            if dr.status == 200:
                                                plain = _strip_html(await dr.text())
                                                if len(plain) > 500:
                                                    info = parse_drug_info_from_text(plain, drug_name)
                                                    _merge_drug_info(best_info, info)
                                                    if info.excipients or info.storage_conditions:
                                                        best_info.source_url = str(dr.url)
                                                        _print_drug_info(best_info)
                                    except Exception:
                                        pass
                                    if len(seen) >= 2:
                                        break
                        continue

                    plain = _strip_html(text)
                    if len(plain) < 300:
                        continue
                    info = parse_drug_info_from_text(plain, drug_name)
                    has_new = _merge_drug_info(best_info, info)
                    if has_new:
                        if not best_info.source_url:
                            best_info.source_url = str(resp.url)
                        print(f"      ✅ excip={bool(info.excipients)}, storage={bool(info.storage_conditions)} ({resp.url})")
            except Exception as e:
                print(f"    → {url} → {type(e).__name__}: {e}")
                continue

            # Если собрали excipients и storage — хватит
            if best_info.excipients and best_info.storage_conditions:
                break

    has_any = bool(
        best_info.excipients or best_info.storage_conditions
        or best_info.manufacturer or best_info.suggested_sex != "males_only"
    )
    if has_any:
        _print_drug_info(best_info)
        return best_info

    logger.warning(f"⚠️ Could not fetch drug info for '{drug_name}'")
    return DrugInfo(drug_name=drug_name)


def _merge_drug_info(target: DrugInfo, source: DrugInfo) -> bool:
    """Мержит данные из source в target. Возвращает True если что-то новое добавлено."""
    changed = False
    for field in [
        'excipients', 'excipients_coating', 'active_substance',
        'composition_full', 'storage_conditions', 'shelf_life',
        'manufacturer', 'ru_number', 'indications',
        'dosage_form', 'dosage', 'inn',
    ]:
        if getattr(source, field) and not getattr(target, field):
            setattr(target, field, getattr(source, field))
            changed = True
    if source.suggested_sex != "males_only" and target.suggested_sex == "males_only":
        target.suggested_sex = source.suggested_sex
        changed = True
    if source.suggested_intake and not target.suggested_intake:
        target.suggested_intake = source.suggested_intake
        changed = True
    return changed


def _print_drug_info(info: DrugInfo):
    """Выводит отладочную информацию."""
    print(f"      ✅ Найдено из инструкции:")
    print(f"         Excip: {'да' if info.excipients else 'нет'}, "
          f"Хранение: {info.storage_conditions or 'нет'}")
    print(f"         Пол: {info.suggested_sex}, "
          f"Приём: {info.suggested_intake or 'не определён'}")


def fetch_drug_info_sync(
    drug_name: str,
    inn: str = "",
    dosage: str = "",
    page_text: str = "",
) -> DrugInfo:
    """
    Синхронная версия — парсит из уже загруженного текста
    или пытается загрузить через requests.
    """
    if page_text:
        plain = _strip_html(page_text)
        return parse_drug_info_from_text(plain, drug_name)

    try:
        import requests
        clean_name = re.sub(r'[®™©]', '', drug_name).strip()
        vidal_slug = _transliterate(clean_name.lower())
        url = f"https://www.vidal.ru/drugs/{vidal_slug}"

        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            plain = _strip_html(resp.text)
            info = parse_drug_info_from_text(plain, drug_name)
            info.source_url = url
            return info
    except Exception as e:
        logger.debug(f"Sync fetch failed: {e}")

    return DrugInfo(drug_name=drug_name)


def _strip_html(html: str) -> str:
    """Убирает HTML-теги, оставляет текст."""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text


def _transliterate(name: str) -> str:
    """Простая транслитерация для URL vidal.ru."""
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    result = []
    for ch in name:
        if ch in table:
            result.append(table[ch])
        elif ch.isalnum() or ch in '-_':
            result.append(ch)
        elif ch == ' ':
            result.append('-')
    return ''.join(result)