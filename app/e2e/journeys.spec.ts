import { expect, test, type Page } from '@playwright/test';

async function go(page: Page, route: string) {
  await page.goto('/?demo=1#' + route);
  await expect(page.locator('.hero')).toBeVisible();
  await expect(page.locator('[aria-label="Загрузка"]')).toHaveCount(0);
}

test('home filters, weekly search, history and navigation', async ({ page }) => {
  await go(page, '/');
  await page.getByRole('button', { name: '1 ч', exact: true }).click();
  await page.getByRole('button', { name: 'Завтра', exact: true }).click();
  await page.getByRole('button', { name: 'От дома', exact: true }).click();
  await page.getByRole('checkbox').click();
  await expect(page.getByRole('checkbox')).toBeChecked();
  await page.getByRole('button', { name: 'Найти дело', exact: true }).click();
  await expect(page).toHaveURL(/search\?d=60&w=tomorrow&f=home/);
  await page.getByRole('button', { name: 'Изменить', exact: true }).click();
  await page.getByRole('button', { name: '2 ч', exact: true }).click();
  await expect(page).toHaveURL(/d=120/);
  await page.getByRole('button', { name: '‹ Назад', exact: true }).click();
  await page.getByRole('button', { name: 'Как в прошлый раз' }).click();
  await expect(page.getByRole('button', { name: '1 ч', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('booking tap, cancellation and keyboard activation', async ({ page }) => {
  await go(page, '/deals/d-books');
  await page.getByRole('button', { name: 'Отменить запись', exact: true }).click();
  const confirm = page.getByRole('button', { name: 'Сдвинь — иду', exact: true });
  await expect(confirm).toHaveAttribute('aria-disabled', 'false');
  await confirm.click();
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toHaveAttribute('aria-disabled', 'true');
  await page.getByRole('button', { name: 'Отменить запись', exact: true }).click();
  await expect(confirm).toHaveAttribute('aria-disabled', 'false');
  await confirm.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
});

test('short drag cancels, full drag books and done knob survives resize', async ({ page }) => {
  await go(page, '/deals/d-books');
  await page.getByRole('button', { name: 'Отменить запись', exact: true }).click();
  const confirm = page.getByRole('button', { name: 'Сдвинь — иду', exact: true });
  await expect(confirm).toHaveAttribute('aria-disabled', 'false');
  await confirm.scrollIntoViewIfNeeded();
  const r = (await confirm.boundingBox())!;
  await page.mouse.move(r.x + 30, r.y + 30);
  await page.mouse.down();
  await page.mouse.move(r.x + 70, r.y + 30, { steps: 5 });
  await page.mouse.up();
  await expect(confirm).toBeVisible();
  await page.mouse.move(r.x + 30, r.y + 30);
  await page.mouse.down();
  await page.mouse.move(r.x + r.width - 15, r.y + 30, { steps: 12 });
  await page.mouse.up();
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 844 });
  const knob = (await page.locator('.slide__knob').boundingBox())!;
  const track = (await page.locator('.slide').boundingBox())!;
  expect(Math.abs(knob.x + knob.width - track.x - track.width)).toBeLessThan(1);
});

test('onboarding validates selections and returns to the destination', async ({ page }) => {
  await go(page, '/welcome?next=/micro');
  await page.getByRole('button', { name: 'Согласен, продолжить' }).click();
  await expect(page.getByRole('button', { name: 'Показать дела' })).toBeDisabled();
  await page.getByRole('group', { name: 'Где учишься' }).getByRole('button').first().click();
  await page.getByRole('group', { name: 'Район, где живёшь' }).getByRole('button').first().click();
  await page.getByRole('button', { name: 'Показать дела' }).click();
  await expect(page).toHaveURL(/#\/micro$/);
});

test('bot links open a contextual conversation, not another webapp', async ({ page }) => {
  await page.addInitScript(() => {
    (window as unknown as { botLinks: string[] }).botLinks = [];
    window.WebApp = { openLink: (url) => (window as unknown as { botLinks: string[] }).botLinks.push(url) };
  });
  await go(page, '/deals/d-books');
  await page.getByRole('button', { name: 'Написать координатору в MAX' }).click();
  const links = await page.evaluate(() => (window as unknown as { botLinks: string[] }).botLinks);
  expect(links[0]).toMatch(/^https:\/\/max.ru\/vremya_test_bot\?start=contact_/);
  await go(page, '/my');
  await page.getByRole('button', { name: 'Открыть мои записи в боте' }).click();
  expect(await page.evaluate(() => (window as unknown as { botLinks: string[] }).botLinks)).toContain('https://max.ru/vremya_test_bot?start=my');
});

test('coordinator tools remain clickable below the sticky footer', async ({ page }) => {
  await go(page, '/coord');
  await page.getByRole('button', { name: 'Метрики', exact: true }).click();
  await expect(page).toHaveURL(/#\/coord\/metrics$/);
  await go(page, '/coord');
  await page.getByRole('button', { name: 'Создать смену', exact: true }).click();
  await page.getByRole('button', { name: 'Опубликовать смену' }).click();
  await expect(page.getByText('Добавь название: его увидят в списке дел.')).toBeVisible();
  await page.getByLabel('Что делать', { exact: true }).fill('Помочь библиотеке');
  await page.getByRole('button', { name: 'Опубликовать смену' }).click();
  await expect(page.getByRole('heading', { name: 'Что дальше' })).toBeVisible();
});

test('coordinator audience, message validation and quick text', async ({ page }) => {
  await go(page, '/coord/shifts/s-books/message');
  await page.getByRole('button', { name: /^Отправить \d/ }).click();
  await expect(page.getByText('Напиши текст сообщения.')).toBeVisible();
  await page.getByRole('button', { name: 'Вход со двора', exact: true }).click();
  await expect(page.getByLabel('Сообщение', { exact: true })).toHaveValue('Вход со двора.');
  await page.getByRole('button', { name: /^Отправить \d/ }).click();
  await expect(page.getByRole('heading', { name: 'Сообщение ушло' })).toBeVisible();
});

test('company selection, booking and cancellation', async ({ page }) => {
  await go(page, '/company/c-demo');
  await page.getByRole('button', { name: 'Отменить запись' }).click();
  const tickets = page.locator('.ticket');
  await tickets.first().click();
  await expect(tickets.first()).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: /^Сдвинь — идём/ }).click();
  await expect(page.getByRole('button', { name: /^Вы идёте/ })).toBeVisible();
  await page.getByRole('button', { name: 'Отменить запись' }).click();
  await expect(page.getByRole('button', { name: /^Сдвинь — идём/ })).toBeVisible();
});

test('route selection keeps at least one deal and books it', async ({ page }) => {
  await go(page, '/route');
  await page.locator('.ticket').first().click();
  await expect(page.locator('.ticket--off')).toHaveCount(1);
  await page.locator('.ticket').last().click();
  await expect(page.locator('.ticket--off')).toHaveCount(1);
  await page.getByRole('button', { name: 'Сдвинь — беру это дело' }).click();
  await expect(page.getByRole('button', { name: 'Записал', exact: true })).toBeVisible();
});

test('micro task answer validation, release and submission', async ({ page }) => {
  await go(page, '/micro');
  await page.getByRole('button', { name: 'Сдвинь — беру' }).click();
  await page.getByRole('button', { name: 'Вернуть дело' }).click();
  await page.getByRole('button', { name: 'Сдвинь — беру' }).click();
  await page.getByRole('button', { name: 'Отправить ответ' }).click();
  await expect(page.getByRole('alert')).toContainText('Ответ пустой');
  await page.getByLabel('Твой ответ').fill('Достаточно подробный ответ на микро-дело для проверки.');
  await page.getByRole('button', { name: 'Отправить ответ' }).click();
  await expect(page.getByText('Ответ отправлен')).toBeVisible();
  await page.getByRole('button', { name: 'Взять ещё одно' }).click();
  await expect(page.getByRole('button', { name: 'Сдвинь — беру' })).toBeVisible();
});

test('hour bank responds and publishes a request', async ({ page }) => {
  await go(page, '/bank');
  await page.getByRole('button', { name: 'Помогу', exact: true }).first().click();
  await expect(page.getByText('ты откликнулся · автор напишет в MAX')).toBeVisible();
  await page.getByRole('button', { name: 'Отменить', exact: true }).first().click();
  await page.getByRole('button', { name: 'Попросить помощи' }).click();
  await page.getByRole('button', { name: 'Опубликовать просьбу' }).click();
  await expect(page.getByRole('alert')).toContainText('Напиши, что нужно');
  await page.getByLabel('Что нужно').fill('Помочь с домашней работой');
  await page.getByRole('button', { name: 'Опубликовать просьбу' }).click();
  await expect(page.getByText('Помочь с домашней работой', { exact: true })).toBeVisible();
});

test('mentorship switch and accepting a request', async ({ page }) => {
  await go(page, '/mentor');
  const toggle = page.getByRole('switch', { name: 'Принимаю просьбы' });
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await toggle.click();
  await expect(toggle).toBeChecked();
  await page.getByRole('button', { name: 'Сдвинь — пойду вместе' }).click();
  await expect(page.getByText('Вы и Камила идёте вместе. Запись на ту же смену подтверждена.', { exact: true })).toBeVisible();
});

test('review requires a note and supports undo', async ({ page }) => {
  await go(page, '/coord/reviews');
  await page.getByRole('button', { name: 'На доработку' }).click();
  await page.getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Напиши, что поправить');
  await page.getByLabel('Что поправить').fill('Добавь пример к первому пункту.');
  await page.getByRole('button', { name: 'Отправить', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('вернули на доработку');
  await page.getByRole('button', { name: 'Вернуть', exact: true }).click();
  await page.getByRole('button', { name: 'Засчитать', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('засчитано');
});

test('bot startapp=my opens bookings', async ({ page }) => {
  await page.goto('/?startapp=my&demo=1');
  await expect(page).toHaveURL(/#\/my$/);
  await expect(page.getByRole('button', { name: 'Открыть мои записи в боте' })).toBeVisible();
});
