"""
pipeline/pipeline.py — Оркестратор мульти-агентной системы.

DAG зависимостей:

  PK Agent ──────┐
                 ├──► Design Agent ──► Sample Size Agent ──► Synopsis Generator
  Regulatory ────┘

Шаг 1: PK + Regulatory запускаются ПАРАЛЛЕЛЬНО (asyncio.gather)
Шаг 2: Design Agent получает результаты PK + Regulatory
Шаг 3: Sample Size Agent получает результат Design
Шаг 4: Synopsis Generator получает ВСЁ

Каждому агенту передаются ТОЛЬКО нужные ему поля, не весь JSON.
"""

import asyncio
from typing import Any, Dict

from app.models.common import PipelineInput
from app.models.pk import PKResult
from app.models.design import DesignResult
from app.models.sample_size import SampleSizeResult
from app.services.llm.factory import build_llm_client

from app.agents.pk_literature import PKLiteratureAgent
from app.agents.regulatory import RegulatoryAgent
from app.agents.study_design import StudyDesignAgent
from app.agents.sample_size import SampleSizeAgent
from app.agents.synopsis_generator import SynopsisGeneratorAgent


class Pipeline:
    def __init__(self) -> None:
        llm_fast = build_llm_client("fast")
        llm_pro = build_llm_client("pro")

        # Распределение моделей:
        # pro  — PK (извлечение чисел из статей), Synopsis (генерация текста)
        # fast — Regulatory (чек-лист), Design (обоснование), Sample Size (описание)
        self.pk_agent = PKLiteratureAgent("pk_literature", llm_pro)
        self.reg_agent = RegulatoryAgent("regulatory", llm_fast)
        self.design_agent = StudyDesignAgent("study_design", llm_fast)
        self.size_agent = SampleSizeAgent("sample_size", llm_fast)
        self.syn_agent = SynopsisGeneratorAgent("synopsis", llm_pro)

    async def run(self, payload: PipelineInput) -> Dict[str, Any]:
        user_input = payload.model_dump()

        # ═══════════════════════════════════════
        # ШАГ 1: PK + Regulatory ПАРАЛЛЕЛЬНО
        # ═══════════════════════════════════════
        # Оба агента зависят только от пользовательского ввода,
        # не друг от друга → запускаем одновременно (экономим время).

        pk_res, reg_res = await asyncio.gather(
            self.pk_agent.run(user_input),
            self.reg_agent.run(user_input),
        )

        # Извлекаем типизированные данные
        pk_data: PKResult = pk_res.data

        # Извлекаем drug_info и protocol_data из PK Agent (один парсинг!)
        drug_info = getattr(pk_data, '_drug_info', None)
        protocol_data = getattr(pk_data, '_protocol_data', None)
        hvd_component_ru = getattr(pk_data, '_hvd_component_ru', "")
        hvd_component_en = getattr(pk_data, '_hvd_component_en', "")
        hvd_cv_value = getattr(pk_data, '_hvd_cv_value', None)

        # Если пользователь указал CVintra или T½ — они приоритетнее
        cv_intra = payload.cv_intra or pk_data.cv_intra_max
        t_half = payload.t_half_hours or pk_data.t_half_hours

        # ═══════════════════════════════════════
        # ШАГ 2: Design Agent
        # ═══════════════════════════════════════
        # Получает: PK-параметры (числа) + regulatory + release_type
        # Возвращает: тип дизайна, отмывочный, dropout и т.д.

        design_input = {
            # PK параметры (только нужные числа)
            "cv_intra": cv_intra,
            "t_half_hours": t_half,
            "tmax_hours": pk_data.tmax.value if pk_data.tmax else None,
            "is_hvd": pk_data.is_hvd,
            "is_nti": pk_data.is_nti,
            # Из пользовательского ввода
            "release_type": user_input.get("release_type"),
            "intake_mode": user_input.get("intake_mode"),
            # Regulatory
            "regulatory": reg_res.data,
            # Переопределения
            "override_washout_min_days": payload.override_washout_min_days,
            "override_dropout_rate": payload.override_dropout_rate,
        }
        design_res = await self.design_agent.run(design_input)
        design_data: DesignResult = design_res.data

        # ═══════════════════════════════════════
        # ШАГ 3: Sample Size Agent
        # ═══════════════════════════════════════
        # Получает: CVintra + результат Design Agent (тип, dropout, периоды)
        # Возвращает: n_total, объём крови и т.д.

        size_input = {
            "cv_intra": cv_intra,
            "is_hvd": pk_data.is_hvd,
            "design": design_data,
            # Пользовательские переопределения констант расчёта
            "overrides": {
                k: v for k, v in {
                    "gmr": payload.override_gmr,
                    "power": payload.override_power,
                    "alpha": payload.override_alpha,
                    "dropout_rate": payload.override_dropout_rate,
                    "screenfail_rate": payload.override_screenfail_rate,
                    "min_subjects": payload.override_min_subjects,
                    "blood_per_point_ml": payload.override_blood_per_point_ml,
                    "max_blood_ml": payload.override_max_blood_ml,
                }.items() if v is not None
            },
        }
        size_res = await self.size_agent.run(size_input)
        size_data: SampleSizeResult = size_res.data

        # ═══════════════════════════════════════
        # ШАГ 4: Synopsis Generator
        # ═══════════════════════════════════════
        # Получает: ВСЁ (пользовательский ввод + результаты всех агентов)
        # Возвращает: dict с 29 полями синопсиса

        syn_input = {
            **user_input,
            "pk": pk_data,
            "regulatory": reg_res.data,
            "design": design_data,
            "sample_size": size_data,
            "drug_info": drug_info,            # из PK Agent (один раз!)
            "protocol_data": protocol_data,    # из PK Agent
            "hvd_component_ru": hvd_component_ru,
            "hvd_component_en": hvd_component_en,
            "hvd_cv_value": hvd_cv_value,
        }
        syn_res = await self.syn_agent.run(syn_input)

        # ═══════════════════════════════════════
        # Собираем результат
        # ═══════════════════════════════════════

        all_sources = []
        for res in [pk_res, reg_res, design_res, size_res, syn_res]:
            all_sources.extend(res.sources)

        return {
            "pk": pk_data,
            "regulatory": reg_res.data,
            "design": design_data,
            "sample_size": size_data,
            "synopsis": syn_res.data,
            "sources": list(set(all_sources)),  # убираем дубли
        }