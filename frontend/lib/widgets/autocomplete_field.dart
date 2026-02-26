import 'dart:async';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Async search callback — returns list of items from server
typedef AsyncSearchFn = Future<List<AutocompleteItem>> Function(String query);

class AutocompleteField extends StatefulWidget {
  final String label;
  final String placeholder;
  final String? hint;
  final bool required;
  final List<AutocompleteItem> items;
  final String value;
  final ValueChanged<String> onChanged;
  final ValueChanged<AutocompleteItem>? onItemSelected;
  final String? warningText;
  final bool showIcon;
  /// If provided, calls server for suggestions (with debounce).
  /// Static [items] are shown first, then async results are appended.
  final AsyncSearchFn? asyncSearch;
  /// If true, triggers asyncSearch on focus even when text is empty.
  /// Useful for fields that should auto-suggest based on external context.
  final bool searchOnFocus;

  const AutocompleteField({
    super.key,
    required this.label,
    required this.placeholder,
    this.hint,
    this.required = false,
    this.items = const [],
    required this.value,
    required this.onChanged,
    this.onItemSelected,
    this.warningText,
    this.showIcon = false,
    this.asyncSearch,
    this.searchOnFocus = false,
  });

  @override
  State<AutocompleteField> createState() => _AutocompleteFieldState();
}

