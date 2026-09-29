import { expect, test } from '@playwright/test';

test('fresh visitor must choose registration or demo', async ({ page }) => {
  const apiRequests: string[] = [];
  page.on('request', (r) => { if (new URL(r.url()).pathname.startsWith('/api/v1/')) apiRequests.push(r.url()); });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Зарегистрироваться через MAX' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Посмотреть демо' }).click();
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Найти дело', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Выйти из демо' }).click();
  await expect(page.getByRole('button', { name: 'Зарегистрироваться через MAX' })).toBeVisible();
  expect(apiRequests).toEqual([]);
});

test('registration opens the MAX bot', async ({ page }) => {
  await page.addInitScript(() => {
    window.WebApp = { openLink: (url) => { document.body.dataset.openedBot = url; } };
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Зарегистрироваться через MAX' }).click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-bot', 'https://max.ru/vremya_test_bot');
});

test('registration preserves the event destination through bot start', async ({ page }) => {
  await page.addInitScript(() => {
    window.WebApp = { openLink: (url) => { document.body.dataset.openedBot = url; } };
  });
  await page.goto('/?startapp=deal_d-books');
  await page.getByRole('button', { name: 'Зарегистрироваться через MAX' }).click();
  await expect(page.locator('body')).toHaveAttribute('data-opened-bot', 'https://max.ru/vremya_test_bot?start=app_deal_d-books');
});
