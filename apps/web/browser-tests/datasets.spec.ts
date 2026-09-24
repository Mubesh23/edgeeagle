import { test, expect, type BrowserContext } from "@playwright/test";
import { listed, inspected, metadata } from "../tests/dataset-fixture";

async function mockApi(context: BrowserContext) {
  const state = {
    listMode: "success",
    inspectionMode: "success",
    inspections: 0,
    unexpected: [] as string[],
  };
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== "http://127.0.0.1:4173" || request.method() !== "GET") {
      state.unexpected.push(request.url());
      return route.abort();
    }
    if (url.pathname === "/api/health")
      return route.fulfill({ json: { status: "ok" } });
    if (url.pathname === "/api/v1/datasets") {
      if (state.listMode === "error")
        return route.fulfill({
          status: 503,
          json: { detail: "private-error-must-not-render" },
        });
      if (state.listMode === "empty")
        return route.fulfill({ json: { items: [] } });
      return route.fulfill({ json: listed });
    }
    if (url.pathname === `/api/v1/datasets/${metadata.root_hash}/inspection`) {
      state.inspections++;
      if (state.inspectionMode === "error")
        return route.fulfill({
          status: 503,
          json: { detail: "private-error-must-not-render" },
        });
      if (state.inspectionMode === "invalid")
        return route.fulfill({
          json: {
            ...inspected,
            metadata: { ...metadata, backtest_eligible: true },
          },
        });
      return route.fulfill({ json: inspected });
    }
    if (url.pathname === "/" || url.pathname.startsWith("/assets/"))
      return route.continue();
    state.unexpected.push(request.url());
    return route.abort();
  });
  return state;
}

test("catalog and explicit replay remain private and readable", async ({
  page,
  context,
}, info) => {
  const state = await mockApi(context);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Retained datasets" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: metadata.operator_label }),
  ).toBeVisible();
  expect(state.inspections).toBe(0);
  await expect(
    page.getByText("Replay-only. Not backtest-eligible.", { exact: true }),
  ).toBeVisible();
  await page.getByText("Provenance and eligibility", { exact: true }).click();
  await expect(
    page.getByText("Unknown — not historically established"),
  ).toBeVisible();
  await expect(
    page.getByText(metadata.root_hash, { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect replay", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Backend replay observation: VERIFIED" }),
  ).toBeVisible();
  await expect(
    page.getByText(inspected.replay_completed_at, { exact: true }),
  ).toBeVisible();
  expect(state.inspections).toBe(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: info.outputPath("dataset-inspection.png"),
    fullPage: true,
  });
  state.inspectionMode = "error";
  await page
    .getByRole("button", { name: "Inspect replay", exact: true })
    .click();
  await expect(page.getByText(/Inspection failed or timed out/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Backend replay observation: VERIFIED" }),
  ).toHaveCount(0);
  await expect(page.getByText("private-error-must-not-render")).toHaveCount(0);
  expect(state.inspections).toBe(2);
  expect(errors).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("unavailable, empty and invalid success fail closed", async ({
  page,
  context,
}) => {
  const state = await mockApi(context);
  state.listMode = "error";
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Catalog unavailable or invalid",
  );
  state.listMode = "empty";
  await page.getByRole("button", { name: "Refresh catalog" }).click();
  await expect(page.getByText(/No dataset roots are selected/)).toBeVisible();
  state.listMode = "success";
  await page.getByRole("button", { name: "Refresh catalog" }).click();
  state.inspectionMode = "invalid";
  await page
    .getByRole("button", { name: "Inspect replay", exact: true })
    .click();
  await expect(page.getByText(/Inspection failed or timed out/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Backend replay observation: VERIFIED" }),
  ).toHaveCount(0);
  expect(state.unexpected).toEqual([]);
});
