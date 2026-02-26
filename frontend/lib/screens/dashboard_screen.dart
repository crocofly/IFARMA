import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../theme/app_theme.dart';
import '../services/app_state.dart';
import '../services/web_iframe.dart';
import '../services/api_service.dart';
import '../models/models.dart';
import '../widgets/autocomplete_field.dart';
import '../widgets/tags_input.dart';
import '../widgets/collapsible_section.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          _buildNavBar(context),
          Expanded(
            child: Row(
              children: [
                SizedBox(width: 340, child: _LeftPanel()),
                VerticalDivider(width: 1, color: AppColors.border),
                Expanded(child: _CenterPanel()),
                VerticalDivider(width: 1, color: AppColors.border),
                SizedBox(width: 260, child: _RightPanel()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavBar(BuildContext context) {
    return Container(
      height: 52,
      decoration: BoxDecoration(color: AppColors.surface, border: Border(bottom: BorderSide(color: AppColors.border))),
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(children: [
        Container(width: 30, height: 30, decoration: BoxDecoration(gradient: AppColors.gradientPrimary, borderRadius: BorderRadius.circular(8)), child: const Icon(Icons.article_outlined, size: 16, color: Colors.white)),
        const SizedBox(width: 9),
        Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('iFarma', style: AppTheme.serif.copyWith(fontSize: 17)),
          Text('ГЕНЕРАТОР СИНОПСИСА', style: TextStyle(fontSize: 9, color: AppColors.muted, letterSpacing: 1.5)),
        ]),
        const Spacer(),
        Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3), decoration: BoxDecoration(color: AppColors.greenLight, borderRadius: BorderRadius.circular(99), border: Border.all(color: AppColors.green.withOpacity(0.18))),
          child: Row(mainAxisSize: MainAxisSize.min, children: [Container(width: 5, height: 5, decoration: BoxDecoration(color: AppColors.green, shape: BoxShape.circle)), const SizedBox(width: 5), Text('Агенты активны', style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w500, color: AppColors.green))])),
        const SizedBox(width: 8),
        Container(padding: const EdgeInsets.only(left: 4, right: 11, top: 3, bottom: 3), decoration: BoxDecoration(borderRadius: BorderRadius.circular(99), border: Border.all(color: AppColors.border, width: 1.5)),
          child: Row(children: [Container(width: 24, height: 24, decoration: BoxDecoration(gradient: AppColors.gradientPrimary, shape: BoxShape.circle), alignment: Alignment.center, child: const Text('П', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: Colors.white))), const SizedBox(width: 7), const Text('Пользователь', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500))])),
      ]),
    );
  }
}

String _companySubtitle(Map<String, dynamic> c) {
  final parts = <String>[];
  final inn = c['inn'];
  final address = c['address'];
  if (inn != null && inn.toString().isNotEmpty) parts.add('ИНН $inn');
  if (address != null && address.toString().isNotEmpty) parts.add(address.toString());
  return parts.join(' · ');
}

String _drugSubtitle(Map<String, dynamic> r) {
  final parts = <String>[];
  final inn = r['inn'];
  final mfg = r['mfg'];
  if (inn != null && inn.toString().isNotEmpty) parts.add(inn.toString());
  if (mfg != null && mfg.toString().isNotEmpty) parts.add(mfg.toString());
  return parts.join(' · ');
}

