from flask import url_for
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter


class AssetMixin(object):
    def image(self, src, title, alt_text):
        src = url_for('static', filename='content/' + src, _external=True)
        return super(AssetMixin, self).image(src, title, alt_text)


class HighlightMixin(object):
    def block_code(self, code, lang):
        if not lang:
            return '\n<pre><code>%s</code></pre>\n' % \
                mistune.escape(code)
        lexer = get_lexer_by_name(lang, stripall=True)
        formatter = HtmlFormatter()
        return highlight(code, lexer, formatter)


class HighlightRenderer(HighlightMixin, AssetMixin, mistune.Renderer, ):
    pass
