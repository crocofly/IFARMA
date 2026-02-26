"""
server.py — FastAPI-сервер для Flutter Web.
Запуск: uvicorn server:app --reload --port 8000
Docs:   http://localhost:8000/docs
"""
import asyncio, os, uuid, traceback, json
from datetime import datetime
from typing import Any, Dict, List, Optional

# Загружаем .env файл
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен — используем системные env

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.models.common import PipelineInput
from app.pipeline.pipeline import Pipeline

# ═══ API Models ═══
class GenerateRequest(BaseModel):
    inn_ru: str
    dosage_form: str
    dosage: str
    storage_conditions: str = ""
    drug_name_trade: Optional[str] = None
    manufacturer: Optional[str] = None
    manufacturer_is_sponsor: bool = True
    sponsor: Optional[str] = None
    protocol_id: Optional[str] = None
    protocol_mode: str = "manual"
    research_center: Optional[str] = None
    bioanalytical_lab: Optional[str] = None
    insurance_company: Optional[str] = None
    reference_drug_name: Optional[str] = None
    excipients: Optional[List[str]] = None
    cv_intra: Optional[float] = None
    t_half_hours: Optional[float] = None
    sex_restriction: str = ""
    age_min: int = 18
    age_max: int = 45
    smoking_restriction: str = ""
    # Overrides — расчётные константы
    override_power: Optional[float] = None
    override_alpha: Optional[float] = None
    override_gmr: Optional[float] = None
    override_dropout_rate: Optional[float] = None
    override_screenfail_rate: Optional[float] = None
    override_min_subjects: Optional[int] = None
    override_blood_per_point_ml: Optional[float] = None
    override_max_blood_ml: Optional[float] = None

    def to_pipeline_input(self) -> PipelineInput:
        sponsor = self.manufacturer if self.manufacturer_is_sponsor else self.sponsor
        kwargs: dict = dict(
            inn_ru=self.inn_ru, dosage_form=self.dosage_form, dosage=self.dosage,
            drug_name_trade=self.drug_name_trade, reference_drug_name=self.reference_drug_name,
            cv_intra=self.cv_intra, t_half_hours=self.t_half_hours,
            sex_restriction=self.sex_restriction if self.sex_restriction else "males_only",
            age_min=self.age_min, age_max=self.age_max,
            sponsor_name=sponsor, research_center=self.research_center,
            bioanalytical_lab=self.bioanalytical_lab, insurance_company=self.insurance_company,
            study_id=self.protocol_id,
            study_id_mode=self.protocol_mode,
            storage_conditions=self.storage_conditions or None,
            manufacturer_name=self.manufacturer,
            excipients=", ".join(self.excipients) if self.excipients else None,
        )
        # Передаём overrides только если заданы
        for attr in ("override_power", "override_alpha", "override_gmr",
                      "override_dropout_rate", "override_screenfail_rate",
                      "override_min_subjects", "override_blood_per_point_ml",
                      "override_max_blood_ml"):
            val = getattr(self, attr)
            if val is not None:
                kwargs[attr] = val
        return PipelineInput(**kwargs)

class StepStatus(BaseModel):
    id: str; label: str; status: str; detail: Optional[str] = None

class TaskResponse(BaseModel):
    task_id: str; status: str; progress: float = 0.0
    steps: List[StepStatus] = []; result: Optional[Dict[str, Any]] = None; error: Optional[str] = None

class HistoryItem(BaseModel):
    task_id: str; inn: str; form: str; dose: str; date: str; status: str

# ═══ Storage ═══
tasks: Dict[str, TaskResponse] = {}
history: List[HistoryItem] = []
file_paths: Dict[str, Dict[str, str]] = {}

