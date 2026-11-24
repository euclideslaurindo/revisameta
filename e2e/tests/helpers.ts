import { readFileSync } from "node:fs";

import {
  APIRequestContext,
  Browser,
  BrowserContext,
  Page,
  test as base,
  expect,
} from "@playwright/test";

export { expect };

/** Interface texts, read from the same i18n file the app uses (never typed here). */
export const pt = JSON.parse(
  readFileSync("/i18n/pt-BR.json", "utf-8"),
) as Record<string, unknown>;

export function t(
  key: string,
  params: Record<string, string | number> = {},
): string {
  let node: unknown = pt;
  for (const part of key.split("."))
    node = (node as Record<string, unknown>)[part];
  if (typeof node !== "string") throw new Error(`missing i18n key ${key}`);
  return node.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k: string) =>
    String(params[k] ?? ""),
  );
}

export const USERS = (process.env["E2E_USERS"] ?? "").split(",");
export const PASSWORD = process.env["E2E_PASSWORD"] ?? "";
export const DEMO_ID = process.env["E2E_DEMO_ID"] ?? "";

export function fixture(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(`/fixtures/${name}`, "utf-8")) as Record<
    string,
    unknown
  >;
}

// The login has a rate limit (protection against brute force), so each account signs
// in once per run. One browser context per account stays open for the whole run; its
// cookie jar follows the rotating session, and every test opens a new tab in it.
const tokens = new Map<string, string>();
const contexts = new Map<string, BrowserContext>();

export const test = base.extend<
  { as: (email: string) => Promise<Page> },
  { browserForUsers: Browser }
>({
  browserForUsers: [
    async ({ browser }, use) => use(browser),
    { scope: "worker" },
  ],
  as: async ({ browserForUsers }, use) => {
    const opened: Page[] = [];
    await use(async (email: string) => {
      let context = contexts.get(email);
      const fresh = context === undefined;
      if (!context) {
        context = await browserForUsers.newContext();
        contexts.set(email, context);
      }
      const page = await context.newPage();
      opened.push(page);
      if (fresh) {
        await page.goto("/entrar");
        await page.getByLabel(t("common.email")).fill(email);
        await page.getByLabel(t("common.password")).fill(PASSWORD);
        await page.getByRole("button", { name: t("login.submit") }).click();
      } else {
        await page.goto("/projetos");
      }
      await expect(
        page.getByRole("heading", { name: t("projects.title") }),
      ).toBeVisible();
      return page;
    });
    for (const page of opened) await page.close();
  },
});

/** API token for setup steps that are not what a test is about. */
export async function token(
  request: APIRequestContext,
  email: string,
): Promise<string> {
  const known = tokens.get(email);
  if (known) return known;
  const r = await request.post("/api/v1/auth/login", {
    data: { email, password: PASSWORD },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  const value = ((await r.json()) as { access_token: string }).access_token;
  tokens.set(email, value);
  return value;
}

/** Formats like the app does in pt-BR (decimal comma), for comparisons. */
export function ptNumber(value: number, digits = 2): string {
  return value.toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
