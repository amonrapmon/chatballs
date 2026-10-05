// Проверяем сетевой отказ, не подменяя API вымышленным ответом.
async (page) => {
  const errors = [];
  const onError = error => errors.push(error.message);
  const endpoint = "**/api/v1/webchat/config/**";
  await page.setViewportSize({ width: 1280, height: 900 });
  page.on("pageerror", onError);
  await page.route(endpoint, route => route.abort("failed"));
  try {
    const failed = page.waitForEvent("requestfailed", { predicate: request => request.url().includes("/webchat/config/") });
    await page.reload({ waitUntil: "domcontentloaded" });
    await failed;
    const button = page.locator(".chatballs-chat-launcher");
    const defaults = await button.evaluate(b => ({ color: getComputedStyle(b).backgroundColor,
      width: b.offsetWidth, radius: b.style.borderRadius, side: b.style.right, standardIcon: !!b.querySelector("svg") }));
    if (defaults.color !== "rgb(22, 119, 255)" || defaults.width !== 56 || defaults.radius !== "50%" ||
        defaults.side !== "24px" || !defaults.standardIcon) throw new Error("Default launcher was lost");
    await button.click();
    await page.waitForFunction(() => document.querySelector("iframe").parentElement.style.clipPath === "none");
    await button.click();
    await page.waitForFunction(() => document.querySelector("iframe").parentElement.style.display === "none");
    if (errors.length) throw new Error(errors.join("; "));
    if (!await page.getByRole("heading").isVisible()) throw new Error("Host page was affected");
    return { defaults, pageErrors: errors, openCloseWorks: true, passed: true };
  } finally {
    await page.unroute(endpoint);
    page.off("pageerror", onError);
  }
}
