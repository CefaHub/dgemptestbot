"""Telegram UI for Dolce Empire. All mutations delegate to transactional Game service."""
import asyncio
import json
from functools import lru_cache
import logging
import os
from html import escape
from pathlib import Path
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile, FSInputFile, InputMediaPhoto, BotCommand
from aiogram.exceptions import TelegramAPIError
from .db import engine_and_session, init_database, retire_unverified_cards_once, CURATION_RESET_KEY
from .service import Game, GameError
from .economy import slot_upgrade_price
from .catalog import RARITY_EMOJIS, RARITY_TITLES, album_groups, search_cards, get_card, all_cards
from .art import render_card

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
log=logging.getLogger('dolce_empire')
router=Router()
service: Game | None=None
BUILD_VERSION = '2026.10.17-unique-photo-r2'


def g():
    if service is None:raise RuntimeError('Bot game service has not been initialized')
    return service


def n(value): return f'{value:,}'.replace(',',' ')


def kb(*rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=title, callback_data=data) for title,data in row]
        for row in rows])


def main_kb():
    return kb([('🎰 Гача','nav:roll'),('🏢 Тайкун','nav:studio')],
              [('🃏 Карточки','cards:0'),('📚 Альбомы','nav:albums')],
              [('✨ SPOTLIGHT','nav:spotlight'),('🌟 Новые сеты','nav:sets')],
              [('🤝 Обмены','nav:trades'),('🛒 Рынок','nav:market')],
              [('🎁 Задания','nav:quests'),('🏆 Топ','nav:top')])


def back(): return [('◀️ Главное меню','nav:home')]


def user_id(event):
    u=event.from_user
    if not u:raise GameError('Не удалось определить пользователя.')
    return u.id


async def send(event, content, markup=None):
    if isinstance(event,CallbackQuery):
        await event.answer()
        if event.message:
            try:
                await event.message.edit_text(content,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)
                return
            except TelegramAPIError:
                pass
        await event.bot.send_message(user_id(event),content,reply_markup=markup,parse_mode='HTML')
    else:
        await event.answer(content,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True)


async def show_home(event):
    p=await g().profile(user_id(event))
    text=(f'✨ <b>DOLCE EMPIRE</b> ✨\n\n'
          f'Продюсер: <b>{escape(p["name"])}</b>\n'
          f'🪙 Монеты: <b>{n(p["coins"])}</b>\n'
          f'🏢 Доход: <b>{n(p["income"])}/ч</b>\n'
          f'💰 Не собрано: <b>{n(p["pending"])}</b>\n'
          f'🆓 Бесплатных круток: <b>{p["free"]}/3</b>\n\n'
          'Выбирай раздел 👇')
    await send(event,text,main_kb())


@router.message(CommandStart())
async def start(message:Message):
    await g().start(user_id(message),message.from_user.full_name)
    await show_home(message)


@router.message(Command('version'))
async def version_cmd(message: Message):
    """Show the deployed build identity to distinguish hosting cache from GitHub main."""
    await message.answer(
        f'🔧 DOLCE EMPIRE\nСборка: <code>{BUILD_VERSION}</code>\n'
        'Галерея SPOTLIGHT: 1 баннер за раз, стрелки ◀️ ▶️',
        parse_mode='HTML',
    )


@router.message(Command('help'))
async def help_cmd(message:Message):
    text='''<b>🎮 DOLCE EMPIRE — команды</b>
/start — главное меню
/version — проверить загруженную версию бота
/me — профиль
/roll — гача и цены
/studio — студия и сбор монет
/claim — забрать накопленное
/cards [страница] — инвентарь, номера экземпляров
/find ИМЯ — найти карты (Eunchae или Ынче)
/card ID — карточка
/equip ID СЛОТ — поставить в студию
/unequip ID — снять карточку
/upgrade ID — поднять уровень
/awake ID — пробудить дубликатом
/expand — купить слот студии
/album — коллекции
/spotlight — новые EPIC-сеты ILLIT и aespa
/sets — галерея всех новых коллекций
/daily — ежедневная награда
/quests — задания
/market — рынок (фиксированные цены)
/sell ID ЦЕНА — выставить карточку
/buy ID — купить объявление
/unsell ID — снять объявление
/trade — справка по безопасным обменам
/trades — твои сделки
/top — рейтинги

<b>Пример обмена (ответом на сообщение другого игрока):</b>
<code>/trade 25 48 0 500</code>
Отдаёшь карточку №25, хочешь карточку №48 и 500 монет от адресата.
Можно использовать 0 вместо карточки или монет.

Другой вариант, без reply:
<code>/trade USER_ID 25 48 0 500</code>

❗️Карточка для торговли должна быть снята со слота, а условия обе стороны подтверждают отдельно. Комиссия рынка — 5%.'''
    await message.answer(text,parse_mode='HTML')


@router.message(Command('me'))
async def me(message:Message): await show_home(message)


