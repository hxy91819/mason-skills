#!/usr/bin/env node
/**
 * Pre-validate Mermaid diagram syntax using mermaid.parse() in a JSDOM
 * context so the parser has real DOM APIs available.
 *
 * Usage: node check_mermaid_syntax.mjs <project-root> <file.html> [file2.html ...]
 *
 *   <project-root> — directory containing node_modules/mermaid and node_modules/jsdom
 *   <file.html>   — one or more HTML files to check
 *
 * Exit 0: all diagrams parse correctly.
 * Exit 1: parse error(s) found.
 */

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

async function extractBlocks(html) {
  const blocks = [];
  const re = /<pre\s+class="mermaid">([\s\S]*?)<\/pre>/gi;
  let match;
  while ((match = re.exec(html)) !== null) {
    blocks.push({ src: match[1].trim(), startOffset: match.index });
  }
  return blocks;
}

function lineAtOffset(html, offset) {
  return html.slice(0, offset).split("\n").length;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("Usage: node check_mermaid_syntax.mjs <project-root> <file.html> [...]");
    process.exit(2);
  }

  const projectRoot = path.resolve(args[0]);
  const files = args.slice(1);
  const require = createRequire(path.join(projectRoot, "package.json"));

  // Set up JSDOM context before loading mermaid
  let jsdom;
  try {
    jsdom = require("jsdom");
  } catch (e) {
    console.error(`Cannot load jsdom from: ${projectRoot}`);
    console.error(`  ${e.message}`);
    process.exit(2);
  }
  const dom = new jsdom.JSDOM("<!DOCTYPE html>");
  const { window } = dom;
  globalThis.window = window;
  globalThis.document = window.document;

  let mod;
  try {
    mod = require("mermaid");
  } catch (e) {
    console.error(`Cannot load mermaid from: ${projectRoot}`);
    console.error(`  ${e.message}`);
    process.exit(2);
  }

  const mermaid = mod.default ?? mod;
  mermaid.initialize({
    securityLevel: "sandbox",
    htmlLabels: false,
    flowchart: { htmlLabels: false },
    sequence: { htmlLabels: false },
  });

  let errors = 0;

  for (const filePath of files) {
    const resolved = path.resolve(filePath);
    let html;
    try {
      html = fs.readFileSync(resolved, "utf-8");
    } catch (e) {
      console.error(`${resolved}: cannot read — ${e.message}`);
      errors++;
      continue;
    }

    const blocks = await extractBlocks(html);
    if (blocks.length === 0) {
      console.error(`${resolved}: no <pre class="mermaid"> blocks found`);
      errors++;
      continue;
    }

    for (const block of blocks) {
      try {
        await mermaid.parse(block.src);
      } catch (e) {
        const line = lineAtOffset(html, block.startOffset);
        console.error(`${resolved}:${line}: [MERMAID_SYNTAX] Parse error`);
        const msg = (e.message ?? String(e))
          .split("\n")
          .map((l) => `  ${l}`)
          .join("\n");
        console.error(msg);
        errors++;
      }
    }
  }

  if (errors > 0) {
    console.error(`\n${errors} Mermaid syntax error(s) found.`);
    process.exit(1);
  }
  console.log("All Mermaid diagrams parse correctly.");
  process.exit(0);
}

main().catch((e) => {
  console.error("Unexpected error:", e);
  process.exit(3);
});
