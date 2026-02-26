import 'dart:async';
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import '../models/models.dart';
import 'api_service.dart';

class AppState extends ChangeNotifier {
  // ── Form ──
  final FormData form = FormData();

  // ── Pipeline ──
  bool isGenerating = false;
  double progress = 0;
  final List<PipelineStep> pipelineSteps = [
    PipelineStep(id: 's1', label: 'PK Литература', icon: '🔍'),
    PipelineStep(id: 's2', label: 'Регуляторный агент', icon: '📋'),
    PipelineStep(id: 's3', label: 'Дизайн исследования', icon: '⚗️'),
    PipelineStep(id: 's4', label: 'Расчёт выборки', icon: '📊'),
    PipelineStep(id: 's5', label: 'Генерация синопсиса', icon: '📄'),
  ];
  bool generationComplete = false;
  String? currentTaskId;

  // ── Editor ──
  String editorContent = '';
  String editorFileName = 'Редактор документов';
  String editorStatus = 'idle';
  String? currentDoc;

  // ── History ──
  final List<HistoryItem> history = [];

  // ── Chat ──
  final List<ChatMessage> chatMessages = [
    ChatMessage(text: 'Привет! Я пока что не работаю, но скоро смогу помочь с правками, вопросами по регуляторике или пересчётом параметров.', role: ChatRole.bot),
  ];
  bool chatExpanded = true;

  // ── API result ──
  Map<String, dynamic>? lastResult;

  // ══════════════════════════
  // FORM
  // ══════════════════════════

  void updateForm(void Function(FormData f) updater) {
    updater(form);
    notifyListeners();
  }

  String? validateForm() {
    if (form.innRu.trim().isEmpty) return 'Введите МНН';
    if (form.dosageForm.trim().isEmpty) return 'Укажите лекарственную форму';
    if (form.dosage.trim().isEmpty) return 'Укажите дозировку';
    if (form.storageConditions.trim().isEmpty) return 'Укажите условия хранения ИП';
    return null;
  }

  // ══════════════════════════
  // GENERATION — REAL API
  // ══════════════════════════

  Future<void> startGeneration() async {
    final error = validateForm();
    if (error != null) return;

    isGenerating = true;
    generationComplete = false;
    progress = 0;
    lastResult = null;
    for (final step in pipelineSteps) {
      step.status = StepStatus.pending;
    }
    notifyListeners();
    addChatMessage('🔄 Отправляю запрос на сервер для «${form.innRu}»…', ChatRole.system);

    try {
      // 1. POST /api/generate
      final body = {
        'inn_ru': form.innRu.trim(),
        'dosage_form': form.dosageForm.trim(),
        'dosage': form.dosage.trim(),
        'storage_conditions': form.storageConditions.trim(),
        'drug_name_trade': form.drugName.isNotEmpty ? form.drugName : null,
        'manufacturer': form.manufacturer.isNotEmpty ? form.manufacturer : null,
        'manufacturer_is_sponsor': form.mfgIsSponsor,
        'sponsor': form.mfgIsSponsor ? null : (form.sponsor.isNotEmpty ? form.sponsor : null),
        'protocol_id': form.protocolId.isNotEmpty ? form.protocolId : null,
        'protocol_mode': form.protocolMode,
        'research_center': form.researchCenter.isNotEmpty ? form.researchCenter : null,
        'bioanalytical_lab': form.bioanalyticalLab.isNotEmpty ? form.bioanalyticalLab : null,
        'insurance_company': form.insuranceCompany.isNotEmpty ? form.insuranceCompany : null,
        'reference_drug_name': form.referenceDrug.isNotEmpty ? form.referenceDrug : null,
        'excipients': form.excipients.isNotEmpty ? form.excipients : null,
        'cv_intra': form.cvIntra,
        't_half_hours': form.tHalfHours,
        'sex_restriction': form.sexRestriction,
        'age_min': form.ageMin,
        'age_max': form.ageMax,
        'smoking_restriction': form.smokingRestriction,
        // Overrides
        'override_power': form.overridePower,
        'override_alpha': form.overrideAlpha,
        'override_gmr': form.overrideGmr,
        'override_dropout_rate': form.overrideDropoutRate,
        'override_screenfail_rate': form.overrideScreenfailRate,
        'override_min_subjects': form.overrideMinSubjects,
        'override_blood_per_point_ml': form.overrideBloodPerPoint,
        'override_max_blood_ml': form.overrideMaxBlood,
      };

      final startResp = await ApiService.startGeneration(body);
      currentTaskId = startResp['task_id'] as String?;

      if (currentTaskId == null) throw Exception('Нет task_id в ответе');

      addChatMessage('📡 Задача ${currentTaskId} запущена. Ожидаю результат…', ChatRole.system);

      // Начинаем показывать прогресс
      pipelineSteps[0].status = StepStatus.running;
      pipelineSteps[1].status = StepStatus.running;
      progress = 0.05;
      notifyListeners();

      // 2. Polling GET /api/generate/{task_id}
      await _pollUntilDone(currentTaskId!);

    } catch (e) {
      isGenerating = false;
      addChatMessage('❌ Ошибка: $e', ChatRole.system);
      for (final step in pipelineSteps) {
        if (step.status == StepStatus.running) step.status = StepStatus.pending;
      }
      notifyListeners();
    }
  }

