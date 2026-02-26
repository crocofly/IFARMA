"""
agents/pk_literature.py — PK Literature Agent.
Ищет фармакокинетические параметры по МНН для проектирования БЭ-исследования.

ПРИОРИТЕТ ИСТОЧНИКОВ CVintra:
1. PubMed BE-статьи по базовому МНН без соли (CVintra из реальных исследований)
2. FDA/EMA BE Guidance Documents (если нет статей)
3. LLM-fallback (Cmax, AUC, T½ — общая ФК-литература)

КРИТИЧНО: поиск ведётся по базовому МНН (без соли), НЕ по торговому названию.
  "тенофовира алафенамид фумарат" → ищем "tenofovir alafenamide"
  НЕ ищем по "Вемлиди" — это референтный препарат, не действующее вещество.
"""

import json
import os
import re
from typing import Any, Dict, Optional, Tuple
from pydantic import ValidationError

from app.agents.base import BaseAgent, AgentResult
from app.models.pk import PKResult, PKParameter, PKSource


# ── Нормализация МНН ──
try:
    from app.utils.inn_utils import normalize_inn, strip_salt_ru, strip_salt_en
except ImportError:
    try:
        from inn_utils import normalize_inn, strip_salt_ru, strip_salt_en
    except ImportError:
        # Fallback: если inn_utils недоступен
        def normalize_inn(inn_ru, inn_en=None):
            return inn_ru, inn_en or ""
        def strip_salt_ru(s): return s
        def strip_salt_en(s): return s


PK_EXTRACT_PROMPT = """
Ты — эксперт по фармакокинетике и биоэквивалентности.
Задача: найти ФК-параметры для препарата с МНН "{inn_ru}" ({inn_en}).
Базовое МНН (без соли): "{inn_ru_base}" ({inn_en_base}).
Лекарственная форма: {dosage_form}, дозировка: {dosage}.

Мне нужны КОНКРЕТНЫЕ ЧИСЛОВЫЕ ЗНАЧЕНИЯ для планирования исследования БЭ:
1. Cmax (нг/мл) — максимальная концентрация в плазме
2. AUC0-t (нг·ч/мл) — площадь под кривой концентрация-время
3. Tmax (ч) — время достижения Cmax
4. T½ (ч) — период полувыведения
5. CVintra для Cmax (%) — внутрииндивидуальный коэффициент вариабельности
6. CVintra для AUC (%) — внутрииндивидуальный коэффициент вариабельности
7. BCS-класс (I, II, III или IV)

ВАЖНО:
- CVintra ищи ТОЛЬКО по базовому МНН без соли: "{inn_en_base}"
- CVintra ищи в статьях по биоэквивалентности ДРУГИХ дженериков этого же МНН
- НЕ используй FDA/EMA Product-Specific Guidance для CVintra — они часто содержат
  пороговое значение CV, а не реальное из исследований
- Если CVintra ≥ 30% для Cmax или AUC — препарат высоковариабельный (is_hvd = true)
- Выбирай НАИБОЛЬШИЙ CVintra из доступных исследований (консервативный подход)
- T½ обычно есть в инструкции (ОХЛП) оригинального препарата
- Если данных нет — укажи null, НЕ выдумывай

Верни ТОЛЬКО JSON:
{{
  "inn_ru": "{inn_ru_base}",
  "inn_en": "{inn_en_base}",
  "cmax": {{"value": ..., "unit": "нг/мл", "source": "PMID:..."}},
  "auc_0t": {{"value": ..., "unit": "нг·ч/мл", "source": "..."}},
  "tmax": {{"value": ..., "unit": "ч", "source": "..."}},
  "t_half": {{"value": ..., "unit": "ч", "source": "..."}},
  "cv_intra_cmax": {{"value": ..., "unit": "%", "source": "..."}},
  "cv_intra_auc": {{"value": ..., "unit": "%", "source": "..."}},
  "is_hvd": false,
  "is_nti": false,
  "bcs_class": "...",
  "reference_drug": "название оригинального препарата",
  "reference_source": "откуда (ЕАЭС/FDA/EMA)",
  "literature_review": "краткий обзор 2-3 абзаца на русском",
  "sources": [
    {{"source_type": "pubmed", "pmid": "...", "title": "...", "url": "..."}}
  ]
}}
"""


