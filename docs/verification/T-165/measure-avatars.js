async (page) => {
  // Run with the assignee menu and participant form open in the real app.
  // Probe text geometry only; restore DOM nodes immediately, without API writes.
  return page.evaluate(() => {
    const results = [];
    for (const selector of [
      ".ctx-select .ctx-avatar-small",
      ".app-dropdown:not(.ant-dropdown-hidden) .ctx-avatar-small",
      ".participant-option .ctx-avatar-small",
    ]) {
      const avatar = document.querySelector(selector);
      if (!avatar) throw new Error(`Missing avatar: ${selector}`);
      const original = Array.from(avatar.childNodes);
      const dot = avatar.querySelector(".presence-dot");
      try {
        for (const initials of ["И", "ИС"]) {
          const text = document.createTextNode(initials);
          avatar.replaceChildren(...(dot ? [dot] : []), text);
          const range = document.createRange();
          range.selectNode(text);
          const a = avatar.getBoundingClientRect();
          const r = range.getBoundingClientRect();
          const dx = r.x + r.width / 2 - a.x - a.width / 2;
          const dy = r.y + r.height / 2 - a.y - a.height / 2;
          results.push({ selector, initials, width: a.width, height: a.height, dx, dy });
          if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) throw new Error(`Uncentered ${selector}: ${dx}, ${dy}`);
        }
      } finally {
        avatar.replaceChildren(...original);
      }
    }
    return results;
  });
}
