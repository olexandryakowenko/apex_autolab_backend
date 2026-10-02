/** Same-origin API, CSRF renewal, timeouts; no automatic retry of uncertain writes. */
export class ApiError extends Error {
  constructor(message, status = 0, code = "client", details = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
let csrf = "";
export function clearToken() {
  csrf = "";
}
export async function request(
  path,
  {
    method = "GET",
    data,
    auth = true,
    timeout = 25000,
    binary = false,
    retry = true,
  } = {},
) {
  const write = !["GET", "HEAD"].includes(method);
  if (write && !csrf)
    csrf = (await request("/api/auth/csrf", { auth: false })).csrf_token;
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), timeout);
  try {
    const form = data instanceof FormData,
      headers = { Accept: binary ? "*/*" : "application/json" };
    if (write) headers["X-CSRFToken"] = csrf;
    if (data !== undefined && !form)
      headers["Content-Type"] = "application/json";
    const response = await fetch(path, {
      method,
      headers,
      body: data === undefined ? undefined : form ? data : JSON.stringify(data),
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
    });
    if (binary && response.ok) return await response.blob();
    const raw = await response.text();
    let result;
    try {
      result = raw ? JSON.parse(raw) : null;
    } catch {
      throw new ApiError(
        "Сервер повернув неочікувану відповідь.",
        response.status,
        "invalid_response",
      );
    }
    if (!response.ok) {
      if (write && retry && result?.error?.code === "csrf_failed") {
        csrf = (await request("/api/auth/csrf", { auth: false })).csrf_token;
        return await request(path, {
          method,
          data,
          auth,
          timeout,
          binary,
          retry: false,
        });
      }
      if (response.status === 401 && auth) {
        csrf = "";
        window.dispatchEvent(new Event("apex:session-ended"));
      }
      throw new ApiError(
        result?.error?.message || `Помилка сервера (${response.status}).`,
        response.status,
        result?.error?.code,
        result?.error?.details,
      );
    }
    if (result?.csrf_token) csrf = result.csrf_token;
    return result;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const message =
      error.name === "AbortError"
        ? "Сервер не відповів вчасно."
        : "Немає зв’язку із сервером. Перевірте, чи запущено застосунок.";
    throw new ApiError(
      message +
        (write
          ? " Результат операції невідомий: перевірте дані перед повторним збереженням."
          : ""),
      0,
      "network",
    );
  } finally {
    clearTimeout(timer);
  }
}
export function params(values) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(values))
    if (v !== "" && v !== null && v !== undefined) q.set(k, v);
  return q.toString();
}
export async function download(path, name) {
  const blob = await request(path, { binary: true, timeout: 60000 });
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
