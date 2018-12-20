import asyncio
import json
import re
from datetime import datetime
from typing import Union, Dict, Tuple

from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types.inline_keyboard import InlineKeyboardButton, InlineKeyboardMarkup
from attr import attrs

from common_functions import init_routing, parse_journal_issue
from config import BOT_TOKEN, ACCESS_CONTROL_CHANNEL_ID
from models import User, Routing, Article, Journal, JournalIssue
import string_resources as str_res
from jw_watcher import JWWatcher

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@attrs
class CallbackData:
    action: str
    params: Dict[str, Union[int, str]]


@dp.message_handler(commands=['init'])
async def init(message: Message):
    User.create_table(fail_silently=True)
    Article.create_table(fail_silently=True)
    Routing.create_table(fail_silently=True)
    Journal.create_table(fail_silently=True)
    JournalIssue.create_table(fail_silently=True)

    # set_db_init_values()


@dp.message_handler(commands=['reset'])
async def reset(message: Message):
    user = User.cog(message)
    user.state = 'default'
    user.save()


async def send_access_request(user):
    keyboard = InlineKeyboardMarkup()
    accept_access_btn = InlineKeyboardButton(text='Принять', callback_data=json.dumps({'action': 'access',
                                                                                       'user': user.user_id,
                                                                                       'access_mode': True}))
    cancel_access_btn = InlineKeyboardButton(text='Отказать', callback_data=json.dumps({'action': 'access',
                                                                                        'user': user.user_id,
                                                                                        'mode': False}))
    keyboard.row(accept_access_btn, cancel_access_btn)
    await bot.send_message(ACCESS_CONTROL_CHANNEL_ID,
                           f"{user.first_name} {user.last_name} (@{user.username})",
                           reply_markup=keyboard)


@dp.message_handler(commands=['start'])
async def start(message: Message):
    user = User.cog(message)
    await message.reply(f"Чтобы получить доступ к материалам Ваше участие должно быть одобрено администратором."
                        f"Запрос на доступ был отправлен. Бот известит Вас как только администратор даст согласие.")

    # keyboard = InlineKeyboardMarkup()
    # keyboard.add(InlineKeyboardButton(text='Библия онлайн', callback_data=json.dumps({'action': 'select_bible'})))
    # keyboard.add(InlineKeyboardButton(text='Журналы', callback_data=json.dumps({'action': 'select_journal'})))
    # keyboard.add(
    #     InlineKeyboardButton(text='Книги и брошюры', callback_data=json.dumps({'action': 'books_and_brochures'})))
    # await bot.send_message(user.user_id, "Выберите тип публикации", reply_markup=keyboard)


async def select_journal(callback: CallbackQuery):
    user = User.cog(callback)
    callback_data = {
        'action': 'select_journal_year',
    }
    keyboard = InlineKeyboardMarkup()
    callback_data['journal_name'] = 'wp'  # Сторожевая башня
    keyboard.add(InlineKeyboardButton(text='Сторожевая башня', callback_data=json.dumps(callback_data)))
    callback_data['journal_name'] = 'g'  # Пробудитесь!
    keyboard.add(InlineKeyboardButton(text='Пробудитесь!', callback_data=json.dumps(callback_data)))
    await bot.send_message(user.user_id, 'Какой журнал Вас интересует?', reply_markup=keyboard)


async def get_article(callback: CallbackQuery):
    print(callback)


async def get_journal(callback: CallbackQuery):
    data = json.loads(callback.data)
    articles = await parse_journal_issue(data['name'], data['year'])

    callback_data = {
        'action': 'get_article'
    }
    keyboard = InlineKeyboardMarkup()
    for article in articles:
        print(article[1])
        callback_data['href'] = "lolkek"
        # callback_data['href'] = article[1]
        keyboard.add(InlineKeyboardButton(text=article[0], callback_data=json.dumps(callback_data)))
    keyboard.add(InlineKeyboardButton(text='Главное меню', callback_data=json.dumps({'action': 'start'})))

    await bot.send_message(callback.from_user.id, 'Выберите статью:', reply_markup=keyboard)


async def select_journal_year(callback: CallbackQuery):
    now = datetime.now()

    data = json.loads(callback.data)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for i in range(now.year, 1999, -1):
        callback_data = {
            'action': 'get_journal',
            'name': data['journal_name'],
            'year': i,
        }
        keyboard.insert(InlineKeyboardButton(text=str(i), callback_data=json.dumps(callback_data)))
        # print(json.dumps(callback_data))
        # keyboard.insert(InlineKeyboardButton(text=str(i), callback_data=str(i)))
    await bot.send_message(callback.from_user.id, 'Выберите год:', reply_markup=keyboard)


@dp.callback_query_handler()
async def callback_handler(callback: CallbackQuery):
    print(callback.data)
    callback_data = json.loads(callback.data)
    User.cog(callback)
    await eval(callback_data['action'])(callback)
    await callback.answer(show_alert=True)


@dp.message_handler(content_types=['text'])
async def text_handler(message: Message):
    print(message)
    user = User.cog(message)

    try:
        r = Routing.get(state=user.state, decision='text')
        try:  # на случай если action не определён в таблице роутинга
            await eval(r.action)(user=user, msg=message)
        except Exception as e:
            print(e)
    except Exception as e:
        print(e)


if __name__ == '__main__':
    event_loop = asyncio.get_event_loop()
    jw_watcher = JWWatcher(loop=event_loop)
    # jw_watcher.start()
    executor.start_polling(dp)
