import 'package:flutter/material.dart';

import '../theme/sber_theme.dart';
import 'calculators/bonds_calculator.dart';
import 'calculators/deposit_calculator.dart';
import 'calculators/inflation_calculator.dart';
import 'calculators/mortgage_calculator.dart';
import 'calculators/ofz_calculator.dart';
import 'calculators/real_estate_calculator.dart';

class CalculatorsScreen extends StatelessWidget {
  const CalculatorsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return DefaultTabController(
      length: 6,
      child: Column(
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
                Text(
                  'Бесплатные расчёты · токены не списываются',
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: 10,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          const Expanded(
            child: TabBarView(
              children: [
                DepositCalculator(),
                OfzCalculator(),
                BondsCalculator(),
                RealEstateCalculator(),
                MortgageCalculator(),
                InflationCalculator(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
