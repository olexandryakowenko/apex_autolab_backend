import {
  esc,
  labels,
  badge,
  date,
  bytes,
  button,
  heading,
  field,
  area,
  pagination,
  empty,
  link,
  active,
  clientForm,
} from "./components.js";
export function login() {
  return `<div class="login"><div class="eyebrow">APEX AUTOLAB RECEPTION</div><h1>Робоче місце приймальника</h1><p class="muted intro">Увійдіть, щоб оформлювати автомобілі та керувати замовленнями.</p><form id="login-form" class="panel form-stack"><h2>Вхід</h2>${field("Ім’я користувача", "username", "operator", 'required maxlength="64" autocomplete="username"')}${field("Пароль", "password", "", 'required type="password" maxlength="256" autocomplete="current-password"')}<button class="primary" type="submit">Увійти</button><p class="tiny muted">Використовуйте обліковий запис, створений під час налаштування застосунку.</p></form></div>`;
}
export function orders(list, filters) {
  return (
    heading(
      "ПРИЙМАЛЬНА ЗОНА",
      "Замовлення",
      "Від першого заїзду — до завершення робіт.",
      link("+ Прийняти авто", "intake", "primary"),
    ) +
    `<form id="filter-form" class="row toolbar">${field("Пошук за номером", "q", filters.q, 'maxlength="40" placeholder="AA1234BB"')}<label>Статус<select name="status"><option value="">Усі замовлення</option>${Object.entries(
      labels,
    )
      .map(
        ([k, v]) =>
          `<option value="${k}" ${filters.status === k ? "selected" : ""}>${v}</option>`,
      )
      .join(
        "",
      )}</select></label><button type="submit">Знайти</button></form><div class="list">${list.data.length ? list.data.map((o) => `<article class="order-row"><div><span class="plate">${esc(o.plate_snapshot)}</span><div class="tiny muted">#${o.id} · ${date(o.created_at)}</div></div><div class="customer">${esc(o.client_name || (o.client_id ? "Клієнта вибрано; дані не підтверджені" : "Дані клієнта не внесені"))}<div>${badge(o.status)}</div></div>${link("Відкрити", "order/" + o.id)}</article>`).join("") : empty("Замовлень не знайдено. Змініть фільтр або прийміть перше авто.")}</div>${pagination(list)}`
  );
}
export function intake() {
  return (
    heading(
      "НОВЕ ПРИЙМАННЯ",
      "Спочатку — номер авто",
      "Перевірте номер перед створенням замовлення.",
    ) +
    `<div class="steps"><span class="active">1 · Номер авто</span><span>2 · Дані клієнта</span><span>3 · Підтвердження</span></div><div class="grid"><section class="panel"><h2>Ідентифікація автомобіля</h2><form id="intake-form" class="form-stack">${field("Державний номер", "plate", "", 'required maxlength="40" placeholder="AA1234BB" autocomplete="off"')}<label class="check"><input id="plate-confirm" type="checkbox" required><span>Я перевірив номер і підтверджую його правильність.</span></label><button class="primary" type="submit">Знайти / створити замовлення</button><p class="tiny muted">Активний наряд буде відкрито повторно. Для нового авто створиться чернетка; клієнта можна внести пізніше.</p></form></section><section class="panel"><h2>Номер із фотографії</h2><p class="muted tiny">Виберіть чітке фото лише номерного знака. Обробка відбувається локально. Автоматичного виділення номера з фото всього авто поки немає.</p><label class="file-field">Фото JPEG / PNG до 10 МБ<input id="ocr-file" type="file" accept="image/jpeg,image/png"></label><div id="ocr-preview" class="photo-zone" hidden></div>${button("Розпізнати номер", "ocr", "", 'id="ocr-button" disabled')}<p id="ocr-result" class="notice" hidden></p><p class="tiny muted intro">Якщо Tesseract недоступний або результат неточний, введіть номер вручну. Це фото не зберігається в замовленні.</p></section></div>`
  );
}
export function order({ o, v, c }) {
  const editable = ["draft", "ready"].includes(o.status),
    closed = !active(o),
    missing = o.missing_fields || [];
  const checks = [
    ["Ім’я клієнта", o.status === "draft" ? !!c?.name : !!o.client_name],
    ["Телефон", o.status === "draft" ? !!c?.phone : !!o.client_phone],
    ["Звернення", !!o.description.trim()],
  ];
  return (
    heading(
      "ЗАМОВЛЕННЯ #" + o.id,
      esc(o.plate_snapshot),
      "Картка приймання та історія обслуговування.",
      link("← До списку", "orders"),
    ) +
    `<div class="row spread detail-meta">${badge(o.status)}<span class="muted tiny wrap">${esc(o.number)} · ${date(o.created_at)}</span></div><div class="grid"><div><section class="panel"><h2>Клієнт і звернення</h2><form id="order-form" class="form-stack"><div class="row spread"><div><span class="muted tiny">Клієнт замовлення</span><p id="selected-client">${esc(c ? c.name + " · " + c.phone : "Не вибраний")}</p></div>${editable ? button("Вибрати клієнта", "choose-client") : ""}</div><input type="hidden" name="client_id" id="client_id" value="${o.client_id || ""}">${editable ? `<div class="row">${button("+ Новий клієнт", "new-client")}${button("Прибрати клієнта", "clear-client")}</div>` : ""}${area("Звернення клієнта", "description", o.description, `maxlength="2000" ${!editable ? "disabled" : ""}`)}${area("Примітки", "notes", o.notes, `maxlength="4000" ${closed ? "disabled" : ""}`)}${!closed ? '<button type="submit">Зберегти зміни</button>' : ""}<p id="dirty-hint" class="notice" hidden>Є незбережені зміни. Збережіть їх перед зміною статусу.</p></form>${o.client_name ? `<p class="tiny muted intro">Дані, зафіксовані в наряді: ${esc(o.client_name)} · ${esc(o.client_phone)}</p>` : ""}</section><section class="panel"><div class="row spread"><h2>Автомобіль</h2>${link("Картка авто", "vehicle/" + v.id)}</div><p>${esc([v.make, v.model].filter(Boolean).join(" ") || "Марка та модель ще не вказані")}</p><p class="tiny muted">VIN: ${esc(v.vin || "не вказаний")}</p><p class="tiny muted intro">Клієнт у наряді та постійний клієнт автомобіля змінюються окремо. Для наступних візитів заповніть картку авто.</p></section><section class="panel"><h2>Фотографії</h2><div class="attachments">${o.attachments.length ? o.attachments.map((a) => button("Фото #" + a.id + " · " + bytes(a.bytes), "download-photo", "", 'data-id="' + a.id + '"')).join("") : '<p class="muted">Фото ще не додані.</p>'}</div>${!closed ? `<form id="photo-form" class="form-stack intro"><label>Додати JPEG / PNG до 10 МБ<input type="file" id="attachment-file" accept="image/jpeg,image/png" required></label><label class="check"><input type="checkbox" id="attachment-confirm" required><span>Підтверджую збереження фото у замовленні.</span></label><button type="submit">Зберегти фото</button></form>` : ""}</section><section class="panel"><h2>Історія статусів</h2><ol class="history">${o.history.map((h) => `<li>${esc(labels[h.new_status] || h.new_status)} · ${date(h.created_at)}${h.reason ? `<br>${esc(h.reason)}` : ""}</li>`).join("")}</ol></section></div><section class="panel status-panel"><h2>Передача в роботу</h2><ul class="checklist">${checks.map(([label, ok]) => `<li><span class="${ok ? "pass" : "fail"}">${ok ? "✓" : "○"}</span>${label}</li>`).join("")}</ul>${o.status === "draft" ? `<p class="notice">${missing.length ? "Запуск заблокований. Заповніть відсутні дані, збережіть і підтвердьте їх." : "Перевірте збережені дані та підтвердьте готовність."}</p><label class="check"><input id="ready-confirm" type="checkbox"><span>Перевірив дані клієнта та зміст звернення.</span></label>${button("Підтвердити готовність", "ready", "primary", 'id="ready-button" disabled')}` : o.status === "ready" ? `<p class="muted intro">Обов’язкові дані підтверджені.</p>${button("Почати роботи", "in_progress", "primary", "data-transition")}` : o.status === "in_progress" ? `<p class="muted intro">Авто перебуває в роботі. Можна доповнювати примітки та фото.</p>${button("Завершити замовлення", "completed", "primary", "data-transition")}` : '<p class="notice good">Замовлення закрите. Доступний лише перегляд.</p>'}${!closed ? `<div class="intro">${button("Скасувати замовлення", "cancel", "danger", "data-transition")}</div>` : ""}</section></div>`
  );
}
export function clients(list, q) {
  return (
    heading(
      "КЛІЄНТСЬКА БАЗА",
      "Клієнти",
      "Контакти та примітки приймальника.",
      button("+ Новий клієнт", "new-client", "primary"),
    ) +
    `<form id="filter-form" class="row toolbar">${field("Пошук за ім’ям або цифрами телефона", "q", q, 'maxlength="200"')}<button type="submit">Знайти</button></form><div class="list">${list.data.length ? list.data.map((c) => `<article class="order-row"><div><h3>${esc(c.name)}</h3><p class="muted">${esc(c.phone)}</p></div><p class="customer tiny muted wrap">${esc(c.notes)}</p>${button("Редагувати", "edit-client", "", 'data-id="' + c.id + '"')}</article>`).join("") : empty("Клієнтів не знайдено.")}</div>${pagination(list)}`
  );
}
export function vehicles(list, q) {
  return (
    heading(
      "АВТОМОБІЛІ",
      "Картотека авто",
      "Номер, VIN і постійний клієнт автомобіля.",
      link("+ Прийняти авто", "intake", "primary"),
    ) +
    `<form id="filter-form" class="row toolbar">${field("Пошук за номером або VIN", "q", q, 'maxlength="200"')}<button type="submit">Знайти</button></form><div class="list">${list.data.length ? list.data.map((v) => `<article class="order-row"><div><span class="plate">${esc(v.plate)}</span><p class="tiny muted wrap">VIN: ${esc(v.vin || "не вказаний")}</p></div><p class="customer">${esc([v.make, v.model].filter(Boolean).join(" ") || "Марка та модель не вказані")}</p>${link("Відкрити", "vehicle/" + v.id)}</article>`).join("") : empty("Автомобілів не знайдено. Нові авто додаються під час приймання.")}</div>${pagination(list)}`
  );
}
export function vehicle({ v, c, history }) {
  return (
    heading(
      "КАРТКА АВТО",
      esc(v.plate),
      "Дані автомобіля для наступних візитів.",
      link("← Автомобілі", "vehicles"),
    ) +
    `<div class="grid"><section class="panel"><h2>Дані автомобіля</h2><form id="vehicle-form" class="form-stack">${field("Номер", "vehicle-plate", v.plate, 'required maxlength="40"')}<div class="fields">${field("Марка", "make", v.make, 'maxlength="100"')}${field("Модель", "model", v.model, 'maxlength="100"')}</div>${field("VIN", "vin", v.vin, 'maxlength="17"')}<div><span class="muted tiny">Постійний клієнт</span><p id="selected-client">${esc(c ? c.name + " · " + c.phone : "Не вибраний")}</p><input type="hidden" id="client_id" name="client_id" value="${v.client_id || ""}"></div><div class="row">${button("Вибрати клієнта", "choose-client")}${button("Прибрати", "clear-client")}</div><button type="submit">Зберегти автомобіль</button><p class="tiny muted">Номер не можна змінити за наявності активного наряду.</p></form></section><section class="panel"><h2>Історія замовлень</h2><div class="list">${history.data.length ? history.data.map((o) => `<div class="row spread"><span>#${o.id} · ${badge(o.status)}</span>${link("Відкрити", "order/" + o.id)}</div>`).join("") : '<p class="muted">Історія порожня.</p>'}</div>${pagination(history)}</section></div>`
  );
}
export function backups(list) {
  return (
    heading(
      "ЗБЕРЕЖЕННЯ ДАНИХ",
      "Резервні копії",
      "База клієнтів, автомобілів, замовлень і фотографії.",
      button("Створити копію", "backup", "primary"),
    ) +
    `<p class="notice">Зберігайте завантажені копії на окремому носії. Вони містять дані клієнтів. Відновлення виконується при зупиненому сервері.</p><div class="list">${list.data.length ? list.data.map((b) => `<article class="order-row"><div><h3>${date(b.created_at || b.modified_unix * 1000)}</h3><p class="tiny muted wrap">${esc(b.id)}</p></div><span>${bytes(b.bytes)}</span>${button("Завантажити", "download-backup", "", 'data-id="' + esc(b.id) + '"')}</article>`).join("") : empty("Резервних копій ще немає.")}</div>`
  );
}
export function clientDialog(c = {}) {
  return `<form id="client-form" class="form-stack"><h2 id="editor-title">${c.id ? "Редагування клієнта" : "Новий клієнт"}</h2>${clientForm(c)}<div id="dialog-error" role="alert" hidden></div><div class="row"><button type="submit" class="primary">Зберегти клієнта</button>${button("Закрити", "close-dialog")}${c.id ? button("Видалити", "delete-client", "danger") : ""}</div></form>`;
}
export function picker(list, q) {
  return `<h2 id="editor-title">Вибрати клієнта</h2><form id="picker-form" class="row toolbar">${field("Ім’я або цифри телефона", "picker-q", q, 'maxlength="200"')}<button type="submit">Знайти</button></form><div id="dialog-error" role="alert" hidden></div><div class="list">${list.data.length ? list.data.map((c) => `<div class="row spread"><div>${esc(c.name)}<br><span class="muted tiny">${esc(c.phone)}</span></div>${button("Вибрати", "pick-client", "", 'data-id="' + c.id + '"')}</div>`).join("") : empty("Нічого не знайдено.")}</div><div class="row spread intro">${button("←", "picker-prev", "", list.offset === 0 ? 'disabled aria-label="Попередні клієнти"' : 'aria-label="Попередні клієнти"')}${button("→", "picker-next", "", !list.has_more ? 'disabled aria-label="Наступні клієнти"' : 'aria-label="Наступні клієнти"')}${button("Закрити", "close-dialog")}</div>`;
}
export function cancelDialog() {
  return `<form id="cancel-form" class="form-stack"><h2 id="editor-title">Скасувати замовлення?</h2>${area("Причина", "reason", "", 'required maxlength="1000"')}<label class="check"><input type="checkbox" required><span>Підтверджую скасування. Закритий наряд не можна редагувати.</span></label><div id="dialog-error" role="alert" hidden></div><div class="row"><button type="submit" class="danger">Підтвердити скасування</button>${button("Повернутися", "close-dialog")}</div></form>`;
}
