import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class OfzCalculator extends StatefulWidget {
  const OfzCalculator({super.key});

  @override
  State<OfzCalculator> createState() => _OfzCalculatorState();
}

class _OfzCalculatorState extends State<OfzCalculator>
    with AutomaticKeepAliveClientMixin {
  final _face = TextEditingController(text: '1000');
  final _price = TextEditingController(text: '95');
  final _quantity = TextEditingController(text: '10');
  final _coupon = TextEditingController(text: '12');
  final _commission = TextEditingController(text: '0.3');
  final _inflation = TextEditingController(text: '8');

  int _years = 3;
  int _couponsPerYear = 2;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _face.dispose();
    _price.dispose();
    _quantity.dispose();
    _coupon.dispose();
    _commission.dispose();
    _inflation.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateBond(
      faceValue: calcNumber(_face, 1000),
      pricePercent: calcNumber(_price, 95),
      quantity: calcNumber(_quantity, 10).round(),
      couponPercent: calcNumber(_coupon, 12),
      years: _years,
      couponsPerYear: _couponsPerYear,
      commissionPercent: calcNumber(_commission, 0.3),
      defaultProbabilityPercent: 0,
      recoveryPercent: 0,
      inflationPercent: calcNumber(_inflation, 8),
      isCorporate: false,
    );

    return CalculatorTab(
      title: 'ОФЗ',
      subtitle: 'Купонный доход, цена покупки и налоги',
      icon: Icons.account_balance_outlined,
      accent: SberColors.greenDark,
      children: [
        CalcCard(
          title: 'Параметры ОФЗ',
          subtitle: 'Цена указана в процентах от номинала.',
          children: [
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _face,
                    label: 'Номинал',
                    suffix: '₽',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _price,
                    label: 'Цена',
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
                  child: CalcField(
                    controller: _quantity,
                    label: 'Количество',
                    suffix: 'шт.',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _coupon,
                    label: 'Купон в год',
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
                    label: 'Срок до погашения',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('1 год')),
                      DropdownMenuItem(value: 2, child: Text('2 года')),
                      DropdownMenuItem(value: 3, child: Text('3 года')),
                      DropdownMenuItem(value: 5, child: Text('5 лет')),
                      DropdownMenuItem(value: 7, child: Text('7 лет')),
                      DropdownMenuItem(value: 10, child: Text('10 лет')),
                    ],
                    onChanged: (value) => setState(() => _years = value),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<int>(
                    value: _couponsPerYear,
                    label: 'Купонов в год',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('1')),
                      DropdownMenuItem(value: 2, child: Text('2')),
                      DropdownMenuItem(value: 4, child: Text('4')),
                      DropdownMenuItem(value: 12, child: Text('12')),
                    ],
                    onChanged: (value) =>
                        setState(() => _couponsPerYear = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _commission,
                    label: 'Комиссия брокера',
                    suffix: '%',
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
          eyebrow: 'Прибыль после налогов',
          value: formatRub(result.netProfit),
          caption:
              'Итоговая сумма ${formatRub(result.terminalValue)} · '
              'вложено ${formatRub(result.invested)}',
          chips: [
            'Доходность к погашению ${formatPct(result.yieldToMaturity)}',
            'Купон в год ${formatRub(result.coupons / _years)}',
          ],
        ),
        const SizedBox(height: 12),
        MetricGrid(
          metrics: [
            CalcMetric(
              label: 'Вложено с комиссией',
              value: formatRub(result.invested),
            ),
            CalcMetric(
              label: 'Купоны за срок',
              value: formatRub(result.coupons),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'Прирост цены',
              value: formatRub(result.priceGain),
            ),
            CalcMetric(
              label: 'Налог',
              value: formatRub(result.tax),
              accent: kTaxAccent,
            ),
            CalcMetric(
              label: 'Итоговая сумма',
              value: formatRub(result.terminalValue),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'Купон за выплату',
              value: formatRub(result.couponPerPayment),
            ),
            CalcMetric(
              label: 'Текущая доходность',
              value: formatPct(result.currentYield),
            ),
            CalcMetric(
              label: 'Доходность в год',
              value: formatPct(result.annualReturn),
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
