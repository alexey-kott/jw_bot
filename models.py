from typing import Union

from aiogram.types import Message, CallbackQuery
from peewee import Model, SqliteDatabase, TextField, IntegerField, CompositeKey, CharField, ForeignKeyField, \
    BooleanField, PostgresqlDatabase
from telegraph import Telegraph

from config import TELEGRAPH_USER_TOKEN

db = SqliteDatabase('db.sqlite3')
# db = PostgresqlDatabase()


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    user_id = IntegerField(primary_key=True)
    first_name = TextField()
    last_name = TextField(default='', null=True)
    username = TextField(null=True)
    state = TextField(default='default')
    access = BooleanField(default=False)
    access_msg_id = IntegerField(null=True)

    @classmethod
    def cog(cls, data: Union[Message, CallbackQuery]) -> 'User':
        if isinstance(data, CallbackQuery) or isinstance(data, Message):
            try:
                return cls.get(user_id=data.from_user.id)
            except Exception as e:
                try:
                    return cls.create(id=data.from_user.id,
                                      username=data.from_user.username,
                                      first_name=data.from_user.first_name,
                                      last_name=data.from_user.last_name)
                except Exception as e:
                    print(e)
        else:
            raise NotImplementedError


class ACL(BaseModel):  # Access Control List
    pass


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
    journal_issue = ForeignKeyField(JournalIssue, backref='articles')
    content_hash = TextField()  # хэш от суммы компонентов статьи (иллюстрация, заголовок, текст),

    #  если он изменился -- заново экспортируем статью в telegraph

    def is_changed(self):
        return False

    def export_to_telegraph(self, content: str):
        telegraph = Telegraph(TELEGRAPH_USER_TOKEN)

        if self.is_changed():
            telegraph_response = telegraph.create_page(title=self.title, html_content=content)

        else:
            telegraph_response = telegraph.edit_page(path=self.telegraph_url, title=self.title, html_content=content)

        print(telegraph_response)

    async def foo(self, content: str):
        from aiograph import Telegraph
        telegraph = Telegraph(TELEGRAPH_USER_TOKEN)
        if self.is_changed():
            await telegraph.edit_page(path=self.telegraph_url, title=self.title, content=content)
        else:
            await telegraph.create_page(title=self.title, content=content)


class Routing(BaseModel):
    state = TextField()
    decision = TextField()  # соответствует либо атрибуту data в инлайн кнопках,
    # либо специальному значению text, которое соответствует любому текстовому сообщению
    action = TextField()

    class Meta:
        primary_key = CompositeKey('state', 'decision')