class _LeftPanel extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final form = state.form;
    return Container(color: AppColors.surface, child: Column(children: [
      Expanded(child: ListView(padding: EdgeInsets.zero, children: [
        _buildBlock1(context, state, form),
        _buildBlock2RefDrug(context, state, form),
        _buildBlock3Org(context, state, form),
        _buildBlock4Params(context, state, form),
      ])),
      Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: AppColors.surface, border: Border(top: BorderSide(color: AppColors.border))),
        child: SizedBox(width: double.infinity, child: ElevatedButton(
          onPressed: state.isGenerating ? null : () { final e = state.validateForm(); if (e != null) { ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e))); return; } state.startGeneration(); },
          style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 12), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)), backgroundColor: AppColors.orange, disabledBackgroundColor: AppColors.orange.withOpacity(0.4)),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [const Icon(Icons.play_arrow, size: 16, color: Colors.white), const SizedBox(width: 7), Text('Сгенерировать синопсис', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Colors.white))]),
        ))),
    ]));
  }

  Widget _buildBlock1(BuildContext ctx, AppState state, FormData form) {
    return CollapsibleSection(number: 1, title: 'Основные данные препарата', tag: 'Обязательно', badgeColor: AppColors.orange, tagColor: AppColors.orange, tagBgColor: AppColors.orangeLight, initiallyExpanded: true, children: [
      AutocompleteField(label: 'МНН', placeholder: 'Амлодипин, Metformin…', hint: 'Можно вводить на русском или английском', required: true, showIcon: true, value: form.innRu, items: const [], onChanged: (v) => state.updateForm((f) => f.innRu = v), asyncSearch: (q) async { final results = await ApiService.searchInn(q); return results.map((d) => AutocompleteItem(title: d['ru'] ?? '', subtitle: d['en'] ?? '')).toList(); }),
      AutocompleteField(label: 'Лекарственная форма', placeholder: 'Начните вводить: таблетки, капсулы…', required: true, value: form.dosageForm, items: const [], onChanged: (v) => state.updateForm((f) => f.dosageForm = v), asyncSearch: (q) async { final results = await ApiService.searchForms(q); return results.map((f) => AutocompleteItem(title: f)).toList(); }),
      AutocompleteField(label: 'Дозировка', placeholder: '10 мг, 500 мг…', hint: 'Укажите дозировку вручную', required: true, value: form.dosage, items: const [], onChanged: (v) => state.updateForm((f) => f.dosage = v)),
      AutocompleteField(label: 'Название исследуемого препарата', placeholder: 'Торговое название (если есть)', hint: 'Если пусто — останется пустым в синопсисе', value: form.drugName, items: const [], onChanged: (v) => state.updateForm((f) => f.drugName = v)),
      AutocompleteField(label: 'Условия хранения ИП', placeholder: 'Хранить при температуре не выше 25°C…', hint: 'Условия хранения дженерика', required: true, value: form.storageConditions, items: const [], onChanged: (v) => state.updateForm((f) => f.storageConditions = v)),
    ]);
  }

  Widget _buildBlock3Org(BuildContext ctx, AppState state, FormData form) {
    return CollapsibleSection(number: 3, title: 'Организация и спонсор', tag: 'Данные', badgeColor: AppColors.blue, tagColor: AppColors.blue, tagBgColor: AppColors.blueLight, children: [
      AutocompleteField(label: 'Производитель', placeholder: 'Начните вводить название…', value: form.manufacturer, items: const [], onChanged: (v) => state.updateForm((f) => f.manufacturer = v), asyncSearch: (q) async { final results = await ApiService.searchManufacturers(q); return results.map((m) => AutocompleteItem(title: m)).toList(); }),
      _CheckboxTile(label: 'Производитель является спонсором исследования', value: form.mfgIsSponsor, onChanged: (v) => state.updateForm((f) => f.mfgIsSponsor = v)),
      if (!form.mfgIsSponsor) AutocompleteField(label: 'Спонсор исследования', placeholder: 'Название или ИНН организации-спонсора', value: form.sponsor, items: const [], onChanged: (v) => state.updateForm((f) => f.sponsor = v), asyncSearch: (q) async { final results = await ApiService.searchCompany(q, kind: 'general'); return results.map((c) => AutocompleteItem(title: c['name'] ?? '', subtitle: _companySubtitle(c))).toList(); }),
      Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Divider(color: AppColors.border, height: 1)),
      _ProtocolIdField(form: form, state: state),
      AutocompleteField(label: 'Исследовательский центр', placeholder: 'Название или ИНН организации', hint: 'Можно ввести ИНН — подскажет название', value: form.researchCenter, items: const [], onChanged: (v) => state.updateForm((f) => f.researchCenter = v), asyncSearch: (q) async { final results = await ApiService.searchCompany(q, kind: 'research_center'); return results.map((c) => AutocompleteItem(title: c['name'] ?? '', subtitle: _companySubtitle(c))).toList(); }),
      AutocompleteField(label: 'Биоаналитическая лаборатория', placeholder: 'Название или ИНН лаборатории', hint: 'Можно ввести ИНН — подскажет название', value: form.bioanalyticalLab, items: const [], onChanged: (v) => state.updateForm((f) => f.bioanalyticalLab = v), asyncSearch: (q) async { final results = await ApiService.searchCompany(q, kind: 'biolab'); return results.map((c) => AutocompleteItem(title: c['name'] ?? '', subtitle: _companySubtitle(c))).toList(); }),
      AutocompleteField(label: 'Страховая компания', placeholder: 'Название или ИНН страховой', hint: 'Можно ввести ИНН — подскажет название', value: form.insuranceCompany, items: const [], onChanged: (v) => state.updateForm((f) => f.insuranceCompany = v), asyncSearch: (q) async { final results = await ApiService.searchCompany(q, kind: 'insurance'); return results.map((c) => AutocompleteItem(title: c['name'] ?? '', subtitle: _companySubtitle(c))).toList(); }),
    ]);
  }

  Widget _buildBlock2RefDrug(BuildContext ctx, AppState state, FormData form) {
    return CollapsibleSection(number: 2, title: 'Референтный препарат и состав', tag: 'Данные', badgeColor: AppColors.blue, tagColor: AppColors.blue, tagBgColor: AppColors.blueLight, children: [
      _ReferenceDrugField(form: form, state: state),
      TagsInput(label: 'Вспомогательные вещества', placeholder: 'Добавить вещество…', hint: 'Enter — добавить, выберите из списка', tags: form.excipients, suggestions: const [], onChanged: (v) => state.updateForm((f) => f.excipients = v), asyncSearch: (q) async { return await ApiService.searchExcipients(q); }),
    ]);
  }

  Widget _buildBlock4Params(BuildContext ctx, AppState state, FormData form) {
    return CollapsibleSection(number: 4, title: 'Параметры дизайна и ФК', tag: 'Опционально', badgeColor: AppColors.dim, tagColor: AppColors.dim, tagBgColor: AppColors.bg, children: [
      Text('ФК параметры', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.dim)),
      const SizedBox(height: 2),
      Text('Если не заполнять — AI найдёт из литературы', style: TextStyle(fontSize: 10, color: AppColors.dim)),
      AutocompleteField(label: 'CVintra (%)', placeholder: 'Внутрииндивидуальная вариабельность', value: form.cvIntra?.toString() ?? '', items: const [], onChanged: (v) => state.updateForm((f) => f.cvIntra = double.tryParse(v))),
      AutocompleteField(label: 'T½ (часы)', placeholder: 'Период полувыведения', value: form.tHalfHours?.toString() ?? '', items: const [], onChanged: (v) => state.updateForm((f) => f.tHalfHours = double.tryParse(v))),
      Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Divider(color: AppColors.border, height: 1)),
      Text('Параметры дизайна', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.dim)),
      const SizedBox(height: 2),
      Text('Если не выбрать — AI определит автоматически', style: TextStyle(fontSize: 10, color: AppColors.dim)),
      _OptionSelector(label: 'Пол добровольцев', options: const [_Option(value: 'males_only', icon: '♂', title: 'Только мужчины', subtitle: 'Стандарт для БЭ'), _Option(value: 'females_only', icon: '♀', title: 'Только женщины', subtitle: 'Требует обоснования'), _Option(value: 'males_and_females', icon: '♂♀', title: 'Мужчины и женщины', subtitle: 'Требует обоснования')], selected: form.sexRestriction, onChanged: (v) => state.updateForm((f) => f.sexRestriction = v)),
      _AgeRange(form: form, state: state),
      _OptionSelector(label: 'Ограничения по курению', options: const [_Option(value: 'non_smokers', icon: '🚭', title: 'Некурящие'), _Option(value: 'cotinine', icon: '🧬', title: '+ Котинин'), _Option(value: 'no_restriction', icon: '✅', title: 'Без ограничений')], selected: form.smokingRestriction, onChanged: (v) => state.updateForm((f) => f.smokingRestriction = v)),
      Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Divider(color: AppColors.border, height: 1)),
      Text('Расчётные константы', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.dim)),
      const SizedBox(height: 2),
      Text('Значения по умолчанию используются если не задано', style: TextStyle(fontSize: 10, color: AppColors.dim)),
      const SizedBox(height: 4),
      _ConstantField(label: 'Мощность (power)', placeholder: '0.80', value: form.overridePower, onChanged: (v) => state.updateForm((f) => f.overridePower = v)),
      _ConstantField(label: 'Уровень значимости (α)', placeholder: '0.05', value: form.overrideAlpha, onChanged: (v) => state.updateForm((f) => f.overrideAlpha = v)),
      _ConstantField(label: 'GMR (T/R отношение)', placeholder: '0.95', value: form.overrideGmr, onChanged: (v) => state.updateForm((f) => f.overrideGmr = v)),
      _ConstantField(label: 'Dropout rate', placeholder: 'Авто (10-30%)', value: form.overrideDropoutRate, onChanged: (v) => state.updateForm((f) => f.overrideDropoutRate = v)),
      _ConstantField(label: 'Screen failure rate', placeholder: '0.15', value: form.overrideScreenfailRate, onChanged: (v) => state.updateForm((f) => f.overrideScreenfailRate = v)),
      _ConstantIntField(label: 'Мин. число добровольцев', placeholder: '12', value: form.overrideMinSubjects, onChanged: (v) => state.updateForm((f) => f.overrideMinSubjects = v)),
      _ConstantField(label: 'Объём крови на пробу (мл)', placeholder: '5.0', value: form.overrideBloodPerPoint, onChanged: (v) => state.updateForm((f) => f.overrideBloodPerPoint = v)),
      _ConstantField(label: 'Макс. объём крови (мл)', placeholder: '450', value: form.overrideMaxBlood, onChanged: (v) => state.updateForm((f) => f.overrideMaxBlood = v)),
    ]);
  }
}

