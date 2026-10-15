"""Self-contained document for an opaque-origin, scriptless sandbox iframe."""

from html import escape

CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
BASE_CSS = "html,body{margin:0;padding:0;width:100%;overflow-wrap:anywhere}*{box-sizing:border-box}"


def isolated_document(content_html, css):
    # CSS is user input: HTML raw-text end tags must never break out of style.
    css = css.replace("<", r"\3c ")
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{escape(CSP, quote=True)}">'
            '<meta name="referrer" content="no-referrer">'
            f'<style>{BASE_CSS}{css}</style></head><body>{content_html}</body></html>')
