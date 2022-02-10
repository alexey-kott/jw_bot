import asyncio
import json
import logging

from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types.inline_keyboard import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types.reply_keyboard import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from common_functions import init_routing
from config import BOT_TOKEN, ACCESS_CONTROL_CHANNEL_ID
from models import User, Routing, Article, Journal, JournalIssue, init_db
from jw_watcher import JWWatcher
from string_resources import STRESS

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

TELEGRAPH_URL = "https://telegra.ph/"


logging.basicConfig(level=logging.ERROR,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='./logs/log')


def check_access(func, *args, **kwargs):
    print(func)

    async def wrapped():
        return await func()
    return wrapped


@dp.message_handler(commands=['ping'])
async def ping(message: Message):
    await message.reply("I'm alive!")


@dp.message_handler(commands=['init'])
async def init(message: Message):
    init_db()
    init_routing()
    await message.reply('Init successful')


@dp.message_handler(commands=['reset'])
async def reset(message: Message):
    user = User.cog(message)
    user.state = 'default'
    user.save()


async def send_access_request(user):
    keyboard = InlineKeyboardMarkup()
    accept_access_btn = InlineKeyboardButton(text='Принять',
                                             callback_data=json.dumps({'action': 'set_access',
                                                                       'user_id': user.user_id,
                                                                       'mode': True}))
    cancel_access_btn = InlineKeyboardButton(text='Отказать',
                                             callback_data=json.dumps({'action': 'set_access',
                                                                       'user_id': user.user_id,
                                                                       'mode': False}))
    keyboard.row(accept_access_btn, cancel_access_btn)

    access_request_msg = f'''
    ***User ID:*** {user.user_id}
    ***First name:*** {user.first_name}
    ***Last name:*** {user.last_name if user.last_name else '—'}
    ***Username:*** {'@'+user.username if user.username else '—'}
    '''
    msg_info = await bot.send_message(ACCESS_CONTROL_CHANNEL_ID, access_request_msg,
                                      reply_markup=keyboard, parse_mode='Markdown')

    if user.access_msg_id is not None:
        await bot.delete_message(ACCESS_CONTROL_CHANNEL_ID, user.access_msg_id)
    user.access_msg_id = msg_info['message_id']
    user.save()


@dp.message_handler(commands=['start'])
async def start(message: Message):
    user = User.cog(message)
    await message.reply(STRESS['start_message'])
    await send_access_request(user)


async def select_journal(user: User, message: Message):
    callback_data = {}
    keyboard = InlineKeyboardMarkup()
    for journal in Journal.select():
        if len(journal.issues) == 0:
            continue
        callback_data['action'] = 'select_journal_year'
        callback_data['journal_id'] = journal.id  # Сторожевая башня
        keyboard.add(InlineKeyboardButton(text=journal.title, callback_data=json.dumps(callback_data)))
    await bot.send_message(user.user_id, 'Какой журнал Вас интересует?', reply_markup=keyboard)


async def select_journal_year(user: User, data: dict):
    keyboard = InlineKeyboardMarkup(row_width=2)
    journal = Journal.get(Journal.id == data['journal_id'])
    for journal_issue in (JournalIssue.select(JournalIssue.year)
                                      .where(JournalIssue.journal == journal).distinct()
                                      .order_by(JournalIssue.year.desc())):
        callback_data = {
            'action': 'select_issue',
            'journal_id': data['journal_id'],
            'year': journal_issue.year
        }
        n = len(json.dumps(callback_data))
        keyboard.add(InlineKeyboardButton(text=journal_issue.year, callback_data=json.dumps(callback_data)))
    await bot.send_message(user.user_id, 'Выберите год:', reply_markup=keyboard)


async def select_issue(user: User, data: dict):
    keyboard = InlineKeyboardMarkup(row_width=2)
    journal = Journal.get(Journal.id == data['journal_id'])
    year = data.get('year', 2021)
    for journal_issue in JournalIssue.select().where(JournalIssue.journal == journal, JournalIssue.year == year).order_by(JournalIssue.number):
        if len(journal_issue.articles) == 0:
            continue
        callback_data = {  # max length 64 symbols
            'action': 'select_article',
            'journal_issue_id': journal_issue.id
        }
        keyboard.add(InlineKeyboardButton(text=f"№{journal_issue.number}|{journal_issue.title}",
                                          callback_data=json.dumps(callback_data)))
    await bot.send_message(user.user_id, 'Выберите номер журнала:', reply_markup=keyboard)


async def select_article(user: User, data: dict):
    keyboard = InlineKeyboardMarkup(row_width=2)
    journal_issue = JournalIssue.get(JournalIssue.id == data['journal_issue_id'])
    for article in Article.select().where(Article.journal_issue == journal_issue):
        callback_data = {
            'action': 'send_article',
            'article_id': article.id
        }
        keyboard.add(InlineKeyboardButton(text=article.title, callback_data=json.dumps(callback_data)))
    await bot.send_message(user.user_id,
                           f'***{journal_issue.title}*** \n\n {journal_issue.annotation}\n\n'
                           f'Выберите статью:',
                           reply_markup=keyboard, parse_mode='Markdown')


async def send_article(user: User, data: dict):
    article = Article.get(Article.id == data['article_id'])
    await bot.send_message(user.user_id, f"{TELEGRAPH_URL}{article.telegraph_path}")


async def set_access(user: User, data: dict):
    bot_user = User.get(User.user_id == data['user_id'])
    bot_user.access = data['mode']

    keyboard = InlineKeyboardMarkup()
    callback_data = {
        'action': 'set_access',
        'user_id': bot_user.user_id,
        'mode': not bot_user.access
    }
    if bot_user.access:
        btn_text = STRESS['access_granted_btn']
        msg_text = STRESS['access_granted_msg']
    else:
        btn_text = STRESS['access_denied_btn']
        msg_text = STRESS['access_denied_msg']
    keyboard.insert(InlineKeyboardButton(text=btn_text, callback_data=json.dumps(callback_data)))
    await bot.edit_message_reply_markup(ACCESS_CONTROL_CHANNEL_ID, bot_user.access_msg_id,
                                        reply_markup=keyboard)

    if bot_user.access:
        bot_user.state = 'default'
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        keyboard.add(KeyboardButton('Главное меню'))
    else:
        keyboard = ReplyKeyboardRemove()
    bot_user.save()
    await bot.send_message(bot_user.user_id, msg_text, reply_markup=keyboard)


@dp.callback_query_handler()
async def callback_handler(callback: CallbackQuery):
    print(callback.data)
    callback_data = json.loads(callback.data)
    user = User.cog(callback)
    await callback.answer(show_alert=True)
    await eval(callback_data['action'])(user, callback_data)


@dp.message_handler(content_types=['text'])
async def text_handler(message: Message):
    print(message)
    user = User.cog(message)
    if not user.access:
        await message.reply('У вас нет доступа к контенту')
        return

    try:
        r = Routing.get(state=user.state, decision='text')
        try:  # на случай если action не определён в таблице роутинга
            await eval(r.action)(user=user, message=message)
        except Exception as e:
            print(e)
    except Exception as e:
        print(e)


if __name__ == '__main__':
    logger = logging.getLogger('jw_bot')
    logger.setLevel(logging.INFO)

    event_loop = asyncio.get_event_loop()
    jw_watcher = JWWatcher(watcher_loop=event_loop, watcher_logger=logger)
    jw_watcher.start()
    executor.start_polling(dp)
