import { readFileSync } from "node:fs";

import { DEMO_ID, USERS, t, expect, test } from "./helpers";

test("GRADE: suggestions, justified decision and Summary of Findings", async ({
  as,
}) => {
  const page = await as(USERS[0]);
  await page.goto(`/projetos/${DEMO_ID}/grade`);
  await page.getByRole("button", { name: t("grade.suggest") }).click();
  // dat.normand1999 has a very high I² and a 95% CI that crosses no effect.
  await expect(
    page.getByText(t("grade.reason.inconsistency_high_i2", { i2: "99,0" })),
  ).toBeVisible();
  await expect(
    page.getByText(t("grade.reason.imprecision_crosses_null")),
  ).toBeVisible();

  // Accepting a downgrade still needs a justification.
  await page.getByRole("button", { name: t("grade.save") }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  const rows = page.getByRole("row");
  for (const domain of ["inconsistency", "imprecision"]) {
    await rows
      .filter({ hasText: t(`grade.domainName.${domain}`) })
      .getByLabel(t("grade.justification"))
      .fill("Conferido pelo grupo (teste fictício)");
  }
  await page.getByRole("button", { name: t("grade.save") }).click();
  // Saved: it shows in the list, with the final level computed from the decisions.
  await expect(
    page.getByRole("button", { name: t("grade.open") }),
  ).toBeVisible();

  const docx = page.waitForEvent("download");
  await page.getByRole("button", { name: t("grade.sof.docx") }).click();
  const bytes = readFileSync(await (await docx).path());
  expect(bytes.subarray(0, 2).toString()).toBe("PK");
});
