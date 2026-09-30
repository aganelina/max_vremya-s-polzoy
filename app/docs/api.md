# API

Базовый адрес стенда: `https://max-bot.centraluniversity.team/api/v1`.
Полная схема находится в [openapi.json](../../openapi/openapi.json),
проверки с тестовыми ролями в [DATA-API.yaml](../../DATA-API.yaml).
Типы клиента описаны в `src/api/types.ts`, запросы в `src/api/http.ts`.

## Общие правила

- `Deal.quorum` сообщает участнику, что к началу смены должны быть заняты все `capacity` мест.
  Иначе worker отменяет смену и записи с уведомлением, без начисления часов и неявок.
  Решение принимается один раз по записям на момент `startsAt`; проверка: раз в минуту.
- База: `/api/v1`. JSON, поля в camelCase. `?:` в `types.ts`: ключа может не быть; `| null`: ключ есть со значением `null`.
- Аутентификация: заголовок `X-Max-Init-Data` с `window.WebApp.initData`; сервер проверяет подпись.
  Только dev-бэкенд (`APP_ENV=dev|test`): `X-Dev-User: <max_user_id>` вместо initData: фронт шлёт его в dev-сборке,
  когда initData нет (`VITE_DEV_USER` или выбор на `#/demo`).
- Время: ISO 8601 с зоной, длительности: в минутах, часы: числом (`1.5`).
- Ошибки: HTTP-статус + `{ "code": "<machine_code>" }` → `ApiError.code` (`src/api/errors.ts`).
  Тексты для пользователя: `src/lib/errors.ts`, показываются у источника (под кнопкой или полем).
- Без согласия и онбординга всё, кроме `/me`, `/dictionaries`, `/me/consent`, `/me/onboarding`,
  `GET /invites/{token}`, `GET /transfers/{token}`, отвечает `403 onboarding_required`.
- `start_param` (`startapp`) ссылок: `fr_<token>` → `#/i/<token>` (друг позвал), `tr_<token>` → `#/t/<token>` (передача места),
  `co_<token>` → `#/co/<token>` (вступить в компанию), `org_<token>` → `#/org/<token>` (приглашение координатора: принимает бот,
  `/start org_<token>`), `deal_<id>` → `#/deals/<id>`. Токены: 22 символа base64url.

### Коды ошибок, которые экраны показывают отдельно

| Код | Где | Статус |
|---|---|---|
| `seat_taken`, `time_conflict`, `deal_closed` | запись, передача места, наставник | 409 |
| `already_checked_in`, `booking_inactive`, `not_checked_in` | отмена записи, отметка | 409 |
| `expired`, `own_transfer`, `already_booked` | забрать место | 409 |
| `onboarding_required`, `consent_required` | онбординг | 403 |
| `already_taken`, `already_answered`, `not_taken` | микро-дела | 409 |
| `answer_too_short` | ответ на микро-дело (< 10 знаков) | 422 |
| `no_micro_tasks` | `GET /micro-tasks/next`: пустое состояние, не ошибка | 404 |
| `no_route` | `GET /route`: пустое состояние, не ошибка | 404 |
| `too_many_requests`, `insufficient_balance`, `request_closed`, `no_helper` | банк часов | 409 |
| `rate_limited` | 5/мин на check-in, urgent, messages | 429 |
| `not_eligible` | наставничество до 3 дел | 403 |
| `last_owner` | удаление профиля единственным владельцем организации | 409 |
| `ics_invalid`, `file_too_large` | загрузка .ics | 422 / 413 |
| `window_marked`, `cannot_remind_self`, `bad_window` | компания | 409 / 422 |
| `not_coordinator`, `not_owner`, `cannot_revoke_self` | `/coord/*`, доступы | 403 / 409 |
| `invalid_title`, `invalid_duration`, `invalid_capacity`, `starts_in_past`, `invalid_people`, `invalid_text`, `invalid_minutes`, `deadline_in_past`, `note_required`, `already_reviewed`, `undo_expired`, `invalid_period` | формы координатора | 422 / 409 |
| `application_pending`, `invalid_inn`, `invalid_phone`, `invalid_name`, `invalid_address`, `invalid_contact_name`, `seal_too_large`, `seal_not_png`, `signature_too_large`, `signature_not_png` | заявка организации | 409 / 422 |
| `not_operator`, `not_pending`, `reason_required` | оператор | 403 / 409 / 422 |

