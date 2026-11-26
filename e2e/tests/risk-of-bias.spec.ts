import { readFileSync } from "node:fs";

import { APIRequestContext } from "@playwright/test";

import { DEMO_ID, USERS, t, token, expect, test } from "./helpers";

// Minimal flow (docs/validacao.md 11.3): two reviewers assess risk of bias, the admin
// resolves the conflicts, and the traffic-light plot is exported. Instrument:
// Newcastle-Ottawa (cohort), whose structure ships with the system.
const base = `/api/v1/projects/${DEMO_ID}`;
const STARS_C: Record<string, string> = {
  "selection.1": "1",
  "selection.2": "1",
  "selection.3": "1",
  "selection.4": "0",
  "comparability.1": "2",
  "outcome.1": "1",
  "outcome.2": "1",
  "outcome.3": "0",
};

async function api(
  request: APIRequestContext,
  bearer: string,
  method: "get" | "post" | "put",
  url: string,
  data?: unknown,
): Promise<Record<string, unknown>> {
  const r = await request[method](url, {
    headers: { Authorization: `Bearer ${bearer}` },
    data,
  });
  expect(r.ok(), `${method} ${url}: ${await r.text()}`).toBeTruthy();
  return (await r.json()) as Record<string, unknown>;
}

async function join(
  request: APIRequestContext,
  admin: string,
  guest: string,
): Promise<void> {
  const invite = await api(request, admin, "post", `${base}/invitations`, {
    roles: ["reviewer"],
  });
  const tokenPart = String(invite["link"]).split("token=")[1];
  const r = await request.post(`/api/v1/invitations/${tokenPart}/accept`, {
    headers: { Authorization: `Bearer ${guest}` },
  });
  // Already a member from another test is fine.
  expect([200, 201, 204, 409]).toContain(r.status());
}

test("two reviewers, conflicts resolved by the admin, traffic-light plot", async ({
  as,
  request,
}) => {
  const [a, b, c] = await Promise.all(USERS.map((u) => token(request, u)));
  await join(request, a, b);
  await join(request, a, c);
  const tool = await api(request, a, "post", `${base}/rob/tools`, {
    template_key: "nos_cohort",
  });
  const studies = (await api(request, a, "get", `${base}/studies`)) as unknown;
  const list = (
    Array.isArray(studies) ? studies : (studies as { items: unknown[] }).items
  ) as {
    id: string;
  }[];
  const studyId = list[0].id;
  await api(request, a, "put", `${base}/rob/studies/${studyId}/tool`, {
    tool_id: tool["id"],
  });

  // Reviewer C (setup through the API): some stars differ from B, overall "moderate".
  const ac = await api(
    request,
    c,
    "post",
    `${base}/rob/studies/${studyId}/assessments`,
    {},
  );
  await api(request, c, "put", `${base}/rob/assessments/${ac["id"]}/answers`, {
    answers: Object.entries(STARS_C).map(([question_key, answer]) => ({
      question_key,
      answer,
    })),
  });
  await api(
    request,
    c,
    "put",
    `${base}/rob/assessments/${ac["id"]}/judgement`,
    {
      final: "moderate",
      justification: "Conforme o artigo (teste fictício)",
    },
  );
  await api(request, c, "post", `${base}/rob/assessments/${ac["id"]}/submit`);

  // Reviewer B, through the interface: one star in every item, overall "low".
  const ab = await api(
    request,
    b,
    "post",
    `${base}/rob/studies/${studyId}/assessments`,
    {},
  );
  const pageB = await as(USERS[1]);
  await pageB.goto(`/projetos/${DEMO_ID}/risco-de-vies/avaliacoes/${ab["id"]}`);
  const groups = pageB.locator("mat-button-toggle-group");
  await expect(groups.first()).toBeVisible();
  const n = await groups.count();
  for (let i = 0; i < n; i++) {
    await groups.nth(i).locator("mat-button-toggle").nth(1).click();
  }
  await pageB.getByLabel(t("rob.assessment.overallJudgement")).click();
  await pageB.getByRole("listbox").getByRole("option").nth(1).click();
  const why = pageB
    .getByLabel(
      new RegExp(
        `${t("rob.assessment.whyDisagree")}|${t("rob.assessment.justification")}`,
      ),
    )
    .last();
  if (await why.isVisible()) {
    await why.fill("Conforme o artigo (teste fictício)");
    await why.blur();
  }
  await pageB.getByRole("button", { name: t("rob.assessment.submit") }).click();
  await expect(
    pageB.getByRole("button", { name: t("rob.assessment.submit") }),
  ).toHaveCount(0);

  // Admin A: consensus, conflicts decided one by one, then submitted.
  const pageA = await as(USERS[0]);
  await pageA.goto(
    `/projetos/${DEMO_ID}/risco-de-vies/estudos/${studyId}/consenso`,
  );
  await pageA.getByRole("button", { name: t("rob.consensus.create") }).click();
  const useA = pageA.getByRole("button", { name: t("rob.consensus.useA") });
  await expect(useA.first()).toBeVisible();
  // Each conflict keeps its buttons after the decision: decide each one once.
  const conflicts = await useA.count();
  for (let i = 0; i < conflicts; i++) {
    const saved = pageA.waitForResponse(
      (r) => r.url().includes("/decisions") && r.ok(),
    );
    await useA.nth(i).click();
    await saved;
  }
  await expect(
    pageA.getByText(t("rob.consensus.counts", { conflicts, undecided: 0 })),
  ).toBeVisible();
  await pageA.getByRole("link", { name: t("rob.consensus.open") }).click();
  await pageA.getByRole("button", { name: t("rob.assessment.submit") }).click();
  await expect(
    pageA.getByRole("button", { name: t("rob.assessment.submit") }),
  ).toHaveCount(0);

  // Consolidated table and traffic-light plot.
  await pageA.goto(`/projetos/${DEMO_ID}/risco-de-vies/tabela`);
  await pageA.getByLabel(t("rob.table.tool")).click();
  await pageA.getByRole("listbox").getByRole("option").first().click();
  await pageA
    .getByRole("button", { name: t("rob.plots.traffic_light") })
    .click();
  const plot = pageA.waitForEvent("download");
  await pageA.getByRole("button", { name: t("rob.plots.downloadSvg") }).click();
  expect(readFileSync(await (await plot).path(), "utf-8")).toContain("<svg");
});
