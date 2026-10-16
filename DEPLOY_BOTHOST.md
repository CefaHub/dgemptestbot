# Установка отдельного Dolce Empire на Bothost

Это **совсем другой** бот. Существующий `CefaHub/DolceGllitBot` не меняй.

1. В Telegram открой **@BotFather** → `/newbot` → название `Dolce Empire` → придумай уникальный username бота, заканчивающийся на `bot`.
2. На GitHub создай **новый** пустой репозиторий, например `DolceEmpireBot`, не загружай туда чужой токен или личную базу данных.
3. Распакуй архив. **Загрузи файлы из архива в корень нового репозитория**, не старого бота.
4. Bothost → **Создать бота** → Python → подключи новый Git-репозиторий.
5. В настройках окружения нового бота создай переменную `BOT_TOKEN` со значением от BotFather (не вставляй токен в исходник).
6. Укажи стартовый файл `main.py` или команду `python main.py`. Зависимости — из `requirements.txt`.
7. Если панель предоставляет отдельную PostgreSQL, добавь `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB`. Для SQLite важен **постоянный том**: без него после обновления можно потерять карточки и баланс.
8. Пересобери/перезапусти нового бота → открой его личку → `/start`. Получишь три стартовые карты и сможешь крутить гачу.

## Быстрая публикация через PowerShell (после создания пустого репозитория)

Открой PowerShell в папке с **распакованными** файлами и введи:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial Dolce Empire release"
git remote add origin https://github.com/ВАШ_ЛОГИН/DolceEmpireBot.git
git push -u origin main
```

Вместо `ВАШ_ЛОГИН` укажи имя своего GitHub. Если ещё не указаны имя/почта Git, выполни `git config --global user.name "CefaHub"` и `git config --global user.email "ПОЧТА_ОТ_GITHUB"`.

## Если возникла ошибка

- `TokenValidationError` — значение `BOT_TOKEN` пустое/неправильного формата. Получи реальный токен нового бота от BotFather.
- `TelegramConflictError` — запущены два экземпляра **одного** бота. Оставь один.
- `ModuleNotFoundError` — Bothost не установил пакеты из `requirements.txt`.
- `OperationalError`, `database is locked` — при нескольких одновременных пользователях или воркерах перейди с SQLite на PostgreSQL (вместо совместного SQLite).
- Прогресс сбросился — база лежала на временном диске. Перенеси хранение в постоянную PostgreSQL/том до следующего деплоя.

**Безопасность:** GitHub-репозиторий не должен содержать `.env`, `data/empire.db`, токены или экспорт базы.
