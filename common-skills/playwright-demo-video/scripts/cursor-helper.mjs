// Reusable Playwright virtual cursor, click ripple, visual upload, and scene-segment timeline tracker.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export const CURSOR_INIT_SCRIPT = () => {
  if (window.__demoCursorInstalled) return;
  window.__demoCursorInstalled = true;

  const ensureDom = () => {
    if (!document.body) return null;
    let cursor = document.getElementById("__demo-cursor");
    if (!cursor) {
      const style = document.createElement("style");
      style.id = "__demo-cursor-style";
      style.textContent = `
        #__demo-cursor {
          position: fixed;
          left: -100px;
          top: -100px;
          width: 28px;
          height: 28px;
          pointer-events: none;
          z-index: 2147483647;
          transform: translate(-2px, -2px);
          transition: transform 80ms ease-out;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.45));
        }
        #__demo-cursor.clicking {
          transform: translate(-2px, -2px) scale(0.86);
        }
        .__demo-ripple {
          position: fixed;
          width: 14px;
          height: 14px;
          border-radius: 9999px;
          border: 3px solid #f97316;
          background: rgba(249, 115, 22, 0.25);
          pointer-events: none;
          z-index: 2147483646;
          transform: translate(-50%, -50%) scale(0.5);
          animation: __demo-ripple-anim 520ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes __demo-ripple-anim {
          0% { opacity: 0.95; transform: translate(-50%, -50%) scale(0.5); }
          100% { opacity: 0; transform: translate(-50%, -50%) scale(3.4); }
        }
        .__demo-spotlight {
          position: fixed;
          pointer-events: none;
          z-index: 2147483645;
          border: 2.5px solid #f97316;
          border-radius: 8px;
          background: rgba(249, 115, 22, 0.08);
          box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.18);
          transition: opacity 220ms ease-out;
        }
      `;
      document.head.appendChild(style);

      cursor = document.createElement("div");
      cursor.id = "__demo-cursor";
      cursor.innerHTML = `
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 2.5L22.5 14.2L13.8 15.8L10.2 24L4 2.5Z" fill="#111827" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round"/>
        </svg>
      `;
      document.body.appendChild(cursor);
    }
    return cursor;
  };

  window.addEventListener(
    "mousemove",
    (e) => {
      const c = ensureDom();
      if (c) {
        c.style.left = `${e.clientX}px`;
        c.style.top = `${e.clientY}px`;
      }
    },
    true,
  );

  window.addEventListener(
    "mousedown",
    (e) => {
      const c = ensureDom();
      if (c) {
        c.style.left = `${e.clientX}px`;
        c.style.top = `${e.clientY}px`;
        c.classList.add("clicking");
        setTimeout(() => c.classList.remove("clicking"), 150);
      }
      if (document.body) {
        const ripple = document.createElement("div");
        ripple.className = "__demo-ripple";
        ripple.style.left = `${e.clientX}px`;
        ripple.style.top = `${e.clientY}px`;
        document.body.appendChild(ripple);
        setTimeout(() => ripple.remove(), 560);
      }
    },
    true,
  );

  window.__demoHighlightRect = (rect, durationMs = 600) => {
    ensureDom();
    if (!document.body) return;
    const el = document.createElement("div");
    el.className = "__demo-spotlight";
    el.style.left = `${Math.max(0, rect.x - 4)}px`;
    el.style.top = `${Math.max(0, rect.y - 4)}px`;
    el.style.width = `${rect.width + 8}px`;
    el.style.height = `${rect.height + 8}px`;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 250);
    }, durationMs);
  };
};

export class DemoActor {
  constructor(page, trackName) {
    this.page = page;
    this.trackName = trackName;
    this.pos = { x: 200, y: 200 };
    this.t0 = Date.now();
  }

  nowSec() {
    return (Date.now() - this.t0) / 1000;
  }

