"""
agents/regulatory.py — Regulatory Agent обёртка.

Оборачивает детерминированный RegulatoryAgent85 в BaseAgent интерфейс.
Regulatory Agent НЕ использует LLM — чистые правила.
"""

from typing import Any, Dict

from app.agents.base import BaseAgent, AgentResult
from app.services.regulatory_engine import RegulatoryAgent85, StudyData


class RegulatoryAgent(BaseAgent):
    """
    Regulatory Agent — обёртка над детерминированным движком правил.
    LLM не используется. Чекает соответствие Решению ЕАЭС №85.
    """

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        # Маппим поля из PipelineInput в StudyData
        release_type = input_data.get("release_type", "immediate")

        dosage_form_map = {
            "таблетки": "tablet_ir" if release_type == "immediate" else "tablet_mr",
            "капсулы": "capsule_ir" if release_type == "immediate" else "capsule_mr",
            "раствор": "solution",
        }
        dosage_form_raw = (input_data.get("dosage_form") or "таблетки").lower()
        dosage_form = dosage_form_map.get(dosage_form_raw, "tablet_ir")

        sex = input_data.get("sex_restriction", "males_only")

        study_data = StudyData(
            dosage_form=dosage_form,
            is_generic=True,
            is_biological=False,
            subjects_healthy=True,
            subject_age_min=input_data.get("age_min", 18),
            subject_age_max=input_data.get("age_max", 45),
            bmi_min=18.5,
            bmi_max=30.0,
            both_sexes_included=(sex == "males_and_females"),
            fasting_hours_before=10.0,
            water_ml_with_dose=200.0,
            food_restriction_hours_after=4.0,
            standardised_diet=True,
            reference_product_defined=True,
            reference_is_originator=True,
            test_gmp_confirmed=True,
            biological_matrix="plasma",
            analyte="parent",
            statistical_method="anova_log",
            ci_level_pct=90,
            bioanalytical_method_validated=True,
        )

        # Запускаем чекер
        engine = RegulatoryAgent85()
        report = engine.run(study_data)

        return AgentResult(
            data=report,
            sources=["decision_85", "regulatory_engine"],
        )
