import '../models/models.dart';

class Dictionaries {
  static const List<InnEntry> innDb = [
    InnEntry(ru: 'Амлодипин', en: 'Amlodipine'),
    InnEntry(ru: 'Аторвастатин', en: 'Atorvastatin'),
    InnEntry(ru: 'Амоксициллин', en: 'Amoxicillin'),
    InnEntry(ru: 'Метформин', en: 'Metformin'),
    InnEntry(ru: 'Левофлоксацин', en: 'Levofloxacin'),
    InnEntry(ru: 'Омепразол', en: 'Omeprazole'),
    InnEntry(ru: 'Лизиноприл', en: 'Lisinopril'),
    InnEntry(ru: 'Розувастатин', en: 'Rosuvastatin'),
    InnEntry(ru: 'Кларитромицин', en: 'Clarithromycin'),
    InnEntry(ru: 'Диклофенак', en: 'Diclofenac'),
    InnEntry(ru: 'Ибупрофен', en: 'Ibuprofen'),
    InnEntry(ru: 'Силденафил', en: 'Sildenafil'),
    InnEntry(ru: 'Варфарин', en: 'Warfarin'),
    InnEntry(ru: 'Парацетамол', en: 'Paracetamol'),
    InnEntry(ru: 'Каптоприл', en: 'Captopril'),
    InnEntry(ru: 'Цефтриаксон', en: 'Ceftriaxone'),
    InnEntry(ru: 'Ципрофлоксацин', en: 'Ciprofloxacin'),
    InnEntry(ru: 'Эналаприл', en: 'Enalapril'),
    InnEntry(ru: 'Лоратадин', en: 'Loratadine'),
    InnEntry(ru: 'Пантопразол', en: 'Pantoprazole'),
    InnEntry(ru: 'Тамсулозин', en: 'Tamsulosin'),
    InnEntry(ru: 'Прогестерон', en: 'Progesterone'),
    InnEntry(ru: 'Валсартан', en: 'Valsartan'),
  ];

  static const List<String> dosageForms = [
    'таблетки',
    'таблетки, покрытые плёночной оболочкой',
    'таблетки, покрытые оболочкой',
    'таблетки пролонгированного действия',
    'таблетки жевательные',
    'таблетки диспергируемые',
    'таблетки шипучие',
    'таблетки подъязычные',
    'капсулы',
    'капсулы твёрдые желатиновые',
    'капсулы мягкие желатиновые',
    'капсулы кишечнорастворимые',
    'капсулы пролонгированного действия',
    'раствор для приёма внутрь',
    'раствор для инъекций',
    'раствор для инфузий',
    'суспензия для приёма внутрь',
    'порошок для приготовления суспензии',
    'сироп',
    'крем',
    'мазь',
    'гель',
    'суппозитории ректальные',
    'пластырь трансдермальный',
    'спрей назальный',
    'аэрозоль для ингаляций',
    'капли глазные',
    'лиофилизат для приготовления раствора',
  ];

  static const Map<String, List<String>> dosagesByInn = {
    'Амлодипин': ['2,5 мг', '5 мг', '10 мг'],
    'Аторвастатин': ['10 мг', '20 мг', '40 мг', '80 мг'],
    'Метформин': ['500 мг', '850 мг', '1000 мг'],
    'Левофлоксацин': ['250 мг', '500 мг', '750 мг'],
    'Омепразол': ['10 мг', '20 мг', '40 мг'],
    'Розувастатин': ['5 мг', '10 мг', '20 мг', '40 мг'],
  };

  static const List<String> manufacturers = [
    'КРКА, д.д., Ново место',
    'Тева Фармацевтикал Индастриз',
    'Гедеон Рихтер',
    'Сандоз',
    'ШТАДА',
    'Вертекс',
    'Фармстандарт',
    'Озон',
    'Канонфарма продакшн',
    'Биокад',
    'Р-Фарм',
    'Герофарм',
    'Акрихин',
    'Нижфарм',
    'Фармасинтез',
    'Zentiva',
    'Servier',
    'Алиум',
    'Промомед',
    'Обнинская ХФК',
  ];

  static const List<RefDrugEntry> referenceDrugs = [
    RefDrugEntry(name: 'Норваск', inn: 'Амлодипин', manufacturer: 'Pfizer'),
    RefDrugEntry(name: 'Липримар', inn: 'Аторвастатин', manufacturer: 'Pfizer'),
    RefDrugEntry(name: 'Амоксил', inn: 'Амоксициллин', manufacturer: 'GSK'),
    RefDrugEntry(name: 'Глюкофаж', inn: 'Метформин', manufacturer: 'Merck'),
    RefDrugEntry(name: 'Таваник', inn: 'Левофлоксацин', manufacturer: 'Sanofi'),
    RefDrugEntry(name: 'Лосек', inn: 'Омепразол', manufacturer: 'AstraZeneca'),
    RefDrugEntry(name: 'Крестор', inn: 'Розувастатин', manufacturer: 'AstraZeneca'),
    RefDrugEntry(name: 'Вольтарен', inn: 'Диклофенак', manufacturer: 'Novartis'),
    RefDrugEntry(name: 'Нурофен', inn: 'Ибупрофен', manufacturer: 'Reckitt'),
    RefDrugEntry(name: 'Виагра', inn: 'Силденафил', manufacturer: 'Pfizer'),
  ];

  static const List<String> excipientsList = [
    'лактозы моногидрат',
    'целлюлоза микрокристаллическая',
    'кроскармеллоза натрия',
    'повидон',
    'магния стеарат',
    'кремния диоксид коллоидный',
    'крахмал кукурузный',
    'тальк',
    'титана диоксид',
    'гипромеллоза',
    'полиэтиленгликоль',
    'натрия крахмалгликолят',
    'маннитол',
    'сорбитол',
    'натрия лаурилсульфат',
    'кальция гидрофосфат',
    'железа оксид жёлтый',
    'макрогол',
    'полисорбат 80',
  ];

  /// Fuzzy search: returns true if query loosely matches text
  static bool fuzzyMatch(String query, String text) {
    final q = query.toLowerCase();
    final t = text.toLowerCase();
    if (t.contains(q)) return true;
    if (q.length >= 3) {
      for (int i = 0; i < q.length; i++) {
        final variant = q.substring(0, i) + q.substring(i + 1);
        if (t.contains(variant)) return true;
      }
    }
    return false;
  }

  /// Simple similarity score 0..1
  static double similarity(String a, String b) {
    if (a.isEmpty || b.isEmpty) return 0;
    int matches = 0;
    final minLen = a.length < b.length ? a.length : b.length;
    final maxLen = a.length > b.length ? a.length : b.length;
    for (int i = 0; i < minLen; i++) {
      if (a[i] == b[i]) matches++;
    }
    return matches / maxLen;
  }

  /// Find closest INN suggestion
  static InnEntry? findClosestInn(String query) {
    if (query.length < 3) return null;
    final q = query.toLowerCase();
    double bestScore = 0;
    InnEntry? best;
    for (final inn in innDb) {
      final s1 = similarity(q, inn.ru.toLowerCase());
      final s2 = similarity(q, inn.en.toLowerCase());
      final score = s1 > s2 ? s1 : s2;
      if (score > bestScore && score > 0.4) {
        bestScore = score;
        best = inn;
      }
    }
    return best;
  }
}
