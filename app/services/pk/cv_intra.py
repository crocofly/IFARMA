"""
services/pk/cv_intra.py — Модуль определения CVintra.

ДВА МЕТОДА:
1. Поиск готового CVintra из литературы (PubMed, FDA Guidance)
2. Расчёт CVintra из опубликованных 90% CI

ПРИОРИТЕТ (ИЗМЕНЁН — PubMed ПЕРВЫМ!):
1. Пользователь передал --cv-intra → используем
2. PubMed: статья с 90% CI из BE-исследования → расчёт CVintra
3. PubMed: статья с прямым CVintra из BE-исследования
4. FDA/EMA BE Guidance Document → CVintra (НО: 30% = порог, пропускаем)
5. Широкий поиск по интернету
6. Default 30% (консервативная оценка)

ВАЖНО: Поиск ведётся по БАЗОВОМУ МНН без соли!
    "тенофовира алафенамид фумарат" → "тенофовира алафенамид"
    "tenofovir alafenamide fumarate" → "tenofovir alafenamide"

ФОРМУЛА РАСЧЁТА CVintra ИЗ 90% CI:
    σ²w = MSE (средний квадрат ошибки из ANOVA лог-данных)
    CVintra = √(exp(σ²w) − 1) × 100%
    Эквивалентно функции CVfromCI() из R-пакета PowerTOST.

ИСПРАВЛЕНИЕ v2 (_extract_cv_from_text):
    Sentence-boundary контекст вместо regex-паттернов.
    Фильтрация inter-subject / between-subject CV.
    Приоритизация intra-subject + Cmax.
"""

import math
import os
import re
import requests
from typing import Optional, Tuple, Dict, List
from scipy import stats
from dataclasses import dataclass


YANDEX_GEN_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/gen/search"


# ════════════════════════════════════════════════════════
# НОРМАЛИЗАЦИЯ МНН — УБИРАЕМ СОЛЬ, ПЕРЕВОДИМ ru→en
# ════════════════════════════════════════════════════════

# Импортируем из inn_utils (авторитетный источник)
try:
    from app.utils.inn_utils import normalize_inn, strip_salt_ru, strip_salt_en, resolve_inn_en
    _HAS_INN_UTILS = True
except ImportError:
    try:
        from inn_utils import normalize_inn, strip_salt_ru, strip_salt_en, resolve_inn_en
        _HAS_INN_UTILS = True
    except ImportError:
        _HAS_INN_UTILS = False


# Fallback если inn_utils не найден
if not _HAS_INN_UTILS:
    import re as _re
    _SALT_EN = [
        "fumarate", "hemifumarate", "hydrochloride", "dihydrochloride",
        "maleate", "mesylate", "besylate", "tartrate", "succinate",
        "citrate", "phosphate", "sulfate", "acetate", "bromide",
        "chloride", "tosylate", "sodium", "potassium", "calcium",
        "magnesium", "monohydrate", "dihydrate",
    ]
    _SALT_RU = [
        "фумарат", "гидрохлорид", "малеат", "мезилат", "безилат",
        "тартрат", "сукцинат", "цитрат", "фосфат", "сульфат",
        "ацетат", "бромид", "хлорид", "тозилат", "натрия",
        "калия", "кальция", "магния", "моногидрат", "дигидрат",
    ]
    def strip_salt_en(s):
        r = s.strip().lower()
        for salt in sorted(_SALT_EN, key=len, reverse=True):
            if r.endswith(salt): r = r[:-len(salt)].strip()
        return r or s.strip()
    def strip_salt_ru(s):
        r = s.strip().lower()
        for salt in sorted(_SALT_RU, key=len, reverse=True):
            if r.endswith(salt): r = r[:-len(salt)].strip()
        return r or s.strip()
    def normalize_inn(inn_ru, inn_en=None):
        return strip_salt_ru(inn_ru), strip_salt_en(inn_en) if inn_en else ""
    def resolve_inn_en(inn_ru):
        return ""  # без словаря не можем перевести


