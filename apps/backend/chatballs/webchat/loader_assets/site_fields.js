  // До загрузки скрипта сайт может объявить:
  // window.Chatballs = { q: [], setFields: function (fields) { this.q.push(fields); } };
  var fieldsApi = window.Chatballs = window.Chatballs || {};
  var queuedFields = Array.isArray(fieldsApi.q) ? fieldsApi.q.slice() : [];
  var siteFields = Object.create(null), fieldsReady = false;
  fieldsApi.q = [];

  function sendFields() {
    if (!fieldsReady || !frame || !frame.contentWindow) return;
    try {
      frame.contentWindow.postMessage({ type: "chatballs-set-fields", fields: siteFields }, origin);
    } catch (_) {} // Ошибка данных/окна не должна ломать страницу сайта.
  }

  fieldsApi.setFields = function (fields) {
    try {
      if (!fields || typeof fields !== "object" || Array.isArray(fields)) return;
      Object.keys(fields).forEach(function (key) {
        var value = fields[key];
        if (value === null || typeof value === "string" || typeof value === "boolean" ||
            (typeof value === "number" && isFinite(value))) siteFields[key] = value;
      });
      sendFields();
    } catch (_) {}
  };
  queuedFields.forEach(function (entry) {
    // Поддерживаем очередь объектов и обычный stub с q.push(["setFields", fields]).
    fieldsApi.setFields(Array.isArray(entry) && entry[0] === "setFields" ? entry[1] : entry);
  });
