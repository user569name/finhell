/* ФинХелл — клиентская логика симулятора. Без внешних зависимостей. */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const money = new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  });
  const numberFmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

  const state = {
    result: null,
    instruments: [],
  };

  const COLORS = {
    cash: "#68809a",
    deposit: "#37d39b",
    ofz: "#5aa9ff",
    corporate_bonds: "#9b8cff",
    stocks: "#ffb454",
    gold: "#f5d76e",
    real_estate: "#ff8a5c",
    crypto: "#ff6b9d",
  };

  const FALLBACK_INSTRUMENTS = [
    { key: "cash", short_name: "Деньги", annual_return: 0.03 },
    { key: "deposit", short_name: "Вклад", annual_return: 0.15 },
    { key: "ofz", short_name: "ОФЗ", annual_return: 0.135 },
    { key: "corporate_bonds", short_name: "Корп. облигации", annual_return: 0.165 },
    { key: "stocks", short_name: "Акции", annual_return: 0.20 },
    { key: "gold", short_name: "Золото", annual_return: 0.11 },
    { key: "real_estate", short_name: "Недвижимость", annual_return: 0.13 },
    { key: "crypto", short_name: "Крипта", annual_return: 0.28 },
  ];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function pct(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${(Number(value) * 100).toFixed(digits).replace(".", ",")}%`;
  }

  function compactMoney(value) {
    const v = Number(value) || 0;
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1).replace(".", ",")} млрд`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1).replace(".", ",")} млн`;
    if (Math.abs(v) >= 1e3) return `${Math.round(v / 1e3)} тыс.`;
    return Math.round(v).toString();
  }

  function readNumber(id) {
    const element = $(id);
    if (!element) return 0;
    const value = Number.parseFloat(element.value);
    return Number.isFinite(value) ? value : 0;
  }

  function addDebtRow() {
    const list = $("#debt-list");
    if (!list) return;
    const row = document.createElement("div");
    row.className = "debt-row";
    row.innerHTML = `
      <input type="text" placeholder="Название" value="Кредит">
      <input type="number" placeholder="Остаток, ₽" min="0" step="1000">
      <input type="number" placeholder="Ставка, %" min="0" step="0.1">
      <input type="number" placeholder="Платёж, ₽" min="0" step="500">
      <button type="button" class="icon-btn" title="Удалить">×</button>
    `;
    row.querySelector(".icon-btn").addEventListener("click", () => row.remove());
    list.appendChild(row);
  }

  function initRiskSliders() {
    $$("#risk-factors .risk-row").forEach((row) => {
      const input = row.querySelector('input[type="range"]');
      const output = row.querySelector("output");
      const update = () => {
        output.textContent = `${input.value}%`;
        input.style.setProperty("--fill", `${input.value}%`);
      };
      input.addEventListener("input", update);
      update();
    });
  }

  function bindHorizon() {
    const input = $("#horizon_months");
    const buttons = $$("#horizon-quick .quick");
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.dataset.months;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
      });
    });
    input.addEventListener("input", () => {
      buttons.forEach((item) => {
        item.classList.toggle("active", item.dataset.months === input.value);
      });
    });
  }

  async function loadInstruments() {
    try {
      const response = await fetch("/instruments");
      if (!response.ok) throw new Error("catalog");
      const data = await response.json();
      state.instruments = data.instruments || [];
    } catch (error) {
      state.instruments = FALLBACK_INSTRUMENTS;
    }
    renderReturnInputs();
  }

  function renderReturnInputs() {
    const grid = $("#return-grid");
    const checkbox = $("#use_custom_returns");
    if (!grid) return;
    grid.innerHTML = state.instruments.map((instrument) => `
      <label>
        ${esc(instrument.short_name)}
        <input type="number" data-key="${esc(instrument.key)}"
               min="-50" max="150" step="0.5"
               value="${(Number(instrument.annual_return) * 100).toFixed(1)}"
               disabled>
      </label>
    `).join("");
    if (checkbox) {
      checkbox.addEventListener("change", () => {
        $$("#return-grid input").forEach((input) => {
          input.disabled = !checkbox.checked;
        });
      });
    }
  }

  function collectPayload() {
    const riskFactors = {};
    $$("#risk-factors .risk-row").forEach((row) => {
      const input = row.querySelector('input[type="range"]');
      riskFactors[row.dataset.risk] = Number(input.value) / 100;
    });

    const debts = $$("#debt-list .debt-row").map((row) => {
      const inputs = row.querySelectorAll("input");
      const balance = Number.parseFloat(inputs[1].value);
      if (!Number.isFinite(balance) || balance <= 0) return null;
      const rate = Number.parseFloat(inputs[2].value);
      const payment = Number.parseFloat(inputs[3].value);
      return {
        name: inputs[0].value.trim() || "Долг",
        balance,
        annual_rate: Number.isFinite(rate) ? rate / 100 : 0,
        monthly_payment: Number.isFinite(payment) ? payment : 0,
      };
    }).filter(Boolean);

    const returnOverrides = {};
    if ($("#use_custom_returns")?.checked) {
      $$("#return-grid input").forEach((input) => {
        const value = Number.parseFloat(input.value);
        if (Number.isFinite(value)) {
          returnOverrides[input.dataset.key] = value / 100;
        }
      });
    }

    const goalValue = $("#goal_amount").value;
    const profile = $('input[name="risk_profile"]:checked');

    return {
      initial_capital: readNumber("#initial_capital"),
      monthly_contribution: readNumber("#monthly_contribution"),
      monthly_expenses: readNumber("#monthly_expenses"),
      horizon_months: Math.max(1, Math.round(readNumber("#horizon_months"))),
      emergency_fund_months: Math.max(0, Math.round(readNumber("#emergency_fund_months"))),
      goal_amount: goalValue ? Number.parseFloat(goalValue) : null,
      risk_profile: profile ? profile.value : "balanced",
      inflation_rate: readNumber("#inflation_rate") / 100,
      risk_factors: riskFactors,
      return_overrides: returnOverrides,
      debts,
      include_crypto: true,
      monte_carlo_paths: 800,
      seed: 42,
    };
  }

  function extractError(data) {
    if (!data) return "Неизвестная ошибка.";
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        return `${field ? field + ": " : ""}${item.msg}`;
      }).join("; ");
    }
    return JSON.stringify(data);
  }

  function showError(message) {
    const results = $("#results");
    results.innerHTML = `
      <div class="error-box">
        <strong>Не удалось рассчитать план.</strong><br>
        ${esc(message)}
      </div>
    `;
  }

  async function submitSimulation(event) {
    event.preventDefault();
    const button = $("#submit-btn");
    const original = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="loading"></span>Считаем сценарии...';

    try {
      const response = await fetch("/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectPayload()),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(extractError(data));
      renderResults(data);
      if (window.innerWidth < 1180) {
        $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (error) {
      showError(error.message || String(error));
    } finally {
      button.disabled = false;
      button.innerHTML = original;
    }
  }

  async function submitBond(event) {
    event.preventDefault();
    const payload = {
      face_value: readNumber("#bond_face"),
      price: readNumber("#bond_price"),
      coupon_rate: readNumber("#bond_coupon") / 100,
      coupons_per_year: Math.max(1, Math.round(readNumber("#bond_freq"))),
      years_to_maturity: readNumber("#bond_years"),
      reinvest_rate: readNumber("#bond_reinvest") / 100,
    };
    try {
      const response = await fetch("/bond/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(extractError(data));
      renderBondResult(data);
    } catch (error) {
      $("#bond-result").innerHTML = `<div class="error-box">${esc(error.message)}</div>`;
    }
  }

  function drawChart(data) {
    const canvas = $("#chart");
    if (!canvas) return;
    const series = data.projection.series || [];
    if (!series.length) return;

    const rect = canvas.getBoundingClientRect();
    const width = Math.max(320, rect.width);
    const height = Math.max(240, rect.height);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const pad = { left: 76, right: 18, top: 16, bottom: 34 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const maxX = Math.max(1, series[series.length - 1].month);
    const maxY = Math.max(
      1,
      ...series.map((point) => Math.max(point.p90, point.contributed))
    ) * 1.06;
    const x = (month) => pad.left + (month / maxX) * innerW;
    const y = (value) => pad.top + innerH - (value / maxY) * innerH;

    ctx.strokeStyle = "rgba(143,166,191,0.12)";
    ctx.fillStyle = "#8fa6bf";
    ctx.font = "11px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const ticks = 5;
    for (let index = 0; index <= ticks; index += 1) {
      const value = (maxY / ticks) * index;
      const py = y(value);
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(width - pad.right, py);
      ctx.stroke();
      ctx.fillText(compactMoney(value), pad.left - 10, py);
    }

    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const step = Math.max(1, Math.ceil(maxX / 6));
    for (let month = 0; month <= maxX; month += step) {
      const label = maxX > 24 ? `${Math.round(month / 12)} г.` : `${month} мес.`;
      ctx.fillText(label, x(month), height - pad.bottom + 12);
    }
    if (maxX % step !== 0) {
      const label = maxX > 24 ? `${Math.round(maxX / 12)} г.` : `${maxX} мес.`;
      ctx.fillText(label, x(maxX), height - pad.bottom + 12);
    }

    ctx.beginPath();
    series.forEach((point, index) => {
      const px = x(point.month);
      const py = y(point.p90);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    for (let index = series.length - 1; index >= 0; index -= 1) {
      const point = series[index];
      ctx.lineTo(x(point.month), y(point.p10));
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(90,169,255,0.12)";
    ctx.fill();

    ctx.beginPath();
    series.forEach((point, index) => {
      const px = x(point.month);
      const py = y(point.contributed);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.setLineDash([5, 5]);
    ctx.strokeStyle = "rgba(143,166,191,0.7)";
    ctx.lineWidth = 1.3;
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.beginPath();
    series.forEach((point, index) => {
      const px = x(point.month);
      const py = y(point.p50);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.strokeStyle = "#37d39b";
    ctx.lineWidth = 2.4;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    const last = series[series.length - 1];
    ctx.beginPath();
    ctx.arc(x(last.month), y(last.p50), 4, 0, Math.PI * 2);
    ctx.fillStyle = "#37d39b";
    ctx.fill();
    ctx.strokeStyle = "#07101d";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  function renderResults(data) {
    state.result = data;
    const s = data.summary;
    const summary = data.allocation_summary || {};

    const kpis = [
      {
        label: "Капитал через срок",
        value: money.format(s.final_p50),
        sub: `p10 ${money.format(s.final_p10)} · p90 ${money.format(s.final_p90)}`,
        accent: true,
      },
      {
        label: "В реальных деньгах",
        value: money.format(s.final_real_p50),
        sub: "в ценах сегодняшнего дня",
      },
      {
        label: "Вложено всего",
        value: money.format(s.total_contributions),
        sub: `из них старт ${money.format(s.initial_capital)}`,
      },
      {
        label: "Прибыль (p50)",
        value: money.format(s.profit_p50),
        sub: `${pct(s.return_pct)} за срок`,
        cls: s.profit_p50 >= 0 ? "positive" : "negative",
      },
      {
        label: "Среднегодовая доходность",
        value: s.irr_annual === null || s.irr_annual === undefined ? "—" : pct(s.irr_annual),
        sub: "IRR с учётом ежемесячных взносов",
      },
      {
        label: "Риск портфеля",
        value: esc(s.risk_label),
        sub: `оценка ${pct(s.portfolio_risk)} · волатильность ${pct(s.portfolio_volatility)}`,
      },
      s.goal_amount
        ? {
            label: "Вероятность цели",
            value: pct(s.probability_goal, 0),
            sub: `цель ${money.format(s.goal_amount)}`,
          }
        : {
            label: "Вероятность убытка",
            value: pct(s.probability_loss, 0),
            sub: "капитал меньше вложенного",
          },
      {
        label: "Просадка p90",
        value: pct(s.max_drawdown_p90),
        sub: `медиана ${pct(s.max_drawdown_median)}`,
      },
    ];

    const kpiHtml = kpis.map((item) => `
      <div class="kpi ${item.accent ? "accent" : ""}">
        <div class="kpi-label">${esc(item.label)}</div>
        <div class="kpi-value ${item.cls || ""}">${item.value}</div>
        <div class="kpi-sub">${item.sub}</div>
      </div>
    `).join("");

    const allocHtml = data.allocation.map((item) => {
      const color = COLORS[item.key] || "#5aa9ff";
      return `
        <div class="alloc-row">
          <div class="alloc-name">
            <b>${esc(item.short_name)}</b>
            <small>${esc(item.name)}</small>
          </div>
          <div class="alloc-bar">
            <div class="alloc-fill" style="width:${Math.max(2, item.share * 100)}%;background:${color}"></div>
          </div>
          <div class="alloc-value">
            ${pct(item.share)}
            <small>${money.format(item.initial_amount)} · ${money.format(item.monthly_amount)}/мес</small>
          </div>
        </div>
      `;
    }).join("");

    const sequenceHtml = data.sequence.map((stage) => {
      const chips = stage.instruments.map((instrument) => {
        let detail = "";
        if (instrument.key === "debt_payoff") {
          detail = money.format(instrument.amount);
        } else if (instrument.monthly_amount > 0) {
          detail = `${pct(instrument.share, 0)} · ${money.format(instrument.monthly_amount)}/мес`;
        } else if (instrument.amount > 0) {
          detail = `${pct(instrument.share, 0)} · ${money.format(instrument.amount)}`;
        }
        return `<span class="chip"><b>${esc(instrument.name)}</b>${detail ? " · " + detail : ""}</span>`;
      }).join("");
      const amount = stage.monthly_amount > 0
        ? `${money.format(stage.monthly_amount)}/мес`
        : stage.amount > 0 ? money.format(stage.amount) : "";
      return `
        <div class="stage">
          <div class="stage-num">${stage.step}</div>
          <div class="stage-body">
            <div class="stage-head">
              <span class="stage-period">${esc(stage.period)}</span>
              <span class="stage-title">${esc(stage.title)}</span>
              ${amount ? `<span class="pill">${amount}</span>` : ""}
            </div>
            <p class="stage-desc">${esc(stage.description)}</p>
            <p class="stage-reason">${esc(stage.reason)}</p>
            ${chips ? `<div class="chips">${chips}</div>` : ""}
          </div>
        </div>
      `;
    }).join("");

    const scenarioHtml = data.scenarios.length ? `
      <section class="panel card">
        <h3>Сравнение профилей</h3>
        <p class="card-sub">Одинаковые вводные, разные допустимые риски. p50 — медиана.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Профиль</th><th>p10</th><th>p50</th><th>p90</th><th>Доходность</th><th>Риск</th></tr></thead>
            <tbody>
              ${data.scenarios.map((scenario) => `
                <tr class="${scenario.is_recommended ? "recommended" : ""}">
                  <td><b>${esc(scenario.label)}</b>${scenario.is_recommended ? " · ваш" : ""}</td>
                  <td>${money.format(scenario.final_p10)}</td>
                  <td><b>${money.format(scenario.final_p50)}</b></td>
                  <td>${money.format(scenario.final_p90)}</td>
                  <td>${pct(scenario.expected_return)}</td>
                  <td>${esc(scenario.risk_label)} · ${pct(scenario.risk)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </section>
    ` : "";

    const ladderHtml = data.bond_ladder.length ? `
      <section class="panel card">
        <h3>Лестница облигаций</h3>
        <p class="card-sub">Разбейте облигационную часть на выпуски с разными сроками погашения.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Инструмент</th><th>Погашение</th><th>Доля портфеля</th><th>Сумма</th><th>Доходность</th></tr></thead>
            <tbody>
              ${data.bond_ladder.map((row) => `
                <tr>
                  <td>${esc(row.name)}</td>
                  <td>${row.maturity_months} мес.</td>
                  <td>${pct(row.share_of_portfolio)}</td>
                  <td>${money.format(row.approx_amount)}</td>
                  <td>${pct(row.expected_yield)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </section>
    ` : "";

    const yearlyHtml = data.projection.yearly.length ? `
      <section class="panel card">
        <h3>По годам</h3>
        <p class="card-sub">Как меняется коридор капитала и сумма вложений.</p>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Период</th><th>Вложено</th><th>p10</th><th>p50</th><th>p90</th></tr></thead>
            <tbody>
              ${data.projection.yearly.map((row) => `
                <tr>
                  <td>${row.month % 12 === 0 ? `${row.month / 12} г.` : `${row.month} мес.`}</td>
                  <td>${money.format(row.contributed)}</td>
                  <td>${money.format(row.p10)}</td>
                  <td><b>${money.format(row.p50)}</b></td>
                  <td>${money.format(row.p90)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </section>
    ` : "";

    const debtHtml = data.debt_advice.has_debts ? `
      <section class="panel card">
        <h3>Долги</h3>
        <p class="card-sub">${esc(data.debt_advice.recommendation)}</p>
        <div class="debt-box">
          ${data.debt_advice.items.map((item) => `
            <div class="debt-item">
              <span><b>${esc(item.name)}</b> · ${money.format(item.balance)} · ${pct(item.annual_rate)}</span>
              <span>
                ${item.high_rate ? "дорогой" : "плановый"} · платёж ${money.format(item.monthly_payment)}
                ${item.payoff_from_capital > 0 ? ` · погасить ${money.format(item.payoff_from_capital)}` : ""}
              </span>
            </div>
          `).join("")}
        </div>
        ${data.debt_advice.payoff > 0 ? `
          <p class="card-sub" style="margin-top:10px">
            Досрочно: ${money.format(data.debt_advice.payoff)} ·
            экономия процентов: ${money.format(data.debt_advice.saved_interest)}
          </p>
        ` : ""}
      </section>
    ` : "";

    const warningHtml = data.warnings.length ? `
      <section class="panel card">
        <h3>На что обратить внимание</h3>
        <div class="warning-list">
          ${data.warnings.map((warning) => `<div class="warning">${esc(warning)}</div>`).join("")}
        </div>
      </section>
    ` : "";

    $("#results").innerHTML = `
      <div class="result-head">
        <div>
          <h2>${esc(data.profile.label)} план</h2>
          <p>
            ${s.horizon_years} лет · ${money.format(s.monthly_contribution)}/мес ·
            инфляция ${pct(data.input.inflation_rate)} ·
            ${data.projection.paths} сценариев
          </p>
        </div>
        <div class="pill">${data.allocation.length} инструментов</div>
      </div>
      <div class="kpi-grid">${kpiHtml}</div>
      <section class="panel card">
        <div class="chart-head">
          <div>
            <h3>Диапазон капитала</h3>
            <p class="card-sub">Медиана и коридор p10–p90 по сценариям Монте-Карло.</p>
          </div>
          <div class="legend">
            <span class="legend-item"><span class="legend-dot" style="background:#37d39b"></span>p50</span>
            <span class="legend-item"><span class="legend-dot" style="background:rgba(90,169,255,.35)"></span>p10–p90</span>
            <span class="legend-item"><span class="legend-dot" style="background:#68809a"></span>вложено</span>
          </div>
        </div>
        <div class="chart-wrap"><canvas id="chart"></canvas></div>
      </section>
      <section class="panel card">
        <h3>Структура портфеля</h3>
        <p class="card-sub">
          Ожидаемая доходность ${pct(summary.expected_return)} ·
          реальная ${pct(summary.real_expected_return)} ·
          риск ${esc(summary.risk_label)} (${pct(summary.risk)})
        </p>
        <div class="alloc-list">${allocHtml}</div>
      </section>
      <section class="panel card">
        <h3>Последовательность действий</h3>
        <p class="card-sub">Сначала защита и долги, затем облигации, потом рост и фиксация результата.</p>
        <div class="sequence">${sequenceHtml}</div>
      </section>
      ${scenarioHtml}
      ${ladderHtml}
      ${yearlyHtml}
      ${debtHtml}
      ${warningHtml}
      <p class="disclaimer">${esc(data.disclaimer)}</p>
    `;

    requestAnimationFrame(() => drawChart(data));
  }

  function renderBondResult(data) {
    $("#bond-result").innerHTML = `
      <div class="bond-kpis">
        <div class="bond-kpi"><span>YTM</span><b class="positive">${pct(data.ytm)}</b></div>
        <div class="bond-kpi"><span>Текущая доходность</span><b>${pct(data.current_yield)}</b></div>
        <div class="bond-kpi"><span>Дюрация</span><b>${Number(data.macaulay_duration_years).toFixed(2).replace(".", ",")} г.</b></div>
        <div class="bond-kpi"><span>Купон в год</span><b>${money.format(data.annual_coupon_income)}</b></div>
        <div class="bond-kpi"><span>Прибыль без реинвестирования</span><b>${money.format(data.profit)}</b></div>
        <div class="bond-kpi"><span>Итог с реинвестированием</span><b>${money.format(data.future_value_reinvested)}</b></div>
        <div class="bond-kpi"><span>Всего купонов</span><b>${money.format(data.total_coupons)}</b></div>
        <div class="bond-kpi"><span>Выплаты всего</span><b>${money.format(data.total_payments)}</b></div>
      </div>
      <p class="bond-note">${esc(data.note)}</p>
    `;
  }

  document.addEventListener("DOMContentLoaded", () => {
    initRiskSliders();
    bindHorizon();
    addDebtRow();
    $("#sim-form").addEventListener("submit", submitSimulation);
    $("#add-debt").addEventListener("click", addDebtRow);
    $("#bond-form").addEventListener("submit", submitBond);
    window.addEventListener("resize", () => {
      if (state.result) drawChart(state.result);
    });
    loadInstruments();
  });
})();
