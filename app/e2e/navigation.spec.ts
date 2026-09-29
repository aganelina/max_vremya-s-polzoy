import { expect, test } from '@playwright/test';

for (const route of ['/welcome/place', '/profile']) {
  test(`unsupported university notice follows selection at ${route}`, async ({ page }) => {
    await page.goto(`/?demo=1#${route}`);
    await page.getByRole('button', { name: 'Другой', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Твой вуз пока не поддерживается');
    await expect(page.getByRole('status')).toContainText('координаты центра Казани');
    await page.getByRole('button', { name: 'КФУ', exact: true }).click();
    await expect(page.getByText('Твой вуз пока не поддерживается', { exact: false })).toHaveCount(0);
  });
}

for (const width of [390, 1366]) {
  test(`curator demo has a separate working menu at ${width}px`, async ({ page }) => {
    const apiRequests: string[] = [];
    page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/v1/')) apiRequests.push(r.url()); });
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await page.getByRole('button', { name: 'Посмотреть демо' }).click();
    const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
    if (width < 900) await nav.getByRole('button', { name: 'Все разделы ↓' }).click();
    const curator = nav.getByRole('group', { name: 'Куратор' });
    await expect(curator.getByRole('link', { name: 'Новая смена' })).toBeVisible();
    await expect(nav.getByRole('group', { name: 'Участник' }).getByRole('link', { name: 'Новая смена' })).toHaveCount(0);
    await curator.getByRole('link', { name: 'Новая смена' }).click();
    await page.getByLabel('Что делать', { exact: true }).fill('Учебная смена куратора');
    await page.getByRole('button', { name: 'Опубликовать смену' }).click();
    await expect(page.getByRole('heading', { name: 'Что дальше' })).toBeVisible();
    if (width < 900) await nav.getByRole('button', { name: 'Все разделы ↓' }).click();
    await nav.getByRole('link', { name: 'Обзор разделов' }).click();
    await expect(page.getByRole('heading', { name: 'Куратор', exact: true })).toBeVisible();
    await page.getByRole('button', { name: /Написать участникам/ }).click();
    await page.getByRole('button', { name: 'Вход со двора', exact: true }).click();
    await page.getByRole('button', { name: /^Отправить \d/ }).click();
    await expect(page.getByRole('heading', { name: 'Сообщение ушло' })).toBeVisible();
    expect(apiRequests).toEqual([]);
  });
}

for (const width of [390, 1366]) {
  test(`sections and six-week calendar work at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/?demo=1#/');
    const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
    if (width < 900) await nav.getByRole('button', { name: 'Все разделы ↓' }).click();
    await nav.getByRole('link', { name: 'Афиша на 6 недель' }).click();
    for (let week = 1; week <= 6; week++) {
      await page.getByRole('button', { name: `${week}-я неделя` }).click();
      const days = page.getByRole('group', { name: 'День события' }).getByRole('button');
      await expect(days).toHaveCount(7);
      await days.last().click();
      await expect(page.locator('.ticket')).toHaveCount(4);
    }
    await page.reload();
    await expect(page.getByRole('button', { name: '6-я неделя' })).toHaveAttribute('aria-pressed', 'true');
    const title = await page.locator('.ticket__title').first().innerText();
    await page.locator('.ticket').first().click();
    await expect(page.locator('.hero__title')).toContainText(title.replace(' (демо)', ''));
    await page.getByRole('button', { name: 'Сдвинь — иду', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
    const eventUrl = page.url();
    await nav.getByRole('link', { name: 'Мои дела', exact: true }).click();
    await page.locator('.ticket').filter({ hasText: title }).last().click();
    await expect(page).toHaveURL(eventUrl);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if (width >= 900) expect((await page.locator('.screen').boundingBox())!.width).toBeGreaterThan(700);
  });
}

test('instruction field and submit button do not overlap with a short viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 430 });
  await page.goto('/?demo=1#/coord/shifts/new');
  const field = page.getByLabel('Инструкция участнику');
  await field.fill('Встречаемся у входа.');
  await field.scrollIntoViewIfNeeded();
  const rect = (await field.boundingBox())!;
  expect(rect.height).toBeLessThan(150);
  expect(await field.evaluate(e => getComputedStyle(e).position)).toBe('static');
  expect(await page.locator('.footer').evaluate(e => getComputedStyle(e).position)).toBe('static');
  await page.getByRole('switch', { name: 'Собирать по кворуму' }).click();
  await expect(page.getByRole('switch')).toBeChecked();
  await page.getByRole('button', { name: 'Опубликовать смену' }).click();
  await expect(page.getByText('Добавь название: его увидят в списке дел.')).toBeVisible();
});

const links = [
  ['my', '/my'], ['deal_d-books', '/deals/d-books'], ['fr_ok', '/i/ok'],
  ['tr_ok', '/t/ok'], ['co_c-demo', '/company/c-demo'], ['org_demo-token', '/org/demo-token'],
];
for (const [payload, route] of links) {
  test(`MAX payload ${payload} routes correctly`, async ({ page }) => {
    await page.addInitScript((start_param) => { window.WebApp = { initDataUnsafe: { start_param } }; }, payload);
    await page.goto('/?demo=1');
    await expect(page).toHaveURL(new RegExp(`#${route}$`));
    await expect(page.locator('.hero')).toBeVisible();
  });
}

test('URL payload survives entry into demo and is consumed only once', async ({ page }) => {
  await page.goto('/?WebAppStartParam=deal_d-books');
  await page.getByRole('button', { name: 'Посмотреть демо' }).click();
  await expect(page).toHaveURL(/#\/deals\/d-books$/);
  await page.getByRole('navigation').getByRole('link', { name: 'Главная' }).click();
  await expect(page).toHaveURL(/#\/$/);
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();
});

test('hash payload and invalid payload fallback', async ({ page }) => {
  await page.goto('/?demo=1#WebAppStartParam=deal_d-books&WebAppData=example');
  await expect(page).toHaveURL(/#\/deals\/d-books$/);
  await page.goto('/?demo=1&startapp=deal_%2Foutside');
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();
});

test('swipe does not jump backwards during confirmation or book on cancellation', async ({ page }) => {
  await page.goto('/?demo=1#/deals/d-books');
  await page.getByRole('button', { name: 'Отменить запись', exact: true }).click();
  const slide = page.getByRole('button', { name: 'Сдвинь — иду', exact: true });
  await expect(slide).toHaveAttribute('aria-disabled', 'false');
  await slide.scrollIntoViewIfNeeded();
  const r = (await slide.boundingBox())!;
  await page.mouse.move(r.x + 30, r.y + 30);
  await page.mouse.down();
  await page.mouse.move(r.x + 90, r.y + 30, { steps: 4 });
  await slide.dispatchEvent('pointercancel', { pointerId: 1 });
  await page.mouse.up();
  await expect(slide).toHaveAttribute('aria-disabled', 'false');
  await page.mouse.move(r.x + 30, r.y + 30);
  await page.mouse.down();
  await page.mouse.move(r.x + r.width - 30, r.y + 30, { steps: 15 });
  const before = (await page.locator('.slide__knob').boundingBox())!.x;
  await page.mouse.up();
  for (let i = 0; i < 4; i++) {
    expect((await page.locator('.slide__knob').boundingBox())!.x).toBeGreaterThanOrEqual(before - 1);
    await page.waitForTimeout(60);
  }
  await expect(page.getByRole('button', { name: 'Ты идёшь', exact: true })).toBeVisible();
});
