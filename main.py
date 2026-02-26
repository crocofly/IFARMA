"""
main.py — Запуск полного пайплайна из командной строки.

Два режима:
  1. CLI:
     python main.py "тенофовира алафенамид" --dose "25 мг" --ref-drug "Вемлиди®"
     python main.py "Амлодипин" --dose "10 мг" --cv-intra 28.5

  2. JSON-конфиг (все параметры в файле):
     python main.py --config input.json

Выходные файлы сохраняются в: output/<МНН>/
При повторной генерации — автоматическое версионирование:
    output/тенофовира_алафенамид_фумарат/
        synopsis_тенофовира_алафенамид_фумарат_v1.docx
        rationale_тенофовира_алафенамид_фумарат_v1.docx
        data_тенофовира_алафенамид_фумарат_v1.json
        synopsis_тенофовира_алафенамид_фумарат_v2.docx
        ...
"""

import asyncio
import argparse
import os
import sys
import json
import re
from datetime import datetime

from app.models.common import PipelineInput
from app.pipeline.pipeline import Pipeline
from app.services.export.docx_exporter import export_synopsis
from app.services.export.rationale_exporter import export_rationale


def _get_next_version(directory: str, base_name: str) -> int:
    """
    Определяет следующий номер версии.

    Сканирует directory на наличие файлов вида:
        {base_name}_v1.docx, {base_name}_v2.docx, ...

    Returns:
        Следующий номер (1 если нет файлов)
    """
    if not os.path.exists(directory):
        return 1

    max_version = 0
    pattern = re.compile(
        re.escape(base_name) + r'_v(\d+)\.\w+$'
    )

    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            v = int(match.group(1))
            max_version = max(max_version, v)

    return max_version + 1


