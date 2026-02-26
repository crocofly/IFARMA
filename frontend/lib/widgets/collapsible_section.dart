import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class CollapsibleSection extends StatefulWidget {
  final int number;
  final String title;
  final String tag;
  final Color badgeColor;
  final Color tagColor;
  final Color tagBgColor;
  final bool initiallyExpanded;
  final List<Widget> children;

  const CollapsibleSection({
    super.key,
    required this.number,
    required this.title,
    required this.tag,
    required this.badgeColor,
    required this.tagColor,
    required this.tagBgColor,
    this.initiallyExpanded = false,
    required this.children,
  });

  @override
  State<CollapsibleSection> createState() => _CollapsibleSectionState();
}

class _CollapsibleSectionState extends State<CollapsibleSection>
    with SingleTickerProviderStateMixin {
  late bool _expanded;
  late AnimationController _controller;
  late Animation<double> _heightFactor;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
    _controller = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
      value: _expanded ? 1.0 : 0.0,
    );
    _heightFactor = _controller.drive(CurveTween(curve: Curves.easeInOut));
  }

  void _toggle() {
    setState(() {
      _expanded = !_expanded;
      if (_expanded) {
        _controller.forward();
      } else {
        _controller.reverse();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        children: [
          // Header
          InkWell(
            onTap: _toggle,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: [
                  // Badge
                  Container(
                    width: 18, height: 18,
                    decoration: BoxDecoration(
                      color: widget.badgeColor,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      '${widget.number}',
                      style: const TextStyle(
                        fontSize: 10, fontWeight: FontWeight.w700, color: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(width: 7),
                  // Title
                  Expanded(
                    child: Text(
                      widget.title,
                      style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700),
                    ),
                  ),
                  // Tag
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: widget.tagBgColor,
                      borderRadius: BorderRadius.circular(99),
                    ),
                    child: Text(
                      widget.tag,
                      style: TextStyle(fontSize: 9, fontWeight: FontWeight.w600, color: widget.tagColor),
                    ),
                  ),
                  const SizedBox(width: 6),
                  // Chevron
                  AnimatedRotation(
                    turns: _expanded ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(Icons.keyboard_arrow_down, size: 16, color: AppColors.dim),
                  ),
                ],
              ),
            ),
          ),
          // Content
          ClipRect(
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, child) => Align(
                heightFactor: _heightFactor.value,
                alignment: Alignment.topCenter,
                child: child,
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: widget.children
                      .expand((w) => [w, const SizedBox(height: 10)])
                      .toList()
                    ..removeLast(),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