  async moveTo(x, y, durationMs = 380) {
    const steps = Math.max(8, Math.round(durationMs / 16));
    const sx = this.pos.x;
    const sy = this.pos.y;
    const cx = (sx + x) / 2 + (Math.abs(y - sy) > 40 ? 18 : 0);
    const cy = (sy + y) / 2 - 12;

    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      const ease = 1 - Math.pow(1 - t, 3);
      const inv = 1 - ease;
      const nx = inv * inv * sx + 2 * inv * ease * cx + ease * ease * x;
      const ny = inv * inv * sy + 2 * inv * ease * cy + ease * ease * y;
      await this.page.mouse.move(nx, ny);
      await this.page.waitForTimeout(Math.max(8, Math.round(durationMs / steps)));
    }
    this.pos = { x, y };
  }

  async centerOf(locator) {
    let box = await locator.boundingBox().catch(() => null);
    const vp = this.page.viewportSize() || { width: 1280, height: 720 };
    const inView = box && box.y >= 20 && box.y + box.height <= vp.height - 20;
    if (!inView) {
      await locator.scrollIntoViewIfNeeded().catch(() => {});
      await this.page.waitForTimeout(100);
      box = await locator.boundingBox();
    }
    if (!box) throw new Error("Element has no boundingBox");
    return { x: box.x + box.width / 2, y: box.y + box.height / 2, box };
  }

  async humanClick(locator, { moveMs = 400, pauseBeforeMs = 140, pauseAfterMs = 260, highlight = true } = {}) {
    await locator.waitFor({ state: "visible", timeout: 15000 });
    const { x, y, box } = await this.centerOf(locator);
    await this.moveTo(x, y, moveMs);
    if (highlight) {
      await this.page.evaluate((r) => window.__demoHighlightRect?.(r, 420), box);
    }
    await this.page.waitForTimeout(pauseBeforeMs);
    await this.page.mouse.down();
    await this.page.waitForTimeout(70);
    await this.page.mouse.up();
    await this.page.waitForTimeout(pauseAfterMs);
  }

  async fastFill(locator, value, { moveMs = 220, pauseAfterMs = 120 } = {}) {
    await locator.waitFor({ state: "visible", timeout: 15000 });
    const { x, y } = await this.centerOf(locator);
    await this.moveTo(x, y, moveMs);
    await this.page.mouse.click(x, y);
    await locator.fill(value);
    await this.page.waitForTimeout(pauseAfterMs);
  }

  async fastSelect(locator, option, { moveMs = 220, pauseAfterMs = 140 } = {}) {
    await locator.waitFor({ state: "visible", timeout: 15000 });
    const { x, y, box } = await this.centerOf(locator);
    await this.moveTo(x, y, moveMs);
    await this.page.evaluate((r) => window.__demoHighlightRect?.(r, 320), box);
    await locator.selectOption(option);
    await this.page.waitForTimeout(pauseAfterMs);
  }

  async fastCheck(locator, { moveMs = 180, pauseAfterMs = 100 } = {}) {
    await locator.waitFor({ state: "visible", timeout: 15000 });
    const { x, y } = await this.centerOf(locator);
    await this.moveTo(x, y, moveMs);
    await locator.check();
    await this.page.waitForTimeout(pauseAfterMs);
  }

  /**
   * Visually demonstrate a file upload: move cursor to visible trigger/slot, highlight it,
   * skip ONLY the network upload wait via `tl.skipWait`, then dwell so thumbnail/status pops in.
   */
  async humanUpload(visualTarget, uploadFn, { tl = null, dwellAfterMs = 420 } = {}) {
    await visualTarget.scrollIntoViewIfNeeded().catch(() => {});
    const box = await visualTarget.boundingBox().catch(() => null);
    if (box) {
      await this.moveTo(box.x + Math.min(80, box.width / 2), box.y + Math.min(40, box.height / 2), 240);
      await this.page.evaluate((r) => window.__demoHighlightRect?.(r, 350), box);
      await this.dwell(150);
    }
    if (tl) {
      await tl.skipWait(this, uploadFn);
    } else {
      await uploadFn();
    }
    await this.dwell(dwellAfterMs);
  }

  async dwell(ms = 600) {
    await this.page.waitForTimeout(ms);
  }
}

export class TimelineRecorder {
  constructor() {
    this.scenes = [];
    this.current = null;
    this.activeSeg = null;
  }

  beginScene(id, { track = "desktop", title, badge = "", narration, titleCard = null, infoLines = null }) {
    if (this.current) this.endScene();
    this.current = { id, track, title, badge, narration, titleCard, infoLines, segments: [] };
    this.scenes.push(this.current);
  }

  startSegment(actor, speed = 1.0) {
    if (!this.current) throw new Error("No active scene");
    if (this.activeSeg) this.endSegment(actor);
    this.activeSeg = { start: actor.nowSec(), end: null, speed };
  }

  endSegment(actor) {
    if (!this.activeSeg) return;
    const end = actor.nowSec();
    if (end - this.activeSeg.start >= 0.08) {
      this.activeSeg.end = end;
      this.current.segments.push(this.activeSeg);
    }
    this.activeSeg = null;
  }

  async record(actor, fn, { speed = 1.0 } = {}) {
    this.startSegment(actor, speed);
    try {
      return await fn();
    } finally {
      this.endSegment(actor);
    }
  }

  async skipWait(actor, fn) {
    const wasActive = Boolean(this.activeSeg);
    const prevSpeed = this.activeSeg?.speed ?? 1.0;
    if (wasActive) this.endSegment(actor);
    try {
      return await fn();
    } finally {
      if (wasActive) this.startSegment(actor, prevSpeed);
    }
  }

  endScene() {
    if (this.activeSeg) {
      throw new Error(`Scene ${this.current?.id} ended with unclosed segment`);
    }
    this.current = null;
  }

  save(outPath, meta = {}) {
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, JSON.stringify({ meta, scenes: this.scenes }, null, 2), "utf8");
  }
}
