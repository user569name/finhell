(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const nf0 = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const AUTH_STORAGE_KEY = "finhell-auth";
  const RISK_LABELS = { low: "Низкий риск", medium: "Средний риск", high: "Высокий риск" };
  const RISK_SHORT = { low: "Низкий", medium: "Средний", high: "Высокий" };
  const ASSET_COLORS = {
    cash: "#9ad8a4",
    savings: "#5cc46e",
    deposit: "#21a038",
    ofz_short: "#0f7a25",
    ofz_long: "#0b5f1d",
    corporate: "#f0a51d",
    municipal: "#2f6fed",
    real_estate: "#8b5cf6",
  };
  const MACRO_FIELDS = {
    ov_key_rate: "key_rate",
    ov_inflation_expected: "inflation_expected",
    ov_deposit_rate: "deposit_rate",
    ov_mortgage_rate: "mortgage_rate",
    ov_ofz_yield_10y: "ofz_yield_10y",
    ov_corporate_yield: "corporate_yield",
    ov_real_estate_growth: "real_estate_growth",
    ov_rent_yield: "rent_yield",
  };

  const state = {
    result: null,
    macro: null,
    instruments: null,
    selectedOptionId: null,
    chatHistory: [],
    chatBusy: false,
    busy: false,
    toastTimer: null,
    lastPayload: null,
    authMode: "login",
  };

  // ---------------------------------------------------------------------
  // Форматирование
  // ---------------------------------------------------------------------
  function money(value, digits = 0) {
    const number = Number(value) || 0;
    return `${digits ? nf2.format(number) : nf0.format(number)} ₽`;
  }

  function compactMoney(value) {
    const number = Number(value) || 0;
    const abs = Math.abs(number);
    if (abs >= 1e9) return `${nf2.format(number / 1e9)} млрд ₽`;
    if (abs >= 1e6) return `${nf1.format(number / 1e6)} млн ₽`;
    if (abs >= 1e3) return `${nf0.format(number / 1e3)} тыс. ₽`;
    return `${nf0.format(number)} ₽`;
  }

  function pct(value, digits = 1) {
    const number = (Number(value) || 0) * 100;
    return `${number.toFixed(digits).replace(".", ",")}%`;
  }

  function pct100(value, digits = 0) {
    const number = (Number(value) || 0) * 100;
    return `${number.toFixed(digits).replace(".", ",")}%`;
  }

  function signedPct(value, digits = 1) {
    const number = Number(value) || 0;
    const text = `${Math.abs(number * 100).toFixed(digits).replace(".", ",")}%`;
    return number > 0 ? `+${text}` : number < 0 ? `−${text}` : text;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatText(value) {
    let text = escapeHtml(value);
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\n\n/g, "<br><br>");
    text = text.replace(/\n/g, "<br>");
    return text;
  }

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function sourceStatus(point) {
    if (!point) return "fallback";
    if (point.is_fallback) return "fallback";
    return "live";
  }

  function sourceLabel(point) {
    if (!point) return "нет данных";
    return point.source || (point.is_fallback ? "демо-данные" : "источник");
  }

  function dateLabel(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  // ---------------------------------------------------------------------
  // Авторизация
  // ---------------------------------------------------------------------
  function loadAuth() {
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.token) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function saveAuth(auth) {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
  }

  function clearAuth() {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  }

  function setAuthError(message) {
    const box = $("authError");
    if (!box) return;
    box.textContent = message || "";
    box.hidden = !message;
  }

  function showAuthGate(message = "") {
    const gate = $("authGate");
    if (!gate) return;
    gate.hidden = false;
    document.body.classList.add("auth-locked");
    setAuthError(message);
    window.setTimeout(() => $("authEmail")?.focus(), 60);
  }

  function hideAuthGate() {
    const gate = $("authGate");
    if (gate) gate.hidden = true;
    document.body.classList.remove("auth-locked");
    setAuthError("");
  }

  function updateAuthUser() {
    const auth = loadAuth();
    const wrap = $("authUser");
    const email = $("authUserEmail");
    if (wrap && email) {
      const value = auth?.user?.email || "";
      email.textContent = value;
      wrap.hidden = !value;
    }
  }

  function setAuthMode(mode) {
    state.authMode = mode === "register" ? "register" : "login";
    const register = state.authMode === "register";
    document.querySelectorAll("[data-auth-mode]").forEach((tab) => {
      const active = tab.dataset.authMode === state.authMode;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    const nameField = $("authNameField");
    const confirmField = $("authConfirmField");
    if (nameField) nameField.hidden = !register;
    if (confirmField) confirmField.hidden = !register;
    const title = $("authTitle");
    const subtitle = $("authSubtitle");
    const submit = $("authSubmit");
    if (title) title.textContent = register ? "Регистрация" : "Вход в оптимизатор";
    if (subtitle) {
      subtitle.textContent = register
        ? "Создайте аккаунт по email — расчёты будут доступны после входа."
        : "Войдите по email, чтобы запускать расчёты и пользоваться AI-чатом.";
    }
    if (submit) submit.textContent = register ? "Создать аккаунт" : "Войти";
    const password = $("authPassword");
    if (password) password.autocomplete = register ? "new-password" : "current-password";
    setAuthError("");
  }

  async function submitAuth(event) {
    event.preventDefault();
    const register = state.authMode === "register";
    const email = $("authEmail").value.trim();
    const password = $("authPassword").value;
    const name = $("authName").value.trim();
    const confirm = $("authConfirm").value;

    if (!email || !email.includes("@")) {
      setAuthError("Введите корректный email.");
      $("authEmail").focus();
      return;
    }
    if (password.length < 8) {
      setAuthError("Пароль должен содержать минимум 8 символов.");
      $("authPassword").focus();
      return;
    }
    if (register && password !== confirm) {
      setAuthError("Пароли не совпадают.");
      $("authConfirm").focus();
      return;
    }

    const submit = $("authSubmit");
    submit.disabled = true;
    submit.textContent = register ? "Создаём аккаунт…" : "Входим…";
    setAuthError("");
    try {
      const data = await api(
        register ? "/api/v2/auth/register" : "/api/v2/auth/login",
        {
          method: "POST",
          body: JSON.stringify(register ? { email, password, name } : { email, password }),
        },
      );
      saveAuth({ token: data.token, user: data.user });
      updateAuthUser();
      hideAuthGate();
      await loadReference();
      showToast(register ? "Аккаунт создан. Добро пожаловать!" : `С возвращением, ${data.user.email}.`);
    } catch (error) {
      setAuthError(error.message || "Не удалось войти. Проверьте email и пароль.");
    } finally {
      submit.disabled = false;
      submit.textContent = register ? "Создать аккаунт" : "Войти";
    }
  }

  function bindAuthEvents() {
    document.querySelectorAll("[data-auth-mode]").forEach((tab) => {
      tab.addEventListener("click", () => setAuthMode(tab.dataset.authMode));
    });
    $("authForm").addEventListener("submit", submitAuth);
    $("logoutBtn").addEventListener("click", () => {
      clearAuth();
      window.location.reload();
    });
  }

  async function initAuth() {
    const auth = loadAuth();
    if (!auth?.token) {
      showAuthGate();
      return;
    }
    updateAuthUser();
    try {
      const me = await api("/api/v2/auth/me");
      saveAuth({ token: auth.token, user: me.user });
      updateAuthUser();
      hideAuthGate();
      await loadReference();
    } catch (_error) {
      clearAuth();
      showAuthGate("Сессия истекла. Войдите снова.");
    }
  }

  // ---------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------
  async function api(path, options = {}) {
    const auth = loadAuth();
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    if (auth?.token) {
      headers.Authorization = `Bearer ${auth.token}`;
    }
    const response = await fetch(path, { ...options, headers });
    if (!response.ok) {
      if (response.status === 401 && auth?.token) {
        clearAuth();
        showAuthGate("Сессия истекла. Войдите снова.");
      }
      let detail = response.statusText;
      try {
        const data = await response.json();
        detail = data.detail || data.message || JSON.stringify(data);
      } catch (_) {
        // ignore
      }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return response.json();
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  // ---------------------------------------------------------------------
  // Тема и сегменты
  // ---------------------------------------------------------------------
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("finhell-theme", theme);
    const icon = $("themeIcon");
    if (icon) {
      icon.innerHTML = theme === "dark"
        ? '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"></path>'
        : '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"></path>';
    }
    if (state.result && state.selectedOptionId) {
      window.requestAnimationFrame(() => drawCharts(findOption(state.selectedOptionId)));
    }
  }

  function bindSegmented(groupId, hiddenId) {
    const group = $(groupId);
    if (!group) return;
    group.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      group.querySelectorAll("button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      $(hiddenId).value = button.dataset.value;
    });
  }

  // ---------------------------------------------------------------------
  // Загрузка справочников
  // ---------------------------------------------------------------------
  async function loadReference() {
    const results = await Promise.allSettled([
      api("/api/v2/macro"),
      api("/api/v2/instruments"),
    ]);
    if (results[0].status === "fulfilled") {
      state.macro = results[0].value;
      Object.entries(MACRO_FIELDS).forEach(([id, key]) => {
        const field = $(id);
        const point = state.macro[key];
        if (field && point) {
          field.placeholder = (Number(point.value) * 100).toFixed(1).replace(".", ",");
        }
      });
    }
    if (results[1].status === "fulfilled") {
      state.instruments = results[1].value;
    }
  }

  // ---------------------------------------------------------------------
  // Сборка запроса
  // ---------------------------------------------------------------------
  function numberValue(id) {
    const field = $(id);
    if (!field) return null;
    const raw = field.value.trim();
    if (!raw) return null;
    const value = Number(raw.replace(",", "."));
    return Number.isFinite(value) ? value : null;
  }

  function buildPayload() {
    const capital = numberValue("capital");
    if (capital === null || capital < 0) {
      showToast("Укажите текущий капитал — число от 0.", true);
      $("capital").focus();
      return null;
    }
    const monthly = numberValue("monthly") ?? 0;
    if (monthly < 0) {
      showToast("Ежемесячный взнос не может быть отрицательным.", true);
      $("monthly").focus();
      return null;
    }
    const horizon = Number($("horizon_months").value) || 60;
    const monthlyExpenses = numberValue("monthly_expenses") ?? 0;
    const emergencyMonths = Math.max(0, Math.min(36, Math.round(numberValue("emergency_fund_months") ?? 0)));

    const profile = {
      capital,
      monthly,
      horizon_months: horizon,
      risk_tolerance: $("risk_tolerance").value,
      liquidity_need: $("liquidity_need").value,
      credit_willingness: $("credit_willingness").checked,
      credit_type: $("credit_type").value,
      monthly_expenses: monthlyExpenses,
      emergency_fund_months: emergencyMonths,
      region: $("region").value.trim() || "Москва",
    };
    const goal = numberValue("goal_amount");
    if (goal !== null && goal > 0) profile.goal_amount = goal;

    const mortgageBalance = numberValue("mortgage_balance");
    if (mortgageBalance !== null && mortgageBalance > 0) {
      const mortgageRate = numberValue("mortgage_rate");
      const fallbackRate = state.macro?.mortgage_rate?.value ?? 0.2;
      profile.existing_mortgage = {
        balance: mortgageBalance,
        annual_rate: (mortgageRate !== null ? mortgageRate : fallbackRate * 100) / 100,
        monthly_payment: Math.max(0, numberValue("mortgage_payment") ?? 0),
        remaining_months: Math.max(0, Math.min(600, Math.round(numberValue("mortgage_remaining_months") ?? 0))),
        property_value: Math.max(0, numberValue("mortgage_property_value") ?? 0),
      };
    }

    const iisType = $("iis_type").value;
    if (iisType !== "none") {
      profile.iis = {
        type: iisType,
        annual_contribution: Math.max(0, numberValue("iis_contribution") ?? 0),
        years: Math.max(0, Math.round(horizon / 12)),
      };
    }

    const depositAmount = numberValue("deposit_amount");
    if (depositAmount !== null && depositAmount > 0) {
      const depositRate = numberValue("deposit_rate");
      const fallbackRate = state.macro?.deposit_rate?.value ?? 0.15;
      profile.deposits = [{
        amount: depositAmount,
        annual_rate: (depositRate !== null ? depositRate : fallbackRate * 100) / 100,
        term_months: horizon,
      }];
    }

    const overrides = {};
    Object.entries(MACRO_FIELDS).forEach(([id, key]) => {
      const value = numberValue(id);
      if (value !== null) overrides[key] = value / 100;
    });

    const payload = {
      profile,
      options: {
        monte_carlo_paths: Number($("paths").value) || 10000,
        distribution: $("distribution").value,
        seed: Math.max(0, Math.min(2147483647, Math.round(numberValue("seed") ?? 42))),
        max_scenarios: Number($("max_scenarios").value) || 18,
        include_real_estate: $("include_real_estate").checked,
        include_mortgage: $("include_mortgage").checked,
        run_stress_tests: $("run_stress_tests").checked,
      },
      refresh_macro: $("refresh_macro").checked,
    };
    if (Object.keys(overrides).length) payload.market_overrides = overrides;
    return payload;
  }

  // ---------------------------------------------------------------------
  // Прогресс и запуск
  // ---------------------------------------------------------------------
  function setBusy(busy) {
    state.busy = busy;
    const button = $("submitBtn");
    if (!button) return;
    button.disabled = busy;
    button.querySelector("span").textContent = busy ? "Считаем…" : "Рассчитать план";
  }

  function updateProgress(progress, message) {
    const safe = Math.max(0, Math.min(100, Number(progress) || 0));
    $("progressBar").style.width = `${safe}%`;
    $("progressPercent").textContent = `${safe}%`;
    $("progressTitle").textContent = safe < 100 ? "Считаем сценарии" : "Готово";
    if (message) $("progressMessage").textContent = message;
  }

  async function runOptimization(payload) {
    state.lastPayload = payload;
    $("emptyState").hidden = true;
    $("resultsContent").hidden = true;
    $("progressCard").hidden = false;
    updateProgress(1, "Отправляем запрос и готовим сценарии…");
    const started = await api("/api/v2/optimize/async", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    let polls = 0;
    while (polls < 900) {
      await sleep(900);
      const job = await api(`/api/v2/jobs/${encodeURIComponent(started.job_id)}`);
      updateProgress(job.progress, job.message);
      if (job.status === "done") {
        if (!job.result) throw new Error("Задание завершилось без результата.");
        return job.result;
      }
      if (job.status === "error") {
        throw new Error(job.error || "Не удалось выполнить расчёт.");
      }
      polls += 1;
    }
    throw new Error("Расчёт занимает слишком долго. Попробуйте меньше путей или повторите позже.");
  }

  // ---------------------------------------------------------------------
  // Рендер результата
  // ---------------------------------------------------------------------
  function findOption(id) {
    if (!state.result || !id) return null;
    for (const level of ["low", "medium", "high"]) {
      const group = state.result.risk_profiles?.[level];
      const option = group?.options?.find((item) => item.id === id);
      if (option) return option;
    }
    return state.result.top_options?.find((item) => item.id === id) || null;
  }

  function renderResult(result) {
    state.result = result;
    state.selectedOptionId = result.top_options?.[0]?.id || null;
    state.chatHistory = [];
    $("emptyState").hidden = true;
    $("progressCard").hidden = true;
    $("resultsContent").hidden = false;
    renderSummary(result);
    renderRiskCards(result);
    renderTopTable(result);
    renderStressOptions(result);
    renderComparisons(result);
    renderAI(result);
    renderWarnings(result);
    $("disclaimer").textContent = result.disclaimer || "";
    $("pathsBadge").textContent = `${nf0.format(result.top_options?.[0]?.monte_carlo?.paths || 0)} путей`;
    $("generatedBadge").textContent = dateLabel(result.generated_at);
    $("topCountBadge").textContent = `${result.top_options?.length || 0} сценариев`;
    initChat(result);
    const drawSelected = () => {
      const option = findOption(state.selectedOptionId);
      if (option) drawCharts(option);
    };
    // Рисуем сразу, затем ещё раз после раскладки и при появлении вкладки.
    drawSelected();
    window.requestAnimationFrame(drawSelected);
    window.setTimeout(drawSelected, 180);
  }

  function renderSummary(result) {
    const best = result.top_options?.[0];
    const macro = result.macro || {};
    if (!best) {
      $("summaryGrid").innerHTML = "";
      return;
    }
    const mc = best.monte_carlo || {};
    const goal = best.probability_goal;
    const goalMetric = goal !== null && goal !== undefined
      ? { label: "Вероятность цели", value: pct(goal), note: "по 10 000+ путям" }
      : { label: "Риск убытка", value: pct(best.probability_loss), note: "капитал ниже взносов" };

    const macroItems = [
      ["key_rate", "Ключевая ставка"],
      ["inflation_expected", "Ожидаемая инфляция"],
      ["deposit_rate", "Ставка по вкладам"],
      ["mortgage_rate", "Ипотека"],
    ].map(([key, label]) => {
      const point = macro[key] || {};
      return `
        <div class="macro-item">
          <label>${label}</label>
          <b>${pct(point.value)}</b>
          <small><i class="source-dot ${sourceStatus(point)}"></i>${escapeHtml(sourceLabel(point))}</small>
        </div>`;
    }).join("");

    $("summaryGrid").innerHTML = `
      <div class="summary-main">
        <div class="summary-top">
          <span class="badge green">Лучший сценарий</span>
          <span class="risk-pill ${best.risk_level}">${RISK_LABELS[best.risk_level] || best.risk_level}</span>
        </div>
        <h3>${escapeHtml(best.name)}</h3>
        <p class="summary-desc">${escapeHtml(best.description || "")}</p>
        <div class="summary-metrics">
          <div class="summary-metric"><label>Доходность</label><b>${pct(best.expected_return_nominal)}</b><small>номинальная</small></div>
          <div class="summary-metric"><label>P50 капитал</label><b>${compactMoney(mc.terminal_p50)}</b><small>${money(mc.terminal_p50)}</small></div>
          <div class="summary-metric"><label>${goalMetric.label}</label><b>${goalMetric.value}</b><small>${goalMetric.note}</small></div>
          <div class="summary-metric"><label>Просадка</label><b>${pct(best.max_drawdown)}</b><small>медиана</small></div>
        </div>
      </div>
      <div class="macro-mini card">
        <div class="card-head" style="margin-bottom:8px">
          <div><h3>Макросрез</h3><p style="font-size:11px">${escapeHtml(dateLabel(macro.fetched_at))}</p></div>
          <span class="badge">источники</span>
        </div>
        <div class="macro-grid">${macroItems}</div>
      </div>`;
  }

  function allocBar(allocation) {
    if (!allocation || !allocation.length) return "";
    return allocation.map((item) => {
      const color = ASSET_COLORS[item.key] || "#9ad8a4";
      return `<i style="width:${Math.max(1, item.weight * 100)}%;background:${color}" title="${escapeHtml(item.name)}: ${pct(item.weight)}"></i>`;
    }).join("");
  }

  function allocLegend(allocation) {
    if (!allocation) return "";
    const visible = allocation.slice(0, 4);
    const rest = allocation.length - visible.length;
    return visible.map((item) => {
      const color = ASSET_COLORS[item.key] || "#9ad8a4";
      return `<span><i style="background:${color}"></i>${escapeHtml(item.name)} ${pct(item.weight, 0)}</span>`;
    }).join("") + (rest > 0 ? `<span>+${rest}</span>` : "");
  }

  function rangeMarkers(mc) {
    const p5 = Number(mc.terminal_p5) || 0;
    const p50 = Number(mc.terminal_p50) || 0;
    const p95 = Number(mc.terminal_p95) || 0;
    const span = Math.max(1, p95 - p5);
    const position = Math.max(0, Math.min(100, ((p50 - p5) / span) * 100));
    return { p5, p50, p95, position };
  }

  function renderRiskCards(result) {
    const levels = ["low", "medium", "high"];
    $("riskGrid").innerHTML = levels.map((level) => {
      const group = result.risk_profiles?.[level];
      if (!group || !group.options?.length) return "";
      const best = group.options[0];
      const mc = best.monte_carlo || {};
      const range = rangeMarkers(mc);
      const score = Math.round((Number(best.score) || 0) * 100);
      return `
        <article class="risk-card ${level}" data-detail="${escapeHtml(best.id)}" tabindex="0" role="button" aria-label="Открыть детали сценария ${escapeHtml(best.name)}">
          <div class="risk-card-head">
            <div>
              <span class="risk-kicker">${RISK_LABELS[level]}</span>
              <h3>${escapeHtml(best.name)}</h3>
            </div>
            <div class="score-ring" style="--score:${score}" title="Рейтинг сценария"><b>${score}</b></div>
          </div>
          <p class="risk-desc">${escapeHtml(group.description || best.description || "")}</p>
          <div class="alloc-bar">${allocBar(best.allocation)}</div>
          <div class="alloc-legend">${allocLegend(best.allocation)}</div>
          <div class="risk-metrics">
            <div class="risk-metric"><label>Доходность</label><b>${pct(best.expected_return_nominal)}</b></div>
            <div class="risk-metric"><label>Реальная</label><b>${pct(best.expected_return_real)}</b></div>
            <div class="risk-metric"><label>P50</label><b>${compactMoney(mc.terminal_p50)}</b></div>
            <div class="risk-metric"><label>P5</label><b>${compactMoney(mc.terminal_p5)}</b></div>
          </div>
          <div class="range-block">
            <div class="range-labels"><span>P5 ${compactMoney(range.p5)}</span><span>P95 ${compactMoney(range.p95)}</span></div>
            <div class="range-track">
              <i style="left:0"></i>
              <i class="p50" style="left:${range.position}%"></i>
              <i style="right:0"></i>
            </div>
          </div>
          <div class="risk-footer">
            <span class="tax-note">Налоги ${pct(best.taxes?.effective_rate || 0)} · ${escapeHtml(best.liquidity_label || "")}</span>
            <button class="link-btn" type="button" data-level="${level}">Все сценарии →</button>
          </div>
        </article>`;
    }).join("");
  }

  function renderTopTable(result) {
    const rows = (result.top_options || []).map((option) => {
      const mc = option.monte_carlo || {};
      const goal = option.probability_goal;
      return `
        <tr data-detail="${escapeHtml(option.id)}">
          <td><span class="rank-badge">${option.rank}</span></td>
          <td>
            <div class="table-name"><b>${escapeHtml(option.name)}</b><small>${escapeHtml((option.tags || []).join(" · ") || option.description || "")}</small></div>
          </td>
          <td><span class="risk-pill ${option.risk_level}">${RISK_SHORT[option.risk_level] || option.risk_level}</span></td>
          <td class="mono pos">${pct(option.expected_return_nominal)}</td>
          <td class="mono">${money(mc.terminal_p50)}</td>
          <td class="mono">${goal !== null && goal !== undefined ? pct(goal) : "—"}</td>
          <td class="mono">${(Number(option.sharpe) || 0).toFixed(2).replace(".", ",")}</td>
          <td>${escapeHtml(option.liquidity_label || "")}</td>
          <td class="mono">${pct(option.taxes?.effective_rate || 0)}</td>
        </tr>`;
    }).join("");
    $("topTableBody").innerHTML = rows;
  }

  function renderStressOptions(result) {
    const select = $("stressSelect");
    const options = result.top_options || [];
    select.innerHTML = options.map((option) =>
      `<option value="${escapeHtml(option.id)}">${escapeHtml(option.name)} · ${RISK_SHORT[option.risk_level] || ""}</option>`
    ).join("");
    if (state.selectedOptionId) select.value = state.selectedOptionId;
    select.onchange = () => {
      state.selectedOptionId = select.value;
      renderStress(select.value);
      const option = findOption(select.value);
      if (option) {
        drawCharts(option);
        renderRiskCardsHighlight(option);
      }
    };
    renderStress(state.selectedOptionId);
  }

  function renderStress(optionId) {
    const option = findOption(optionId);
    const body = $("stressTableBody");
    if (!option || !option.stress_tests?.length) {
      body.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">Стресс-тесты отключены или недоступны.</td></tr>`;
      return;
    }
    body.innerHTML = option.stress_tests.map((item) => {
      const impact = Number(item.impact_p50) || 0;
      const impactP5 = Number(item.impact_p5) || 0;
      return `
        <tr>
          <td><b>${escapeHtml(item.scenario)}</b></td>
          <td class="mono ${impact >= 0 ? "pos" : "neg"}">${signedPct(impact)}</td>
          <td class="mono ${impactP5 >= 0 ? "pos" : "neg"}">${signedPct(impactP5)}</td>
          <td class="mono">${money(item.terminal_p50)}</td>
          <td style="color:var(--muted);font-size:11px">${escapeHtml(item.note || "")}</td>
        </tr>`;
    }).join("");
  }

  function comparisonCard(item, emptyText) {
    if (!item) {
      return `<div class="comparison-empty">${escapeHtml(emptyText)}</div>`;
    }
    const details = item.details || {};
    const stats = Object.entries(details).slice(0, 4).map(([key, value]) => {
      const labels = {
        property_value: "Стоимость объекта",
        down_payment: "Первый взнос",
        monthly_payment: "Платёж",
        monthly_rent: "Аренда",
        debt_rate: "Ставка долга",
        portfolio_return: "Доходность портфеля",
        prepay_capital: "Сумма погашения",
        saved_interest: "Экономия на процентах",
      };
      const isRate = key.includes("rate") || key.includes("return");
      const display = typeof value === "number" && isRate ? pct(value) : money(value);
      return `<div class="comparison-stat"><label>${labels[key] || key}</label><b>${display}</b></div>`;
    }).join("");
    const diff = Number(item.npv_difference) || 0;
    return `
      <div class="comparison-card">
        <h3>${escapeHtml(item.name)}</h3>
        <span class="better">${escapeHtml(item.better_option)}</span>
        <p>${escapeHtml(item.note || "")}</p>
        <div class="comparison-stats">${stats}</div>
        <p style="margin-top:10px">Разница NPV: <b class="${diff >= 0 ? "pos" : "neg"}">${money(diff)}</b></p>
      </div>`;
  }

  function renderComparisons(result) {
    const comparisons = result.comparisons || {};
    $("comparisonGrid").innerHTML =
      comparisonCard(comparisons.rent_vs_buy, "Добавьте капитал и горизонт от 12 месяцев, чтобы сравнить аренду и покупку.") +
      comparisonCard(comparisons.prepay_vs_invest, "Добавьте существующую ипотеку или кредит, чтобы сравнить досрочное погашение и инвестирование.");
  }

  function renderAI(result) {
    const template = result.ai_template || {};
    const riskTexts = template.risk_profiles || {};
    const chips = ["low", "medium", "high"].map((level) => {
      const text = riskTexts[level];
      if (!text) return "";
      return `<div class="ai-risk-chip"><b>${RISK_LABELS[level]}</b>${escapeHtml(text)}</div>`;
    }).join("");
    const steps = (template.steps || []).map((step) => `<li>${escapeHtml(step)}</li>`).join("");
    $("aiContent").innerHTML = `
      <div class="ai-summary">${formatText(template.summary || "Объяснение появится после расчёта.")}</div>
      ${chips ? `<div class="ai-risk-chips">${chips}</div>` : ""}
      ${steps ? `<div class="ai-block"><h4>Что сделать</h4><ol>${steps}</ol></div>` : ""}
      ${template.why ? `<div class="ai-block"><h4>Почему так</h4><p>${formatText(template.why)}</p></div>` : ""}
      ${template.risks ? `<div class="ai-block"><h4>Главные риски</h4><p>${formatText(template.risks)}</p></div>` : ""}`;
    $("aiSourceBadge").textContent = template.generated_by || "template";
  }

  function renderWarnings(result) {
    const warnings = result.warnings || [];
    const box = $("warnings");
    if (!warnings.length) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML = `<h4>На что обратить внимание</h4><ul>${warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function renderRiskCardsHighlight(option) {
    document.querySelectorAll(".risk-card").forEach((card) => {
      card.style.borderColor = card.dataset.detail === option.id ? "var(--green)" : "";
    });
  }

  // ---------------------------------------------------------------------
  // Модальные окна
  // ---------------------------------------------------------------------
  function openModal(title, subtitle, bodyHtml) {
    $("modalTitle").textContent = title;
    $("modalSubtitle").textContent = subtitle || "";
    $("modalBody").innerHTML = bodyHtml;
    $("detailModal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    $("detailModal").hidden = true;
    document.body.style.overflow = "";
  }

  function openDetail(id) {
    const option = findOption(id);
    if (!option) return;
    const mc = option.monte_carlo || {};
    const allocation = option.allocation || [];
    const metrics = [
      ["Доходность", pct(option.expected_return_nominal)],
      ["Реальная", pct(option.expected_return_real)],
      ["После налогов", pct(option.after_tax_return)],
      ["Волатильность", pct(option.volatility)],
      ["VaR 95", pct(option.var_95)],
      ["CVaR 95", pct(option.cvar_95)],
      ["Просадка", pct(option.max_drawdown)],
      ["Sharpe", (Number(option.sharpe) || 0).toFixed(2).replace(".", ",")],
      ["Sortino", (Number(option.sortino) || 0).toFixed(2).replace(".", ",")],
      ["P5", money(mc.terminal_p5)],
      ["P50", money(mc.terminal_p50)],
      ["P95", money(mc.terminal_p95)],
    ].map(([label, value]) => `<div class="detail-metric"><label>${label}</label><b>${value}</b></div>`).join("");

    const allocRows = allocation.map((item) => `
      <div class="detail-row">
        <span>${escapeHtml(item.name)} · ${pct(item.weight)}</span>
        <b>${money(item.amount)}</b>
      </div>`).join("");

    const stressRows = (option.stress_tests || []).map((item) => `
      <div class="detail-row">
        <span>${escapeHtml(item.scenario)}</span>
        <b class="${Number(item.impact_p50) >= 0 ? "pos" : "neg"}">${signedPct(item.impact_p50)}</b>
      </div>`).join("");

    const body = `
      <div class="detail-grid">
        <div class="detail-panel">
          <h4>Ожидаемый результат</h4>
          <div class="big">${pct(option.expected_return_nominal)}</div>
          <p>${escapeHtml(option.description || "")}</p>
          <div class="detail-metrics">${metrics}</div>
        </div>
        <div class="detail-panel">
          <h4>Налоги и комиссии</h4>
          <div class="big">${pct(option.taxes?.effective_rate || 0)}</div>
          <p>${escapeHtml(option.taxes?.note || "")}</p>
          <div class="detail-row" style="margin-top:10px"><span>Годовой налог</span><b>${money(option.taxes?.annual_tax || 0)}</b></div>
          <div class="detail-row" style="margin-top:6px"><span>Годовые комиссии</span><b>${money(option.fees?.annual_fee || 0)}</b></div>
          <div class="detail-row" style="margin-top:6px"><span>Ликвидность</span><b>${escapeHtml(option.liquidity_label || "")} · ${pct(option.liquidity)}</b></div>
          <div class="detail-row" style="margin-top:6px"><span>Дюрация</span><b>${(Number(option.duration_years) || 0).toFixed(1).replace(".", ",")} лет</b></div>
        </div>
      </div>
      <div class="detail-section">
        <h4>Состав портфеля</h4>
        <div class="detail-list">${allocRows || '<div class="detail-row"><span>Нет данных</span></div>'}</div>
      </div>
      <div class="detail-section">
        <h4>Стресс-тесты</h4>
        <div class="detail-list">${stressRows || '<div class="detail-row"><span>Стресс-тесты отключены</span></div>'}</div>
      </div>
      <div class="detail-section">
        <h4>Почему сценарий в топе</h4>
        <p style="color:var(--muted);font-size:12px;line-height:1.55">${escapeHtml(option.why_recommended || "")}</p>
      </div>`;
    openModal(option.name, `${RISK_LABELS[option.risk_level] || ""} · рейтинг ${Math.round((Number(option.score) || 0) * 100)}`, body);
  }

  function openLevelModal(level) {
    const group = state.result?.risk_profiles?.[level];
    if (!group) return;
    const options = group.options || [];
    const body = `<div class="level-list">${options.map((option) => {
      const mc = option.monte_carlo || {};
      return `
        <div class="level-option" data-detail="${escapeHtml(option.id)}" tabindex="0" role="button">
          <div>
            <b>${escapeHtml(option.name)}</b>
            <small>${escapeHtml(option.description || "")}</small>
          </div>
          <div class="level-metrics">
            <div>${pct(option.expected_return_nominal)}</div>
            <div>P50 ${compactMoney(mc.terminal_p50)}</div>
            <div>риск ${Math.round((Number(option.score) || 0) * 100)}</div>
          </div>
        </div>`;
    }).join("")}</div>`;
    openModal(`${RISK_LABELS[level]} — все сценарии`, group.description || "", body);
  }

  // ---------------------------------------------------------------------
  // Графики
  // ---------------------------------------------------------------------
  function prepareCanvas(canvas) {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(300, rect.width || canvas.parentElement.clientWidth || 600);
    const height = Math.max(220, rect.height || 300);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    return { ctx, width, height };
  }

  function drawFan(option) {
    const canvas = $("fanChart");
    if (!canvas) return;
    const series = option?.monte_carlo?.series || [];
    if (series.length < 2) {
      const { ctx, width, height } = prepareCanvas(canvas);
      ctx.fillStyle = cssVar("--muted");
      ctx.font = "13px " + cssVar("--font");
      ctx.textAlign = "center";
      ctx.fillText("Нет данных для графика", width / 2, height / 2);
      return;
    }
    const { ctx, width, height } = prepareCanvas(canvas);
    const pad = { left: 58, right: 20, top: 16, bottom: 34 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const maxMonth = Math.max(...series.map((item) => Number(item.month) || 0), 1);
    const maxValue = Math.max(...series.map((item) => Math.max(Number(item.p95) || 0, Number(item.contributed) || 0)), 1) * 1.04;
    const x = (month) => pad.left + (month / maxMonth) * innerW;
    const y = (value) => pad.top + innerH - (Math.max(0, value) / maxValue) * innerH;

    const lineColor = cssVar("--line");
    const muted = cssVar("--muted");
    const green = cssVar("--green");
    const greenDark = cssVar("--green-dark");

    ctx.font = "11px " + cssVar("--font");
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let index = 0; index <= 4; index += 1) {
      const value = (maxValue / 4) * index;
      const yy = y(value);
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.left, yy);
      ctx.lineTo(width - pad.right, yy);
      ctx.stroke();
      ctx.fillStyle = muted;
      ctx.fillText(compactMoney(value), pad.left - 8, yy);
    }

    // Коридор P5–P95
    ctx.beginPath();
    series.forEach((item, index) => {
      const xx = x(Number(item.month) || 0);
      const yy = y(Number(item.p95) || 0);
      if (index === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    for (let index = series.length - 1; index >= 0; index -= 1) {
      const item = series[index];
      ctx.lineTo(x(Number(item.month) || 0), y(Number(item.p5) || 0));
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(33, 160, 56, 0.14)";
    ctx.fill();

    // P50
    ctx.beginPath();
    series.forEach((item, index) => {
      const xx = x(Number(item.month) || 0);
      const yy = y(Number(item.p50) || 0);
      if (index === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.strokeStyle = green;
    ctx.lineWidth = 2.6;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    // Взносы
    ctx.beginPath();
    series.forEach((item, index) => {
      const xx = x(Number(item.month) || 0);
      const yy = y(Number(item.contributed) || 0);
      if (index === 0) ctx.moveTo(xx, yy);
      else ctx.lineTo(xx, yy);
    });
    ctx.strokeStyle = muted;
    ctx.lineWidth = 1.4;
    ctx.setLineDash([5, 5]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Точка P50 на конце
    const last = series[series.length - 1];
    const lastX = x(Number(last.month) || 0);
    const lastY = y(Number(last.p50) || 0);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
    ctx.fillStyle = greenDark;
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Подпись P50
    const label = compactMoney(last.p50);
    ctx.font = "700 11px " + cssVar("--font");
    const labelWidth = ctx.measureText(label).width + 14;
    const labelX = Math.min(width - pad.right - labelWidth, lastX - labelWidth / 2);
    const labelY = Math.max(6, lastY - 28);
    ctx.fillStyle = greenDark;
    ctx.beginPath();
    ctx.roundRect(labelX, labelY, labelWidth, 20, 7);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, labelX + labelWidth / 2, labelY + 10);

    // Ось X: ровные годы, а не четверти горизонта.
    ctx.fillStyle = muted;
    ctx.font = "11px " + cssVar("--font");
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    let tickStep = 12;
    if (maxMonth > 120) tickStep = 60;
    else if (maxMonth > 60) tickStep = 24;
    else if (maxMonth < 12) tickStep = Math.max(1, Math.round(maxMonth / 4));
    const ticks = [];
    for (let month = 0; month <= maxMonth; month += tickStep) ticks.push(month);
    if (ticks[ticks.length - 1] !== maxMonth) ticks.push(maxMonth);
    ticks.forEach((month) => {
      const xx = x(month);
      const label = month >= 12 && month % 12 === 0
        ? `${month / 12} г.`
        : month >= 12
          ? `${(month / 12).toFixed(1).replace(".", ",")} г.`
          : `${month} мес.`;
      ctx.fillText(label, xx, height - pad.bottom + 10);
    });
  }

  function drawHistogram(option) {
    const canvas = $("histChart");
    if (!canvas) return;
    const histogram = option?.monte_carlo?.histogram || [];
    if (!histogram.length) {
      const { ctx, width, height } = prepareCanvas(canvas);
      ctx.fillStyle = cssVar("--muted");
      ctx.font = "13px " + cssVar("--font");
      ctx.textAlign = "center";
      ctx.fillText("Нет данных для гистограммы", width / 2, height / 2);
      return;
    }
    const { ctx, width, height } = prepareCanvas(canvas);
    const pad = { left: 16, right: 16, top: 22, bottom: 40 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const maxCount = Math.max(...histogram.map((item) => Number(item.count) || 0), 1);
    const minValue = Number(histogram[0].from) || 0;
    const maxValue = Number(histogram[histogram.length - 1].to) || 1;
    const span = Math.max(1, maxValue - minValue);
    const barWidth = innerW / histogram.length;
    const p5 = Number(option.monte_carlo.terminal_p5) || 0;
    const p50 = Number(option.monte_carlo.terminal_p50) || 0;
    const p95 = Number(option.monte_carlo.terminal_p95) || 0;

    histogram.forEach((bin, index) => {
      const count = Number(bin.count) || 0;
      const barHeight = (count / maxCount) * innerH;
      const xx = pad.left + index * barWidth;
      const yy = pad.top + innerH - barHeight;
      const midpoint = (Number(bin.from) + Number(bin.to)) / 2;
      ctx.fillStyle = midpoint < p5 ? "rgba(229, 72, 77, 0.55)" : "rgba(33, 160, 56, 0.72)";
      ctx.beginPath();
      ctx.roundRect(xx + 1, yy, Math.max(1, barWidth - 2), barHeight, 3);
      ctx.fill();
    });

    const marker = (value, label, color) => {
      const xx = pad.left + ((value - minValue) / span) * innerW;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.6;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(xx, pad.top - 4);
      ctx.lineTo(xx, pad.top + innerH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.font = "700 10px " + cssVar("--font");
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillText(label, xx, pad.top - 7);
    };
    marker(p5, "P5", "rgba(229, 72, 77, 0.9)");
    marker(p50, "P50", cssVar("--green-dark"));
    marker(p95, "P95", "rgba(33, 160, 56, 0.9)");

    ctx.fillStyle = cssVar("--muted");
    ctx.font = "11px " + cssVar("--font");
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(compactMoney(minValue), pad.left, height - pad.bottom + 12);
    ctx.textAlign = "center";
    ctx.fillText(compactMoney(p50), pad.left + innerW / 2, height - pad.bottom + 12);
    ctx.textAlign = "right";
    ctx.fillText(compactMoney(maxValue), width - pad.right, height - pad.bottom + 12);
  }

  function drawCharts(option) {
    if (!option) return;
    $("fanSubtitle").textContent = `${option.name} · P5–P95 и медиана`;
    $("histSubtitle").textContent = `${nf0.format(option.monte_carlo?.paths || 0)} путей · капитал через горизонт`;
    drawFan(option);
    drawHistogram(option);
  }

  // ---------------------------------------------------------------------
  // Чат
  // ---------------------------------------------------------------------
  function initChat(result) {
    const best = result.top_options?.[0];
    const messages = $("chatMessages");
    const greeting = best
      ? `Расчёт готов. Лучший сценарий — «${best.name}»: ожидаемая доходность ${pct(best.expected_return_nominal)}, медианный капитал ${money(best.monte_carlo?.terminal_p50)}. Спросите про риски, налоги, ставку или сравнение с ипотекой.`
      : "Расчёт готов. Спросите про сценарии, риски, налоги или стресс-тесты.";
    messages.innerHTML = "";
    appendChat("assistant", greeting);
  }

  function appendChat(role, text) {
    const messages = $("chatMessages");
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${role}`;
    bubble.innerHTML = formatText(text);
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  function appendTyping() {
    const bubble = appendChat("assistant", "Печатает…");
    bubble.classList.add("typing");
    return bubble;
  }

  function setChatBusy(busy) {
    state.chatBusy = busy;
    $("chatSend").disabled = busy;
    $("chatInput").disabled = busy;
  }

  async function askQuestion(question) {
    const text = String(question || "").trim();
    if (!text || !state.result || state.chatBusy) return;
    appendChat("user", text);
    $("chatInput").value = "";
    setChatBusy(true);
    const history = state.chatHistory.slice(-8);
    state.chatHistory.push({ role: "user", content: text });
    const typing = appendTyping();
    try {
      const response = await api("/api/v2/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          context_id: state.result.context_id,
          question: text,
          history,
          use_llm: true,
        }),
      });
      typing.remove();
      appendChat("assistant", response.answer || "Не удалось сформировать ответ.");
      state.chatHistory.push({ role: "assistant", content: response.answer || "" });
    } catch (error) {
      typing.remove();
      appendChat("assistant", `Не удалось получить ответ: ${error.message}`);
    } finally {
      setChatBusy(false);
      $("chatInput").focus();
    }
  }

  // ---------------------------------------------------------------------
  // Уведомления
  // ---------------------------------------------------------------------
  function showToast(message, isError = false) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.toggle("error", Boolean(isError));
    toast.hidden = false;
    if (state.toastTimer) window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, 5200);
  }

  // ---------------------------------------------------------------------
  // События
  // ---------------------------------------------------------------------
  function bindEvents() {
    $("themeToggle").addEventListener("click", () => {
      setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    });

    bindSegmented("riskSegmented", "risk_tolerance");
    bindSegmented("liquiditySegmented", "liquidity_need");

    $("resetMacroBtn").addEventListener("click", () => {
      Object.keys(MACRO_FIELDS).forEach((id) => {
        const field = $(id);
        if (field) field.value = "";
      });
      showToast("Ручные макропараметры сброшены. Будут использованы данные источника.");
    });

    $("optimizerForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (state.busy) return;
      const payload = buildPayload();
      if (!payload) return;
      setBusy(true);
      try {
        const result = await runOptimization(payload);
        renderResult(result);
        showToast("Расчёт готов. Три уровня риска и стресс-тесты обновлены.");
        window.setTimeout(() => {
          $("results").scrollIntoView({ behavior: "smooth", block: "start" });
        }, 120);
      } catch (error) {
        showToast(`Ошибка расчёта: ${error.message}`, true);
        $("progressCard").hidden = true;
        if (state.result) {
          $("resultsContent").hidden = false;
        } else {
          $("emptyState").hidden = false;
        }
      } finally {
        setBusy(false);
      }
    });

    $("riskGrid").addEventListener("click", (event) => {
      const levelButton = event.target.closest("[data-level]");
      if (levelButton) {
        event.stopPropagation();
        openLevelModal(levelButton.dataset.level);
        return;
      }
      const card = event.target.closest("[data-detail]");
      if (card) openDetail(card.dataset.detail);
    });

    $("riskGrid").addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const card = event.target.closest("[data-detail]");
      if (card) {
        event.preventDefault();
        openDetail(card.dataset.detail);
      }
    });

    $("topTableBody").addEventListener("click", (event) => {
      const row = event.target.closest("[data-detail]");
      if (row) openDetail(row.dataset.detail);
    });

    $("modalBody").addEventListener("click", (event) => {
      const item = event.target.closest("[data-detail]");
      if (item) openDetail(item.dataset.detail);
    });

    $("modalClose").addEventListener("click", closeModal);
    $("detailModal").addEventListener("click", (event) => {
      if (event.target === $("detailModal")) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$("detailModal").hidden) closeModal();
    });

    $("chatForm").addEventListener("submit", (event) => {
      event.preventDefault();
      askQuestion($("chatInput").value);
    });

    $("chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        askQuestion($("chatInput").value);
      }
    });

    $("chatInput").addEventListener("input", (event) => {
      const field = event.target;
      field.style.height = "auto";
      field.style.height = `${Math.min(110, field.scrollHeight)}px`;
    });

    $("chatSuggestions").addEventListener("click", (event) => {
      const button = event.target.closest("[data-question]");
      if (button) askQuestion(button.dataset.question);
    });

    $("refreshAiBtn").addEventListener("click", async () => {
      if (!state.result) return;
      const button = $("refreshAiBtn");
      button.disabled = true;
      button.textContent = "Обновляем…";
      try {
        const explanation = await api("/api/v2/ai/explain", {
          method: "POST",
          body: JSON.stringify({ context_id: state.result.context_id, use_llm: true }),
        });
        state.result.ai_template = explanation;
        renderAI(state.result);
        showToast(`Объяснение обновлено: ${explanation.generated_by}.`);
      } catch (error) {
        showToast(`Не удалось обновить объяснение: ${error.message}`, true);
      } finally {
        button.disabled = false;
        button.textContent = "Обновить объяснение";
      }
    });

    let resizeTimer = null;
    window.addEventListener("resize", () => {
      if (resizeTimer) window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        const option = findOption(state.selectedOptionId);
        if (option) drawCharts(option);
      }, 160);
    });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        const option = findOption(state.selectedOptionId);
        if (option) window.setTimeout(() => drawCharts(option), 80);
      }
    });
  }

  async function init() {
    const stored = localStorage.getItem("finhell-theme");
    const preferred = stored || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    setTheme(preferred);
    bindEvents();
    bindAuthEvents();
    updateAuthUser();
    await initAuth();
  }

  window.__finhellOptimizer = {
    redraw() {
      const option = findOption(state.selectedOptionId);
      if (option) drawCharts(option);
      return Boolean(option);
    },
    state,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
