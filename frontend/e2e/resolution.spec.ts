import { test, expect } from "@playwright/test";

test("customer answer, admin revision and correction, and customer reopening", async ({
  browser,
}) => {
  const admin = await browser.newContext();
  const customer = await browser.newContext();
  try {
    const login = await admin.request.post("/api/auth/login", {
      data: { username: "admin", password: "test-password" },
    });
    expect(login.ok()).toBeTruthy();
    const csrf = (await login.json()).csrf_token;
    for (const article of [
      {
        title: "Browser refund guidance",
        body: "Duplicate charges belong to Billing. An approved refund can take five to ten business days.",
      },
      {
        title: "Browser urgency policy",
        body: "Routine billing requests have normal priority.",
        is_policy: true,
      },
    ])
      expect(
        (
          await admin.request.post("/api/articles", {
            headers: { "X-CSRF-Token": csrf },
            data: article,
          })
        ).ok(),
      ).toBeTruthy();
    expect(
      (
        await admin.request.post("/api/knowledge/reindex", {
          headers: { "X-CSRF-Token": csrf },
        })
      ).ok(),
    ).toBeTruthy();
    const page = await customer.newPage();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/support");
    await page
      .getByLabel("Subject", { exact: true })
      .fill("Refund policy timing");
    await page
      .getByLabel("Your enquiry", { exact: true })
      .fill("How long does an approved refund usually take?");
    const result = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/portal/tickets") &&
        r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Get help", exact: true }).click();
    const ticket = (await (await result).json()).ticket;
    await expect(
      page.getByRole("main").getByText("Answered by AI", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Your enquiry has been answered.", { exact: true }),
    ).toBeVisible();
    await page
      .getByText("Sources behind this answer", { exact: false })
      .click();
    await expect(page.locator("blockquote").first()).toContainText(
      "five to ten business days",
    );
    await page.screenshot({
      path: "../artifacts/customer-portal-resolution.png",
      fullPage: true,
    });
    await page.reload();
    await page
      .getByRole("button", {
        name: "#" + String(ticket.id).padStart(4, "0"),
        exact: false,
      })
      .click();
    await expect(
      page.getByText("Your enquiry has been answered.", { exact: true }),
    ).toBeVisible();
    const ops = await admin.newPage();
    await ops.goto("/tickets/" + ticket.id);
    await ops
      .getByLabel("Correction or revision instructions")
      .fill("Make the answer more concise without changing the policy.");
    await ops
      .getByRole("button", { name: "Request AI changes", exact: true })
      .click();
    await expect(
      ops.getByText("Draft · not visible to customer", { exact: true }),
    ).toBeVisible();
    await ops.screenshot({
      path: "../artifacts/admin-resolution-review.png",
      fullPage: true,
    });
    await ops
      .getByRole("button", { name: "Publish revised answer", exact: true })
      .click();
    await expect(
      ops.getByRole("heading", { name: "Resolved by support", exact: true }),
    ).toBeVisible();
    await ops
      .getByLabel("Correction or revision instructions")
      .fill(
        "Our support team has reviewed the timing. Approved refunds normally take five to ten business days.",
      );
    await ops
      .getByRole("button", { name: "Publish correction", exact: true })
      .click();
    await expect(
      ops.getByText("Correction published to the customer.", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect(
      page.getByText("Updated answer", { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Still need help?", { exact: true })
      .fill("I still need help, please ask a person to investigate.");
    await page
      .getByRole("button", { name: "Send to support team", exact: true })
      .click();
    await expect(
      page.getByText("Our support team is reviewing your enquiry.", {
        exact: true,
      }),
    ).toBeVisible();
    await ops.goto("/tickets?resolution=review");
    await expect(
      ops.getByRole("link", { name: "Refund policy timing", exact: false }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await admin.close();
    await customer.close();
  }
});

test("customer requesting human help goes directly to support", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/support");
  await page.getByLabel("Subject", { exact: true }).fill("I need an agent");
  await page
    .getByLabel("Your enquiry", { exact: true })
    .fill("Please connect me to a human agent about my account.");
  await page.getByRole("button", { name: "Get help", exact: true }).click();
  await expect(
    page.getByText("Our support team is reviewing your enquiry.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("The customer requested a person.", { exact: false }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../artifacts/customer-portal-mobile.png",
    fullPage: true,
  });
});
