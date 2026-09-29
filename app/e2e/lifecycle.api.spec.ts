import { expect, test } from '@playwright/test';

test('API: onboarding, create shift, book/cancel, attendance, coordinator message, CSV', async ({ page, browser, baseURL }) => {
  const user = String(80_000_000 + Date.now() % 10_000_000);
  await page.addInitScript((id) => localStorage.setItem('vremya:dev-user', id), user);
  await page.goto('/');
  await page.getByRole('button', { name: 'Согласен, продолжить' }).click();
  await page.getByRole('group', { name: 'Где учишься' }).getByRole('button').first().click();
  await page.getByRole('group', { name: 'Район, где живёшь' }).getByRole('button').first().click();
  await page.getByRole('button', { name: 'Показать дела' }).click();
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();

  const context = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, timezoneId: 'Europe/Moscow' });
  await context.addInitScript(() => localStorage.setItem('vremya:dev-user', '900206'));
  const coord = await context.newPage();
  await coord.goto('/#/coord/shifts/new');
  await coord.getByLabel('Что делать', { exact: true }).fill(`Проверка интерфейса ${user}`);
  await coord.getByLabel('Инструкция участнику').fill('Встречаемся у входа. Вопросы — координатору в MAX.');
  const creation = coord.waitForResponse((r) => r.url().endsWith('/api/v1/coord/shifts') && r.request().method() === 'POST');
  await coord.getByRole('button', { name: 'Опубликовать смену' }).click();
  const response = await creation;
  expect(response.ok()).toBeTruthy();
  const shift = await response.json();
  await expect(coord.getByRole('heading', { name: 'Что дальше' })).toBeVisible();

  await page.goto(`/#/deals/${shift.id}`);
  await page.getByRole('button', { name: 'Сдвинь — иду', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Отменить запись', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Сдвинь — иду', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Сдвинь — иду', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();

  await coord.goto(`/#/coord/shifts/${shift.id}`);
  await coord.getByRole('button', { name: 'Отметить', exact: true }).click();
  await expect(coord.getByText('отметка вручную')).toBeVisible();
  await coord.getByRole('button', { name: 'Вернуть', exact: true }).click();
  await expect(coord.getByRole('button', { name: 'Отметить', exact: true })).toBeVisible();
  await coord.goto(`/#/coord/shifts/${shift.id}/message`);
  await coord.getByRole('button', { name: 'Вход со двора', exact: true }).click();
  await coord.getByRole('button', { name: 'Отправить 1 человеку' }).click();
  await expect(coord.getByRole('heading', { name: 'Сообщение ушло' })).toBeVisible();
  await coord.goto('/#/coord/access');
  const download = coord.waitForEvent('download');
  await coord.getByRole('button', { name: 'Выгрузить CSV' }).click();
  expect((await download).suggestedFilename()).toMatch(/\.csv$/);
  await context.close();
});

test('API: profile persists, calendar import, micro task submission, PDF', async ({ page }) => {
  const user = String(90_000_000 + Date.now() % 10_000_000);
  const headers = { 'X-Dev-User': user };
  await page.request.get('/api/v1/me', { headers });
  await page.request.post('/api/v1/me/consent', { headers, data: {} });
  const dict = await (await page.request.get('/api/v1/dictionaries', { headers })).json();
  const onboarding = await page.request.post('/api/v1/me/onboarding', { headers, data: { universityId: dict.universities[0].id, districtId: dict.districts[0].id } });
  expect(onboarding.ok()).toBeTruthy();
  await page.addInitScript((id) => localStorage.setItem('vremya:dev-user', id), user);
  await page.goto('/#/profile');
  const transport = page.getByRole('group', { name: 'Как добираешься' }).getByRole('button').last();
  const name = await transport.innerText();
  await transport.click();
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('button', { name, exact: true })).toHaveAttribute('aria-pressed', 'true');

  await page.goto('/#/windows');
  await page.locator('input[type=file]').setInputFiles({ name: 'schedule.ics', mimeType: 'text/calendar', buffer: Buffer.from('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//UI Test//RU\r\nBEGIN:VEVENT\r\nUID:ui-test\r\nDTSTART:20261005T060000Z\r\nDTEND:20261005T080000Z\r\nSUMMARY:Учёба\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n') });
  await expect(page.getByRole('button', { name: 'Загружено: schedule.ics' })).toBeVisible();

  await page.goto('/#/micro');
  await page.getByRole('button', { name: 'Сдвинь — беру' }).click();
  await page.getByLabel('Твой ответ').fill('Проверил текст задания и подготовил подробный ответ для координатора.');
  await page.getByRole('button', { name: 'Отправить ответ' }).click();
  await expect(page.getByText('Ответ отправлен')).toBeVisible();

  await page.goto('/#/certificate');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: /Скачать PDF/ }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
});

for (const source of ['query', 'hash']) {
test(`API: MAX ${source} deep link survives mandatory registration and returns home once`, async ({ page }) => {
  const user = String(110_000_000 + Date.now() % 10_000_000);
  const records = await (await page.request.get('/api/v1/me/deals', { headers: { 'X-Dev-User': '1' } })).json();
  const id = records.upcoming[0].id;
  await page.addInitScript((user) => localStorage.setItem('vremya:dev-user', user), user);
  await page.goto(source === 'query' ? `/?WebAppStartParam=deal_${id}` : `/#WebAppStartParam=deal_${id}&WebAppData=example`);
  await page.getByRole('button', { name: 'Согласен, продолжить' }).click();
  await page.getByRole('group', { name: 'Где учишься' }).getByRole('button').first().click();
  await page.getByRole('group', { name: 'Район, где живёшь' }).getByRole('button').first().click();
  await page.getByRole('button', { name: 'Показать дела' }).click();
  await expect(page).toHaveURL(new RegExp(`#/deals/${id}$`));
  await expect(page.getByRole('button', { name: 'Сдвинь — иду', exact: true })).toBeVisible();
  await page.getByRole('navigation').getByRole('link', { name: 'Главная' }).click();
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();
});

}
