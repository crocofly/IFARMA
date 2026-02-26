# iFarma — Генератор синопсиса БЭ-исследования

Автоматизированная генерация синопсиса исследования биоэквивалентности (БЭ) лекарственных препаратов в соответствии с российским законодательством (Решение ЕЭК №85, ГОСТ Р 57082, ЕАЭС).

## Возможности

- **Автоматический поиск ФК-параметров** (T½, Cmax, Tmax, CVintra) по PubMed, FDA BE Guidance, инструкциям к препаратам
- **Расчёт дизайна исследования** — перекрёстный 2×2, реплицированный 4-периодный или параллельный в зависимости от ФК-профиля
- **Расчёт размера выборки** с учётом dropout, HVD-статуса, объёма крови
- **Регуляторная проверка** по Решению ЕЭК №85 (13 контрольных точек)
- **Экспорт в DOCX** — синопсис + обоснования с PK-кривой
- **Парсинг инструкций** — Vidal, ГРЛС, medi.ru, RLS, Etabl
- **Перевод МНН** ru→en — словарь + Yandex Translate + INN-транслитерация

## Структура проекта

```
ifarma_project/
├── main.py                          # CLI — точка входа
├── app/
│   ├── config/
│   │   └── settings.py              # Конфигурация (.env)
│   ├── models/
│   │   ├── common.py                # PipelineInput, базовые модели
│   │   ├── pk.py                    # PKResult, PKParameter
│   │   ├── design.py                # DesignResult, DesignType
│   │   └── sample_size.py           # SampleSizeResult
│   ├── agents/
│   │   ├── base.py                  # BaseAgent, AgentResult
│   │   ├── pk_literature.py         # PK Agent — ФК-параметры
│   │   ├── regulatory.py            # Regulatory Agent — проверка по Решению №85
│   │   ├── study_design.py          # Design Agent — выбор дизайна
│   │   ├── sample_size.py           # Sample Size Agent — расчёт выборки
│   │   └── synopsis_generator.py    # Генерация текста синопсиса
│   ├── pipeline/
│   │   └── pipeline.py              # Оркестратор агентов
│   ├── services/
│   │   ├── pk/
│   │   │   └── cv_intra.py          # Поиск CVintra + T½ по PubMed/FDA
│   │   ├── llm/
│   │   │   ├── base.py              # Абстрактный LLM-клиент
│   │   │   ├── groq_client.py       # Groq (LLaMA)
│   │   │   └── factory.py           # Фабрика LLM-клиентов
│   │   ├── search/
│   │   │   ├── yandex_search.py     # Yandex Search API
│   │   │   ├── protocol_search.py   # Поиск протоколов БЭ
│   │   │   └── rag_decision85.py    # RAG по Решению №85
│   │   └── export/
│   │       ├── docx_exporter.py     # Экспорт синопсиса в DOCX
│   │       ├── rationale_exporter.py # Обоснования в DOCX
│   │       └── pk_curve.py          # PK-кривая (matplotlib)
│   └── utils/
│       ├── inn_utils.py             # Нормализация МНН, перевод ru→en
│       ├── drug_info_parser.py      # Парсинг инструкций (vidal/grls/rls)
│       ├── blood_sampling.py        # Расчёт схемы отбора крови
│       ├── criteria_generator.py    # Критерии включения/исключения
│       ├── methodology_text.py      # Текст методологии
│       └── study_timeline.py        # Таймлайн исследования
├── data/
│   ├── шаблон_для_заполнения.docx   # DOCX-шаблон синопсиса
│   └── decision85/                   # Текст Решения ЕЭК №85 для RAG
├── output/                           # Результаты генерации
├── .env                              # API-ключи (не в git!)
└── requirements.txt                  # Зависимости
```

## Установка

```bash
# 1. Клонировать / распаковать проект
cd ifarma_project

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить API-ключи
cp .env.example .env
# Отредактировать .env — указать ключи
```

## Настройка `.env`

```env
# LLM-провайдер: "groq" (рекомендуется) или "gemini"
LLM_PROVIDER=groq

# Groq API (https://console.groq.com)
GROQ_API_KEY=gsk_...

# Yandex Cloud (для поиска CVintra, T½, перевода МНН)
YANDEX_FOLDER_ID=b1g...
YANDEX_API_KEY=AQVN...

# Опционально: Gemini API
# GEMINI_API_KEY=AIza...
```

## Использование

### Базовый запуск

```bash
python main.py "амлодипин" \
  --dose "10 мг" \
  --ref-drug "Норваск®"
```

### Полный запуск со всеми параметрами

```bash
python main.py "висмодегиб" \
  --study-id "ONC-VIS-01" \
  --sponsor "ООО «Фармстандарт-Лексредства»" \
  --sponsor-country "Россия" \
  --center "ООО «ИФАРМА»" \
  --lab "ООО «ИФАРМА»" \
  --insurance "АО «СОГАЗ»" \
  --form "капсулы" \
  --dose "150 мг" \
  --release "immediate" \
  --manufacturer "ООО «Фармстандарт-Лексредства», Россия" \
  --ref-drug "Эриведж®" \
  --ref-form "капсулы" \
  --ref-dose "150 мг" \
  --ref-manufacturer "Ф. Хоффман-Ля Рош Лтд., Швейцария" \
  --sex "males_and_females" \
  --intake "fasting" \
  --template "data/шаблон_для_заполнения.docx"
```

### Ручное указание ФК-параметров

