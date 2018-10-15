from peewee import Model, SqliteDatabase

db = SqliteDatabase('bot.db')

class Journal(Model):


    class Meta:
        database = db