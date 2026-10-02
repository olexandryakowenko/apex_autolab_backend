/** Real browser + real temporary Flask/SQLite/Waitress. No mock business data. */
const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const root = path.resolve(__dirname, ".."),
  data = fs.mkdtempSync(path.join(os.tmpdir(), "apex-frontend-"));
const python =
  process.env.APEX_PYTHON ||
  path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
const server = spawn(
  python,
  [path.join(__dirname, "frontend_fixture.py"), data],
  { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
);
const output =
  process.env.APEX_E2E_ARTIFACTS || path.join(root, "frontend-test-results");
fs.mkdirSync(output, { recursive: true });
const checks = [];
let browser,
  logs = "";
server.stderr.on("data", (x) => (logs += x));
const ready = new Promise((resolve, reject) => {
  const timer = setTimeout(
    () => reject(new Error("Server startup timeout: " + logs)),
    30000,
  );
  let buf = "";
  server.stdout.on("data", (x) => {
    buf += x;
    const m = buf.match(/READY (\d+)/);
    if (m) {
      clearTimeout(timer);
      resolve(Number(m[1]));
    }
  });
  server.on("error", (e) => {
    clearTimeout(timer);
    reject(e);
  });
  server.on("exit", (code) => {
    clearTimeout(timer);
    if (!buf.includes("READY"))
      reject(new Error("Server exit " + code + ": " + logs));
  });
});
(async () => {
  const port = await ready,
    launch = { headless: true };
  if (process.env.APEX_BROWSER_EXECUTABLE) {
    launch.executablePath = process.env.APEX_BROWSER_EXECUTABLE;
    launch.args = [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--no-zygote",
      "--single-process",
    ];
  }
  browser = await chromium.launch(launch);
  const page = await browser.newPage({
      viewport: { width: 1200, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const base = "http://127.0.0.1:" + port;
  const idle = () => page.locator("#busy").waitFor({ state: "hidden" });
  const act = (a) => page.locator(`[data-action="${a}"]`);
  const nav = async (n) => {
    await page.locator(`[data-nav="${n}"]`).click();
    await idle();
  };
  const shot = (name) =>
    page.screenshot({ path: path.join(output, name + ".png"), fullPage: true });
  const submit = async (id) => {
    await page.locator("#" + id + " button[type=submit]").click();
    await idle();
  };
  await page.goto(base);
  await idle();
  assert(await page.locator("#login-form").isVisible());
  await shot("01-login");
  await page.locator("#password").fill("incorrect-password");
  await submit("login-form");
  assert.match(await page.locator("#error").innerText(), /Невірне/);
  checks.push("401: помилка входу показана користувачеві");
  await page.locator("#password").fill("Frontend-test-2026!");
  await submit("login-form");
  assert.match(await page.locator("main").innerText(), /Замовлень не знайдено/);
  checks.push("Вхід та порожній список із реальної БД");
  await page.locator("#apex-theme").selectOption("light");
  await page.reload();
  await idle();
  assert.equal(await page.locator("#apex-theme").inputValue(), "light");
  await page.locator("#apex-theme").selectOption("dark");
  checks.push("Тема та сесія зберігаються після перезавантаження");
  await nav("intake");
  await page.locator("#plate").fill("АА 1234 ВВ");
  await page.locator("#plate-confirm").check();
  await submit("intake-form");
  assert(await act("ready").isDisabled());
  checks.push("Створення чернетки, нормалізація номера, блокування готовності");
  await act("new-client").click();
  await idle();
  await page.locator("#editor #name").fill("Тестовий клієнт");
  await page.locator("#editor #phone").fill("123");
  await submit("client-form");
  assert.match(await page.locator("#dialog-error").innerText(), /7–15/);
  assert.equal(
    await page.locator("#editor #name").inputValue(),
    "Тестовий клієнт",
  );
  checks.push("422: помилка валідації без втрати введених даних");
  await page.locator("#editor #phone").fill("+380 (00) 000-00-01");
  await submit("client-form");
  await page.locator("#description").fill("Діагностика підвіски");
  await submit("order-form");
  await page.locator("#ready-confirm").check();
  await act("ready").click();
  await idle();
  assert(await act("in_progress").isEnabled());
  checks.push("Створення клієнта, PATCH наряду, підтвердження готовності");
  await shot("02-ready");
  let csrfFailures = 0;
  await page.route("**/api/orders/1", async (route) => {
    if (route.request().method() === "PATCH" && csrfFailures++ === 0)
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "csrf_failed",
            message: "Відсутній або недійсний CSRF-токен.",
          },
        }),
      });
    else await route.continue();
  });
  await page.locator("#notes").fill("Зателефонувати після діагностики");
  await submit("order-form");
  assert(await act("in_progress").isEnabled());
  assert.equal(csrfFailures, 2);
  await page.unroute("**/api/orders/1");
  checks.push(
    "Оновлення CSRF після явної відмови та збереження лише приміток без скидання ready",
  );
  await page.locator("#description").fill("Діагностика підвіски та гальм");
  assert(await act("in_progress").isDisabled());
  await submit("order-form");
  assert(await act("ready").isDisabled());
  checks.push(
    "Незбережені зміни блокують запуск; зміна звернення повертає draft",
  );
  await page
    .locator("#attachment-file")
    .setInputFiles(path.join(data, "plate.png"));
  await page.locator("#attachment-confirm").check();
  await submit("photo-form");
  assert(await act("download-photo").isVisible());
  const photoDownload = page.waitForEvent("download");
  await act("download-photo").click();
  await photoDownload;
  await idle();
  checks.push("Завантаження та отримання справжнього фото через API");
  await page.locator("#ready-confirm").check();
  await act("ready").click();
  await idle();
  await act("in_progress").click();
  await idle();
  assert(await page.locator("#description").isDisabled());
  checks.push("Запуск робіт та незмінність підтверджених полів");
  await nav("intake");
  await page.locator("#plate").fill("AA1234BB");
  await page.locator("#plate-confirm").check();
  await submit("intake-form");
  assert.match(await page.locator("#message").innerText(), /Дублікат/);
  checks.push("Повторне приймання відкриває той самий активний наряд");
  page.once("dialog", (d) => d.accept());
  await act("completed").click();
  await idle();
  assert.equal(
    await page.locator("#order-form button[type=submit]").count(),
    0,
  );
  checks.push("Завершення та блокування редагування");
  await page.locator('a[href="#vehicle/1"]').click();
  await idle();
  await act("choose-client").click();
  await idle();
  await act("pick-client").click();
  await idle();
  await page.locator("#make").fill("Volkswagen");
  await page.locator("#model").fill("Golf");
  await submit("vehicle-form");
  checks.push("Картка авто: марка, модель та постійний клієнт");
  await nav("intake");
  await page.locator("#plate").fill("AA1234BB");
  await page.locator("#plate-confirm").check();
  await submit("intake-form");
  assert.match(
    await page.locator("#selected-client").innerText(),
    /Тестовий клієнт/,
  );
  checks.push("Новий візит після завершення успадковує клієнта автомобіля");
  await act("cancel").click();
  await idle();
  await page.locator("#reason").fill("Перенесення візиту");
  await page.locator("#cancel-form input[type=checkbox]").check();
  await submit("cancel-form");
  assert.match(await page.locator("main").innerText(), /Скасовано/);
  checks.push("Скасування з причиною та підтвердженням");
  await nav("clients");
  await act("edit-client").click();
  await idle();
  page.once("dialog", (d) => d.accept());
  await act("delete-client").click();
  await idle();
  assert.match(await page.locator("#dialog-error").innerText(), /пов’язані/);
  await act("close-dialog").click();
  checks.push("409: захист клієнта з пов’язаними записами");
  await nav("backups");
  await act("backup").click();
  await idle();
  assert(await act("download-backup").isVisible());
  const backupDownload = page.waitForEvent("download");
  await act("download-backup").click();
  await backupDownload;
  await idle();
  checks.push("Створення та завантаження резервної копії");
  await nav("intake");
  await page.locator("#ocr-file").setInputFiles(path.join(data, "plate.png"));
  await act("ocr").click();
  await idle();
  if (await page.locator("#ocr-result").isVisible()) {
    assert(!(await page.locator("#plate-confirm").isChecked()));
    checks.push("Справжній OCR-виклик; результат вимагає підтвердження");
  } else {
    assert.match(
      await page.locator("#error").innerText(),
      /Tesseract|OCR|номер/,
    );
    checks.push("OCR недоступний: показано помилку, ручне поле доступне");
  }
  await shot("03-intake");
  await page.route("**/api/ocr", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "ocr_unavailable",
          message: "Tesseract не встановлено. Введіть номер вручну.",
        },
      }),
    }),
  );
  await act("ocr").click();
  await idle();
  assert.match(
    await page.locator("#error").innerText(),
    /Введіть номер вручну/,
  );
  assert(await page.locator("#plate").isEnabled());
  await page.unroute("**/api/ocr");
  checks.push("503: контрольована відмова OCR з ручним введенням");
  await nav("orders");
  await shot("04-orders");
  let release;
  const gate = new Promise((resolve) => (release = resolve));
  await page.route("**/api/orders?**", async (route) => {
    await gate;
    await route.continue();
  });
  await page.locator("#filter-form button").click();
  await page.locator("#busy").waitFor({ state: "visible" });
  assert(await page.locator("#logout").isDisabled());
  release();
  await idle();
  await page.unroute("**/api/orders?**");
  checks.push(
    "Повільний запит: видимий стан завантаження, повторні дії заблоковано",
  );
  await page.route("**/api/orders?**", (r) => r.abort());
  await page.locator("#q").fill("ZZ999");
  await submit("filter-form");
  assert.match(await page.locator("#error").innerText(), /зв’язку/);
  await page.unroute("**/api/orders?**");
  await act("retry").click();
  await idle();
  assert.match(await page.locator("main").innerText(), /не знайдено/);
  checks.push("Мережева помилка, повторення GET та порожній результат");
  for (const width of [1200, 736, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ["light", "dark"]) {
      await page.locator("#apex-theme").selectOption(theme);
      for (const route of [
        "orders",
        "clients",
        "vehicles",
        "backups",
        "intake",
      ]) {
        await nav(route);
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          `Overflow ${width}/${theme}/${route}`,
        );
      }
    }
    if (width === 390) await shot("05-mobile");
  }
  checks.push("Адаптивність на 1200/736/390/320 px у світлій та темній темі");
  await page.setViewportSize({ width: 320, height: 1000 });
  await nav("orders");
  await page.locator('a[href="#order/1"]').click();
  await idle();
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await shot("07-mobile-detail");
  checks.push("Детальна картка наряду без переповнення на 320 px");
  await page.setViewportSize({ width: 1200, height: 1000 });
  await page.locator("#apex-theme").selectOption("light");
  await nav("orders");
  await shot("06-light");
  // CSRF renewal uses an explicit rejected mutation; it never repeats an uncertain write.
  await page.context().clearCookies();
  await page.locator("#logout").click();
  await idle();
  assert(await page.locator("#login-form").isVisible());
  checks.push("Завершення сесії повертає на вхід");
  assert.deepEqual(errors, []);
  checks.push("Немає помилок JavaScript");
  const result = { passed: checks.length, checks, platform: process.platform };
  fs.writeFileSync(
    path.join(output, "results.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
})()
  .catch((e) => {
    console.error(e, logs);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    server.kill();
    await new Promise((resolve) => {
      if (server.exitCode !== null) resolve();
      else server.once("exit", resolve);
    });
    fs.rmSync(data, { recursive: true, force: true });
  });