```bash
python main.py "висмодегиб" \
  --dose "150 мг" \
  --ref-drug "Эриведж®" \
  --t-half 288 \       # T½ = 288 ч (12 дней) — ручной ввод
  --cv 45              # CVintra = 45% — ручной ввод
```

## Аргументы CLI

| Аргумент | Описание | Пример |
|----------|----------|--------|
| `МНН` | Международное непатентованное название (позиционный) | `"амлодипин"` |
| `--dose` | Дозировка | `"10 мг"` |
| `--form` | Лекарственная форма | `"таблетки"` |
| `--release` | Тип высвобождения: `immediate` / `modified` | `"immediate"` |
| `--ref-drug` | Торговое название референтного препарата | `"Норваск®"` |
| `--ref-dose` | Дозировка референтного | `"10 мг"` |
| `--ref-form` | Форма референтного | `"таблетки"` |
| `--ref-manufacturer` | Производитель референтного | `"Pfizer, США"` |
| `--sex` | Пол добровольцев: `males_only` / `females_only` / `males_and_females` | `"males_only"` |
| `--intake` | Режим приёма: `fasting` / `fed` | `"fasting"` |
| `--study-id` | Идентификатор исследования | `"BE-AML-01"` |
| `--sponsor` | Спонсор | `"ООО «Фарма»"` |
| `--sponsor-country` | Страна спонсора | `"Россия"` |
| `--center` | Клинический центр | `"ООО «ИФАРМА»"` |
| `--lab` | Биоаналитическая лаборатория | `"ООО «ИФАРМА»"` |
| `--insurance` | Страховая компания | `"АО «СОГАЗ»"` |
| `--manufacturer` | Производитель тестового препарата | `"ООО «Фарма», Россия"` |
| `--template` | Путь к DOCX-шаблону | `"data/шаблон.docx"` |
| `--t-half` | T½ вручную (часы) — наивысший приоритет | `288` |
| `--cv` | CVintra вручную (%) — наивысший приоритет | `45` |

## Архитектура пайплайна

```
┌─────────────────────────────────────────────────┐
│                  CLI (main.py)                    │
│        PipelineInput → Pipeline.run()            │
└──────────────────────┬──────────────────────────┘
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
   ┌─────────────────┐  ┌──────────────────┐
   │   PK Agent       │  │ Regulatory Agent  │  ← параллельно
   │                  │  │                  │
   │ 1. CVintra       │  │ Проверка по      │
   │    (PubMed)      │  │ Решению №85      │
   │ 2. T½/Tmax/Cmax  │  │ (13 чек-поинтов) │
   │    (PubMed)      │  │                  │
   │ 3. Инструкция    │  └──────────────────┘
   │    (vidal/grls)  │
   │ 4. LLM (пробелы) │
   └────────┬─────────┘
            │
            ▼
   ┌─────────────────┐
   │  Design Agent    │
   │                  │
   │ Дизайн, отмыв,  │
   │ dropout, границы │
   └────────┬─────────┘
            │
            ▼
   ┌─────────────────┐
   │ Sample Size Agent│
   │                  │
   │ N, объём крови,  │
   │ кол-во образцов  │
   └────────┬─────────┘
            │
            ▼
   ┌─────────────────────────────┐
   │  Synopsis Generator + Export │
   │                              │
   │ • synopsis.docx              │
   │ • rationale.docx             │
   │ • pk_curve.png               │
   │ • data.json                  │
   └──────────────────────────────┘
```

## Приоритеты источников данных

| Параметр | Приоритет 1 | Приоритет 2 | Приоритет 3 | Приоритет 4 |
|----------|-------------|-------------|-------------|-------------|
| **CVintra** | `--cv` (CLI) | PubMed CI | PubMed direct | FDA Guidance |
| **T½** | `--t-half` (CLI) | PubMed PK | Инструкция | LLM |
| **Tmax** | PubMed PK | Инструкция | LLM | — |
| **Cmax** | PubMed PK | Инструкция | LLM | — |
| **Пол** | `--sex` (CLI) | Инструкция (показания) | По умолчанию: М | — |
| **Приём** | `--intake` (CLI) | Инструкция | По умолчанию: натощак | — |

## Источники инструкций (порядок поиска)

1. **Vidal.ru** — по торговому названию (транслитерация + варианты)
2. **Vidal.ru search** — поиск по сайту → переход по ссылке
3. **Medi.ru** — полная инструкция с фармакокинетикой
4. **RLS active-substance** — полная ФК по МНН
5. **ГРЛС** (grls.rosminzdrav.ru) — государственный реестр
6. **RLS search** — поисковый fallback
7. **Etabl.ru** — аптечный справочник

## Перевод МНН (ru → en)

1. **Словарь** — 240+ МНН (мгновенно, без сети)
2. **Yandex Translate API** — точный перевод для неизвестных МНН
3. **INN-транслитерация** — offline fallback по фармацевтическим правилам

## Выходные файлы

| Файл | Описание |
|------|----------|
| `synopsis_<МНН>_v<N>.docx` | Синопсис исследования (заполненный шаблон) |
| `rationale_<МНН>_v<N>.docx` | Научные обоснования с PK-графиками и расчётами |
| `pk_curve_<МНН>_v<N>.png` | PK-кривая (Cmax, Tmax, AUC) |
| `data_<МНН>_v<N>.json` | Все данные в машиночитаемом формате |

## Лицензия

Проприетарный. Для внутреннего использования.
