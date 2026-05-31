#!/usr/bin/env node
/**
 * Runtime smoke check for generated tech-doc HTML.
 *
 * Loads each HTML file in headless Chromium via Playwright, waits for
 * Mermaid (if present) to finish rendering, then asserts zero
 * `pageerror` and zero `console.error` events. Complements the
 * security/syntax gates by catching runtime failures they miss — e.g.
 * Mermaid `translate(undefined, NaN)` from `display:none` containers,
 * JS SyntaxError preventing handler binding, unhandled rejections.
 *
 * Usage:
 *   node check_runtime.mjs <project-root> <file.html> [file2.html ...]
 *
 *   <project-root> — directory containing node_modules/playwright
 *   <file.html>    — one or more HTML files to check
 *
 * Options (via env var):
 *   QA_ALLOW_CONSOLE — regex; matching console.error lines are ignored
 *                      (e.g. `^Failed to load resource:` for offline)
 *   QA_TIMEOUT_MS    — page load + mermaid-ready timeout (default 30000)
 *   QA_WAIT_MS       — extra wait after networkidle (default 1500)
 *   QA_VIEWPORT      — viewport size WxH (default 1280x900)
 *
 * Exit 0: all files clean.
 * Exit 1: at least one runtime error detected.
 * Exit 2: bad CLI args or cannot load playwright.
 */

import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("Usage: node check_runtime.mjs <project-root> <file.html> [...]");
    process.exit(2);
  }

  const projectRoot = path.resolve(args[0]);
  const files = args.slice(1);
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

  const allowRegex = process.env.QA_ALLOW_CONSOLE
    ? new RegExp(process.env.QA_ALLOW_CONSOLE)
    : null;
  const timeoutMs = Number(process.env.QA_TIMEOUT_MS ?? 30000);
  const extraWaitMs = Number(process.env.QA_WAIT_MS ?? 1500);
  const viewport = (() => {
    const raw = process.env.QA_VIEWPORT ?? "1280x900";
    const [w, h] = raw.split("x").map(Number);
    return { width: w || 1280, height: h || 900 };
  })();

  const browser = await playwright.chromium.launch({ headless: true });
  let totalIssues = 0;

  try {
    for (const filePath of files) {
      const resolved = path.resolve(filePath);
      const url = pathToFileURL(resolved).href;
      const ctx = await browser.newContext({ viewport });
      const page = await ctx.newPage();

      const events = [];
      page.on("pageerror", (e) => events.push({ kind: "pageerror", text: e.message }));
      page.on("console", (msg) => {
        if (msg.type() === "error") {
          events.push({ kind: "console.error", text: msg.text() });
        }
      });

      try {
        await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });
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
            events.push({
              kind: "mermaid-ready-timeout",
              text:
                "Not all <pre class=\"mermaid\"> reached data-processed=true within timeout",
            });
          }
        }
        await page.waitForTimeout(extraWaitMs);
      } catch (e) {
        events.push({ kind: "navigation", text: e.message });
      } finally {
        await ctx.close();
      }

      const significant = events.filter(
        (ev) => !allowRegex || !allowRegex.test(ev.text),
      );
      if (significant.length === 0) {
        console.log(`${resolved}: OK`);
      } else {
        console.error(`${resolved}: ${significant.length} runtime issue(s)`);
        for (const ev of significant) {
          console.error(`  [${ev.kind}] ${ev.text}`);
        }
        totalIssues += significant.length;
      }
    }
  } finally {
    await browser.close();
  }

  if (totalIssues > 0) {
    console.error(`\n${totalIssues} runtime issue(s) detected.`);
    process.exit(1);
  }
  console.log("All HTML files load without runtime errors.");
  process.exit(0);
}

main().catch((e) => {
  console.error("Unexpected error:", e);
  process.exit(3);
});
