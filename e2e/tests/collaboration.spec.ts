import { DEMO_ID, USERS, t, token, expect, test } from "./helpers";

test("a comment mentioning a member reaches that member as a notice", async ({
  as,
  request,
}) => {
  // Setup (not what this test is about): D joins the demo project as reader.
  const a = await token(request, USERS[0]);
  const b = await token(request, USERS[3]);
  const base = `/api/v1/projects/${DEMO_ID}`;
  const invite = await request.post(`${base}/invitations`, {
    headers: { Authorization: `Bearer ${a}` },
    data: { roles: ["reader"] },
  });
  expect(invite.ok(), await invite.text()).toBeTruthy();
  const link = ((await invite.json()) as { link: string }).link;
  const accepted = await request.post(
    `/api/v1/invitations/${link.split("token=")[1]}/accept`,
    {
      headers: { Authorization: `Bearer ${b}` },
    },
  );
  expect(accepted.ok(), await accepted.text()).toBeTruthy();
  const studies = (await (
    await request.get(`${base}/studies`, {
      headers: { Authorization: `Bearer ${a}` },
    })
  ).json()) as
    | { id: string; label: string }[]
    | { items: { id: string; label: string }[] };
  const study = Array.isArray(studies) ? studies[0] : studies.items[0];

  const pageA = await as(USERS[0]);
  // Wait for the member list before opening the mention selector.
  const members = pageA.waitForResponse((r) => r.url().includes("/comments/members") && r.ok());
  await pageA.goto(`/projetos/${DEMO_ID}/estudos/${study.id}`);
  await members;
  const text = `Confere o DP do grupo 1? (teste fictício ${Date.now()})`;
  await pageA.getByLabel(t("comments.new")).fill(text);
  await pageA.getByLabel(t("comments.mention")).click();
  await pageA.getByRole("option", { name: "E2E D" }).click();
  await pageA.keyboard.press("Escape");
  await pageA.getByRole("button", { name: t("comments.send") }).click();
  await expect(pageA.getByText(text)).toBeVisible();

  const pageB = await as(USERS[3]);
  await pageB.getByRole("button", { name: t("notifications.title") }).click();
  const notice = pageB.getByRole("menuitem", {
    name: new RegExp(t("notifications.kind.mention", { author_name: "E2E A" })),
  });
  await expect(notice.first()).toBeVisible();
  await notice.first().click();
  // The notice opens the commented study, where the comment is.
  await expect(pageB).toHaveURL(new RegExp(`/estudos/${study.id}`));
  await expect(pageB.getByText(text)).toBeVisible();
});