async def show_roll(event):
    p=await g().profile(user_id(event))
    remaining='Готовы к использованию' if p['free'] else ('Следующая: '+p['refill_at'].strftime('%H:%M UTC') if p['refill_at'] else 'Через час')
    msg=(f'🎰 <b>ГАЧА</b>\n\n🆓 Заряды: <b>{p["free"]}/3</b> — {remaining}\n'
         f'💸 Обычная крутка: <b>{n(p["price"])} 🪙</b>\n'
         '💎 Премиум-баннер: временно недоступен (нет проверенных сетов других редкостей)\n'
         f'📈 Платных круток сегодня: <b>{p["paid_count"]}</b>\n\n'
         'Цена зависит от рекордного дохода в час и растёт на 15% за каждую платную крутку за сутки. '
         'Бесплатная крутка не дорожает. Сейчас доступны только EPIC-фотокарты из двух цельных сетов.\n\n'
         'Гаранты других редкостей заработают после выхода проверенных сетов.')
    await send(event,msg,kb([('🎁 Бесплатная','roll:free')],
                            [('🪙 Обычная','roll:paid')],back()))


@router.message(Command('roll'))
async def roll_cmd(message:Message):await show_roll(message)


async def show_roll_result(event, mode):
    r=await g().roll(user_id(event),mode)
    c=r['card'];tier=c['rarity']
    caption=(f'🎉 <b>НОВАЯ КАРТОЧКА!</b>\n'
             f'{RARITY_EMOJIS[tier]} <b>{escape(c["name"])}</b> — {RARITY_TITLES[tier]}\n'
             f'{escape(c["group"])} · {escape(c["era"])}\n'
             f'🆔 #{c["id"]} · +{n(c["hourly"])}/ч\n'
             f'🪙 Стоимость: {n(r["price"])}\n\n'
             'Поставь карточку в студию через её профиль, чтобы получать доход.')
    photo=BufferedInputFile(render_card(c['definition_id'], c['level'], c['awakening'], c['id']),filename='dolce_card.png')
    markup=kb([('🃏 Открыть карту',f'card:{c["id"]}'),('🔁 Ещё крутка','nav:roll')],back())
    if isinstance(event,CallbackQuery):
        await event.answer('Карточка получена!')
        await event.bot.send_photo(user_id(event),photo,caption=caption,parse_mode='HTML',reply_markup=markup)
    else:
        await event.answer_photo(photo,caption=caption,parse_mode='HTML',reply_markup=markup)


async def show_studio(event):
    p=await g().profile(user_id(event))
    cards=[c for c in await g().cards(user_id(event)) if c['slot'] is not None]
    cards.sort(key=lambda v:v['slot'])
    lines=[f'🏢 <b>ТВОЯ СТУДИЯ</b>\n🪙 Баланс: <b>{n(p["coins"])}</b>',
           f'📈 Доход: <b>{n(p["income"])}/ч</b> (бонус сетов: +{p["album_bonus"]}%)',
           f'💰 Ожидает сбора: <b>{n(p["pending"])}</b>',
           f'🔓 Слотов: <b>{p["slots"]}/8</b>\n']
    lines += [f'{c["slot"]}. {RARITY_EMOJIS[c["rarity"]]} <b>{escape(c["name"])}</b> · Lv.{c["level"]} · +{n(c["hourly"])}/ч · #{c["id"]}' for c in cards]
    if p['slots']<8:lines.append(f'\nНовый слот: {n(slot_upgrade_price(p["slots"]))} 🪙')
    else:lines.append('\nВсе слоты открыты!')
    await send(event,'\n'.join(lines),kb([('💰 Забрать доход','act:claim'),('➕ Купить слот','act:expand')],
                                          [('🃏 Выбрать карты','cards:0')],back()))


@router.message(Command('studio'))
async def studio_cmd(message:Message):await show_studio(message)


@router.message(Command('claim'))
async def claim_cmd(message:Message):
    amount,total=await g().claim(user_id(message))
    await message.answer(f'🪙 Собрано {n(amount)} монет! На счету: {n(total)}.')


