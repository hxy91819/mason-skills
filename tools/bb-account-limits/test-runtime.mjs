import { createRequire } from "node:module";

// SDK 0.4.47 的 Node bundle 仍含 CJS require；测试补齐 host 的模块加载环境。
globalThis.require = createRequire(import.meta.url);
