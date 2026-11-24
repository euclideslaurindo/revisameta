import { DEMO_ID, USERS, expect, t, test } from "./helpers";

test("the AI turns on only after the admin accepts the data-use notice", async ({
  as,
}) => {
  const page = await as(USERS[0]);
  await page.goto(`/projetos/${DEMO_ID}/configuracoes`);
  await expect(page.getByText(t("settings.ai.off"))).toBeVisible();
  const turnOn = page.getByRole("button", { name: t("settings.ai.turnOn") });
  await expect(turnOn).toBeDisabled();
  // The notice says who receives the data before anything can be turned on.
  await expect(page.getByText(/Google \(API Gemini/)).toBeVisible();
  await page.getByRole("checkbox", { name: /Li e aceito este aviso/ }).check();
  await turnOn.click();
  await expect(page.getByText(t("settings.ai.on"))).toBeVisible();
  await page.getByRole("button", { name: t("settings.ai.turnOff") }).click();
  await expect(page.getByText(t("settings.ai.off"))).toBeVisible();
});
