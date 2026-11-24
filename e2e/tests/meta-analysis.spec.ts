import { readFileSync } from "node:fs";

import { Page } from "@playwright/test";

import { DEMO_ID, USERS, fixture, ptNumber, t, expect, test } from "./helpers";

// docs/validacao.md 11.1 item 4: same data through the interface -> same result as
// metafor. The demo project holds dat.normand1999 (length of stay, lower is better,
// so the screen shows the sign inverted). Expected values come from the fixture R wrote.
const cases = fixture("meta-analysis.json")["cases"] as {
  name: string;
  expected: Record<string, number>;
}[];
const expected = cases.find(
  (c) => c.name === "dat.normand1999_MD_REML_knha",
)!.expected;

async function runWizard(page: Page): Promise<void> {
  await page.goto(`/projetos/${DEMO_ID}/meta-analise`);
  // Steps 1 to 3 keep the plan's choices; each step has its own "next" button.
  for (let i = 0; i < 3; i++) {
    // While a step slides in, the previous one is still on screen: take the newest.
    await page
      .getByRole("button", { name: t("meta.next") })
      .locator("visible=true")
      .last()
      .click();
    await page.waitForTimeout(500);
  }
  await page.getByRole("button", { name: t("meta.run") }).click();
}

test("the pooled effect on screen matches metafor", async ({ as }) => {
  const page = await as(USERS[0]);
  await runWizard(page);
  const effect = page.getByRole("row").filter({
    has: page.getByRole("rowheader", {
      name: t("meta.res.effect", { measure: "MD" }),
    }),
  });
  // Inverted sign: estimate -15.11 becomes 15.11; the interval swaps ends.
  await expect(effect).toContainText(ptNumber(-expected["estimate"]));
  await expect(effect).toContainText(ptNumber(-expected["ci_ub"]));
  await expect(effect).toContainText(ptNumber(-expected["ci_lb"]));
});

test("forest plot, history and R script are downloadable", async ({ as }) => {
  const page = await as(USERS[0]);
  await runWizard(page);
  const forest = page.waitForEvent("download");
  await page
    .getByRole("button", { name: t("rob.plots.downloadSvg") })
    .first()
    .click();
  const svg = readFileSync(await (await forest).path(), "utf-8");
  expect(svg).toContain("<svg");

  await page.getByRole("button", { name: t("meta.history.save") }).click();
  await expect(page.getByText(t("meta.history.saved"))).toBeVisible();
  const script = page.waitForEvent("download");
  await page
    .getByRole("button", { name: t("meta.history.script") })
    .first()
    .click();
  const r = readFileSync(await (await script).path(), "utf-8");
  expect(r).toContain("library(metafor)");
  expect(r).toContain("rma(");
});

test("publication bias with fewer than ten studies carries the strong warning", async ({
  as,
}) => {
  const page = await as(USERS[0]);
  await runWizard(page);
  await page.getByRole("button", { name: t("meta.pb.run") }).click();
  // dat.normand1999 has 9 studies: Egger and the funnel cannot be read as a conclusion.
  await expect(page.getByText(t("meta.pb.fewTitle", { k: 9 }))).toBeVisible();
});
