import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class MortgageCalculator extends StatefulWidget {
  const MortgageCalculator({super.key});

  @override
  State<MortgageCalculator> createState() => _MortgageCalculatorState();
}

class _MortgageCalculatorState extends State<MortgageCalculator>
    with AutomaticKeepAliveClientMixin {
  final _price = TextEditingController(text: '8000000');
  final _downPayment = TextEditingController(text: '2000000');
  final _rate = TextEditingController(text: '18');
  final _inflation = TextEditingController(text: '8');
  final _income = TextEditingController(text: '1200000');

  int _years = 20;
  bool _annuity = true;
  bool _useDeductions = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _price.dispose();
    _downPayment.dispose();
    _rate.dispose();
    _inflation.dispose();
    _income.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateMortgage(
      price: calcNumber(_price, 8000000),
      downPayment: calcNumber(_downPayment, 2000000),
      annualRatePercent: calcNumber(_rate, 18),
      years: _years,
      annuity: _annuity,
      inflationPercent: calcNumber(_inflation, 8),
      annualIncome: calcNumber(_income, 1200000),
      useDeductions: _useDeductions,
    );

    final heroValue = _annuity ? result.monthlyPayment : result.firstPayment;
    final heroLabel = _annuity ? 'Платёж в месяц' : 'Первый платёж';

    return CalculatorTab(
      title: 'Ипотека',
      subtitle: 'Платёж, переплата, вычет и реальная стоимость',
      icon: Icons.apartment_outlined,
      accent: SberColors.greenDark,
      children: [
        CalcCard(
          title: 'Параметры ипотеки',
          subtitle: 'Первоначальный взнос уменьшает сумму кредита.',
          children: [
            CalcField(
              controller: _price,
              label: 'Стоимость жилья',
              suffix: '₽',
              onChanged: _changed,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _downPayment,
                    label: 'Первоначальный взнос',
                    suffix: '₽',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _rate,
                    label: 'Ставка',
                    suffix: '%',
                    onChanged: _changed,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcDropdown<int>(
                    value: _years,
                    label: 'Срок',
                    items: const [
                      DropdownMenuItem(value: 5, child: Text('5 лет')),
                      DropdownMenuItem(value: 10, child: Text('10 лет')),
                      DropdownMenuItem(value: 15, child: Text('15 лет')),
                      DropdownMenuItem(value: 20, child: Text('20 лет')),
                      DropdownMenuItem(value: 25, child: Text('25 лет')),
                      DropdownMenuItem(value: 30, child: Text('30 лет')),
                    ],
                    onChanged: (value) => setState(() => _years = value),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<bool>(
                    value: _annuity,
                    label: 'Тип платежа',
                    items: const [
                      DropdownMenuItem(value: true, child: Text('Аннуитет')),
                      DropdownMenuItem(
                        value: false,
                        child: Text('Дифференцированный'),
                      ),
                    ],
                    onChanged: (value) => setState(() => _annuity = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _income,
                    label: 'Доход в год',
                    suffix: '₽',
                    helper: 'Для расчёта уплаченного НДФЛ',
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
            const SizedBox(height: 6),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: const Text(
                'Учитывать налоговый вычет',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
              ),
              subtitle: const Text(
                'Возврат 13% от стоимости жилья и процентов',
                style: TextStyle(fontSize: 11),
              ),
              value: _useDeductions,
              onChanged: (value) => setState(() => _useDeductions = value),
            ),
          ],
        ),
        const SizedBox(height: 14),
        ResultHero(
          eyebrow: heroLabel,
          value: formatRub(heroValue),
          caption: _annuity
              ? 'Переплата ${formatRub(result.totalInterest)} · '
                    'всего ${formatRub(result.totalPayments)}'
              : 'Последний платёж ${formatRub(result.lastPayment)} · '
                    'всего ${formatRub(result.totalPayments)}',
          chips: [
            if (_useDeductions) 'Вычет ${formatRub(result.usableDeduction)}',
            'Реальная переплата ${formatRub(result.realOverpayment)}',
          ],
        ),
        const SizedBox(height: 12),
        MetricGrid(
          metrics: [
            CalcMetric(
              label: 'Сумма кредита',
              value: formatRub(result.principal),
            ),
            CalcMetric(
              label: 'Переплата по процентам',
              value: formatRub(result.totalInterest),
              accent: kTaxAccent,
            ),
            CalcMetric(
              label: 'Всего платежей',
              value: formatRub(result.totalPayments),
            ),
            CalcMetric(
              label: 'Переплата',
              value: formatPct(result.overpaymentRate),
            ),
            CalcMetric(
              label: 'Налоговый вычет',
              value: formatRub(result.usableDeduction),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'Стоимость с вычетом',
              value: formatRub(result.effectiveCost),
            ),
            CalcMetric(
              label: 'Платежи в сегодняшних деньгах',
              value: formatRub(result.realPaymentsValue),
            ),
            CalcMetric(
              label: 'Ставка минус инфляция',
              value: formatPct(result.realRate),
              accent: kInflationAccent,
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