@dataclass
class CVintraResult:
    """Результат определения CVintra."""
    cv_intra: float
    source: str
    source_detail: str
    confidence: str
    method: str
    ci_data: Optional[Dict] = None


# ════════════════════════════════════════════════════════
# РАСЧЁТ CVintra ИЗ 90% CI
# ════════════════════════════════════════════════════════

def cv_from_ci(
    lower: float, upper: float, n: int,
    design: str = "2x2x2", alpha: float = 0.05,
) -> float:
    """
    CVintra из 90% CI. Эквивалент CVfromCI() из PowerTOST.
    """
    if lower > 2:
        lower = lower / 100
    if upper > 2:
        upper = upper / 100
    if lower <= 0 or upper <= 0 or lower >= upper:
        raise ValueError(f"Некорректные границы CI: [{lower}, {upper}]")
    if n < 4:
        raise ValueError(f"Слишком мало добровольцев: n={n}")

    df = _get_df(n, design)
    halfwidth = (math.log(upper) - math.log(lower)) / 2
    t_val = stats.t.ppf(1 - alpha, df)
    mse = (halfwidth ** 2) * n / (2 * t_val ** 2)
    cv = math.sqrt(math.exp(mse) - 1) * 100
    return round(cv, 1)


def _get_df(n: int, design: str) -> int:
    if design in ("2x2x2", "2x2"):
        return n - 2
    elif design in ("2x2x4", "2x4x4"):
        return 3 * (n // 2) - 3
    elif design in ("2x2x3",):
        return 2 * (n // 2) - 2
    elif design == "parallel":
        return n - 2
    else:
        return n - 2


# ════════════════════════════════════════════════════════
# ПОИСК CVintra
# ════════════════════════════════════════════════════════

def search_cv_intra(
    inn_en: str,
    inn_ru: str = "",
    ref_drug_name: str = "",
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> CVintraResult:
    """
    Комплексный поиск CVintra.

    ВАЖНО:
    - ref_drug_name ИГНОРИРУЕТСЯ. CVintra — свойство МНН, не бренда.
    - Если inn_en пустой — автоматически переводим из inn_ru через словарь.
    - Поиск по базовому МНН (без соли), затем по полному.

    Порядок:
    1. PubMed CI → расчёт CVintra (самый надёжный)
    2. PubMed direct CVintra
    3. FDA BE Guidance
    4. Широкий интернет
    5. Повтор 1-4 с полным МНН (с солью)
    6. Default = 30%
    """
    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        return _default_result()

    # ═══════════════════════════════════════
    # НОРМАЛИЗАЦИЯ: убираем соль + авто-перевод ru→en
    # ═══════════════════════════════════════
    inn_ru_base, inn_en_base = normalize_inn(inn_ru, inn_en if inn_en else None)

    # Если normalize_inn не нашёл перевод — пробуем resolve_inn_en
    if not inn_en_base and inn_ru:
        inn_en_base = resolve_inn_en(inn_ru)

    # Основной термин — английский без соли
    search_base = inn_en_base or (strip_salt_en(inn_en) if inn_en else "") or inn_ru_base or inn_ru
    # Полный термин (с солью) — fallback
    search_full = inn_en or inn_ru

    if search_base.lower() != search_full.lower():
        print(f"  МНН для поиска: '{search_base}' (базовый), '{search_full}' (полный)")
    else:
        print(f"  МНН для поиска: '{search_base}'")

    # ═══════════════════════════════════════
    # РАУНД 1: базовый МНН (без соли)
    # ═══════════════════════════════════════
    result = _search_all_sources(search_base, folder_id, api_key)
    if result:
        return result

    # ═══════════════════════════════════════
    # РАУНД 2: полный МНН (с солью)
    # ═══════════════════════════════════════
    if search_full.lower() != search_base.lower():
        print(f"  ↳ Не найдено по '{search_base}'. Пробуем '{search_full}'...")
        result = _search_all_sources(search_full, folder_id, api_key)
        if result:
            return result

    # ═══════════════════════════════════════
    # РАУНД 3: русский МНН (fallback)
    # ═══════════════════════════════════════
    for term in _unique([inn_ru_base, inn_ru]):
        if term and term.lower() not in (search_base.lower(), search_full.lower()):
            print(f"  ↳ Пробуем русский МНН: '{term}'...")
            result = _search_all_sources(term, folder_id, api_key)
            if result:
                return result

    return _default_result()


def _search_all_sources(
    term: str, folder_id: str, api_key: str,
) -> Optional[CVintraResult]:
    """Поиск CVintra по одному термину во всех источниках."""
    # 1. PubMed CI → расчёт
    result = _search_pubmed_ci(term, folder_id, api_key)
    if result:
        return result

    # 2. PubMed direct
    result = _search_pubmed_direct(term, folder_id, api_key)
    if result:
        return result

    # 3. FDA BE Guidance
    result = _search_fda_guidance(term, folder_id, api_key)
    if result:
        return result

    # 4. Broad internet
    result = _search_broad_internet(term, folder_id, api_key)
    if result:
        return result

    return None


def _search_fda_guidance(
    term: str, folder_id: str, api_key: str,
) -> Optional[CVintraResult]:
    """
    Ищет CVintra в FDA/EMA BE Guidance Documents.

    FIX #3: Если CVintra = 30.0% — пропускаем (это порог HVD, не реальный CV).
    """
    queries = [
        f'Notes on the Design of Bioequivalence Study {term}',
        f'bioequivalence study {term} within-subject variability Cmax coefficient of variation',
        f'{term} generic bioequivalence Cmax intra-individual variability percent',
    ]

    for query in queries:
        answer = _call_yandex_world(query, folder_id, api_key)
        if not answer or "not found" in answer.lower():
            continue

        cv = _extract_cv_from_text(answer)
        if cv is not None:
            source_name = _extract_source_name(answer) or f"FDA BE Guidance for {term}"

            # FIX #3: 30.0% из Guidance — скорее всего порог HVD
            if cv == 30.0:
                print(
                    f"   ⚠️  BE Guidance ({term}): CVintra=30.0% — "
                    f"вероятно порог HVD, а не реальный CVintra. Пропускаем."
                )
                continue

            print(f"   ✅ BE Guidance ({term}): CVintra={cv}% [{source_name}]")
            return CVintraResult(
                cv_intra=cv, source="guidance",
                source_detail=source_name,
                confidence="high", method="lookup",
            )

    print(f"   ⚠️  BE Guidance: не найден для '{term}'")
    return None


def _search_pubmed_ci(
    term: str, folder_id: str, api_key: str,
) -> Optional[CVintraResult]:
    """Ищет 90% CI из PubMed BE-статей → расчёт CVintra."""
    queries = [
        f'{term} bioequivalence study 90% confidence interval Cmax results',
        f'{term} bioequivalence Cmax AUC 90 CI healthy volunteers crossover',
    ]

    for query in queries:
        answer = _call_yandex_world(query, folder_id, api_key)
        if not answer:
            continue

        ci = _extract_ci_from_text(answer)
        if ci is None:
            continue

        lower, upper, n, design = ci
        try:
            cv = cv_from_ci(lower, upper, n, design)
        except (ValueError, ZeroDivisionError) as e:
            print(f"   ⚠️  CVintra из CI: ошибка расчёта: {e}")
            continue

        print(
            f"   ✅ PubMed CI ({term}): 90% CI=[{lower:.2f}, {upper:.2f}], "
            f"n={n}, design={design} → CVintra={cv}%"
        )
        return CVintraResult(
            cv_intra=cv, source="pubmed_ci",
            source_detail=f"Calculated from 90% CI [{lower:.2f}-{upper:.2f}], n={n}",
            confidence="high", method="calculated_from_ci",
            ci_data={"lower": lower, "upper": upper, "n": n, "design": design},
        )

    return None


def _search_pubmed_direct(
    term: str, folder_id: str, api_key: str,
) -> Optional[CVintraResult]:
    """Ищет прямое значение CVintra из PubMed."""
    queries = [
        f'{term} bioequivalence intra-subject variability Cmax coefficient of variation',
        f'{term} pharmacokinetic variability within-subject Cmax bioequivalence study',
    ]

    for query in queries:
        answer = _call_yandex_world(query, folder_id, api_key)
        if not answer:
            continue

        cv = _extract_cv_from_text(answer)
        if cv is not None:
            source_name = _extract_source_name(answer) or f"PubMed: {term} bioequivalence"
            print(f"   ✅ PubMed direct ({term}): CVintra={cv}% [{source_name}]")
            return CVintraResult(
                cv_intra=cv, source="pubmed_direct",
                source_detail=source_name,
                confidence="medium", method="lookup",
            )

    return None


def _search_broad_internet(
    term: str, folder_id: str, api_key: str,
) -> Optional[CVintraResult]:
    """Широкий поиск по интернету — последняя попытка."""
    queries = [
        f'{term} bioequivalence Cmax intra-subject variability coefficient of variation',
        f'{term} generic bioequivalence study sample size within-subject variability',
        f'{term} bioequivalence 90 confidence interval Cmax healthy volunteers',
        f'{term} pharmacokinetics Cmax high variability bioequivalence',
    ]

    for query in queries:
        answer = _call_yandex_world(query, folder_id, api_key)
        if not answer:
            continue

        cv = _extract_cv_from_text(answer)
        if cv is not None:
            source_name = _extract_source_name(answer) or f"Internet search: {term}"
            print(f"   ✅ Broad search ({term}): CVintra={cv}% [{source_name}]")
            return CVintraResult(
                cv_intra=cv, source="internet",
                source_detail=source_name,
                confidence="low", method="lookup",
            )

        ci = _extract_ci_from_text(answer)
        if ci is not None:
            lower, upper, n, design = ci
            try:
                cv = cv_from_ci(lower, upper, n, design)
                print(
                    f"   ✅ Broad search CI ({term}): "
                    f"90% CI=[{lower:.2f}, {upper:.2f}], n={n} → CVintra={cv}%"
                )
                return CVintraResult(
                    cv_intra=cv, source="internet_ci",
                    source_detail=f"Internet: 90% CI [{lower:.2f}-{upper:.2f}], n={n}",
                    confidence="low", method="calculated_from_ci",
                    ci_data={"lower": lower, "upper": upper, "n": n, "design": design},
                )
            except (ValueError, ZeroDivisionError):
                continue

    print(f"   ⚠️  Broad search: ничего не найдено для '{term}'")
    return None


# ════════════════════════════════════════════════════════
# ПАРСИНГ ОТВЕТОВ (ИСПРАВЛЕНО v2 — sentence-boundary)
# ════════════════════════════════════════════════════════

def _extract_cv_from_text(text: str) -> Optional[float]:
    """
    Извлекает CVintra из текста с контекстной фильтрацией.

    ИСПРАВЛЕНИЕ v2: Sentence-boundary контекст.
    Контекст определяется ВНУТРИ ПРЕДЛОЖЕНИЯ (от точки до точки),
    что предотвращает «утечку» контекста из соседних предложений.

    Приоритет бакетов:
      1. intra-subject + Cmax  → ЛУЧШЕЕ
      2. intra-subject         → ХОРОШЕЕ
      3. Cmax (без intra)      → OK
      4. Прочие                → FALLBACK

    Фильтрует:
      - inter-subject / between-subject → SKIP
      - AUC-контекст → не путать с Cmax
      - 30.0% → порог HVD, а не реальный CVintra
    """

    BAD_CONTEXT = re.compile(
        r'between.?subject|inter.?subject|inter.?individual|'
        r'межиндивидуальн|между\s*субъект|between.?group',
        re.IGNORECASE
    )
    INTRA_CONTEXT = re.compile(
        r'within.?subject|intra.?subject|intra.?individual|'
        r'внутрииндивидуальн|CVintra|CVw[RrTt]?[\s=]|intra-subject',
        re.IGNORECASE
    )
    CMAX_CONTEXT = re.compile(
        r'Cmax|C_?max|peak\s+concentr|максимальн\w+\s+концентр',
        re.IGNORECASE
    )
    AUC_CONTEXT = re.compile(
        r'\bAUC\b|area\s+under|площад\w+\s+под\s+кривой',
        re.IGNORECASE
    )

    intra_cmax = []
    intra_other = []
    general_cmax = []
    general_other = []

    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%', text):
        val = float(m.group(1))

        # Базовая фильтрация
        if not (5 <= val <= 120):
            continue
        if val == 30.0:
            continue  # 30% — скорее всего порог HVD

        # ── Контекст в пределах ТЕКУЩЕГО предложения ──
        # Начало предложения: предыдущая точка
        before_text = text[:m.start()]
        sent_start = before_text.rfind('.')
        sent_start = sent_start + 1 if sent_start != -1 else 0

        # Конец предложения: следующая точка
        after_text = text[m.end():]
        sent_end_rel = after_text.find('.')
        sent_end = m.end() + sent_end_rel if sent_end_rel != -1 else len(text)

        ctx_before = text[sent_start:m.end()]    # От начала предложения до числа
        ctx_after = text[m.end():sent_end]        # От числа до конца предложения

        # Фильтруем inter-subject / between-subject
        if BAD_CONTEXT.search(ctx_before):
            continue

        # Определяем тип
        is_intra = bool(INTRA_CONTEXT.search(ctx_before))
        is_cmax = bool(CMAX_CONTEXT.search(ctx_before + ctx_after))

        # AUC-контекст ПОСЛЕ числа → это не Cmax
        if AUC_CONTEXT.search(ctx_after):
            is_cmax = False
        # AUC-контекст ДО числа без Cmax → тоже не Cmax
        if AUC_CONTEXT.search(ctx_before) and not CMAX_CONTEXT.search(ctx_before):
            is_cmax = False

        # Классифицируем по бакетам
        if is_intra and is_cmax:
            intra_cmax.append(val)
        elif is_intra:
            intra_other.append(val)
        elif is_cmax:
            general_cmax.append(val)
        else:
            general_other.append(val)

    # Приоритет: intra+Cmax > intra > Cmax > other
    # Берём ПЕРВОЕ найденное значение из бакета (порядок в тексте = порядок
    # упоминания в источнике). НЕ max() — max может взять значение из 
    # соседнего контекста (другой препарат в таблице, inter-subject и т.п.)
    for bucket in [intra_cmax, intra_other, general_cmax, general_other]:
        if bucket:
            return round(bucket[0], 1)

    # Fallback: "CV = 0.XX" формат (без %)
    decimal_match = re.search(r'CV\s*=\s*0\.(\d{2,})', text)
    if decimal_match:
        val = float(f"0.{decimal_match.group(1)}") * 100
        if 5 <= val <= 120 and val != 30.0:
            return round(val, 1)

    return None


def _extract_ci_from_text(text: str) -> Optional[Tuple[float, float, int, str]]:
    """Извлекает 90% CI, N и дизайн из текста."""
    ci_patterns = [
        r'90\s*%\s*CI[:\s]*\[?(\d+\.?\d*)\s*[-–,]\s*(\d+\.?\d*)\]?',
        r'confidence\s+interval[:\s]*(\d+\.?\d*)\s*(?:to|[-–])\s*(\d+\.?\d*)',
        r'lower[:\s]*(\d+\.?\d*)[^.]*upper[:\s]*(\d+\.?\d*)',
        r'\[(\d+\.?\d*)\s*%?\s*[-–,]\s*(\d+\.?\d*)\s*%?\]',
    ]

    lower, upper = None, None
    for pattern in ci_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lower = float(match.group(1))
            upper = float(match.group(2))
            break

    if lower is None or upper is None:
        return None

    if lower > 2:
        lower = lower / 100
    if upper > 2:
        upper = upper / 100

    if not (0.5 < lower < 1.5 and 0.5 < upper < 1.5 and lower < upper):
        return None

    n = None
    n_patterns = [
        r'(?:n\s*=|subjects?|participants?|volunteers?)[:\s]*(\d+)',
        r'(\d+)\s*(?:subjects?|participants?|volunteers?|healthy)',
    ]
    for pattern in n_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = int(match.group(1))
            if 6 <= val <= 200:
                n = val
                break

    if n is None:
        return None

    design = "2x2x2"
    text_lower = text.lower()
    if any(k in text_lower for k in ["4-period", "4 period", "full replicate", "2x2x4"]):
        design = "2x2x4"
    elif any(k in text_lower for k in ["3-period", "3 period", "partial replicate", "2x2x3"]):
        design = "2x2x3"
    elif any(k in text_lower for k in ["parallel"]):
        design = "parallel"

    return (lower, upper, n, design)


def _extract_source_name(text: str) -> Optional[str]:
    """Извлекает название документа/статьи."""
    patterns = [
        r'Notes on the Design[^.\n]+',
        r'Product[- ]Specific Guidance[^.\n]+',
        r'Guidance Document[^.\n]+',
        r'PMID[:\s]*\d+',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


# ════════════════════════════════════════════════════════
# УТИЛИТЫ
# ════════════════════════════════════════════════════════

def _call_yandex_world(query: str, folder_id: str, api_key: str) -> str:
    """Вызов Yandex GenSearch."""
    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folder_id": folder_id,
    }
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(YANDEX_GEN_SEARCH_URL, json=body, headers=headers, timeout=25)
        if resp.status_code != 200:
            print(f"   ⚠️  Yandex HTTP {resp.status_code}: {resp.text[:200]}")
            return ""
        data = resp.json()

        if isinstance(data, list):
            data = data[0] if data else {}

        message = data.get("message", {})
        if isinstance(message, list):
            message = message[0] if message else {}
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        parts.append(str(item.get("content", item.get("text", ""))))
                    elif isinstance(item, str):
                        parts.append(item)
                content = " ".join(parts)
        else:
            content = ""

        sources = data.get("sources", [])
        if sources:
            source_urls = []
            for s in sources:
                if isinstance(s, dict):
                    url = s.get("url", "")
                    title = s.get("title", "")
                    if url:
                        source_urls.append(f"[SOURCE: {title} | {url}]")
            if source_urls:
                content += "\n" + "\n".join(source_urls)

        return content if isinstance(content, str) else ""
    except Exception as e:
        print(f"   ⚠️  Yandex Search: {e}")
        return ""


def _unique(items: list) -> list:
    """Уникальные непустые элементы."""
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _default_result() -> CVintraResult:
    """Результат по умолчанию если ничего не найдено."""
    return CVintraResult(
        cv_intra=30.0,
        source="default",
        source_detail="Консервативная оценка (ничего не найдено)",
        confidence="low",
        method="default",
    )


# ════════════════════════════════════════════════════════
# ПОИСК ФК-ПАРАМЕТРОВ (T½, Tmax, Cmax) ПО PUBMED
# ════════════════════════════════════════════════════════

@dataclass
class PKParamsResult:
    """Результат поиска ФК-параметров."""
    t_half_hours: Optional[float] = None
    tmax_hours: Optional[float] = None
    cmax_value: Optional[float] = None
    cmax_unit: str = ""
    source: str = ""
    source_detail: str = ""


def search_pk_params(
    inn_en: str,
    inn_ru: str = "",
    folder_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> PKParamsResult:
    """
    Поиск T½, Tmax, Cmax по PubMed/FDA/интернету.
    Использует тот же Yandex Search API что и CVintra.
    """
    folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID", "")
    api_key = api_key or os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        return PKParamsResult()

    inn_ru_base, inn_en_base = normalize_inn(inn_ru, inn_en if inn_en else None)
    if not inn_en_base and inn_ru:
        inn_en_base = resolve_inn_en(inn_ru)
    term = inn_en_base or inn_en or inn_ru_base or inn_ru

    queries = [
        f'{term} pharmacokinetics half-life Cmax Tmax single dose healthy volunteers',
        f'{term} half-life elimination terminal single oral dose pharmacokinetic parameters',
        f'{term} pharmacokinetic profile AUC Cmax Tmax elimination half-life hours',
    ]

    # Русские запросы — ищут по инструкции/ГРЛС
    inn_ru_term = inn_ru_base or inn_ru
    if inn_ru_term:
        queries.extend([
            f'{inn_ru_term} период полувыведения фармакокинетика инструкция',
            f'{inn_ru_term} T1/2 фармакокинетика однократный приём',
        ])

    result = PKParamsResult()

    for query in queries:
        answer = _call_yandex_world(query, folder_id, api_key)
        if not answer:
            continue

        # Извлекаем T½
        if result.t_half_hours is None:
            t_half = _extract_t_half_from_text(answer)
            if t_half is not None:
                result.t_half_hours = t_half
                result.source = "pubmed_pk"
                result.source_detail = _extract_source_name(answer) or f"PubMed PK: {term}"
                print(f"   ✅ PubMed PK ({term}): T½={t_half} ч [{result.source_detail}]")

        # Извлекаем Tmax
        if result.tmax_hours is None:
            tmax = _extract_tmax_from_text(answer)
            if tmax is not None:
                result.tmax_hours = tmax

        # Извлекаем Cmax
        if result.cmax_value is None:
            cmax, unit = _extract_cmax_from_text(answer)
            if cmax is not None:
                result.cmax_value = cmax
                result.cmax_unit = unit

        # Если нашли T½ — основная цель достигнута
        if result.t_half_hours is not None:
            break

    return result


def _extract_t_half_from_text(text: str) -> Optional[float]:
    """
    Извлекает T½ из текста PubMed/FDA ответа.

    ВАЖНО: Возвращает значение в ЧАСАХ.
    Если в тексте "12 days" → возвращает 288.0
    Если в тексте "12 hours" → возвращает 12.0
    """
    t = text.lower()

    patterns = [
        # "t1/2 = 12 h" / "t½ = 12 days" — самый надёжный формат
        r'(?:t\s*1\s*/\s*2|t½|t1/2)\s*(?:[=:\-–—]\s*|(?:of|is|was)\s+)'
        r'(\d+[.,]?\d*)\s*(hours?|hrs?|h\b|days?|d\b|minutes?|min|weeks?|wk)',

        # "terminal half-life of 12 days" / "elimination half-life was approximately 12 h"
        r'(?:terminal\s+)?(?:elimination\s+)?half[- ]?life'
        r'(?:\s+(?:of\s+)?(?:the\s+)?(?:drug\s+)?(?:is\s+|was\s+|of\s+)?(?:approximately\s+|about\s+|~\s*)?)?'
        r'(\d+[.,]?\d*)\s*(hours?|hrs?|h\b|days?|d\b|minutes?|min|weeks?|wk)',

        # "half-life of approximately 12 days" — с промежутком до 80 символов
        r'half[- ]?life'
        r'(?:[^.]{0,80}?)'
        r'(?:of|is|was|approximately|about|~|=|:)\s*'
        r'(\d+[.,]?\d*)\s*(hours?|hrs?|h\b|days?|d\b|minutes?|min|weeks?|wk)',

        # "half-life 12 days" — прямо рядом
        r'half[- ]?life\s+(\d+[.,]?\d*)\s*(hours?|hrs?|h\b|days?|d\b|min|weeks?|wk)',

        # Русский: "период полувыведения составляет 12 суток"
        r'период\s+полу[- ]?(?:выведения|элиминации)'
        r'(?:[^.]{0,120}?)'
        r'(?:составля\w+|равен|равна|приблизительно|примерно|около|~|≈|=|:)\s*'
        r'(\d+[.,]?\d*)\s*(час(?:ов|а|ы)?|ч\b|мин\w*|сут(?:ок|ки)?|дн(?:ей|я)?|день|нед\w*)',

        # Русский: "T½ составляет 12 суток"
        r'(?:t\s*1\s*/\s*2|t½)\s*(?:составля\w+|равен|равна|=|:|-)\s*'
        r'(\d+[.,]?\d*)\s*(час(?:ов|а|ы)?|ч\b|мин\w*|сут(?:ок|ки)?|дн(?:ей|я)?|день|нед\w*)',
    ]

    for pat in patterns:
        m = re.search(pat, t)
        if m:
            val_str = m.group(1).replace(',', '.')
            try:
                val = float(val_str)
            except ValueError:
                continue

            unit = m.group(2).lower().strip()
            hours = _pk_unit_to_hours(val, unit)

            if hours is None:
                continue

            # Санитарная проверка
            if hours < 0.01 or hours > 10000:
                continue

            # Логируем для отладки
            if hours != val:
                print(f"   📐 T½ конвертация: {val} {unit} → {hours} ч")

            return hours

    return None


def _extract_tmax_from_text(text: str) -> Optional[float]:
    """Извлекает Tmax из текста PubMed."""
    t = text.lower()
    patterns = [
        r'(?:tmax|t\s*max)\s*(?:[=:\-–—]\s*|(?:of|is|was)\s+)'
        r'(\d+[.,]?\d*)\s*(hours?|h|days?|d|min)',
        r'(?:time\s+to\s+(?:peak|maximum)\s+(?:concentration|cmax))'
        r'(?:[^.]{0,60}?)'
        r'(?:of|is|was|approximately)\s*'
        r'(\d+[.,]?\d*)\s*(hours?|h|days?|d|min)',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            val_str = m.group(1).replace(',', '.')
            try:
                val = float(val_str)
            except ValueError:
                continue
            hours = _pk_unit_to_hours(val, m.group(2).lower())
            if hours and 0.01 < hours < 500:
                return hours
    return None


def _extract_cmax_from_text(text: str) -> tuple:
    """Извлекает Cmax из текста PubMed. Returns (value, unit) or (None, '')."""
    t = text.lower()
    patterns = [
        r'(?:cmax|c\s*max|peak\s+(?:plasma\s+)?concentration)'
        r'(?:[^.]{0,60}?)'
        r'(?:of|is|was|=)\s*'
        r'(\d+[.,]?\d*)\s*(ng/ml|µg/ml|mg/ml|μg/ml|нг/мл|мкг/мл)',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            val_str = m.group(1).replace(',', '.')
            try:
                return float(val_str), m.group(2)
            except ValueError:
                continue
    return None, ""


def _pk_unit_to_hours(val: float, unit: str) -> Optional[float]:
    """
    Конвертирует PK-единицы в часы.

    ВАЖНО: Если единица не распознана — возвращает None (не val!).
    Это предотвращает баг "12 days → 12 hours".
    """
    u = unit.lower().strip()

    # Часы
    if u in ('h', 'hr', 'hrs', 'hour', 'hours') or u.startswith('час'):
        return val

    # Минуты
    if u in ('min', 'minute', 'minutes') or u.startswith('мин'):
        return val / 60

    # Дни / сутки
    if u in ('d', 'day', 'days') or u.startswith('сут') or u.startswith('дн') or u == 'день':
        return val * 24

    # Недели
    if u in ('wk', 'week', 'weeks') or u.startswith('нед'):
        return val * 24 * 7

    # Русское "ч" — только если ровно "ч" (не начало другого слова)
    if u == 'ч':
        return val

    # Неизвестная единица — НЕ возвращаем val, т.к. можем перепутать дни с часами
    print(f"   ⚠️ T½: неизвестная единица '{unit}' для значения {val}")
    return None