# ═══ App ═══
app = FastAPI(title="iFarma API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ═══ Generate ═══
@app.post("/api/generate", response_model=TaskResponse)
async def generate(req: GenerateRequest, bg: BackgroundTasks):
    task_id = uuid.uuid4().hex[:8]
    task = TaskResponse(task_id=task_id, status="running", steps=[
        StepStatus(id="s1", label="PK Литература", status="pending"),
        StepStatus(id="s2", label="Регуляторный агент", status="pending"),
        StepStatus(id="s3", label="Дизайн исследования", status="pending"),
        StepStatus(id="s4", label="Расчёт выборки", status="pending"),
        StepStatus(id="s5", label="Генерация синопсиса", status="pending"),
    ])
    tasks[task_id] = task
    history.insert(0, HistoryItem(task_id=task_id, inn=req.inn_ru, form=req.dosage_form, dose=req.dosage, date=datetime.now().strftime("%d.%m.%Y %H:%M"), status="running"))
    bg.add_task(_run, task_id, req)
    print(f"\n{'='*50}\n  🚀 {task_id}: {req.inn_ru} {req.dosage}\n{'='*50}\n")
    return task

async def _run(task_id: str, req: GenerateRequest):
    task = tasks[task_id]
    try:
        payload = req.to_pipeline_input()
        pipeline = Pipeline()
        task.steps[0].status = "running"; task.steps[1].status = "running"; task.progress = 0.05
        result = await pipeline.run(payload)
        for s in task.steps: s.status = "done"
        task.progress = 1.0; task.result = _ser(result); task.status = "done"
        _export(task_id, payload, result)
        for h in history:
            if h.task_id == task_id: h.status = "done"; break
        print(f"  ✅ {task_id} done: {req.inn_ru}")
    except Exception as e:
        traceback.print_exc(); task.status = "error"; task.error = str(e)
        for s in task.steps:
            if s.status in ("running","pending"): s.status = "error"
        for h in history:
            if h.task_id == task_id: h.status = "error"; break

def _export(task_id, payload, result):
    try:
        safe = payload.inn_ru.replace(" ","_").replace("+","_")
        d = os.path.join("output", safe); os.makedirs(d, exist_ok=True); paths = {}
        tpl = "data/шаблон_для_заполнения.docx"
        if os.path.exists(tpl):
            p = os.path.join(d, f"synopsis_{task_id}.docx")
            try:
                from app.services.export.docx_exporter import export_synopsis
                export_synopsis(result, template_path=tpl, output_path=p); paths["synopsis"] = p
            except Exception as e: print(f"  ⚠️ synopsis export: {e}")
        try:
            p = os.path.join(d, f"rationale_{task_id}.docx")
            from app.services.export.rationale_exporter import export_rationale
            export_rationale(result, output_path=p); paths["rationale"] = p
        except Exception as e: print(f"  ⚠️ rationale export: {e}")
        if paths: file_paths[task_id] = paths
    except Exception as e: print(f"  ⚠️ export: {e}")

def _ser(result):
    out = {}
    for k, v in result.items():
        if hasattr(v, "model_dump"): out[k] = v.model_dump()
        elif isinstance(v, list): out[k] = [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
        elif isinstance(v, dict): out[k] = v
        else: out[k] = str(v) if v is not None else None
    return out

@app.get("/api/generate/{task_id}", response_model=TaskResponse)
async def get_status(task_id: str):
    if task_id not in tasks: raise HTTPException(404, "Not found")
    return tasks[task_id]

@app.get("/api/download/{task_id}/{doc_type}")
async def download(task_id: str, doc_type: str):
    paths = file_paths.get(task_id, {})
    # Если есть отредактированная версия — скачиваем её
    edited_key = f"{doc_type}_edited"
    edited_p = paths.get(edited_key)
    if edited_p and os.path.exists(edited_p):
        return FileResponse(edited_p, media_type="application/msword", filename=os.path.basename(edited_p))
    # Иначе — оригинальный .docx из шаблона
    p = paths.get(doc_type)
    if not p or not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=os.path.basename(p))

@app.get("/api/preview/{task_id}/{doc_type}")
async def preview_html(task_id: str, doc_type: str):
    """Конвертирует .docx → HTML для отображения в редакторе."""
    p = file_paths.get(task_id, {}).get(doc_type)
    if not p or not os.path.exists(p):
        raise HTTPException(404, f"File not found: {doc_type}")
    try:
        import mammoth
        with open(p, "rb") as f:
            result = mammoth.convert_to_html(f)
        html = result.value
        # Добавляем базовые стили
        styled = f"""<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1a1a2e; padding: 20px; }}
h1 {{ font-size: 20px; color: #1a1a2e; border-bottom: 2px solid #4361ee; padding-bottom: 8px; }}
h2 {{ font-size: 16px; color: #3a3a5c; margin-top: 24px; }}
h3 {{ font-size: 14px; color: #4361ee; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; font-size: 13px; }}
th {{ background: #f0f2ff; font-weight: 600; }}
tr:nth-child(even) {{ background: #fafbff; }}
p {{ margin: 6px 0; }}
strong {{ color: #1a1a2e; }}
</style>
{html}"""
        return {"html": styled, "messages": result.messages}
    except Exception as e:
        raise HTTPException(500, f"Conversion error: {e}")

@app.put("/api/save/{task_id}/{doc_type}")
async def save_html(task_id: str, doc_type: str, body: dict):
    """Сохраняет отредактированный HTML рядом с оригинальным .docx (не перезаписывая его)."""
    p = file_paths.get(task_id, {}).get(doc_type)
    if not p:
        raise HTTPException(404, "File not found")
    html_content = body.get("html", "")
    if not html_content:
        raise HTTPException(400, "Empty HTML")
    # Сохраняем HTML-версию рядом с оригиналом (оригинальный .docx из шаблона НЕ трогаем)
    edited_path = p.replace(".docx", "_edited.doc")
    # Оборачиваем в Word-совместимый HTML (Word откроет .doc с таблицами и форматированием)
    import re
    clean_html = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
    # Центрируем «СИНОПСИС ПРОТОКОЛА» — ищем любой тег, содержащий этот текст
    # и оборачиваем всю строку в <center> (самый надёжный способ для Word)
    clean_html = re.sub(
        r'<p[^>]*>.*?СИНОПСИС\s+ПРОТОКОЛА.*?</p>',
        '<center><p><b>СИНОПСИС ПРОТОКОЛА</b></p></center>',
        clean_html,
        flags=re.IGNORECASE | re.DOTALL
    )
    # Логируем первые 300 символов для отладки
    print(f"  📝 save_html: first 300 chars of clean_html: {clean_html[:300]}")
    word_html = f'''<html xmlns:o="urn:schemas-microsoft-com:office:office"
xmlns:w="urn:schemas-microsoft-com:office:word"
xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8">
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->
<style>
body {{ font-family: 'Times New Roman', serif; font-size: 12pt; line-height: 1.5; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ border: 1px solid #000; padding: 4pt 6pt; vertical-align: top; font-size: 12pt; }}
th {{ background: #f0f2ff; font-weight: bold; }}
p {{ margin: 3pt 0; font-size: 12pt; }}
h1, h2, h3 {{ text-align: center; font-size: 14pt; }}
</style>
</head>
<body>{clean_html}</body></html>'''
    with open(edited_path, "w", encoding="utf-8") as f:
        f.write(word_html)
    # Запоминаем путь отредактированной версии
    if task_id not in file_paths:
        file_paths[task_id] = {}
    file_paths[task_id][f"{doc_type}_edited"] = edited_path
    return {"ok": True, "path": edited_path}

@app.get("/api/history", response_model=List[HistoryItem])
async def get_history(): return history[:50]

@app.delete("/api/history/{task_id}")
async def del_history(task_id: str):
    global history; history = [h for h in history if h.task_id != task_id]; return {"ok": True}

@app.post("/api/chat")
async def chat(message: str = "", task_id: str = ""):
    return {"reply": "Понял, обрабатываю."}

# ═══ Dictionaries (подсказки, БЕЗ валидации) ═══
_INN = [
    {"ru":"Амлодипин","en":"Amlodipine"},{"ru":"Аторвастатин","en":"Atorvastatin"},
    {"ru":"Амоксициллин","en":"Amoxicillin"},{"ru":"Метформин","en":"Metformin"},
    {"ru":"Левофлоксацин","en":"Levofloxacin"},{"ru":"Омепразол","en":"Omeprazole"},
    {"ru":"Лизиноприл","en":"Lisinopril"},{"ru":"Розувастатин","en":"Rosuvastatin"},
    {"ru":"Кларитромицин","en":"Clarithromycin"},{"ru":"Диклофенак","en":"Diclofenac"},
    {"ru":"Ибупрофен","en":"Ibuprofen"},{"ru":"Силденафил","en":"Sildenafil"},
    {"ru":"Варфарин","en":"Warfarin"},{"ru":"Парацетамол","en":"Paracetamol"},
    {"ru":"Эналаприл","en":"Enalapril"},{"ru":"Лоратадин","en":"Loratadine"},
    {"ru":"Валсартан","en":"Valsartan"},{"ru":"Тамсулозин","en":"Tamsulosin"},
    {"ru":"Тенофовира алафенамид","en":"Tenofovir alafenamide"},
    {"ru":"Эмтрицитабин","en":"Emtricitabine"},{"ru":"Биктегравир","en":"Bictegravir"},
    {"ru":"биктегравир + тенофовира алафенамид + эмтрицитабин","en":"Bictegravir + Tenofovir alafenamide + Emtricitabine"},
    {"ru":"Дапаглифлозин","en":"Dapagliflozin"},{"ru":"Эмпаглифлозин","en":"Empagliflozin"},
    {"ru":"Апиксабан","en":"Apixaban"},{"ru":"Ривароксабан","en":"Rivaroxaban"},
    {"ru":"Ципрофлоксацин","en":"Ciprofloxacin"},{"ru":"Цефтриаксон","en":"Ceftriaxone"},
    {"ru":"Прегабалин","en":"Pregabalin"},{"ru":"Дулоксетин","en":"Duloxetine"},
]


# ═══ Глобальная HTTP-сессия (переиспользуется, не создаётся каждый раз) ═══

import aiohttp, urllib.parse

_http_session: aiohttp.ClientSession | None = None
_TIMEOUT = aiohttp.ClientTimeout(total=2)
_HEADERS = {"User-Agent": "Mozilla/5.0"}

async def _get_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS)
    return _http_session

