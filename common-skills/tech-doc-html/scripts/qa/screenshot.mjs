#!/usr/bin/env node
/**
 * Take a screenshot of a tech-doc HTML page for visual review.
 *
 * Loads in headless Chromium via Playwright, waits for Mermaid (if
 * present) to finish rendering, then writes a PNG to disk. Intended
 * for the agent to inspect its own visual output during iterative
 * editing — not a go/no-go gate.
 *
 * Usage:
 *   node screenshot.mjs <project-root> <file.html> <out.png>
 *
 *   <project-root> — directory containing node_modules/playwright
 *   <file.html>    — HTML file to load
 *   <out.png>      — output image path
 *
 * Options (via env var):
 *   QA_SELECTOR   — CSS selector to screenshot (default: whole viewport)
 *   QA_VIEWPORT   — viewport size WxH (default 1280x900)
 *   QA_FULL_PAGE  — "1" to capture full scrollable page (default 0)
 *   QA_TIMEOUT_MS — page load + mermaid-ready timeout (default 30000)
 *   QA_WAIT_MS    — extra wait after networkidle (default 1500)
 *
 * Exit 0 on success, 1 on selector missing / write failure,
 * 2 on bad CLI args or cannot load playwright.
 */

import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 3) {
    console.error(
      "Usage: node screenshot.mjs <project-root> <file.html> <out.png>",
    );
    process.exit(2);
  }

  const projectRoot = path.resolve(args[0]);
  const filePath = path.resolve(args[1]);
  const outPath = path.resolve(args[2]);
  const require = createRequire(path.join(projectRoot, "package.json"));

  let playwright;
  try {
    playwright = require("playwright");
  } catch (e) {
    console.error(`Cannot load playwright from: ${projectRoot}`);
    console.error(`  ${e.message}`);
    console.error(`  Install with: cd ${projectRoot} && npm i playwright`);
    process.exit(2);
  }

  const viewport = (() => {
    const raw = process.env.QA_VIEWPORT ?? "1280x900";
    const [w, h] = raw.split("x").map(Number);
    return { width: w || 1280, height: h || 900 };
  })();
  const fullPage = process.env.QA_FULL_PAGE === "1";
  const timeoutMs = Number(process.env.QA_TIMEOUT_MS ?? 30000);
  const extraWaitMs = Number(process.env.QA_WAIT_MS ?? 1500);
  const selector = process.env.QA_SELECTOR;

  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const ctx = await browser.newContext({ viewport });
    const page = await ctx.newPage();
    await page.goto(pathToFileURL(filePath).href, {
      waitUntil: "networkidle",
      timeout: timeoutMs,
    });
    const hasMermaid = await page.evaluate(
      () => !!document.querySelector("pre.mermaid"),
    );
    if (hasMermaid) {
      try {
        await page.waitForFunction(
          () =>
            Array.from(document.querySelectorAll("pre.mermaid")).every(
              (el) => el.getAttribute("data-processed") === "true",
            ),
          { timeout: timeoutMs },
        );
      } catch {
        // proceed anyway; partial render still useful for visual review
      }
    }
    await page.waitForTimeout(extraWaitMs);
    if (selector) {
      const elt = await page.$(selector);
      if (!elt) {
        console.error(`Selector not found: ${selector}`);
        process.exit(1);
      }
      await elt.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      await elt.screenshot({ path: outPath });
    } else {
      await page.screenshot({ path: outPath, fullPage });
    }
  } finally {
    await browser.close();
  }
  console.log(`Saved screenshot: ${outPath}`);
}

main().catch((e) => {
  console.error("Unexpected error:", e);
  process.exit(3);
});
