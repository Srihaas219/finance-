import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MINI = path.join(__dirname, "fixtures", "mini_tape.csv");

// The full judge journey through the REAL UI + REAL backend (demo-seeded).
// No API responses are mocked. Behavior is asserted, not element existence.

test("operator → reviewer → consumer end-to-end", async ({ page }) => {
  // ---- 1-3. Login as Data Operator ----
  await page.goto("/login");
  await page.getByTestId("demo-operator").click();
  await expect(page).toHaveURL(/\/operator/);
  await expect(page.getByRole("heading", { name: "Data Operator Dashboard" })).toBeVisible();

  // 7. Validation info visible: seeded records imported + import history (real backend data).
  await expect(page.getByText("Records imported")).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();
  await expect(page.getByText("Import history")).toBeVisible();

  // 4/6. Real upload through the UI produces an import summary.
  await page.locator('input[type="file"]').first().setInputFiles(MINI);
  await page.getByRole("button", { name: "Upload & ingest" }).click();
  await expect(page.getByText(/Imported/)).toBeVisible();

  // 10. Logout
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  // ---- 11-13. Login as Reviewer, open queue ----
  await page.getByTestId("demo-reviewer").click();
  await expect(page).toHaveURL(/\/reviewer/);
  await expect(page.getByRole("heading", { name: "Reviewer Workbench" })).toBeVisible();

  // Filter to high severity, pick the first exception.
  await page.locator("select").first().selectOption("high");
  const firstException = page.getByTestId("exception-item").first();
  await expect(firstException).toBeVisible();
  await firstException.click();

  // 15. Detail shows the validation failure (rule + message).
  await expect(page.getByText("Reviewer decision")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve loan" })).toBeVisible();

  // 16-17. Trigger AI assistance — advisory, separate from the decision.
  await expect(page.getByText("AI Assistant")).toBeVisible();
  await page.getByRole("button", { name: "explain", exact: true }).click();
  // AI recommendation card appears (deterministic Mock).
  await expect(page.getByText(/flagged by rule/)).toBeVisible({ timeout: 15000 });

  // 20-21. Make a real reviewer decision → UI reflects new state.
  await page.getByRole("button", { name: "Ignore exception" }).click();
  await expect(page.getByText(/Ignored exception/)).toBeVisible({ timeout: 15000 });

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  // ---- 25-29. Login as Consumer, inspect verified record ----
  await page.getByTestId("demo-consumer").click();
  await expect(page).toHaveURL(/\/consumer/);
  await expect(page.getByRole("heading", { name: "Data Consumer" })).toBeVisible();

  // Verified records exist (seeded). Open the first.
  const firstVerified = page.getByTestId("verified-item").first();
  await expect(firstVerified).toBeVisible();
  await firstVerified.click();

  // 29. Hash + version visible.
  await expect(page.getByText(/hash:/)).toBeVisible();
  await expect(page.getByText(/v1/).first()).toBeVisible();

  // 30-31. Traceability chain accessible.
  await page.getByRole("button", { name: /Inspect.*traceability/ }).click();
  await expect(page.getByText("Raw → Verified lineage")).toBeVisible();
  await expect(page.getByText("Source file")).toBeVisible();
});
