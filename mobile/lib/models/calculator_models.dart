import 'dart:math' as math;

/// Прогрессивная шкала НДФЛ 2025+ (налоговая база за год).
const List<(double, double)> kNdflBrackets = [
  (2400000.0, 0.13),
  (5000000.0, 0.15),
  (20000000.0, 0.18),
  (50000000.0, 0.20),
  (double.infinity, 0.22),
];

double progressiveTax(double income) {
  if (income <= 0) return 0;
  var tax = 0.0;
  var lower = 0.0;
  for (final bracket in kNdflBrackets) {
    if (income <= lower) break;
    final upper = bracket.$1;
    final rate = bracket.$2;
    final taxable = math.min(income, upper) - lower;
    if (taxable > 0) tax += taxable * rate;
    lower = upper;
  }
  return tax;
}

double _growth(double annualRate, double years) =>
    math.pow(1 + annualRate, years).toDouble();

double _annualize(double totalReturn, double years) {
  if (years <= 0) return 0;
  final base = 1 + totalReturn;
  if (base <= 0) return -1;
  return math.pow(base, 1 / years).toDouble() - 1;
}

double _safeDiv(double value, double divisor) =>
    divisor == 0 ? 0 : value / divisor;

class CalcRow {
  const CalcRow(this.label, this.value, {this.percent = false, this.note});

  final String label;
  final double value;
  final bool percent;
  final String? note;
}

class TaxBreakdown {
  const TaxBreakdown({
    required this.rows,
    required this.total,
    required this.note,
    this.title = 'Налоги',
    this.isRefund = false,
  });

  final List<CalcRow> rows;
  final double total;
  final String note;
  final String title;

  /// true — это возврат налога (вычет), а не уплата.
  final bool isRefund;
}

class InflationBreakdown {
  const InflationBreakdown({
    required this.rows,
    required this.futureCost,
    required this.realValue,
    required this.loss,
    required this.realAnnualReturn,
    required this.note,
    this.benefit,
    this.realLabel = 'Реальная доходность',
  });

  final List<CalcRow> rows;
  final double futureCost;
  final double realValue;
  final double loss;
  final double realAnnualReturn;
  final String note;
  final double? benefit;
  final String realLabel;
}

// ---------------------------------------------------------------------------
// Вклад
// ---------------------------------------------------------------------------

class DepositResult {
  const DepositResult({
    required this.finalAmount,
    required this.contributed,
    required this.grossInterest,
    required this.tax,
    required this.netAmount,
    required this.totalYield,
    required this.annualYield,
    required this.realValue,
    required this.inflationLoss,
    required this.realAnnualYield,
    required this.taxes,
    required this.inflation,
  });