/// Поле «Референтный препарат» с авто-подгрузкой чипов по МНН
class _ReferenceDrugField extends StatefulWidget {
  final FormData form;
  final AppState state;
  const _ReferenceDrugField({required this.form, required this.state});
  @override
  State<_ReferenceDrugField> createState() => _ReferenceDrugFieldState();
}

class _ReferenceDrugFieldState extends State<_ReferenceDrugField> {
  List<String> _suggestions = [];
  bool _loading = false;
  String _lastInn = '';
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(_ReferenceDrugField old) {
    super.didUpdateWidget(old);
    final inn = widget.form.innRu.trim();
    // Минимум 4 символа и МНН изменился
    if (inn != _lastInn && inn.length >= 4) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(milliseconds: 800), () {
        _lastInn = inn;
        _loadSuggestions();
      });
    }
  }

  @override
  void initState() {
    super.initState();
    final inn = widget.form.innRu.trim();
    if (inn.length >= 4) {
      _lastInn = inn;
      _loadSuggestions();
    }
  }

  Future<void> _loadSuggestions() async {
    setState(() => _loading = true);
    try {
      final results = await ApiService.searchReference(_lastInn, '');
      if (mounted) {
        setState(() {
          _suggestions = results.map((r) => (r['name'] ?? '') as String).where((s) => s.isNotEmpty).toList();
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Текстовое поле
        AutocompleteField(
          label: 'Референтный препарат',
          placeholder: 'Введите название или выберите ниже',
          hint: widget.form.innRu.isEmpty ? 'Сначала введите МНН' : null,
          value: widget.form.referenceDrug,
          items: const [],
          onChanged: (v) => widget.state.updateForm((f) => f.referenceDrug = v),
        ),
        // Чипы-подсказки
        if (_loading)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Row(children: [
              SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5, color: AppColors.blue)),
              const SizedBox(width: 6),
              Text('Ищем препараты по МНН…', style: TextStyle(fontSize: 10, color: AppColors.dim)),
            ]),
          ),
        if (!_loading && _suggestions.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Возможные оригинальные препараты:', style: TextStyle(fontSize: 10, color: AppColors.dim)),
                const SizedBox(height: 4),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: _suggestions.map((name) {
                    final isSelected = widget.form.referenceDrug == name;
                    return InkWell(
                      onTap: () => widget.state.updateForm((f) => f.referenceDrug = name),
                      borderRadius: BorderRadius.circular(99),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: isSelected ? AppColors.blue : AppColors.blueLight,
                          borderRadius: BorderRadius.circular(99),
                          border: Border.all(color: isSelected ? AppColors.blue : AppColors.blue.withOpacity(0.2)),
                        ),
                        child: Text(
                          name,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: isSelected ? Colors.white : AppColors.blue,
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
        if (!_loading && _suggestions.isEmpty && widget.form.innRu.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('Введите название вручную', style: TextStyle(fontSize: 10, color: AppColors.dim)),
          ),
      ],
    );
  }
}

class _CheckboxTile extends StatelessWidget {
  final String label; final bool value; final ValueChanged<bool> onChanged;
  const _CheckboxTile({required this.label, required this.value, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    return InkWell(onTap: () => onChanged(!value), child: Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Row(children: [
      Container(width: 16, height: 16, decoration: BoxDecoration(color: value ? AppColors.blue : AppColors.bg, borderRadius: BorderRadius.circular(4), border: Border.all(color: value ? AppColors.blue : AppColors.border2, width: 1.5)), child: value ? const Icon(Icons.check, size: 11, color: Colors.white) : null),
      const SizedBox(width: 7), Expanded(child: Text(label, style: TextStyle(fontSize: 11.5, color: AppColors.text2))),
    ])));
  }
}

class _Option { final String value; final String icon; final String title; final String? subtitle; const _Option({required this.value, required this.icon, required this.title, this.subtitle}); }

class _OptionSelector extends StatelessWidget {
  final String label; final List<_Option> options; final String selected; final ValueChanged<String> onChanged;
  const _OptionSelector({required this.label, required this.options, required this.selected, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2)),
      const SizedBox(height: 5),
      Wrap(spacing: 5, runSpacing: 5, children: options.map((opt) {
        final isOn = selected == opt.value;
        return InkWell(onTap: () => onChanged(isOn ? '' : opt.value), borderRadius: BorderRadius.circular(7), child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(color: isOn ? AppColors.blueLight : AppColors.bg, borderRadius: BorderRadius.circular(7), border: Border.all(color: isOn ? AppColors.blue : AppColors.border, width: 1.5)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Text(opt.icon, style: const TextStyle(fontSize: 13)), const SizedBox(width: 6),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(opt.title, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text)),
              if (opt.subtitle != null) Text(opt.subtitle!, style: TextStyle(fontSize: 9, color: AppColors.muted)),
            ]),
          ]),
        ));
      }).toList()),
    ]);
  }
}

class _AgeRange extends StatelessWidget {
  final FormData form; final AppState state;
  const _AgeRange({required this.form, required this.state});
  InputDecoration _d(String h) => InputDecoration(hintText: h, hintStyle: TextStyle(color: AppColors.dim, fontSize: 13), contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9), filled: true, fillColor: AppColors.bg, isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.blue, width: 1.5)));
  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Возраст добровольцев', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2)), const SizedBox(height: 4),
      Row(children: [Expanded(child: TextField(controller: TextEditingController(text: '${form.ageMin}'), style: const TextStyle(fontSize: 13), keyboardType: TextInputType.number, decoration: _d('от 18'), onChanged: (v) => state.updateForm((f) => f.ageMin = int.tryParse(v) ?? 18))),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 6), child: Text('—', style: TextStyle(color: AppColors.dim))),
        Expanded(child: TextField(controller: TextEditingController(text: '${form.ageMax}'), style: const TextStyle(fontSize: 13), keyboardType: TextInputType.number, decoration: _d('до 45'), onChanged: (v) => state.updateForm((f) => f.ageMax = int.tryParse(v) ?? 45)))]),
    ]);
  }
}

