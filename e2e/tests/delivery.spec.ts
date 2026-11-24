import { readFileSync } from "node:fs";

import { DEMO_ID, USERS, t, expect, test } from "./helpers";

test("PRISMA checklist: record where an item is reported", async ({ as }) => {
  const page = await as(USERS[0]);
  await page.goto(`/projetos/${DEMO_ID}/prisma`);
  const row = page
    .getByRole("row")
    .filter({ hasText: t("prisma.checklist.item") })
    .first();
  await expect(row).toBeVisible();
  const item1 = page
    .getByRole("row")
    .filter({ has: page.getByText("1", { exact: true }) })
    .first();
  await item1.getByLabel(t("prisma.checklist.location")).fill("Título, p. 1");
  await item1.getByLabel(t("prisma.checklist.status")).click();
  await page
    .getByRole("option", { name: t("prisma.checklist.statusName.reported") })
    .click();
  await item1.getByRole("button", { name: t("prisma.save") }).click();
  await expect(
    page.getByText(
      t("prisma.checklist.summary", { reported: 1, na: 0, pending: 41 }),
    ),
  ).toBeVisible();
});

test("backup of the project downloads a ZIP that restores as a new project", async ({
  as,
}) => {
  const page = await as(USERS[0]);
  await page.goto(`/projetos/${DEMO_ID}/exportar`);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: t("export.backup.start") }).click();
  const file = await (await download).path();
  expect(readFileSync(file).subarray(0, 2).toString()).toBe("PK");

  await page.goto("/projetos");
  await page.getByLabel(t("projects.restore.label")).setInputFiles({
    name: "backup.zip",
    mimeType: "application/zip",
    buffer: readFileSync(file),
  });
  // Every author has an account here, so it opens the restored project.
  await expect(page).toHaveURL(/\/projetos\/[0-9a-f-]{36}/, {
    timeout: 60_000,
  });
  await expect(page).not.toHaveURL(new RegExp(DEMO_ID));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "dat.normand1999",
  );
});
