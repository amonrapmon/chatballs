"""Editable sources reproducing the approved order/status cards, not UI code."""

CARD_HTML = """<div class="card order-card">
<strong class="heading">@order@ {{ order_no }}</strong>
<div class="items">{{#each items}}<div class="item"><span class="details"><span class="title">{{ title }}</span><small class="price">{{ qty }} × {{ price }} ₽</small></span><span class="sum">{{ sum }} ₽</span></div>{{/each}}</div>
<small class="count"></small>
<div class="total"><span>@total@</span><b>{{ total }} ₽</b></div></div>"""
CARD_TEXT = """@order@ {{ order_no }}
{{#each items}}{{ title }} — {{ qty }} × {{ price }} ₽ = {{ sum }} ₽
{{/each}}@total@: {{ total }} ₽"""
STATUS_HTML = """<div class="card"><small class="order-no">@order@ {{ order_no }}</small>
<span class="status"><i class="dot"></i>{{ status }}</span>
{{#if eta}}<div class="eta"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 6v6l4 2"></path></svg><span>@eta@: <b>{{ eta }}</b></span></div>{{/if}}</div>"""
STATUS_TEXT = """@order@ {{ order_no }}
@status@: {{ status }}{{#if eta}}
@eta@: {{ eta }}{{/if}}"""
COMMON_CSS = """
.card{width:100%;background:#fff;border:1px solid #eee;border-radius:4px 14px 14px 14px;padding:12px 13px;color:#262626;font-family:system-ui,sans-serif}
"""
CARD_CSS = """
.order-card{display:flex;flex-wrap:wrap;counter-reset:items;gap:0 8px}
.heading{font-size:13.5px;flex:1;order:0;overflow-wrap:anywhere;min-width:0}
.count{font-size:11px;color:#8c8c8c;white-space:nowrap;order:1}
.count::before{content:counter(items)}
.items{margin-top:8px;display:flex;flex-direction:column;width:100%;order:2}
.item{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:7px 0;border-top:1px solid #f0f0f0;counter-increment:items}
.details{min-width:0}
.title{display:block;font-size:12.5px;line-height:1.4;overflow-wrap:anywhere}
.price{display:block;margin-top:1px;font-size:11.5px;color:#8c8c8c}
.sum{font-size:12.5px;font-weight:600;white-space:nowrap}
.total{display:flex;justify-content:space-between;gap:10px;padding-top:9px;border-top:1px solid #e8e8e8;font-size:13.5px;width:100%;order:3}
.total b{white-space:nowrap}
"""
STATUS_CSS = """
.order-no{display:block;font-size:11.5px;color:#8c8c8c;overflow-wrap:anywhere}
.status{display:inline-flex;align-items:center;gap:6px;margin-top:6px;padding:4px 10px;border-radius:12px;background:#e6f4f2;color:#0f766e;font-size:13px;font-weight:600;overflow-wrap:anywhere;max-width:100%}
.dot{width:7px;height:7px;flex:none;border-radius:50%;background:currentColor}
.eta{display:flex;align-items:center;gap:6px;margin-top:9px;padding-top:9px;border-top:1px solid #f0f0f0;font-size:12.5px;color:#595959}
.eta svg{flex:none}
.eta b{color:#262626}
"""

INSTRUCTION = """Help customers read their orders, never change or cancel them.
Use only tools already enabled for this agent. Choose a read-only HTTP/MCP tool
by its description and input/output schema, not by an invented operation name.
Ask for the missing order number before searching. A number from website data
does not authorize access: the external system must verify that this customer
owns the order using the available authenticated context. Never bypass that
check or disclose an order without it. Do not infer ownership from the number.
For contents and totals, choose the order card; for progress or ETA, choose the
status template. Load the skill and use the actual template IDs/schema supplied
by the server. Pass only trustworthy tool values. Do not invent products,
prices, quantities, sums, totals, statuses or dates, and do not calculate missing
commercial amounts. The supplied card labels money in RUB: use it ONLY when
the trusted source explicitly confirms currency RUB. For another or unknown
currency, give a faithful text answer with the source currency if known, or
hand over; an administrator can edit the template for other currencies.
If ETA is missing, omit eta; never fill it with a guess, dash or placeholder.
Examples are design-only editor data. Never use them as live answers and never
query a demonstration service. If a suitable tool is unavailable, fails, denies
access or lacks required trustworthy data, ask a useful clarification or hand
the conversation to a human using the existing handover mechanism. Requests
to edit/cancel an order must be handed to a human. Do not enable tools, attach
integrations, modify orders or invent a successful result yourself."""
