# API v1 — APEX AutoLab Reception

Базова адреса: `http://127.0.0.1:8765`. UTF-8, JSON; фото передаються як `multipart/form-data`. Усі часові позначки в базі — ISO 8601 UTC. Ключ `data` містить об’єкт або список. Списки: `data`, `limit`, `offset`, `has_more`; без загальної кількості. Параметри `limit` 1–100 (типово 50), `offset` від 0.

## Вхід і CSRF

1. `GET /api/auth/csrf` → `{"csrf_token":"..."}` і session cookie.
2. `POST /api/auth/login` з JSON `{"username":"operator","password":"..."}` і заголовком `X-CSRFToken`.
3. Зберегти cookie та **новий** `csrf_token` з відповіді входу.
4. Передавати cookie в усіх запитах, а `X-CSRFToken` — у POST/PATCH/DELETE.
5. `GET /api/auth/csrf` дозволяє оновити CSRF-токен. Його типовий строк — 1 година; серверна сесія — 8 годин від входу.
6. `POST /api/auth/logout` відкликає сесію; повертає 204 без тіла.

Публічні лише HTML-оболонка `/`, статичні ресурси `/static/*`, `/api/health`, `/api/auth/csrf`, `/api/auth/login`. Для решти потрібен вхід. `GET /api/auth/me` повертає id й username. Після п’яти неправильних спроб входу за 5 хвилин наступна спроба повертає 429 до завершення вікна.

## Маршрути

| Метод | Шлях | Дія / результат |
|---|---|---|
| GET | `/api/health` | Стан БД, 200 |
| GET, POST | `/api/clients` | Пошук `q` за ім’ям/телефоном; створення 201 |
| GET, PATCH, DELETE | `/api/clients/{id}` | Читання, часткова зміна, видалення 204 |
| GET, POST | `/api/vehicles` | Пошук `q` за номером/VIN; створення 201 |
| GET, PATCH, DELETE | `/api/vehicles/{id}` | Картка, часткова зміна, видалення 204 |
| GET | `/api/vehicles/{id}/orders` | Історія нарядів автомобіля |
| GET, POST | `/api/orders` | Список / приймання за номером |
| GET, PATCH | `/api/orders/{id}` | Деталі / зміна клієнта, опису, приміток |
| PATCH | `/api/orders/{id}/status` | Перехід статусу |
| POST | `/api/ocr` | Розпізнати фото; не зберігати |
| POST | `/api/orders/{id}/attachments` | Додати фото, 201 |
| GET | `/api/attachments/{id}` | Завантажити JPEG |
| GET, POST | `/api/backups` | Перелік / створення копії 201 |
| GET | `/api/backups/{id}` | Завантажити ZIP |

DELETE працює лише для клієнтів і автомобілів без пов’язаних записів. Замовлення не видаляються: використовувати скасування. Відновлення доступне лише офлайн через CLI. GET списку резервних копій повертає `data` без пагінації.

## Тіла запитів і валідація

**Клієнт** — POST обов’язкові `name`, `phone`; PATCH — непорожня підмножина цих полів і `notes`.

```json
{"name":"Тестовий клієнт","phone":"+380 (67) 123-45-67","notes":"Контактна особа"}
```

`name` — непорожній рядок до 120 символів; `phone` — 7–15 цифр, дозволені початковий +, пробіли, дужки й дефіси; зберігаються лише цифри. `notes` до 2000 символів. Пошук телефона — за збереженими цифрами.

**Автомобіль** — POST обов’язковий `plate`; PATCH — хоча б одне дозволене поле:

```json
{"plate":"АА 1234 ВВ","vin":"WVWZZZ1JZXW000001","make":"Volkswagen","model":"Golf","client_id":1}
```

Номер: до 40 символів до нормалізації, після неї 3–12 латинських літер/цифр; пробіли й дефіси видаляються, відповідні кириличні літери зіставляються з латиницею. Формат не обмежений тільки українською маскою. Зберігаються оригінал і нормалізований номер. VIN — 17 символів A–Z/0–9 без I/O/Q або null/порожній рядок. Марка/модель до 100 символів; `client_id` — існуюче додатне ціле або null. Boolean як id не приймається. Ідентифікатори не більші за 2^63−1. Зміна номера при активному наряді заборонена (409).

**Приймання** — `POST /api/orders`:

```json
{"plate":"AA1234BB","confirmed":true,"client_id":1,"description":"Діагностика підвіски","notes":""}
```

