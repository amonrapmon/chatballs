"""Opt-in local draft only: no database writes, seeds or tool connections."""

from html import escape

from chatballs.i18n import t, tn

from .order_sources import (
    CARD_CSS,
    CARD_HTML,
    CARD_TEXT,
    COMMON_CSS,
    INSTRUCTION,
    STATUS_CSS,
    STATUS_HTML,
    STATUS_TEXT,
)

CARD_ID = "b1787429-4258-4866-8e6b-e350e0b1e55b"
STATUS_ID = "44cdfcaa-d98c-4243-835c-1f45eb455610"


def order_basis(*, language):
    def label(key):
        return t("skills.orders_" + key, language=language)

    def localized(value, *, html=False):
        for key in ("order", "total", "eta", "status"):
            replacement = label(key)
            value = value.replace("@" + key + "@", escape(replacement) if html else replacement)
        return value

    def field(kind, *, required=True, **extra):
        return {"type": kind, "required": required, **extra}

    def obj(properties):
        return field("object", properties=properties)

    # Counter value is derived by CSS from the rendered rows; no arithmetic or
    # extra facts are requested from the model. tn supplies the locale's forms.
    groups = {}
    for count in range(101):
        suffix = tn("skills.orders_item_suffix", count, language=language)
        groups.setdefault(suffix, []).append(count)
    count_css = []
    for suffix, counts in groups.items():
        selectors = [f'.items:has(.item:nth-child({count}):last-child) ~ .count::after' for count in counts if count]
        if 0 in counts:
            selectors.append(".count::after")
        count_css.append(",".join(selectors) + '{content:"' + suffix + '"}')

    schema = obj({
        "order_no": field("string"),
        "items": field("list", items=obj({
            "title": field("string"), "qty": field("number"),
            "price": field("number"), "sum": field("number"),
        })),
        "total": field("number"),
    })
    short = {"order_no": "4512", "items": [
        {"title": label("item_coat"), "qty": 1, "price": 18400, "sum": 18400},
        {"title": label("item_trousers"), "qty": 2, "price": 900, "sum": 1800},
    ], "total": 20200}
    long = {"order_no": "4598", "items": [
        {"title": label("item_suit"), "qty": 1, "price": 64000, "sum": 64000},
        {"title": label("item_shirt"), "qty": 3, "price": 4200, "sum": 12600},
        {"title": label("item_sleeves"), "qty": 1, "price": 2500, "sum": 2500},
        {"title": label("item_tie"), "qty": 2, "price": 3100, "sum": 6200},
        {"title": label("item_lining"), "qty": 1, "price": 3800, "sum": 3800},
        {"title": label("item_buttons"), "qty": 1, "price": 1600, "sum": 1600},
        {"title": label("item_cleaning"), "qty": 2, "price": 1200, "sum": 2400},
    ], "total": 93100}
    status = {"order_no": "4512", "status": label("example_status"), "eta": label("example_eta")}
    return {
        "name": label("name"), "description": label("description"), "instruction": INSTRUCTION,
        "templates": [
            {"id": CARD_ID, "name": label("card_name"), "purpose": label("card_purpose"),
             "schema": schema, "html": localized(CARD_HTML, html=True),
             "text": localized(CARD_TEXT), "css": COMMON_CSS + CARD_CSS + "\n".join(count_css),
             "examples": [short, long]},
            {"id": STATUS_ID, "name": label("status_name"), "purpose": label("status_purpose"),
             "schema": obj({"order_no": field("string"), "status": field("string"), "eta": field("string", required=False)}),
             "html": localized(STATUS_HTML, html=True), "text": localized(STATUS_TEXT),
             "css": COMMON_CSS + STATUS_CSS,
             "examples": [status, {"order_no": "4512", "status": label("example_no_eta")}]},
        ],
    }