Отметка на месте ошибки кода отдаёт не статусом, а в теле: `CheckInResult.error = expired | wrong_code | too_early | too_late`.

## Доступ к данным

- Данные участника: MAX-id, имя из профиля MAX, вуз, район, интересы, способ передвижения, окна, записи и часы.
  Полное ФИО, телефон, почта и точная геопозиция участника не запрашиваются.
- Данные организации: имя и телефон контактного лица, ФИО и должность подписанта, подпись и печать.
  Контакты доступны оператору и членам организации. Данные подписанта включаются в справки.
- Участникам другие участники видны только инициалами (`Deal.goingInitials`).
- Координатор видит только записавшихся на его смены: имя и статус.
- Статистика: только группы от трёх человек; координатору: своя организация и «В среднем по пилоту», оператору: все.

## Эндпоинты

### Профиль и онбординг
| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/me` | `Me` |
| GET | `/dictionaries` | `Dictionaries` |
| POST | `/me/consent` | `Me` |
| POST | `/me/onboarding` `{universityId, districtId}` | `Me`; `403 consent_required` |
| PATCH | `/me` `ProfilePatch` | `Me` (`notify=pause` → `pauseUntil` через 7 дней) |
| PUT | `/me/weekly-search` `{params: SearchParams \| null}` | 204 |
| POST | `/me/export` | 204: бот присылает файл в чат MAX |
| DELETE | `/me` | 204; `409 last_owner` |

### Подбор и дела
| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/search/preview?duration_min&when&from[&company_id][&window_from&window_to]` | `{count}`; `0`, если в расписании нет подходящего окна |
| GET | `/search?…` (те же параметры) | `SearchResult`: `window: {from,to} \| null`, `windowSource: 'explicit' \| 'company' \| 'schedule' \| 'fallback' \| 'none'`, `nextWindow: {from,to} \| null`, дела с запасом (`slackMin`, `fit`), `counts` для чипов. Окно: явное → общее компании → расписание → запасное (только если расписания нет). `tonight`: с max(сейчас, 17:30), `tomorrow`: завтра с 17:30, `weekend`: сб/вс с 11:00, `now`: окно, которое идёт или начнётся в ближайшие 15 мин; с расписанием и без: одинаково. Расписание есть, но окна нужной длины нет → `windowSource: 'none'`, `window: null`, `items: []`, все `counts` = 0, `nextWindow`: ближайшее свободное окно расписания ≥ `duration_min` в любой день (или `null`). Дела, задевающие учёбу из расписания вместе с дорогой туда и обратно, не подбираются; дело без известной точки от корпуса не подбирается (`travelMin` не считается нулём) |
| GET | `/deals/{id}[?from=campus\|home]` | `Deal` (с `myBooking`, `cancelUntil`, `instructionsAt`) |
| POST | `/deals/{id}/bookings` `{companyId?, inviteToken?}` | `Booking`; повтор возвращает ту же запись |
| DELETE | `/bookings/{id}` | 204 (после `cancelUntil`: можно, но отмена поздняя) |
| POST | `/deals/{id}/invite` | `{link}`: `startapp=fr_<token>` |
| GET | `/invites/{token}` | `FriendInvite {status: ok\|full\|expired, inviterName, deal}` |
| GET | `/deals/{id}/ics` | `text/calendar`: публичный, без авторизации |
| GET | `/me/deals` | `MyDeals` |

`when`: `now | tonight | tomorrow | weekend`; `from`: `campus | home`; `duration_min`: `30 | 60 | 120 | 180`.
`from=home`: дорогу не считаем, дела своего и соседних районов, `Deal.travelMin = null`: экран пишет «в твоём районе».
`Deal.instructionsAt`: когда бот пришлёт инструкцию: 19:00 накануне или сразу при поздней записи;
экран пишет «Инструкцию пришлю вечером накануне» / «…сразу», без часа.