@app.on_event("shutdown")
async def _close_session():
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()


# ═══ Yandex Suggest — универсальная функция ═══

async def _yandex_suggest(query: str, suffix: str = "", clean_fn=None) -> list[str]:
    """Подсказки через Yandex Suggest API (бесплатный, без ключа)."""
    search_q = f"{query} {suffix}".strip() if suffix else query
    url = f"https://suggest.yandex.ru/suggest-ff.cgi?part={urllib.parse.quote(search_q)}&uil=ru&n=10"
    results = []
    try:
        session = await _get_session()
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if isinstance(data, list) and len(data) >= 2:
                    for s in data[1]:
                        clean = clean_fn(s) if clean_fn else s.strip()
                        if clean and len(clean) >= 2:
                            results.append(clean)
    except Exception:
        pass
    return results


def _clean_inn(text: str) -> str:
    import re
    text = re.sub(
        r'\s+(мнн|инструкция|по применению|таблетки|капсулы|препарат|аналоги|цена|отзывы|'
        r'побочные|действия|показания|состав|дозировка|рецепт|купить|аптека).*$',
        '', text.strip(), flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[0].upper() + text[1:] if text else ""


def _clean_form(text: str) -> str:
    import re
    text = re.sub(
        r'\s+(это|что такое|инструкция|препарат|лекарство|лекарственная форма|определение|'
        r'виды|классификация|примеры|список|фото|купить).*$',
        '', text.strip(), flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip().lower()


def _clean_company(text: str) -> str:
    import re
    text = re.sub(
        r'\s+(официальный сайт|отзывы|вакансии|адрес|телефон|инн|огрн|реквизиты|продукция|'
        r'сайт|wiki|wikipedia|контакты|руководство|лицензия|история).*$',
        '', text.strip(), flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip()


def _clean_drug(text: str) -> str:
    import re
    original = text.strip()
    # Убираем хвосты: "инструкция", "цена", "аналоги" и т.д.
    text = re.sub(
        r'\s+(инструкция|по применению|цена|аналоги|отзывы|побочные|показания|состав|'
        r'купить|аптека|рецепт|дозировка|для чего|побочные действия|отличие|'
        r'и \w+|или \w+|что лучше|сравнение|замена|вместо).*$',
        '', original, flags=re.IGNORECASE)
    # Убираем "таблетки", "капсулы" в конце
    text = re.sub(r'\s+(таблетки|капсулы|раствор|мазь|гель|крем|сироп)$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[0].upper() + text[1:] if text else ""


def _extract_trade_name(text: str, inn: str) -> str:
    """Извлекает торговое название, убирая МНН из строки."""
    if not inn:
        return text
    # Убираем МНН из строки (регистронезависимо)
    import re
    cleaned = re.sub(re.escape(inn), '', text, flags=re.IGNORECASE).strip()
    # Убираем оставшиеся пробелы и мусор
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'^[\s\-\+\·,]+|[\s\-\+\·,]+$', '', cleaned)
    if cleaned and len(cleaned) >= 2:
        return cleaned[0].upper() + cleaned[1:]
    return text  # Если после удаления МНН ничего не осталось — возвращаем как есть


def _clean_excipient(text: str) -> str:
    import re
    text = re.sub(
        r'\s+(что это|это|применение|свойства|формула|пищевая добавка|в таблетках|'
        r'вред|польза|описание|e\s*\d+|купить|цена|производство).*$',
        '', text.strip(), flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip().lower()


async def _suggest_and_merge_strings(q: str, local: list[str], suffix: str, clean_fn) -> list[str]:
    """Объединяет локальные результаты с Yandex Suggest для строковых списков."""
    if len(local) < 5 and len(q) >= 2:
        try:
            suggestions = await _yandex_suggest(q, suffix=suffix, clean_fn=clean_fn)
            local_lower = {x.lower() for x in local}
            for s in suggestions:
                if s.lower() not in local_lower and s.lower() != q.lower():
                    local.append(s)
                    local_lower.add(s.lower())
        except Exception as e:
            print(f"  ⚠️ Yandex Suggest error: {e}")
    return local[:10]


# ═══ DaData — поиск компаний ═══

DADATA_TOKEN = os.getenv("DADATA_TOKEN", "")
print(f"  ℹ️ DADATA_TOKEN: {'✅ загружен (' + DADATA_TOKEN[:8] + '...)' if DADATA_TOKEN else '❌ не задан'}")
_YANDEX_FOLDER = os.getenv("YANDEX_FOLDER_ID", "")
_YANDEX_KEY = os.getenv("YANDEX_API_KEY", "")
print(f"  ℹ️ YANDEX_FOLDER_ID: {'✅ ' + _YANDEX_FOLDER[:8] + '...' if _YANDEX_FOLDER else '❌ не задан'}")
print(f"  ℹ️ YANDEX_API_KEY: {'✅ загружен' if _YANDEX_KEY else '❌ не задан'}")

async def _dadata_suggest_company(query: str, count: int = 10) -> list[dict]:
    """Поиск компании через DaData Suggestions API."""
    if not DADATA_TOKEN:
        print(f"  ⚠️ DaData: токен не задан (DADATA_TOKEN пустой)")
        return []
    url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {DADATA_TOKEN}",
    }
    payload = {"query": query, "count": count}
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as dadata_session:
            async with dadata_session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []
                    for s in data.get("suggestions", []):
                        d = s.get("data", {})
                        name_full = s.get("value", "")
                        inn = d.get("inn", "")
                        address = ""
                        if d.get("address"):
                            address = d["address"].get("value", "")
                        results.append({"name": name_full, "inn": inn, "address": address})
                    return results
                else:
                    body = await resp.text()
                    print(f"  ⚠️ DaData HTTP {resp.status}: {body[:200]}")
    except Exception as e:
        print(f"  ⚠️ DaData error: {type(e).__name__}: {e}")
    return []


async def _search_company_combined(q: str, kind: str = "") -> list[dict]:
    """Комбинированный поиск: DaData (приоритет) → Yandex Suggest (fallback)."""
    results = []
    if DADATA_TOKEN:
        dadata_results = await _dadata_suggest_company(q)
        for r in dadata_results:
            results.append({
                "name": r["name"], "inn": r.get("inn", ""),
                "address": r.get("address", ""), "source": "dadata",
            })
    if len(results) < 3:
        suffix_map = {
            "research_center": "клинический центр клинические исследования",
            "biolab": "биоаналитическая лаборатория",
            "insurance": "страховая компания",
            "general": "компания организация",
        }
        suffix = suffix_map.get(kind, "компания организация")
        try:
            yandex = await _yandex_suggest(q, suffix=suffix, clean_fn=_clean_company)
            existing = {r["name"].lower() for r in results}
            for s in yandex:
                if s.lower() not in existing and len(s) >= 2:
                    results.append({"name": s, "inn": "", "address": "", "source": "yandex"})
                    existing.add(s.lower())
        except Exception:
            pass
    if not results:
        results = [{"name": q, "inn": "", "address": ""}]
    return results[:10]


# ═══ Справочники ═══

@app.get("/api/dictionaries/inn")
async def inn(q: str = ""):
    if not q: return _INN[:10]
    ql = q.lower()
    local = [d for d in _INN if ql in d["ru"].lower() or ql in d["en"].lower()]
    if len(q) >= 2:
        try:
            suggestions = await _yandex_suggest(q, suffix="МНН", clean_fn=_clean_inn)
            local_names = {d["ru"].lower() for d in local}
            for s in suggestions:
                if s.lower() not in local_names:
                    local.append({"ru": s, "en": "", "source": "yandex"})
                    local_names.add(s.lower())
        except Exception as e:
            print(f"  ⚠️ Yandex INN error: {e}")
    if not local: local = [{"ru": q, "en": "", "custom": True}]
    return local[:10]


@app.get("/api/dictionaries/forms")
async def forms(q: str = ""):
    _FORMS = [
        "таблетки","таблетки, покрытые плёночной оболочкой","таблетки, покрытые пленочной оболочкой",
        "таблетки, покрытые оболочкой","таблетки пролонгированного действия","таблетки жевательные",
        "таблетки диспергируемые","таблетки для рассасывания","таблетки растворимые",
        "таблетки шипучие","таблетки сублингвальные","таблетки буккальные",
        "капсулы","капсулы твёрдые желатиновые","капсулы мягкие желатиновые",
        "капсулы кишечнорастворимые","капсулы с модифицированным высвобождением",
        "раствор для приёма внутрь","суспензия для приёма внутрь","сироп","эликсир",
        "капли для приёма внутрь","порошок для приготовления раствора для приёма внутрь",
        "гранулы для приготовления суспензии","гранулы","пастилки","леденцы",
        "порошок для приготовления раствора для инъекций",
        "лиофилизат для приготовления раствора для инъекций",
        "раствор для внутривенного введения","раствор для внутримышечного введения",
        "раствор для инъекций","эмульсия для инфузий","суспензия для инъекций",
        "крем","мазь","гель","гель для наружного применения","линимент","паста",
        "раствор для наружного применения","спрей для наружного применения",
        "суппозитории ректальные","суппозитории вагинальные",
        "спрей назальный","капли назальные","капли глазные","мазь глазная","гель глазной",
        "капли ушные","раствор для ингаляций","порошок для ингаляций",
        "аэрозоль для ингаляций дозированный","спрей для ингаляций",
        "пластырь трансдермальный","плёнка лекарственная",
    ]
    if q:
        ql = q.lower()
        local = [x for x in _FORMS if ql in x.lower()]
        return await _suggest_and_merge_strings(q, local, suffix="лекарственная форма", clean_fn=_clean_form)
    return _FORMS


@app.get("/api/dictionaries/manufacturers")
async def mfg(q: str = ""):
    if not q: return []
    results = await _search_company_combined(q, kind="general")
    return [r["name"] for r in results]


@app.get("/api/dictionaries/company")
async def company_search(q: str = "", kind: str = ""):
    if not q: return []
    return await _search_company_combined(q, kind=kind)


@app.get("/api/dictionaries/reference")
async def refs(inn: str = "", q: str = ""):
    """Референтные препараты по МНН — через Yandex GenSearch (ГРЛС)."""
    import re
    if not q and not inn:
        return []

    search_term = (q or inn).strip()
    # Минимум 4 символа — не тратим GenSearch на "па", "пал"
    if len(search_term) < 4:
        return []

    YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
    YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")

    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        print("⚠️  YANDEX_FOLDER_ID/YANDEX_API_KEY не заданы — fallback на Suggest")
        return await _refs_fallback_suggest(inn, q)

    query = (
        f"Перечисли все торговые названия лекарственных препаратов с МНН «{search_term}», "
        f"зарегистрированные в России (ГРЛС). "
        f"Укажи только торговые названия через запятую, без дозировок и лекарственных форм. "
        f"Начни с оригинального (референтного) препарата."
    )

    body = {
        "messages": [{"content": query, "role": "ROLE_USER"}],
        "folderId": YANDEX_FOLDER_ID,
        "searchType": "SEARCH_TYPE_RU",
        "fixMisspell": True,
    }
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        session = await _get_session()
        async with session.post(
            "https://searchapi.api.cloud.yandex.net/v2/gen/search",
            json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"❌ Yandex GenSearch reference: HTTP {resp.status}")
                return await _refs_fallback_suggest(inn, q)
            data = await resp.json(content_type=None)
    except Exception as e:
        print(f"❌ Yandex GenSearch reference error: {e}")
        return await _refs_fallback_suggest(inn, q)

    # GenSearch может вернуть массив
    if isinstance(data, list):
        data = data[0] if data else {}

    answer_text = ""
    try:
        message = data.get("message", {})
        if isinstance(message, list):
            message = message[0] if message else {}
        if isinstance(message, dict):
            answer_text = message.get("content", "")
        if isinstance(answer_text, list):
            parts = []
            for item in answer_text:
                if isinstance(item, dict):
                    parts.append(str(item.get("content", item.get("text", ""))))
                elif isinstance(item, str):
                    parts.append(item)
            answer_text = " ".join(parts)
    except Exception:
        answer_text = str(data)[:500]

    if not answer_text:
        return await _refs_fallback_suggest(inn, q)

    print(f"📋 GenSearch reference ({search_term}): {answer_text[:200]}")

    # Парсим торговые названия из ответа
    # pre_clean: убираем только markdown bold и сноски, сохраняем кавычки для парсинга
    pre_clean = answer_text.replace("**", "").strip()
    pre_clean = re.sub(r'\[\d+\]', '', pre_clean)

    # clean: полная очистка для fallback-парсинга
    clean = re.sub(r'\([^)]*\)', '', pre_clean)
    clean = re.sub(r'[®™«»„"""\*]', '', clean)

    # Извлекаем названия из ответа GenSearch
    names = []
    inn_lower = (inn or q or "").lower()

    # Мусорные слова
    _GARBAGE = {
        "препарат", "лекарство", "таблетки", "капсулы", "оригинальный", "аналоги",
        "торговое название", "инструкция", "цена", "купить", "отзывы", "состав",
        "это", "это химия", "химия", "формула", "действие", "механизм",
        "побочные", "показания", "противопоказания", "дозировка", "применение",
        "и другие", "другие", "также", "например", "включая", "некоторые",
    }

    def _extract_name(text: str) -> str | None:
        """Извлекает торговое название из строки GenSearch."""
        # Убираем markdown и сноски
        text = re.sub(r'\[\d+\]', '', text)
        text = text.replace("**", "").strip()
        # Извлекаем текст в кавычках — самый надёжный способ
        m = re.search(r'[«"„]([^»""]+)[»""]', text)
        if m:
            return m.group(1).strip()
        # Убираем скобки с содержимым
        text = re.sub(r'\([^)]*\)', '', text)
        text = re.sub(r'[®™«»„"""\*]', '', text)
        # Убираем всё после тире (— производитель, описание)
        text = re.split(r'\s*[—–-]\s', text)[0].strip()
        # Убираем вводные "Оригинальный:", "Референтный:" и т.д.
        text = re.sub(r'^(оригинальн\w*|референтн\w*|генерик\w*)\s*:\s*', '', text, flags=re.IGNORECASE)
        text = text.strip().strip('.,;:')
        return text if text and len(text) >= 2 else None

    def _is_valid(name: str) -> bool:
        nl = name.lower().strip()
        if not nl or len(nl) < 2 or len(nl) > 40:
            return False
        if nl == inn_lower or nl in _GARBAGE:
            return False
        if len(nl.split()) > 3:
            return False
        if re.match(r'^[\d\s,.\+/]+\s*(мг|мкг|г|мл|%|ме|ед)?$', nl):
            return False
        if any(w in nl for w in ['является', 'зарегистрирован', 'выпускается', 'содержит', 'применяется', 'торговые названия']):
            return False
        return True

    # Стратегия 1: разбиваем по строкам (markdown списки * или 1. 2. 3.)
    lines = pre_clean.split('\n')
    for line in lines:
        line = line.strip().lstrip('*•-– ').strip()
        if not line:
            continue
        extracted = _extract_name(line)
        if extracted and _is_valid(extracted):
            names.append(extracted)

    # Стратегия 2: если строки не дали результат — разбиваем по запятой из clean
    if not names:
        text_for_parse = re.sub(
            r'^.*?(торговые названия|зарегистрированы|препараты)\s*[:—–-]\s*',
            '', clean, count=1, flags=re.IGNORECASE
        )
        candidates = re.split(r'[,;]\s*|\d+[.)]\s*', text_for_parse)
        for c in candidates:
            extracted = _extract_name(c)
            if extracted and _is_valid(extracted):
                names.append(extracted)

    # Дедупликация
    seen = set()
    result = []
    for name in names:
        nl = name.lower()
        if nl not in seen:
            seen.add(nl)
            result.append({"name": name, "inn": inn or "", "mfg": "", "source": "yandex_gensearch"})

    if not result:
        # Если GenSearch не дал результатов — fallback
        return await _refs_fallback_suggest(inn, q)

    return result[:10]


async def _refs_fallback_suggest(inn: str, q: str):
    """Fallback: поиск через Yandex Suggest (менее точный)."""
    import re
    search_term = q or inn
    inn_lower = (inn or q or "").lower()
    seen = set()
    result = []

    def _extract(text):
        text = re.sub(
            r'\s+(инструкция|по применению|цена|аналоги|отзывы|таблетки|капсулы|'
            r'купить|препарат|лекарство|оригинальный|торговое название|это|что это).*$',
            '', text.strip(), flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        if inn_lower:
            text_low = text.lower()
            if text_low.startswith(inn_lower):
                remainder = text[len(inn_lower):].strip()
                return remainder[0].upper() + remainder[1:] if remainder else ""
        return text[0].upper() + text[1:] if text else ""

    for suffix in ["торговое название", "оригинальный препарат"]:
        if len(result) >= 5:
            break
        try:
            suggestions = await _yandex_suggest(search_term, suffix=suffix, clean_fn=_extract)
            for s in suggestions:
                sl = s.lower()
                if sl not in seen and len(s) >= 3 and sl != inn_lower and len(sl.split()) <= 3:
                    if not re.match(r'^[\d\s,.\+/]+\s*(мг|мкг|г|мл|%)?$', sl):
                        result.append({"name": s, "inn": inn or "", "mfg": "", "source": "yandex"})
                        seen.add(sl)
        except Exception:
            pass

    return result[:10]


@app.get("/api/dictionaries/excipients")
async def exc(q: str = ""):
    if not q: return []
    try:
        suggestions = await _yandex_suggest(q, suffix="вспомогательное вещество фармацевтика", clean_fn=_clean_excipient)
        seen = set()
        result = []
        for s in suggestions:
            if s.lower() not in seen and len(s) >= 2:
                result.append(s)
                seen.add(s.lower())
        return result[:10] if result else [q]
    except Exception:
        return [q]


@app.get("/api/health")
async def health():
    return {"status": "ok", "llm": os.getenv("LLM_PROVIDER","mock"), "time": datetime.now().isoformat()}