class _ConstantField extends StatelessWidget {
  final String label;
  final String placeholder;
  final double? value;
  final ValueChanged<double?> onChanged;
  const _ConstantField({required this.label, required this.placeholder, required this.value, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    return Padding(padding: const EdgeInsets.only(bottom: 4), child: Row(children: [
      Expanded(flex: 3, child: Text(label, style: TextStyle(fontSize: 11, color: AppColors.text2))),
      const SizedBox(width: 8),
      SizedBox(width: 80, child: TextField(
        controller: TextEditingController(text: value != null ? value.toString() : ''),
        style: const TextStyle(fontSize: 12),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        textAlign: TextAlign.center,
        decoration: InputDecoration(
          hintText: placeholder, hintStyle: TextStyle(color: AppColors.dim, fontSize: 11),
          contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
          filled: true, fillColor: AppColors.bg, isDense: true,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.border)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.border)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.blue)),
        ),
        onChanged: (v) => onChanged(v.isEmpty ? null : double.tryParse(v)),
      )),
    ]));
  }
}

class _ConstantIntField extends StatelessWidget {
  final String label;
  final String placeholder;
  final int? value;
  final ValueChanged<int?> onChanged;
  const _ConstantIntField({required this.label, required this.placeholder, required this.value, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    return Padding(padding: const EdgeInsets.only(bottom: 4), child: Row(children: [
      Expanded(flex: 3, child: Text(label, style: TextStyle(fontSize: 11, color: AppColors.text2))),
      const SizedBox(width: 8),
      SizedBox(width: 80, child: TextField(
        controller: TextEditingController(text: value != null ? value.toString() : ''),
        style: const TextStyle(fontSize: 12),
        keyboardType: TextInputType.number,
        textAlign: TextAlign.center,
        decoration: InputDecoration(
          hintText: placeholder, hintStyle: TextStyle(color: AppColors.dim, fontSize: 11),
          contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
          filled: true, fillColor: AppColors.bg, isDense: true,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.border)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.border)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: AppColors.blue)),
        ),
        onChanged: (v) => onChanged(v.isEmpty ? null : int.tryParse(v)),
      )),
    ]));
  }
}

class _ProtocolIdField extends StatelessWidget {
  final FormData form; final AppState state;
  const _ProtocolIdField({required this.form, required this.state});
  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Идентификационный номер протокола', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2)), const SizedBox(height: 4),
      Wrap(spacing: 5, runSpacing: 5, children: ['manual', 'auto', 'empty'].map((mode) {
        final labels = {'manual': 'Вручную', 'auto': 'Сгенерировать', 'empty': 'Пустой'};
        final isOn = form.protocolMode == mode;
        return InkWell(onTap: () { state.updateForm((f) { f.protocolMode = mode; if (mode == 'auto') { f.protocolId = 'BE-${f.innRu.length >= 3 ? f.innRu.substring(0, 3).toUpperCase() : "XXX"}-2026-${(100 + DateTime.now().millisecond % 900)}'; } else if (mode == 'empty') { f.protocolId = ''; } }); },
          child: Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5), decoration: BoxDecoration(color: isOn ? AppColors.blueLight : AppColors.bg, borderRadius: BorderRadius.circular(6), border: Border.all(color: isOn ? AppColors.blue : AppColors.border, width: 1.5)),
            child: Text(labels[mode]!, style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w500, color: isOn ? AppColors.blue : AppColors.muted))));
      }).toList()),
      if (form.protocolMode == 'manual') ...[const SizedBox(height: 6), TextField(style: const TextStyle(fontSize: 13), decoration: InputDecoration(hintText: 'BE-AML-2026-001', hintStyle: TextStyle(color: AppColors.dim, fontSize: 13), contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9), filled: true, fillColor: AppColors.bg, isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.blue, width: 1.5))), onChanged: (v) => state.updateForm((f) => f.protocolId = v))],
      if (form.protocolMode == 'auto' && form.protocolId.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: Text('Сгенерирован: ${form.protocolId}', style: TextStyle(fontSize: 10, color: AppColors.dim))),
      if (form.protocolMode == 'empty') Padding(padding: const EdgeInsets.only(top: 4), child: Text('Поле останется пустым', style: TextStyle(fontSize: 10, color: AppColors.dim))),
    ]);
  }
}

class _CenterPanel extends StatefulWidget {
  @override
  State<_CenterPanel> createState() => _CenterPanelState();
}

class _CenterPanelState extends State<_CenterPanel> {
  int _iframeKey = 0;
  String? _lastHtml;

  void _download(AppState state, String docType) async {
    // Извлекаем актуальный HTML из iframe
    final html = getIframeBodyHtml();
    if (html != null && html.isNotEmpty) {
      // Сохраняем напрямую на сервер, БЕЗ updateEditorContent (чтобы не пересоздать iframe)
      final taskId = state.currentTaskId;
      final doc = state.currentDoc ?? docType;
      if (taskId != null) {
        final ok = await ApiService.saveDocHtml(taskId, doc, html);
        if (!ok) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('❌ Ошибка сохранения'), duration: Duration(seconds: 2)));
          return;
        }
      }
    }
    final url = docType == 'synopsis' ? state.synopsisDownloadUrl : state.rationaleDownloadUrl;
    if (url != null) {
      final name = docType == 'synopsis'
          ? 'Синопсис_${state.form.innRu}.docx'
          : 'Обоснование_${state.form.innRu}.docx';
      downloadFile(url, name);
    }
  }

  void _save(AppState state) async {
    final html = getIframeBodyHtml();
    if (html == null || html.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ Не удалось извлечь документ'), duration: Duration(seconds: 2)));
      return;
    }
    // Сохраняем напрямую на сервер, минуя updateEditorContent → notifyListeners → iframe rebuild
    final taskId = state.currentTaskId;
    final doc = state.currentDoc;
    if (taskId != null && doc != null) {
      final ok = await ApiService.saveDocHtml(taskId, doc, html);
      if (ok) {
        // Обновляем только статус, не контент (чтобы iframe не пересоздался)
        state.editorStatus = 'saved';
        // Синхронизируем editorContent без триггера rebuild
        _lastHtml = html;
        state.editorContent = html;
        state.notifyListeners();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('💾 Сохранено'), duration: Duration(seconds: 2)));
        state.addChatMessage('💾 Документ сохранён', ChatRole.system);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('❌ Ошибка сохранения'), duration: Duration(seconds: 2)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final hasDoc = state.editorContent.isNotEmpty;

    // Rebuild iframe only when content changes from server
    if (hasDoc && state.editorContent != _lastHtml) {
      _lastHtml = state.editorContent;
      _iframeKey++;
    }

    return Container(color: AppColors.surface, child: Column(children: [
      // ── Top bar ──
      Container(height: 46, padding: const EdgeInsets.symmetric(horizontal: 14), decoration: BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.border))),
        child: Row(children: [
          Icon(Icons.description_outlined, size: 15, color: AppColors.muted), const SizedBox(width: 6),
          Expanded(child: Text(state.editorFileName, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis)),
          _StatusPill(status: state.editorStatus),
          if (hasDoc) ...[
            const SizedBox(width: 6),
            _SmBtn(icon: Icons.download, label: 'Скачать .docx', onTap: () => _download(state, state.currentDoc ?? 'synopsis')),
            const SizedBox(width: 4),
            _SmBtn(icon: Icons.save, label: 'Сохранить', primary: true, onTap: () => _save(state)),
          ],
        ])),
      // ── Formatting toolbar ──
      if (hasDoc) _FormattingToolbar(),
      // ── Body: always editable iframe ──
      Expanded(child: hasDoc
        ? _DocIframeView(html: state.editorContent, key: ValueKey('iframe_$_iframeKey'))
        : state.isGenerating
          ? _GenerationProgress(state: state)
          : Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text('🧬', style: const TextStyle(fontSize: 36)), const SizedBox(height: 12),
              Text('Редактор документов', style: AppTheme.serif.copyWith(fontSize: 18)), const SizedBox(height: 6),
              Text('Заполните поля и нажмите «Сгенерировать»', style: TextStyle(fontSize: 12, color: AppColors.muted)),
            ]))),
      // ── Footer ──
      if (hasDoc) Container(height: 24, padding: const EdgeInsets.symmetric(horizontal: 14), decoration: BoxDecoration(color: AppColors.bg, border: Border(top: BorderSide(color: AppColors.border))),
        child: Row(children: [
          Text('.docx → HTML', style: TextStyle(fontSize: 10, color: AppColors.dim)),
          const Spacer(),
          Text('Кликните на текст чтобы редактировать', style: TextStyle(fontSize: 10, color: AppColors.dim)),
        ])),
    ]));
  }
}

