import { request, params, download, clearToken, ApiError } from "./api.js";
import { esc, normalize, active, button } from "./components.js";
import * as view from "./views.js";

const main = document.getElementById("main"),
  dialog = document.getElementById("editor");
const navigation = document.getElementById("navigation"),
  message = document.getElementById("message"),
  errorBox = document.getElementById("error");
const state = {
  user: null,
  route: "orders",
  busy: false,
  dirty: false,
  model: null,
  list: null,
  offset: 0,
  filters: { q: "", status: "" },
  picker: { q: "", offset: 0, list: null },
  client: null,
  photo: null,
  preview: null,
  sequence: 0,
};
const fieldNames = {
  client_id: "клієнт",
  client_name: "ім’я клієнта",
  client_phone: "телефон",
  description: "звернення",
};
function clearMessages() {
  message.hidden = true;
  errorBox.hidden = true;
  message.textContent = "";
  errorBox.textContent = "";
}
function tell(text) {
  message.textContent = text;
  message.hidden = false;
}
function showError(error) {
  const text =
    (error.message || "Не вдалося виконати операцію.") +
    (Array.isArray(error.details)
      ? " Перевірте: " + error.details.map((k) => fieldNames[k] || k).join(", ")
      : "");
  const box = dialog.open ? dialog.querySelector("#dialog-error") : errorBox;
  if (box) {
    box.textContent = text;
    box.hidden = false;
    box.classList.add("notice");
  }
  if (error.code === "network")
    document.getElementById("connection").textContent =
      "Зв’язок із сервером відсутній або перерваний";
}
async function task(fn, label = "Завантаження…") {
  if (state.busy) return;
  state.busy = true;
  clearMessages();
  const busy = document.getElementById("busy");
  busy.textContent = label;
  busy.hidden = false;
  main.setAttribute("aria-busy", "true");
  const controls = [
    ...document.querySelectorAll("button,input,textarea,select"),
  ].filter((el) => el.id !== "apex-theme");
  const previous = controls.map((el) => [el, el.disabled]);
  controls.forEach((el) => (el.disabled = true));
  try {
    await fn();
    if (state.user)
      document.getElementById("connection").textContent =
        "Локальний сервер · підключено";
  } catch (error) {
    showError(error);
  } finally {
    previous.forEach(([el, disabled]) => {
      if (el.isConnected) el.disabled = disabled;
    });
    state.busy = false;
    busy.hidden = true;
    main.setAttribute("aria-busy", "false");
    syncReady();
  }
}
function uiSession() {
  navigation.hidden = !state.user;
  document.getElementById("operator-name").textContent =
    state.user?.username || "";
}
function showLogin() {
  state.sequence++;
  state.user = null;
  state.dirty = false;
  clearToken();
  releasePhoto();
  if (dialog.open) dialog.close();
  uiSession();
  main.innerHTML = view.login();
  document.getElementById("connection").textContent = "Потрібно увійти";
}
window.addEventListener("apex:session-ended", () => {
  showLogin();
  tell(
    "Сесія завершилася. Увійдіть повторно; незбережені дані не було надіслано повторно.",
  );
});
function markDirty() {
  state.dirty = true;
  const hint = document.getElementById("dirty-hint");
  if (hint) hint.hidden = false;
  const c = document.getElementById("ready-confirm");
  if (c) c.checked = false;
  syncReady();
}
function syncReady() {
  const ready = document.getElementById("ready-button");
  if (ready)
    ready.disabled =
      state.busy ||
      state.dirty ||
      !document.getElementById("ready-confirm")?.checked ||
      !!state.model?.o?.missing_fields.length;
  main
    .querySelectorAll("[data-transition]")
    .forEach((el) => (el.disabled = state.busy || state.dirty));
}
function releasePhoto() {
  if (state.preview) URL.revokeObjectURL(state.preview);
  state.preview = null;
  state.photo = null;
}
async function loadRoute(route = state.route) {
  const seq = ++state.sequence;
  state.route = route;
  state.dirty = false;
  state.model = null;
  releasePhoto();
  if (!state.user) {
    main.innerHTML = view.login();
    return;
  }
  navigation.querySelectorAll("[data-nav]").forEach((a) => {
    const type = route.split("/")[0];
    if (
      a.dataset.nav === ({ order: "orders", vehicle: "vehicles" }[type] || type)
    )
      a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  main.innerHTML = '<p class="empty">Завантаження даних…</p>';
  let html = "",
    model = null,
    list = null;
  try {
    if (route === "orders") {
      list = await request(
        "/api/orders?" +
          params({ ...state.filters, limit: 20, offset: state.offset }),
      );
      html = view.orders(list, state.filters);
    } else if (route === "intake") html = view.intake();
    else if (route === "clients") {
      list = await request(
        "/api/clients?" +
          params({ q: state.filters.q, limit: 20, offset: state.offset }),
      );
      html = view.clients(list, state.filters.q);
    } else if (route === "vehicles") {
      list = await request(
        "/api/vehicles?" +
          params({ q: state.filters.q, limit: 20, offset: state.offset }),
      );
      html = view.vehicles(list, state.filters.q);
    } else if (/^order\/\d+$/.test(route)) {
      const o = (await request("/api/orders/" + route.split("/")[1])).data;
      const [vr, cr] = await Promise.all([
        request("/api/vehicles/" + o.vehicle_id),
        o.client_id
          ? request("/api/clients/" + o.client_id)
          : Promise.resolve({ data: null }),
      ]);
      model = { o, v: vr.data, c: cr.data };
      html = view.order(model);
    } else if (/^vehicle\/\d+$/.test(route)) {
      const v = (await request("/api/vehicles/" + route.split("/")[1])).data;
      const [cr, hr] = await Promise.all([
        v.client_id
          ? request("/api/clients/" + v.client_id)
          : Promise.resolve({ data: null }),
        request(
          "/api/vehicles/" +
            v.id +
            "/orders?" +
            params({ limit: 20, offset: state.offset }),
        ),
      ]);
      model = { v, c: cr.data, history: hr };
      list = hr;
      html = view.vehicle(model);
    } else if (route === "backups") {
      list = await request("/api/backups");
      html = view.backups(list);
    } else throw new ApiError("Сторінку не знайдено.", 404, "not_found");
    if (seq !== state.sequence || !state.user) return;
    state.model = model;
    state.list = list;
    main.innerHTML = html;
  } catch (error) {
    if (seq === state.sequence && state.user)
      main.innerHTML = `<section class="panel empty"><h2>Не вдалося відкрити сторінку</h2><p>Перевірте повідомлення та спробуйте ще раз.</p>${button("Повторити", "retry")} <a href="#orders" class="link-button">До замовлень</a></section>`;
    throw error;
  }
}
async function navigate(route, force = false) {
  if (
    !force &&
    state.dirty &&
    !confirm("Є незбережені зміни. Залишити сторінку?")
  ) {
    history.replaceState(null, "", "#" + state.route);
    return;
  }
  if (route !== state.route) {
    state.offset = 0;
    state.filters = { q: "", status: "" };
  }
  history.pushState(null, "", "#" + route);
  await loadRoute(route);
}
window.addEventListener("beforeunload", (e) => {
  if (state.dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.addEventListener("hashchange", () => {
  const route = location.hash.slice(1) || "orders";
  if (state.busy) {
    history.replaceState(null, "", "#" + state.route);
    return;
  }
  task(() => navigate(route));
});
document.addEventListener("click", (e) => {
  const a = e.target.closest('a[href^="#"]');
  if (a) {
    e.preventDefault();
    if (!state.busy) task(() => navigate(a.hash.slice(1)));
  }
});
main.addEventListener("input", (e) => {
  if (e.target.closest("#order-form,#vehicle-form")) markDirty();
  if (e.target.id === "plate")
    document.getElementById("plate-confirm").checked = false;
});
main.addEventListener("change", (e) => {
  if (e.target.id === "ready-confirm") syncReady();
  if (e.target.id === "ocr-file") choosePhoto(e.target.files[0]);
});
function choosePhoto(file) {
  releasePhoto();
  const preview = document.getElementById("ocr-preview"),
    ocr = document.getElementById("ocr-button");
  preview.replaceChildren();
  preview.hidden = true;
  ocr.disabled = true;
  if (!file) return;
  if (
    !["image/jpeg", "image/png"].includes(file.type) ||
    file.size > 10 * 1024 * 1024
  ) {
    showError(new ApiError("Потрібне JPEG/PNG до 10 МБ."));
    return;
  }
  state.photo = file;
  state.preview = URL.createObjectURL(file);
  const img = document.createElement("img");
  img.src = state.preview;
  img.alt = "Вибране фото номера";
  preview.append(img);
  preview.hidden = false;
  ocr.disabled = false;
}
async function openClient(c = {}) {
  state.client = c;
  dialog.innerHTML = view.clientDialog(c);
  dialog.showModal();
}
async function openPicker() {
  state.picker = { q: "", offset: 0, list: null };
  await renderPicker();
  dialog.showModal();
}
async function renderPicker() {
  const p = state.picker;
  p.list = await request(
    "/api/clients?" + params({ q: p.q, offset: p.offset, limit: 10 }),
  );
  dialog.innerHTML = view.picker(p.list, p.q);
}
function selectClient(c) {
  document.getElementById("client_id").value = c?.id || "";
  document.getElementById("selected-client").textContent = c
    ? c.name + " · " + c.phone
    : "Не вибраний";
  markDirty();
}
dialog.addEventListener("cancel", (e) => {
  if (state.busy) e.preventDefault();
});
document.getElementById("logout").addEventListener("click", () => {
  if (state.dirty && !confirm("Вийти без збереження змін?")) return;
  task(async () => {
    await request("/api/auth/logout", { method: "POST" });
    showLogin();
    tell("Ви вийшли із застосунку.");
  });
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-action]");
  if (!b || b.disabled || state.busy) return;
  const action = b.dataset.action;
  if (action === "close-dialog") {
    dialog.close();
    return;
  }
  if (action === "clear-client") {
    selectClient(null);
    return;
  }
  task(
    async () => {
      if (action === "retry") await loadRoute();
      else if (action === "prev" || action === "next") {
        if (state.dirty && !confirm("Є незбережені зміни. Залишити сторінку?"))
          return;
        state.offset = Math.max(
          0,
          state.offset + (action === "next" ? 20 : -20),
        );
        await loadRoute();
      } else if (action === "new-client") await openClient();
      else if (action === "edit-client")
        await openClient((await request("/api/clients/" + b.dataset.id)).data);
      else if (action === "choose-client") await openPicker();
      else if (action === "picker-prev" || action === "picker-next") {
        state.picker.offset = Math.max(
          0,
          state.picker.offset + (action === "picker-next" ? 10 : -10),
        );
        await renderPicker();
      } else if (action === "pick-client") {
        selectClient(
          state.picker.list.data.find((c) => String(c.id) === b.dataset.id),
        );
        dialog.close();
      } else if (action === "delete-client") {
        if (
          !confirm(
            "Видалити клієнта? Клієнтів із пов’язаними записами видалити неможливо.",
          )
        )
          return;
        await request("/api/clients/" + state.client.id, { method: "DELETE" });
        dialog.close();
        await loadRoute();
        tell("Клієнта видалено.");
      } else if (["ready", "in_progress", "completed"].includes(action)) {
        if (state.dirty) throw new ApiError("Спочатку збережіть зміни.");
        if (
          action === "ready" &&
          !document.getElementById("ready-confirm").checked
        )
          throw new ApiError("Підтвердьте перевірку даних.");
        if (
          action === "completed" &&
          !confirm(
            "Підтвердити завершення? Після цього наряд доступний лише для перегляду.",
          )
        )
          return;
        await request("/api/orders/" + state.model.o.id + "/status", {
          method: "PATCH",
          data: {
            status: action,
            ...(action === "ready" ? { confirmed: true } : {}),
          },
        });
        await loadRoute();
        tell("Статус замовлення оновлено.");
      } else if (action === "cancel") {
        dialog.innerHTML = view.cancelDialog();
        dialog.showModal();
      } else if (action === "ocr") {
        if (!state.photo) throw new ApiError("Виберіть фото.");
        const fd = new FormData();
        fd.append("file", state.photo);
        const r = await request("/api/ocr", {
          method: "POST",
          data: fd,
          timeout: 22000,
        });
        document.getElementById("plate").value = r.data.text || "";
        document.getElementById("plate-confirm").checked = false;
        const info = document.getElementById("ocr-result");
        info.textContent = r.data.text
          ? "Перевірте розпізнаний номер, виправте помилки та підтвердьте його."
          : "Номер не прочитано. Введіть його вручну.";
        info.hidden = false;
      } else if (action === "download-photo")
        await download(
          "/api/attachments/" + b.dataset.id,
          "apex-photo-" + b.dataset.id + ".jpg",
        );
      else if (action === "backup") {
        await request("/api/backups", { method: "POST", timeout: 60000 });
        await loadRoute();
        tell("Резервну копію створено. Завантажте її на окремий носій.");
      } else if (action === "download-backup")
        await download(
          "/api/backups/" + b.dataset.id,
          "apex-backup-" + b.dataset.id + ".zip",
        );
    },
    action === "ocr"
      ? "Розпізнавання номера…"
      : action === "backup"
        ? "Створення резервної копії…"
        : "Обробка…",
  );
});
document.addEventListener("submit", (e) => {
  e.preventDefault();
  if (state.busy) return;
  const form = e.target,
    values = Object.fromEntries(new FormData(form));
  const id = form.id,
    attachment = document.getElementById("attachment-file")?.files[0];
  task(
    async () => {
      if (id === "login-form") {
        const r = await request("/api/auth/login", {
          method: "POST",
          data: { username: values.username, password: values.password },
          auth: false,
        });
        state.user = r.data;
        uiSession();
        state.dirty = false;
        await navigate(location.hash.slice(1) || "orders", true);
      } else if (id === "filter-form") {
        state.filters = { q: values.q || "", status: values.status || "" };
        state.offset = 0;
        await loadRoute();
      } else if (id === "intake-form") {
        const plate = normalize(values.plate);
        if (!/^[A-Z0-9]{3,12}$/.test(plate))
          throw new ApiError(
            "Номер: 3–12 літер та цифр після видалення пробілів.",
          );
        if (!document.getElementById("plate-confirm").checked)
          throw new ApiError("Підтвердьте номер.");
        const r = await request("/api/orders", {
          method: "POST",
          data: { plate: values.plate, confirmed: true },
        });
        await navigate("order/" + r.data.id, true);
        tell(
          r.created
            ? "Чернетку створено. Заповніть дані перед початком робіт."
            : "Відкрито активний наряд. Дублікат не створено.",
        );
      } else if (id === "order-form") {
        const o = state.model.o,
          data = {};
        if (values.notes !== o.notes) data.notes = values.notes;
        if (["draft", "ready"].includes(o.status)) {
          const client_id = Number(values.client_id) || null;
          if (client_id !== o.client_id) data.client_id = client_id;
          if (values.description !== o.description)
            data.description = values.description;
        }
        if (!Object.keys(data).length) {
          state.dirty = false;
          await loadRoute();
          tell("Дані не змінювалися.");
          return;
        }
        await request("/api/orders/" + o.id, { method: "PATCH", data });
        state.dirty = false;
        await loadRoute();
        tell("Зміни збережено.");
      } else if (id === "vehicle-form") {
        await request("/api/vehicles/" + state.model.v.id, {
          method: "PATCH",
          data: {
            plate: values["vehicle-plate"],
            make: values.make,
            model: values.model,
            vin: values.vin,
            client_id: Number(values.client_id) || null,
          },
        });
        state.dirty = false;
        await loadRoute();
        tell("Картку автомобіля збережено.");
      } else if (id === "client-form") {
        const editing = state.client.id,
          r = await request("/api/clients" + (editing ? "/" + editing : ""), {
            method: editing ? "PATCH" : "POST",
            data: {
              name: values.name,
              phone: values.phone,
              notes: values["client-notes"],
            },
          });
        dialog.close();
        if (
          state.route.startsWith("order/") ||
          state.route.startsWith("vehicle/")
        ) {
          selectClient(r.data);
          tell(
            "Клієнта збережено. Збережіть зміни в картці, щоб прив’язати його.",
          );
        } else {
          await loadRoute();
          tell("Клієнта збережено.");
        }
      } else if (id === "picker-form") {
        state.picker.q = values["picker-q"];
        state.picker.offset = 0;
        await renderPicker();
      } else if (id === "cancel-form") {
        await request("/api/orders/" + state.model.o.id + "/status", {
          method: "PATCH",
          data: { status: "cancelled", confirmed: true, reason: values.reason },
        });
        dialog.close();
        await loadRoute();
        tell("Замовлення скасовано.");
      } else if (id === "photo-form") {
        if (!attachment) throw new ApiError("Виберіть файл.");
        if (attachment.size > 10 * 1024 * 1024)
          throw new ApiError("Фото перевищує 10 МБ.");
        if (state.dirty)
          throw new ApiError("Збережіть зміни в наряді перед додаванням фото.");
        const fd = new FormData();
        fd.append("file", attachment);
        fd.append("confirmed", "true");
        await request("/api/orders/" + state.model.o.id + "/attachments", {
          method: "POST",
          data: fd,
        });
        await loadRoute();
        tell("Фото збережено.");
      }
    },
    id === "login-form" ? "Вхід…" : "Збереження…",
  );
});
task(async () => {
  try {
    state.user = (await request("/api/auth/me", { auth: false })).data;
    uiSession();
    await loadRoute(location.hash.slice(1) || "orders");
  } catch (error) {
    if (error.status === 401) showLogin();
    else {
      showLogin();
      throw error;
    }
  }
});
