import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
if (!process.env.ADMIN_PASSWORD) throw new Error("Set ADMIN_PASSWORD before capturing a preview.");
const output = new URL("../../artifacts/", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(process.env.PREVIEW_URL || "http://127.0.0.1:8000");
await page.getByLabel("Username", { exact: true }).fill(process.env.ADMIN_USERNAME || "admin");
await page
  .getByLabel("Password", { exact: true })
  .fill(process.env.ADMIN_PASSWORD);
await page.getByRole("button", { name: "Sign in to workspace" }).click();
await page
  .getByRole("heading", { name: "A clearer view of your queue." })
  .waitFor();
await page.screenshot({
  path: fileURLToPath(new URL("dashboard.png", output)),
  fullPage: true,
});
await page
  .getByRole("navigation")
  .getByRole("link", { name: "All tickets", exact: false })
  .click();
await page.getByRole("heading", { name: "All tickets", exact: true }).waitFor();
await page.screenshot({
  path: fileURLToPath(new URL("tickets.png", output)),
  fullPage: true,
});
await page.getByRole("link", { name: "Knowledge base", exact: true }).click();
await page.getByLabel("Article title").waitFor();
await page.screenshot({
  path: fileURLToPath(new URL("knowledge.png", output)),
  fullPage: true,
});
await page.getByRole("link", { name: "Overview", exact: true }).click();
await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({
  path: fileURLToPath(new URL("mobile.png", output)),
  fullPage: true,
});
const overflow = await page.evaluate(
  () => document.documentElement.scrollWidth > innerWidth + 1,
);
await browser.close();
if (errors.length || overflow)
  throw new Error(JSON.stringify({ errors, mobileOverflow: overflow }));
console.log(
  "Desktop and mobile previews captured; no page errors or page-level mobile overflow.",
);