async def show_cards(event,page=0):
    items=await g().cards(user_id(event))
    page=max(0,min(page,max(0,(len(items)-1)//8)))
    subset=items[page*8:(page+1)*8]
    lines=[f'🃏 <b>МОЯ КОЛЛЕКЦИЯ</b> — {len(items)} экземпляров\n',
           'Нажми на карту для улучшений и назначения в студию:\n']
    rows=[]
    for c in subset:
        lines.append(f'{RARITY_EMOJIS[c["rarity"]]} <b>#{c["id"]} {escape(c["name"])}</b> · Lv.{c["level"]}'+(f' [слот {c["slot"]}]' if c['slot'] else ''))
        rows.append([(f'#{c["id"]} {c["name"][:18]}',f'card:{c["id"]}')])
    nav=[]
    if page>0:nav.append(('⬅️',f'cards:{page-1}'))
    if (page+1)*8<len(items):nav.append(('➡️',f'cards:{page+1}'))
    if nav:rows.append(nav)
    rows.append(back())
    await send(event,'\n'.join(lines),kb(*rows))


@router.message(Command('cards'))
async def cards_cmd(message:Message):
    args=(message.text or '').split()
    page=(int(args[1])-1) if len(args)>1 and args[1].isdigit() else 0
    await show_cards(message,page)


async def show_card(event,card_id):
    c=await g().card_details(user_id(event),card_id)
    # Keep fixed suffix separate from conditional text.
    header=(f'{RARITY_EMOJIS[c["rarity"]]} <b>{escape(c["name"])}</b> — {RARITY_TITLES[c["rarity"]]}\n'
         f'{escape(c["group"])} / {escape(c["era"])}\n'
         f'🆔 Серийный №{c["id"]}\n⭐ Уровень: {c["level"]}/50\n'
         f'🌟 Пробуждение: {c["awakening"]}/5\n'
         f'🪙 Доход: {n(c["hourly"])}/ч\n'
         f'🏢 Слот: {c["slot"] or "нет"}\n'
         + (f'📈 Улучшение: {n(c["upgrade_price"])} 🪙\n' if c['upgrade_price'] is not None else '📈 Максимальный уровень\n')
         + f'🃏 Дубликаты: {len(c["dupes"])}')
    rows=[[('⬆️ Улучшить',f'act:upgrade:{c["id"]}'),('🌟 Пробудить',f'act:awake:{c["id"]}')]]
    studio_slots=(await g().profile(user_id(event)))['slots']
    for start_slot in (1,5):
        if start_slot<=studio_slots:
            rows.append([('🏢 В слот '+str(i),f'act:equip:{c["id"]}:{i}')
                        for i in range(start_slot,min(start_slot+4,studio_slots+1))])
    rows.append([('📤 Снять со слота',f'act:unequip:{c["id"]}')])
    rows.append([('🃏 Инвентарь','cards:0'),('🏠 Меню','nav:home')])
    photo=BufferedInputFile(render_card(c['definition_id'],c['level'],c['awakening'],c['id']),filename='card.png')
    if isinstance(event,CallbackQuery):
        await event.answer()
        await event.bot.send_photo(user_id(event),photo,caption=header,reply_markup=kb(*rows),parse_mode='HTML')
    else:
        await event.answer_photo(photo,caption=header,reply_markup=kb(*rows),parse_mode='HTML')


@router.message(Command('find','search'))
async def search_cmd(message:Message):
    query=(message.text or '').split(maxsplit=1)
    if len(query)<2 or not query[1].strip():
        raise GameError('Используй: /find Ынче (или /find Eunchae)')
    matches=search_cards(query[1])
    owned=await g().cards(user_id(message))
    matched_ids={d['id'] for d in matches}
    mine=[c for c in owned if c['definition_id'] in matched_ids]
    lines=[f'🔎 <b>Поиск: {escape(query[1][:60])}</b>',
           f'В каталоге найдено версий: {len(matches)}']
    for item in matches[:12]:
        lines.append(f'{RARITY_EMOJIS[item["rarity"]]} {escape(item["idol"])} · {escape(item["group"])} / {escape(item["era"])}')
    if mine:
        lines.append('\n<b>Твои экземпляры:</b>')
        lines += [f'#{c["id"]} {escape(c["name"])} · Lv.{c["level"]}' for c in mine[:12]]
    if not matches:lines.append('Ничего не найдено. Попробуй другое написание.')
    rows=[[(f'🃏 Открыть #{c["id"]}',f'card:{c["id"]}')] for c in mine[:6]]
    rows.append(back())
    await message.answer('\n'.join(lines),parse_mode='HTML',reply_markup=kb(*rows))


@router.message(Command('card'))
async def card_cmd(message:Message):
    args=(message.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /card ID')
    await show_card(message,int(args[1]))


async def show_album(event):
    groups=album_groups()
    progress=await g().album(user_id(event))
    by_group={}
    for a in progress:
        by_group.setdefault(a['group'],[]).append(a)
    lines=['📚 <b>АЛЬБОМЫ</b>\n','Найденные однажды карты сохраняются в альбоме навсегда. Каждый полный сет даёт +5% дохода, суммарно не более +20%.\n']
    for name,items in by_group.items():
        got=sum(i['found'] for i in items);total=sum(i['total'] for i in items)
        completed=sum(i['completed'] for i in items)
        lines.append(f'🎤 <b>{escape(name)}</b> — {got}/{total} · полных сетов: {completed}')
    rows=[[(name[:28],f'album:{index}')] for index,name in enumerate(groups)]
    rows.append(back())
    await send(event,'\n'.join(lines),kb(*rows))


async def show_album_group(event,index):
    groups=list(album_groups().items())
    if not 0<=index<len(groups):raise GameError('Группа не найдена.')
    name,eras=groups[index]
    progress=await g().album(user_id(event))
    lines=[f'🎤 <b>{escape(name)}</b>\n']
    for era,defs in eras.items():
        stats=next((s for s in progress if s['group']==name and s['era']==era),None)
        lines.append(f'📀 <b>{escape(era)}</b>: {stats["found"]}/{stats["total"]}'+(' ✅' if stats['completed'] else ''))
        lines.append(', '.join(escape(c['idol']) for c in defs))
        lines.append('')
    await send(event,'\n'.join(lines),kb([('◀️ Все группы','nav:albums')],back()))


# Only one Spotlight release is displayed per Telegram message.
SPOTLIGHT_SETS = (
    ('ILLIT', '5/5', 'Юна · Минджу · Мока · Вонхи · Ироха',
     'assets/banners/illit/illit_spotlight_epic_banner.png'),
    ('aespa', '4/4', 'Карина · Винтер · Жизель · Ниннин',
     'assets/banners/aespa/aespa_spotlight_epic_banner.png'),
)


async def show_spotlight(event, page: int = 0):
    """Single-message Spotlight carousel. Arrow clicks edit the existing banner."""
    if not 0 <= page < len(SPOTLIGHT_SETS):
        raise GameError('Такой страницы SPOTLIGHT нет.')

    group, count, names, relative_path = SPOTLIGHT_SETS[page]
    caption = (f'✨ <b>{escape(group)} — SPOTLIGHT</b>\n'
               f'🟣 Редкость: <b>EPIC</b> · полный сет {count}\n'
               f'{escape(names)}\n'
               '📚 Бонус за полный сет: +5% к доходу (общий лимит +20%).\n'
               '🎰 Карточки доступны в обычной и премиум-гаче.\n\n'
               f'📖 Коллекция {page + 1}/{len(SPOTLIGHT_SETS)} · {BUILD_VERSION}')
    buttons = kb(
        [('◀️', f'spotlight:{(page - 1) % len(SPOTLIGHT_SETS)}'),
         ('▶️', f'spotlight:{(page + 1) % len(SPOTLIGHT_SETS)}')],
        [('🎰 Крутить', 'nav:roll'), ('📚 Альбомы', 'nav:albums')],
        back(),
    )
    banner = Path(__file__).resolve().parent.parent / relative_path

    if isinstance(event, CallbackQuery):
        await event.answer()
        # When browsing an existing photo, update that same message instead of
        # sending another image and filling the chat with duplicate banners.
        if isinstance(event.message, Message) and event.message.photo:
            try:
                if banner.is_file():
                    await event.message.edit_media(
                        media=InputMediaPhoto(
                            media=FSInputFile(banner), caption=caption, parse_mode='HTML'
                        ),
                        reply_markup=buttons,
                    )
                else:
                    await event.message.edit_caption(
                        caption=caption, parse_mode='HTML', reply_markup=buttons
                    )
                return
            except TelegramAPIError:
                log.warning('Could not edit SPOTLIGHT photo, sending a replacement', exc_info=True)
        if banner.is_file():
            await event.bot.send_photo(
                user_id(event), FSInputFile(banner), caption=caption,
                parse_mode='HTML', reply_markup=buttons
            )
        else:
            await event.bot.send_message(
                user_id(event), caption, parse_mode='HTML', reply_markup=buttons
            )
        return

    if banner.is_file():
        await event.answer_photo(
            FSInputFile(banner), caption=caption, parse_mode='HTML', reply_markup=buttons
        )
    else:
        await event.answer(caption, parse_mode='HTML', reply_markup=buttons)


@lru_cache(maxsize=1)
def collection_gallery():
    manifest = Path(__file__).resolve().parent.parent / 'assets/collections/verified_sets.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    return [
        {
            'group': row['group'],
            'series': row['era'],
            'rarity': row['rarity'],
            'size': len(row['expected_members']),
            'banner': row['banner_path'],
            'photo_series': row['source_collection'],
        }
        for row in data['sets']
    ]

async def show_sets(event, page=0):
    """Paginated gallery of all full-member K-pop collection releases."""
    items = collection_gallery()
    if not items:
        raise GameError('Коллекции ещё не установлены.')
    if not 0 <= page < len(items):
        raise GameError('Такой страницы нет.')
    item = items[page]
    caption = (f'🌟 <b>{escape(item["group"])} — {escape(item["series"])}</b>\n'
               f'{RARITY_EMOJIS[item["rarity"]]} Редкость: <b>{RARITY_TITLES[item["rarity"]]}</b>\n'
               f'🃏 Полный состав: <b>{item["size"]}/{item["size"]}</b>\n'
               f'📖 Коллекция {page+1}/{len(items)}\n'
               f'📷 Фотосерия: {escape(item["photo_series"])}\n'
               'Карточки доступны в гаче. Это одна серия снимков, не официальный альбом.')
    markup=kb(
        [('◀️', f'sets:{(page-1)%len(items)}'),
         ('▶️', f'sets:{(page+1)%len(items)}')],
        [('🎰 Крутить','nav:roll'),('📚 Альбомы','nav:albums')],
        back(),
    )
    imagepath=Path(__file__).resolve().parent.parent / item['banner']
    if isinstance(event, CallbackQuery):
        await event.answer()
        if isinstance(event.message, Message) and event.message.photo and imagepath.is_file():
            try:
                await event.message.edit_media(
                    media=InputMediaPhoto(media=FSInputFile(imagepath),caption=caption,parse_mode='HTML'),
                    reply_markup=markup,
                )
                return
            except TelegramAPIError:
                log.warning('Unable to edit collection photo in-place',exc_info=True)
        if imagepath.is_file():
            await event.bot.send_photo(user_id(event),FSInputFile(imagepath),
                                       caption=caption,parse_mode='HTML',reply_markup=markup)
        else:
            await event.bot.send_message(user_id(event),caption,
                                         parse_mode='HTML',reply_markup=markup)
    else:
        if imagepath.is_file():
            await event.answer_photo(FSInputFile(imagepath),caption=caption,
                                     parse_mode='HTML',reply_markup=markup)
        else:
            await event.answer(caption,parse_mode='HTML',reply_markup=markup)


async def show_market(event):
    entries=await g().market()
    lines=['🛒 <b>РЫНОК КАРТОЧЕК</b>\n','Фиксированные объявления; комиссия с продавца 5%.\n']
    rows=[]
    for x in entries:
        c=x['card']
        lines.append(f'#{x["id"]}: {RARITY_EMOJIS[c["rarity"]]} <b>{escape(c["name"])}</b> Lv.{c["level"]} · {n(x["price"])} 🪙 (карта #{c["id"]})')
        rows.append([(f'🪙 Купить лот #{x["id"]}',f'buy:{x["id"]}')])
    if not entries:lines.append('Пока нет объявлений.')
    lines.append('\nВыставить: <code>/sell ID ЦЕНА</code> · Снять: <code>/unsell ID_ЛОТА</code>')
    rows.append(back())
    await send(event,'\n'.join(lines),kb(*rows))


async def show_trades(event):
    trades=await g().recent_trades(user_id(event))
    lines=['🤝 <b>ТВОИ ОБМЕНЫ</b>\n']
    rows=[]
    for t in trades:
        other=t['receiver'] if t['sender']==user_id(event) else t['sender']
        lines.append(f'#{t["id"]} · {t["status"]} · игрок {other}: отдать #{t["sender_card"] or "—"} + {n(t["sender_coins"])} 🪙, получить #{t["receiver_card"] or "—"} + {n(t["receiver_coins"])} 🪙')
        if t['status']=='pending' and t['receiver']==user_id(event):
            rows.append([('✅ Принять #'+str(t['id']),f'trade:accept:{t["id"]}')])
        elif t['status']=='accepted' and t['sender']==user_id(event):
            rows.append([('✅ Завершить #'+str(t['id']),f'trade:confirm:{t["id"]}')])
        if t['status'] in ('pending','accepted'):rows.append([('❌ Отменить #'+str(t['id']),f'trade:cancel:{t["id"]}')])
    if not trades:lines.append('Нет предложений. Инструкция: /trade')
    rows.append(back())
    await send(event,'\n'.join(lines),kb(*rows))


async def show_quests(event):
    p=await g().quests(user_id(event))
    names=[('roll',1,p['roll'],'Сделать крутку'),('claim',2,p['claim'],'Собрать монеты'),('upgrade',4,p['upgrade'],'Улучшить карту')]
    lines=['🎁 <b>ЗАДАНИЯ НА СЕГОДНЯ</b>\n','Сброс в 00:00 UTC. Каждая выполненная задача даёт монеты, зависящие от дохода студии.\n']
    rows=[]
    for code,bit,progress,title in names:
        done=bool(p['claimed_mask'] & bit)
        lines.append(f'{"✅" if done else "🟢" if progress else "⬜"} {title}: {min(progress,1)}/1')
        if not done:rows.append([('🎁 Забрать '+title,f'quest:{code}')])
    rows.append([('🎀 Ежедневный подарок','act:daily')])
    rows.append(back())
    await send(event,'\n'.join(lines),kb(*rows))


async def show_leaders(event,kind='income'):
    labels={'income':'пиковому доходу','rich':'монетам','rolls':'круткам','collector':'собранным монетам'}
    vals=await g().leaders(kind)
    lines=[f'🏆 <b>ТОП ПО {labels[kind].upper()}</b>\n']
    for index,p in enumerate(vals,1):
        lines.append(f'{index}. <b>{escape(p["name"])}</b> — {n(p["value"])}')
    await send(event,'\n'.join(lines),kb([('🪙 Баланс','top:rich'),('🏢 Доход','top:income')],
                                         [('🎰 Крутки','top:rolls'),('💰 Собрано','top:collector')],back()))


@router.message(Command('sets','collections'))
async def sets_cmd(m: Message):await show_sets(m)

@router.message(Command('spotlight'))
async def spotlight_cmd(m:Message):await show_spotlight(m)

@router.message(Command('album'))
async def album_cmd(m:Message):await show_album(m)
@router.message(Command('market'))
async def market_cmd(m:Message):await show_market(m)
@router.message(Command('trades'))
async def trades_cmd(m:Message):await show_trades(m)
@router.message(Command('quests'))
async def quests_cmd(m:Message):await show_quests(m)
@router.message(Command('top'))
async def top_cmd(m:Message):await show_leaders(m)
@router.message(Command('daily'))
async def daily_cmd(m:Message):
    reward=await g().daily(user_id(m))
    await m.answer(f'🎁 Ежедневный подарок: +{n(reward)} 🪙')


@router.message(Command('trade'))
async def trade_cmd(m:Message):
    args=(m.text or '').split()[1:]
    if not args:
        await help_cmd(m);return
    target=m.reply_to_message.from_user.id if m.reply_to_message and m.reply_to_message.from_user else None
    if target:
        if len(args) not in (2,4):raise GameError('Ответом на сообщение: /trade МОЯ_КАРТА ЕГО_КАРТА [МОИ_МОНЕТЫ ЕГО_МОНЕТЫ]')
    else:
        if len(args) not in (3,5):raise GameError('Без reply: /trade USER_ID МОЯ_КАРТА ЕГО_КАРТА [МОИ_МОНЕТЫ ЕГО_МОНЕТЫ]')
        try:target=int(args.pop(0))
        except ValueError:raise GameError('USER_ID должен быть числом.')
    try:values=[int(v) for v in args]
    except ValueError:raise GameError('Все значения сделки должны быть числами.')
    cid1,cid2=values[0],values[1]
    money1,money2=(values[2],values[3]) if len(values)==4 else (0,0)
    if cid1<0 or cid2<0:raise GameError('ID карточки не может быть отрицательным.')
    trade_id=await g().offer_trade(user_id(m),target,cid1,cid2,money1,money2)
    await m.answer(f'✅ Обмен #{trade_id} создан. Получатель должен принять, а потом ты подтвердить завершение.')
    try:
        await m.bot.send_message(target,
            f'🤝 Тебе предложен обмен #{trade_id}!\nОтдаёшь карточку #{cid2 or "—"} + {n(money2)} 🪙\nПолучаешь карточку #{cid1 or "—"} + {n(money1)} 🪙\nПроверь условия и нажми кнопку.',
            reply_markup=kb([('✅ Принять',f'trade:accept:{trade_id}'),('❌ Отклонить',f'trade:cancel:{trade_id}')]))
    except TelegramAPIError:
        await m.answer('⚠️ Второму игроку не удалось написать в личку — пусть сначала откроет бота и зайдёт в /trades.')


@router.message(Command('sell'))
async def sell_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=3 or not all(s.isdigit() for s in args[1:]):raise GameError('Используй: /sell ID_КАРТЫ ЦЕНА')
    lid=await g().list_card(user_id(m),int(args[1]),int(args[2]))
    await m.answer(f'🛒 Лот #{lid} выставлен. Комиссия при продаже — 5%.')


@router.message(Command('unsell'))
async def unsell_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /unsell ID_ЛОТА')
    await g().cancel_listing(user_id(m),int(args[1]));await m.answer('✅ Объявление снято.')


@router.message(Command('buy'))
async def buy_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /buy ID_ЛОТА')
    result,tax=await g().buy(user_id(m),int(args[1]))
    await m.answer(f'✅ Куплена карта #{result["id"]} {escape(result["name"])}. Комиссия продавца {n(tax)}.',parse_mode='HTML')


@router.message(Command('equip'))
async def equip_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=3 or not all(x.isdigit() for x in args[1:]):raise GameError('Используй: /equip ID_КАРТЫ НОМЕР_СЛОТА')
    c=await g().equip(user_id(m),int(args[1]),int(args[2]));await m.answer(f'✅ {c["name"]} установлена в слот {c["slot"]}.')


@router.message(Command('unequip'))
async def unequip_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /unequip ID_КАРТЫ')
    await g().unequip(user_id(m),int(args[1]));await m.answer('✅ Карточка снята со слота.')


@router.message(Command('upgrade'))
async def upgrade_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /upgrade ID_КАРТЫ')
    c,cost=await g().upgrade(user_id(m),int(args[1]))
    await m.answer(f'⬆️ {c["name"]}: уровень {c["level"]}, +{n(c["hourly"])}/ч. Потрачено {n(cost)} 🪙.')


@router.message(Command('awake'))
async def awake_cmd(m:Message):
    args=(m.text or '').split()
    if len(args)!=2 or not args[1].isdigit():raise GameError('Используй: /awake ID_КАРТЫ')
    c,used=await g().awaken(user_id(m),int(args[1]))
    await m.answer(f'🌟 {c["name"]} пробуждена до {c["awakening"]}/5, использован дубликат #{used}.')


@router.message(Command('expand'))
async def expand_cmd(m:Message):
    slots,cost=await g().upgrade_studio(user_id(m))
    await m.answer(f'🏢 Открыт слот {slots}/8 за {n(cost)} 🪙.')


@router.callback_query(F.data.startswith('nav:'))
async def nav_callback(c:CallbackQuery):
    section=c.data.split(':',1)[1]
    match section:
        case 'home':await show_home(c)
        case 'roll':await show_roll(c)
        case 'studio':await show_studio(c)
        case 'albums':await show_album(c)
        case 'spotlight':await show_spotlight(c)
        case 'sets':await show_sets(c)
        case 'trades':await show_trades(c)
        case 'market':await show_market(c)
        case 'quests':await show_quests(c)
        case 'top':await show_leaders(c)
        case _:raise GameError('Раздел не найден.')


@router.callback_query(F.data.startswith('sets:'))
async def sets_callback(c: CallbackQuery):
    index = c.data.split(':',1)[1]
    if not index.isdecimal():
        raise GameError('Неверный номер коллекции.')
    await show_sets(c,int(index))


@router.callback_query(F.data.startswith('spotlight:'))
async def spotlight_callback(c: CallbackQuery):
    raw = c.data.split(':', 1)[1]
    if not raw.isdecimal():
        raise GameError('Неверная страница SPOTLIGHT.')
    await show_spotlight(c, int(raw))


@router.callback_query(F.data.startswith('cards:'))
async def cards_callback(c:CallbackQuery):
    await show_cards(c,int(c.data.split(':')[1]))


@router.callback_query(F.data.startswith('card:'))
async def card_callback(c:CallbackQuery):
    await show_card(c,int(c.data.split(':')[1]))


@router.callback_query(F.data.startswith('album:'))
async def album_callback(c:CallbackQuery):
    await show_album_group(c,int(c.data.split(':')[1]))


@router.callback_query(F.data.startswith('roll:'))
async def roll_callback(c:CallbackQuery):
    await show_roll_result(c,c.data.split(':')[1])


@router.callback_query(F.data.startswith('act:'))
async def action_callback(c:CallbackQuery):
    args=c.data.split(':')
    op=args[1]
    if op=='claim':
        amount,total=await g().claim(user_id(c))
        await c.answer(f'+{n(amount)} монет!',show_alert=True)
        await show_studio(c)
    elif op=='expand':
        slots,cost=await g().upgrade_studio(user_id(c))
        await c.answer(f'Слот {slots} открыт!',show_alert=True)
        await show_studio(c)
    elif op=='daily':
        reward=await g().daily(user_id(c))
        await c.answer(f'+{n(reward)} 🪙!',show_alert=True)
        await show_quests(c)
    elif op=='upgrade':
        item,cost=await g().upgrade(user_id(c),int(args[2]))
        await c.answer(f'Уровень {item["level"]}; −{n(cost)} 🪙',show_alert=True)
        await show_card(c,item['id'])
    elif op=='awake':
        item,used=await g().awaken(user_id(c),int(args[2]))
        await c.answer(f'Пробуждение {item["awakening"]}!',show_alert=True)
        await show_card(c,item['id'])
    elif op=='unequip':
        await g().unequip(user_id(c),int(args[2]));await show_studio(c)
    elif op=='equip':
        await g().equip(user_id(c),int(args[2]),int(args[3]));await show_studio(c)
    else:raise GameError('Неизвестное действие.')


@router.callback_query(F.data.startswith('trade:'))
async def trade_callback(c:CallbackQuery):
    _,action,number=c.data.split(':')
    status=await g().trade_action(user_id(c),int(number),action)
    await c.answer('Новый статус: '+status,show_alert=True)
    await show_trades(c)
    # Notify both sides when the receiver accepts, or on completion.
    if status in ('accepted','completed'):
        t=await g().trade_details(user_id(c),int(number))
        target=t['sender'] if status=='accepted' else t['receiver']
        try:
            await c.bot.send_message(target,f'🤝 Обмен #{number}: {status}. Открой /trades для действий.')
        except TelegramAPIError:pass


@router.callback_query(F.data.startswith('buy:'))
async def buy_callback(c:CallbackQuery):
    lid=int(c.data.split(':')[1])
    entries=await g().market()
    offer=next((x for x in entries if x['id']==lid),None)
    if not offer:
        raise GameError('Лот больше не доступен в текущем списке.')
    card=offer['card']
    await send(c,f'🛒 <b>Подтверди покупку</b>\n\n'
                 f'{RARITY_EMOJIS[card["rarity"]]} {escape(card["name"])} '
                 f'(Lv.{card["level"]})\n'
                 f'🪙 Цена: <b>{n(offer["price"])}</b>\n\n'
                 'После оплаты отменить покупку нельзя.',
               kb([('✅ Купить',f'buyconfirm:{lid}'),('❌ Назад','nav:market')]))


@router.callback_query(F.data.startswith('buyconfirm:'))
async def buy_confirm_callback(c:CallbackQuery):
    card,tax=await g().buy(user_id(c),int(c.data.split(':')[1]))
    await c.answer('Куплено: '+card['name'],show_alert=True)
    await show_market(c)


@router.callback_query(F.data.startswith('top:'))
async def top_callback(c:CallbackQuery):await show_leaders(c,c.data.split(':')[1])


@router.callback_query(F.data.startswith('quest:'))
async def quest_callback(c:CallbackQuery):
    reward=await g().quest_reward(user_id(c),c.data.split(':')[1])
    await c.answer(f'Награда +{n(reward)} 🪙',show_alert=True)
    await show_quests(c)


@router.errors()
async def handle_error(event):
    exc=event.exception
    if isinstance(exc,GameError):
        msg='⚠️ '+str(exc)
        update=event.update
        try:
            if update.callback_query:
                await update.callback_query.answer(msg,show_alert=True)
            elif update.message:
                await update.message.answer(msg)
        except TelegramAPIError:pass
        return True
    log.exception('Unhandled update exception',exc_info=(type(exc),exc,exc.__traceback__))
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer('Внутренняя ошибка. Попробуй позже.',show_alert=True)
        elif event.update.message:
            await event.update.message.answer('Внутренняя ошибка. Попробуй позже.')
    except TelegramAPIError:pass
    return True


async def main():
    global service
    token=os.getenv('BOT_TOKEN','').strip()
    if not token:
        raise RuntimeError('Set BOT_TOKEN environment variable (from @BotFather). Never commit tokens to Git.')
    db_url=os.getenv('DATABASE_URL','sqlite+aiosqlite:///./data/empire.db')
    if db_url.startswith('postgresql://'):
        db_url='postgresql+asyncpg://'+db_url[len('postgresql://'):]
    if db_url.startswith('postgres://'):
        db_url='postgresql+asyncpg://'+db_url[len('postgres://'):]
    if db_url.startswith('sqlite'):
        Path('data').mkdir(exist_ok=True)
    # Validated catalog rejects incomplete or inconsistent photo collections.
    # Never erase all existing players when a release changes its catalog.
    photo_cards = all_cards()
    if len(photo_cards) != 9:
        raise RuntimeError(f'Expected 9 verified member photographs, got {len(photo_cards)}')
    root = Path(__file__).resolve().parent.parent
    missing = [c['id'] for c in photo_cards if not c.get('image_path')
               or not (root / c['image_path']).is_file()]
    if missing:
        raise RuntimeError('Refusing reset: incomplete card images: ' + ', '.join(missing[:5]))
    log.info('DOLCE EMPIRE running build: %s', BUILD_VERSION)
    log.info('Loaded %s same-event verified photo cards', len(photo_cards))
    engine,sf=engine_and_session(db_url)
    try:
        await init_database(engine)
        retired = await retire_unverified_cards_once(
            engine, {c['id']: c['base_income'] for c in photo_cards}
        )
        if retired:
            log.warning('Retired mixed-photo sets once (%s): player accounts and coins kept',
                        CURATION_RESET_KEY)
        else:
            log.info('Previously retired mixed-photo sets; keeping fresh progress')
        service=Game(sf)
        bot=Bot(token=token)
        dp=Dispatcher()
        dp.include_router(router)
        async with bot:
            await bot.delete_webhook(drop_pending_updates=False)
            try:
                await bot.set_my_commands([
                    BotCommand(command='start', description='✨ Главное меню'),
                    BotCommand(command='version', description='🔧 Версия сборки'),
                    BotCommand(command='roll', description='🎰 Крутить гачу'),
                    BotCommand(command='studio', description='🏢 Тайкун и сбор дохода'),
                    BotCommand(command='cards', description='🃏 Мои карточки'),
                    BotCommand(command='album', description='📚 Коллекции'),
                    BotCommand(command='spotlight', description='✨ Новые EPIC-сеты'),
                    BotCommand(command='sets', description='🌟 Листать новые сеты'),
                    BotCommand(command='market', description='🛒 Рынок'),
                    BotCommand(command='trades', description='🤝 Обмены'),
                    BotCommand(command='quests', description='🎁 Задания'),
                    BotCommand(command='help', description='❔ Список команд'),
                ])
            except TelegramAPIError:
                log.warning('Failed to register Telegram commands (will continue)')
            log.info('DOLCE EMPIRE started (%s)', 'PostgreSQL' if 'postgresql' in db_url else 'SQLite')
            await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally:
        await engine.dispose()


if __name__=='__main__':
    asyncio.run(main())
