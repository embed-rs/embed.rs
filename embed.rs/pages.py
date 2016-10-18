#!/usr/bin/env python
import os

import arrow
import click
from flask import Flask, render_template, url_for, current_app, abort
from flask_frozen import Freezer
from flask_mistune import Mistune
import highlight
import mistune
import tflat
from tinydb import TinyDB, Query
from werkzeug.contrib.atom import AtomFeed


class TinyORM(object):
    def __init__(self, db=None):
        self.bind(db)
        self.model_classes = {}

        class DBModel(object):
            _metadata = self
            _schema = {}

            @classmethod
            def search(cls, *args, **kwargs):
                return [cls.from_record(r)
                        for r in cls._metadata._get_table(cls._table).search(
                            *args, **kwargs)]

            @classmethod
            def all(cls):
                return [cls.from_record(rec)
                        for rec in cls._metadata._get_table(cls._table).all()]

            @classmethod
            def get(cls, slug):
                Q = Query()
                return cls.search(Q.slug == slug)[0]

            @classmethod
            def from_record(cls, rec):
                item = cls()
                for k, v in rec.items():
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


class Page(db.Model):
    _table = 'pages'


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

    @classmethod
    def get_or_404(cls, url_slug):
        article = cls.get(url_slug + '.md')
        if not article:
            abort(404)
        return article

    @classmethod
    def get_articles(cls, drafts=None):
        if drafts is None:
            drafts = current_app.config['SHOW_DRAFTS']

        return sorted(
            [a for a in cls.all() if drafts or a.published],
            key=lambda a: a.date,
            reverse=True)

    @property
    def published(self):
        return not getattr(self, 'draft', False)

    @property
    def url_slug(self):
        return self.slug.rstrip('.md')

    @property
    def authors(self):
        A = Query()
        return Author.search(A.slug.test(lambda x: x in self.author_ids))

    @property
    def contributors(self):
        A = Query()
        return Author.search(A.slug.test(lambda x: x in self.contributor_ids))


def site_db(path):
    return TinyDB(
        os.path.abspath(path),
        'slug',
        'content',
        storage=tflat.FlatDocumentStorage,
        read_only=True)


app = Flask(__name__)
app.config.setdefault('SHOW_DRAFTS', False)

app.jinja_env.filters['arrow'] = arrow.get

# setup database
db.bind((site_db(os.path.join(os.path.dirname(__file__), 'content'))))

# add extensions
Mistune(app, renderer=highlight.HighlightRenderer())
atom_renderer = highlight.HighlightRenderer(use_xhtml=True)
freezer = Freezer(app)


@app.route('/articles/')
@app.route('/', endpoint='index')
def list_articles():
    return render_template('articles.html', articles=Article.get_articles())


@app.route('/articles/<path:slug>/')
def show_article(slug):
    article = Article.get(slug + '.md')
    if not article.published:
        abort(404)
    return render_template('article.html', article=Article.get_or_404(slug))


@freezer.register_generator
def show_draft():
    for article in Article.get_articles(drafts=True):
        if not article.published:
            yield {'slug': article.url_slug}


@app.route('/drafts/<path:slug>/')
def show_draft(slug):
    article = Article.get(slug + '.md')

    if article.published:
        return 'already published'

    return render_template('article.html', article=Article.get_or_404(slug))


@app.route('/about/')
def about():
    return render_template('page.html', page=Page.get('about.md'))


@app.route('/atom.xml')
def atom_feed():
    # FIXME: collect site meta-data somewhere
    feed = AtomFeed('embed.rs',
                    feed_url=url_for('atom_feed', _external=True),
                    url='http://embed.rs',
                    subtitle='Rust embedded development')

    for article in Article.get_articles():
        feed.add(
            article.title,
            mistune.markdown(article.content,
                             renderer=atom_renderer),
            content_type='html',
            author=", ".join(a.full_name for a in article.authors),
            url=url_for('show_article', slug=article.url_slug),
            id='article:article.slug',
            updated=article.date,
            published=article.date)

    return feed.get_response()


cli = click.Group()


def all_files(path):
    for (dir_name, _, fns) in os.walk(path):
        for fn in fns:
            yield os.path.join(dir_name, fn)


@cli.command()
@click.option('-g', '--global', 'run_global', is_flag=True)
def run(run_global):
    path = os.path.dirname(__file__)

    content_files = list(all_files(os.path.join(path, 'content')))
    template_files = list(all_files(os.path.join(path, 'templates')))
    extra_files = content_files + template_files

    app.config['SHOW_DRAFTS'] = True

    app.run(host='0.0.0.0' if run_global else '127.0.0.1',
            debug=True,
            extra_files=extra_files, )


@cli.command()
def freeze():
    # enable below to create a zippable version
    # app.config['FREEZER_RELATIVE_URLS'] = True
    app.config['SERVER_NAME'] = 'embed.rs'
    freezer.freeze()


if __name__ == '__main__':
    cli()
