import { test, expect } from "@playwright/test";

const START = "2026-09-01";
const END = "2026-09-30";

function watch(page) {
  const errors = [];
  page.on("pageerror", (error) => {
    errors.push(String(error && error.message ? error.message : error));
  });
  return errors;
}

async function assertClear(page, errors) {
  await expect(page.locator("#dashboardLoading")).toBeHidden();
  await expect(page.locator("#dashboardLoading.loading-error")).toHaveCount(0);
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(/couldn['’]t refresh this view/i);
  expect(errors, errors.join("\n")).toEqual([]);
}

test("Daily Update dates do not raise the error cover", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/daily_update?start=2026-10-11&end=2026-10-11");
  await assertClear(page, errors);
  await page.locator("#startDate").fill(START);
  await page.locator("#endDate").fill(END);
  await Promise.all([
    page.waitForURL(/start=2026-09-01/),
    page.locator("#applyBtn").click(),
  ]);
  await expect(page).toHaveURL(/end=2026-09-30/);
  await assertClear(page, errors);
  await expect(page.locator("#startDate")).toHaveValue(START);
  await expect(page.locator("#endDate")).toHaveValue(END);
});

test("Morning Brief dates do not raise the error cover", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/morning_brief?start=2026-10-11&end=2026-10-11");
  await assertClear(page, errors);
  await page.locator("#startDate").fill(START);
  await page.locator("#endDate").fill(END);
  await Promise.all([
    page.waitForURL(/start=2026-09-01/),
    page.locator("#applyBtn").click(),
  ]);
  await expect(page).toHaveURL(/end=2026-09-30/);
  await assertClear(page, errors);
  await expect(page.locator("#startDate")).toHaveValue(START);
  await expect(page.locator("#endDate")).toHaveValue(END);
});

test("Website Traffic dates do not raise the error cover", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/website_traffic");
  await assertClear(page, errors);
  await page.locator("#startDate").fill(START);
  await page.locator("#endDate").fill(END);
  await page.locator("#apply").click();
  await assertClear(page, errors);
  await expect(page.locator("#startDate")).toHaveValue(START);
  await expect(page.locator("#endDate")).toHaveValue(END);
});

test("Inbound CAC dates do not raise the error cover", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/inbound_cac");
  await assertClear(page, errors);
  await Promise.all([
    page.waitForURL(/end=2026-09-30/),
    page.locator("#ocEnd").fill(END),
  ]);
  await assertClear(page, errors);
  await Promise.all([
    page.waitForURL(/start=2026-09-01/),
    page.locator("#ocStart").fill(START),
  ]);
  await expect(page).toHaveURL(/end=2026-09-30/);
  await assertClear(page, errors);
});

test("Company Overview dates do not raise the error cover", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/company_overview");
  await assertClear(page, errors);
  await page.locator("#ocStart").fill(START);
  await assertClear(page, errors);
  await page.locator("#ocEnd").fill(END);
  await assertClear(page, errors);
  await expect(page.locator("#ocStart")).toHaveValue(START);
  await expect(page.locator("#ocEnd")).toHaveValue(END);
});

test("Company Overview keeps the quick date preset buttons", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/api/company_overview");
  await assertClear(page, errors);
  for (const label of ["Today", "Yesterday", "This week", "Last week", "MTD", "Last month", "Last 30", "YTD"]) {
    await expect(page.locator("#filterHost .date-preset", { hasText: new RegExp("^" + label + "$") })).toHaveCount(1);
  }
  await page.locator('#filterHost [data-preset="lastmonth"]').click();
  await assertClear(page, errors);
  await expect(page.locator("#ocStart")).toHaveValue(/-01$/);
  await expect(page.locator('#filterHost [data-preset="lastmonth"]')).toHaveAttribute("aria-pressed", "true");
});
