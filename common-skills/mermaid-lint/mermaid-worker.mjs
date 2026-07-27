#!/usr/bin/env node
/**
 * Batch mermaid validation worker.
 *
 * Input:  argv[2] points at a JSON file { cliDir, perBlockTimeoutMs, blocks: [{ key, domId, content }] }
 * Output: a single JSON object on stdout { status, results: [{ key, valid, error?, timedOut? }] }
 *
 * Validation drives the real renderer (mermaid.render) rather than only parsing
 * (mermaid.parse). The two are not equivalent: parse covers the parse phase only and
 * misses anything thrown while rendering or laying out, such as the invalid gantt date
 * "notadate", which parses cleanly but fails to render. Rendering is what answers the
 * question that actually matters — will this diagram display at all.
 *
 * The whole batch shares one browser session instead of spawning a process per block.
 * Launching Chromium costs roughly 1.7s per block; sharing a session brings the
 * marginal cost down to about 12ms, taking 60 blocks from ~100s to ~2s.
 */

import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const INPUT_PATH = process.argv[2];

function emit(payload) {
  process.stdout.write(JSON.stringify(payload));
}

function fail(message) {
  emit({ status: "worker_error", error: message, results: [] });
  process.exit(2);
}

if (!INPUT_PATH) {
  fail("Usage: mermaid-worker.mjs <input.json>");
}

const input = JSON.parse(readFileSync(INPUT_PATH, "utf8"));
const cliDir = input.cliDir;
const perBlockTimeoutMs = input.perBlockTimeoutMs ?? 20000;
// Fixed cost such as browser startup; raise it for cold starts or slow machines.
const sessionOverheadMs = input.sessionOverheadMs ?? 15000;
const allBlocks = input.blocks ?? [];

const requireFromCli = createRequire(path.join(cliDir, "package.json"));

/**
 * Locate the mermaid runtime bundle.
 *
 * Neither the mermaid-cli Node API nor its internal directory layout is covered by
 * semver, so probe the candidate paths in order and fail loudly when all of them miss.
 * Degrading silently here would turn the linter into one that always passes.
 */
function resolveMermaidBundle() {
  const candidates = [];
  try {
    const pkg = requireFromCli.resolve("mermaid/package.json");
    candidates.push(path.join(path.dirname(pkg), "dist", "mermaid.min.js"));
  } catch {
    // mermaid may not expose package.json via its exports field; fall through below.
  }
  candidates.push(path.join(cliDir, "node_modules", "mermaid", "dist", "mermaid.min.js"));
  candidates.push(path.join(cliDir, "..", "..", "mermaid", "dist", "mermaid.min.js"));

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

const bundlePath = resolveMermaidBundle();
if (!bundlePath) {
  fail(
    `Could not locate the mermaid runtime under the mermaid-cli install directory (${cliDir}). ` +
      "Reinstall @mermaid-js/mermaid-cli and try again.",
  );
}

let puppeteer;
try {
  puppeteer = requireFromCli("puppeteer");
} catch (e) {
  fail(`Could not load puppeteer from mermaid-cli: ${e?.message ?? e}`);
}

// As root, Chromium refuses to start unless the sandbox is disabled, reporting
// "Running as root without --no-sandbox is not supported".
const launchArgs =
  typeof process.getuid === "function" && process.getuid() === 0
    ? ["--no-sandbox", "--disable-setuid-sandbox"]
    : [];

function withTimeout(promise, ms, label) {
  let timer;
  const guard = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(label)), ms);
  });
  return Promise.race([promise, guard]).finally(() => clearTimeout(timer));
}

/** A setup failure means the environment is broken, not that one block hung, so it must not be retried. */
class SessionSetupError extends Error {}

/**
 * Validate blocks sequentially inside a single browser session.
 *
 * Results are reported back per block through exposeFunction rather than waiting for
 * evaluate to return as a whole. If one block hangs the page, the results already
 * collected survive, which lets the caller see which block stalled and resume after it.
 */
