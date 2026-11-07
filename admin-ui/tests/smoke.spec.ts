import { expect, test } from "@playwright/test";

test("renders login screen", async ({ page }) => {
  await page.goto("/_app/login");
  await expect(page.getByText("Sign in to Sandala")).toBeVisible();
  await expect(page.getByLabel("Login")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
});
