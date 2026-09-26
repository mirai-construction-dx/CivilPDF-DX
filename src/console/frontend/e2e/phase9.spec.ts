import { test, expect } from "@playwright/test";
import { setupApp } from "./helpers";

test.describe("Phase 1 features", () => {
  test("shows unread notification badge from the API", async ({ page }) => {
    await setupApp(page, { documents: [], projects: [] });
    await page.goto("/");

    const badge = page.locator(".ep-notif-dot");
    await expect(badge).toHaveText("1");
    await badge.click();
    await expect(page.getByText("承認依頼が届いています")).toBeVisible();
  });

  test("documents page renders server-side pagination", async ({ page }) => {
    await setupApp(page);
    await page.goto("/");
    await page.getByRole("button", { name: "図書管理" }).click();

    await expect(page.getByText("橋梁設計図")).toBeVisible();
    await expect(page.getByText(/1 件中/)).toBeVisible();
  });

  test("login page offers SSO and password reset", async ({ page }) => {
    await page.goto("/login");
    await expect(
      page.getByRole("button", { name: /組織アカウントでログイン/ }),
    ).toBeVisible();
    await page.getByRole("button", { name: "パスワードを忘れた場合" }).click();
    await expect(
      page.getByRole("dialog", { name: "パスワード再設定" }),
    ).toBeVisible();
  });
});
