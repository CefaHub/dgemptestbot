# DOLCE EMPIRE — фотокарточки: полный состав, ориентир ~100

**Актуально: 19 октября 2026 года.** Цель **около 100**, не фиксированное ограничение. **Никогда не обрывать коллекцию на 2–3 участницах ради ровного числа**: публиковать только полный состав группы и всю одну серию одной редкости; выход за 100 допустим.

**Сейчас выпущено: 58 полноценных игровых фото в 12 наборах.** Начальная очередь рассчитана на 100 фото как сумму 20 *полных* альбомов; в ней осталось 42 фото в 8 наборах. Следующее расширение может вывести итог за 100; оно не должно урезать состав.

## Опубликованные альбомы

| Группа | Серия | Редкость | Фотографий |
|---|---|---|---:|
| ILLIT | SPOTLIGHT | EPIC | 5 |
| aespa | SPOTLIGHT | EPIC | 4 |
| aespa | AURA | RARE | 4 |
| aespa | VELVET LIGHT | LEGENDARY | 4 |
| ITZY | SPOTLIGHT | EPIC | 5 |
| LE SSERAFIM | SPOTLIGHT | EPIC | 5 |
| aespa | ROYAL HAZE | MYTHIC | 4 |
| LE SSERAFIM | AURA | RARE | 5 |
| LE SSERAFIM | VELVET LIGHT | LEGENDARY | 5 |
| IVE | AURA | RARE | 6 |
| IVE | SPOTLIGHT | EPIC | 6 |
| LE SSERAFIM | ROYAL HAZE | MYTHIC | 5 |

## Неопубликованные полные альбомы

| Приоритет | Группа | Серия | Редкость | Состав | Заметки / блокер |
|---:|---|---|---|---:|---|
| 1 | ITZY | AURA | RARE | 4 | Подобрана единая фотосессия ITZY G-SHOCK 23.10.2024. Исследовательские PNG для RYUJIN и CHAERYEONG собраны; исходники LIA и YUNA известны, но 404 у медиа-сервера; YEJI — пока нет подтверждённого исходника с правами. Сет не публиковать до 5/5 без повторов. |
| 2 | ILLIT | AURA | RARE | 4 | Нужны пять уникальных фото из одной серии |
| 3 | ILLIT | VELVET LIGHT | LEGENDARY | 4 | Нужны пять отдельных фото, не повторяющих EPIC |
| 4 | ITZY | VELVET LIGHT | LEGENDARY | 4 | Нужны пять отдельных фото, не повторяющих RARE/EPIC |
| 5 | IVE | VELVET LIGHT | LEGENDARY | 5 | Нужны шесть отдельных фото, не повторяющих RARE/EPIC |
| 6 | ILLIT | ROYAL HAZE | MYTHIC | 4 | Нужны пять уникальных фото, отдельная серия |
| 7 | ITZY | ROYAL HAZE | MYTHIC | 4 | Нужны пять уникальных фото, отдельная серия |
| 8 | IVE | ROYAL HAZE | MYTHIC | 5 | Нужны шесть уникальных фото, отдельная серия |

## Жёсткие критерии качества

- Только реально существующие фото, без ИИ-портретов, из подтверждённых источников с соблюдением лицензии.
- Один альбом = единое мероприятие/фотосессия, единая редкость; все действующие участницы, каждой свой уникальный снимок. Никого не пропускаем.
- Проверки дублей исходных URL и страниц, SHA-256 и перцептуального хеша глобально для всего каталога.
- Кроп 3:4 без растягивания и с целым лицом; необходимый исходный сольный регион не меньше 600×800, готовый PNG 900×1200, баннер 1600×900.
- Перед публикацией — контакт-лист и визуальная проверка. Если хотя бы одна фотография плохая или без подтверждённых прав, весь альбом остаётся превью, а не добавляется частично.

## Последний релиз

IVE SPOTLIGHT EPIC: **6 из 6 реальных фото**, 19 октября 2026. Юджин, Гаыль, Рей, Вонён, Лиз, Лисо. Один концерт (Амстердам 13.06.2024), другие фотографии относительно AURA RARE. [Карточки](https://github.com/CefaHub/dgemptestbot/tree/main/assets/cards/ive) · [баннер](https://github.com/CefaHub/dgemptestbot/blob/main/assets/banners/ive/ive_spotlight_epic_banner.png). Все шесть оформлены единым мастер-шаблоном, игровой каталог 58 карт.



LE SSERAFIM ROYAL HAZE MYTHIC: **5 из 5 фотографий** — CHAEWON, SAKURA, YUNJIN, KAZUHA, EUNCHAE. Действительно выпущены на GitHub 19.10.2026, без повторов оригиналов и без генеративных портретов. [Карточки](https://github.com/CefaHub/dgemptestbot/tree/main/assets/cards/lesserafim) · [Баннер](https://github.com/CefaHub/dgemptestbot/blob/main/assets/banners/lesserafim/lesserafim_royal_haze_mythic_banner.png).

Ранее выпущен IVE AURA RARE: **6 из 6 фотографий** — YUJIN, GAEUL, REI, WONYOUNG, LIZ, LEESEO. Одна концертная серия из 42 фотографий Robbie Klinkenberg (Амстердам, 13.06.2024), CC BY-SA 4.0. [Карточки на GitHub](https://github.com/CefaHub/dgemptestbot/tree/main/assets/cards/ive) · [Баннер](https://github.com/CefaHub/dgemptestbot/blob/main/assets/banners/ive/ive_aura_rare_banner.png).

## Изменяемость цели

Рабочие `tools/photo_release_plan.json` и `tools/photo_production_schedule.json` согласованы между собой, а код сверяет суммарное число карточек **из полных запланированных групп** с объявленным target, не с магической константой 100. При добавлении новых групп/серий обновить план и очередь полными коллекциями, после чего цель может стать 101, 103, 116 и т. д. Тест `test_approximate_goal_can_expand_by_whole_member_sets` проверяет этот сценарий.

Первоисточник правил оформления: [CARD_IMAGE_MASTER_BRIEF_RU.md](CARD_IMAGE_MASTER_BRIEF_RU.md), подтверждённые изображения — [GALLERY.md](../GALLERY.md).