async def run_pipeline(payload: PipelineInput, args) -> None:
    """Запуск пайплайна и генерация файлов."""

    print()
    print("=" * 60)
    print("  iFarma — Генератор синопсиса БЭ-исследования")
    print("=" * 60)
    print(f"  МНН:            {payload.inn_ru}")
    if payload.dosage:
        print(f"  Форма:          {payload.dosage_form}, {payload.dosage}")
    if payload.reference_drug_name:
        print(f"  Референтный:    {payload.reference_drug_name}")
    if payload.cv_intra is not None:
        print(f"  CVintra:        {payload.cv_intra}%")
    if payload.t_half_hours is not None:
        print(f"  T½:             {payload.t_half_hours} ч")
    if payload.sex_restriction:
        sex_text = {"males_only": "М", "females_only": "Ж", "males_and_females": "М+Ж"}.get(payload.sex_restriction, "М")
        print(f"  Пол:            {sex_text}")
    if payload.follow_up_days:
        print(f"  Период ПН:      {payload.follow_up_days} дней")
    print(f"  LLM:            {os.getenv('LLM_PROVIDER', 'mock')}")
    print(f"  Время:          {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Запускаем пайплайн
    pipeline = Pipeline()

    print("⏳ [1/4] PK Agent + Regulatory Agent (параллельно)...")
    result = await pipeline.run(payload)

    # Показываем результат
    pk = result["pk"]
    design = result["design"]
    sample = result["sample_size"]
    regulatory = result["regulatory"]

    print(f"✅ PK Agent:")
    if hasattr(pk, "t_half_hours") and pk.t_half_hours:
        print(f"       T½ = {pk.t_half_hours} ч")
    if hasattr(pk, "cv_intra_max") and pk.cv_intra_max:
        print(f"       CVintra = {pk.cv_intra_max}%")
    if hasattr(pk, "is_hvd"):
        print(f"       HVD = {'да' if pk.is_hvd else 'нет'}")
    if hasattr(pk, "reference_drug") and pk.reference_drug:
        print(f"       Референт = {pk.reference_drug}")

    print(f"✅ Regulatory Agent:")
    summary = regulatory.get("summary", {})
    print(f"       Вердикт: {summary.get('verdict', 'N/A')}")
    print(f"       PASS: {summary.get('pass', 0)}, FAIL: {summary.get('fail', 0)}, WARN: {summary.get('warning', 0)}")

    print(f"✅ Design Agent:")
    print(f"       Дизайн: {design.design_type.value}")
    print(f"       Периодов: {design.n_periods}")
    print(f"       Отмывочный: {design.washout_days or 'нет'} дней")
    print(f"       Dropout: {design.dropout_rate * 100:.0f}%")
    be_method = getattr(design, 'be_method', 'standard')
    if be_method == "ABEL":
        be_lo_cmax = getattr(design, 'be_lower_cmax', 80.0)
        be_hi_cmax = getattr(design, 'be_upper_cmax', 125.0)
        print(f"       Границы БЭ (AUC): {design.be_lower:.2f}–{design.be_upper:.2f}%")
        print(f"       Границы БЭ (Cmax): {be_lo_cmax:.2f}–{be_hi_cmax:.2f}% (ABEL расширенные)")
        print(f"       PE constraints: 80.00–125.00%")
    else:
        print(f"       Границы БЭ: {design.be_lower:.2f}–{design.be_upper:.2f}%")
    # Длительность
    total_min = getattr(design, 'total_duration_days_min', 0)
    total_max = getattr(design, 'total_duration_days_max', 0)
    if total_max > 0:
        print(f"       Длительность: {total_min}–{total_max} дней")
        formula = getattr(design, 'duration_formula', '')
        if formula:
            print(f"       Формула: {formula}")

    print(f"✅ Sample Size Agent:")
    print(f"       Базовый: {sample.n_base} чел.")
    print(f"       С dropout: {sample.n_with_dropout} чел.")
    print(f"       Итого: {sample.n_total} чел.")
    print(f"       Кровь: {sample.blood_volume_ml:.0f} мл {'✅' if sample.blood_volume_ok else '⚠️ ПРЕВЫШЕНИЕ'}")

    # ═══════════════════════════════════════
    # Определяем выходные пути с версионированием
    # ═══════════════════════════════════════
    safe_inn = payload.inn_ru.replace(" ", "_")

    base_output_dir = args.output_dir or "output"
    inn_dir = os.path.join(base_output_dir, safe_inn)
    os.makedirs(inn_dir, exist_ok=True)

    # Определяем версию
    version = _get_next_version(inn_dir, f"synopsis_{safe_inn}")
    version_suffix = f"_v{version}"

    synopsis_path = os.path.join(inn_dir, args.output or f"synopsis_{safe_inn}{version_suffix}.docx")
    rationale_path = os.path.join(inn_dir, f"rationale_{safe_inn}{version_suffix}.docx")
    json_path = os.path.join(inn_dir, f"data_{safe_inn}{version_suffix}.json")

    # Экспорт Synopsis .docx
    print(f"\n⏳ [4/4] Экспорт файлов (v{version})...")

    template = args.template
    if os.path.exists(template):
        result["protocol_version"] = version
        export_synopsis(result, template_path=template, output_path=synopsis_path)
        print(f"  📄 Синопсис:     {synopsis_path}")
    else:
        print(f"  ⚠️  Шаблон не найден: {template}")
        print(f"       Синопсис не сгенерирован. Укажите путь через --template")

    # ── Генерация PK-кривой ──
    pk_curve_path = None
    pk_curve_data = None
    try:
        try:
            from app.services.pk.pk_curve import generate_pk_curve
        except ImportError:
            from pk_curve import generate_pk_curve

        # Извлекаем Cmax, tmax, T½ из PK-результата
        _cmax_val = None
        _tmax_val = None
        _thalf_val = None

        if hasattr(pk, "cmax") and pk.cmax and hasattr(pk.cmax, "value"):
            _cmax_val = pk.cmax.value
        if hasattr(pk, "tmax") and pk.tmax and hasattr(pk.tmax, "value"):
            _tmax_val = pk.tmax.value
        if hasattr(pk, "t_half") and pk.t_half and hasattr(pk.t_half, "value"):
            _thalf_val = pk.t_half.value

        # Fallback: t_half_hours
        if _thalf_val is None and hasattr(pk, "t_half_hours") and pk.t_half_hours:
            _thalf_val = pk.t_half_hours

        if _cmax_val and _tmax_val and _thalf_val:
            pk_curve_data = generate_pk_curve(
                cmax=float(_cmax_val),
                tmax=float(_tmax_val),
                t_half=float(_thalf_val),
            )
            pk_curve_path = os.path.join(inn_dir, f"pk_curve_{safe_inn}{version_suffix}.png")

            # Безопасно получаем intake_mode
            _intake_str = ""
            if hasattr(design, "intake_mode"):
                _im = design.intake_mode
                _intake_str = _im.value if hasattr(_im, "value") else str(_im)

            _dose_str = getattr(payload, "dosage", "") or ""

            pk_curve_data.save_plot(
                pk_curve_path,
                inn=payload.inn_ru,
                dose=f"{_dose_str} {_intake_str}".strip(),
            )
            print(f"  📈 PK-кривая:    {pk_curve_path}")
            print(f"     AUC₀₋ₜ = {pk_curve_data.auc_0t:.1f} нг·ч/мл")
            print(f"     AUC₀₋∞ = {pk_curve_data.auc_0inf:.1f} нг·ч/мл")
            print(f"     Остаточная AUC = {pk_curve_data.auc_residual_pct:.1f}%")
        else:
            missing = []
            if not _cmax_val: missing.append("Cmax")
            if not _tmax_val: missing.append("tmax")
            if not _thalf_val: missing.append("T½")
            print(f"  ℹ️  PK-кривая: пропущена (нет данных: {', '.join(missing)})")
    except Exception as e:
        import traceback
        print(f"  ⚠️  PK-кривая: ошибка ({e})")
        traceback.print_exc()

    # Экспорт Rationale .docx (с PK-кривой)
    export_rationale(
        result,
        output_path=rationale_path,
        pk_curve_path=pk_curve_path,
        pk_curve_data=pk_curve_data,
    )
    print(f"  📋 Обоснования:  {rationale_path}")

    # Сохраняем JSON с данными
    json_data = {
        "version": version,
        "input": payload.model_dump(),
        "pk": pk.model_dump() if hasattr(pk, "model_dump") else pk,
        "design": design.model_dump() if hasattr(design, "model_dump") else design,
        "sample_size": sample.model_dump() if hasattr(sample, "model_dump") else sample,
        "regulatory_summary": summary,
        "synopsis_fields": result["synopsis"],
        "sources": result["sources"],
        "pk_curve": {
            "auc_0t": pk_curve_data.auc_0t if pk_curve_data else None,
            "auc_0inf": pk_curve_data.auc_0inf if pk_curve_data else None,
            "auc_residual_pct": pk_curve_data.auc_residual_pct if pk_curve_data else None,
            "kel": pk_curve_data.kel if pk_curve_data else None,
            "ka": pk_curve_data.ka if pk_curve_data else None,
            "sampling_times": pk_curve_data.sampling_times if pk_curve_data else None,
            "plot_path": pk_curve_path,
        } if pk_curve_data else None,
        "timestamp": datetime.now().isoformat(),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"  💾 Данные JSON:  {json_path}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ ГОТОВО! (версия {version})")
    print(f"  📁 Папка: {inn_dir}")
    print(f"{'=' * 60}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="iFarma — генератор синопсиса БЭ-исследования",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main.py "тенофовира алафенамид" --dose "25 мг" --ref-drug "Вемлиди®"
  python main.py "Амлодипин" --dose "10 мг" --cv-intra 28.5
  python main.py --config input.json
        """,
    )

    # ── JSON-конфиг ──
    parser.add_argument("--config", default=None,
                        help="JSON-файл со всеми параметрами")

    # ── 1. МНН (обязательное если нет --config) ──
    parser.add_argument("inn", nargs="?", default=None,
                        help="МНН на русском (ОБЯЗАТЕЛЬНОЕ)")

    # ── 2. Идентификационный номер ──
    parser.add_argument("--study-id", default=None,
                        help="Номер протокола (вписать вручную)")
    parser.add_argument("--study-id-mode", default="auto",
                        choices=["manual", "auto", "empty"],
                        help="Режим ID: manual=вписать, auto=сгенерировать, empty=пустой")

    # ── 3. Организационные ──
    parser.add_argument("--sponsor", default=None, help="Спонсор (=производитель)")
    parser.add_argument("--sponsor-country", default="Россия", help="Страна спонсора")
    parser.add_argument("--center", default=None, help="Исследовательский центр")
    parser.add_argument("--lab", default=None, help="Биоаналитическая лаборатория")
    parser.add_argument("--insurance", default=None, help="Страховая компания")

    # ── 4. Исследуемый препарат ──
    parser.add_argument("--drug-name", default=None, help="Торговое название дженерика")
    parser.add_argument("--form", default=None,
                        help="Лекарственная форма (ОБЯЗАТЕЛЬНОЕ)")
    parser.add_argument("--dose", default=None,
                        help="Дозировка (ОБЯЗАТЕЛЬНОЕ)")
    parser.add_argument("--release", default="immediate",
                        choices=["immediate", "modified", "delayed"])
    parser.add_argument("--manufacturer", default=None,
                        help="Производитель (Название, Страна)")
    parser.add_argument("--excipients", default=None,
                        help="Вспомогательные вещества (строка)")
    parser.add_argument("--storage", default=None, help="Условия хранения")
    parser.add_argument("--composition", default=None,
                        help="Состав на 1 ед. лек. формы (напр. '25 мг тенофовира алафенамида')")

    # ── 5. Референтный препарат ──
    parser.add_argument("--ref-drug", default=None,
                        help="Референтный препарат (ОБЯЗАТЕЛЬНОЕ)")
    parser.add_argument("--ref-form", default=None,
                        help="Форма РП (если не указана — ищем через Yandex)")
    parser.add_argument("--ref-dose", default=None,
                        help="Дозировка РП (если не указана — ищем через Yandex)")
    parser.add_argument("--ref-manufacturer", default=None,
                        help="Производитель РП (если не указан — ищем через Yandex)")
    parser.add_argument("--ref-ru", default=None,
                        help="Номер РУ ЛП референтного препарата")

    # ── 6. Настройки дизайна ──
    parser.add_argument("--inn-en", default=None, help="МНН на английском")
    parser.add_argument("--intake", default=None,
                        choices=["fasting", "fed", "both"],
                        help="Режим приёма")
    parser.add_argument("--sex", default="auto",
                        choices=["auto", "males_only", "females_only", "males_and_females"],
                        help="Пол добровольцев. auto = AI определит из инструкции")
    parser.add_argument("--age-min", type=int, default=18)
    parser.add_argument("--age-max", type=int, default=45)
    parser.add_argument("--follow-up-days", type=int, default=None,
                        help="Период ПН (дни, по умолчанию 7)")

    # ── 7. Override ──
    parser.add_argument("--cv-intra", type=float, default=None, help="CVintra (%%)")
    parser.add_argument("--t-half", type=float, default=None, help="T½ (часы)")

    # ── 8. Переопределение констант расчёта ──
    parser.add_argument("--gmr", type=float, default=None,
                        help="Ожидаемое GMR (theta0). По умолчанию 0.95")
    parser.add_argument("--power", type=float, default=None,
                        help="Мощность теста. По умолчанию 0.80")
    parser.add_argument("--alpha", type=float, default=None,
                        help="Уровень значимости. По умолчанию 0.05")
    parser.add_argument("--dropout-rate", type=float, default=None,
                        help="Dropout rate. По умолчанию определяется Design Agent")
    parser.add_argument("--screenfail-rate", type=float, default=None,
                        help="Screen failure rate. По умолчанию 0.15")
    parser.add_argument("--min-subjects", type=int, default=None,
                        help="Мин. число добровольцев. По умолчанию 18 (ГОСТ)")
    parser.add_argument("--washout-days", type=int, default=None,
                        help="Отмывочный период (дни). По умолчанию ≥5×T½")

    # ── Пути ──
    parser.add_argument("--template",
                        default="data/шаблон_для_заполнения.docx")
    parser.add_argument("--output", default=None, help="Имя выходного файла")
    parser.add_argument("--output-dir", default=None,
                        help="Базовая директория (по умолчанию output/)")

    args = parser.parse_args()

    # ── Формируем PipelineInput ──
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
        payload = PipelineInput(**config)
    else:
        if not args.inn:
            parser.error("Укажите МНН или используйте --config input.json")
        if not args.form:
            parser.error("Укажите лекарственную форму: --form 'таблетки'")
        if not args.dose:
            parser.error("Укажите дозировку: --dose '25 мг'")
        if not args.ref_drug:
            parser.error("Укажите референтный препарат: --ref-drug 'Вемлиди®'")

        # study_id: если передан --study-id, mode автоматически = manual
        study_id = args.study_id
        if study_id:
            study_id_mode = "manual"
        else:
            study_id_mode = args.study_id_mode

        # manufacturer
        mfr_name, mfr_country = None, None
        if args.manufacturer:
            parts = [p.strip() for p in args.manufacturer.split(",", 1)]
            mfr_name = parts[0]
            if len(parts) > 1:
                mfr_country = parts[1]

        # excipients: если передан как строка — используем как есть
        excipients_str = args.excipients
        if isinstance(excipients_str, list):
            excipients_str = ", ".join(excipients_str)

        payload = PipelineInput(
            inn_ru=args.inn,
            study_id_mode=study_id_mode,
            study_id=study_id,
            sponsor_name=args.sponsor,
            sponsor_country=args.sponsor_country,
            research_center=args.center,
            bioanalytical_lab=args.lab,
            insurance_company=args.insurance,
            drug_name_trade=args.drug_name,
            dosage_form=args.form,
            dosage=args.dose,
            release_type=args.release,
            manufacturer_name=mfr_name,
            manufacturer_country=mfr_country,
            excipients=excipients_str,
            storage_conditions=args.storage,
            composition=args.composition,
            reference_drug_name=args.ref_drug,
            reference_drug_form=args.ref_form,
            reference_drug_dose=args.ref_dose,
            reference_drug_manufacturer=args.ref_manufacturer,
            ref_ru_number=args.ref_ru,
            inn_en=args.inn_en,
            intake_mode=args.intake,
            sex_restriction=args.sex if args.sex != "auto" else "",
            age_min=args.age_min,
            age_max=args.age_max,
            follow_up_days=args.follow_up_days,
            cv_intra=args.cv_intra,
            t_half_hours=args.t_half,
            # Переопределения констант расчёта
            override_gmr=args.gmr,
            override_power=args.power,
            override_alpha=args.alpha,
            override_dropout_rate=args.dropout_rate,
            override_screenfail_rate=args.screenfail_rate,
            override_min_subjects=args.min_subjects,
            override_washout_min_days=args.washout_days,
        )

    asyncio.run(run_pipeline(payload, args))


if __name__ == "__main__":
    main()