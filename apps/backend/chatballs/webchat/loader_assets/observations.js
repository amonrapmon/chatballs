// The host owns panel and page lifecycle. Credentials stay in the iframe.
function notifyVisitor(kind) {
  if (!frame || !frame.contentWindow) return;
  frame.contentWindow.postMessage({ type: "chatballs-visitor-signal", instanceId: instanceId, kind: kind }, origin);
}
function notifyVisitorState() {
  notifyVisitor(open ? "widget_open" : "widget_close");
  notifyVisitor(document.hidden ? "page_hidden" : "page_visible");
}
document.addEventListener("visibilitychange", function () {
  notifyVisitor(document.hidden ? "page_hidden" : "page_visible");
});
document.addEventListener("freeze", function () { notifyVisitor("page_freeze"); });
document.addEventListener("resume", function () { notifyVisitor("page_resume"); notifyVisitorState(); });
window.addEventListener("pagehide", function () { notifyVisitor("page_hide"); });
window.addEventListener("pageshow", function () { notifyVisitor("page_show"); notifyVisitorState(); });