class _AutocompleteFieldState extends State<AutocompleteField> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();
  final _layerLink = LayerLink();
  OverlayEntry? _overlayEntry;
  bool _hasFocus = false;
  Timer? _debounce;
  List<AutocompleteItem> _asyncItems = [];
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _controller.text = widget.value;
    _focusNode.addListener(_onFocusChange);
  }

  @override
  void didUpdateWidget(AutocompleteField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != _controller.text) {
      _controller.text = widget.value;
    }
  }

  void _onFocusChange() {
    _hasFocus = _focusNode.hasFocus;
    if (_hasFocus) {
      // Don't show overlay for plain text fields (no items, no asyncSearch)
      if (widget.items.isEmpty && widget.asyncSearch == null) return;

      // Auto-search on focus (e.g. reference drug by INN)
      if (widget.searchOnFocus && widget.asyncSearch != null && _asyncItems.isEmpty) {
        setState(() => _isLoading = true);
        _showOverlay();
        widget.asyncSearch!(_controller.text.trim()).then((results) {
          if (mounted) {
            setState(() {
              _asyncItems = results;
              _isLoading = false;
            });
            _showOverlay();
          }
        }).catchError((_) {
          if (mounted) setState(() => _isLoading = false);
        });
      } else {
        _showOverlay();
      }
    } else {
      Future.delayed(const Duration(milliseconds: 200), _removeOverlay);
    }
  }

  void _onTextChanged(String val) {
    widget.onChanged(val);

    // Don't show overlay for plain text fields
    if (widget.items.isEmpty && widget.asyncSearch == null) return;

    _showOverlay();

    // Async search with debounce
    if (widget.asyncSearch != null && val.trim().length >= 2) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(milliseconds: 150), () async {
        if (!mounted) return;
        setState(() => _isLoading = true);
        try {
          final results = await widget.asyncSearch!(val.trim());
          if (mounted) {
            setState(() {
              _asyncItems = results;
              _isLoading = false;
            });
            _showOverlay();
          }
        } catch (_) {
          if (mounted) setState(() => _isLoading = false);
        }
      });
    } else {
      _asyncItems = [];
    }
  }

  void _showOverlay() {
    _removeOverlay();
    final overlay = Overlay.of(context);
    final renderBox = context.findRenderObject() as RenderBox;
    final size = renderBox.size;

    _overlayEntry = OverlayEntry(
      builder: (context) => Positioned(
        width: size.width,
        child: CompositedTransformFollower(
          link: _layerLink,
          showWhenUnlinked: false,
          offset: Offset(0, size.height + 2),
          child: Material(
            elevation: 8,
            borderRadius: BorderRadius.circular(7),
            child: _buildDropdown(),
          ),
        ),
      ),
    );
    overlay.insert(_overlayEntry!);
  }

  void _removeOverlay() {
    _overlayEntry?.remove();
    _overlayEntry = null;
  }

  Widget _buildDropdown() {
    final query = _controller.text.trim().toLowerCase();

    // Merge: static items filtered locally + async items from server
    final staticFiltered = widget.items.where((item) {
      if (query.isEmpty) return true;
      return item.title.toLowerCase().contains(query) ||
          (item.subtitle?.toLowerCase().contains(query) ?? false);
    }).toList();

    // Deduplicate: async items that aren't already in static
    final staticTitles = staticFiltered.map((e) => e.title.toLowerCase()).toSet();
    final asyncNew = _asyncItems.where((item) =>
        !staticTitles.contains(item.title.toLowerCase())).toList();

    final all = [...staticFiltered, ...asyncNew].take(10).toList();

    if (all.isEmpty && !_isLoading) {
      // If searchOnFocus with empty text and no results — just hide, don't show "nothing found"
      if (widget.searchOnFocus && query.isEmpty) {
        Future.microtask(() => _removeOverlay());
        return const SizedBox.shrink();
      }
      // For typed queries — show "nothing found" only if there's actual text
      if (query.isEmpty) {
        Future.microtask(() => _removeOverlay());
        return const SizedBox.shrink();
      }
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: AppColors.border),
        ),
        child: Text(
          'Ничего не найдено',
          style: TextStyle(fontSize: 12, color: AppColors.dim),
        ),
      );
    }

    return Container(
      constraints: const BoxConstraints(maxHeight: 220),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(7),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_isLoading)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: SizedBox(height: 14, width: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.blue)),
            ),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              padding: EdgeInsets.zero,
              itemCount: all.length,
              itemBuilder: (ctx, i) {
                final item = all[i];
                final isAsync = i >= staticFiltered.length;
                return InkWell(
                  onTap: () {
                    _controller.text = item.title;
                    widget.onChanged(item.title);
                    widget.onItemSelected?.call(item);
                    _removeOverlay();
                    _focusNode.unfocus();
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    decoration: BoxDecoration(
                      border: i < all.length - 1
                          ? Border(bottom: BorderSide(color: AppColors.border))
                          : null,
                    ),
                    child: Row(
                      children: [
                        if (isAsync)
                          Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: Icon(Icons.travel_explore, size: 12, color: AppColors.muted),
                          ),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(item.title, style: const TextStyle(fontSize: 12.5)),
                              if (item.subtitle != null)
                                Text(
                                  item.subtitle!,
                                  style: TextStyle(fontSize: 10, color: AppColors.muted),
                                ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _removeOverlay();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Label
        Row(
          children: [
            if (widget.required)
              Text('* ', style: TextStyle(color: AppColors.orange, fontWeight: FontWeight.w700, fontSize: 13)),
            Text(
              widget.label,
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.text2),
            ),
          ],
        ),
        const SizedBox(height: 4),
        // Input
        CompositedTransformTarget(
          link: _layerLink,
          child: TextField(
            controller: _controller,
            focusNode: _focusNode,
            style: const TextStyle(fontSize: 13),
            decoration: InputDecoration(
              hintText: widget.placeholder,
              hintStyle: TextStyle(color: AppColors.dim, fontSize: 13),
              prefixIcon: widget.showIcon
                  ? Icon(Icons.search, size: 16, color: AppColors.muted)
                  : null,
              prefixIconConstraints: const BoxConstraints(minWidth: 36),
              contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
              filled: true,
              fillColor: _hasFocus ? AppColors.surface : AppColors.bg,
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
            ),
            onChanged: _onTextChanged,
          ),
        ),
        // Hint
        if (widget.hint != null) ...[
          const SizedBox(height: 3),
          Text(widget.hint!, style: TextStyle(fontSize: 10, color: AppColors.dim)),
        ],
        // Warning
        if (widget.warningText != null) ...[
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: AppColors.yellowLight,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: AppColors.yellow.withOpacity(0.2)),
            ),
            child: Row(
              children: [
                Icon(Icons.warning_amber_rounded, size: 13, color: AppColors.yellow),
                const SizedBox(width: 5),
                Expanded(
                  child: Text(
                    widget.warningText!,
                    style: TextStyle(fontSize: 10, color: AppColors.yellow),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class AutocompleteItem {
  final String title;
  final String? subtitle;
  final dynamic data;

  const AutocompleteItem({required this.title, this.subtitle, this.data});
}