import 'package:flutter/material.dart';

import '../theme/sber_theme.dart';
import 'calculators/bonds_calculator.dart';
import 'calculators/credit_calculator.dart';
import 'calculators/deposit_calculator.dart';
import 'calculators/inflation_calculator.dart';
import 'calculators/mortgage_calculator.dart';
import 'calculators/ofz_calculator.dart';
import 'calculators/real_estate_calculator.dart';

class CalculatorsScreen extends StatefulWidget {
  const CalculatorsScreen({
    super.key,
    this.selectedIndex = 0,
    this.onTabChanged,
  });

  static const int tabCount = 7;

  final int selectedIndex;
  final ValueChanged<int>? onTabChanged;

  @override
  State<CalculatorsScreen> createState() => _CalculatorsScreenState();
}

class _CalculatorsScreenState extends State<CalculatorsScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _controller;
  late int _lastNotified;

  int _safeIndex(int value) {
    if (value < 0) return 0;
    if (value >= CalculatorsScreen.tabCount) {
      return CalculatorsScreen.tabCount - 1;
    }
    return value;
  }

  @override
  void initState() {
    super.initState();
    _lastNotified = _safeIndex(widget.selectedIndex);
    _controller = TabController(
      length: CalculatorsScreen.tabCount,
      vsync: this,
      initialIndex: _lastNotified,
    );
    _controller.addListener(_handleController);
  }

  void _handleController() {
    final index = _controller.index;
    if (index != _lastNotified) {
      _lastNotified = index;
      widget.onTabChanged?.call(index);
    }
  }

  @override
  void didUpdateWidget(covariant CalculatorsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final target = _safeIndex(widget.selectedIndex);
    if (target != _controller.index) {
      _lastNotified = target;
      _controller.animateTo(target);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_handleController);
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return Column(
      children: [
        Container(
          margin: const EdgeInsets.fromLTRB(20, 4, 20, 6),
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            color: theme.colorScheme.surfaceContainerHighest.withOpacity(
              dark ? 0.35 : 0.55,
            ),
          ),
          child: TabBar(
            controller: _controller,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            dividerColor: Colors.transparent,
            indicatorSize: TabBarIndicatorSize.tab,
            indicator: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: SberColors.green,
            ),
            labelColor: Colors.white,
            unselectedLabelColor: theme.colorScheme.onSurfaceVariant,
            labelStyle: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
            unselectedLabelStyle: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
            labelPadding: const EdgeInsets.symmetric(horizontal: 14),
            tabs: const [
              Tab(text: 'Вклад'),
              Tab(text: 'ОФЗ'),
              Tab(text: 'Облигации'),
              Tab(text: 'Недвижимость'),
              Tab(text: 'Ипотека'),
              Tab(text: 'Кредит'),
              Tab(text: 'Инфляция'),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 4),
          child: Row(
            children: [
              const Icon(Icons.lock_open, size: 13, color: SberColors.green),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  'Бесплатные расчёты · токены не списываются',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 10,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: TabBarView(
            controller: _controller,
            children: const [
              DepositCalculator(),
              OfzCalculator(),
              BondsCalculator(),
              RealEstateCalculator(),
              MortgageCalculator(),
              CreditCalculator(),
              InflationCalculator(),
            ],
          ),
        ),
      ],
    );
  }
}
