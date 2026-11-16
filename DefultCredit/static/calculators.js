(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const nf0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });

  const HTML_ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
  }

  function num(value, fallback = 0) {
    if (typeof value === "number") {
      return Number.isFinite(value) ? value : fallback;
    }
    const raw = String(value ?? "")
      .trim()
      .replace(/\s+/g, "")
      .replace(/\u00A0/g, "")
      .replace(",", ".");
    if (raw === "") return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function rub(value) {
    const safe = Number.isFinite(value) ? value : 0;
    const sign = safe < 0 ? "−" : "";
    return `${sign}${nf0.format(Math.abs(Math.round(safe)))} ₽`;
  }

  function pct(value, digits = 1) {
    const safe = Number.isFinite(value) ? value * 100 : 0;
    const sign = safe < 0 ? "−" : "";
    const formatted =
      digits === 1
        ? nf1.format(Math.abs(safe))
        : Math.abs(safe).toFixed(digits).replace(".", ",");
    return `${sign}${formatted}%`;
  }

  function signedLoss(value) {
    if (value >= 0) return `−${rub(value)}`;
    return `+${rub(-value)}`;
  }

  function formatYears(value) {
    const years = Math.max(1, Math.round(value));
    const mod10 = years % 10;
    const mod100 = years % 100;
    if (mod10 === 1 && mod100 !== 11) return `${years} год`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
      return `${years} года`;
    }
    return `${years} лет`;
  }

  function growth(annualRate, years) {
    return Math.pow(1 + annualRate, years);
  }

  function annualize(totalReturn, years) {
    if (years <= 0) return 0;
    const base = 1 + totalReturn;
    if (base <= 0) return -1;
    return Math.pow(base, 1 / years) - 1;
  }

  function safeDiv(value, divisor) {
    return divisor === 0 ? 0 : value / divisor;
  }

  const NDFL_BRACKETS = [
    [2400000, 0.13],
    [5000000, 0.15],
    [20000000, 0.18],
    [50000000, 0.2],
    [Infinity, 0.22],
  ];

  function progressiveTax(income) {
    if (!(income > 0)) return 0;
    let tax = 0;
    let lower = 0;
    for (const [upper, rate] of NDFL_BRACKETS) {
      if (income <= lower) break;
      const taxable = Math.min(income, upper) - lower;
      if (taxable > 0) tax += taxable * rate;
      lower = upper;
    }
    return tax;
  }

  function row(label, value, options = {}) {
    return {
      label,
      value,
      percent: Boolean(options.percent),
      note: options.note || "",
    };
  }

  function metric(label, value, accent = "", note = "") {
    return { label, value, accent, note };
  }

  function iconUse(name) {
    return `<svg class="icon" aria-hidden="true"><use href="#${name}"></use></svg>`;
  }

  // -------------------------------------------------------------------
  // Формулы: ипотека
  // -------------------------------------------------------------------

  function computeMortgage(values) {
    const safeYears = Math.max(1, Math.round(num(values.years, 20)));
    const months = safeYears * 12;
    const price = Math.max(0, num(values.price, 8000000));
    const downPayment = Math.max(0, num(values.downPayment, 2000000));
    const annualRate = num(values.rate, 18);
    const inflationPercent = num(values.inflation, 8);
    const annualIncome = Math.max(0, num(values.income, 1200000));
    const useDeductions = Boolean(values.useDeductions);
    const annuity = values.paymentType !== "diff";

    const principal = Math.max(0, price - downPayment);
    const monthlyRate = annualRate / 100 / 12;
    const inflation = inflationPercent / 100;

    let payment = 0;
    let firstPayment = 0;
    let lastPayment = 0;
    let totalInterest = 0;

    if (principal <= 0) {
      payment = 0;
    } else if (annuity) {
      if (monthlyRate <= 0) {
        payment = principal / months;
      } else {
        const factor = Math.pow(1 + monthlyRate, months);
        payment = (principal * monthlyRate * factor) / (factor - 1);
      }
      firstPayment = payment;
      lastPayment = payment;
      totalInterest = payment * months - principal;
    } else {
      const principalPart = principal / months;
      firstPayment = principalPart + principal * monthlyRate;
      lastPayment = principalPart + principalPart * monthlyRate;
      totalInterest = (principal * monthlyRate * (months + 1)) / 2;
      payment = firstPayment;
    }

    const totalPayments = principal + totalInterest;
    const overpaymentRate = safeDiv(totalInterest, principal);

    const propertyDeduction = Math.min(price, 2000000) * 0.13;
    const interestDeduction = Math.min(totalInterest, 3000000) * 0.13;
    const potentialDeduction = propertyDeduction + interestDeduction;
    const annualNdfl = progressiveTax(annualIncome);
    const ndflPaid = annualNdfl * safeYears;
    const usableDeduction = useDeductions
      ? Math.min(potentialDeduction, ndflPaid)
      : 0;
    const effectiveCost = totalPayments - usableDeduction;

    const monthlyInflation = Math.pow(1 + inflation, 1 / 12) - 1;
    let realPaymentsValue = 0;

    if (principal > 0) {
      if (annuity) {
        realPaymentsValue =
          monthlyInflation === 0
            ? payment * months
            : (payment * (1 - Math.pow(1 + monthlyInflation, -months))) /
              monthlyInflation;
      } else {
        const principalPart = principal / months;
        let balance = principal;
        for (let month = 1; month <= months; month += 1) {
          const interest = balance * monthlyRate;
          const currentPayment = principalPart + interest;
          realPaymentsValue +=
            currentPayment / Math.pow(1 + monthlyInflation, month);
          balance -= principalPart;
        }
      }
    }

    const inflationSaving = totalPayments - realPaymentsValue;
    const realOverpayment = realPaymentsValue - principal;
    const realRate = (1 + annualRate / 100) / (1 + inflation) - 1;
    const factor = growth(inflation, safeYears);
    const realValue = safeDiv(totalPayments, factor);
    const inflationLoss = totalPayments - realValue;

    const taxRows = useDeductions
      ? [
          row("Имущественный вычет (до 2 млн ₽)", propertyDeduction),
          row("Вычет по процентам (до 3 млн ₽)", interestDeduction),
          row("Уплаченный НДФЛ за срок", ndflPaid),
          row("К возврату с учётом НДФЛ", usableDeduction),
        ]
      : [
          row("Потенциальный вычет", potentialDeduction),
          row("Вычеты отключены", 0),
        ];

    const tax = {
      title: "Налоги и вычеты",
      total: usableDeduction,
      isRefund: true,
      rows: taxRows,
      note: useDeductions
        ? "Вычет — это возврат ранее уплаченного НДФЛ, а не уменьшение ежемесячного платежа. Лимиты: 2 млн ₽ по покупке и 3 млн ₽ по ипотечным процентам."
        : "Вычеты отключены в расчёте. Потенциально можно вернуть 13% от стоимости жилья до 2 млн ₽ и 13% от процентов до 3 млн ₽.",
    };

    const inflationBlock = {
      futureCost: totalPayments,
      realValue,
      loss: inflationLoss,
      realAnnualReturn: realRate,
      benefit: inflationSaving,
      realLabel: "Реальная ставка",
      rows: [
        row("Всего платежей", totalPayments),
        row("В сегодняшних деньгах", realPaymentsValue),
        row("Обесценивание платежей инфляцией", inflationSaving),
        row("Реальная переплата", realOverpayment),
        row("Ставка минус инфляция", realRate, { percent: true }),
      ],
      note: "Инфляция снижает реальную нагрузку на платежи. Стоимость платежей в сегодняшних деньгах рассчитана по месячной инфляции.",
    };

    const hero = {
      eyebrow: annuity ? "Платёж в месяц" : "Первый платёж",
      value: rub(annuity ? payment : firstPayment),
      caption: annuity
        ? `Переплата ${rub(totalInterest)} · всего ${rub(totalPayments)}`
        : `Последний платёж ${rub(lastPayment)} · всего ${rub(totalPayments)}`,
      chips: [
        useDeductions
          ? `Вычет ${rub(usableDeduction)}`
          : "Вычеты отключены",
        `Реальная переплата ${rub(realOverpayment)}`,
      ],
    };

    return {
      hero,
      metrics: [
        metric("Сумма кредита", rub(principal)),
        metric("Переплата по процентам", rub(totalInterest), "amber"),
        metric("Всего платежей", rub(totalPayments)),
        metric("Переплата", pct(overpaymentRate)),
        metric("Налоговый вычет", rub(usableDeduction), "green"),
        metric("Стоимость с вычетом", rub(effectiveCost)),
        metric("Платежи в сегодняшних деньгах", rub(realPaymentsValue), "blue"),
        metric("Ставка минус инфляция", pct(realRate), "blue"),
      ],
      tax,
      inflation: inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Формулы: потребительский кредит
  // -------------------------------------------------------------------

  function computeCredit(values) {
    const safeYears = Math.max(1, Math.round(num(values.years, 3)));
    const months = safeYears * 12;
    const principal = Math.max(0, num(values.amount, 500000));
    const annualRate = num(values.rate, 22);
    const commissionPercent = num(values.commission, 1);
    const insurancePercent = num(values.insurance, 0);
    const inflationPercent = num(values.inflation, 8);
    const annuity = values.paymentType !== "diff";

    const monthlyRate = annualRate / 100 / 12;
    const inflation = inflationPercent / 100;

    let payment = 0;
    let firstPayment = 0;
    let lastPayment = 0;
    let totalInterest = 0;

    if (principal <= 0) {
      payment = 0;
    } else if (annuity) {
      if (monthlyRate <= 0) {
        payment = principal / months;
      } else {
        const factor = Math.pow(1 + monthlyRate, months);
        payment = (principal * monthlyRate * factor) / (factor - 1);
      }
      firstPayment = payment;
      lastPayment = payment;
      totalInterest = payment * months - principal;
    } else {
      const principalPart = principal / months;
      firstPayment = principalPart + principal * monthlyRate;
      lastPayment = principalPart + principalPart * monthlyRate;
      totalInterest = (principal * monthlyRate * (months + 1)) / 2;
      payment = firstPayment;
    }

    const totalPayments = principal + totalInterest;
    const commission = principal * (commissionPercent / 100);
    const insurance = principal * (insurancePercent / 100) * safeYears;
    const totalCost = totalPayments + commission + insurance;
    const overpaymentRate = safeDiv(totalCost - principal, principal);

    const monthlyInflation = Math.pow(1 + inflation, 1 / 12) - 1;
    const insuranceMonthly = (principal * (insurancePercent / 100)) / 12;
    let realCost = commission;

    if (principal > 0) {
      if (annuity) {
        const stream = payment + insuranceMonthly;
        realCost +=
          monthlyInflation === 0
            ? stream * months
            : (stream * (1 - Math.pow(1 + monthlyInflation, -months))) /
              monthlyInflation;
      } else {
        const principalPart = principal / months;
        let balance = principal;
        for (let month = 1; month <= months; month += 1) {
          const interest = balance * monthlyRate;
          const currentPayment = principalPart + interest + insuranceMonthly;
          realCost += currentPayment / Math.pow(1 + monthlyInflation, month);
          balance -= principalPart;
        }
      }
    }

    const inflationSaving = totalCost - realCost;
    const realOverpayment = realCost - principal;
    const realRate = (1 + annualRate / 100) / (1 + inflation) - 1;

    const tax = {
      title: "Налоги",
      total: 0,
      isRefund: false,
      rows: [
        row("НДФЛ с кредита", 0),
        row("Вычет по процентам", 0, {
          note: "Предусмотрен только для ипотеки",
        }),
      ],
      note: "Потребительский кредит не облагается НДФЛ: это не доход. Проценты, комиссия и страховка не уменьшают налоговую базу. Вычет по процентам доступен только по ипотеке.",
    };

    const inflationBlock = {
      futureCost: totalCost,
      realValue: realCost,
      loss: inflationSaving,
      realAnnualReturn: realRate,
      benefit: inflationSaving,
      realLabel: "Реальная ставка",
      rows: [
        row("Всего к возврату с комиссией", totalCost),
        row("В сегодняшних деньгах", realCost),
        row("Обесценивание платежей инфляцией", inflationSaving),
        row("Реальная переплата", realOverpayment),
        row("Ставка минус инфляция", realRate, { percent: true }),
      ],
      note: "Инфляция снижает реальную нагрузку на платежи. Стоимость в сегодняшних деньгах рассчитана по месячной инфляции с учётом комиссии и страховки.",
    };

    const hero = {
      eyebrow: annuity ? "Платёж в месяц" : "Первый платёж",
      value: rub(annuity ? payment : firstPayment),
      caption: annuity
        ? `Проценты ${rub(totalInterest)} · всего ${rub(totalCost)}`
        : `Последний платёж ${rub(lastPayment)} · всего ${rub(totalCost)}`,
      chips: [
        `Комиссия ${rub(commission)}`,
        `Реальная переплата ${rub(realOverpayment)}`,
      ],
    };

    return {
      hero,
      metrics: [
        metric("Сумма кредита", rub(principal)),
        metric("Проценты за срок", rub(totalInterest), "amber"),
        metric("Комиссия", rub(commission)),
        metric("Страховка", rub(insurance)),
        metric("Всего к возврату", rub(totalCost)),
        metric("Полная переплата", pct(overpaymentRate)),
        metric("В сегодняшних деньгах", rub(realCost), "blue"),
        metric("Ставка минус инфляция", pct(realRate), "blue"),
      ],
      tax,
      inflation: inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Формулы: вклад
  // -------------------------------------------------------------------

  function computeDeposit(values) {
    const safeMonths = Math.max(1, Math.round(num(values.months, 12)));
    const years = safeMonths / 12;
    const annualRate = num(values.rate, 16);
    const monthlyRate = annualRate / 100 / 12;
    const inflationPercent = num(values.inflation, 8);
    const inflation = inflationPercent / 100;
    const capitalization = Math.max(0, Math.round(num(values.capitalization, 1)));
    const keyRate = num(values.keyRate, 16);

    let balance = Math.max(0, num(values.amount, 500000));
    let contributed = balance;
    let accrued = 0;
    const topUp = Math.max(0, num(values.topUp, 10000));

    for (let month = 1; month <= safeMonths; month += 1) {
      balance += topUp;
      contributed += topUp;
      const interest = balance * monthlyRate;
      accrued += interest;
      if (capitalization > 0 && month % capitalization === 0) {
        balance += accrued;
        accrued = 0;
      }
    }

    const grossInterest =
      capitalization > 0 ? balance - contributed + accrued : accrued;
    const finalAmount = contributed + grossInterest;

    const yearsCount = Math.max(1, Math.ceil(safeMonths / 12));
    const allowance = 1000000 * (keyRate / 100) * yearsCount;
    const taxableTotal = Math.max(0, grossInterest - allowance);
    const taxAmount = progressiveTax(taxableTotal / yearsCount) * yearsCount;

    const netAmount = finalAmount - taxAmount;
    const netProfit = grossInterest - taxAmount;
    const totalYield = safeDiv(netProfit, contributed);
    const annualYield = annualize(totalYield, years);
    const factor = growth(inflation, years);
    const realValue = safeDiv(netAmount, factor);
    const inflationLoss = netAmount - realValue;
    const realAnnualYield = (1 + annualYield) / (1 + inflation) - 1;
    const futureCost = contributed * factor;

    const tax = {
      title: "Налоги",
      total: taxAmount,
      isRefund: false,
      rows: [
        row("Проценты за срок", grossInterest),
        row("Необлагаемый лимит", allowance),
        row("Налоговая база", taxableTotal),
        row("НДФЛ с процентов", taxAmount),
      ],
      note: "Лимит: 1 млн ₽ × ключевая ставка за каждый год. Ставка НДФЛ прогрессивная: 13–22%.",
    };

    const inflationBlock = {
      futureCost,
      realValue,
      loss: inflationLoss,
      realAnnualReturn: realAnnualYield,
      realLabel: "Реальная доходность",
      rows: [
        row("Будущая цена текущих взносов", futureCost),
        row("Покупательная способность итога", realValue),
        row("Потеря покупательной способности", inflationLoss),
        row("Реальная доходность в год", realAnnualYield, { percent: true }),
      ],
      note: "Инфляция уменьшает покупательную способность итоговой суммы. Реальная доходность — это доходность сверх инфляции.",
    };

    const hero = {
      eyebrow: `Итог через ${safeMonths} мес.`,
      value: rub(netAmount),
      caption: `До налога ${rub(finalAmount)} · налог ${rub(taxAmount)}`,
      chips: [
        `Взносы ${rub(contributed)}`,
        `Доходность ${pct(annualYield)} в год`,
      ],
    };

    return {
      hero,
      metrics: [
        metric("Взносы за срок", rub(contributed)),
        metric("Проценты", rub(grossInterest), "green"),
        metric("НДФЛ с процентов", rub(taxAmount), "amber"),
        metric("На руки", rub(netAmount)),
        metric("Доходность за срок", pct(totalYield)),
        metric("Доходность в год", pct(annualYield), "green"),
        metric("Покупательная способность", rub(realValue), "blue"),
        metric("Реальная доходность", pct(realAnnualYield), "blue"),
      ],
      tax,
      inflation: inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Формулы: ОФЗ и облигации
  // -------------------------------------------------------------------

  function bondCore(values, isCorporate) {
    const safeYears = Math.max(1, Math.round(num(values.years, 3)));
    const quantity = Math.max(1, Math.round(num(values.quantity, 10)));
    const faceValue = Math.max(0, num(values.face, 1000));
    const pricePercent = num(values.price, isCorporate ? 100 : 95);
    const couponPercent = num(values.coupon, isCorporate ? 16 : 12);
    const couponsPerYear = Math.max(
      1,
      Math.round(num(values.couponsPerYear, 2)),
    );
    const commissionPercent = num(values.commission, 0.3);
    const inflationPercent = num(values.inflation, 8);
    const defaultProbabilityPercent = isCorporate
      ? num(values.defaultProbability, 1)
      : 0;
    const recoveryPercent = isCorporate ? num(values.recovery, 40) : 0;
    const inflation = inflationPercent / 100;

    const annualCoupon = faceValue * (couponPercent / 100) * quantity;
    const invested = faceValue * (pricePercent / 100) * quantity;
    const commission = invested * (commissionPercent / 100);
    const totalInvested = invested + commission;
    const coupons = annualCoupon * safeYears;
    const redemption = faceValue * quantity;
    const priceGain = redemption - invested;
    const grossProfit = coupons + priceGain - commission;

    const couponTax = progressiveTax(annualCoupon) * safeYears;
    const gainTax = Math.max(0, priceGain) * 0.13;
    const totalTax = couponTax + gainTax;
    const netProfit = grossProfit - totalTax;

    const expectedLoss = isCorporate
      ? redemption *
        (defaultProbabilityPercent / 100) *
        (1 - recoveryPercent / 100)
      : 0;
    const riskAdjustedProfit = netProfit - expectedLoss;
    const terminalValue = totalInvested + netProfit;

    const couponPerPayment = safeDiv(
      annualCoupon,
      Math.max(1, couponsPerYear),
    );
    const currentYield = safeDiv(annualCoupon, totalInvested);
    const averageInvested = (totalInvested + redemption) / 2;
    const yieldToMaturity = safeDiv(
      annualCoupon + priceGain / safeYears,
      averageInvested,
    );
    const totalReturn = safeDiv(netProfit, totalInvested);
    const annualReturn = annualize(totalReturn, safeYears);
    const factor = growth(inflation, safeYears);
    const realValue = safeDiv(terminalValue, factor);
    const inflationLoss = terminalValue - realValue;
    const realAnnualReturn = (1 + annualReturn) / (1 + inflation) - 1;
    const futureCost = totalInvested * factor;

    const tax = {
      title: "Налоги",
      total: totalTax,
      isRefund: false,
      rows: [
        row("НДФЛ с купонов", couponTax),
        row("НДФЛ с прироста цены", gainTax),
        row("Купонный доход за год", annualCoupon),
      ],
      note: isCorporate
        ? "Купон и положительная разница цены облагаются НДФЛ 13–22%. Риск дефолта показан отдельно и не входит в налоги."
        : "Купоны ОФЗ и положительный доход от продажи облагаются НДФЛ. Убыток от продажи может уменьшить базу при наличии других доходов.",
    };

    const inflationBlock = {
      futureCost,
      realValue,
      loss: inflationLoss,
      realAnnualReturn,
      realLabel: "Реальная доходность",
      rows: [
        row("Будущая цена вложенной суммы", futureCost),
        row("Покупательная способность итога", realValue),
        row("Потеря покупательной способности", inflationLoss),
        row("Реальная доходность в год", realAnnualReturn, {
          percent: true,
        }),
      ],
      note: "Инфляция сравнивается с итоговой суммой после налогов. Купонные выплаты в течение срока здесь не реинвестируются.",
    };

    return {
      safeYears,
      annualCoupon,
      invested: totalInvested,
      commission,
      coupons,
      priceGain,
      grossProfit,
      tax: totalTax,
      netProfit,
      expectedLoss,
      riskAdjustedProfit,
      terminalValue,
      couponPerPayment,
      currentYield,
      yieldToMaturity,
      totalReturn,
      annualReturn,
      realValue,
      inflationLoss,
      realAnnualReturn,
      taxBlock: tax,
      inflationBlock,
    };
  }

  function computeOfz(values) {
    const result = bondCore(values, false);

    return {
      hero: {
        eyebrow: "Прибыль после налогов",
        value: rub(result.netProfit),
        caption: `Итоговая сумма ${rub(result.terminalValue)} · вложено ${rub(result.invested)}`,
        chips: [
          `Доходность к погашению ${pct(result.yieldToMaturity)}`,
          `Купон в год ${rub(result.coupons / result.safeYears)}`,
        ],
      },
      metrics: [
        metric("Вложено с комиссией", rub(result.invested)),
        metric("Купоны за срок", rub(result.coupons), "green"),
        metric("Прирост цены", rub(result.priceGain)),
        metric("Налог", rub(result.tax), "amber"),
        metric("Итоговая сумма", rub(result.terminalValue), "green"),
        metric("Купон за выплату", rub(result.couponPerPayment)),
        metric("Текущая доходность", pct(result.currentYield)),
        metric("Доходность в год", pct(result.annualReturn), "green"),
      ],
      tax: result.taxBlock,
      inflation: result.inflationBlock,
    };
  }

  function computeBonds(values) {
    const isCorporate = values.isCorporate !== "municipal";
    const result = bondCore(values, isCorporate);
    const mainProfit = isCorporate
      ? result.riskAdjustedProfit
      : result.netProfit;

    return {
      hero: {
        eyebrow: isCorporate
          ? "Прибыль с учётом риска"
          : "Прибыль после налогов",
        value: rub(mainProfit),
        caption: isCorporate
          ? `После налогов ${rub(result.netProfit)} · ожидаемые потери ${rub(result.expectedLoss)}`
          : `Итоговая сумма ${rub(result.terminalValue)} · вложено ${rub(result.invested)}`,
        chips: [
          `Доходность к погашению ${pct(result.yieldToMaturity)}`,
          `Купон в год ${rub(result.coupons / result.safeYears)}`,
        ],
      },
      metrics: [
        metric("Вложено с комиссией", rub(result.invested)),
        metric("Купоны за срок", rub(result.coupons), "green"),
        metric("Прирост цены", rub(result.priceGain)),
        metric("Налог", rub(result.tax), "amber"),
        metric("Прибыль после налогов", rub(result.netProfit)),
        ...(isCorporate
          ? [
              metric(
                "Ожидаемые потери",
                rub(result.expectedLoss),
                "red",
              ),
            ]
          : []),
        metric("Купон за выплату", rub(result.couponPerPayment)),
        metric("Доходность в год", pct(result.annualReturn), "green"),
      ],
      tax: result.taxBlock,
      inflation: result.inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Формулы: недвижимость под аренду
  // -------------------------------------------------------------------

  function computeRealEstate(values) {
    const safeYears = Math.max(1, Math.round(num(values.years, 5)));
    const price = Math.max(0, num(values.price, 8000000));
    const monthlyRent = Math.max(0, num(values.rent, 45000));
    const vacancyPercent = num(values.vacancy, 8);
    const monthlyExpenses = Math.max(0, num(values.expenses, 8000));
    const annualGrowthPercent = num(values.growth, 6);
    const purchaseCostsPercent = num(values.purchaseCosts, 2);
    const saleCostsPercent = num(values.saleCosts, 2);
    const rentTaxMode = values.rentTaxMode || "ndfl";
    const propertyTaxPercent = num(values.propertyTax, 0.1);
    const inflationPercent = num(values.inflation, 8);
    const inflation = inflationPercent / 100;

    const purchaseCosts = price * (purchaseCostsPercent / 100);
    const invested = price + purchaseCosts;
    const annualRentGross = monthlyRent * 12;
    const effectiveAnnualRent = annualRentGross * (1 - vacancyPercent / 100);
    const totalRent = effectiveAnnualRent * safeYears;
    const expenses = monthlyExpenses * 12 * safeYears;

    const rentTax =
      rentTaxMode === "self"
        ? totalRent * 0.04
        : rentTaxMode === "none"
          ? 0
          : progressiveTax(effectiveAnnualRent) * safeYears;
    const propertyTax = price * (propertyTaxPercent / 100) * safeYears;

    const salePrice = price * growth(annualGrowthPercent / 100, safeYears);
    const saleCosts = salePrice * (saleCostsPercent / 100);
    const saleGain = Math.max(0, salePrice - price - purchaseCosts);
    const saleTax = safeYears < 5 ? saleGain * 0.13 : 0;

    const totalTax = rentTax + propertyTax + saleTax;
    const netCashFlow = totalRent - expenses - propertyTax - rentTax;
    const terminalValue = netCashFlow + salePrice - saleCosts - saleTax;
    const totalProfit = terminalValue - invested;
    const totalReturn = safeDiv(totalProfit, invested);
    const annualReturn = annualize(totalReturn, safeYears);

    const factor = growth(inflation, safeYears);
    const realValue = safeDiv(terminalValue, factor);
    const inflationLoss = terminalValue - realValue;
    const realAnnualReturn = (1 + annualReturn) / (1 + inflation) - 1;
    const futureCost = invested * factor;

    const tax = {
      title: "Налоги",
      total: totalTax,
      isRefund: false,
      rows: [
        row("НДФЛ с аренды", rentTax),
        row("Налог на имущество", propertyTax),
        row("Налог с продажи", saleTax),
      ],
      note: "Аренда: НДФЛ 13–22% или 4% для самозанятого. При владении 5+ лет налог с продажи обычно не возникает (в ряде случаев — от 3 лет). Налог на имущество — оценка.",
    };

    const inflationBlock = {
      futureCost,
      realValue,
      loss: inflationLoss,
      realAnnualReturn,
      realLabel: "Реальная доходность",
      rows: [
        row("Будущая цена вложений", futureCost),
        row("Покупательная способность итога", realValue),
        row("Потеря покупательной способности", inflationLoss),
        row("Реальная доходность в год", realAnnualReturn, {
          percent: true,
        }),
      ],
      note: "Учитывается рост цены объекта и инфляция. Арендные платежи в модели не индексируются.",
    };

    return {
      hero: {
        eyebrow: "Прибыль после налогов",
        value: rub(totalProfit),
        caption: `Итоговая сумма ${rub(terminalValue)} · вложено ${rub(invested)}`,
        chips: [
          `Доходность ${pct(annualReturn)} в год`,
          `Аренда за срок ${rub(totalRent)}`,
        ],
      },
      metrics: [
        metric("Вложено с расходами", rub(invested)),
        metric("Аренда за срок", rub(totalRent), "green"),
        metric("Расходы за срок", rub(expenses)),
        metric("Цена продажи", rub(salePrice)),
        metric("Налоги", rub(totalTax), "amber"),
        metric("Прибыль после налогов", rub(totalProfit), "green"),
        metric("Чистый поток аренды", rub(netCashFlow)),
        metric("Доходность в год", pct(annualReturn), "green"),
      ],
      tax,
      inflation: inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Формулы: инфляция
  // -------------------------------------------------------------------

  function computeInflation(values) {
    const safeYears = Math.max(1, Math.round(num(values.years, 10)));
    const amount = Math.max(0, num(values.amount, 1000000));
    const inflationPercent = num(values.inflation, 8);
    const depositRatePercent = num(values.depositRate, 16);
    const keyRatePercent = num(values.keyRate, 16);
    const inflation = inflationPercent / 100;

    const factor = growth(inflation, safeYears);
    const futureCost = amount * factor;
    const purchasingPower = safeDiv(amount, factor);
    const loss = amount - purchasingPower;
    const requiredPreTax = (1 + inflation) / (1 - 0.13) - 1;

    const hasIncome = depositRatePercent > 0;
    const nominalCapital = hasIncome
      ? amount * growth(depositRatePercent / 100, safeYears)
      : amount;
    const interest = nominalCapital - amount;
    const allowance = 1000000 * (keyRatePercent / 100) * safeYears;
    const taxable = Math.max(0, interest - allowance);
    const taxAmount = hasIncome
      ? progressiveTax(taxable / safeYears) * safeYears
      : 0;
    const afterTax = nominalCapital - taxAmount;
    const afterTaxReal = safeDiv(afterTax, factor);
    const realCapital = safeDiv(nominalCapital, factor);
    const afterTaxAnnual = annualize(
      safeDiv(afterTax - amount, amount),
      safeYears,
    );
    const realReturn = hasIncome
      ? (1 + afterTaxAnnual) / (1 + inflation) - 1
      : 1 / (1 + inflation) - 1;

    const tax = {
      title: "Налоги",
      total: taxAmount,
      isRefund: false,
      rows: hasIncome
        ? [
            row("Проценты за срок", interest),
            row("Необлагаемый лимит", allowance),
            row("Налоговая база", taxable),
            row("НДФЛ с процентов", taxAmount),
          ]
        : [row("Доход от вложения", 0), row("Налоговая база", 0)],
      note: hasIncome
        ? "НДФЛ с процентов: 13–22% с суммы сверх лимита 1 млн ₽ × ключевая ставка за каждый год."
        : "Укажите доходность вложения, чтобы рассчитать налог с процентов.",
    };

    const inflationRows = [
      row("Будущая цена корзины", futureCost),
      row("Покупательная способность суммы", purchasingPower),
      row("Потеря покупательной способности", loss),
      row("Инфляция за срок", factor - 1, { percent: true }),
    ];
    if (hasIncome) {
      inflationRows.push(
        row("Реальная доходность вложения", realReturn, { percent: true }),
      );
    }
    inflationRows.push(
      row("Нужная доходность до налога", requiredPreTax, { percent: true }),
    );

    const inflationBlock = {
      futureCost,
      realValue: purchasingPower,
      loss,
      realAnnualReturn: realReturn,
      realLabel: "Реальная доходность",
      rows: inflationRows,
      note: "Чтобы сохранить покупательную способность после НДФЛ 13%, нужна доходность выше инфляции. Сумма «под матрасом» теряет покупательную способность.",
    };

    return {
      hero: {
        eyebrow: "Будущая цена корзины",
        value: rub(futureCost),
        caption: `Сегодня ${rub(amount)} · через ${formatYears(safeYears)}`,
        chips: [
          `Потеря ${rub(loss)}`,
          `Нужно ${pct(inflation)} в год`,
        ],
      },
      metrics: [
        metric("Сумма сегодня", rub(amount)),
        metric("Будущая цена корзины", rub(futureCost), "blue"),
        metric("Покупательная способность", rub(purchasingPower)),
        metric("Потеря покупательной способности", rub(loss), "red"),
        metric("Нужная доходность", pct(inflation)),
        metric("Доходность до налога", pct(requiredPreTax), "", "При НДФЛ 13%"),
        metric("Капитал с доходностью", rub(nominalCapital)),
        metric("Реальный капитал после налога", rub(afterTaxReal), "green"),
      ],
      tax,
      inflation: inflationBlock,
    };
  }

  // -------------------------------------------------------------------
  // Описание калькуляторов
  // -------------------------------------------------------------------

  const YEARS_MORTGAGE = [
    ["5", "5 лет"],
    ["10", "10 лет"],
    ["15", "15 лет"],
    ["20", "20 лет"],
    ["25", "25 лет"],
    ["30", "30 лет"],
  ];
  const YEARS_CREDIT = [
    ["1", "1 год"],
    ["2", "2 года"],
    ["3", "3 года"],
    ["4", "4 года"],
    ["5", "5 лет"],
    ["7", "7 лет"],
  ];
  const MONTHS_DEPOSIT = [
    ["3", "3 месяца"],
    ["6", "6 месяцев"],
    ["12", "1 год"],
    ["18", "1,5 года"],
    ["24", "2 года"],
    ["36", "3 года"],
    ["60", "5 лет"],
  ];
  const YEARS_BOND = [
    ["1", "1 год"],
    ["2", "2 года"],
    ["3", "3 года"],
    ["5", "5 лет"],
    ["7", "7 лет"],
    ["10", "10 лет"],
  ];
  const COUPONS = [
    ["1", "1"],
    ["2", "2"],
    ["4", "4"],
    ["12", "12"],
  ];
  const YEARS_REAL_ESTATE = [
    ["1", "1 год"],
    ["3", "3 года"],
    ["5", "5 лет"],
    ["7", "7 лет"],
    ["10", "10 лет"],
    ["15", "15 лет"],
  ];
  const YEARS_INFLATION = [
    ["1", "1 год"],
    ["3", "3 года"],
    ["5", "5 лет"],
    ["10", "10 лет"],
    ["15", "15 лет"],
    ["20", "20 лет"],
  ];

  const CALCULATORS = {
    mortgage: {
      name: "Ипотека",
      subtitle: "Платёж, переплата, вычет и реальная стоимость",
      icon: "i-mortgage",
      compute: computeMortgage,
      groups: [
        {
          title: "Параметры ипотеки",
          fields: [
            {
              id: "price",
              label: "Стоимость жилья",
              type: "number",
              suffix: "₽",
              default: 8000000,
              step: 100000,
              wide: true,
            },
            {
              id: "downPayment",
              label: "Первоначальный взнос",
              type: "number",
              suffix: "₽",
              default: 2000000,
              step: 100000,
            },
            {
              id: "rate",
              label: "Ставка",
              type: "number",
              suffix: "%",
              default: 18,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок",
              type: "select",
              default: "20",
              options: YEARS_MORTGAGE,
            },
            {
              id: "paymentType",
              label: "Тип платежа",
              type: "segment",
              default: "annuity",
              wide: true,
              options: [
                ["annuity", "Аннуитет"],
                ["diff", "Дифференцированный"],
              ],
            },
          ],
        },
        {
          title: "Вычеты и инфляция",
          fields: [
            {
              id: "income",
              label: "Доход в год",
              type: "number",
              suffix: "₽",
              default: 1200000,
              step: 50000,
              hint: "Для расчёта уплаченного НДФЛ",
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
            {
              id: "useDeductions",
              label: "Учитывать налоговый вычет",
              type: "switch",
              default: true,
              hint: "Возврат 13% от стоимости жилья и процентов",
            },
          ],
        },
      ],
    },
    credit: {
      name: "Кредит",
      subtitle: "Платёж, комиссия, страховка и реальная нагрузка",
      icon: "i-credit",
      compute: computeCredit,
      groups: [
        {
          title: "Параметры кредита",
          fields: [
            {
              id: "amount",
              label: "Сумма кредита",
              type: "number",
              suffix: "₽",
              default: 500000,
              step: 10000,
              wide: true,
            },
            {
              id: "rate",
              label: "Ставка",
              type: "number",
              suffix: "%",
              default: 22,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок",
              type: "select",
              default: "3",
              options: YEARS_CREDIT,
            },
            {
              id: "paymentType",
              label: "Тип платежа",
              type: "segment",
              default: "annuity",
              wide: true,
              options: [
                ["annuity", "Аннуитет"],
                ["diff", "Дифференцированный"],
              ],
            },
          ],
        },
        {
          title: "Комиссия, страховка и инфляция",
          fields: [
            {
              id: "commission",
              label: "Комиссия",
              type: "number",
              suffix: "%",
              default: 1,
              step: 0.1,
              hint: "Разово при выдаче",
            },
            {
              id: "insurance",
              label: "Страховка",
              type: "number",
              suffix: "% в год",
              default: 0,
              step: 0.1,
              hint: "От суммы кредита",
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
              wide: true,
            },
          ],
        },
      ],
    },
    deposit: {
      name: "Вклад",
      subtitle: "Сложный процент, пополнения и НДФЛ с процентов",
      icon: "i-deposit",
      compute: computeDeposit,
      groups: [
        {
          title: "Параметры вклада",
          fields: [
            {
              id: "amount",
              label: "Сумма вклада",
              type: "number",
              suffix: "₽",
              default: 500000,
              step: 10000,
              wide: true,
            },
            {
              id: "rate",
              label: "Ставка",
              type: "number",
              suffix: "%",
              default: 16,
              step: 0.1,
            },
            {
              id: "months",
              label: "Срок",
              type: "select",
              default: "12",
              options: MONTHS_DEPOSIT,
            },
            {
              id: "topUp",
              label: "Пополнение в месяц",
              type: "number",
              suffix: "₽",
              default: 10000,
              step: 1000,
            },
            {
              id: "capitalization",
              label: "Капитализация",
              type: "select",
              default: "1",
              options: [
                ["1", "Ежемесячно"],
                ["3", "Ежеквартально"],
                ["12", "Ежегодно"],
                ["0", "В конце срока"],
              ],
            },
          ],
        },
        {
          title: "Налоги и инфляция",
          fields: [
            {
              id: "keyRate",
              label: "Ключевая ставка",
              type: "number",
              suffix: "%",
              default: 16,
              step: 0.1,
              hint: "Для лимита налога",
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
          ],
        },
      ],
    },
    ofz: {
      name: "ОФЗ",
      subtitle: "Купоны, цена покупки и доходность к погашению",
      icon: "i-ofz",
      compute: computeOfz,
      groups: [
        {
          title: "Параметры ОФЗ",
          fields: [
            {
              id: "face",
              label: "Номинал",
              type: "number",
              suffix: "₽",
              default: 1000,
              step: 100,
            },
            {
              id: "price",
              label: "Цена",
              type: "number",
              suffix: "%",
              default: 95,
              step: 0.1,
            },
            {
              id: "quantity",
              label: "Количество",
              type: "number",
              suffix: "шт.",
              default: 10,
              step: 1,
            },
            {
              id: "coupon",
              label: "Купон в год",
              type: "number",
              suffix: "%",
              default: 12,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок до погашения",
              type: "select",
              default: "3",
              options: YEARS_BOND,
            },
            {
              id: "couponsPerYear",
              label: "Купонов в год",
              type: "select",
              default: "2",
              options: COUPONS,
            },
          ],
        },
        {
          title: "Налоги и инфляция",
          fields: [
            {
              id: "commission",
              label: "Комиссия брокера",
              type: "number",
              suffix: "%",
              default: 0.3,
              step: 0.1,
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
          ],
        },
      ],
    },
    bonds: {
      name: "Облигации",
      subtitle: "Корпоративные и муниципальные: купон, риск и налоги",
      icon: "i-bonds",
      compute: computeBonds,
      groups: [
        {
          title: "Параметры облигации",
          fields: [
            {
              id: "isCorporate",
              label: "Тип эмитента",
              type: "segment",
              default: "corporate",
              wide: true,
              options: [
                ["corporate", "Корпоративная"],
                ["municipal", "Муниципальная"],
              ],
            },
            {
              id: "face",
              label: "Номинал",
              type: "number",
              suffix: "₽",
              default: 1000,
              step: 100,
            },
            {
              id: "price",
              label: "Цена",
              type: "number",
              suffix: "%",
              default: 100,
              step: 0.1,
            },
            {
              id: "quantity",
              label: "Количество",
              type: "number",
              suffix: "шт.",
              default: 10,
              step: 1,
            },
            {
              id: "coupon",
              label: "Купон в год",
              type: "number",
              suffix: "%",
              default: 16,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок",
              type: "select",
              default: "3",
              options: YEARS_BOND,
            },
            {
              id: "couponsPerYear",
              label: "Купонов в год",
              type: "select",
              default: "2",
              options: COUPONS,
            },
          ],
        },
        {
          title: "Риск, налоги и инфляция",
          fields: [
            {
              id: "commission",
              label: "Комиссия",
              type: "number",
              suffix: "%",
              default: 0.3,
              step: 0.1,
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
            {
              id: "defaultProbability",
              label: "Вероятность дефолта",
              type: "number",
              suffix: "%",
              default: 1,
              step: 0.1,
              hint: "За весь срок",
              showIf: (values) => values.isCorporate === "corporate",
            },
            {
              id: "recovery",
              label: "Возврат при дефолте",
              type: "number",
              suffix: "%",
              default: 40,
              step: 1,
              hint: "Доля номинала",
              showIf: (values) => values.isCorporate === "corporate",
            },
          ],
        },
      ],
    },
    realestate: {
      name: "Недвижимость",
      subtitle: "Аренда, рост цены, расходы и налоги",
      icon: "i-realestate",
      compute: computeRealEstate,
      groups: [
        {
          title: "Параметры объекта",
          fields: [
            {
              id: "price",
              label: "Стоимость объекта",
              type: "number",
              suffix: "₽",
              default: 8000000,
              step: 100000,
              wide: true,
            },
            {
              id: "rent",
              label: "Аренда в месяц",
              type: "number",
              suffix: "₽",
              default: 45000,
              step: 1000,
            },
            {
              id: "vacancy",
              label: "Простой",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.5,
              hint: "Доля года без арендатора",
            },
            {
              id: "expenses",
              label: "Расходы в месяц",
              type: "number",
              suffix: "₽",
              default: 8000,
              step: 1000,
              hint: "ЖКХ, ремонт, страховка",
            },
            {
              id: "growth",
              label: "Рост цены в год",
              type: "number",
              suffix: "%",
              default: 6,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок владения",
              type: "select",
              default: "5",
              options: YEARS_REAL_ESTATE,
            },
            {
              id: "rentTaxMode",
              label: "Налог с аренды",
              type: "select",
              default: "ndfl",
              options: [
                ["ndfl", "НДФЛ 13–22%"],
                ["self", "Самозанятый 4%"],
                ["none", "Без налога"],
              ],
            },
            {
              id: "purchaseCosts",
              label: "Расходы покупки",
              type: "number",
              suffix: "%",
              default: 2,
              step: 0.1,
            },
            {
              id: "saleCosts",
              label: "Расходы продажи",
              type: "number",
              suffix: "%",
              default: 2,
              step: 0.1,
            },
            {
              id: "propertyTax",
              label: "Налог на имущество",
              type: "number",
              suffix: "% в год",
              default: 0.1,
              step: 0.05,
              hint: "От стоимости объекта",
            },
            {
              id: "inflation",
              label: "Инфляция",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
          ],
        },
      ],
    },
    inflation: {
      name: "Инфляция",
      subtitle: "Покупательная способность, будущие цены и нужная доходность",
      icon: "i-inflation",
      compute: computeInflation,
      groups: [
        {
          title: "Параметры расчёта",
          fields: [
            {
              id: "amount",
              label: "Сумма сегодня",
              type: "number",
              suffix: "₽",
              default: 1000000,
              step: 50000,
              wide: true,
            },
            {
              id: "inflation",
              label: "Инфляция в год",
              type: "number",
              suffix: "%",
              default: 8,
              step: 0.1,
            },
            {
              id: "years",
              label: "Срок",
              type: "select",
              default: "10",
              options: YEARS_INFLATION,
            },
          ],
        },
        {
          title: "Доходность и налоги",
          fields: [
            {
              id: "depositRate",
              label: "Доходность вложения",
              type: "number",
              suffix: "%",
              default: 16,
              step: 0.1,
              hint: "0 — деньги без вложения",
            },
            {
              id: "keyRate",
              label: "Ключевая ставка",
              type: "number",
              suffix: "%",
              default: 16,
              step: 0.1,
              hint: "Для лимита налога",
            },
          ],
        },
      ],
    },
  };

  // -------------------------------------------------------------------
  // Состояние и форма
  // -------------------------------------------------------------------

  const state = {
    current: "mortgage",
    values: {},
    lastComputed: null,
  };

  Object.entries(CALCULATORS).forEach(([id, calc]) => {
    const values = {};
    calc.groups.forEach((group) => {
      group.fields.forEach((field) => {
        values[field.id] = field.default;
      });
    });
    state.values[id] = values;
  });

  function fieldMarkup(field, values) {
    const inputId = `field-${state.current}-${field.id}`;
    const hidden = field.showIf && !field.showIf(values);
    const classes = ["calc-field"];
    if (field.wide) classes.push("wide");
    if (hidden) classes.push("is-hidden");
    const wrapper = `class="${classes.join(" ")}" data-field="${field.id}"`;
    const hint = field.hint ? `<span class="hint">${esc(field.hint)}</span>` : "";

    if (field.type === "number") {
      return `<div ${wrapper}>
        <label for="${inputId}">${esc(field.label)}</label>
        <div class="input-shell">
          <input id="${inputId}" data-field-id="${field.id}" type="text" inputmode="decimal" autocomplete="off" value="${esc(values[field.id])}">
          <span class="input-suffix">${esc(field.suffix || "")}</span>
        </div>
        ${hint}
      </div>`;
    }

    if (field.type === "select") {
      const options = field.options
        .map(
          (option) =>
            `<option value="${esc(option[0])}"${String(option[0]) === String(values[field.id]) ? " selected" : ""}>${esc(option[1])}</option>`,
        )
        .join("");
      return `<div ${wrapper}>
        <label for="${inputId}">${esc(field.label)}</label>
        <div class="select-shell">
          <select id="${inputId}" data-field-id="${field.id}">${options}</select>
        </div>
        ${hint}
      </div>`;
    }

    if (field.type === "segment") {
      const buttons = field.options
        .map((option) => {
          const active = String(option[0]) === String(values[field.id]);
          return `<button type="button" data-segment="${field.id}" data-value="${esc(option[0])}" class="${active ? "is-active" : ""}" aria-pressed="${active}">${esc(option[1])}</button>`;
        })
        .join("");
      return `<div ${wrapper}>
        <span class="field-label">${esc(field.label)}</span>
        <div class="segmented-control" role="group" aria-label="${esc(field.label)}">${buttons}</div>
        ${hint}
      </div>`;
    }

    if (field.type === "switch") {
      return `<label class="switch-field${hidden ? " is-hidden" : ""}" data-field="${field.id}">
        <span class="switch-copy">
          <strong>${esc(field.label)}</strong>
          ${field.hint ? `<small>${esc(field.hint)}</small>` : ""}
        </span>
        <span class="switch">
          <input id="${inputId}" data-field-id="${field.id}" type="checkbox"${values[field.id] ? " checked" : ""}>
          <span class="switch-track" aria-hidden="true"></span>
        </span>
      </label>`;
    }

    return "";
  }

  function renderForm() {
    const calc = CALCULATORS[state.current];
    const values = state.values[state.current];
    const markup = calc.groups
      .map(
        (group) => `<div class="form-group">
          <div class="form-group-title">${esc(group.title)}</div>
          <div class="form-grid">
            ${group.fields.map((field) => fieldMarkup(field, values)).join("")}
          </div>
        </div>`,
      )
      .join("");
    $("calcForm").innerHTML = markup;
    bindFormEvents();
  }

  function readValue(input, field) {
    if (field.type === "switch") return input.checked;
    if (field.type === "number") {
      return input.value === "" ? field.default : input.value;
    }
    return input.value;
  }

  function bindFormEvents() {
    const form = $("calcForm");
    const calc = CALCULATORS[state.current];
    const fields = calc.groups.flatMap((group) => group.fields);
    const byId = Object.fromEntries(fields.map((field) => [field.id, field]));

    form.querySelectorAll("[data-field-id]").forEach((input) => {
      const field = byId[input.dataset.fieldId];
      if (!field) return;
      const eventName =
        input.type === "checkbox" || input.tagName === "SELECT"
          ? "change"
          : "input";
      input.addEventListener(eventName, () => {
        state.values[state.current][field.id] = readValue(input, field);
        syncVisibility();
        recalc();
      });
    });

    form.querySelectorAll("[data-segment]").forEach((button) => {
      button.addEventListener("click", () => {
        const fieldId = button.dataset.segment;
        state.values[state.current][fieldId] = button.dataset.value;
        button.parentElement.querySelectorAll("button").forEach((item) => {
          const active = item === button;
          item.classList.toggle("is-active", active);
          item.setAttribute("aria-pressed", String(active));
        });
        syncVisibility();
        recalc();
      });
    });
  }

  function syncVisibility() {
    const calc = CALCULATORS[state.current];
    const values = state.values[state.current];
    calc.groups.forEach((group) => {
      group.fields.forEach((field) => {
        if (!field.showIf) return;
        const element = $("calcForm").querySelector(
          `[data-field="${field.id}"]`,
        );
        if (element) {
          element.classList.toggle("is-hidden", !field.showIf(values));
        }
      });
    });
  }

  // -------------------------------------------------------------------
  // Рендер результатов
  // -------------------------------------------------------------------

  function impactRow(item) {
    const value = item.percent ? pct(item.value) : rub(item.value);
    return `<div class="impact-row">
      <div class="impact-row-label">${esc(item.label)}${item.note ? `<small>${esc(item.note)}</small>` : ""}</div>
      <div class="impact-row-value">${value}</div>
    </div>`;
  }

  function renderResults(computed) {
    const tax = computed.tax;
    const inflation = computed.inflation;
    const taxValue =
      tax.isRefund && tax.total > 0 ? `−${rub(tax.total)}` : rub(tax.total);
    const inflationBadge =
      inflation.benefit != null
        ? inflation.benefit >= 0
          ? `+${rub(inflation.benefit)}`
          : rub(inflation.benefit)
        : signedLoss(inflation.loss);
    const todayRow = inflation.rows.find(
      (item) => item.label === "В сегодняшних деньгах",
    );
    const purchasingRow = inflation.rows.find((item) =>
      item.label.startsWith("Покупательная способность"),
    );
    const totalRow = todayRow || purchasingRow;
    const inflationRows = totalRow
      ? inflation.rows.filter((item) => item !== totalRow)
      : inflation.rows;
    const inflationTotalLabel = totalRow ? totalRow.label : "Покупательная способность";
    const inflationTotalValue = totalRow ? totalRow.value : inflation.realValue;

    const metrics = computed.metrics
      .map((item) => {
        const accent = item.accent ? ` accent-${item.accent}` : "";
        return `<article class="metric-card${accent}">
          <div class="metric-label">${esc(item.label)}</div>
          <div class="metric-value">${esc(item.value)}</div>
          ${item.note ? `<div class="metric-note">${esc(item.note)}</div>` : ""}
        </article>`;
      })
      .join("");

    const chips = computed.hero.chips
      .map((chip) => `<span class="result-chip">${esc(chip)}</span>`)
      .join("");

    $("calcResults").innerHTML = `
      <div class="result-hero">
        <div class="result-hero-top">
          <span class="result-eyebrow">${esc(computed.hero.eyebrow)}</span>
          <span class="result-free">0 ₽ · без токенов</span>
        </div>
        <div class="result-value">${esc(computed.hero.value)}</div>
        <p class="result-caption">${esc(computed.hero.caption)}</p>
        <div class="result-chips">${chips}</div>
      </div>

      <div class="metrics-grid">${metrics}</div>

      <div class="breakdown-grid">
        <article class="impact-card${tax.isRefund ? " tax-refund" : ""}">
          <div class="impact-head">
            <span class="impact-icon">${iconUse("i-receipt")}</span>
            <div class="impact-title">
              <h3>${esc(tax.title)}</h3>
              <p>Отдельно от основного расчёта</p>
            </div>
            <span class="impact-badge">${taxValue}</span>
          </div>
          <div class="impact-rows">${tax.rows.map(impactRow).join("")}</div>
          <div class="impact-total">
            <span>${tax.isRefund ? "К возврату" : "Итого налогов"}</span>
            <strong>${taxValue}</strong>
          </div>
          <p class="impact-note">${esc(tax.note)}</p>
        </article>

        <article class="impact-card inflation-card">
          <div class="impact-head">
            <span class="impact-icon">${iconUse("i-trend")}</span>
            <div class="impact-title">
              <h3>Влияние инфляции</h3>
              <p>${esc(inflation.realLabel)} ${pct(inflation.realAnnualReturn)}</p>
            </div>
            <span class="impact-badge">${inflationBadge}</span>
          </div>
          <div class="impact-rows">${inflationRows.map(impactRow).join("")}</div>
          <div class="impact-total">
            <span>${inflationTotalLabel}</span>
            <strong>${rub(inflationTotalValue)}</strong>
          </div>
          <p class="impact-note">${esc(inflation.note)}</p>
        </article>
      </div>
    `;
  }

  function renderSpotlight(calc, computed) {
    $("spotlightIcon").innerHTML = iconUse(calc.icon);
    $("spotlightName").textContent = calc.name;
    $("spotlightLabel").textContent = computed.hero.eyebrow;
    $("spotlightValue").textContent = computed.hero.value;
    $("spotlightChips").innerHTML = computed.hero.chips
      .slice(0, 2)
      .map((chip) => `<span class="spotlight-chip">${esc(chip)}</span>`)
      .join("");
  }

  function recalc() {
    const calc = CALCULATORS[state.current];
    try {
      const computed = calc.compute(state.values[state.current]);
      state.lastComputed = computed;
      renderResults(computed);
      renderSpotlight(calc, computed);
    } catch (error) {
      console.error("Не удалось пересчитать калькулятор", error);
      $("calcResults").innerHTML = `
        <div class="result-hero">
          <div class="result-hero-top">
            <span class="result-eyebrow">Ошибка расчёта</span>
          </div>
          <div class="result-value">Проверьте параметры</div>
          <p class="result-caption">Одно из значений не удалось разобрать. Сбросьте форму и попробуйте снова.</p>
        </div>`;
    }
  }

  // -------------------------------------------------------------------
  // Переключение калькуляторов и меню
  // -------------------------------------------------------------------

  function updateActiveNav() {
    document.querySelectorAll("[data-calc]").forEach((element) => {
      const active = element.dataset.calc === state.current;
      element.classList.toggle("is-active", active);
      if (element.classList.contains("drawer-item") || element.classList.contains("quick-pill")) {
        if (active) {
          element.setAttribute("aria-current", "page");
        } else {
          element.removeAttribute("aria-current");
        }
      }
    });
  }

  function selectCalculator(id, options = {}) {
    const calc = CALCULATORS[id];
    if (!calc) return;
    const updateHash = options.updateHash !== false;
    const scroll = Boolean(options.scroll);

    state.current = id;
    $("formTitle").textContent = calc.name;
    $("formSubtitle").textContent = calc.subtitle;
    $("formIcon").innerHTML = iconUse(calc.icon);
    renderForm();
    recalc();
    updateActiveNav();
    document.title = `${calc.name} — Калькуляторы ФинХелл`;

    if (updateHash) {
      try {
        history.replaceState(null, "", `#${id}`);
      } catch (error) {
        location.hash = id;
      }
    }

    if (scroll) {
      const card = $("calcFormCard");
      card.scrollIntoView({ behavior: "smooth", block: "start" });
      if (typeof card.focus === "function") {
        card.focus({ preventScroll: true });
      }
    }
  }

  const drawer = $("calcDrawer");
  const backdrop = $("drawerBackdrop");
  const trigger = $("menuTrigger");
  const closeButton = $("drawerClose");
  let lastFocused = null;

  function openDrawer() {
    lastFocused = document.activeElement;
    document.body.classList.add("drawer-open");
    trigger.setAttribute("aria-expanded", "true");
    drawer.setAttribute("aria-hidden", "false");
    window.requestAnimationFrame(() => closeButton.focus({ preventScroll: true }));
  }

  function closeDrawer(options = {}) {
    const restoreFocus = options.restoreFocus !== false;
    document.body.classList.remove("drawer-open");
    trigger.setAttribute("aria-expanded", "false");
    drawer.setAttribute("aria-hidden", "true");
    if (restoreFocus && lastFocused instanceof HTMLElement) {
      lastFocused.focus({ preventScroll: true });
    }
  }

  function trapFocus(event) {
    const selector =
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusable = Array.from(drawer.querySelectorAll(selector)).filter(
      (element) => element.offsetParent !== null,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function setTheme(theme, persist = true) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    if (persist) {
      try {
        localStorage.setItem("finhell-theme", next);
      } catch (error) {
        // localStorage может быть отключён — тема просто не сохранится.
      }
    }
    const button = $("themeToggle");
    if (button) {
      const label =
        next === "dark" ? "Включить светлую тему" : "Включить тёмную тему";
      button.setAttribute("aria-label", label);
      button.title = label;
    }
  }

  function resetCurrent() {
    const calc = CALCULATORS[state.current];
    calc.groups.forEach((group) => {
      group.fields.forEach((field) => {
        state.values[state.current][field.id] = field.default;
      });
    });
    renderForm();
    recalc();
  }

  function bindStaticEvents() {
    $("calcForm").addEventListener("submit", (event) => event.preventDefault());
    trigger.addEventListener("click", openDrawer);
    closeButton.addEventListener("click", () => closeDrawer());
    backdrop.addEventListener("click", () => closeDrawer());

    document.addEventListener("keydown", (event) => {
      if (!document.body.classList.contains("drawer-open")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer();
      } else if (event.key === "Tab") {
        trapFocus(event);
      }
    });

    document.querySelectorAll(".drawer-item").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const id = link.dataset.calc;
        closeDrawer({ restoreFocus: false });
        selectCalculator(id, { scroll: true });
      });
    });

    document.querySelectorAll(".quick-pill").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        selectCalculator(link.dataset.calc, { scroll: true });
      });
    });

    $("resetBtn").addEventListener("click", resetCurrent);

    $("themeToggle").addEventListener("click", () => {
      const current =
        document.documentElement.dataset.theme === "dark" ? "dark" : "light";
      setTheme(current === "dark" ? "light" : "dark");
    });

    window.addEventListener("hashchange", () => {
      const id = location.hash.replace("#", "");
      if (CALCULATORS[id]) {
        if (id !== state.current) {
          selectCalculator(id, { updateHash: false });
        }
      } else {
        selectCalculator("mortgage", { updateHash: true });
      }
    });

    window.addEventListener("storage", (event) => {
      if (
        event.key === "finhell-theme" &&
        (event.newValue === "dark" || event.newValue === "light")
      ) {
        setTheme(event.newValue, false);
      }
    });
  }

  function init() {
    bindStaticEvents();
    setTheme(
      document.documentElement.dataset.theme === "dark" ? "dark" : "light",
      false,
    );
    const hash = location.hash.replace("#", "");
    const initial = CALCULATORS[hash] ? hash : "mortgage";
    selectCalculator(initial, { updateHash: true, scroll: false });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
