# Публичный JS-лоадер виджета (SPEC-CHATBALLS-0003 §3). Подключается одним тегом:
#   <script src="https://<ваш-домен>/chat-widget.js"
#           data-widget-key="wgt_public_key" async></script>
# Лоадер рисует launcher и открывает панель в изолированном iframe (/chat/).
#
# TODO (security): для production настроить CSP `frame-ancestors` для /chat/
# (раздаётся vite/nginx, не Django — настраивается в infra/deploy), разрешив
# домены сайтов, где стоит виджет. Домены — у владельца.

LOADER_JS = r"""
(function () {
  var script = document.currentScript;
  if (!script) return;
  var widgetKey = script.getAttribute("data-widget-key") || "";
  var legacyChannel = script.getAttribute("data-channel") || "";
  if (!widgetKey && !legacyChannel) return;
  var origin = new URL(script.src, location.href).origin;
  var instanceId = "chat_" + Math.random().toString(36).slice(2);
  var entryQuery = widgetKey
    ? "widgetKey=" + encodeURIComponent(widgetKey)
    : "channel=" + encodeURIComponent(legacyChannel);
  var panelUrl = origin + "/chat/?" + entryQuery + "&instanceId=" + encodeURIComponent(instanceId);

  var open = false, frame = null, shell = null, unread = false, callActive = false, expanded = false;
  var contentTimer = 0;
  var api = window.ChatballsChat = window.ChatballsChat || {};
  window.ChatballsChat = api; // legacy alias для уже встроенных хостов

  var style = document.createElement("style");
  style.textContent = "@keyframes chatballs-chat-pop{from{opacity:0;transform:scale(.55) rotate(-25deg)}to{opacity:1;transform:none}}.chatballs-chat-launcher svg{animation:chatballs-chat-pop .24s cubic-bezier(.16,1,.3,1)}@keyframes chatballs-chat-blink{0%,92%,100%{transform:scaleY(1)}95%{transform:scaleY(.12)}}.chatballs-chat-eyes{transform-origin:24px 20px;animation:chatballs-chat-blink 4.2s infinite}@keyframes chatballs-chat-message-bump{0%,100%{transform:translateY(0)}35%{transform:translateY(-6px)}70%{transform:translateY(-2px)}}@keyframes chatballs-chat-call-shake{0%,18%,100%{transform:translateX(0)}3%{transform:translateX(-5px)}6%{transform:translateX(5px)}9%{transform:translateX(-4px)}12%{transform:translateX(4px)}15%{transform:translateX(-2px)}}.chatballs-chat-message-bump{animation:chatballs-chat-message-bump .42s ease-out}.chatballs-chat-call-shake{animation:chatballs-chat-call-shake 3.2s ease-in-out infinite}.chatballs-chat-launcher:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgba(22,119,255,0.45)}.chatballs-chat-launcher:focus-visible{outline:3px solid rgba(22,119,255,0.45);outline-offset:2px}";
  (document.head || document.documentElement).appendChild(style);

  // Launcher — круглая кнопка со знаком агента. Знак вшит как inline SVG:
  // на сайте, где стоит виджет, наших файлов нет. Пока панель открыта, кнопка
  // остаётся на месте и показывает шеврон — им же панель и закрывают.
  var BOT_ICON = '<svg viewBox="0 0 48 48" width="30" height="30" fill="#fff" style="flex:none"><mask id="chatballs-launcher-face" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48"><rect width="48" height="48" fill="#fff"/><g class="chatballs-chat-eyes"><rect x="15" y="16.4" width="4" height="7.2" rx="2" fill="#000"/><rect x="29" y="16.4" width="4" height="7.2" rx="2" fill="#000"/></g><path d="M17.6 26.4c1.7 2.4 3.9 3.6 6.4 3.6s4.7-1.2 6.4-3.6" fill="none" stroke="#000" stroke-width="2.6" stroke-linecap="round"/></mask><circle cx="24" cy="3.6" r="2.4"/><rect x="22.8" y="4.8" width="2.4" height="5"/><rect x="2.2" y="18" width="2.6" height="8.4" rx="1.3"/><rect x="43.2" y="18" width="2.6" height="8.4" rx="1.3"/><path mask="url(#chatballs-launcher-face)" d="M14 9.2h20a6.8 6.8 0 0 1 6.8 6.8v12.4a6.8 6.8 0 0 1-6.8 6.8H21.6l-6.4 5.2a.9.9 0 0 1-1.5-.7v-4.5h-.3A6.8 6.8 0 0 1 7.2 28.4V16A6.8 6.8 0 0 1 14 9.2Z"/></svg>';
  var CHEVRON_ICON = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><polyline points="6 9 12 15 18 9"/></svg>';

  var btn = document.createElement("button");
  btn.className = "chatballs-chat-launcher";
  btn.type = "button";
  btn.setAttribute("aria-label", "Открыть чат");
  btn.style.cssText = "position:fixed;right:24px;bottom:24px;width:56px;height:56px;padding:0;border:none;border-radius:50%;background:#1677ff;box-shadow:0 8px 24px rgba(22,119,255,0.35);cursor:pointer;z-index:2147483002;display:flex;align-items:center;justify-content:center;color:#fff;transition:transform .18s ease,box-shadow .18s ease,opacity .14s ease;";
  btn.innerHTML = BOT_ICON;

  var dot = document.createElement("span");
  dot.style.cssText = "position:absolute;top:-2px;right:-2px;width:12px;height:12px;border-radius:50%;background:#faad14;border:2px solid #fff;display:none;";
  btn.appendChild(dot);

  var notification = new Audio(origin + "/chat/audio/notification.mp3");
  var ringtone = new Audio(origin + "/chat/audio/ringtone.mp3");
  notification.preload = "auto";
  ringtone.preload = "auto";
  ringtone.loop = true;
  ringtone.volume = 1;

  function play(audio) {
    var result = audio.play();
    if (result && result.catch) result.catch(function () {});
  }

  function updateDot() {
    dot.style.display = !open && (unread || callActive) ? "block" : "none";
  }

  function bumpLauncher() {
    btn.classList.remove("chatballs-chat-message-bump");
    void btn.offsetWidth;
    btn.classList.add("chatballs-chat-message-bump");
    window.setTimeout(function () { btn.classList.remove("chatballs-chat-message-bump"); }, 450);
  }

  function setCallActive(active) {
    callActive = active;
    btn.classList.toggle("chatballs-chat-call-shake", active);
    if (active) play(ringtone);
    else {
      ringtone.pause();
      ringtone.currentTime = 0;
    }
    updateDot();
  }

  function ensureFrame() {
    if (frame) return;
    shell = document.createElement("div");
    shell.style.cssText = "position:fixed;right:24px;bottom:92px;width:" + PANEL_WIDTH.normal + ";height:" + PANEL_HEIGHT.normal + ";z-index:2147483001;display:none;transition:width .32s cubic-bezier(.4,0,.2,1),height .32s cubic-bezier(.4,0,.2,1);";
    frame = document.createElement("iframe");
    frame.src = panelUrl;
    frame.title = "Чат";
    frame.style.cssText = "width:100%;height:100%;border:none;border-radius:24px;box-shadow:0 12px 40px rgba(0,0,0,0.18);background:transparent;display:block;transform-origin:0 0;";
    shell.appendChild(frame);
    // Панель может открыться раньше, чем загрузится iframe — тогда сообщение
    // «открыто» (по нему виджет доскроллит ленту вниз) будет потеряно, поэтому
    // повторяем его на load.
    frame.addEventListener("load", function () { if (open) notifyOpened(); });
    document.body.appendChild(shell);
    window.addEventListener("message", function (e) {
      if (e.origin !== origin || !frame || e.source !== frame.contentWindow) return;
      var d = e.data || {};
      if (d.instanceId && d.instanceId !== instanceId) return;
      if (d.type === "chatballs-chat-close") setOpen(false);
      if (d.type === "chatballs-chat-expand") setExpanded(Boolean(d.expanded));
      if (d.type === "chatballs-chat-unread") {
        unread = Boolean(d.unread);
        updateDot();
      }
      if (d.type === "chatballs-chat-activity" && d.kind === "message") {
        unread = !open;
        updateDot();
        if (!open && !callActive) bumpLauncher();
        notification.currentTime = 0;
        play(notification);
      }
      if (d.type === "chatballs-chat-activity" && d.kind === "call") setCallActive(Boolean(d.active));
    });
  }

  // Развёрнутая панель почти вдвое шире и немного выше; переход анимируется
  // самим iframe (transition в его стилях).
  var PANEL_WIDTH = { normal: "min(440px,calc(100vw - 32px))", expanded: "min(820px,calc(100vw - 32px))" };
  var PANEL_HEIGHT = { normal: "min(720px,calc(100vh - 116px))", expanded: "min(820px,calc(100vh - 116px))" };

  function setExpanded(next) {
    expanded = next;
    if (!shell) return;
    shell.style.width = next ? PANEL_WIDTH.expanded : PANEL_WIDTH.normal;
    shell.style.height = next ? PANEL_HEIGHT.expanded : PANEL_HEIGHT.normal;
  }

  // Эффект джина: окно втягивается в кнопку, вытягивая горловину, — как в
  // доке macOS. Аффинными трансформациями такое не получить: там изгиб, а не
  // масштаб. Поэтому силуэт рисуется контуром SVG и перестраивается на каждом
  // кадре. Сам iframe в анимации не участвует — менять его размеры покадрово
  // нельзя, внутри переворачивалась бы вёрстка.
  var GENIE_OPEN_MS = 300;
  var GENIE_CLOSE_MS = 240;
  var SVG_NS = "http://www.w3.org/2000/svg";
  var genieSvg = null, geniePath = null, genieRaf = 0;

  function ensureGenie() {
    if (genieSvg) return;
    genieSvg = document.createElementNS(SVG_NS, "svg");
    genieSvg.style.cssText = "position:fixed;left:0;top:0;width:100%;height:100%;z-index:2147482999;pointer-events:none;display:none;overflow:visible;";
    geniePath = document.createElementNS(SVG_NS, "path");
    geniePath.style.filter = "drop-shadow(0 12px 40px rgba(0,0,0,0.18))";
    genieSvg.appendChild(geniePath);
    document.body.appendChild(genieSvg);
  }

  function smooth(x) {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    return x * x * (3 - 2 * x);
  }

  function mix(a, b, k) { return a + (b - a) * k; }

  function shapeAt(p, panel, icon) {
    // Низ втягивается раньше верха — из-за этого и появляется горловина.
    var pb = smooth(Math.min(1, p * 1.7));
    var pt = smooth(Math.max(0, (p - 0.3) / 0.7));

    var topY = mix(panel.top, icon.top, pt);
    var topHalf = mix(panel.half, icon.half, pt);
    var topCx = mix(panel.cx, icon.cx, pt);
    var topR = Math.min(mix(panel.radius, icon.half, pt), topHalf);

    var bottomY = mix(panel.bottom, icon.bottom, pb);
    var bottomHalf = mix(panel.half, icon.half, pb);
    var bottomCx = mix(panel.cx, icon.cx, pb);
    var bottomR = Math.min(mix(panel.radius, icon.half, pb), bottomHalf);

    return {
      topY: topY, topL: topCx - topHalf, topRt: topCx + topHalf, topR: topR,
      bottomY: bottomY, bottomL: bottomCx - bottomHalf, bottomRt: bottomCx + bottomHalf, bottomR: bottomR,
      // Плечо кривой: чем длиннее горловина, тем мягче изгиб.
      k: Math.max(0, (bottomY - topY) * 0.45),
      fill: pt
    };
  }

  function pathOf(g, dx, dy) {
    var tl = g.topL - dx, tr = g.topRt - dx, ty = g.topY - dy;
    var bl = g.bottomL - dx, br = g.bottomRt - dx, by = g.bottomY - dy;
    return "M" + (tl + g.topR) + "," + ty +
      "H" + (tr - g.topR) +
      "Q" + tr + "," + ty + " " + tr + "," + (ty + g.topR) +
      "C" + tr + "," + (ty + g.k) + " " + br + "," + (by - g.k) + " " + br + "," + (by - g.bottomR) +
      "Q" + br + "," + by + " " + (br - g.bottomR) + "," + by +
      "H" + (bl + g.bottomR) +
      "Q" + bl + "," + by + " " + bl + "," + (by - g.bottomR) +
      "C" + bl + "," + (by - g.k) + " " + tl + "," + (ty + g.k) + " " + tl + "," + (ty + g.topR) +
      "Q" + tl + "," + ty + " " + (tl + g.topR) + "," + ty + "Z";
  }

  function paintGenie(p, panel, icon) {
    var g = shapeAt(p, panel, icon);
    geniePath.setAttribute("d", pathOf(g, 0, 0));
    geniePath.setAttribute(
      "fill",
      "rgb(" + Math.round(mix(255, 22, g.fill)) + "," +
        Math.round(mix(255, 119, g.fill)) + "," +
        Math.round(mix(255, 255, g.fill)) + ")"
    );
    // Контур режет контейнер. Его собственная геометрия не меняется, поэтому
    // координаты контура честно переводятся в его систему простым сдвигом.
    var box = shell.getBoundingClientRect();
    shell.style.clipPath = "path('" + pathOf(g, box.left, box.top) + "')";

    // Окно внутри повторяет форму: ширина идёт за горловиной, высота — за
    // длиной силуэта, наклон — за уходом центра к кнопке. Содержимое из-за
    // этого сжимается и заваливается вместе с окном, а не стоит на месте.
    var width = Math.max(1, box.width);
    var height = Math.max(1, box.height);
    var sx = Math.max(0.001, (g.topRt - g.topL) / width);
    var sy = Math.max(0.001, (g.bottomY - g.topY) / height);
    var lean = ((g.bottomL + g.bottomRt) / 2 - (g.topL + g.topRt) / 2) /
      Math.max(1, g.bottomY - g.topY);
    var skew = Math.atan((sy / sx) * lean) * 180 / Math.PI;
    frame.style.transform = "translate(" + (g.topL - box.left) + "px," + (g.topY - box.top) + "px)" +
      " scale(" + sx + "," + sy + ") skewX(" + skew + "deg)";
    frame.style.borderRadius = Math.round(mix(24, icon.half, g.fill)) + "px";
  }

  function restPanel() {
    shell.style.clipPath = "none";
    frame.style.transform = "none";
    frame.style.borderRadius = "24px";
  }

  function playGenie(from, to, duration, panel, icon, done) {
    ensureGenie();
    genieSvg.style.display = "block";
    var started = 0;
    window.cancelAnimationFrame(genieRaf);
    function step(now) {
      if (!started) started = now;
      var linear = Math.min(1, (now - started) / duration);
      // Мягкий вход и выход: резкий старт читается как рывок.
      var eased = linear < 0.5 ? 2 * linear * linear : 1 - Math.pow(-2 * linear + 2, 2) / 2;
      paintGenie(mix(from, to, eased), panel, icon);
      if (linear < 1) genieRaf = window.requestAnimationFrame(step);
      else done();
    }
    genieRaf = window.requestAnimationFrame(step);
  }

  function panelRect() {
    var box = shell.getBoundingClientRect();
    return {
      top: box.top,
      bottom: box.bottom,
      cx: box.left + box.width / 2,
      half: box.width / 2,
      radius: 24
    };
  }

  function iconRect() {
    var box = btn.getBoundingClientRect();
    return {
      top: box.top,
      bottom: box.bottom,
      cx: box.left + box.width / 2,
      half: box.width / 2
    };
  }

  function notifyOpened() {
    try { frame.contentWindow.postMessage({ type: "chatballs-chat-opened" }, origin); } catch (_) {}
  }

  function setOpen(next) {
    ensureFrame();
    open = next;
    window.clearTimeout(contentTimer);
    btn.style.opacity = "0";
    btn.style.pointerEvents = "none";
    if (open) {
      // Контейнер раскладывается до расчёта: силуэт строится по настоящим
      // границам панели, а они известны только разложенной.
      shell.style.display = "block";
      paintGenie(1, panelRect(), iconRect());
      playGenie(1, 0, GENIE_OPEN_MS, panelRect(), iconRect(), function () {
        if (!open) return;
        genieSvg.style.display = "none";
        restPanel();
        btn.style.opacity = "1";
        btn.style.pointerEvents = "";
      });
    } else {
      var box = panelRect();
      playGenie(0, 1, GENIE_CLOSE_MS, box, iconRect(), function () {
        if (open) return;
        genieSvg.style.display = "none";
        shell.style.display = "none";
        restPanel();
        btn.style.opacity = "1";
        btn.style.pointerEvents = "";
      });
    }
    btn.innerHTML = open ? CHEVRON_ICON : BOT_ICON;
    btn.setAttribute("aria-label", open ? "Свернуть чат" : "Открыть чат");
    btn.appendChild(dot);
    if (open) {
      unread = false;
      updateDot();
      if (callActive) play(ringtone);
      notifyOpened();
    } else updateDot();
  }

  btn.addEventListener("click", function () { setOpen(!open); });
  function mount() {
    document.body.appendChild(btn);
    ensureFrame();
  }
  if (document.body) mount();
  else window.addEventListener("DOMContentLoaded", mount);
})();
"""
