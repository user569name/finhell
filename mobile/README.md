# ФинХелл — мобильный оптимизатор капитала

Flutter-клиент для Android и iOS к API `DefultCredit/optimizer` (v2).
Интерфейс повторяет визуальный язык веб-версии: зелёный/белый/почти чёрный,
крупные скругления, светлая и тёмная темы.

> Release APK собирается в GitHub Actions (`.github/workflows/android-apk.yml`).
> Готовый файл — в разделе Releases репозитория и в корне проекта
> (`Finhell-release.apk`).

## Требования

- Flutter 3.27+ (Material 3, `CardThemeData`, `surfaceContainerHighest`).
- Dart 3.6+.
- Запущенный backend: `http://127.0.0.1:8002`.

## Запуск backend

Из корня репозитория:

```powershell
.\myvenv\Scripts\python.exe -m uvicorn DefultCredit.simulator:app --host 127.0.0.1 --port 8002
```

Проверка:

```powershell
curl http://127.0.0.1:8002/api/v2/health
```

## Запуск приложения

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8002
```

`10.0.2.2` — адрес хост-машины из Android-эмулятора. Для iOS-симулятора:

```powershell
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8002
```

Для физического устройства укажите LAN-адрес компьютера и разрешите входящие
подключения к порту 8002 в брандмауэре:

```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8002
```

Адрес сервера также можно поменять прямо в приложении: иконка сервера в правом
верхнем углу главного экрана (или ссылка «Сервер: …» на экране входа).
Значение применяется сразу и сохраняется между запусками, пересборка не нужна.

## Авторизация

При первом запуске открывается экран входа. Можно войти по email или создать
аккаунт; пароль — минимум 8 символов. Токен и email сохраняются локально
(`shared_preferences`), поэтому повторный вход нужен только после выхода или
истечения 30 дней. В шапке главного экрана виден email и кнопка «Выйти».

## APK для Android

Готовый release APK: скачайте `Finhell-v0.2.0.apk` из
[Releases](https://github.com/user569name/finhell/releases) или возьмите
`Finhell-release.apk` из корня проекта.

Установка на подключённое устройство:

```powershell
adb install -r Finhell-release.apk
```

APK содержит разрешения `INTERNET` и `usesCleartextTraffic`, поэтому может
обращаться к локальному FastAPI по HTTP. Для эмулятора используйте
`http://10.0.2.2:8002`, для физического телефона — `http://<IP-компьютера>:8002`
(компьютер и телефон должны быть в одной сети, порт 8002 открыт в брандмауэре).

## Что реализовано

- Экран входа и регистрации по email, сохранение токена, выход из аккаунта.
- Форма: капитал, взнос, цель, горизонт, риск-профиль, ликвидность,
  расходы и резерв, число путей и сценариев.
- Асинхронный расчёт через `/api/v2/optimize/async` с прогрессом и polling
  `/api/v2/jobs/{id}`.
- Экран результатов:
  - hero-карточка лучшего сценария;
  - макроданные с источником, временем и пометкой «демо»;
  - три карточки риска с составом, доходностью, P5/P50/P95, ликвидностью,
    просадкой и вероятностью цели;
  - «веер» капитала P5–P95 с медианой и линией взносов (`fl_chart`);
  - гистограмма терминального капитала;
  - топ сценариев с переходом к составу, налогам, комиссиям и стресс-тестам;
  - стресс-тесты с переключением сценария;
  - AI-объяснение и чат по `context_id`;
  - дисклеймер.
- Светлая/тёмная тема, переключатель в шапке.
- Ручной парсинг JSON без code generation.

## Структура

```text
mobile/
├── pubspec.yaml
├── lib/
│   ├── main.dart                     точка входа, AuthGate, тема
│   ├── theme/sber_theme.dart         палитра и ThemeData
│   ├── models/
│   │   ├── optimizer_models.dart     модели ответа API
│   │   └── auth_models.dart          пользователь и сессия
│   ├── services/
│   │   ├── api_client.dart           HTTP-клиент с Bearer-токеном
│   │   └── auth_store.dart           сохранение токена и адреса сервера
│   ├── screens/
│   │   ├── auth_screen.dart          вход и регистрация
│   │   ├── home_screen.dart          форма и запуск расчёта
│   │   └── results_screen.dart       результаты, модалки, стресс-тесты
│   └── widgets/
│       ├── risk_card.dart            карточка уровня риска
│       ├── fan_chart.dart            коридор P5–P95
│       ├── histogram_chart.dart      распределение капитала
│       └── ai_chat.dart              чат по расчёту
└── README.md
```

## API-контракт

Клиент использует:

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/v2/auth/register` | регистрация по email |
| `POST` | `/api/v2/auth/login` | вход, получение Bearer-токена |
| `GET` | `/api/v2/auth/me` | проверка токена и данные пользователя |
| `POST` | `/api/v2/auth/logout` | выход (токен удаляется на клиенте) |
| `GET` | `/api/v2/macro` | макросрез (не блокирует форму) |
| `POST` | `/api/v2/optimize/async` | запуск 10 000 путей |
| `GET` | `/api/v2/jobs/{id}` | прогресс и результат |
| `POST` | `/api/v2/ai/explain` | объяснение (опционально) |
| `POST` | `/api/v2/ai/chat` | чат по `context_id` |

Все расчётные и AI-методы требуют заголовок `Authorization: Bearer <token>`.
Синхронный `/api/v2/optimize` ограничен 3000 путями, поэтому мобильный клиент
всегда использует асинхронный режим.

## Проверка

```powershell
cd mobile
flutter analyze
flutter test
```

Автотестов Flutter пока нет: каркас не собирался в текущем окружении.
Backend-тесты (69) запускаются из корня:

```powershell
.\myvenv\Scripts\python.exe -m unittest discover -s DefultCredit/tests -v
```

## Ограничения

- Нет истории расчётов и локального кэша — это MVP-каркас.
- Токен хранится в `shared_preferences`; для production лучше
  `flutter_secure_storage` и HTTPS.
- AI-чат работает в шаблонном режиме, если на сервере не заданы ключи LLM.
- Числа и ставки — сценарные допущения, а не индивидуальная инвестиционная
  рекомендация.
- Для production нужны HTTPS, pinning/secure storage, rate limit и
  обработка офлайн-режима.
