import { expect, test } from '@playwright/test';

const screens: [string, string][] = [
  ['calendar', '/calendar'], ['3c', '/'], ['2d', '/company/c-demo'], ['3a', '/deals/d-books'], ['3b', '/my'],
  ['3d', '/deals/d-books/check-in'], ['3e', '/search?d=120&w=tonight&f=campus'],
  ['3f', '/profile'], ['3g', '/windows'], ['3h', '/micro'], ['3i', '/bank'],
  ['3j', '/mentor'], ['3k', '/coord'], ['3l', '/coord/shifts/s-books'],
  ['3n', '/coord/shifts/new'], ['3o', '/coord/urgent'], ['3p', '/coord/reviews'],
  ['3q', '/welcome'], ['3r', '/welcome/place'], ['3s', '/route'], ['3t', '/t/ok'],
  ['3u', '/certificate'], ['3v', '/privacy'], ['3w', '/coord/metrics'],
  ['3x', '/coord/access'], ['3y', '/coord/shifts/s-books/message'],
  ['friend', '/i/ok'], ['friend-full', '/i/full'], ['expired', '/t/expired'],
  ['org', '/org/demo-token'], ['apply', '/orgs/apply'],
  ['tasks', '/coord/micro'], ['new-task', '/coord/micro/new'], ['operator', '/operator/orgs'],
];

for (const width of [320, 390, 1366]) {
  for (const [id, route] of screens) {
    test(`${id}: layout and reachable controls at ${width}px`, async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.route(/^https:\/\//, (r) => r.abort());
      await page.setViewportSize({ width, height: 844 });
      await page.goto('/?demo=1#' + route);
      await expect(page.locator('.hero')).toBeVisible();
      await expect(page.locator('[aria-label="Загрузка"]')).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('main')).toHaveCSS('font-family', /Onest/);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      for (const button of await page.locator('button:visible').all()) {
        if (await button.isDisabled()) continue;
        await button.click({ trial: true, timeout: 3000 });
      }
      expect(errors).toEqual([]);
    });
  }
}