  final double finalAmount;
  final double contributed;
  final double grossInterest;
  final double tax;
  final double netAmount;
  final double totalYield;
  final double annualYield;
  final double realValue;
  final double inflationLoss;
  final double realAnnualYield;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

DepositResult calculateDeposit({
  required double amount,
  required double annualRatePercent,
  required int months,
  required double monthlyTopUp,
  required int capitalizationMonths,
  required double keyRatePercent,
  required double inflationPercent,
}) {
  final safeMonths = math.max(1, months);
  final years = safeMonths / 12;
  final monthlyRate = annualRatePercent / 100 / 12;
  final inflation = inflationPercent / 100;

  var balance = math.max(0.0, amount);
  var contributed = math.max(0.0, amount);
  var accrued = 0.0;
  final topUp = math.max(0.0, monthlyTopUp);

  for (var month = 1; month <= safeMonths; month++) {
    balance += topUp;
    contributed += topUp;
    final interest = balance * monthlyRate;
    accrued += interest;
    if (capitalizationMonths > 0 && month % capitalizationMonths == 0) {
      balance += accrued;
      accrued = 0;
    }
  }

  final grossInterest = capitalizationMonths > 0
      ? balance - contributed + accrued
      : accrued;
  final finalAmount = contributed + grossInterest;

  final yearsCount = math.max(1, (safeMonths / 12).ceil());
  final allowance = 1000000.0 * (keyRatePercent / 100) * yearsCount;
  final taxableTotal = math.max(0.0, grossInterest - allowance);
  final tax = progressiveTax(taxableTotal / yearsCount) * yearsCount;

  final netAmount = finalAmount - tax;
  final netProfit = grossInterest - tax;
  final totalYield = _safeDiv(netProfit, contributed);
  final annualYield = _annualize(totalYield, years);
  final factor = _growth(inflation, years);
  final realValue = _safeDiv(netAmount, factor);
  final inflationLoss = netAmount - realValue;
  final realAnnualYield = (1 + annualYield) / (1 + inflation) - 1;
  final futureCost = contributed * factor;

  final taxes = TaxBreakdown(
    total: tax,
    rows: [
      CalcRow('Проценты за срок', grossInterest),
      CalcRow('Необлагаемый лимит', allowance),
      CalcRow('Налоговая база', taxableTotal),
      CalcRow('НДФЛ с процентов', tax),
    ],
    note:
        'Лимит: 1 млн ₽ × ключевая ставка за каждый год. '
        'Ставка НДФЛ прогрессивная: 13–22%.',
  );

  final inflationBlock = InflationBreakdown(
    futureCost: futureCost,
    realValue: realValue,
    loss: inflationLoss,
    realAnnualReturn: realAnnualYield,
    rows: [
      CalcRow('Будущая цена текущих взносов', futureCost),
      CalcRow('Покупательная способность итога', realValue),
      CalcRow('Потеря покупательной способности', inflationLoss),
      CalcRow('Реальная доходность в год', realAnnualYield, percent: true),
    ],
    note:
        'Инфляция уменьшает покупательную способность итоговой суммы. '
        'Реальная доходность — это доходность сверх инфляции.',
  );

  return DepositResult(
    finalAmount: finalAmount,
    contributed: contributed,
    grossInterest: grossInterest,
    tax: tax,
    netAmount: netAmount,
    totalYield: totalYield,
    annualYield: annualYield,
    realValue: realValue,
    inflationLoss: inflationLoss,
    realAnnualYield: realAnnualYield,
    taxes: taxes,
    inflation: inflationBlock,
  );
}

// ---------------------------------------------------------------------------
// ОФЗ и облигации
// ---------------------------------------------------------------------------

class BondResult {
  const BondResult({
    required this.invested,
    required this.commission,
    required this.coupons,
    required this.priceGain,
    required this.grossProfit,
    required this.tax,
    required this.netProfit,
    required this.expectedLoss,
    required this.riskAdjustedProfit,
    required this.terminalValue,
    required this.couponPerPayment,
    required this.currentYield,
    required this.yieldToMaturity,
    required this.totalReturn,
    required this.annualReturn,
    required this.realValue,
    required this.inflationLoss,
    required this.realAnnualReturn,
    required this.taxes,
    required this.inflation,
  });

