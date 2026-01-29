# Tech: Resource Plan Auditor Bot

## Выбранный стек (MVP)

- **Python 3.11+**
- **Google Sheets API**: `google-api-python-client`, `google-auth`
- **Telegram Bot**: `python-telegram-bot`
- **Scheduler**: `APScheduler` (для периодических проверок)
- **Конфиг**: `.env` + `pydantic-settings`

## Высокоуровневая архитектура

Компоненты:
- **Sheets Client**: чтение/запись данных из Google Sheets
- **Audit Service**: сбор данных, запуск проверок, формирование отчета
- **Checks**: независимые проверки (правила), возвращающие список проблем
- **Notifications**: отправка сообщений в Telegram (в будущем — Google Chat/Slack)
- **Bot API**: команды пользователя → запуск аудита/репортов/применение правок

Поток:
1) Планировщик (или бот-команда) запускает `AuditService`
2) `AuditService` читает таблицу
3) Преобразует в нормализованную модель (строки, люди, недели)
4) Прогоняет проверки
5) Формирует отчет (текст + структура)
6) Отправляет уведомление (и/или ждет команды пользователя)

## Доступ к Google Sheets

Поддерживаем 2 режима аутентификации (в конфиге `GOOGLE_AUTH_MODE`):

### 1) `service_account` (рекомендуется для “сервиса”)

- Создается Service Account в Google Cloud
- Таблица шарится на email сервис-аккаунта (как на обычный email), роль **Viewer**
- Ключи хранятся как файл JSON локально (не коммитить) или как переменная окружения

Переменные:
- `GOOGLE_SERVICE_ACCOUNT_FILE` (путь к json файлу)
- `GOOGLE_SCOPES` (опционально, scopes через запятую)

Чек-лист настройки:
1) Google Cloud Console → создать Project
2) Включить API: **Google Sheets API**
3) IAM & Admin → Service Accounts → создать аккаунт
4) Keys → создать JSON ключ → скачать
5) Положить файл, указать путь в `GOOGLE_SERVICE_ACCOUNT_FILE`
6) В Google Sheets → Share → добавить email сервис-аккаунта → Viewer

### 2) `oauth_user` (для локальной разработки)

- OAuth flow, токен сохраняется локально
- удобно для тестов “на своем аккаунте”

## Модель данных (концептуально)

Мы приводим таблицу к структуре:
- `Person` (id/имя/роль/капасити)
- `Week` (start_date)
- `Allocation` (person, week, project?, hours)

Важно: конкретный парсинг зависит от реального формата таблицы.

## Формат результата проверок

Каждая проверка возвращает список `Issue`:
- `severity`: `red|yellow|info`
- `code`: короткий код (например `MISSING_HOURS`)
- `message`: человеко-понятный текст
- `location`: где проблема (person/week/cell)
- `suggestion`: предложение исправления (если возможно)

## Безопасность

- Секреты только через `.env` / секреты окружения
- Логи не должны содержать:
  - токены бота
  - содержимое ключей Google
  - личные данные (по возможности маскировать)

## План развертывания (позже)

Варианты:
- Docker контейнер + облако (GCP/Render/Fly.io/AWS)
- Windows Task Scheduler (для локального запуска в офисе)
- GitHub Actions / Cloud Scheduler (если будет endpoint)

## Структура репозитория (ожидаемая)

- `src/config.py` — настройки
- `src/sheets/` — работа с Sheets API
- `src/checks/` — проверки
- `src/services/audit.py` — оркестрация аудита
- `src/notifications/` — уведомления
- `src/bot/` — чат-бот

