# ФинХелл — оптимизатор капитала

Финансовый планировщик для России: считает, как капитал, ежемесячные взносы и
горизонт превращаются в результат при разных уровнях риска. Внутри — два
продукта:

| Версия | Что это | Где |
|---|---|---|
| v1 | Пошаговый экономический симулятор: резерв, долги, облигации, акции, недвижимость, Монте-Карло | `/` |
| v2 | Оптимизатор капитала: три уровня риска, 10 000+ путей, стресс-тесты, сравнения, AI | `/optimizer` |

Оба работают в одном FastAPI-приложении. Акции и криптовалюта в v2 исключены:
только вклады, накопительные счета, ОФЗ, корпоративные и муниципальные
облигации, арендная недвижимость и ипотека.

## Быстрый старт

Из корня проекта:

```powershell
# доступ только с этого компьютера
.\myvenv\Scripts\python.exe -m uvicorn DefultCredit.simulator:app --host 127.0.0.1 --port 8002

# доступ с телефона в той же Wi-Fi сети
.\myvenv\Scripts\python.exe -m uvicorn DefultCredit.simulator:app --host 0.0.0.0 --port 8002
```

Открыть:

- <http://127.0.0.1:8002/optimizer> — оптимизатор v2;
- <http://127.0.0.1:8002/> — симулятор v1;
- <http://127.0.0.1:8002/docs> — Swagger / OpenAPI;
- <http://127.0.0.1:8002/api/v2/health> — проверка v2.

При первом открытии `/optimizer` зарегистрируйтесь по email — без входа
расчёты и AI-чат недоступны. Пользователи хранятся в SQLite
(`DefultCredit/data/finhell.db`), секрет подписи токенов — в
`DefultCredit/data/auth_secret`. Для production задайте `FINHELL_AUTH_SECRET`,
`FINHELL_DB_PATH` и `FINHELL_TOKEN_TTL_SECONDS`.

## Что умеет v2

- **Вход:** капитал, взнос, горизонт 1–600 месяцев, риск-профиль, ликвидность,
  кредит, ипотека, ИИС, вклады, цель, расходы, регион.
- **Макроданные:** ключевая ставка, инфляция, FX, кривая ОФЗ, ставки вкладов и
  ипотеки. У каждой цифры — источник, время и пометка fallback.
- **Инструменты:** вклады, накопительный счёт, короткие и длинные ОФЗ,
  корпоративные и муниципальные облигации, арендная недвижимость, ипотечные
  сценарии с плечом.
- **Расчёт:** 10–18 сценариев, 10 000 путей Монте-Карло на сценарий,
  нормальное / t-распределение / историческая выборка.
- **Метрики:** номинальная и реальная доходность, YTM, дюрация, волатильность,
  VaR95, CVaR95, максимальная просадка, Sharpe, Sortino, вероятность цели и
  убытка, P5/P25/P50/P75/P95, гистограмма, налоги, вычеты, комиссии, NPV/IRR.
- **Стресс-тесты:** ставка ±100/300/500 б.п., инфляция +3 п.п., налоги +2 п.п.,
  недвижимость −20%, ипотечная ставка +3 п.п.
- **Сравнения:** аренда vs покупка, досрочное погашение vs инвестирование.
- **AI:** объяснение и чат по детерминированному JSON-контексту; валидатор
  блокирует выдуманные числа; провайдеры OpenAI/Anthropic/YandexGPT/GigaChat
  опциональны, без ключей работает шаблонный режим.
- **Авторизация:** регистрация и вход по email и паролю. Пароли хранятся в
  SQLite только как PBKDF2-HMAC-SHA256 хеши (210 000 итераций, индивидуальная
  соль), токен — HMAC-SHA256 подпись со сроком 30 дней. Расчёты, задания и
  AI-методы доступны только после входа.
- **UI:** Sber-style, зелёный/белый/почти чёрный, светлая и тёмная темы,
  адаптивная вёрстка, графики и модалки.

## Структура