  final double invested;
  final double commission;
  final double coupons;
  final double priceGain;
  final double grossProfit;
  final double tax;
  final double netProfit;
  final double expectedLoss;
  final double riskAdjustedProfit;
  final double terminalValue;
  final double couponPerPayment;
  final double currentYield;
  final double yieldToMaturity;
  final double totalReturn;
  final double annualReturn;
  final double realValue;
  final double inflationLoss;
  final double realAnnualReturn;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

BondResult calculateBond({
  required double faceValue,
  required double pricePercent,
  required int quantity,
  required double couponPercent,
  required int years,
  required int couponsPerYear,
  required double commissionPercent,
  required double defaultProbabilityPercent,
  required double recoveryPercent,
  required double inflationPercent,
  required bool isCorporate,
}) {
  final safeYears = math.max(1, years);
  final count = math.max(1, quantity);
  final inflation = inflationPercent / 100;
  final annualCoupon = math.max(0.0, faceValue) * (couponPercent / 100) * count;
  final invested = math.max(0.0, faceValue) * (pricePercent / 100) * count;
  final commission = invested * (commissionPercent / 100);
  final totalInvested = invested + commission;
  final coupons = annualCoupon * safeYears;
  final redemption = math.max(0.0, faceValue) * count;
  final priceGain = redemption - invested;
  final grossProfit = coupons + priceGain - commission;

  final couponTax = progressiveTax(annualCoupon) * safeYears;
  final gainTax = math.max(0.0, priceGain) * 0.13;
  final totalTax = couponTax + gainTax;
  final netProfit = grossProfit - totalTax;

  final expectedLoss = isCorporate
      ? redemption *
            (defaultProbabilityPercent / 100) *
            (1 - recoveryPercent / 100)
      : 0.0;
  final riskAdjustedProfit = netProfit - expectedLoss;
  final terminalValue = totalInvested + netProfit;

  final couponPerPayment = _safeDiv(
    annualCoupon,
    math.max(1, couponsPerYear).toDouble(),
  );
  final currentYield = _safeDiv(annualCoupon, totalInvested);
  final averageInvested = (totalInvested + redemption) / 2;
  final yieldToMaturity = _safeDiv(
    annualCoupon + priceGain / safeYears,
    averageInvested,
  );
  final totalReturn = _safeDiv(netProfit, totalInvested);
  final annualReturn = _annualize(totalReturn, safeYears.toDouble());
  final factor = _growth(inflation, safeYears.toDouble());
  final realValue = _safeDiv(terminalValue, factor);
  final inflationLoss = terminalValue - realValue;
  final realAnnualReturn = (1 + annualReturn) / (1 + inflation) - 1;
  final futureCost = totalInvested * factor;

  final taxes = TaxBreakdown(
    total: totalTax,
    rows: [
      CalcRow('НДФЛ с купонов', couponTax),
      CalcRow('НДФЛ с прироста цены', gainTax),
      CalcRow('Купонный доход за год', annualCoupon),
    ],
    note: isCorporate
        ? 'Купон и положительная разница цены облагаются НДФЛ 13–22%. '
              'Риск дефолта показан отдельно и не входит в налоги.'
        : 'Купоны ОФЗ и положительный доход от продажи облагаются НДФЛ. '
              'Убыток от продажи может уменьшить базу при наличии других доходов.',
  );

  final inflationBlock = InflationBreakdown(
    futureCost: futureCost,
    realValue: realValue,
    loss: inflationLoss,
    realAnnualReturn: realAnnualReturn,
    rows: [
      CalcRow('Будущая цена вложенной суммы', futureCost),
      CalcRow('Покупательная способность итога', realValue),
      CalcRow('Потеря покупательной способности', inflationLoss),
      CalcRow('Реальная доходность в год', realAnnualReturn, percent: true),
    ],
    note:
        'Инфляция сравнивается с итоговой суммой после налогов. '
        'Купонные выплаты в течение срока здесь не реинвестируются.',
  );

  return BondResult(
    invested: totalInvested,
    commission: commission,
    coupons: coupons,
    priceGain: priceGain,
    grossProfit: grossProfit,
    tax: totalTax,
    netProfit: netProfit,
    expectedLoss: expectedLoss,
    riskAdjustedProfit: riskAdjustedProfit,
    terminalValue: terminalValue,
    couponPerPayment: couponPerPayment,
    currentYield: currentYield,
    yieldToMaturity: yieldToMaturity,
    totalReturn: totalReturn,
    annualReturn: annualReturn,
    realValue: realValue,
    inflationLoss: inflationLoss,
    realAnnualReturn: realAnnualReturn,
    taxes: taxes,
    inflation: inflationBlock,
  );
}

// ---------------------------------------------------------------------------
// Недвижимость под аренду
// ---------------------------------------------------------------------------

class RealEstateResult {
  const RealEstateResult({
    required this.invested,
    required this.totalRent,
    required this.expenses,
    required this.propertyTax,
    required this.rentTax,
    required this.salePrice,
    required this.saleCosts,
    required this.saleTax,
    required this.netCashFlow,
    required this.totalProfit,
    required this.terminalValue,
    required this.totalReturn,
    required this.annualReturn,
    required this.realValue,
    required this.inflationLoss,
    required this.realAnnualReturn,
    required this.taxes,
    required this.inflation,
  });

