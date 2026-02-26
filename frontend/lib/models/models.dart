/// Form input data — mirrors PipelineInput from common.py
class FormData {
  String innRu;
  String dosageForm;
  String dosage;
  String drugName;
  String manufacturer;
  bool mfgIsSponsor;
  String sponsor;
  String referenceDrug;
  List<String> excipients;
  String storageConditions;
  String protocolId;
  String protocolMode; // 'manual' | 'auto' | 'empty'
  String researchCenter;
  String bioanalyticalLab;
  String insuranceCompany;
  double? cvIntra;
  double? tHalfHours;
  String sexRestriction; // '' | 'males_only' | 'females_only' | 'males_and_females'
  int ageMin;
  int ageMax;
  String smokingRestriction; // '' | 'non_smokers' | 'cotinine' | 'no_restriction'
  // Расчётные константы (overrides)
  double? overridePower;         // По умолч. 0.80
  double? overrideAlpha;         // По умолч. 0.05
  double? overrideGmr;           // По умолч. 0.95
  double? overrideDropoutRate;   // По умолч. рассчитывается AI
  double? overrideScreenfailRate; // По умолч. 0.15
  int? overrideMinSubjects;      // По умолч. 12
  double? overrideBloodPerPoint; // По умолч. 5.0 мл
  double? overrideMaxBlood;      // По умолч. 450 мл

  FormData({
    this.innRu = '',
    this.dosageForm = '',
    this.dosage = '',
    this.drugName = '',
    this.manufacturer = '',
    this.mfgIsSponsor = true,
    this.sponsor = '',
    this.referenceDrug = '',
    this.excipients = const [],
    this.storageConditions = '',
    this.protocolId = '',
    this.protocolMode = 'manual',
    this.researchCenter = '',
    this.bioanalyticalLab = '',
    this.insuranceCompany = '',
    this.cvIntra,
    this.tHalfHours,
    this.sexRestriction = '',
    this.ageMin = 18,
    this.ageMax = 45,
    this.smokingRestriction = '',
    this.overridePower,
    this.overrideAlpha,
    this.overrideGmr,
    this.overrideDropoutRate,
    this.overrideScreenfailRate,
    this.overrideMinSubjects,
    this.overrideBloodPerPoint,
    this.overrideMaxBlood,
  });

  String get effectiveSponsor => mfgIsSponsor ? manufacturer : sponsor;
}

/// INN dictionary entry
class InnEntry {
  final String ru;
  final String en;
  const InnEntry({required this.ru, required this.en});
}

/// Reference drug entry
class RefDrugEntry {
  final String name;
  final String inn;
  final String manufacturer;
  const RefDrugEntry({
    required this.name,
    required this.inn,
    required this.manufacturer,
  });
}

/// History item
class HistoryItem {
  final String id;
  final String inn;
  final String form;
  final String dose;
  final String date;
  final String synopsisHtml;

  const HistoryItem({
    required this.id,
    required this.inn,
    required this.form,
    required this.dose,
    required this.date,
    required this.synopsisHtml,
  });
}

/// Chat message
class ChatMessage {
  final String text;
  final ChatRole role;
  final DateTime time;

  ChatMessage({
    required this.text,
    required this.role,
    DateTime? time,
  }) : time = time ?? DateTime.now();
}

enum ChatRole { user, bot, system }

/// Pipeline step
class PipelineStep {
  final String id;
  final String label;
  final String icon;
  StepStatus status;

  PipelineStep({
    required this.id,
    required this.label,
    required this.icon,
    this.status = StepStatus.pending,
  });
}

enum StepStatus { pending, running, done }