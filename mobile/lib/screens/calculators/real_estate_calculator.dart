import 'package:flutter/material.dart';

import '../../models/calculator_models.dart';
import '../../theme/sber_theme.dart';
import '../../widgets/calculator_widgets.dart';

class RealEstateCalculator extends StatefulWidget {
  const RealEstateCalculator({super.key});

  @override
  State<RealEstateCalculator> createState() => _RealEstateCalculatorState();
}

class _RealEstateCalculatorState extends State<RealEstateCalculator>
    with AutomaticKeepAliveClientMixin {
  final _price = TextEditingController(text: '8000000');
  final _rent = TextEditingController(text: '45000');
  final _vacancy = TextEditingController(text: '8');
  final _expenses = TextEditingController(text: '8000');
  final _growth = TextEditingController(text: '6');
  final _purchaseCosts = TextEditingController(text: '2');
  final _saleCosts = TextEditingController(text: '2');
  final _propertyTax = TextEditingController(text: '0.1');
  final _inflation = TextEditingController(text: '8');

  int _years = 5;
  String _rentTaxMode = 'ndfl';

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _price.dispose();
    _rent.dispose();
    _vacancy.dispose();
    _expenses.dispose();
    _growth.dispose();
    _purchaseCosts.dispose();
    _saleCosts.dispose();
    _propertyTax.dispose();
    _inflation.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final result = calculateRealEstate(
      price: calcNumber(_price, 8000000),
      monthlyRent: calcNumber(_rent, 45000),
      vacancyPercent: calcNumber(_vacancy, 8),
      monthlyExpenses: calcNumber(_expenses, 8000),
      annualGrowthPercent: calcNumber(_growth, 6),
      years: _years,
      purchaseCostsPercent: calcNumber(_purchaseCosts, 2),
      saleCostsPercent: calcNumber(_saleCosts, 2),
      rentTaxMode: _rentTaxMode,
      propertyTaxPercent: calcNumber(_propertyTax, 0.1),
      inflationPercent: calcNumber(_inflation, 8),
    );

    return CalculatorTab(
      title: 'Недвижимость',
      subtitle: 'Аренда, рост цены, расходы и налоги',
      icon: Icons.home_work_outlined,
      accent: const Color(0xFFB07A52),
      children: [
        CalcCard(
          title: 'Параметры объекта',
          subtitle: 'Аренда указана до вычета простоя и налогов.',
          children: [
            CalcField(
              controller: _price,
              label: 'Стоимость объекта',
              suffix: '₽',
              onChanged: _changed,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _rent,
                    label: 'Аренда в месяц',
                    suffix: '₽',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _vacancy,
                    label: 'Простой',
                    suffix: '%',
                    helper: 'Доля года без арендатора',
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
                    controller: _expenses,
                    label: 'Расходы в месяц',
                    suffix: '₽',
                    helper: 'ЖКХ, ремонт, страховка',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _growth,
                    label: 'Рост цены в год',
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
                    label: 'Срок владения',
                    items: const [
                      DropdownMenuItem(value: 1, child: Text('1 год')),
                      DropdownMenuItem(value: 3, child: Text('3 года')),
                      DropdownMenuItem(value: 5, child: Text('5 лет')),
                      DropdownMenuItem(value: 7, child: Text('7 лет')),
                      DropdownMenuItem(value: 10, child: Text('10 лет')),
                      DropdownMenuItem(value: 15, child: Text('15 лет')),
                    ],
                    onChanged: (value) => setState(() => _years = value),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcDropdown<String>(
                    value: _rentTaxMode,
                    label: 'Налог с аренды',
                    items: const [
                      DropdownMenuItem(
                        value: 'ndfl',
                        child: Text('НДФЛ 13–22%'),
                      ),
                      DropdownMenuItem(
                        value: 'self',
                        child: Text('Самозанятый 4%'),
                      ),
                      DropdownMenuItem(
                        value: 'none',
                        child: Text('Без налога'),
                      ),
                    ],
                    onChanged: (value) => setState(() => _rentTaxMode = value),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: CalcField(
                    controller: _purchaseCosts,
                    label: 'Расходы покупки',
                    suffix: '%',
                    onChanged: _changed,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: CalcField(
                    controller: _saleCosts,
                    label: 'Расходы продажи',
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
                    controller: _propertyTax,
                    label: 'Налог на имущество',
                    suffix: '% в год',
                    helper: 'От стоимости объекта',
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
          value: formatRub(result.totalProfit),
          caption:
              'Итоговая сумма ${formatRub(result.terminalValue)} · '
              'вложено ${formatRub(result.invested)}',
          chips: [
            'Доходность ${formatPct(result.annualReturn)} в год',
            'Аренда за срок ${formatRub(result.totalRent)}',
          ],
        ),
        const SizedBox(height: 12),
        MetricGrid(
          metrics: [
            CalcMetric(
              label: 'Вложено с расходами',
              value: formatRub(result.invested),
            ),
            CalcMetric(
              label: 'Аренда за срок',
              value: formatRub(result.totalRent),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'Расходы за срок',
              value: formatRub(result.expenses),
            ),
            CalcMetric(
              label: 'Цена продажи',
              value: formatRub(result.salePrice),
            ),
            CalcMetric(
              label: 'Налоги',
              value: formatRub(result.taxes.total),
              accent: kTaxAccent,
            ),
            CalcMetric(
              label: 'Прибыль после налогов',
              value: formatRub(result.totalProfit),
              accent: SberColors.green,
            ),
            CalcMetric(
              label: 'Чистый поток аренды',
              value: formatRub(result.netCashFlow),
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