  final double invested;
  final double totalRent;
  final double expenses;
  final double propertyTax;
  final double rentTax;
  final double salePrice;
  final double saleCosts;
  final double saleTax;
  final double netCashFlow;
  final double totalProfit;
  final double terminalValue;
  final double totalReturn;
  final double annualReturn;
  final double realValue;
  final double inflationLoss;
  final double realAnnualReturn;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

RealEstateResult calculateRealEstate({
  required double price,
  required double monthlyRent,
  required double vacancyPercent,
  required double monthlyExpenses,
  required double annualGrowthPercent,
  required int years,
  required double purchaseCostsPercent,
  required double saleCostsPercent,
  required String rentTaxMode,
  required double propertyTaxPercent,
  required double inflationPercent,
}) {
  final safeYears = math.max(1, years);
  final safePrice = math.max(0.0, price);
  final inflation = inflationPercent / 100;

  final purchaseCosts = safePrice * (purchaseCostsPercent / 100);
  final invested = safePrice + purchaseCosts;
  final annualRentGross = math.max(0.0, monthlyRent) * 12;
  final effectiveAnnualRent = annualRentGross * (1 - vacancyPercent / 100);
  final totalRent = effectiveAnnualRent * safeYears;
  final expenses = math.max(0.0, monthlyExpenses) * 12 * safeYears;

  final rentTax = rentTaxMode == 'self'
      ? totalRent * 0.04
      : rentTaxMode == 'none'
      ? 0.0
      : progressiveTax(effectiveAnnualRent) * safeYears;
  final propertyTax = safePrice * (propertyTaxPercent / 100) * safeYears;

  final salePrice =
      safePrice * _growth(annualGrowthPercent / 100, safeYears.toDouble());
  final saleCosts = salePrice * (saleCostsPercent / 100);
  final saleGain = math.max(0.0, salePrice - safePrice - purchaseCosts);
  final saleTax = safeYears < 5 ? saleGain * 0.13 : 0.0;

  final totalTax = rentTax + propertyTax + saleTax;
  final netCashFlow = totalRent - expenses - propertyTax - rentTax;
  final terminalValue = netCashFlow + salePrice - saleCosts - saleTax;
  final totalProfit = terminalValue - invested;
  final totalReturn = _safeDiv(totalProfit, invested);
  final annualReturn = _annualize(totalReturn, safeYears.toDouble());

  final factor = _growth(inflation, safeYears.toDouble());
  final realValue = _safeDiv(terminalValue, factor);
  final inflationLoss = terminalValue - realValue;
  final realAnnualReturn = (1 + annualReturn) / (1 + inflation) - 1;
  final futureCost = invested * factor;

  final taxes = TaxBreakdown(
    total: totalTax,
    rows: [
      CalcRow('НДФЛ с аренды', rentTax),
      CalcRow('Налог на имущество', propertyTax),
      CalcRow('Налог с продажи', saleTax),
    ],
    note:
        'Аренда: НДФЛ 13–22% или 4% для самозанятого. '
        'При владении 5+ лет налог с продажи обычно не возникает '
        '(в ряде случаев — от 3 лет). Налог на имущество — оценка.',
  );

  final inflationBlock = InflationBreakdown(
    futureCost: futureCost,
    realValue: realValue,
    loss: inflationLoss,
    realAnnualReturn: realAnnualReturn,
    rows: [
      CalcRow('Будущая цена вложений', futureCost),
      CalcRow('Покупательная способность итога', realValue),
      CalcRow('Потеря покупательной способности', inflationLoss),
      CalcRow('Реальная доходность в год', realAnnualReturn, percent: true),
    ],
    note:
        'Учитывается рост цены объекта и инфляция. '
        'Арендные платежи в модели не индексируются.',
  );

  return RealEstateResult(
    invested: invested,
    totalRent: totalRent,
    expenses: expenses,
    propertyTax: propertyTax,
    rentTax: rentTax,
    salePrice: salePrice,
    saleCosts: saleCosts,
    saleTax: saleTax,
    netCashFlow: netCashFlow,
    totalProfit: totalProfit,
    terminalValue: terminalValue,
    totalReturn: totalReturn,
    annualReturn: annualReturn,
    realValue: realValue,
    inflationLoss: inflationLoss,
    realAnnualReturn: realAnnualReturn,
    taxes: taxes,
    inflation: inflationBlock,
  );
}

// ---------------------------------------------------------------------------
// Ипотека
// ---------------------------------------------------------------------------

class MortgageResult {
  const MortgageResult({
    required this.principal,
    required this.monthlyPayment,
    required this.firstPayment,
    required this.lastPayment,
    required this.totalPayments,
    required this.totalInterest,
    required this.overpaymentRate,
    required this.propertyDeduction,
    required this.interestDeduction,
    required this.ndflPaid,
    required this.usableDeduction,
    required this.effectiveCost,
    required this.realPaymentsValue,
    required this.inflationSaving,
    required this.realOverpayment,
    required this.realRate,
    required this.taxes,
    required this.inflation,
  });

