# Мини-приложение

React 19, TypeScript, Vite, MAX UI, React Query и React Router.
Шрифты Onest и Unbounded включены в сборку; лицензии находятся в `public/licenses`.
Запуск всего проекта описан в [корневом README](../README.md).

## Локальная разработка

Команды фронтенда выполняются из каталога `app`.

```sh
pnpm install --frozen-lockfile
VITE_USE_MOCKS=true pnpm dev
```

Приложение откроется на `http://localhost:5173`. В этом режиме используются данные
из `src/api/mock.ts`, бэкенд не нужен. Список экранов доступен по `#/demo`.

Для работы с реальным API сначала запустите локальный бэкенд с `APP_ENV=dev`,
`PUBLIC_BASE_URL=http://localhost:8080` и демо-данными. Затем:

```sh
VITE_USE_MOCKS=false VITE_DEV_USER=1 pnpm dev
```

Vite проксирует `/api`, `/files` и `/check` на `http://localhost:8000`.
Другой адрес задаётся через `VITE_PROXY_TARGET`. `VITE_DEV_USER` выбирает тестового
пользователя; такой вход доступен только на локальном бэкенде.

## Сборка

```sh
pnpm typecheck
VITE_USE_MOCKS=false pnpm build
```

Результат появится в `dist/`. Docker задаёт адрес MAX Bridge, ник бота и доступность
демо через аргументы сборки. Отдельную сборку с тестовыми данными можно получить так:

```sh
VITE_USE_MOCKS=true VITE_ALLOW_MOCK_BUILD=true pnpm build
```

| Переменная | Назначение |
| --- | --- |
| `VITE_USE_MOCKS` | Использовать встроенные тестовые данные вместо API |
| `VITE_API_BASE` | Префикс API, по умолчанию `/api/v1` |
| `VITE_PROXY_TARGET` | Адрес бэкенда для локального прокси Vite |
| `VITE_DEV_USER` | MAX-id тестового пользователя в dev-режиме |
| `VITE_MAX_BRIDGE_URL` | `https://st.max.ru/js/max-web-app.js` |
| `VITE_BOT_USERNAME` | Ник бота для ссылок, без `@` |
| `VITE_DEMO_ENABLED` | Показывать кнопку входа в демо; в Docker зависит от `SEED_DEMO` |
| `VITE_ALLOW_MOCK_BUILD` | Разрешить production-сборку с тестовыми данными |

## Структура

- `src/screens/`: экраны участника, координатора, оператора и регистрации.
- `src/ui/`, `src/styles/`: компоненты и стили.
- `src/api/`: типы, HTTP-клиент и тестовые данные.
- `src/max/`: вызовы MAX Bridge и ссылки в бот.
- `src/lib/`: навигация, файлы, форматирование и обработка ошибок.
- [docs/api.md](docs/api.md): маршруты и ответы API.

## Браузерные тесты

```sh
pnpm exec playwright install chromium
pnpm test:e2e
```

Можно использовать установленный Chrome: `PLAYWRIGHT_CHANNEL=chrome pnpm test:e2e`.
Тесты проверяют навигацию, формы, запись и отмену, ссылки, основные сценарии и вёрстку
на разных размерах экрана. При ошибке трасса сохраняется в `test-results/`.

Для тестов с реальным API нужен отдельный локальный бэкенд с демо-данными,
`APP_ENV=dev` и пустым `MAX_BOT_TOKEN`. Они создают пользователей и смены,
поэтому запускаются только с отдельной тестовой базой.

```sh
E2E_API_URL=http://127.0.0.1:8001 PLAYWRIGHT_CHANNEL=chrome pnpm test:e2e:api
```

## Демо

`SEED_DEMO=true` или `refresh` в Docker включает кнопку «Посмотреть демо».
После её нажатия приложение открывается с `?demo=1` и использует данные в памяти
вкладки. Для настоящего участия пользователь проходит регистрацию через MAX.
