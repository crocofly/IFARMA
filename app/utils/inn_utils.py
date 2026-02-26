"""
inn_utils.py — Нормализация МНН (INN) для поиска ФК-параметров.

Проблема: МНН с солью ("тенофовира алафенамид фумарат") даёт плохие результаты
при поиске CVintra. Нужно искать по базовому МНН без соли.

Правила:
1. Удаляем соли (фумарат, гидрохлорид, малеат, мезилат, тартрат и т.д.)
2. Удаляем приставки форм (натрий, калий, кальций, магний)
3. Для перевода ru→en используем маппинг

Источник: INN Guidelines, WHO
"""

import re
from typing import Optional, Tuple


# ─── Маппинг популярных МНН ru→en ───
# Покрывает ~80% запросов для дженериков в РФ
_INN_RU_TO_EN = {
    "тенофовира алафенамид": "tenofovir alafenamide",
    "тенофовир": "tenofovir",
    "амлодипин": "amlodipine",
    "амлодипина": "amlodipine",
    "розувастатин": "rosuvastatin",
    "аторвастатин": "atorvastatin",
    "метформин": "metformin",
    "метформина": "metformin",
    "силденафил": "sildenafil",
    "тадалафил": "tadalafil",
    "омепразол": "omeprazole",
    "эзомепразол": "esomeprazole",
    "пантопразол": "pantoprazole",
    "лансопразол": "lansoprazole",
    "рабепразол": "rabeprazole",
    "ибупрофен": "ibuprofen",
    "диклофенак": "diclofenac",
    "парацетамол": "paracetamol",
    "лозартан": "losartan",
    "валсартан": "valsartan",
    "олмесартан": "olmesartan",
    "олмесартана": "olmesartan",
    "олмесартана медоксомил": "olmesartan medoxomil",
    "телмисартан": "telmisartan",
    "кандесартан": "candesartan",
    "ирбесартан": "irbesartan",
    "лизиноприл": "lisinopril",
    "эналаприл": "enalapril",
    "периндоприл": "perindopril",
    "рамиприл": "ramipril",
    "каптоприл": "captopril",
    "метопролол": "metoprolol",
    "бисопролол": "bisoprolol",
    "карведилол": "carvedilol",
    "небиволол": "nebivolol",
    "нифедипин": "nifedipine",
    "верапамил": "verapamil",
    "дилтиазем": "diltiazem",
    "варфарин": "warfarin",
    "клопидогрел": "clopidogrel",
    "ривароксабан": "rivaroxaban",
    "апиксабан": "apixaban",
    "дабигатран": "dabigatran",
    "габапентин": "gabapentin",
    "прегабалин": "pregabalin",
    "ламотриджин": "lamotrigine",
    "леветирацетам": "levetiracetam",
    "карбамазепин": "carbamazepine",
    "сертралин": "sertraline",
    "флуоксетин": "fluoxetine",
    "эсциталопрам": "escitalopram",
    "венлафаксин": "venlafaxine",
    "дулоксетин": "duloxetine",
    "кветиапин": "quetiapine",
    "оланзапин": "olanzapine",
    "арипипразол": "aripiprazole",
    "монтелукаст": "montelukast",
    "цетиризин": "cetirizine",
    "лоратадин": "loratadine",
    "дезлоратадин": "desloratadine",
    "левоцетиризин": "levocetirizine",
    "тамсулозин": "tamsulosin",
    "финастерид": "finasteride",
    "дутастерид": "dutasteride",
    "метотрексат": "methotrexate",
    "циклоспорин": "ciclosporin",
    "такролимус": "tacrolimus",
    "микофенолат": "mycophenolate",
    "микофеноловая кислота": "mycophenolic acid",
    "левотироксин": "levothyroxine",
    "дексаметазон": "dexamethasone",
    "преднизолон": "prednisolone",
    "метилпреднизолон": "methylprednisolone",
    "ципрофлоксацин": "ciprofloxacin",
    "левофлоксацин": "levofloxacin",
    "азитромицин": "azithromycin",
    "кларитромицин": "clarithromycin",
    "амоксициллин": "amoxicillin",
    "доксициклин": "doxycycline",
    "флуконазол": "fluconazole",
    "итраконазол": "itraconazole",
    "тербинафин": "terbinafine",
    "ацикловир": "aciclovir",
    "валацикловир": "valaciclovir",
    "осельтамивир": "oseltamivir",
    "софосбувир": "sofosbuvir",
    "даклатасвир": "daclatasvir",
    "ледипасвир": "ledipasvir",
    "энтекавир": "entecavir",
    "дапаглифлозин": "dapagliflozin",
    "эмпаглифлозин": "empagliflozin",
    "ситаглиптин": "sitagliptin",
    "линаглиптин": "linagliptin",
    "пиоглитазон": "pioglitazone",
    "глимепирид": "glimepiride",
    "гликлазид": "gliclazide",
    "индапамид": "indapamide",
    "гидрохлоротиазид": "hydrochlorothiazide",
    "фуросемид": "furosemide",
    "спиронолактон": "spironolactone",
    "торасемид": "torasemide",
    "эплеренон": "eplerenone",
    "фенофибрат": "fenofibrate",
    "эзетимиб": "ezetimibe",
    "ацетилсалициловая кислота": "acetylsalicylic acid",
    "мелоксикам": "meloxicam",
    "нимесулид": "nimesulide",
    "целекоксиб": "celecoxib",
    "эторикоксиб": "etoricoxib",
    "трамадол": "tramadol",
    "тапентадол": "tapentadol",
    "золпидем": "zolpidem",
    "донепезил": "donepezil",
    "мемантин": "memantine",
    "ропинирол": "ropinirole",
    "прамипексол": "pramipexole",
    "леводопа": "levodopa",
    "энтакапон": "entacapone",
    "баклофен": "baclofen",
    "тизанидин": "tizanidine",
    "толперизон": "tolperisone",
    "офатумумаб": "ofatumumab",
    "тофацитиниб": "tofacitinib",
    "барицитиниб": "baricitinib",
    "упадацитиниб": "upadacitinib",
    # Онкология
    "висмодегиб": "vismodegib",
    "палбоциклиб": "palbociclib",
    "рибоциклиб": "ribociclib",
    "абемациклиб": "abemaciclib",
    "иматиниб": "imatinib",
    "дазатиниб": "dasatinib",
    "нилотиниб": "nilotinib",
    "сорафениб": "sorafenib",
    "сунитиниб": "sunitinib",
    "пазопаниб": "pazopanib",
    "регорафениб": "regorafenib",
    "ленватиниб": "lenvatinib",
    "эрлотиниб": "erlotinib",
    "гефитиниб": "gefitinib",
    "афатиниб": "afatinib",
    "осимертиниб": "osimertinib",
    "кризотиниб": "crizotinib",
    "алектиниб": "alectinib",
    "вемурафениб": "vemurafenib",
    "дабрафениб": "dabrafenib",
    "траметиниб": "trametinib",
    "олапариб": "olaparib",
    "рукапариб": "rucaparib",
    "энзалутамид": "enzalutamide",
    "абиратерон": "abiraterone",
    "абиратерона": "abiraterone",
    "тамоксифен": "tamoxifen",
    "летрозол": "letrozole",
    "анастрозол": "anastrozole",
    "эксеместан": "exemestane",
    "капецитабин": "capecitabine",
    "темозоломид": "temozolomide",
    "иринотекан": "irinotecan",
    "эверолимус": "everolimus",
    "сиролимус": "sirolimus",
    "бортезомиб": "bortezomib",
    "леналидомид": "lenalidomide",
    "помалидомид": "pomalidomide",
    "ибрутиниб": "ibrutinib",
    "акалабрутиниб": "acalabrutinib",
    "руксолитиниб": "ruxolitinib",
    "нинтеданиб": "nintedanib",
    # Антиретровирусные
    "биктегравир": "bictegravir",
    "долутегравир": "dolutegravir",
    "ралтегравир": "raltegravir",
    "элвитегравир": "elvitegravir",
    "эмтрицитабин": "emtricitabine",
    "ламивудин": "lamivudine",
    "абакавир": "abacavir",
    "зидовудин": "zidovudine",
    "эфавиренз": "efavirenz",
    "невирапин": "nevirapine",
    "рилпивирин": "rilpivirine",
    "дарунавир": "darunavir",
    "атазанавир": "atazanavir",
    "лопинавир": "lopinavir",
    "ритонавир": "ritonavir",
    "кобицистат": "cobicistat",
    "маравирок": "maraviroc",
    # Кардиология / метаболизм
    "тикагрелор": "ticagrelor",
    "прасугрел": "prasugrel",
    "эдоксабан": "edoxaban",
    "сакубитрил": "sacubitril",
    "ивабрадин": "ivabradine",
    "ранолазин": "ranolazine",
    "алискирен": "aliskiren",
    "моксонидин": "moxonidine",
    "урапидил": "urapidil",
    "амиодарон": "amiodarone",
    "дронедарон": "dronedarone",
    "пропафенон": "propafenone",
    "аллопуринол": "allopurinol",
    "фебуксостат": "febuxostat",
    "колхицин": "colchicine",
    "орлистат": "orlistat",
    "лираглутид": "liraglutide",
    "семаглутид": "semaglutide",
    "дулаглутид": "dulaglutide",
    "канаглифлозин": "canagliflozin",
    # Неврология / психиатрия
    "рисперидон": "risperidone",
    "палиперидон": "paliperidone",
    "зипрасидон": "ziprasidone",
    "луразидон": "lurasidone",
    "клозапин": "clozapine",
    "пароксетин": "paroxetine",
    "циталопрам": "citalopram",
    "миртазапин": "mirtazapine",
    "тразодон": "trazodone",
    "бупропион": "bupropion",
    "вальпроевая кислота": "valproic acid",
    "вальпроат": "valproate",
    "топирамат": "topiramate",
    "зонисамид": "zonisamide",
    "окскарбазепин": "oxcarbazepine",
    "перампанел": "perampanel",
    "лакосамид": "lacosamide",
    # Пульмонология
    "сальбутамол": "salbutamol",
    "формотерол": "formoterol",
    "салметерол": "salmeterol",
    "индакатерол": "indacaterol",
    "тиотропий": "tiotropium",
    "будесонид": "budesonide",
    "флутиказон": "fluticasone",
    "беклометазон": "beclomethasone",
    "рофлумиласт": "roflumilast",
    # Гастроэнтерология
    "месалазин": "mesalazine",
    "сульфасалазин": "sulfasalazine",
    "урсодезоксихолевая кислота": "ursodeoxycholic acid",
    "домперидон": "domperidone",
    "метоклопрамид": "metoclopramide",
    "ондансетрон": "ondansetron",
    "апрепитант": "aprepitant",
    # Дерматология / аутоиммунные
    "ацитретин": "acitretin",
    "изотретиноин": "isotretinoin",
    "апремиласт": "apremilast",
    "диметилфумарат": "dimethyl fumarate",
    "финголимод": "fingolimod",
    "терифлуномид": "teriflunomide",
}