  final double principal;
  final double monthlyPayment;
  final double firstPayment;
  final double lastPayment;
  final double totalPayments;
  final double totalInterest;
  final double overpaymentRate;
  final double propertyDeduction;
  final double interestDeduction;
  final double ndflPaid;
  final double usableDeduction;
  final double effectiveCost;
  final double realPaymentsValue;
  final double inflationSaving;
  final double realOverpayment;
  final double realRate;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

MortgageResult calculateMortgage({
  required double price,
  required double downPayment,
  required double annualRatePercent,
  required int years,
  required bool annuity,
  required double inflationPercent,
  required double annualIncome,
  required bool useDeductions,
}) {
  final safeYears = math.max(1, years);
  final months = safeYears * 12;
  final safePrice = math.max(0.0, price);
  final principal = math.max(0.0, safePrice - math.max(0.0, downPayment));
  final monthlyRate = annualRatePercent / 100 / 12;
  final inflation = inflationPercent / 100;

  double payment;
  double firstPayment;
  double lastPayment;
  double totalInterest;

  if (principal <= 0) {
    payment = 0;
    firstPayment = 0;
    lastPayment = 0;
    totalInterest = 0;
  } else if (annuity) {
    if (monthlyRate <= 0) {
      payment = principal / months;
    } else {
      final factor = math.pow(1 + monthlyRate, months).toDouble();
      payment = principal * monthlyRate * factor / (factor - 1);
    }
    firstPayment = payment;
    lastPayment = payment;
    totalInterest = payment * months - principal;
  } else {
    final principalPart = principal / months;
    firstPayment = principalPart + principal * monthlyRate;
    lastPayment = principalPart + principalPart * monthlyRate;
    totalInterest = principal * monthlyRate * (months + 1) / 2;
    payment = firstPayment;
  }

  final totalPayments = principal + totalInterest;
  final overpaymentRate = _safeDiv(totalInterest, principal);

  final propertyDeduction = math.min(safePrice, 2000000.0) * 0.13;
  final interestDeduction = math.min(totalInterest, 3000000.0) * 0.13;
  final potentialDeduction = propertyDeduction + interestDeduction;
  final annualNdfl = progressiveTax(math.max(0.0, annualIncome));
  final ndflPaid = annualNdfl * safeYears;
  final usableDeduction = useDeductions
      ? math.min(potentialDeduction, ndflPaid)
      : 0.0;
  final effectiveCost = totalPayments - usableDeduction;

  final monthlyInflation = math.pow(1 + inflation, 1 / 12).toDouble() - 1;
  var realPaymentsValue = 0.0;
  if (principal > 0) {
    if (annuity) {
      realPaymentsValue = monthlyInflation == 0
          ? payment * months
          : payment *
                (1 - math.pow(1 + monthlyInflation, -months).toDouble()) /
                monthlyInflation;
    } else {
      final principalPart = principal / months;
      var balance = principal;
      for (var month = 1; month <= months; month++) {
        final interest = balance * monthlyRate;
        final currentPayment = principalPart + interest;
        realPaymentsValue +=
            currentPayment / math.pow(1 + monthlyInflation, month).toDouble();
        balance -= principalPart;
      }
    }
  }

  final inflationSaving = totalPayments - realPaymentsValue;
  final realOverpayment = realPaymentsValue - principal;
  final realRate = (1 + annualRatePercent / 100) / (1 + inflation) - 1;

  final taxes = TaxBreakdown(
    total: usableDeduction,
    isRefund: true,
    title: 'Налоги и вычеты',
    rows: useDeductions
        ? [
            CalcRow('Имущественный вычет (до 2 млн ₽)', propertyDeduction),
            CalcRow('Вычет по процентам (до 3 млн ₽)', interestDeduction),
            CalcRow('Уплаченный НДФЛ за срок', ndflPaid),
            CalcRow('К возврату с учётом НДФЛ', usableDeduction),
          ]
        : [
            CalcRow('Потенциальный вычет', potentialDeduction),
            CalcRow('Вычеты отключены', 0),
          ],
    note: useDeductions
        ? 'Вычет — это возврат ранее уплаченного НДФЛ, а не уменьшение '
              'ежемесячного платежа. Лимиты: 2 млн ₽ по покупке и 3 млн ₽ '
              'по ипотечным процентам.'
        : 'Вычеты отключены в расчёте. Потенциально можно вернуть '
              '13% от стоимости жилья до 2 млн ₽ и 13% от процентов до 3 млн ₽.',
  );

  final factor = _growth(inflation, safeYears.toDouble());
  final realValue = _safeDiv(totalPayments, factor);
  final inflationLoss = totalPayments - realValue;

  final inflationBlock = InflationBreakdown(
    futureCost: totalPayments,
    realValue: realValue,
    loss: inflationLoss,
    realAnnualReturn: realRate,
    benefit: inflationSaving,
    realLabel: 'Реальная ставка',
    rows: [
      CalcRow('Всего платежей', totalPayments),
      CalcRow('В сегодняшних деньгах', realPaymentsValue),
      CalcRow('Обесценивание платежей инфляцией', inflationSaving),
      CalcRow('Реальная переплата', realOverpayment),
      CalcRow('Ставка минус инфляция', realRate, percent: true),
    ],
    note:
        'Инфляция снижает реальную нагрузку на платежи. '
        'Стоимость платежей в сегодняшних деньгах рассчитана '
        'по месячной инфляции.',
  );

  return MortgageResult(
    principal: principal,
    monthlyPayment: payment,
    firstPayment: firstPayment,
    lastPayment: lastPayment,
    totalPayments: totalPayments,
    totalInterest: totalInterest,
    overpaymentRate: overpaymentRate,
    propertyDeduction: propertyDeduction,
    interestDeduction: interestDeduction,
    ndflPaid: ndflPaid,
    usableDeduction: usableDeduction,
    effectiveCost: effectiveCost,
    realPaymentsValue: realPaymentsValue,
    inflationSaving: inflationSaving,
    realOverpayment: realOverpayment,
    realRate: realRate,
    taxes: taxes,
    inflation: inflationBlock,
  );
}

// ---------------------------------------------------------------------------
// Потребительский кредит
// ---------------------------------------------------------------------------

class CreditResult {
  const CreditResult({
    required this.principal,
    required this.monthlyPayment,
    required this.firstPayment,
    required this.lastPayment,
    required this.totalPayments,
    required this.totalInterest,
    required this.commission,
    required this.insurance,
    required this.totalCost,
    required this.overpaymentRate,
    required this.realCost,
    required this.inflationSaving,
    required this.realOverpayment,
    required this.realRate,
    required this.taxes,
    required this.inflation,
  });