  Future<void> _pollUntilDone(String taskId) async {
    const pollInterval = Duration(seconds: 2);
    const maxPolls = 120; // 4 минуты макс
    int polls = 0;

    while (polls < maxPolls) {
      await Future.delayed(pollInterval);
      polls++;

      try {
        final resp = await ApiService.getTaskStatus(taskId);
        final status = resp['status'] as String? ?? '';
        final prog = (resp['progress'] as num?)?.toDouble() ?? 0;
        final steps = resp['steps'] as List? ?? [];

        // Обновляем шаги
        for (int i = 0; i < steps.length && i < pipelineSteps.length; i++) {
          final s = steps[i] as Map<String, dynamic>;
          final st = s['status'] as String? ?? 'pending';
          pipelineSteps[i].status = st == 'done'
              ? StepStatus.done
              : st == 'running'
                  ? StepStatus.running
                  : StepStatus.pending;
        }

        progress = prog;
        notifyListeners();

        if (status == 'done') {
          lastResult = resp['result'] as Map<String, dynamic>?;
          _onGenerationDone(taskId);
          return;
        }

        if (status == 'error') {
          final err = resp['error'] ?? 'Неизвестная ошибка';
          throw Exception(err);
        }
      } catch (e) {
        if (e.toString().contains('error') || polls >= maxPolls) {
          isGenerating = false;
          addChatMessage('❌ Ошибка: $e', ChatRole.system);
          notifyListeners();
          return;
        }
      }
    }

    isGenerating = false;
    addChatMessage('⏰ Таймаут: генерация заняла слишком много времени', ChatRole.system);
    notifyListeners();
  }

  void _onGenerationDone(String taskId) async {
    for (final step in pipelineSteps) {
      step.status = StepStatus.done;
    }
    progress = 1.0;
    generationComplete = true;
    isGenerating = false;

    // Загружаем HTML preview с сервера — ОДИН раз
    currentDoc = 'synopsis';
    editorFileName = 'Синопсис_${form.innRu}.docx';
    editorStatus = 'saved';

    try {
      final html = await ApiService.getDocHtml(taskId, 'synopsis');
      editorContent = html;
    } catch (e) {
      _buildSynopsisFromResult();
    }

    // История
    history.insert(0, HistoryItem(
      id: taskId,
      inn: form.innRu,
      form: form.dosageForm,
      dose: form.dosage,
      date: _formatDate(DateTime.now()),
      synopsisHtml: editorContent,
    ));

    addChatMessage('✅ Синопсис «${form.innRu}» готов! Скачайте .docx или отредактируйте в редакторе.', ChatRole.system);
    notifyListeners();
  }

  // ══════════════════════════
  // EDITOR
  // ══════════════════════════

  void openDocument(String which) async {
    currentDoc = which;
    if (which == 'synopsis') {
      editorFileName = 'Синопсис_${form.innRu}.docx';
    } else {
      editorFileName = 'Обоснование_${form.innRu}.docx';
    }
    editorStatus = 'saved';

    // Загружаем HTML с сервера
    if (currentTaskId != null) {
      try {
        final html = await ApiService.getDocHtml(currentTaskId!, which);
        editorContent = html;
      } catch (_) {}
    }

    notifyListeners();
  }

  void saveEditor() {
    editorStatus = 'saved';
    // Сохраняем на сервер
    if (currentTaskId != null && currentDoc != null) {
      ApiService.saveDocHtml(currentTaskId!, currentDoc!, editorContent).then((ok) {
        if (ok) {
          addChatMessage('💾 Документ сохранён', ChatRole.system);
        }
      });
    }
    notifyListeners();
  }

  void updateEditorContent(String html) {
    editorContent = html;
    editorStatus = 'edited';
    notifyListeners();
  }

  /// URL для скачивания .docx
  String? get synopsisDownloadUrl =>
      currentTaskId != null ? ApiService.downloadUrl(currentTaskId!, 'synopsis') : null;

  String? get rationaleDownloadUrl =>
      currentTaskId != null ? ApiService.downloadUrl(currentTaskId!, 'rationale') : null;

