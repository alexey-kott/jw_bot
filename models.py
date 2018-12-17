from enum import Enum
from typing import Union

from aiogram.types import Message, CallbackQuery
from peewee import Model, SqliteDatabase, TextField, IntegerField, CompositeKey, DateField, CharField, ForeignKeyField

db = SqliteDatabase('db.sqlite3')


# class Journal(Enum):
#     # такие обозначения используются на сайте
#     AWAKE = 'g'  # Awake! (Пробудитесь!)
#     WATCHTOWER = 'wp'  # Watchtower (Сторожевая башня)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    user_id = IntegerField(primary_key=True)
    first_name = TextField()
    last_name = TextField(null=True)
    username = TextField(null=True)
    state = TextField(default='default')

    @classmethod
    def cog(cls, data: Union[Message, CallbackQuery]) -> 'User':
        if isinstance(data, CallbackQuery) or isinstance(data, Message):
            try:
                return cls.get(user_id=data.from_user.id)
            except Exception as e:
                return cls.create(user_id=data.from_user.id,
                                  username=data.from_user.username,
                                  first_name=data.from_user.first_name,
                                  last_name=data.from_user.last_name)
        else:
            raise NotImplementedError


class Journal(BaseModel):
    symbol = CharField(max_length=2, unique=True)
    title = TextField()
    priority = IntegerField()


class JournalIssue(BaseModel):
    #  журнальный выпуск
    journal = ForeignKeyField(Journal, backref='issues')
    year = IntegerField()
    number = IntegerField()
    title = TextField()
    annotation = TextField()
    link = TextField(unique=True)


class Article(BaseModel):
    title = TextField(unique=True)
    url = TextField(unique=True)
    telegraph_url = TextField()
    journal_issue = ForeignKeyField(JournalIssue, backref='articles', null=True)
    content_hash = TextField()  # хэш от суммы компонентов статьи (иллюстрация, заголовок, текст),
                        #  если он изменился -- заново экспортируем статью в telegraph


class Routing(BaseModel):
    state = TextField()
    decision = TextField()  # соответствует либо атрибуту data в инлайн кнопках,
    # либо специальному значению text, которое соответствует любому текстовому сообщению
    action = TextField()

    class Meta:
        primary_key = CompositeKey('state', 'decision')