def resolve_inn_en(inn_ru: str) -> str:
    """
    Резолвит русский МНН в английский INN.

    Стратегия:
    1. Маппинг (мгновенно, без сети)
    2. Yandex Translate API (точный перевод)
    3. INN-транслитерация (offline fallback)
    """
    key = inn_ru.strip().lower()

    # 1. Прямой маппинг
    if key in _INN_RU_TO_EN:
        return _INN_RU_TO_EN[key]

    # Убираем соль → маппинг
    key_base = strip_salt_ru(key)
    if key_base in _INN_RU_TO_EN:
        return _INN_RU_TO_EN[key_base]

    if key_base.endswith("а"):
        key_no_a = key_base[:-1]
        if key_no_a in _INN_RU_TO_EN:
            return _INN_RU_TO_EN[key_no_a]

    # 2. Yandex Translate API
    translated = _translate_yandex(key_base)
    if translated:
        # Кэшируем в маппинг для будущих вызовов
        _INN_RU_TO_EN[key_base] = translated
        return translated

    # 3. INN-транслитерация (offline fallback)
    transliterated = _inn_transliterate(key_base)
    if transliterated:
        return transliterated

    return ""


def _translate_yandex(text: str) -> str:
    """
    Переводит текст ru→en через Yandex Translate API.

    Использует тот же YANDEX_FOLDER_ID / YANDEX_API_KEY
    что и Yandex Search.
    """
    import os
    folder_id = os.getenv("YANDEX_FOLDER_ID", "")
    api_key = os.getenv("YANDEX_API_KEY", "")

    if not folder_id or not api_key:
        return ""

    try:
        import requests
        resp = requests.post(
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
            json={
                "folderId": folder_id,
                "texts": [text],
                "sourceLanguageCode": "ru",
                "targetLanguageCode": "en",
            },
            headers={"Authorization": f"Api-Key {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            translations = data.get("translations", [])
            if translations:
                result = translations[0].get("text", "").strip().lower()
                # Убираем артикли и лишнее
                result = re.sub(r'^(the|a|an)\s+', '', result)
                if result and result != text:
                    return result
    except Exception as e:
        # Тихо падаем — перейдём к транслитерации
        pass

    return ""


def _inn_transliterate(inn_ru: str) -> str:
    """
    Фармацевтическая транслитерация МНН ru→en.

    Отличается от обычной транслитерации:
    - "ф" → "ph" (не "f") в фарм-контексте: нет, INN использует "f"
    - "кс" → "x"
    - "ц" → "c" перед e/i, иначе "ts"
    - Окончание "-иб" → "-ib"
    - Окончание "-ин" → "-ine" (для большинства)
    - Окончание "-ол" → "-ol"
    - Окончание "-ан" → "-an"
    - Окончание "-ид" → "-ide"
    - Окончание "-ат" → "-ate"
    - Окончание "-аза" → "-ase"
    - Окончание "-маб" → "-mab"
    - Окончание "-ниб" → "-nib"
    - Окончание "-вир" → "-vir"

    Правила INN максимально приближены к WHO INN Programme.
    """
    if not inn_ru:
        return ""

    text = inn_ru.strip().lower()

    # Специфичные INN-суффиксы (заменяем ПЕРЕД общей транслитерацией)
    # Порядок: от длинных к коротким
    _SUFFIX_MAP = [
        # Антитела
        ("зумаб", "zumab"), ("тузумаб", "tuzumab"), ("лизумаб", "lizumab"),
        ("цизумаб", "cizumab"), ("ксимаб", "ximab"), ("момаб", "momab"),
        ("тумаб", "tumab"), ("нумаб", "numab"),
        # Ингибиторы киназ
        ("тиниб", "tinib"), ("заниб", "zanib"), ("цениб", "cenib"),
        ("ратиниб", "ratinib"), ("метиниб", "metinib"),
        ("циклиб", "ciclib"),
        # Противовирусные
        ("бувир", "buvir"), ("превир", "previr"), ("асвир", "asvir"),
        ("тасвир", "tasvir"),
        # Окончания
        ("глифлозин", "gliflozin"), ("глиптин", "gliptin"),
        ("сартан", "sartan"), ("прил", "pril"), ("статин", "statin"),
        ("лукаст", "lukast"), ("дипин", "dipine"),
        ("тидин", "tidine"), ("празол", "prazole"),
        ("золам", "zolam"), ("барбитал", "barbital"),
        ("филлин", "phylline"), ("филлин", "phylline"),
        ("ксабан", "xaban"),
    ]

    for ru_suf, en_suf in _SUFFIX_MAP:
        if text.endswith(ru_suf):
            prefix = text[:-len(ru_suf)]
            return _basic_translit(prefix) + en_suf

    # Общие правила окончаний
    _ENDING_MAP = [
        ("егиб", "egib"), ("адиб", "adib"),
        ("олиб", "olib"), ("иниб", "inib"),
        ("атиниб", "atinib"),
        ("зомиб", "zomib"),
        ("циклин", "cycline"), ("мицин", "mycin"),
        ("бактам", "bactam"),
        ("золид", "zolid"),
        ("вудин", "vudine"), ("цитабин", "citabine"),
        ("кловир", "clovir"), ("цикловир", "ciclovir"),
        ("навир", "navir"), ("тегравир", "tegravir"),
        ("фенак", "fenac"),
        ("ксикам", "xicam"), ("коксиб", "coxib"),
        ("дегиб", "degib"),
    ]

    for ru_end, en_end in _ENDING_MAP:
        if text.endswith(ru_end):
            prefix = text[:-len(ru_end)]
            return _basic_translit(prefix) + en_end

    # Fallback: полная транслитерация
    return _basic_translit(text)


def _basic_translit(text: str) -> str:
    """Базовая фармацевтическая транслитерация."""
    _MAP = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
        'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z', 'и': 'i',
        'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
        'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch',
        'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya',
    }
    result = []
    for i, ch in enumerate(text):
        if ch in _MAP:
            result.append(_MAP[ch])
        elif ch == ' ':
            result.append(' ')
        else:
            result.append(ch)
    r = ''.join(result)
    # Пост-обработка INN
    r = r.replace('ks', 'x')  # "кс" → "x"
    return r

# ─── Соли и формы для удаления ───
# Русские окончания
SALT_FORMS_RU = [
    "фумарат", "гидрохлорид", "дигидрохлорид", "малеат", "мезилат",
    "безилат", "тартрат", "сукцинат", "цитрат", "фосфат", "дифосфат",
    "сульфат", "ацетат", "бензоат", "бромид", "хлорид", "йодид",
    "нитрат", "оксалат", "памоат", "стеарат", "тозилат", "трифлат",
    "лактат", "глюконат", "аспартат", "валерат", "пропионат",
    "бутират", "капроат", "олеат", "пальмитат",
    "натрия", "калия", "кальция", "магния",
    "дитозилат", "монофумарат", "дигидрат", "моногидрат",
    "гемифумарат", "полуфумарат", "полугидрат",
]

# Английские окончания
SALT_FORMS_EN = [
    "fumarate", "hemifumarate", "hydrochloride", "dihydrochloride",
    "maleate", "mesylate", "mesilate", "besylate", "besilate",
    "tartrate", "succinate", "citrate", "phosphate", "diphosphate",
    "sulfate", "sulphate", "acetate", "benzoate", "bromide",
    "chloride", "iodide", "nitrate", "oxalate", "pamoate",
    "stearate", "tosylate", "triflate", "lactate", "gluconate",
    "aspartate", "valerate", "propionate", "butyrate",
    "sodium", "potassium", "calcium", "magnesium",
    "ditosylate", "monohydrate", "dihydrate", "hemihydrate",
]


def strip_salt_ru(inn_ru: str) -> str:
    """
    Убирает соль из русского МНН.
    
    'тенофовира алафенамид фумарат' → 'тенофовира алафенамид'
    'амлодипина безилат' → 'амлодипина'
    'розувастатин кальция' → 'розувастатин'
    """
    result = inn_ru.strip().lower()
    for salt in sorted(SALT_FORMS_RU, key=len, reverse=True):
        # Удаляем соль если она в конце
        if result.endswith(salt):
            result = result[: -len(salt)].strip()
        # Или если она отдельным словом
        result = re.sub(r'\b' + re.escape(salt) + r'\b', '', result).strip()
    # Убираем лишние пробелы
    result = re.sub(r'\s+', ' ', result).strip()
    return result or inn_ru.strip()


def strip_salt_en(inn_en: str) -> str:
    """
    Убирает соль из английского INN.
    
    'tenofovir alafenamide fumarate' → 'tenofovir alafenamide'
    'amlodipine besylate' → 'amlodipine'
    """
    result = inn_en.strip().lower()
    for salt in sorted(SALT_FORMS_EN, key=len, reverse=True):
        if result.endswith(salt):
            result = result[: -len(salt)].strip()
        result = re.sub(r'\b' + re.escape(salt) + r'\b', '', result).strip()
    result = re.sub(r'\s+', ' ', result).strip()
    return result or inn_en.strip()


def normalize_inn(inn_ru: str, inn_en: Optional[str] = None) -> Tuple[str, str]:
    """
    Возвращает (inn_ru_base, inn_en_base) — МНН без соли.
    
    Если inn_en не указан — автоматически резолвит из маппинга.
    
    >>> normalize_inn("тенофовира алафенамид фумарат", "tenofovir alafenamide fumarate")
    ('тенофовира алафенамид', 'tenofovir alafenamide')
    
    >>> normalize_inn("тенофовира алафенамид фумарат")  # inn_en не указан!
    ('тенофовира алафенамид', 'tenofovir alafenamide')
    
    >>> normalize_inn("амлодипина безилат")
    ('амлодипина', 'amlodipine')
    """
    ru_base = strip_salt_ru(inn_ru)
    
    if inn_en:
        en_base = strip_salt_en(inn_en)
    else:
        # Автоматически резолвим из маппинга
        en_base = resolve_inn_en(inn_ru)
        if not en_base:
            en_base = resolve_inn_en(ru_base)
    
    return ru_base, en_base


def build_cv_search_queries(inn_ru: str, inn_en: Optional[str] = None) -> list[str]:
    """
    Генерирует список поисковых запросов для CVintra.
    
    Порядок приоритета:
    1. МНН без соли (en) + bioequivalence CVintra
    2. МНН без соли (en) + bioequivalence intrasubject variability
    3. МНН без соли (en) + bioequivalence Cmax CV
    4. МНН полное (en) + bioequivalence
    """
    ru_base, en_base = normalize_inn(inn_ru, inn_en)
    
    queries = []
    
    if en_base:
        queries.extend([
            f"{en_base} bioequivalence CVintra intrasubject variability",
            f"{en_base} bioequivalence Cmax coefficient of variation",
            f"{en_base} generic bioequivalence pharmacokinetics",
        ])
    
    # Полное МНН (с солью) — на случай если базовое не найдёт
    if inn_en and inn_en.lower() != en_base:
        queries.append(f"{inn_en} bioequivalence")
    
    if ru_base:
        queries.append(f"{ru_base} биоэквивалентность CVintra")
    
    return queries

# ═══════════════════════════════════════════════════════════
# Транслитерация EN → RU (для синопсиса)
# ═══════════════════════════════════════════════════════════

_EN_RU_MAP = {
    'a': 'а', 'b': 'б', 'c': 'ц', 'd': 'д', 'e': 'е',
    'f': 'ф', 'g': 'г', 'h': 'х', 'i': 'и', 'j': 'дж',
    'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
    'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т',
    'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'й',
    'z': 'з',
}


def _translit_en_to_ru(text: str) -> str:
    """Побуквенная транслитерация EN → RU. Сохраняет регистр."""
    if not text:
        return text
    result = []
    for ch in text:
        low = ch.lower()
        if low in _EN_RU_MAP:
            repl = _EN_RU_MAP[low]
            if ch.isupper():
                repl = repl[0].upper() + repl[1:]
            result.append(repl)
        else:
            result.append(ch)
    return "".join(result)



def _translate_word(text: str) -> str:
    """Переводит слово/фразу EN→RU через Yandex Translate (для стран)."""
    import os
    folder_id = os.getenv("YANDEX_FOLDER_ID", "")
    api_key = os.getenv("YANDEX_API_KEY", "")
    if not folder_id or not api_key:
        return _translit_en_to_ru(text)
    try:
        import requests as _req
        resp = _req.post(
            "https://translate.api.cloud.yandex.net/translate/v2/translate",
            json={
                "folderId": folder_id,
                "texts": [text.strip()],
                "sourceLanguageCode": "en",
                "targetLanguageCode": "ru",
            },
            headers={"Authorization": f"Api-Key {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            tr = resp.json().get("translations", [])
            if tr:
                result = tr[0].get("text", "").strip()
                if result:
                    return result
    except Exception:
        pass
    return _translit_en_to_ru(text)


def ensure_russian_text(text: str) -> str:
    """
    Транслитерирует латиницу → кириллицу.

    Последняя часть после последней запятой — страна → Yandex Translate.
    Всё остальное (название компании, вкл. запятые внутри) → побуквенный транслит.
    Кириллицу не трогает.
    """
    if not text or not text.strip():
        return text
    has_latin = any('a' <= c.lower() <= 'z' for c in text)
    if not has_latin:
        return text

    # Последняя часть после последней запятой — страна
    last_comma = text.rfind(",")
    if last_comma >= 0:
        company_part = text[:last_comma].strip()
        country_part = text[last_comma + 1:].strip()

        # Компания — транслит (если есть латиница)
        if any('a' <= c.lower() <= 'z' for c in company_part):
            company_part = _translit_en_to_ru(company_part)

        # Страна — перевод (если есть латиница)
        if any('a' <= c.lower() <= 'z' for c in country_part):
            country_part = _translate_word(country_part)

        return f"{company_part}, {country_part}"

    # Нет запятой — просто транслит
    return _translit_en_to_ru(text)