### Компания
| Метод | Маршрут | Ответ |
|---|---|---|
| POST | `/companies` `{date: YYYY-MM-DD}` | `Company`: создать (3e «Пойти компанией») |
| POST | `/companies/join/{token}` | `Company`: ссылка `co_<token>` |
| GET | `/companies/{id}` | `Company`: участники с окнами, общее окно, дела в нём с голосами |
| PUT | `/companies/{id}/window` `{window: {from, to} \| null}` | `Company`: отметить своё окно |
| POST | `/companies/{id}/members/{memberId}/remind` | 204; `409 window_marked`, `cannot_remind_self` |
| PUT | `/companies/{id}/pick` `{dealId \| null}` | `Company` |

### Отметка на месте
| Метод | Маршрут | Ответ |
|---|---|---|
| POST | `/bookings/{id}/check-in` `{code}` | `CheckInResult` (`late: true`: позже начала + 10 мин). Код: 6 цифр или QR `vremya:checkin:<code>`, TOTP 60 с |
| DELETE | `/bookings/{id}/check-in` | 204: «Отметка ошибочная» |

Сканер: `window.WebApp.openCodeReader()` клиента MAX; запасной путь: снимок камерой и `BarcodeDetector`, затем ввод цифр.

### Свободные окна
| GET | `/me/schedule` | `Schedule` |
|---|---|---|
| POST | `/me/schedule` (multipart, поле `file`, `.ics`) | `Schedule`; `422 ics_invalid`, `413 file_too_large` |

### Микро-дела
| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/micro-tasks/next[?skip=id]` | `MicroTask`; `404 no_micro_tasks` |
| POST | `/micro-tasks/{id}/take` | `MicroTask` (с `deadline`, 2 ч); `409 already_taken` |
| POST | `/micro-tasks/{id}/answer` `{answer}` | `MicroTask` (`status: sent`); `422 answer_too_short` |
| DELETE | `/micro-tasks/{id}/take` | 204 |

### Банк часов
| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/bank` | `HourBank`: `balance` по журналу, `reserved`: часы своих open/matched просьб; новая просьба ≤ `balance − reserved` |
| PUT / DELETE | `/bank/requests/{id}/response` | `HourBank` |
| POST | `/bank/requests` `{text, hours, when?}` | `HourBank`; `409 too_many_requests`, `insufficient_balance` |
| POST | `/bank/requests/{id}/received` | `HourBank`; `409 insufficient_balance`, если баланс < часов просьбы |

### Наставничество
| GET | `/mentorship` | `Mentorship` |
|---|---|---|
| PATCH | `/mentorship` `{accepting}` | `Mentorship` |
| POST | `/mentorship/requests/{id}/accept` | `Mentorship`: записывает на ту же смену |
| POST | `/mentorship/requests/{id}/decline` | `Mentorship` |