class PKLiteratureAgent(BaseAgent):
    """
    PK Literature Agent — ищет ФК-параметры по МНН.

    Алгоритм:
    1. Нормализуем МНН (убираем соль: "фумарат", "гидрохлорид" и т.д.)
    2. Ищем CVintra по базовому МНН (без соли) — search_cv_intra()
    3. Если не нашли — пробуем полный МНН (с солью)
    4. LLM извлекает остальные параметры (Cmax, AUC, T½)
    5. CVintra из поиска приоритетнее CVintra из LLM
    6. Пользовательский --cv-intra приоритетнее всего
    7. Определяет is_hvd (CVintra ≥ 30%)

    ВАЖНО: НЕ передаём торговое название референтного препарата в поиск CVintra.
    CVintra — свойство действующего вещества, не конкретного бренда.
    """

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        inn_ru = (input_data.get("inn_ru") or "").strip()
        if not inn_ru:
            raise ValueError("input_data['inn_ru'] is required")

        inn_en = input_data.get("inn_en") or ""
        dosage_form = input_data.get("dosage_form") or "таблетки"
        dosage = input_data.get("dosage") or ""

        user_cv = input_data.get("cv_intra")
        user_t_half = input_data.get("t_half_hours")

        # ══════════════════════════════════════════
        # Шаг 0: Нормализация МНН — убираем соль
        # ══════════════════════════════════════════
        inn_ru_base, inn_en_base = normalize_inn(inn_ru, inn_en)

        print(f"  МНН полное:  {inn_ru}" + (f" ({inn_en})" if inn_en else ""))
        if inn_ru_base != inn_ru or (inn_en and inn_en_base != inn_en):
            print(f"  МНН базовое: {inn_ru_base}" + (f" ({inn_en_base})" if inn_en_base else ""))

        # ══════════════════════════════════════════
        # Шаг 0.5: Поиск существующих протоколов БЭ
        # ══════════════════════════════════════════
        # ПРИОРИТЕТ ВЫШЕ PubMed статей. Если найден реальный протокол —
        # берём CVintra, дизайн, выборку, режим приёма оттуда.
        protocol_data = None
        try:
            try:
                from app.services.search.protocol_search import search_existing_protocols
            except ImportError:
                from protocol_search import search_existing_protocols

            ref_drug_name_raw = (
                input_data.get("reference_drug_name")
                or input_data.get("ref_drug")
                or ""
            )
            print(f"🔎 Поиск существующих протоколов БЭ для '{inn_en_base or inn_ru_base}'...")
            protocol_data = search_existing_protocols(
                inn_ru=inn_ru_base,
                inn_en=inn_en_base or inn_en,
                ref_drug_name=ref_drug_name_raw,
            )

            if protocol_data and protocol_data.get("found"):
                src = protocol_data.get("source", "?")
                nct = protocol_data.get("nct_id", "")
                design = protocol_data.get("design_type", "")
                n_subj = protocol_data.get("n_subjects", "")
                cv = protocol_data.get("cv_intra")
                print(f"  ✅ Найден протокол ({src}): {nct}")
                if design:
                    print(f"     Дизайн: {design}")
                if cv:
                    print(f"     CVintra: {cv}%")
                if n_subj:
                    print(f"     Выборка: {n_subj}")
            else:
                print(f"  ⚠️ Существующих протоколов БЭ не найдено")
        except ImportError:
            print("  ⚠️ protocol_search модуль не найден")
        except Exception as e:
            print(f"  ⚠️ Поиск протоколов: {type(e).__name__}: {e}")

        # ══════════════════════════════════════════
        # Шаг 1: CVintra — поиск по PubMed
        # ══════════════════════════════════════════
        # Для комбинированных препаратов (А + Б + В) ищем CVintra
        # ПО КАЖДОМУ КОМПОНЕНТУ ОТДЕЛЬНО и берём максимальный.
        cv_result = None
        hvd_component_ru = ""   # какой компонент высоковариабельный
        hvd_component_en = ""
        hvd_cv_value = None     # его CVintra
        component_cv_results = {}  # {component_en: CVintraResult}

        if user_cv is None:
            try:
                from app.services.pk.cv_intra import search_cv_intra

                # Разбиваем комбинацию на компоненты
                components_ru = [c.strip() for c in inn_ru_base.split('+') if c.strip()]
                components_en_raw = [c.strip() for c in (inn_en_base or inn_en or "").split('+') if c.strip()]

                # Нормализуем каждый компонент отдельно
                components = []  # [(ru, en), ...]
                for i, comp_ru in enumerate(components_ru):
                    comp_en = components_en_raw[i] if i < len(components_en_raw) else ""
                    comp_ru_norm, comp_en_norm = normalize_inn(comp_ru, comp_en if comp_en else None)
                    components.append((comp_ru_norm, comp_en_norm))

                if len(components) <= 1:
                    # Одиночный МНН — ищем как раньше
                    search_inn_en = inn_en_base or inn_en
                    search_inn_ru = inn_ru_base or inn_ru

                    print(f"🔎 Поиск CVintra для '{search_inn_en or search_inn_ru}'...")
                    cv_result = search_cv_intra(
                        inn_en=search_inn_en,
                        inn_ru=search_inn_ru,
                        ref_drug_name="",
                    )

                    if cv_result.source == "default" and (
                        inn_ru_base != inn_ru or inn_en_base != inn_en
                    ):
                        print(f"  ↳ Не найдено. Пробуем полный МНН: '{inn_en or inn_ru}'...")
                        cv_result = search_cv_intra(
                            inn_en=inn_en,
                            inn_ru=inn_ru,
                            ref_drug_name="",
                        )

                    if cv_result.source != "default":
                        print(
                            f"📊 CVintra = {cv_result.cv_intra}% "
                            f"({cv_result.source}, {cv_result.confidence}) "
                            f"[{cv_result.source_detail}]"
                        )
                    else:
                        print(f"⚠️  CVintra не найден — используем {cv_result.cv_intra}% (default)")
                else:
                    # КОМБИНАЦИЯ — ищем по каждому компоненту отдельно
                    print(f"🔎 Комбинированный препарат: {len(components)} компонентов")
                    best_cv = None
                    best_cv_result = None

                    for comp_ru, comp_en in components:
                        search_term = comp_en or comp_ru
                        print(f"  🔎 CVintra для '{search_term}'...")
                        comp_cv = search_cv_intra(
                            inn_en=comp_en,
                            inn_ru=comp_ru,
                            ref_drug_name="",
                        )
                        component_cv_results[comp_en or comp_ru] = comp_cv

                        if comp_cv.source != "default":
                            print(
                                f"     📊 {search_term}: CVintra = {comp_cv.cv_intra}% "
                                f"({comp_cv.source})"
                            )
                            if best_cv is None or comp_cv.cv_intra > best_cv:
                                best_cv = comp_cv.cv_intra
                                best_cv_result = comp_cv
                                hvd_component_ru = comp_ru
                                hvd_component_en = comp_en
                                hvd_cv_value = comp_cv.cv_intra
                        else:
                            print(f"     ⚠️ {search_term}: не найден")

                    if best_cv_result:
                        cv_result = best_cv_result
                        print(
                            f"📊 Макс. CVintra = {cv_result.cv_intra}% "
                            f"(компонент: {hvd_component_en or hvd_component_ru}) "
                            f"[{cv_result.source_detail}]"
                        )
                    else:
                        cv_result = None
                        print(f"⚠️  CVintra не найден ни для одного компонента")

            except ImportError:
                print("⚠️  cv_intra модуль не найден — CVintra будет из LLM")
            except Exception as e:
                print(f"⚠️  Поиск CVintra: {type(e).__name__}: {e}")


        # ══════════════════════════════════════════
        # Шаг 2: PubMed → T½, Tmax, Cmax
        # ══════════════════════════════════════════
        pk_params = None
        try:
            from app.services.pk.cv_intra import search_pk_params
            print(f"🔎 Поиск T½/Tmax/Cmax по PubMed для '{inn_en_base or inn_ru_base}'...")
            pk_params = search_pk_params(
                inn_en=inn_en_base or inn_en,
                inn_ru=inn_ru_base or inn_ru,
            )
            if pk_params and pk_params.t_half_hours:
                t_display = f"{pk_params.t_half_hours} ч"
                if pk_params.t_half_hours >= 48:
                    t_display = f"{pk_params.t_half_hours/24:.1f} дней ({pk_params.t_half_hours} ч)"
                print(f"  ✅ T½ = {t_display} (PubMed)")
            else:
                print(f"  ⚠️ T½ не найден в PubMed")
        except ImportError:
            print("  ⚠️ search_pk_params не доступен")
        except Exception as e:
            print(f"  ⚠️ Поиск PK: {type(e).__name__}: {e}")

        # ══════════════════════════════════════════
        # Шаг 3: Инструкция → состав, хранение, пол, приём
        # ══════════════════════════════════════════
        # ФК-параметры (T½, Tmax, Cmax) НЕ берём из инструкции — только из PubMed/статей.
        # Инструкция нужна для: excipients, storage, sex, intake, composition.
        drug_info = None
        ref_drug_name = (
            input_data.get("reference_drug_name")
            or input_data.get("ref_drug")
            or ""
        )
        try:
            try:
                from app.utils.drug_info_parser import fetch_drug_info
            except ImportError:
                from drug_info_parser import fetch_drug_info

            print(f"📋 Поиск инструкции для '{ref_drug_name or inn_ru_base}'...")
            drug_info = await fetch_drug_info(
                drug_name=ref_drug_name or inn_ru_base,
                inn=inn_ru_base,
                dosage=dosage,
            )
            if drug_info and (drug_info.excipients or drug_info.storage_conditions):
                print(f"  ✅ Инструкция найдена ({drug_info.source_url or 'vidal/grls'})")
            else:
                print(f"  ⚠️ Инструкция не найдена")
        except ImportError:
            print("  ⚠️ drug_info_parser не найден")
        except Exception as e:
            print(f"  ⚠️ Парсинг инструкции: {type(e).__name__}: {e}")

        # ══════════════════════════════════════════
        # Шаг 4: LLM — дополняет пробелы
        # ══════════════════════════════════════════
        prompt = PK_EXTRACT_PROMPT.format(
            inn_ru=inn_ru,
            inn_en=inn_en,
            inn_ru_base=inn_ru_base,
            inn_en_base=inn_en_base,
            dosage_form=dosage_form,
            dosage=dosage,
        )

        raw = await self.llm.generate(prompt)

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                cleaned = cleaned.rsplit("```", 1)[0]
            data = json.loads(cleaned)
            result = PKResult.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            result = PKResult(
                inn_ru=inn_ru,
                inn_en=inn_en,
                literature_review=f"LLM вернул невалидный ответ. Raw: {raw[:500]}",
            )
            return AgentResult(data=result, sources=["llm_parse_error"])

        # ══════════════════════════════════════════
        # Шаг 5: Наложение приоритетов
        # ══════════════════════════════════════════
        # PubMed/Инструкция > LLM (для T½, Tmax, Cmax)
        if pk_params and pk_params.t_half_hours is not None:
            llm_t_half = result.t_half_hours
            pk_src = pk_params.source_detail or "PubMed"
            result.t_half = PKParameter(value=pk_params.t_half_hours, unit="ч", source=pk_src)
            if llm_t_half and abs(llm_t_half - pk_params.t_half_hours) > max(llm_t_half, pk_params.t_half_hours) * 0.3:
                print(f"  ⚠️ T½: LLM={llm_t_half} ч vs PubMed={pk_params.t_half_hours} ч → используем PubMed")

        if pk_params and pk_params.tmax_hours is not None and not result.tmax:
            result.tmax = PKParameter(value=pk_params.tmax_hours, unit="ч",
                                       source=pk_params.source_detail or "PubMed")

        if pk_params and pk_params.cmax_value is not None and not result.cmax:
            result.cmax = PKParameter(value=pk_params.cmax_value, unit=pk_params.cmax_unit,
                                       source=pk_params.source_detail or "PubMed")

        # PubMed CVintra > LLM CVintra
        if cv_result and cv_result.source != "default":
            result.cv_intra_cmax = PKParameter(
                value=cv_result.cv_intra,
                unit="%",
                source=cv_result.source_detail,
            )
            result.sources.append(PKSource(
                source_type=cv_result.source,
                title=cv_result.source_detail,
                url="",
            ))

        # Протокол CVintra > PubMed CVintra (если найден)
        if protocol_data and protocol_data.get("found") and protocol_data.get("cv_intra"):
            proto_cv = protocol_data["cv_intra"]
            result.cv_intra_cmax = PKParameter(
                value=proto_cv,
                unit="%",
                source=f"Протокол БЭ: {protocol_data.get('nct_id', '')}",
            )
            result.sources.append(PKSource(
                source_type="protocol",
                title=f"Протокол БЭ: {protocol_data.get('nct_id', '')}",
                url="",
            ))
            print(f"  📋 CVintra из протокола: {proto_cv}% (приоритет над PubMed)")

        # Пользовательские данные → высший приоритет
        if user_cv is not None:
            result.cv_intra_cmax = PKParameter(value=user_cv, unit="%", source="user_input")
        if user_t_half is not None:
            result.t_half = PKParameter(value=user_t_half, unit="ч", source="user_input")


        # ══════════════════════════════════════════
        # Шаг 5: Автоматически определяем HVD
        # ══════════════════════════════════════════
        cv_max = result.cv_intra_max
        if cv_max is not None and cv_max >= 30.0:
            result.is_hvd = True

        source_labels = [s.source_type for s in result.sources] or ["llm"]

        # Прикрепляем drug_info для использования в synopsis_generator
        if drug_info and drug_info.source_url:
            result.sources.append(PKSource(
                source_type="instruction",
                title=f"Инструкция {ref_drug_name}",
                url=drug_info.source_url,
            ))
            # Сохраняем как атрибут для доступа из pipeline
            result._drug_info = drug_info  # type: ignore

        # Прикрепляем данные протокола для доступа из pipeline
        if protocol_data and protocol_data.get("found"):
            result._protocol_data = protocol_data  # type: ignore

        # Прикрепляем информацию о HVD-компоненте (для текста дизайна)
        result._hvd_component_ru = hvd_component_ru  # type: ignore
        result._hvd_component_en = hvd_component_en  # type: ignore
        result._hvd_cv_value = hvd_cv_value  # type: ignore
        result._component_cv_results = component_cv_results  # type: ignore

        return AgentResult(data=result, sources=source_labels)

    def validate(self, result: AgentResult) -> bool:
        """Проверяем, что критичные параметры найдены."""
        if not isinstance(result.data, PKResult):
            return False
        pk: PKResult = result.data
        has_cv = pk.cv_intra_max is not None
        has_t_half = pk.t_half_hours is not None
        return has_cv or has_t_half