/// Animated generation progress — self-timed 2-minute animation
class _GenerationProgress extends StatefulWidget {
  final AppState state;
  const _GenerationProgress({required this.state});
  @override
  State<_GenerationProgress> createState() => _GenerationProgressState();
}

class _GenerationProgressState extends State<_GenerationProgress> with TickerProviderStateMixin {
  late AnimationController _progressCtrl;
  late AnimationController _pulseCtrl;
  late AnimationController _rotateCtrl;
  late Animation<double> _pulseAnim;
  bool _waitingForServer = false;

  // Шаги и их тайминг (когда начинают running, % от общего времени)
  // 0-17% PK Литература, 17-38% Регуляторный, 38-58% Дизайн, 58-78% Расчёт, 78-100% Генерация
  static const _stepTimings = [0.0, 0.17, 0.38, 0.58, 0.78];

  @override
  void initState() {
    super.initState();
    // Анимация идёт 110 сек, но upperBound = 0.92 — дальше ждём сервер
    _progressCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 110), upperBound: 0.92)
      ..addListener(_updateSteps)
      ..addStatusListener((status) {
        if (status == AnimationStatus.completed && widget.state.isGenerating) {
          setState(() => _waitingForServer = true);
        }
      })
      ..forward();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))..repeat(reverse: true);
    _rotateCtrl = AnimationController(vsync: this, duration: const Duration(seconds: 8))..repeat();
    _pulseAnim = Tween<double>(begin: 0.88, end: 1.12).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
  }

  void _updateSteps() {
    if (!mounted) return;
    // Нормализуем t к 0..1 для тайминга шагов (0.92 → ~1.0)
    final t = (_progressCtrl.value / 0.92).clamp(0.0, 1.0);
    final steps = widget.state.pipelineSteps;
    for (int i = 0; i < steps.length; i++) {
      final start = _stepTimings[i];
      final end = i + 1 < _stepTimings.length ? _stepTimings[i + 1] : 1.0;
      if (t >= end) {
        steps[i].status = StepStatus.done;
      } else if (t >= start) {
        steps[i].status = StepStatus.running;
      } else {
        steps[i].status = StepStatus.pending;
      }
    }
    setState(() {});
  }

  @override
  void didUpdateWidget(_GenerationProgress old) {
    super.didUpdateWidget(old);
    if (!widget.state.isGenerating && _progressCtrl.isAnimating) {
      _progressCtrl.stop();
    }
  }

  @override
  void dispose() {
    _progressCtrl.dispose();
    _pulseCtrl.dispose();
    _rotateCtrl.dispose();
    super.dispose();
  }

  double get _displayProgress => _waitingForServer
      ? 0.92 + (_pulseAnim.value - 0.88) / (1.12 - 0.88) * 0.06 // пульсирует 92-98%
      : _progressCtrl.value;

  String _etaText(double t) {
    if (_waitingForServer) return 'ещё чуть-чуть…';
    final secsLeft = ((0.92 - t) / 0.92 * 110).round();
    if (secsLeft > 90) return '~1.5–2 минуты';
    if (secsLeft > 60) return '~1.5 минуты';
    if (secsLeft > 30) return '~1 минута';
    if (secsLeft > 10) return '~30 секунд';
    return 'почти готово';
  }

  String _funFact(double t) {
    if (_waitingForServer) return 'Финализируем документ…';
    final tn = (t / 0.92).clamp(0.0, 1.0);
    if (tn < 0.17) return 'Анализируем фармакокинетику из научных публикаций…';
    if (tn < 0.38) return 'Проверяем требования Решения ЕАЭС №85…';
    if (tn < 0.58) return 'Подбираем оптимальный дизайн исследования…';
    if (tn < 0.78) return 'Рассчитываем размер выборки…';
    return 'Собираем синопсис в единый документ…';
  }

  @override
  Widget build(BuildContext context) {
    final steps = widget.state.pipelineSteps;
    final t = _displayProgress;

    return Center(child: SingleChildScrollView(child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        // ── Animated molecule ──
        AnimatedBuilder(
          animation: _pulseCtrl,
          builder: (_, __) => AnimatedBuilder(
            animation: _rotateCtrl,
            builder: (_, __) => Transform.rotate(
              angle: _rotateCtrl.value * 6.28,
              child: Transform.scale(
                scale: _pulseAnim.value,
                child: Container(
                  width: 72, height: 72,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(colors: [
                      AppColors.blue.withOpacity(0.15),
                      AppColors.blue.withOpacity(0.05),
                      Colors.transparent,
                    ]),
                  ),
                  child: const Center(child: Text('🧬', style: TextStyle(fontSize: 36))),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),

        // ── Title ──
        Text('Генерация синопсиса', style: AppTheme.serif.copyWith(fontSize: 20)),
        const SizedBox(height: 4),
        Text(_etaText(t), style: TextStyle(fontSize: 12, color: AppColors.muted)),
        const SizedBox(height: 20),

        // ── Progress bar ──
        SizedBox(width: 320, child: Column(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(height: 8, child: Stack(children: [
              Container(decoration: BoxDecoration(color: AppColors.bg, borderRadius: BorderRadius.circular(6))),
              FractionallySizedBox(
                alignment: Alignment.centerLeft,
                widthFactor: t.clamp(0.01, 1.0),
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(6),
                    gradient: LinearGradient(colors: [AppColors.blue, AppColors.blue.withOpacity(0.7)]),
                  ),
                ),
              ),
            ])),
          ),
          const SizedBox(height: 6),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('${(t * 100).toInt()}%', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.blue)),
            Flexible(child: Text(_funFact(t), style: TextStyle(fontSize: 10, color: AppColors.dim, fontStyle: FontStyle.italic), overflow: TextOverflow.ellipsis)),
          ]),
        ])),
        const SizedBox(height: 28),

        // ── Step indicators ──
        SizedBox(width: 340, child: Column(children: List.generate(steps.length, (i) {
          final step = steps[i];
          final isDone = step.status == StepStatus.done;
          final isRunning = step.status == StepStatus.running;
          final isPending = step.status == StepStatus.pending;
          return Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 400),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isRunning ? AppColors.blue.withOpacity(0.06) : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: isRunning ? AppColors.blue.withOpacity(0.15) : Colors.transparent),
              ),
              child: Row(children: [
                // Status icon
                SizedBox(width: 22, height: 22, child: isDone
                  ? Icon(Icons.check_circle, size: 18, color: AppColors.green)
                  : isRunning
                    ? SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.blue))
                    : Icon(Icons.radio_button_unchecked, size: 16, color: AppColors.border)),
                const SizedBox(width: 10),
                // Step icon
                Text(step.icon, style: TextStyle(fontSize: 14, color: isPending ? AppColors.dim : null)),
                const SizedBox(width: 8),
                // Label
                Expanded(child: Text(
                  step.label,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: isRunning ? FontWeight.w600 : FontWeight.w400,
                    color: isPending ? AppColors.dim : isDone ? AppColors.green : AppColors.text,
                  ),
                )),
                if (isDone) Text('✓', style: TextStyle(fontSize: 11, color: AppColors.green, fontWeight: FontWeight.w600)),
                if (isRunning) _DotPulse(),
              ]),
            ),
          );
        }))),
      ]),
    )));
  }
}

