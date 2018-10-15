from peewee import Model, SqliteDatabase, TextField, DateTimeField, IntegerField

db = SqliteDatabase('bot.db')


class Publication(Model):
    publication_type = TextField()
    publication_number = IntegerField()
    publication_year = IntegerField()
    url = TextField()
    telegraph_url = TextField()
    parsed_date = DateTimeField()
    text = TextField()

    class Meta:
        database = db
