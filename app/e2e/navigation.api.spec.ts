import { expect, test } from '@playwright/test';

for (const width of [390, 1366]) {
  test(`API: demo sections are absent, coordinator access remains at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => localStorage.setItem('vremya:dev-user', '900206'));
    await page.goto('/#/profile');
    const nav = page.getByRole('navigation', { name: 'Разделы приложения' });
    await expect(nav.getByRole('link', { name: 'Главная' })).toBeVisible();
    await expect(nav.getByRole('button', { name: /разделы/ })).toHaveCount(0);
    await expect(nav.locator('#app-sections')).toHaveCount(0);
    await page.getByRole('button', { name: 'Другой', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('координаты центра Казани');
    await expect(page.getByRole('status')).not.toContainText('В демо');
    await page.getByRole('button', { name: /Кабинет координатора/ }).click();
    await expect(page.getByRole('button', { name: 'Создать смену', exact: true })).toBeVisible();
    await expect(nav.locator('#app-sections')).toHaveCount(0);
  });
}