/// Three-dot pulse animation for running steps
class _DotPulse extends StatefulWidget {
  @override
  State<_DotPulse> createState() => _DotPulseState();
}
class _DotPulseState extends State<_DotPulse> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat();
  }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) {
        final v = _ctrl.value;
        return Row(mainAxisSize: MainAxisSize.min, children: List.generate(3, (i) {
          final delay = i * 0.2;
          final t = ((v - delay) % 1.0).clamp(0.0, 1.0);
          final opacity = (t < 0.5 ? t * 2 : 2 - t * 2).clamp(0.3, 1.0);
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 1),
            child: Opacity(opacity: opacity, child: Container(width: 4, height: 4, decoration: BoxDecoration(shape: BoxShape.circle, color: AppColors.blue))),
          );
        }));
      },
    );
  }
}

/// Toolbar with formatting buttons — executes commands inside contenteditable iframe
class _FormattingToolbar extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: AppColors.bg, border: Border(bottom: BorderSide(color: AppColors.border))),
      child: Row(children: [
        // ── Text style ──
        _ToolBtn(icon: Icons.format_bold, tooltip: 'Жирный (Ctrl+B)', onTap: () => iframeExecCommand('bold')),
        _ToolBtn(icon: Icons.format_italic, tooltip: 'Курсив (Ctrl+I)', onTap: () => iframeExecCommand('italic')),
        _ToolBtn(icon: Icons.format_underlined, tooltip: 'Подчёркнутый (Ctrl+U)', onTap: () => iframeExecCommand('underline')),
        _ToolBtn(icon: Icons.strikethrough_s, tooltip: 'Зачёркнутый', onTap: () => iframeExecCommand('strikeThrough')),
        _ToolDivider(),
        // ── Headings ──
        _ToolDropdown(label: 'Стиль', items: {
          'Обычный': 'P',
          'Заголовок 1': 'H1',
          'Заголовок 2': 'H2',
          'Заголовок 3': 'H3',
        }, onSelected: (tag) => iframeExecCommand('formatBlock', '<$tag>')),
        _ToolDivider(),
        // ── Lists ──
        _ToolBtn(icon: Icons.format_list_bulleted, tooltip: 'Маркированный список', onTap: () => iframeExecCommand('insertUnorderedList')),
        _ToolBtn(icon: Icons.format_list_numbered, tooltip: 'Нумерованный список', onTap: () => iframeExecCommand('insertOrderedList')),
        _ToolDivider(),
        // ── Indentation ──
        _ToolBtn(icon: Icons.format_indent_decrease, tooltip: 'Уменьшить отступ', onTap: () => iframeExecCommand('outdent')),
        _ToolBtn(icon: Icons.format_indent_increase, tooltip: 'Увеличить отступ', onTap: () => iframeExecCommand('indent')),
        _ToolDivider(),
        // ── Alignment ──
        _ToolBtn(icon: Icons.format_align_left, tooltip: 'По левому краю', onTap: () => iframeExecCommand('justifyLeft')),
        _ToolBtn(icon: Icons.format_align_center, tooltip: 'По центру', onTap: () => iframeExecCommand('justifyCenter')),
        _ToolBtn(icon: Icons.format_align_right, tooltip: 'По правому краю', onTap: () => iframeExecCommand('justifyRight')),
        _ToolBtn(icon: Icons.format_align_justify, tooltip: 'По ширине', onTap: () => iframeExecCommand('justifyFull')),
        _ToolDivider(),
        // ── Other ──
        _ToolBtn(icon: Icons.horizontal_rule, tooltip: 'Горизонтальная линия', onTap: () => iframeExecCommand('insertHorizontalRule')),
        _ToolBtn(icon: Icons.format_clear, tooltip: 'Очистить форматирование', onTap: () => iframeExecCommand('removeFormat')),
        const Spacer(),
        _ToolBtn(icon: Icons.undo, tooltip: 'Отменить (Ctrl+Z)', onTap: () => iframeExecCommand('undo')),
        _ToolBtn(icon: Icons.redo, tooltip: 'Повторить (Ctrl+Y)', onTap: () => iframeExecCommand('redo')),
      ]),
    );
  }
}

