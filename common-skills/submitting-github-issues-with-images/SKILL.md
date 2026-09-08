---
name: submitting-github-issues-with-images
description: "Upload local screenshots, videos, or diagnostic attachments as GitHub Release Assets, embed them in an issue, PR body, or comment, and read the published result back online. Flow skill: explicit user invocation, or reuse by an authorized caller workflow."
disable-model-invocation: true
---

# Submitting GitHub Evidence With Images

這是流程類 Skill，預設僅在使用者顯式調用 `$submitting-github-issues-with-images` 時執行。明文例外：呼叫端倉庫自己的授權 workflow（例如驗收 closeout）在執行該 workflow 時可直接讀取本 skill 並遵循；除此之外不得隱式觸發。

## Core Contract

建立一條可驗證的證據鏈：**本機檔案 → GitHub 持久 URL → issue 本文或 PR 正文／評論 → 線上回讀**。完成時必須回傳 issue 或 PR URL；不能只報告 API 成功。

呼叫端若維護自己的證據 workflow（例如某倉庫的驗收 closeout 要求候選正文先通過專用校驗），先完成該呼叫端校驗再上傳；本 skill 只負責上傳、嵌入與線上回讀，不替代呼叫端的项目校驗。

## Workflow

1. **準備**：確認使用者已授權目標 issue／PR 與 Release Asset 寫入、`gh auth status` 正常，且目前身份有對應權限。Issue 流程搜尋重複 issue；PR 流程解析唯一 PR、目前正文與既有 marker comment。檢查圖片／trace 不含 secrets 或不必要個資，使用語意化檔名。瀏覽器視覺證據預設截取完整頁面（full-page，包含頁面可滾動內容），讓讀者能看到整體版面與上下文；只有專門驗證固定 viewport、sticky 或摺疊區域時才使用 viewport 截圖，並在正文說明例外原因。
2. **上傳附件**：呼叫端契約要求先驗證候選正文時，先完成該驗證，再說明會新增專用 prerelease／tag 並用官方 Release Asset API 上傳。上傳後檢查 asset response 為 `state=uploaded`，且 `content_type` 與本機檔案 media type 一致（PNG 為 `image/png`）；issue／PR 使用 `browser_download_url`，private repo 只供已授權讀者存取。建立資源時立即記錄精確的 `release_id`、tag、`asset_id` 與 URL，清理不得靠模糊搜尋。
3. **提交**：Issue 以 body file 透過 GitHub API／`gh` 建立或更新，立即記錄 `issue_number`；PR 依呼叫端契約更新正文及／或帶唯一 HTML marker 的單一 comment，重跑時原位更新，不重複區塊或留言。內容包含目標、預期、實際、環境／證據及帶場景說明的圖片；trace 使用一般連結，不放進 `<img>`。
4. **API 驗證**：
   - 回讀 issue 的 title、state、labels、body，或 PR 的 state、body 與 comment id／marker；在各目標正文中每個附件 URL 恰好一次，沒有 placeholder 或 `Uploading`。
   - 以授權 API 下載 Release Asset 並比對本機 SHA-256；用 GitHub Markdown renderer 確認預期 `<img>` 數量。
   - 這些證據只證明 GitHub 已保存正確圖片位元與 Markdown reference，不等於像素已在瀏覽器載入；不得宣稱已目視圖片。
5. **清理**：
   - 測試 issue：有刪除權限時，按精確 number 刪除 issue；否則先移除本文附件 URL 再關閉，並回報仍保留 sanitized closed issue。測試 PR comment 按精確 comment id 刪除；保留的正式 comment 不清理。
   - 刪除整個專用 release 時按 `release_id` 清理（其 assets 一併刪除）；若保留 release，才按記錄的 `asset_id` 單獨刪除。最後刪 exact tag ref，並逐項 API 回讀確認不存在。若 issue 本文或保留的 PR 正文／comment 仍引用附件 URL，禁止刪除其附件資源。
   - 中途失敗也遵循相同依賴順序；不得先刪除仍被 issue 或 PR comment 引用的附件。

## Guardrails

- 不使用本機 `file://`、repo 內 `tmp/` 路徑或未公開的 GitHub upload endpoint。
- 不假設 `gh issue create`、PR body 或 comment API 能直接上傳附件；它們只提交 Markdown。
- 不把截圖 commit 到業務 branch，除非使用者明確要求文件化保存。
- 不輸出 token；不使用模糊名稱或 glob 刪除 GitHub 資源。
