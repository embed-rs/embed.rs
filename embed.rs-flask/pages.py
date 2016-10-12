import os

import arrow
from flask import Flask, render_template
from flask_mistune import Mistune
import highlight
import tflat
from tinydb import TinyDB, Query


class TinyORM(object):
    def __init__(self, db=None):
        self.bind(db)
        self.model_classes = {}

        class DBModel(object):
            _metadata = self
            _schema = {}

            @classmethod
            def search(cls, *args, **kwargs):
                return cls._metadata._get_table(cls._table).search(*args,
                                                                   **kwargs)

            @classmethod
            def all(cls):
                return [cls.from_record(rec.items())
                        for rec in cls._metadata._get_table(cls._table).all()]

            @classmethod
            def from_record(cls, rec):
                item = cls()
                for k, v in rec:
                    if k in cls._schema:
                        setattr(item, k, cls._schema[k].deserialize(v))
                    else:
                        setattr(item, k, v)
                return item

            def __str__(self):
                return '<{} {!r}>'.format(self.__class__.__name__,
                                          self.__dict__)

        self.Model = DBModel

    def bind(self, db):
        self.db = db

    def _get_table(self, name):
        return self.db.table(name)


db = TinyORM()


class AttributeField(object):
    def deserialize(self, val):
        return val

    def serialize(self, val):
        return val


class Timestamp(AttributeField):
    def deserialize(self, val):
        return arrow.get(val)


class Author(db.Model):
    _table = 'authors'

    @property
    def link(self):
        # currently, we juts return the homepage. later on, a bio page could
        # be added here
        return self.homepage


class Article(db.Model):
    _table = 'articles'
    _schema = {'date': Timestamp()}

    @property
    def authors(self):
        A = Query()
        return Author.search(A.slug == 'mbr')


def site_db(path):
    return TinyDB(
        os.path.abspath(path),
        'slug',
        'content',
        storage=tflat.FlatDocumentStorage,
        read_only=True)


app = Flask(__name__)

app.jinja_env.filters['arrow'] = arrow.get

# setup database
db.bind((site_db(os.path.join(os.path.dirname(__file__), 'content'))))

# add extensions
Mistune(app, renderer=highlight.HighlightRenderer())


@app.route('/')
def hello_world():
    return render_template("base.html")


@app.route('/articles')
def list_articles():
    return render_template("articles.html", articles=Article.all())


if __name__ == '__main__':
    app.run(debug=True)