  final double principal;
  final double monthlyPayment;
  final double firstPayment;
  final double lastPayment;
  final double totalPayments;
  final double totalInterest;
  final double commission;
  final double insurance;
  final double totalCost;
  final double overpaymentRate;
  final double realCost;
  final double inflationSaving;
  final double realOverpayment;
  final double realRate;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

CreditResult calculateCredit({
  required double amount,
  required double annualRatePercent,
  required int years,
  required bool annuity,
  required double commissionPercent,
  required double insurancePercent,
  required double inflationPercent,
}) {
  final safeYears = math.max(1, years);
  final months = safeYears * 12;
  final principal = math.max(0.0, amount);
  final monthlyRate = annualRatePercent / 100 / 12;
  final inflation = inflationPercent / 100;

  double payment;
  double firstPayment;
  double lastPayment;
  double totalInterest;

  if (principal <= 0) {
    payment = 0;
    firstPayment = 0;
    lastPayment = 0;
    totalInterest = 0;
  } else if (annuity) {
    if (monthlyRate <= 0) {
      payment = principal / months;
    } else {
      final factor = math.pow(1 + monthlyRate, months).toDouble();
      payment = principal * monthlyRate * factor / (factor - 1);
    }
    firstPayment = payment;
    lastPayment = payment;
    totalInterest = payment * months - principal;
  } else {
    final principalPart = principal / months;
    firstPayment = principalPart + principal * monthlyRate;
    lastPayment = principalPart + principalPart * monthlyRate;
    totalInterest = principal * monthlyRate * (months + 1) / 2;
    payment = firstPayment;
  }

  final totalPayments = principal + totalInterest;
  final commission = principal * (commissionPercent / 100);
  final insurance = principal * (insurancePercent / 100) * safeYears;
  final totalCost = totalPayments + commission + insurance;
  final overpaymentRate = _safeDiv(totalCost - principal, principal);

  final monthlyInflation = math.pow(1 + inflation, 1 / 12).toDouble() - 1;
  final insuranceMonthly = principal * (insurancePercent / 100) / 12;
  var realCost = commission;
  if (principal > 0) {
    if (annuity) {
      final stream = payment + insuranceMonthly;
      realCost += monthlyInflation == 0
          ? stream * months
          : stream *
                (1 - math.pow(1 + monthlyInflation, -months).toDouble()) /
                monthlyInflation;
    } else {
      final principalPart = principal / months;
      var balance = principal;
      for (var month = 1; month <= months; month++) {
        final interest = balance * monthlyRate;
        final currentPayment = principalPart + interest + insuranceMonthly;
        realCost +=
            currentPayment / math.pow(1 + monthlyInflation, month).toDouble();
        balance -= principalPart;
      }
    }
  }

  final inflationSaving = totalCost - realCost;
  final realOverpayment = realCost - principal;
  final realRate = (1 + annualRatePercent / 100) / (1 + inflation) - 1;

  final taxes = TaxBreakdown(
    total: 0,
    rows: [
      const CalcRow('НДФЛ с кредита', 0),
      const CalcRow(
        'Вычет по процентам',
        0,
        note: 'Предусмотрен только для ипотеки',
      ),
    ],
    note:
        'Потребительский кредит не облагается НДФЛ: это не доход. '
        'Проценты, комиссия и страховка не уменьшают налоговую базу. '
        'Вычет по процентам доступен только по ипотеке.',
  );

  final inflationBlock = InflationBreakdown(
    futureCost: totalCost,
    realValue: realCost,
    loss: inflationSaving,
    realAnnualReturn: realRate,
    benefit: inflationSaving,
    realLabel: 'Реальная ставка',
    rows: [
      CalcRow('Всего к возврату с комиссией', totalCost),
      CalcRow('В сегодняшних деньгах', realCost),
      CalcRow('Обесценивание платежей инфляцией', inflationSaving),
      CalcRow('Реальная переплата', realOverpayment),
      CalcRow('Ставка минус инфляция', realRate, percent: true),
    ],
    note:
        'Инфляция снижает реальную нагрузку на платежи. '
        'Стоимость в сегодняшних деньгах рассчитана по месячной инфляции '
        'с учётом комиссии и страховки.',
  );

  return CreditResult(
    principal: principal,
    monthlyPayment: payment,
    firstPayment: firstPayment,
    lastPayment: lastPayment,
    totalPayments: totalPayments,
    totalInterest: totalInterest,
    commission: commission,
    insurance: insurance,
    totalCost: totalCost,
    overpaymentRate: overpaymentRate,
    realCost: realCost,
    inflationSaving: inflationSaving,
    realOverpayment: realOverpayment,
    realRate: realRate,
    taxes: taxes,
    inflation: inflationBlock,
  );
}

// ---------------------------------------------------------------------------
// Инфляция
// ---------------------------------------------------------------------------

class InflationResult {
  const InflationResult({
    required this.futureCost,
    required this.purchasingPower,
    required this.loss,
    required this.requiredNominal,
    required this.requiredPreTax,
    required this.nominalCapital,
    required this.realCapital,
    required this.afterTaxReal,
    required this.realReturn,
    required this.tax,
    required this.taxes,
    required this.inflation,
  });

