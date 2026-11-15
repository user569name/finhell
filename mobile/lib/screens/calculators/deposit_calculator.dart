import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class DepositCalculator extends StatefulWidget {
  const DepositCalculator({super.key});

  @override
  State<DepositCalculator> createState() => _DepositCalculatorState();
}

class _DepositCalculatorState extends State<DepositCalculator>
    with AutomaticKeepAliveClientMixin {
  final _amount = TextEditingController(text: '500000');
  final _rate = TextEditingController(text: '16');
  final _topUp = TextEditingController(text: '10000');
  final _keyRate = TextEditingController(text: '16');
  final _inflation = TextEditingController(text: '8');

  int _months = 12;
  int _capitalization = 1;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _amount.dispose();
    _rate.dispose();
    _topUp.dispose();
    _keyRate.dispose();
    _inflation.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateDeposit(
      amount: calcNumber(_amount, 500000),
      annualRatePercent: calcNumber(_rate, 16),
      months: _months,
      monthlyTopUp: calcNumber(_topUp, 10000),
      capitalizationMonths: _capitalization,
      keyRatePercent: calcNumber(_keyRate, 16),
      inflationPercent: calcNumber(_inflation, 8),
    );

    return CalculatorTab(
      title: 'Вклад',
      subtitle: 'Сложный процент, пополнения и НДФЛ с процентов',
      icon: Icons.savings_outlined,
      accent: SberColors.green,
      children: [
        CalcCard(
          title: 'Параметры вклада',
          subtitle: 'Пополнения учитываются в начале каждого месяца.',
          children: [
            CalcField(
              controller: _amount,
              label: 'Сумма вклада',
              suffix: '₽',
              onChanged: _changed,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _rate,
                    label: 'Ставка',
                    suffix: '%',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<int>(
                    value: _months,
                    label: 'Срок',
                    items: const [
                      DropdownMenuItem(value: 3, child: Text('3 месяца')),
                      DropdownMenuItem(value: 6, child: Text('6 месяцев')),
                      DropdownMenuItem(value: 12, child: Text('1 год')),
                      DropdownMenuItem(value: 18, child: Text('1,5 года')),
                      DropdownMenuItem(value: 24, child: Text('2 года')),
                      DropdownMenuItem(value: 36, child: Text('3 года')),
                      DropdownMenuItem(value: 60, child: Text('5 лет')),
                    ],
                    onChanged: (value) => setState(() => _months = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _topUp,
                    label: 'Пополнение в месяц',
                    suffix: '₽',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<int>(
                    value: _capitalization,
                    label: 'Капитализация',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('Ежемесячно')),
                      DropdownMenuItem(value: 3, child: Text('Ежеквартально')),
                      DropdownMenuItem(value: 12, child: Text('Ежегодно')),
                      DropdownMenuItem(value: 0, child: Text('В конце срока')),
                    ],
                    onChanged: (value) =>
                        setState(() => _capitalization = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _keyRate,
                    label: 'Ключевая ставка',
                    suffix: '%',
                    helper: 'Для лимита налога',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _inflation,
                    label: 'Инфляция',
                    suffix: '%',
                    onChanged: _changed,
                  ),
                ),
              ],
            ),
          ],
        ),
        const SizedBox(height: 14),
        ResultHero(
          eyebrow: 'Итог через $_months мес.',
          value: formatRub(result.netAmount),
          caption:
              'До налога ${formatRub(result.finalAmount)} · '
              'налог ${formatRub(result.tax)}',
          chips: [
            'Взносы ${formatRub(result.contributed)}',
            'Доходность ${formatPct(result.annualYield)} в год',
          ],
        ),
        const SizedBox(height: 12),
        MetricGrid(
          metrics: [
            CalcMetric(
              label: 'Взносы за срок',
              value: formatRub(result.contributed),
            ),
            CalcMetric(
              label: 'Проценты',
              value: formatRub(result.grossInterest),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'НДФЛ с процентов',
              value: formatRub(result.tax),
              accent: kTaxAccent,
            ),
            CalcMetric(label: 'На руки', value: formatRub(result.netAmount)),
            CalcMetric(
              label: 'Доходность за срок',
              value: formatPct(result.totalYield),
            ),
            CalcMetric(
              label: 'Доходность в год',
              value: formatPct(result.annualYield),
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
