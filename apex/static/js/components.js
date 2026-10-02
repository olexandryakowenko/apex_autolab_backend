export const labels = {
  draft: "Чернетка",
  ready: "Готове до роботи",
  in_progress: "У роботі",
  completed: "Завершено",
  cancelled: "Скасовано",
};
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const normalize = (value) =>
  String(value)
    .toUpperCase()
    .replace(
      /[АВЕКМНОРСТУХІ]/g,
      (c) =>
        ({
          А: "A",
          В: "B",
          Е: "E",
          К: "K",
          М: "M",
          Н: "H",
          О: "O",
          Р: "P",
          С: "C",
          Т: "T",
          У: "Y",
          Х: "X",
          І: "I",
        })[c],
    )
    .replace(/[\s-]/g, "");
export const active = (o) => !["completed", "cancelled"].includes(o.status);
export const badge = (status) =>
  `<span class="badge ${esc(status)}">${esc(labels[status] || status)}</span>`;
export const date = (value) =>
  value
    ? new Intl.DateTimeFormat("uk-UA", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "—";
export const bytes = (value) => `${(value / 1024 / 1024).toFixed(2)} МБ`;
export const button = (text, action, kind = "", extra = "") =>
  `<button type="button" class="${kind}" data-action="${action}" ${extra}>${text}</button>`;
export const heading = (section, title, subtitle, action = "") =>
  `<div class="heading"><div><div class="eyebrow">${section}</div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
export const field = (label, name, value = "", extra = "") =>
  `<label>${label}<input name="${name}" id="${name}" value="${esc(value)}" ${extra}></label>`;
export const area = (label, name, value = "", extra = "") =>
  `<label>${label}<textarea name="${name}" id="${name}" ${extra}>${esc(value)}</textarea></label>`;
export const pagination = (list) =>
  `<div class="row spread pagination"><span class="muted tiny">Показано ${list.data.length ? list.offset + 1 : 0}–${list.offset + list.data.length}</span><div class="row">${button("← Попередні", "prev", "", list.offset === 0 ? "disabled" : "")}${button("Наступні →", "next", "", !list.has_more ? "disabled" : "")}</div></div>`;
export const empty = (text) => `<div class="panel empty">${text}</div>`;
export const link = (text, hash, kind = "") =>
  `<a class="link-button ${kind}" href="#${hash}">${text}</a>`;
export function clientForm(c = {}) {
  return `${field("Ім’я та прізвище", "name", c.name, 'required maxlength="120" autocomplete="name"')}${field("Телефон", "phone", c.phone, 'required type="tel" maxlength="40" autocomplete="tel" placeholder="+380…"')}${area("Примітки", "client-notes", c.notes, 'maxlength="2000"')}`;
}