  final double futureCost;
  final double purchasingPower;
  final double loss;
  final double requiredNominal;
  final double requiredPreTax;
  final double nominalCapital;
  final double realCapital;
  final double afterTaxReal;
  final double realReturn;
  final double tax;
  final TaxBreakdown taxes;
  final InflationBreakdown inflation;
}

InflationResult calculateInflation({
  required double amount,
  required double inflationPercent,
  required int years,
  required double depositRatePercent,
  required double keyRatePercent,
}) {
  final safeYears = math.max(1, years);
  final safeAmount = math.max(0.0, amount);
  final inflation = inflationPercent / 100;
  final factor = _growth(inflation, safeYears.toDouble());
  final futureCost = safeAmount * factor;
  final purchasingPower = _safeDiv(safeAmount, factor);
  final loss = safeAmount - purchasingPower;
  final requiredPreTax = (1 + inflation) / (1 - 0.13) - 1;

  final hasIncome = depositRatePercent > 0;
  final nominalCapital = hasIncome
      ? safeAmount * _growth(depositRatePercent / 100, safeYears.toDouble())
      : safeAmount;
  final interest = nominalCapital - safeAmount;
  final allowance = 1000000.0 * (keyRatePercent / 100) * safeYears;
  final taxable = math.max(0.0, interest - allowance);
  final tax = hasIncome ? progressiveTax(taxable / safeYears) * safeYears : 0.0;
  final afterTax = nominalCapital - tax;
  final afterTaxReal = _safeDiv(afterTax, factor);
  final realCapital = _safeDiv(nominalCapital, factor);
  final afterTaxAnnual = _annualize(
    _safeDiv(afterTax - safeAmount, safeAmount),
    safeYears.toDouble(),
  );
  final realReturn = hasIncome
      ? (1 + afterTaxAnnual) / (1 + inflation) - 1
      : (1 / (1 + inflation)) - 1;

  final taxes = TaxBreakdown(
    total: tax,
    rows: hasIncome
        ? [
            CalcRow('Проценты за срок', interest),
            CalcRow('Необлагаемый лимит', allowance),
            CalcRow('Налоговая база', taxable),
            CalcRow('НДФЛ с процентов', tax),
          ]
        : [CalcRow('Доход от вложения', 0), CalcRow('Налоговая база', 0)],
    note: hasIncome
        ? 'НДФЛ с процентов: 13–22% с суммы сверх лимита '
              '1 млн ₽ × ключевая ставка за каждый год.'
        : 'Укажите доходность вложения, чтобы рассчитать налог с процентов.',
  );

  final inflationBlock = InflationBreakdown(
    futureCost: futureCost,
    realValue: purchasingPower,
    loss: loss,
    realAnnualReturn: realReturn,
    rows: [
      CalcRow('Будущая цена корзины', futureCost),
      CalcRow('Покупательная способность суммы', purchasingPower),
      CalcRow('Потеря покупательной способности', loss),
      CalcRow('Инфляция за срок', factor - 1, percent: true),
      if (hasIncome)
        CalcRow('Реальная доходность вложения', realReturn, percent: true),
      CalcRow('Нужная доходность до налога', requiredPreTax, percent: true),
    ],
    note:
        'Чтобы сохранить покупательную способность после НДФЛ 13%, '
        'нужна доходность выше инфляции. Сумма «под матрасом» '
        'теряет покупательную способность.',
  );

  return InflationResult(
    futureCost: futureCost,
    purchasingPower: purchasingPower,
    loss: loss,
    requiredNominal: inflation,
    requiredPreTax: requiredPreTax,
    nominalCapital: nominalCapital,
    realCapital: realCapital,
    afterTaxReal: afterTaxReal,
    realReturn: realReturn,
    tax: tax,
    taxes: taxes,
    inflation: inflationBlock,
  );
}