class _ToolBtn extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback onTap;
  const _ToolBtn({required this.icon, required this.tooltip, required this.onTap});
  @override
  Widget build(BuildContext context) {
    return Tooltip(message: tooltip, waitDuration: const Duration(milliseconds: 400),
      child: InkWell(onTap: onTap, borderRadius: BorderRadius.circular(4),
        child: Container(
          width: 28, height: 28,
          alignment: Alignment.center,
          child: Icon(icon, size: 16, color: AppColors.text2),
        ),
      ),
    );
  }
}

class _ToolDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(width: 1, height: 18, margin: const EdgeInsets.symmetric(horizontal: 4), color: AppColors.border);
  }
}

class _ToolDropdown extends StatelessWidget {
  final String label;
  final Map<String, String> items;
  final ValueChanged<String> onSelected;
  const _ToolDropdown({required this.label, required this.items, required this.onSelected});
  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      tooltip: 'Стиль текста',
      onSelected: onSelected,
      offset: const Offset(0, 32),
      itemBuilder: (_) => items.entries.map((e) => PopupMenuItem(value: e.value,
        child: Text(e.key, style: TextStyle(
          fontSize: e.value == 'P' ? 13 : (e.value == 'H1' ? 18 : e.value == 'H2' ? 15 : 13),
          fontWeight: e.value == 'P' ? FontWeight.normal : FontWeight.bold,
        )),
      )).toList(),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(borderRadius: BorderRadius.circular(4), border: Border.all(color: AppColors.border)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(label, style: TextStyle(fontSize: 11, color: AppColors.text2)),
          const SizedBox(width: 2),
          Icon(Icons.arrow_drop_down, size: 14, color: AppColors.dim),
        ]),
      ),
    );
  }
}

/// Renders HTML inside iframe with contenteditable body — WYSIWYG editor
class _DocIframeView extends StatefulWidget {
  final String html;
  const _DocIframeView({required this.html, super.key});
  @override
  State<_DocIframeView> createState() => _DocIframeViewState();
}

class _DocIframeViewState extends State<_DocIframeView> {
  late String _viewId;

  @override
  void initState() {
    super.initState();
    _viewId = 'doc-iframe-${DateTime.now().millisecondsSinceEpoch}';
    final fullHtml = _buildEditableHtml(widget.html);
    registerDocIframe(_viewId, fullHtml);
  }

  String _buildEditableHtml(String bodyHtml) {
    // Body is contenteditable — user clicks and types like Google Docs
    return '''<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {
  font-family: 'Segoe UI', -apple-system, Arial, sans-serif;
  font-size: 13px; line-height: 1.7; color: #1a1a2e;
  padding: 32px 40px; margin: 0; background: #fff;
  outline: none; min-height: 100vh;
}
body:focus { outline: none; }
h1, h2, h3 { color: #1a1a2e; margin-top: 24px; }
h1 { font-size: 18px; border-bottom: 2px solid #4361ee; padding-bottom: 8px; }
h2 { font-size: 15px; color: #3a3a5c; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; }
h3 { font-size: 13px; color: #4361ee; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }
th, td { border: 1px solid #dde; padding: 8px 10px; text-align: left; vertical-align: top; }
th { background: #f0f2ff; font-weight: 600; color: #3a3a5c; }
tr:nth-child(even) { background: #fafbff; }
td:first-child { font-weight: 500; min-width: 180px; background: #f8f9ff; }
p { margin: 6px 0; }
strong { color: #1a1a2e; }
a { color: #4361ee; }
blockquote { border-left: 3px solid #4361ee; padding: 8px 16px; margin: 12px 0; background: #f8f9ff; color: #666; font-style: italic; }
ul, ol { padding-left: 24px; }
li { margin-bottom: 4px; }
::selection { background: #4361ee33; }
</style></head>
<body contenteditable="true" spellcheck="true">$bodyHtml</body>
</html>''';
  }

  @override
  Widget build(BuildContext context) {
    return HtmlElementView(viewType: _viewId);
  }
}

class _SmBtn extends StatelessWidget {
  final IconData icon; final String label; final bool primary; final VoidCallback onTap;
  const _SmBtn({required this.icon, required this.label, this.primary = false, required this.onTap});
  @override
  Widget build(BuildContext context) {
    return InkWell(onTap: onTap, borderRadius: BorderRadius.circular(6), child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(color: primary ? AppColors.blue : AppColors.bg, borderRadius: BorderRadius.circular(6), border: primary ? null : Border.all(color: AppColors.border, width: 1.5)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [Icon(icon, size: 12, color: primary ? Colors.white : AppColors.muted), const SizedBox(width: 4), Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: primary ? Colors.white : AppColors.muted))]),
    ));
  }
}

class _StatusPill extends StatelessWidget {
  final String status; const _StatusPill({required this.status});
  @override
  Widget build(BuildContext context) {
    final m = {'idle': (AppColors.bg, AppColors.dim, 'ожидание'), 'saved': (AppColors.greenLight, AppColors.green, '✓ Сохранено'), 'edited': (AppColors.orangeLight, AppColors.orange, '● Изменено')};
    final (bg, fg, text) = m[status] ?? m['idle']!;
    return Container(padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3), decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)), child: Text(text, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: fg)));
  }
}

class _RightPanel extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    return Container(color: AppColors.surface, child: Column(children: [
      _DocumentsSection(state: state),
      Expanded(child: _HistorySection(state: state)),
      _ChatSection(state: state),
    ]));
  }
}

class _DocumentsSection extends StatelessWidget {
  final AppState state; const _DocumentsSection({required this.state});
  @override
  Widget build(BuildContext context) {
    return Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.border))), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('ДОКУМЕНТЫ', style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.w700, letterSpacing: 1, color: AppColors.dim)),
      const SizedBox(height: 8),
      if (state.generationComplete) ...[
        _DocCard(icon: '📋', name: state.editorFileName, sub: '.docx', onTap: () => state.openDocument('synopsis')),
        _DocCard(icon: '📊', name: 'Обоснование_${state.form.innRu}.docx', sub: 'Источники', onTap: () => state.openDocument('rationale')),
      ] else
        Center(child: Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Column(children: [
          Text('📂', style: TextStyle(fontSize: 20, color: AppColors.dim.withOpacity(0.3))),
          const SizedBox(height: 4),
          Text('Документы появятся после генерации', style: TextStyle(fontSize: 11, color: AppColors.dim)),
        ]))),
    ]));
  }
}

