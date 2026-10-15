/** Scoped to this panel; every color follows BB's active palette. */
export const panelStyles = `
.limits-panel {
  --limits-line: color-mix(in srgb, var(--border) 75%, var(--card));
  --limits-soft: color-mix(in srgb, var(--muted) 35%, var(--card));
  --limits-hover: color-mix(in srgb, var(--primary) 3%, var(--card));
  --limits-fill: color-mix(in srgb, var(--primary) 85%, var(--foreground));
  --limits-danger-text: color-mix(in srgb, var(--destructive) 85%, var(--foreground));
  height: 100%; overflow: auto; container: limits / inline-size;
  color: var(--foreground); background: var(--background);
  font-size: 13px; line-height: 1.5;
}
.limits-panel *, .limits-panel *::before, .limits-panel *::after { box-sizing: border-box; }
.limits-panel button { font: inherit; cursor: pointer; }
.limits-panel button:disabled { cursor: wait; opacity: .5; }
.limits-panel button:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
.limits-panel ul { list-style: none; margin: 0; padding: 0; }
.limits-panel p, .limits-panel h1, .limits-panel h2, .limits-panel h3 { margin: 0; }
.limits-panel .limits-shell { max-width: 1280px; margin: 0 auto; padding: 28px 28px 48px; }
.limits-panel .limits-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 4px 0 24px; }
.limits-panel .limits-title-wrap { display: flex; align-items: center; gap: 14px; min-width: 0; }
.limits-panel .limits-emblem { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 14px; color: var(--primary); background: color-mix(in srgb, var(--primary) 9%, var(--background)); border: 1px solid color-mix(in srgb, var(--primary) 12%, transparent); }
.limits-panel .limits-emblem .limits-icon { width: 22px; height: 22px; }
.limits-panel .limits-title { font-size: 25px; font-weight: 650; letter-spacing: -.045em; line-height: 1.25; }
.limits-panel .limits-subtitle { color: var(--muted-foreground); font-size: 12px; margin-top: 5px; }
.limits-panel .limits-overview { display: flex; gap: 28px; font-variant-numeric: tabular-nums; }
.limits-panel .limits-stat { display: grid; grid-template-columns: auto auto; align-items: baseline; gap: 8px; }
.limits-panel .limits-stat-number { font-size: 26px; font-weight: 550; letter-spacing: -.055em; line-height: 1; }
.limits-panel .limits-stat-label { font-size: 11px; color: var(--muted-foreground); white-space: nowrap; }
.limits-panel .limits-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 0; margin-bottom: 12px; border-top: 1px solid var(--limits-line); position: sticky; top: 0; z-index: 2; background: color-mix(in srgb, var(--background) 94%, transparent); backdrop-filter: blur(12px); }
.limits-panel .limits-toolbar-end { display: flex; align-items: center; gap: 12px; }
.limits-panel .limits-segments { display: flex; gap: 3px; padding: 3px; border-radius: 10px; background: var(--limits-soft); border: 1px solid var(--limits-line); }
.limits-panel .limits-segment { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 6px 12px; border-radius: 7px; border: 1px solid transparent; color: var(--muted-foreground); background: transparent; font-size: 12px; white-space: nowrap; transition: background .15s, color .15s, box-shadow .15s; }
.limits-panel .limits-segment:hover { color: var(--foreground); }
.limits-panel .limits-segment[aria-pressed=true] { color: var(--foreground); background: var(--card); border-color: var(--limits-line); box-shadow: 0 1px 3px color-mix(in srgb, var(--foreground) 5%, transparent); font-weight: 600; }
.limits-panel .limits-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 8px 12px; background: var(--card); border: 1px solid var(--limits-line); border-radius: 9px; color: var(--foreground); font-size: 12px; transition: border-color .15s, background .15s; white-space: nowrap; }
.limits-panel .limits-button:hover:enabled { border-color: color-mix(in srgb, var(--primary) 40%, var(--border)); background: var(--limits-hover); }
.limits-panel .limits-icon { width: 15px; height: 15px; flex-shrink: 0; }
.limits-panel .limits-icon--spin { animation: limits-spin 1.3s linear infinite; }
.limits-panel .limits-source-section + .limits-source-section { margin-top: 24px; }
.limits-panel .limits-source-label { display: flex; align-items: center; gap: 9px; font-size: 11px; font-weight: 550; color: var(--muted-foreground); margin-bottom: 10px; }
.limits-panel .limits-source-label::after { content: ''; flex: 1; height: 1px; background: var(--limits-line); }
.limits-panel .limits-provider { border: 1px solid var(--limits-line); border-radius: 16px; overflow: hidden; background: var(--card); box-shadow: 0 3px 12px color-mix(in srgb, var(--foreground) 2%, transparent); margin-bottom: 16px; }
.limits-panel .limits-provider-head { display: flex; align-items: center; gap: 12px; padding: 17px 20px; border-bottom: 1px solid var(--limits-line); background: linear-gradient(110deg, color-mix(in srgb, var(--primary) 3%, var(--card)), var(--card) 65%); }
.limits-panel .limits-provider-mark { display: grid; place-items: center; flex-shrink: 0; width: 34px; height: 34px; color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--card)); border: 1px solid color-mix(in srgb, var(--primary) 10%, var(--card)); border-radius: 11px; }
.limits-panel .limits-provider-mark--claude { color: var(--foreground); background: var(--limits-soft); border-color: var(--limits-line); }
.limits-panel .limits-provider-mark--codex { color: var(--card); background: var(--foreground); border-color: var(--foreground); }
.limits-panel .limits-mark-icon { width: 19px; height: 19px; }
.limits-panel .limits-mark-letter { font-size: 20px; font-weight: 600; line-height: 1; }
.limits-panel .limits-provider-title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; }
.limits-panel .limits-provider-name { font-size: 15px; font-weight: 650; letter-spacing: -.02em; min-width: 0; overflow-wrap: anywhere; }
.limits-panel .limits-source-badge { font-size: 10px; color: var(--muted-foreground); border: 1px solid var(--limits-line); padding: 1px 6px; border-radius: 5px; font-weight: 450; }
.limits-panel .limits-provider-count { font-size: 11px; font-variant-numeric: tabular-nums; color: var(--muted-foreground); }
.limits-panel .limits-provider-actions { margin-left: auto; display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
.limits-panel .limits-updated { color: var(--muted-foreground); font-size: 11px; }
.limits-panel .limits-refresh { width: 30px; height: 30px; padding: 0; border-color: transparent; background: transparent; }
.limits-panel .limits-provider-body { padding: 0 20px; }
.limits-panel .limits-account { display: grid; grid-template-columns: minmax(160px, .85fr) minmax(0, 2fr); gap: 24px; padding: 16px 0; align-items: start; border-bottom: 1px solid var(--limits-line); }
.limits-panel .limits-account:last-child { border-bottom: 0; }
.limits-panel .limits-account:hover { background: var(--limits-hover); box-shadow: 12px 0 var(--limits-hover), -12px 0 var(--limits-hover); }
.limits-panel .limits-identity { display: flex; align-items: start; gap: 10px; min-width: 0; padding-top: 2px; }
.limits-panel .limits-account-index { font-size: 10px; padding-top: 2px; color: var(--muted-foreground); opacity: .65; font-variant-numeric: tabular-nums; }
.limits-panel .limits-identity-text { min-width: 0; }
.limits-panel .limits-account-name { font-size: 13px; line-height: 1.6; font-weight: 550; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.limits-panel .limits-account-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; color: var(--muted-foreground); font-size: 11px; margin-top: 5px; }
.limits-panel .limits-account-meta:empty { display: none; }
.limits-panel .limits-plan { border-radius: 4px; padding: 1px 5px; background: var(--limits-soft); max-width: 100%; overflow-wrap: anywhere; }
.limits-panel .limits-meters { display: grid; grid-template-columns: repeat(var(--quota-columns), minmax(0, 1fr)); gap: 12px 24px; min-width: 0; }
.limits-panel .limits-meter { min-width: 0; }
.limits-panel .limits-meter-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 7px; }
.limits-panel .limits-meter-title { display: flex; align-items: center; flex-wrap: wrap; gap: 5px 7px; min-width: 0; }
.limits-panel .limits-meter-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: var(--muted-foreground); }
.limits-panel .limits-pace { display: inline-flex; flex-shrink: 0; padding: 1px 5px; border-radius: 4px; border: 1px solid var(--limits-line); color: var(--muted-foreground); background: var(--limits-soft); font-size: 10px; line-height: 1.5; font-weight: 500; }
.limits-panel .limits-pace[data-level=generous] { color: color-mix(in srgb, var(--primary) 60%, var(--foreground)); border-color: color-mix(in srgb, var(--primary) 20%, var(--card)); background: color-mix(in srgb, var(--primary) 7%, var(--card)); }
.limits-panel .limits-pace[data-level=conserve], .limits-panel .limits-pace[data-level=exhausted] { color: var(--limits-danger-text); border-color: color-mix(in srgb, var(--destructive) 20%, var(--card)); background: color-mix(in srgb, var(--destructive) 5%, var(--card)); }
.limits-panel .limits-pace[data-level=unknown] { border-style: dashed; background: transparent; }
.limits-panel .limits-meter-number { font-size: 17px; font-weight: 550; letter-spacing: -.04em; line-height: 1.1; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.limits-panel .limits-meter-track { height: 4px; overflow: hidden; border-radius: 9px; background: color-mix(in srgb, var(--muted) 70%, var(--card)); }
.limits-panel .limits-meter-fill { height: 100%; border-radius: inherit; background: var(--limits-fill); transition: width .3s ease; }
.limits-panel .limits-meter[data-depleted] .limits-meter-number { color: var(--limits-danger-text); }
.limits-panel .limits-meter[data-depleted] .limits-meter-fill { background: var(--destructive); }
.limits-panel .limits-meter-track--recovery { display: flex; height: 6px; }
.limits-panel .limits-recovery-segment { display: block; flex: none; height: 100%; box-shadow: inset -1px 0 var(--card); background: color-mix(in srgb, var(--limits-fill) var(--recovery-strength), var(--card)); }
.limits-panel .limits-recovery-segment--unresolved { background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--limits-fill) 40%, var(--card)) 0 3px, color-mix(in srgb, var(--limits-fill) 12%, var(--card)) 3px 6px); }
.limits-panel .limits-meter[data-depleted] .limits-meter-track--recovery { --limits-fill: var(--destructive); }
.limits-panel .limits-recovery-legend { display: flex; align-items: start; gap: 8px; color: var(--muted-foreground); font-size: 11px; line-height: 1.6; margin: -2px 0 16px; }
.limits-panel .limits-recovery-key { width: 32px; height: 5px; border-radius: 3px; margin-top: 6px; flex-shrink: 0; background: linear-gradient(90deg, var(--limits-fill), color-mix(in srgb, var(--limits-fill) 25%, var(--card))); }
.limits-panel .limits-reset { color: var(--muted-foreground); font-size: 11px; line-height: 1.6; font-variant-numeric: tabular-nums; margin-top: 5px; overflow-wrap: anywhere; }
.limits-panel .limits-quotas { min-width: 0; }
.limits-panel .limits-quotas--weekly { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; }
.limits-panel .limits-weekly { min-width: 0; }
.limits-panel .limits-weekly-unknown { display: grid; grid-template-columns: 1fr auto; color: var(--muted-foreground); font-size: 11px; }
.limits-panel .limits-unknown-value { font-size: 17px; line-height: 1.1; }
.limits-panel .limits-weekly-unknown .limits-reset { grid-column: 1 / -1; margin-top: 12px; }
.limits-panel .limits-exhausted { color: var(--limits-danger-text); font-size: 10px; margin-top: 3px; }
.limits-panel .limits-caps { margin-top: 8px; }
.limits-panel .limits-cap { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px 10px; }
.limits-panel .limits-cap + .limits-cap { margin-top: 8px; }
.limits-panel .limits-cap-heading { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px 8px; color: var(--muted-foreground); font-size: 11px; }
.limits-panel .limits-cap-label { white-space: nowrap; }
.limits-panel .limits-cap-label::before { content: '↳'; margin-right: 5px; opacity: .6; }
.limits-panel .limits-cap-value { font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 550; }
.limits-panel .limits-cap-value[data-depleted] { color: var(--limits-danger-text); }
.limits-panel .limits-cap-mode { font-weight: 400; }
.limits-panel .limits-cap .limits-reset { margin-top: 0; }
.limits-panel .limits-footnote { display: flex; align-items: start; gap: 7px; color: var(--muted-foreground); font-size: 11px; line-height: 1.6; padding: 11px 20px; border-top: 1px solid var(--limits-line); background: var(--limits-soft); }
.limits-panel .limits-footnote .limits-icon { width: 12px; height: 12px; margin-top: 2px; }
.limits-panel .limits-pool { padding: 18px 0; border-bottom: 1px solid var(--limits-line); }
.limits-panel .limits-pool:last-child { border-bottom: 0; }
.limits-panel .limits-pool-label { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; color: var(--muted-foreground); font-size: 11px; font-weight: 500; }
.limits-panel .limits-message { color: var(--muted-foreground); font-size: 12px; line-height: 1.7; padding: 16px 0; min-width: 0; overflow-wrap: anywhere; }
.limits-panel .limits-message--error { color: var(--limits-danger-text); }
.limits-panel .limits-alert { padding: 12px 16px; margin-bottom: 14px; border: 1px solid color-mix(in srgb, var(--destructive) 25%, var(--card)); background: color-mix(in srgb, var(--destructive) 5%, var(--card)); color: var(--limits-danger-text); font-size: 12px; border-radius: 10px; overflow-wrap: anywhere; }
.limits-panel .limits-empty { padding: 44px 24px; border: 1px dashed var(--limits-line); border-radius: 16px; text-align: center; color: var(--muted-foreground); font-size: 12px; }
.limits-panel .limits-loading { display: flex; align-items: center; justify-content: center; gap: 10px; min-height: 180px; color: var(--muted-foreground); font-size: 12px; }
@keyframes limits-spin { to { transform: rotate(360deg); } }
@container limits (max-width: 760px) {
  .limits-panel .limits-shell { padding: 20px 16px 36px; }
  .limits-panel .limits-overview { gap: 18px; }
  .limits-panel .limits-account { grid-template-columns: minmax(135px, .8fr) minmax(0, 2fr); gap: 18px; }
  .limits-panel .limits-meters, .limits-panel .limits-quotas--weekly { gap: 14px; }
  .limits-panel .limits-provider-body { padding: 0 16px; }
  .limits-panel .limits-provider-head { padding: 14px 16px; }
}
@container limits (max-width: 580px) {
  .limits-panel .limits-shell { padding: 16px 12px 28px; }
  .limits-panel .limits-hero { padding-bottom: 18px; gap: 12px; }
  .limits-panel .limits-title { font-size: 22px; }
  .limits-panel .limits-emblem { width: 38px; height: 38px; border-radius: 12px; }
  .limits-panel .limits-overview { gap: 12px; }
  .limits-panel .limits-stat { display: flex; flex-direction: column; gap: 3px; align-items: end; }
  .limits-panel .limits-stat-number { font-size: 20px; }
  .limits-panel .limits-toolbar { flex-wrap: wrap; gap: 8px; }
  .limits-panel .limits-toolbar-end { gap: 8px; }
  .limits-panel .limits-segment { padding: 6px 9px; }
  .limits-panel .limits-segment, .limits-panel .limits-toolbar .limits-button { min-height: 36px; }
  .limits-panel .limits-button { padding: 8px; }
  .limits-panel .limits-account { grid-template-columns: minmax(0, 1fr); gap: 12px; padding: 16px 0; }
  .limits-panel .limits-account-name { font-size: 13px; }
  .limits-panel .limits-account-meta { margin-top: 3px; }
  .limits-panel .limits-provider-head { gap: 8px; }
  .limits-panel .limits-provider-title { gap: 5px; }
  .limits-panel .limits-provider-name { font-size: 14px; }
  .limits-panel .limits-provider-actions { gap: 4px; }
  .limits-panel .limits-updated { display: none; }
  .limits-panel .limits-refresh { width: 36px; height: 36px; }
  .limits-panel .limits-meters[data-columns='3'], .limits-panel .limits-meters[data-columns='4'] { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .limits-panel .limits-meter-number { font-size: 16px; }
  .limits-panel .limits-footnote { padding: 10px 16px; }
}
@container limits (max-width: 380px) {
  .limits-panel .limits-subtitle { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .limits-panel *, .limits-panel *::before, .limits-panel *::after { animation: none !important; transition: none !important; }
}
`;
