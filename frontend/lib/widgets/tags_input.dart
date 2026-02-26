import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

typedef AsyncTagSearchFn = Future<List<String>> Function(String query);

class TagsInput extends StatefulWidget {
  final String label;
  final String placeholder;
  final String? hint;
  final List<String> tags;
  final List<String> suggestions;
  final ValueChanged<List<String>> onChanged;
  final AsyncTagSearchFn? asyncSearch;

  const TagsInput({
    super.key,
    required this.label,
    required this.placeholder,
    this.hint,
    required this.tags,
    required this.suggestions,
    required this.onChanged,
    this.asyncSearch,
  });

  @override
  State<TagsInput> createState() => _TagsInputState();
}

class _TagsInputState extends State<TagsInput> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  List<String> _filtered = [];
  List<String> _asyncResults = [];
  bool _showSuggestions = false;
  bool _loading = false;
  Timer? _debounce;

  void _addTag(String tag) {
    final trimmed = tag.trim();
    if (trimmed.isEmpty || widget.tags.contains(trimmed)) return;
    final newTags = [...widget.tags, trimmed];
    widget.onChanged(newTags);
    _controller.clear();
    setState(() {
      _showSuggestions = false;
      _filtered = [];
      _asyncResults = [];
    });
  }

  void _removeTag(int index) {
    final newTags = [...widget.tags];
    newTags.removeAt(index);
    widget.onChanged(newTags);
  }

  void _updateFilter(String query) {
    final q = query.toLowerCase();
    setState(() {
      if (q.isEmpty) {
        _filtered = [];
        _asyncResults = [];
        _showSuggestions = false;
        _loading = false;
      } else {
        _filtered = widget.suggestions
            .where((s) => s.toLowerCase().contains(q) && !widget.tags.contains(s))
            .take(6)
            .toList();
        _showSuggestions = _filtered.isNotEmpty;
      }
    });

    // Async search
    if (widget.asyncSearch != null && query.length >= 2) {
      _debounce?.cancel();
      setState(() {
        _loading = true;
        _showSuggestions = true; // Show dropdown immediately with loading indicator
      });
      _debounce = Timer(const Duration(milliseconds: 150), () async {
        try {
          final results = await widget.asyncSearch!(query);
          if (!mounted) return;
          setState(() {
            _asyncResults = results
                .where((s) => !widget.tags.contains(s) &&
                    !_filtered.any((f) => f.toLowerCase() == s.toLowerCase()))
                .toList();
            _showSuggestions = _filtered.isNotEmpty || _asyncResults.isNotEmpty;
            _loading = false;
          });
        } catch (_) {
          if (mounted) setState(() { _loading = false; _showSuggestions = _filtered.isNotEmpty; });
        }
      });
    } else {
      _debounce?.cancel();
      setState(() {
        _asyncResults = [];
        _loading = false;
      });
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final allSuggestions = [..._filtered, ..._asyncResults];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.label,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2),
        ),
        const SizedBox(height: 4),
        // Tags
        if (widget.tags.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Wrap(
              spacing: 4,
              runSpacing: 4,
              children: widget.tags.asMap().entries.map((e) {
                return Container(
                  padding: const EdgeInsets.only(left: 8, top: 3, bottom: 3, right: 3),
                  decoration: BoxDecoration(
                    color: AppColors.blueLight,
                    borderRadius: BorderRadius.circular(99),
                    border: Border.all(color: AppColors.blue.withOpacity(0.16)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(e.value, style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w500, color: AppColors.blue)),
                      const SizedBox(width: 3),
                      InkWell(
                        onTap: () => _removeTag(e.key),
                        child: Container(
                          width: 14, height: 14,
                          decoration: BoxDecoration(
                            color: AppColors.blue.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(99),
                          ),
                          child: Icon(Icons.close, size: 9, color: AppColors.blue),
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        // Input
        TextField(
          controller: _controller,
          focusNode: _focusNode,
          style: const TextStyle(fontSize: 13),
          decoration: InputDecoration(
            hintText: widget.placeholder,
            hintStyle: TextStyle(color: AppColors.dim, fontSize: 13),
            contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            filled: true,
            fillColor: AppColors.bg,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(7),
              borderSide: BorderSide(color: AppColors.border, width: 1.5),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(7),
              borderSide: BorderSide(color: AppColors.border, width: 1.5),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(7),
              borderSide: BorderSide(color: AppColors.blue, width: 1.5),
            ),
            isDense: true,
            suffixIcon: _loading
                ? const Padding(
                    padding: EdgeInsets.all(10),
                    child: SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 1.5)),
                  )
                : null,
            suffixIconConstraints: const BoxConstraints(maxWidth: 34, maxHeight: 34),
          ),
          onChanged: _updateFilter,
          onSubmitted: (val) {
            _addTag(val);
          },
        ),
        // Suggestions dropdown
        if (_showSuggestions || _loading)
          Container(
            margin: const EdgeInsets.only(top: 2),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(7),
              border: Border.all(color: AppColors.border),
              boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.08), blurRadius: 12)],
            ),
            constraints: const BoxConstraints(maxHeight: 180),
            child: ListView(
              shrinkWrap: true,
              padding: EdgeInsets.zero,
              children: [
                // Local results
                ..._filtered.map((item) => InkWell(
                  onTap: () => _addTag(item),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    child: Text(item, style: const TextStyle(fontSize: 12)),
                  ),
                )),
                // Async results
                ..._asyncResults.map((item) => InkWell(
                  onTap: () => _addTag(item),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    child: Row(
                      children: [
                        Text('🌐 ', style: TextStyle(fontSize: 10)),
                        Expanded(child: Text(item, style: const TextStyle(fontSize: 12))),
                      ],
                    ),
                  ),
                )),
                // Loading
                if (_loading && allSuggestions.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    child: Text('Поиск...', style: TextStyle(fontSize: 11, color: AppColors.dim)),
                  ),
              ],
            ),
          ),
        // Hint
        if (widget.hint != null) ...[
          const SizedBox(height: 3),
          Text(widget.hint!, style: TextStyle(fontSize: 10, color: AppColors.dim)),
        ],
      ],
    );
  }
}