# WireGuard + Telegram Bot + SQLite

Серверная связка: **WireGuard VPN** (на случайном порту), **Telegram-бот** для управления конфигами и пользователями, **SQLite** с ежедневной статистикой.

## Сети

- **Общая подсеть** `10.0.113.0/24` — устройства видят друг друга и доступны остальным.
- **Изолированные подсети** `10.0.i.0/24` (i ≠ 113) — доступ только между устройствами в одной такой подсети.

Изоляция обеспечивается правилами iptables (скрипт `scripts/setup-wg-isolation.sh`).

## Функции бота

### Пользователь
- Создать конфиг в **общей** сети или в **своей** изолированной (одна изолированная подсеть на пользователя).
- Отключить / включить / удалить свой конфиг.

### Админ
- Всё то же + создание конфигов в **любой** изолированной подсети (указание номера).
- Управление пользователями: добавление, отключение, удаление.
- **Пригласительная ссылка** — одноразовая. Админ нажимает «🔗 Пригласительная ссылка», бот выдаёт ссылку; кто первый перейдёт — добавляется в бота, после этого ссылка недействительна (повторная передача не сработает).
- Просмотр статистики.

Пользователи: по пригласительной ссылке, командой `/add_user <telegram_id> [1 для админа]` или через БД. ID из `TELEGRAM_ADMIN_IDS` при первом `/start` автоматически добавляются как админы.

Управление конфигами — через **inline-меню** (кнопки под сообщениями): список конфигов → выбор → включить/отключить/удалить. Названия интерфейсов задают пользователи при создании конфига.

## Установка и запуск

### Одной командой (Docker или native + автозапуск)

Скрипт спросит: установить в Docker или на хост (systemd), запросит токен бота, ID админов и endpoint сервера, установит WireGuard и бота и добавит в автозапуск.

```bash
# Из каталога проекта:
sh scripts/install.sh
```

Или скачать и запустить (подставить свой URL репозитория или хостинг скрипта):
```bash
export WIREGUARD_BOT_REPO=https://github.com/USER/wireguard-bot.git
sh -c "$(curl -fsSL https://YOUR_HOST/scripts/install.sh)"
```

### Вручную

1. Клонировать/скопировать проект, перейти в каталог:
   ```bash
   cd wireguard-bot
   ```

2. Создать конфиг и окружение:
   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   # Вписать в config.yaml и .env: TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_IDS, server.endpoint, server.public_key
   ```

3. Развернуть WireGuard на сервере (один раз):
   ```bash
   chmod +x scripts/deploy.sh
   sudo ./scripts/deploy.sh
   ```
   Скрипт создаёт ключи, выставляет случайный порт и выводит `public_key` и порт для `config.yaml`.

4. Запуск бота (локально):
   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m src.main
   ```
   (или `pip install -r requirements.txt` в своём окружении)

5. Или через Docker:
   ```bash
   docker compose up -d
   ```

Если WireGuard крутится на хосте, а бот в Docker — нужно пробросить каталог с конфигом WG в контейнер (в `docker-compose.yml` раскомментировать volume `/etc/wireguard`) и при необходимости дать контейнеру доступ к `wg`/файлам конфига.

## Конфигурация

- **config.yaml** — интерфейс WG, пути, подсети, `bot.admin_ids`, `server.public_key`, `server.endpoint`.
- **.env** — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS`, `DATABASE_PATH`, при необходимости `WG_SERVER_ENDPOINT`.

Порт WG можно задать в `wireguard.port` или оставить пустым — при первом запуске будет выбран случайный (см. `scripts/deploy.sh`).

## Статистика (SQLite)

Раз в день (по умолчанию в 00:05) собирается срез:
- число пиров (всего / включённых),
- трафик (rx/tx),
- разбивка по подсетям.

Данные пишутся в таблицу `daily_stats` в той же БД, что использует бот.

## Структура

```
wireguard-bot/
├── config.example.yaml
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── scripts/
│   ├── install.sh          # установка одной командой (Docker или native + автозапуск)
│   ├── deploy.sh           # первый запуск WG на сервере
│   └── setup-wg-isolation.sh  # iptables для изоляции подсетей
└── src/
    ├── main.py              # точка входа, планировщик
    ├── config.py
    ├── bot/
    │   ├── handlers.py      # команды и callback'и
    │   ├── filters.py       # админ / доступ
    │   └── keyboards.py
    ├── db/
    │   ├── database.py      # схема SQLite
    │   ├── models.py
    │   └── repository.py
    ├── wireguard/
    │   └── manager.py       # генерация конфигов, добавление/удаление пиров
    └── stats/
        └── collector.py     # ежедневный сбор статистики
```