  void resetAll() {
    isGenerating = false;
    generationComplete = false;
    progress = 0;
    editorContent = '';
    editorFileName = 'Редактор документов';
    editorStatus = 'idle';
    currentDoc = null;
    currentTaskId = null;
    lastResult = null;
    for (final step in pipelineSteps) {
      step.status = StepStatus.pending;
    }
    notifyListeners();
  }

  // ══════════════════════════
  // HISTORY
  // ══════════════════════════

  void removeHistory(int index) {
    if (index >= 0 && index < history.length) {
      history.removeAt(index);
      notifyListeners();
    }
  }

  // ══════════════════════════
  // CHAT — REAL API
  // ══════════════════════════

  void toggleChat() {
    chatExpanded = !chatExpanded;
    notifyListeners();
  }

  void addChatMessage(String text, ChatRole role) {
    chatMessages.add(ChatMessage(text: text, role: role));
    notifyListeners();
  }

  Future<void> sendChatMessage(String text) async {
    addChatMessage(text, ChatRole.user);
    try {
      final reply = await ApiService.sendChat(text, taskId: currentTaskId);
      addChatMessage(reply, ChatRole.bot);
    } catch (e) {
      addChatMessage('Ошибка: $e', ChatRole.system);
    }
  }

  // ══════════════════════════
  // BUILDERS
  // ══════════════════════════

  String _formatDate(DateTime d) =>
      '${d.day.toString().padLeft(2, '0')}.${d.month.toString().padLeft(2, '0')}.${d.year}';

  void _buildSynopsisFromResult() {
    if (lastResult == null) {
      editorContent = 'Результат пуст';
      return;
    }

    final r = lastResult!;
    final pk = r['pk'] as Map<String, dynamic>? ?? {};
    final design = r['design'] as Map<String, dynamic>? ?? {};
    final sample = r['sample_size'] as Map<String, dynamic>? ?? {};
    final synopsis = r['synopsis'] as Map<String, dynamic>? ?? {};
    final regulatory = r['regulatory'] as Map<String, dynamic>? ?? {};

    final buf = StringBuffer();
    buf.writeln('═══ СИНОПСИС ПРОТОКОЛА ═══');
    buf.writeln('МНН: ${form.innRu}');
    buf.writeln('Форма: ${form.dosageForm}, ${form.dosage}');
    buf.writeln('Референт: ${form.referenceDrug}');
    buf.writeln('');

    // PK
    buf.writeln('── Фармакокинетика ──');
    if (pk['cv_intra_max'] != null) buf.writeln('CVintra: ${pk['cv_intra_max']}%');
    if (pk['t_half_hours'] != null) buf.writeln('T½: ${pk['t_half_hours']} ч');
    if (pk['is_hvd'] != null) buf.writeln('HVD: ${pk['is_hvd'] == true ? "Да" : "Нет"}');
    buf.writeln('');

    // Design
    buf.writeln('── Дизайн исследования ──');
    if (design['design_type'] != null) buf.writeln('Тип: ${design['design_type']}');
    if (design['n_periods'] != null) buf.writeln('Периодов: ${design['n_periods']}');
    if (design['n_sequences'] != null) buf.writeln('Последовательностей: ${design['n_sequences']}');
    if (design['washout_days'] != null) buf.writeln('Отмывочный: ${design['washout_days']} дней');
    if (design['dropout_rate'] != null) buf.writeln('Dropout: ${((design['dropout_rate'] as num) * 100).toStringAsFixed(0)}%');
    if (design['be_lower'] != null && design['be_upper'] != null) {
      buf.writeln('Границы БЭ: ${design['be_lower']}–${design['be_upper']}%');
    }
    buf.writeln('');

    // Sample size
    buf.writeln('── Размер выборки ──');
    if (sample['n_base'] != null) buf.writeln('Базовый: ${sample['n_base']}');
    if (sample['n_with_dropout'] != null) buf.writeln('С dropout: ${sample['n_with_dropout']}');
    if (sample['n_total'] != null) buf.writeln('Итого: ${sample['n_total']}');
    if (sample['blood_volume_ml'] != null) buf.writeln('Кровь: ${sample['blood_volume_ml']} мл');
    buf.writeln('');

    // Regulatory
    final regSummary = regulatory['summary'] as Map<String, dynamic>? ?? {};
    if (regSummary.isNotEmpty) {
      buf.writeln('── Регуляторная проверка ──');
      buf.writeln('PASS: ${regSummary['pass'] ?? 0}, FAIL: ${regSummary['fail'] ?? 0}, WARN: ${regSummary['warning'] ?? 0}');
      buf.writeln('');
    }

    // Synopsis fields
    if (synopsis.isNotEmpty) {
      buf.writeln('── Поля синопсиса ──');
      synopsis.forEach((k, v) {
        if (v != null && v.toString().isNotEmpty) {
          buf.writeln('$k: $v');
        }
      });
    }

    editorContent = buf.toString();
  }
}