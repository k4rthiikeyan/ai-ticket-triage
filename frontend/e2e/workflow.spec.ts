import { test, expect } from "@playwright/test";

test("separate demo browsers cannot see each other's ticket", async ({
  browser,
}) => {
  const first = await browser.newContext();
  const second = await browser.newContext();
  try {
    const one = await first.newPage();
    const two = await second.newPage();
    for (const page of [one, two]) {
      await page.goto("/");
      await page
        .getByRole("button", { name: "Try the demo", exact: true })
        .click();
      await expect(
        page.getByText("Your tickets and knowledge are isolated", {
          exact: false,
        }),
      ).toBeVisible();
    }
    await one.getByRole("button", { name: "New ticket", exact: true }).click();
    await one
      .getByLabel("Subject", { exact: true })
      .fill("Visitor isolation browser check");
    await one
      .getByLabel("Customer request")
      .fill("This ticket belongs only to the first browser visitor.");
    await one
      .getByRole("button", { name: "Create ticket", exact: true })
      .click();
    await expect(
      one.getByRole("heading", { name: "Customer request", exact: true }),
    ).toBeVisible();
    const privateUrl = one.url();
    await two.goto(privateUrl);
    await expect(two.getByRole("alert")).toContainText("Ticket not found");
    await one.reload();
    await expect(
      one.getByRole("heading", { name: "Customer request", exact: true }),
    ).toBeVisible();
  } finally {
    await first.close();
    await second.close();
  }
});

test("public credentials allow a demo visit with administrator settings protected", async ({
  page,
}) => {
  await page.goto("/");
  const demo = page.getByRole("region", { name: "Public demo access" });
  await expect(demo).toContainText("demo");
  await expect(demo).toContainText("try-triage");
  await page.getByRole("button", { name: "Try the demo", exact: true }).click();
  await expect(page.getByText("Demo visitor", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Add category" }),
  ).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add queue" })).toBeDisabled();
  await page.getByRole("link", { name: "All tickets", exact: false }).click();
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("A visitor request " + Date.now());
  await page
    .getByLabel("Customer request")
    .fill("This is a request typed by a demo visitor to try the workspace.");
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Customer request", exact: true }),
  ).toBeVisible();
});

test("operator creates a ticket, compares rules, confirms, notes, resolves, and sees audit history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "A clearer view of your queue." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Browser test duplicate charge " + Date.now());
  await page
    .getByLabel("Customer request")
    .fill(
      "A duplicate charge appeared on my subscription. The product still works normally.",
    );
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Customer request", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Compare rules" }).click();
  await expect(
    page.getByText("Matched keywords:", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dismiss job notification" }).click();
  await page.getByLabel("Final priority").selectOption("high");
  await page.getByLabel("Decision note").fill("Operator clarified the impact.");
  await page
    .getByRole("button", { name: "Confirm decision", exact: true })
    .click();
  await expect(
    page.getByText("Overridden decision", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Internal note", { exact: true })
    .fill("Keep this internal context for the team.");
  await page.getByRole("button", { name: "Add note", exact: false }).click();
  await expect(
    page.getByText("Keep this internal context for the team.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mark resolved" }).click();
  await expect(
    page.getByRole("button", { name: "Reopen ticket" }),
  ).toBeVisible();
  await page.getByText("Audit trail", { exact: false }).click();
  await expect(
    page.getByText("decision overridden", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "All tickets", exact: false }).click();
  await page.getByLabel("Search tickets").fill("Browser test duplicate charge");
  await expect(page.getByRole("table")).toContainText(
    "Browser test duplicate charge",
  );
});
test("knowledge editing marks the index stale and exposes revisions", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await page.getByRole("link", { name: "Knowledge base", exact: true }).click();
  await page.getByRole("button", { name: "New article", exact: true }).click();
  await page
    .getByLabel("Article title")
    .fill("Browser test support article " + Date.now());
  await page
    .getByLabel("Article content")
    .fill(
      "A synthetic guide for routine billing requests. These requests have normal priority and belong to Billing.",
    );
  await page.getByRole("button", { name: "Save article" }).click();
  await expect(
    page.getByText(
      "Article saved. Rebuild the index to use these changes in RAG.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "View article revision history" })
    .click();
  await expect(
    page.getByText("Version 1", { exact: false }).first(),
  ).toBeVisible();
});
test("mocked RAG retrieves cited evidence, confirms it, and rejects stale knowledge", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Sign in to workspace" }).click();
  await page.getByRole("link", { name: "Knowledge base", exact: true }).click();
  await page.getByRole("button", { name: "New article", exact: true }).click();
  await page.getByLabel("Use as urgency policy").check();
  await page.getByLabel("Article title").fill("User entered urgency policy");
  await page
    .getByLabel("Article content")
    .fill(
      "Routine billing requests have normal priority. Service outages affecting all users have urgent priority.",
    );
  await page.getByRole("button", { name: "Save article" }).click();
  await expect(
    page.getByText(
      "Article saved. Rebuild the index to use these changes in RAG.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rebuild index" }).click();
  await expect(
    page.getByText("Knowledge index is up to date", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Search question")
    .fill("Help with duplicate payment charges");
  await page
    .getByRole("button", { name: "Search knowledge", exact: true })
    .click();
  await expect(page.locator(".search-result")).toContainText(
    "Duplicate charges belong to Billing.",
  );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "All tickets", exact: false })
    .click();
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Mocked RAG browser duplicate charge " + Date.now());
  await page
    .getByLabel("Customer request")
    .fill(
      "There is a duplicate charge on my subscription. The product still works normally.",
    );
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await page.getByRole("button", { name: "Run triage", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Supporting evidence" }),
  ).toBeVisible();
  await expect(
    page.getByText("82% evidence support", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator("blockquote").first()).toContainText(
    "Duplicate charges belong to Billing.",
  );
  await page
    .getByRole("button", { name: "Confirm decision", exact: true })
    .click();
  await expect(
    page.getByText("Accepted decision", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Knowledge base", exact: true }).click();
  await page
    .getByLabel("Article content")
    .fill(
      "Shared urgency policy changed for browser testing. Routine requests need normal priority and must be reviewed by an operator.",
    );
  await page.getByRole("button", { name: "Save article" }).click();
  await expect(
    page.getByText("Changes are waiting to be indexed", { exact: true }),
  ).toBeVisible();
});