Обов’язкові `plate`, `confirmed:true`. `description` до 2000, `notes` до 4000 символів. Нове авто створюється автоматично. Для відомого авто використовується його `client_id`, якщо поле не передано; явне null залишає наряд без клієнта. Новий наряд: 201, `created:true`; уже активний: 200, `created:false`, повертається існуючий об’єкт без перезаписування його даних. Відповідь містить `missing_fields`, `history`, `attachments`. Унікальний номер наряду має префікс `APX-` і UUID; для маршруту використовується числовий `id`.

**Редагування наряду** — PATCH із `client_id`, `description`, `notes`. Зміна клієнта або опису у готовому наряді повертає його в draft і скидає підтвердження. У in_progress редагуються лише примітки. completed/cancelled незмінні.

**Статуси** — `PATCH /api/orders/{id}/status`:

```json
{"status":"ready","confirmed":true}
```

| Зі статусу | Дозволені наступні |
|---|---|
| draft | ready, cancelled |
| ready | draft, in_progress, cancelled |
| in_progress | completed, cancelled |
| completed, cancelled | Немає |

ready вимагає клієнта з ім’ям/телефоном, непорожнього опису та `confirmed:true`; ім’я/телефон копіюються в наряд. in_progress повторно перевіряє заповненість знімка й прапорець підтвердження. cancelled вимагає `confirmed:true` та непорожній `reason` до 1000 символів. Інші переходи не потребують `confirmed`.

**Фільтри нарядів**: `q` — фрагмент номера; `status` — один зі статусів; `date_from`, `date_to` у форматі YYYY-MM-DD, обидві межі включено, за датою створення UTC; `limit`, `offset`. Сортування за id від новіших. Приклад: `/api/orders?status=draft&date_from=2026-10-01&limit=20`.

**Фото** — `file` у multipart, справжній JPEG/PNG до 10 МБ і до 20 мегапікселів. Загальна межа HTTP-тіла 11 МБ. OCR додатково приймає `crop` як рядок JSON `[left,top,right,bottom]` у пікселях зображення після застосування EXIF-орієнтації. Межі цілі, правий/нижній край виключні, прямокутник усередині фото. OCR: `{"data":{"text":"AA1234BB","requires_confirmation":true,"stored":false}}`. Порожній text означає, що потрібне ручне введення. Час очікування процесу обмежено 15 с. При завантаженні вкладення обов’язкове поле `confirmed` зі **строковим** значенням `true`; воно означає згоду на збереження. Фото перекодовується у JPEG без початкових EXIF-метаданих; ім’я генерується сервером.

**Копія** — POST без полів, відповідь `data:{id,created_at,bytes}`. Ідентифікатор — 32 символи hex. У копію входять схема, дані та фото; активні сесії й лічильники входу очищені.

## Формат помилок

```json
{"error":{"code":"incomplete_order","message":"Заповніть дані перед початком робіт.","details":["client_id","client_name","client_phone"]}}
```

400 — JSON/CSRF/Host; 401 — немає чинної сесії або невірні дані входу; 403 — не локальна адреса; 404 — запис відсутній; 409 — конфлікт, заборонений перехід або зв’язаний запис; 413 — завеликий файл; 422 — неправильні поля чи неповний наряд; 429 — забагато спроб входу; 503 — OCR/БД тимчасово недоступні; 504 — timeout OCR. Для неочікуваної помилки — 500 без деталей SQL і персональних даних. Невідомі JSON-поля відхиляються. Повторна спроба POST приймання після мережевої помилки безпечна щодо дублювання активного наряду.

## Приклад виклику з інтерфейсу

Front-end працює з того самого origin; його реалізація — apex/static/js. Password береться з поля форми й не зберігається в коді або localStorage.

```javascript
const pre = await fetch('/api/auth/csrf').then(r => r.json());
const loginResponse = await fetch('/api/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': pre.csrf_token},
  body: JSON.stringify({username, password})
});
const login = await loginResponse.json();
if (!loginResponse.ok) throw new Error(login.error.message);
const response = await fetch('/api/orders', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': login.csrf_token},
  body: JSON.stringify({plate: 'AA1234BB', confirmed: true})
});
const result = await response.json();
if (!response.ok) throw new Error(result.error.message);
// Відкрити result.data; показати missing_fields перед запуском робіт.
```

CORS навмисно не ввімкнений. HTML та статика доступні до входу; API з даними залишається захищеним. CSP дозволяє script/style/connect лише зі свого origin, img зі свого origin і blob; inline-скрипти та eval заборонені.
