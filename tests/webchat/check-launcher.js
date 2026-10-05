// Сценарий для task-local Playwright MCP на штатной demo.html?widgetKey=… .
// Конфигурация берётся с реального API; ответы и учётные записи не подменяются.
async (page) => {
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.reload({ waitUntil: "domcontentloaded" });
  const config = await page.evaluate(async () => {
    const key = new URLSearchParams(location.search).get("widgetKey");
    const response = await fetch("/api/v1/webchat/config/?widgetKey=" + encodeURIComponent(key) +
      "&hostOrigin=" + encodeURIComponent(location.origin));
    return response.json();
  });
  check(config.available, "The real widget must be available");
  const { launcherPosition: side, launcherSize: size, launcherShape: shape, accent, launcherIcon } = config.appearance;
  const rgb = [1, 3, 5].map(offset => parseInt(accent.slice(offset, offset + 2), 16)).join(", ");
  const fill = `rgb(${rgb.replaceAll(" ", "")})`;
  await page.waitForFunction(({ side, size }) => {
    const b = document.querySelector(".chatballs-chat-launcher");
    return b && b.style[side] === "24px" && b.offsetWidth === size;
  }, { side, size });
  const button = page.locator(".chatballs-chat-launcher");
  await page.mouse.move(640, 850);
  await page.waitForFunction(rgb => getComputedStyle(document.querySelector(".chatballs-chat-launcher"))
    .boxShadow.includes(`rgba(${rgb}, 0.35)`), rgb);
  const read = () => button.evaluate(b => ({ box: b.getBoundingClientRect().toJSON(),
    color: getComputedStyle(b).backgroundColor, radius: getComputedStyle(b).borderRadius,
    shadow: getComputedStyle(b).boxShadow, outline: getComputedStyle(b).outlineColor,
    icon: b.querySelector("img")?.src, iconWidth: b.querySelector("img")?.naturalWidth }));
  if (launcherIcon) await page.waitForFunction(() => document.querySelector(".chatballs-chat-launcher img")?.naturalWidth > 0);
  const launcher = await read();
  check(launcher.color === `rgb(${rgb})`, "Accent was not applied");
  check(launcher.box.width === size && launcher.box.height === size, "Incorrect launcher size");
  check(launcher.radius === ({ circle: "50%", rounded: "30%", square: "10px" })[shape], "Incorrect launcher shape");
  check(side === "left" ? launcher.box.left === 24 : launcher.box.right === 1256, "Incorrect launcher side");
  await page.keyboard.press("Tab");
  await button.focus();
  const focus = await read();
  check(focus.outline === `rgba(${rgb}, 0.45)`, "Focus must use accent");
  await button.hover();
  await page.waitForFunction(rgb => getComputedStyle(document.querySelector(".chatballs-chat-launcher"))
    .boxShadow.includes(`rgba(${rgb}, 0.45)`), rgb);
  const hover = await read();
  await page.mouse.move(640, 850);
  const animate = () => page.evaluate(() => new Promise(resolve => {
    document.querySelector(".chatballs-chat-launcher").click();
    const svg = document.querySelector("body > svg");
    const path = svg.querySelector("path");
    const samples = [];
    const sample = () => {
      samples.push({ fill: path.getAttribute("fill"), path: path.getAttribute("d") });
      if (svg.style.display === "none") resolve(samples);
      else requestAnimationFrame(sample);
    };
    sample();
  }));
  const opening = await animate();
  check(opening.length > 2 && opening[0].fill === fill, "Genie must start in the launcher accent");
  check(opening.every(s => !/NaN|Infinity/.test(s.path)), "Genie geometry must stay finite");
  const panel = () => page.locator("iframe").evaluate(f => f.parentElement.getBoundingClientRect().toJSON());
  const normal = await panel();
  check(normal.bottom === 900 - size - 36, "Panel must stay 12px above launcher");
  check(side === "left" ? normal.left === 24 : normal.right === 1256, "Panel must follow launcher side");
  const frame = page.frameLocator("iframe");
  await frame.getByRole("button", { name: "Развернуть окно", exact: true }).click();
  await page.waitForFunction(() => Math.abs(document.querySelector("iframe").parentElement.getBoundingClientRect().width - 820) < .1);
  const expanded = await panel();
  check(side === "left" ? expanded.left === 24 : expanded.right === 1256, "Expanded panel must keep its side");
  const closing = await animate();
  check(closing.at(-1).fill === fill, "Genie must close into the launcher accent");
  if (launcherIcon) check((await read()).iconWidth > 0, "Custom icon must return after closing");
  await page.setViewportSize({ width: 390, height: 844 });
  await animate();
  const mobile = await panel();
  check(mobile.x === 0 && mobile.y === 0 && mobile.width === 390 && mobile.height === 844, "Mobile panel must be fullscreen");
  check(await button.evaluate(b => b.style.opacity === "0" && b.style.pointerEvents === "none"), "Launcher must be hidden on mobile");
  check(await frame.getByRole("button", { name: "Развернуть окно", exact: true }).count() === 0, "Fullscreen panel cannot expand");
  await frame.getByRole("button", { name: "Свернуть", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("iframe").parentElement.style.display === "none");
  check(await button.evaluate(b => b.style.opacity === "1" && b.style.pointerEvents !== "none"), "Launcher must return after mobile close");
  return { side, size, shape, accent, launcher, focus: focus.outline, hover: hover.shadow,
    normal, expanded, mobile, genieFrames: [opening.length, closing.length], passed: true };
}