### Маршрут, передача места и справка
| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/route[?duration_min&when&from&window_from&window_to]` | `Route`; параметры: как у `/search` (вход: ссылка «Два дела подряд» на результатах); `404 no_route`: экран показывает «пары нет» |
| POST | `/route/bookings` `{dealIds}` | 204: всё или ничего |
| POST | `/bookings/{id}/transfer` | `{link}`: `startapp=tr_<token>`, место держится до начала смены |
| GET | `/transfers/{token}` | `SeatTransfer` (`ok \| taken \| expired`) |
| POST | `/transfers/{token}/claim` | `Booking`; `409 seat_taken`, `expired`, `own_transfer`, `already_booked` |
| GET | `/me/certificate?period=semester\|all` | `Certificate` |
| GET | `/me/certificate.pdf?period=` | PDF (с авторизацией) |
| POST | `/me/certificate/link?period=semester\|all` | `FileLink` `{url, fileName, expiresAt}`: ссылка на PDF на 5 минут для `WebApp.downloadFile` |
| POST | `/me/certificate/share` `{period}` | 204: бот присылает PDF в чат |

Вне `/api/v1`: `GET /check/{code}`: публичная HTML-страница проверки справки (аннулированная: «Справка аннулирована: сформируйте новую»; справки аннулируются при снятии засчитанных часов).
`GET /files/{token}`: файл по ссылке из `FileLink.url` (`{PUBLIC_BASE_URL}/files/{token}`, HMAC-подпись, 5 минут), без авторизации, `Content-Disposition: attachment`; неверная/подделанная/истёкшая ссылка: 404, лимит частоты по IP как у `/check`.

### Координатор
Доступ: активное членство в проверенной организации (`Me.roles.coordinator`), иначе `403 not_coordinator`.
Чужая смена: `404`.

| Метод | Маршрут | Ответ |
|---|---|---|
| GET | `/coord/home` | `CoordinatorHome` |
| GET | `/coord/shifts/{id}/attendance` | `ShiftAttendance` |
| PUT / DELETE | `/coord/shifts/{id}/participants/{pid}/manual` | `ShiftAttendance` |
| GET | `/coord/shifts/{id}/code` | `CheckInCode` |
| POST | `/coord/shifts/{id}/cancel` | 204 |
| POST | `/coord/shifts` `NewShift` | `Shift` |
| POST | `/coord/urgent` `UrgentCall` (`where` обязателен) | `UrgentCallStatus` (`shiftId` созданной смены) |
| GET | `/coord/urgent/{id}` | `UrgentCallStatus`: экран опрашивает каждые 15 с |
| GET | `/coord/reviews` | `{items, acceptedToday, returnedToday}` |
| POST | `/coord/reviews/{id}` `{verdict: accept\|return, note?}` | 204; `note` обязателен для `return` |
| DELETE | `/coord/reviews/{id}` | 204: в течение 10 минут |
| GET | `/coord/micro-tasks` | `CoordMicroTask[]` |
| POST | `/coord/micro-tasks` `NewMicroTask` | `CoordMicroTask` |
| PATCH | `/coord/micro-tasks/{id}` `{active}` | `CoordMicroTask` |
| GET | `/coord/metrics` | `Metrics`: своя организация + «В среднем по пилоту» |
| GET | `/coord/access` | `OrgAccess` |
| GET | `/coord/attendance.csv?from&to` | CSV (UTF-8 с BOM) |
| POST | `/coord/attendance/link?from&to` | `FileLink`: ссылка на тот же CSV на 5 минут для `WebApp.downloadFile`; 422 `invalid_period` |
| POST | `/coord/access/invites` | `OrgAccess`: `startapp=org_<token>`, 7 дней, одноразовая; только владелец |
| PATCH | `/coord/access/{id}` `{revoked}` | `OrgAccess`; только владелец |
| POST | `/coord/access/{id}/owner` | `OrgAccess`: передать владение (без тела); только владелец; 403 `not_owner`, 409 `cannot_transfer_to_self`, 404 `member_not_found` (и для отозванных) |
| GET | `/coord/shifts/{id}/audiences` | `Audience[]` |
| POST | `/coord/shifts/{id}/messages` `{audience, text ≤ 500}` | `{sent}` |

### Организации и оператор
| Метод | Маршрут | Ответ |
|---|---|---|
| POST | `/orgs` (multipart: `name, inn?, address, districtId?, contactName, contactPhone, signName?, signPosition?`, файлы `seal?`, `signature?`: PNG ≤ 1 МБ) | `OrgApplication` (`status: pending`) |
| GET | `/orgs/mine` | `OrgApplication[]`: статус и причина отказа |
| GET | `/operator/orgs[?status=pending\|verified\|rejected]` | `OperatorOrg[]` |
| GET | `/operator/orgs/{id}/{seal\|signature}.png` | PNG |
| POST | `/operator/orgs/{id}/verify` `{lat: number, lon: number, districtId?: string}` | `OperatorOrg`; точка адреса обязательна (рамка России: lat 41–82, lon 19–180, иначе `422 invalid_point`), `422 unknown_district`, `409 not_pending`. Точку получают организация и её смены без своей точки |
| POST | `/operator/orgs/{id}/reject` `{reason}` | `OperatorOrg` |
| GET | `/operator/metrics` | `Metrics`: все организации |

`/operator/*`: только `users.is_operator` (`python -m app.cli make-operator <max_user_id>`), иначе `403 not_operator`.
