import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class InflationCalculator extends StatefulWidget {
  const InflationCalculator({super.key});

  @override
  State<InflationCalculator> createState() => _InflationCalculatorState();
}

class _InflationCalculatorState extends State<InflationCalculator>
    with AutomaticKeepAliveClientMixin {
  final _amount = TextEditingController(text: '1000000');
  final _inflation = TextEditingController(text: '8');
  final _depositRate = TextEditingController(text: '16');
  final _keyRate = TextEditingController(text: '16');

  int _years = 10;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _amount.dispose();
    _inflation.dispose();
    _depositRate.dispose();
    _keyRate.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateInflation(
      amount: calcNumber(_amount, 1000000),
      inflationPercent: calcNumber(_inflation, 8),
      years: _years,
      depositRatePercent: calcNumber(_depositRate, 16),
      keyRatePercent: calcNumber(_keyRate, 16),
    );

    return CalculatorTab(
      title: 'Инфляция',
      subtitle: 'Покупательная способность, будущие цены и нужная доходность',
      icon: Icons.trending_down,
      accent: kInflationAccent,
      children: [
        CalcCard(
          title: 'Параметры расчёта',
          subtitle:
              'Доходность вложения можно поставить в 0, чтобы '
              'посчитать только инфляцию.',
          children: [
            CalcField(
              controller: _amount,
              label: 'Сумма сегодня',
              suffix: '₽',
              onChanged: _changed,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _inflation,
                    label: 'Инфляция в год',
                    suffix: '%',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<int>(
                    value: _years,
                    label: 'Срок',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('1 год')),
                      DropdownMenuItem(value: 3, child: Text('3 года')),
                      DropdownMenuItem(value: 5, child: Text('5 лет')),
                      DropdownMenuItem(value: 10, child: Text('10 лет')),
                      DropdownMenuItem(value: 15, child: Text('15 лет')),
                      DropdownMenuItem(value: 20, child: Text('20 лет')),
                    ],
                    onChanged: (value) => setState(() => _years = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _depositRate,
                    label: 'Доходность вложения',
                    suffix: '%',
                    helper: '0 — деньги без вложения',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _keyRate,
                    label: 'Ключевая ставка',
                    suffix: '%',
                    helper: 'Для лимита налога',
                    onChanged: _changed,
                  ),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 14),
        ResultHero(
          eyebrow: 'Будущая цена корзины',
          value: formatRub(result.futureCost),
          caption:
              'Сегодня ${formatRub(calcNumber(_amount, 1000000))} · '
              'через ${formatYears(_years)}',
          chips: [
            'Потеря ${formatRub(result.loss)}',
            'Нужно ${formatPct(result.requiredNominal)} в год',
          ],
        ),
        const SizedBox(height: 12),
        MetricGrid(
          metrics: [
            CalcMetric(
              label: 'Сумма сегодня',
              value: formatRub(calcNumber(_amount, 1000000)),
            ),
            CalcMetric(
              label: 'Будущая цена корзины',
              value: formatRub(result.futureCost),
              accent: kInflationAccent,
            ),
            CalcMetric(
              label: 'Покупательная способность',
              value: formatRub(result.purchasingPower),
            ),
            CalcMetric(
              label: 'Потеря покупательной способности',
              value: formatRub(result.loss),
              accent: SberColors.red,
            ),
            CalcMetric(
              label: 'Нужная доходность',
              value: formatPct(result.requiredNominal),
            ),
            CalcMetric(
              label: 'Доходность до налога',
              value: formatPct(result.requiredPreTax),
              note: 'При НДФЛ 13%',
            ),
            CalcMetric(
              label: 'Капитал с доходностью',
              value: formatRub(result.nominalCapital),
            ),
            CalcMetric(
              label: 'Реальный капитал после налога',
              value: formatRub(result.afterTaxReal),
              accent: SberColors.green,
            ),
          ],
        ),
        const SizedBox(height: 12),
        TaxCard(breakdown: result.taxes),
        const SizedBox(height: 12),
        InflationCard(breakdown: result.inflation),
      ],
    );
  }
}
