#!/usr/bin/env node
/**
 * mermaid 批量校验 worker。
 *
 * 输入：argv[2] 指向 JSON 文件 { cliDir, perBlockTimeoutMs, blocks: [{ key, domId, content }] }
 * 输出：stdout 单个 JSON { status, results: [{ key, valid, error?, timedOut? }] }
 *
 * 校验方式仍然是驱动真实渲染器（mermaid.render），而不是只做语法解析（mermaid.parse）。
 * 两者不等价：mermaid.parse 只覆盖解析阶段，渲染/布局阶段抛出的错误它看不到，
 * 例如 gantt 里的非法日期 "notadate" 能通过 parse 却渲染失败。用 render 才能对齐
 * "这张图在文档里到底能不能画出来" 这个真正要回答的问题。
 *
 * 整批共用一个浏览器会话，而不是每块起一个进程：单块启动 Chromium 的固定开销约 1.7s，
 * 共用会话后每块边际成本约 12ms，60 块从约 100s 降到约 2s。
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
  fail("用法: mermaid-worker.mjs <input.json>");
}

const input = JSON.parse(readFileSync(INPUT_PATH, "utf8"));
const cliDir = input.cliDir;
const perBlockTimeoutMs = input.perBlockTimeoutMs ?? 20000;
// 浏览器启动等固定开销，冷启动或慢机器上需要调高。
const sessionOverheadMs = input.sessionOverheadMs ?? 15000;
const allBlocks = input.blocks ?? [];

const requireFromCli = createRequire(path.join(cliDir, "package.json"));

/**
 * 定位 mermaid 运行时 bundle。
 *
 * mermaid-cli 的 Node API 和内部目录结构都不在 semver 保护范围内，所以这里按候选路径
 * 依次探测，并在全部落空时显式报错，不做静默降级——否则会退化成"校验永远通过"。
 */
function resolveMermaidBundle() {
  const candidates = [];
  try {
    const pkg = requireFromCli.resolve("mermaid/package.json");
    candidates.push(path.join(path.dirname(pkg), "dist", "mermaid.min.js"));
  } catch {
    // mermaid 的 exports 字段可能不暴露 package.json，交给下面的兜底路径
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
    `未能在 mermaid-cli 安装目录下定位 mermaid 运行时 (${cliDir})。` +
      "请重新安装 @mermaid-js/mermaid-cli 后重试。",
  );
}

let puppeteer;
try {
  puppeteer = requireFromCli("puppeteer");
} catch (e) {
  fail(`未能从 mermaid-cli 加载 puppeteer: ${e?.message ?? e}`);
}

// root 下 Chromium 必须关掉 sandbox 才能启动，否则报
// "Running as root without --no-sandbox is not supported"。
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

/** 会话搭建阶段的失败，代表环境本身有问题，不该按"某个块卡死"来降级重试。 */
class SessionSetupError extends Error {}

/**
 * 在一个浏览器会话里顺序校验 blocks。
 *
 * 结果通过 exposeFunction 逐块回传，而不是等 evaluate 整体返回：页面被某个块卡死时，
 * 已完成的结果不会一起丢失，外层因此能知道卡在哪一块并从下一块继续。
 */
async function runSession(blocks, results) {
  let browser;
  try {
    browser = await puppeteer.launch({ args: launchArgs });
  } catch (e) {
    throw new SessionSetupError(`浏览器启动失败: ${e?.message ?? e}`);
  }

  let inFlight = null;

  try {
    let page;
    try {
      page = await browser.newPage();
      await page.setContent("<!DOCTYPE html><html><body></body></html>");
      await page.addScriptTag({ path: bundlePath });
      await page.evaluate(() => {
        // suppressErrorRendering 让 render 在出错时抛异常，而不是画一张"错误图"当作成功。
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
      throw new SessionSetupError(`mermaid 运行时注入失败: ${e?.message ?? e}`);
    }

    // 页内的 Promise.race 只能拦住异步等待，拦不住同步布局把 JS 线程占死——定时器回调
    // 排在同步任务之后根本没机会执行。所以真正兜底同步卡死的是这条 Node 侧的整轮预算。
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
                setTimeout(() => reject(new Error(`渲染超时 (${blockTimeoutMs}ms)`)), blockTimeoutMs);
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
              // mermaid 会为每次 render 留下临时容器，逐块清掉避免大文档下 DOM 膨胀。
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
      `整轮校验超时 (${budgetMs}ms)`,
    );
  } catch (e) {
    // 把"卡在哪一块"随异常带出去，否则外层无从判断该把哪个块判定为超时。
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
  // 每轮至少消化一个块，轮数上限取块数即可覆盖"每块都卡死"的最坏情况。
  let roundsLeft = allBlocks.length + 1;

  while (pending.length > 0 && roundsLeft > 0) {
    roundsLeft -= 1;
    let inFlight = null;
    let lastError = null;
    try {
      inFlight = await runSession(pending, results);
    } catch (e) {
      // 环境问题重试多少轮都是同样结果，直接失败并给出可操作的原因。
      if (e instanceof SessionSetupError) {
        fail(e.message);
      }
      // 整轮超时等运行期异常不终止流程，交给下面的推进逻辑标记责任块后继续。
      lastError = e;
      inFlight = e?.inFlight ?? null;
    }

    const remaining = pending.filter((b) => !results.has(b.key));
    if (remaining.length === pending.length) {
      // 本轮零进展：把卡住的那一块（拿不到就退化成队首）判定为超时，保证下一轮能往前走。
      const culprit = remaining.find((b) => b.key === inFlight) ?? remaining[0];
      results.set(culprit.key, {
        key: culprit.key,
        valid: false,
        timedOut: true,
        error: lastError
          ? `校验中断，该块被判定为责任块: ${lastError.message}`
          : `校验超时或渲染进程崩溃 (${perBlockTimeoutMs}ms)`,
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
          error: "worker 未返回该块的校验结果",
        },
    ),
  });
}

main().catch((e) => fail(`worker 异常退出: ${e?.stack ?? e}`));