```text
DefultCredit/
├── simulator.py              FastAPI-приложение, монтирует v1 и v2
├── simulator_engine.py       движок v1
├── simulator_plan.py         план v1
├── templates/
│   ├── simulator.html        интерфейс v1
│   └── optimizer.html        интерфейс v2
├── static/
│   ├── app.js                фронтенд v1
│   ├── optimizer.css         дизайн-система v2
│   └── optimizer.js          фронтенд v2
├── optimizer/
│   ├── models.py             Pydantic-модели
│   ├── auth.py               email-авторизация, PBKDF2, HMAC-токены
│   ├── market_data.py        ЦБ РФ, MOEX ISS, кэш, fallback
│   ├── instruments.py        активы, сценарии, портфельные метрики
│   ├── taxes.py              НДФЛ, ИИС, аннуитет, NPV/IRR
│   ├── engine.py             Монте-Карло, стресс-тесты, ранжирование
│   ├── ai.py                 контекст, валидатор, провайдеры, SSE
│   ├── jobs.py               фоновые задания с привязкой к пользователю
│   └── api.py                маршруты /api/v2
└── tests/
    ├── test_simulator_engine.py
    ├── test_optimizer.py
    └── test_auth.py          регистрация, вход, защита API и заданий

docs/CAPITAL_OPTIMIZER.md     полная документация v2
mobile/                       Flutter-клиент Android (APK в Releases)
```

## Android APK

Готовый release APK:
[Finhell-v0.2.0.apk](https://github.com/user569name/finhell/releases/download/v0.2.0/Finhell-v0.2.0.apk)
(~50 МБ, package `ru.finhell.finhell`, minSdk 24, targetSdk 36). Собирается
в GitHub Actions workflow `.github/workflows/android-apk.yml`. При первом
запуске приложение попросит зарегистрироваться по email или войти.

```powershell
adb install -r Finhell-release.apk
```

Адрес API меняется прямо в приложении (иконка сервера в шапке): для эмулятора —
`http://10.0.2.2:8002`, для телефона — `http://<IP-компьютера>:8002`.

## API v2

Сначала зарегистрируйтесь или войдите — в ответ придёт Bearer-токен:

```bash
curl -X POST http://127.0.0.1:8002/api/v2/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123", "name": "Имя"}'

curl -X POST http://127.0.0.1:8002/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "password123"}'
```

Дальше передавайте токен в заголовке `Authorization: Bearer <token>`.
Публично доступны `/api/v2/health`, `/macro`, `/instruments`, `/scenarios` и
`/compare/*`; расчёты, задания и AI требуют входа.

```bash
# макросрез (публично)
curl http://127.0.0.1:8002/api/v2/macro

# синхронный расчёт (до 3000 путей)
curl -X POST http://127.0.0.1:8002/api/v2/optimize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "profile": {
      "capital": 500000,
      "monthly": 20000,
      "horizon_months": 60,
      "goal_amount": 1500000
    },
    "options": {"monte_carlo_paths": 1000, "max_scenarios": 10}
  }'

# асинхронный расчёт (10 000 путей)
curl -X POST http://127.0.0.1:8002/api/v2/optimize/async \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"profile": {"capital": 500000, "monthly": 20000, "horizon_months": 60},
       "options": {"monte_carlo_paths": 10000, "max_scenarios": 10}}'

# статус задания (только своё задание)
curl http://127.0.0.1:8002/api/v2/jobs/<job_id> \
  -H "Authorization: Bearer <token>"
```

## Тесты

```powershell
.\myvenv\Scripts\python.exe -m unittest discover -s DefultCredit/tests -v
```

69 тестов: налоги, аннуитеты, NPV/IRR, каталог инструментов, сценарии,
ликвидность, ипотека, Монте-Карло, стресс-тесты, ранжирование, AI-валидатор,
чат, парсер MOEX, v1-симулятор, регистрация/вход и защита API.

## Ограничения

- Расчётное ядро — чистый Python: 10 000 путей × 10 сценариев занимают ~20 с.
  Для production нужен NumPy/SciPy или векторизация.
- Живые данные ЦБ/MOEX запрашиваются только при `refresh=true`; по умолчанию
  используется кэш или демо-срез.
- LLM-провайдеры реализованы, но без ключей проверен только шаблонный режим.
- APK собран в GitHub Actions; локально Flutter/Dart SDK не установлен.
- Это не индивидуальная инвестиционная рекомендация. Проверяйте условия
  у банка, брокера и налогового консультанта.

## Документация

- `docs/CAPITAL_OPTIMIZER.md` — архитектура, алгоритмы, AI-слой, риск-модуль,
  API, производительность, roadmap.
- `DefultCredit/README_SIMULATOR.md` — v1-симулятор.
- `mobile/README.md` — запуск Flutter-клиента.
