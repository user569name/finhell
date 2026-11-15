import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class CreditCalculator extends StatefulWidget {
  const CreditCalculator({super.key});

  @override
  State<CreditCalculator> createState() => _CreditCalculatorState();
}

class _CreditCalculatorState extends State<CreditCalculator>
    with AutomaticKeepAliveClientMixin {
  final _amount = TextEditingController(text: '500000');
  final _rate = TextEditingController(text: '22');
  final _commission = TextEditingController(text: '1');
  final _insurance = TextEditingController(text: '0');
  final _inflation = TextEditingController(text: '8');

  int _years = 3;
  bool _annuity = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _amount.dispose();
    _rate.dispose();
    _commission.dispose();
    _insurance.dispose();
    _inflation.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateCredit(
      amount: calcNumber(_amount, 500000),
      annualRatePercent: calcNumber(_rate, 22),
      years: _years,
      annuity: _annuity,
      commissionPercent: calcNumber(_commission, 1),
      insurancePercent: calcNumber(_insurance, 0),
      inflationPercent: calcNumber(_inflation, 8),
    );

    final heroValue = _annuity ? result.monthlyPayment : result.firstPayment;
    final heroLabel = _annuity ? 'Платёж в месяц' : 'Первый платёж';

    return CalculatorTab(
      title: 'Кредит',
      subtitle: 'Платёж, полная стоимость и реальная нагрузка',
      icon: Icons.request_quote_outlined,
      accent: kTaxAccent,
      children: [
        CalcCard(
          title: 'Параметры кредита',
          subtitle: 'Комиссия и страховка увеличивают полную стоимость.',
          children: [
            CalcField(
              controller: _amount,
              label: 'Сумма кредита',
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
                    value: _years,
                    label: 'Срок',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('1 год')),
                      DropdownMenuItem(value: 2, child: Text('2 года')),
                      DropdownMenuItem(value: 3, child: Text('3 года')),
                      DropdownMenuItem(value: 4, child: Text('4 года')),
                      DropdownMenuItem(value: 5, child: Text('5 лет')),
                      DropdownMenuItem(value: 7, child: Text('7 лет')),
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
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _commission,
                    label: 'Комиссия',
                    suffix: '%',
                    helper: 'Разово при выдаче',
                    onChanged: _changed,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _insurance,
                    label: 'Страховка',
                    suffix: '% в год',
                    helper: 'От суммы кредита',
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
          eyebrow: heroLabel,
          value: formatRub(heroValue),
          caption: _annuity
              ? 'Проценты ${formatRub(result.totalInterest)} · '
                    'всего ${formatRub(result.totalCost)}'
              : 'Последний платёж ${formatRub(result.lastPayment)} · '
                    'всего ${formatRub(result.totalCost)}',
          chips: [
            'Комиссия ${formatRub(result.commission)}',
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
              label: 'Проценты за срок',
              value: formatRub(result.totalInterest),
              accent: kTaxAccent,
            ),
            CalcMetric(label: 'Комиссия', value: formatRub(result.commission)),
            CalcMetric(label: 'Страховка', value: formatRub(result.insurance)),
            CalcMetric(
              label: 'Всего к возврату',
              value: formatRub(result.totalCost),
            ),
            CalcMetric(
              label: 'Полная переплата',
              value: formatPct(result.overpaymentRate),
            ),
            CalcMetric(
              label: 'В сегодняшних деньгах',
              value: formatRub(result.realCost),
              accent: kInflationAccent,
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
