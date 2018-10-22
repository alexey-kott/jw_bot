from typing import Union

from aiogram.types import Message, CallbackQuery
from peewee import Model, SqliteDatabase, TextField, IntegerField, CompositeKey

db = SqliteDatabase('db.sqlite3')


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


class Article(BaseModel):
    site_url = TextField(unique=True)
    telegraph_url = TextField()


class Routing(BaseModel):
    state = TextField()
    decision = TextField()  # соответствует либо атрибуту data в инлайн кнопках,
    # либо специальному значению text, которое соответствует любому текстовому сообщению
    action = TextField()

    class Meta:
        primary_key = CompositeKey('state', 'decision')
