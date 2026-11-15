import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class BondsCalculator extends StatefulWidget {
  const BondsCalculator({super.key});

  @override
  State<BondsCalculator> createState() => _BondsCalculatorState();
}

class _BondsCalculatorState extends State<BondsCalculator>
    with AutomaticKeepAliveClientMixin {
  final _face = TextEditingController(text: '1000');
  final _price = TextEditingController(text: '100');
  final _quantity = TextEditingController(text: '10');
  final _coupon = TextEditingController(text: '16');
  final _commission = TextEditingController(text: '0.3');
  final _defaultProbability = TextEditingController(text: '1');
  final _recovery = TextEditingController(text: '40');
  final _inflation = TextEditingController(text: '8');

  int _years = 3;
  int _couponsPerYear = 2;
  bool _isCorporate = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _face.dispose();
    _price.dispose();
    _quantity.dispose();
    _coupon.dispose();
    _commission.dispose();
    _defaultProbability.dispose();
    _recovery.dispose();
    _inflation.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateBond(
      faceValue: calcNumber(_face, 1000),
      pricePercent: calcNumber(_price, 100),
      quantity: calcNumber(_quantity, 10).round(),
      couponPercent: calcNumber(_coupon, 16),
      years: _years,
      couponsPerYear: _couponsPerYear,
      commissionPercent: calcNumber(_commission, 0.3),
      defaultProbabilityPercent: _isCorporate
          ? calcNumber(_defaultProbability, 1)
          : 0,
      recoveryPercent: _isCorporate ? calcNumber(_recovery, 40) : 0,
      inflationPercent: calcNumber(_inflation, 8),
      isCorporate: _isCorporate,
    );

    final mainProfit = _isCorporate
        ? result.riskAdjustedProfit
        : result.netProfit;

    return CalculatorTab(
      title: 'Облигации',
      subtitle: 'Корпоративные и муниципальные: купон, риск и налоги',
      icon: Icons.business_center_outlined,
      accent: const Color(0xFF8B5CF6),
      children: [
        CalcCard(
          title: 'Параметры облигации',
          subtitle: 'Цена указана в процентах от номинала.',
          children: [
            CalcDropdown<bool>(
              value: _isCorporate,
              label: 'Тип эмитента',
              items: const [
                DropdownMenuItem(value: true, child: Text('Корпоративная')),
                DropdownMenuItem(value: false, child: Text('Муниципальная')),
              ],
              onChanged: (value) => setState(() => _isCorporate = value),
            ),
            const SizedBox(height: 12),
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
                    label: 'Срок',
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
                    label: 'Комиссия',
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
            if (_isCorporate) ...[
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: CalcField(
                      controller: _defaultProbability,
                      label: 'Вероятность дефолта',
                      suffix: '%',
                      helper: 'За весь срок',
                      onChanged: _changed,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: CalcField(
                      controller: _recovery,
                      label: 'Возврат при дефолте',
                      suffix: '%',
                      helper: 'Доля номинала',
                      onChanged: _changed,
                    ),
                  ),
                ],
              ),
            ] else ...[
              const SizedBox(height: 12),
              Text(
                'Для муниципальных облигаций риск дефолта в расчёте '
                'не учитывается — надёжность выше, купон обычно ниже.',
                style: TextStyle(
                  fontSize: 11,
                  height: 1.35,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 14),
        ResultHero(
          eyebrow: _isCorporate
              ? 'Прибыль с учётом риска'
              : 'Прибыль после налогов',
          value: formatRub(mainProfit),
          caption: _isCorporate
              ? 'После налогов ${formatRub(result.netProfit)} · '
                    'ожидаемые потери ${formatRub(result.expectedLoss)}'
              : 'Итоговая сумма ${formatRub(result.terminalValue)} · '
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
              label: 'Прибыль после налогов',
              value: formatRub(result.netProfit),
            ),
            if (_isCorporate)
              CalcMetric(
                label: 'Ожидаемые потери',
                value: formatRub(result.expectedLoss),
                accent: SberColors.red,
              ),
            CalcMetric(
              label: 'Купон за выплату',
              value: formatRub(result.couponPerPayment),
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
