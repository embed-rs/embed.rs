import os

from flask import Flask, render_template
from flask_mistune import Mistune
import highlight
import tflat
from tinydb import TinyDB


def site_db(path):
    return TinyDB(
        os.path.abspath(path),
        'slug',
        'content',
        storage=tflat.FlatDocumentStorage,
        read_only=True)


app = Flask(__name__)

# setup database
db = site_db(os.path.join(os.path.dirname(__file__), 'content'))

# tables
tbl_articles = db.table('articles')

# add extensions
Mistune(app, renderer=highlight.HighlightRenderer())


@app.route('/')
def hello_world():
    return render_template("base.html")


@app.route('/articles')
def list_articles():
    return render_template("articles.html", articles=tbl_articles.all())


if __name__ == '__main__':
    app.run(debug=True)
