import { USERS, t, expect, test } from "./helpers";

test("signs in and sees the demonstration project", async ({ as }) => {
  const page = await as(USERS[0]);
  await expect(
    page.getByRole("link", { name: /dat\.normand1999|demonstra/i }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: t("notifications.title") }),
  ).toBeVisible();
});