async function runSession(blocks, results) {
  let browser;
  try {
    browser = await puppeteer.launch({ args: launchArgs });
  } catch (e) {
    throw new SessionSetupError(`Browser launch failed: ${e?.message ?? e}`);
  }

  let inFlight = null;

  try {
    let page;
    try {
      page = await browser.newPage();
      await page.setContent("<!DOCTYPE html><html><body></body></html>");
      await page.addScriptTag({ path: bundlePath });
      await page.evaluate(() => {
        // suppressErrorRendering makes render throw instead of drawing an error
        // diagram that would otherwise be mistaken for success.
        window.mermaid.initialize({ startOnLoad: false, suppressErrorRendering: true });
      });
      await page.exposeFunction("lintStarted", (key) => {
        inFlight = key;
      });
      await page.exposeFunction("lintDone", (result) => {
        results.set(result.key, result);
        inFlight = null;
      });
    } catch (e) {
      throw new SessionSetupError(`Failed to inject the mermaid runtime: ${e?.message ?? e}`);
    }

    // The in-page Promise.race only guards against async waits. It cannot stop a
    // synchronous layout from monopolising the JS thread, because the timer callback is
    // queued behind that synchronous work and never gets to run. This Node-side budget
    // is therefore the real backstop for a synchronous hang.
    const budgetMs = perBlockTimeoutMs * blocks.length + sessionOverheadMs;

    await withTimeout(
      page.evaluate(
        async (pageBlocks, blockTimeoutMs) => {
          for (const block of pageBlocks) {
            await window.lintStarted(block.key);
            let outcome;
            try {
              const rendering = window.mermaid.render(block.domId, block.content);
              const guard = new Promise((_, reject) => {
                setTimeout(() => reject(new Error(`Render timed out (${blockTimeoutMs}ms)`)), blockTimeoutMs);
              });
              await Promise.race([rendering, guard]);
              outcome = { key: block.key, valid: true };
            } catch (e) {
              outcome = {
                key: block.key,
                valid: false,
                error: String(e?.message ?? e),
              };
            } finally {
              // mermaid leaves a temporary container behind on every render; clear it
              // per block so the DOM does not balloon on large documents.
              document
                .querySelectorAll(`#${block.domId}, #d${block.domId}`)
                .forEach((node) => node.remove());
            }
            await window.lintDone(outcome);
          }
        },
        blocks,
        perBlockTimeoutMs,
      ),
      budgetMs,
      `Session-wide validation timed out (${budgetMs}ms)`,
    );
  } catch (e) {
    // Carry "which block stalled" out with the error; without it the caller cannot tell
    // which block to mark as timed out.
    e.inFlight = inFlight;
    throw e;
  } finally {
    await browser.close().catch(() => {});
  }

  return inFlight;
}

async function main() {
  const results = new Map();
  let pending = allBlocks;
  // Each round retires at least one block, so a cap of one round per block covers the
  // worst case where every single block hangs.
  let roundsLeft = allBlocks.length + 1;

  while (pending.length > 0 && roundsLeft > 0) {
    roundsLeft -= 1;
    let inFlight = null;
    let lastError = null;
    try {
      inFlight = await runSession(pending, results);
    } catch (e) {
      // Retrying an environment problem yields the same result every time, so fail
      // immediately with an actionable reason.
      if (e instanceof SessionSetupError) {
        fail(e.message);
      }
      // Runtime failures such as a session timeout must not abort the run; the progress
      // logic below attributes the stall to a block and carries on.
      lastError = e;
      inFlight = e?.inFlight ?? null;
    }

    const remaining = pending.filter((b) => !results.has(b.key));
    if (remaining.length === pending.length) {
      // No progress this round: mark the stalled block as timed out, falling back to the
      // head of the queue when it cannot be identified, so the next round can advance.
      const culprit = remaining.find((b) => b.key === inFlight) ?? remaining[0];
      results.set(culprit.key, {
        key: culprit.key,
        valid: false,
        timedOut: true,
        error: lastError
          ? `Validation aborted; this block was held responsible: ${lastError.message}`
          : `Validation timed out or the render process crashed (${perBlockTimeoutMs}ms)`,
      });
      pending = remaining.filter((b) => b.key !== culprit.key);
    } else {
      pending = remaining;
    }
  }

  emit({
    status: "ok",
    results: allBlocks.map(
      (b) =>
        results.get(b.key) ?? {
          key: b.key,
          valid: false,
          error: "Worker returned no result for this block",
        },
    ),
  });
}

main().catch((e) => fail(`Worker exited abnormally: ${e?.stack ?? e}`));