class _DocCard extends StatelessWidget {
  final String icon, name, sub; final VoidCallback onTap; const _DocCard({required this.icon, required this.name, required this.sub, required this.onTap});
  @override
  Widget build(BuildContext context) {
    return InkWell(onTap: onTap, child: Container(margin: const EdgeInsets.only(bottom: 4), padding: const EdgeInsets.all(8), decoration: BoxDecoration(color: AppColors.bg, borderRadius: BorderRadius.circular(7), border: Border.all(color: AppColors.border, width: 1.5)),
      child: Row(children: [Text(icon, style: const TextStyle(fontSize: 14)), const SizedBox(width: 8), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(name, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis), Text(sub, style: TextStyle(fontSize: 9, color: AppColors.muted))])), Text('Открыть', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: AppColors.mid))])));
  }
}

class _HistorySection extends StatelessWidget {
  final AppState state; const _HistorySection({required this.state});
  @override
  Widget build(BuildContext context) {
    return Container(decoration: BoxDecoration(border: Border(bottom: BorderSide(color: AppColors.border))), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(padding: const EdgeInsets.fromLTRB(14, 12, 14, 8), child: Row(children: [Text('ИСТОРИЯ ГЕНЕРАЦИЙ', style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.w700, letterSpacing: 1, color: AppColors.dim)), const Spacer(), Container(padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1), decoration: BoxDecoration(color: AppColors.blueLight, borderRadius: BorderRadius.circular(99)), child: Text('${state.history.length}', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: AppColors.blue)))])),
      Expanded(child: state.history.isEmpty
        ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [Text('📂', style: TextStyle(fontSize: 20, color: AppColors.dim.withOpacity(0.3))), const SizedBox(height: 4), Text('Нет сохранённых генераций', style: TextStyle(fontSize: 11, color: AppColors.dim))]))
        : ListView.builder(padding: const EdgeInsets.symmetric(horizontal: 14), itemCount: state.history.length, itemBuilder: (ctx, i) { final h = state.history[i]; return Container(margin: const EdgeInsets.only(bottom: 2), padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6), decoration: BoxDecoration(borderRadius: BorderRadius.circular(6)),
            child: Row(children: [Text('📋', style: const TextStyle(fontSize: 12)), const SizedBox(width: 7), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text('${h.inn} · ${h.dose}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600), overflow: TextOverflow.ellipsis), Text('${h.form} · ${h.date}', style: TextStyle(fontSize: 9.5, color: AppColors.muted))])), IconButton(icon: Icon(Icons.close, size: 13, color: AppColors.dim), onPressed: () => state.removeHistory(i), padding: EdgeInsets.zero, constraints: const BoxConstraints())])); })),
    ]));
  }
}

class _ChatSection extends StatefulWidget {
  final AppState state; const _ChatSection({required this.state});
  @override State<_ChatSection> createState() => _ChatSectionState();
}

class _ChatSectionState extends State<_ChatSection> {
  final _c = TextEditingController(); final _sc = ScrollController();
  void _send() { final t = _c.text.trim(); if (t.isEmpty) return; widget.state.sendChatMessage(t); _c.clear(); Future.delayed(const Duration(milliseconds: 100), () { if (_sc.hasClients) _sc.animateTo(_sc.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut); }); }
  @override
  Widget build(BuildContext context) {
    final s = widget.state; final exp = s.chatExpanded;
    return AnimatedContainer(duration: const Duration(milliseconds: 250), height: exp ? 340 : 42, child: Column(children: [
      InkWell(onTap: s.toggleChat, child: Container(height: 42, padding: const EdgeInsets.symmetric(horizontal: 14), decoration: BoxDecoration(border: Border(top: BorderSide(color: AppColors.border))),
        child: Row(children: [Container(width: 22, height: 22, decoration: BoxDecoration(gradient: AppColors.gradientPrimary, borderRadius: BorderRadius.circular(6)), child: const Icon(Icons.chat_bubble, size: 12, color: Colors.white)), const SizedBox(width: 6),
          Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [Text('Ассистент', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.text)), Text('Правки и вопросы', style: TextStyle(fontSize: 9, color: AppColors.muted))]),
          const Spacer(), AnimatedRotation(turns: exp ? 0 : 0.5, duration: const Duration(milliseconds: 200), child: Icon(Icons.keyboard_arrow_up, size: 16, color: AppColors.dim))]))),
      if (exp) ...[
        Expanded(child: ListView.builder(controller: _sc, padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8), itemCount: s.chatMessages.length, itemBuilder: (ctx, i) => _ChatBubble(message: s.chatMessages[i]))),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Wrap(spacing: 3, runSpacing: 3, children: ['Пересчитай выборку', 'Добавь женщин', 'Измени отмывочный', 'Объясни дизайн'].map((sug) => InkWell(onTap: () { _c.text = sug; _send(); }, child: Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3), decoration: BoxDecoration(color: AppColors.violetLight, borderRadius: BorderRadius.circular(99), border: Border.all(color: AppColors.violet.withOpacity(0.16))), child: Text(sug, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w500, color: AppColors.mid))))).toList())),
        Padding(padding: const EdgeInsets.all(10), child: Row(children: [
          Expanded(child: TextField(controller: _c, style: const TextStyle(fontSize: 12), maxLines: 1, decoration: InputDecoration(hintText: 'Что изменить…', hintStyle: TextStyle(color: AppColors.dim, fontSize: 12), contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7), filled: true, fillColor: AppColors.bg, isDense: true, border: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.border, width: 1.5)), focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(7), borderSide: BorderSide(color: AppColors.blue, width: 1.5))), onSubmitted: (_) => _send())),
          const SizedBox(width: 5), InkWell(onTap: _send, child: Container(width: 32, height: 32, decoration: BoxDecoration(gradient: AppColors.gradientPrimary, borderRadius: BorderRadius.circular(7)), child: const Icon(Icons.send, size: 14, color: Colors.white)))])),
      ],
    ]));
  }
}

class _ChatBubble extends StatelessWidget {
  final ChatMessage message; const _ChatBubble({required this.message});
  @override
  Widget build(BuildContext context) {
    final isU = message.role == ChatRole.user; final isS = message.role == ChatRole.system;
    return Align(alignment: isU ? Alignment.centerRight : (isS ? Alignment.center : Alignment.centerLeft),
      child: Container(margin: const EdgeInsets.only(bottom: 5), padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7), constraints: BoxConstraints(maxWidth: isS ? 280 : 250),
        decoration: BoxDecoration(color: isU ? null : (isS ? AppColors.greenLight : AppColors.bg), gradient: isU ? AppColors.gradientPrimary : null, borderRadius: BorderRadius.circular(9), border: isU ? null : Border.all(color: isS ? AppColors.green.withOpacity(0.2) : AppColors.border)),
        child: Text(message.text, style: TextStyle(fontSize: 11.5, color: isU ? Colors.white : (isS ? AppColors.green : AppColors.text2)))));
  }
}