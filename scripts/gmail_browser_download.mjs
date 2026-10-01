// Run this function in the supported Codex browser session after Python prepare.
// A download event is not proof of a complete file: always run Python collect.
export async function downloadGmailAttachment(tab, filename, { timeoutMs = 20000 } = {}) {
  if (typeof filename !== "string" || !filename.toLowerCase().endsWith(".pdf")
      || /[/\\\x00-\x1f]/.test(filename) || filename.length > 240) {
    throw new Error("invalid_attachment_filename");
  }
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 120000) {
    throw new Error("invalid_download_timeout");
  }
  const url = new URL(await tab.url());
  if (url.protocol !== "https:" || url.hostname !== "mail.google.com") {
    throw new Error("gmail_source_required");
  }
  const button = tab.playwright.getByRole("button", {
    name: `下載附件「${filename}」`, exact: true,
  });
  if (await button.count() !== 1 || !await button.isVisible() || !await button.isEnabled()) {
    throw new Error("attachment_not_ready");
  }

  // The connected Chrome runtime needs the listener armed before the click.
  // Drain it even if clicking fails; never leave an unhandled rejected promise.
  const pending = tab.playwright.waitForEvent("download", { timeoutMs })
    .then(async download => {
      const path = await download.path({ timeoutMs });
      return { event: path ? "path_returned" : "path_unavailable", path };
    })
    .catch(() => ({ event: "not_observed", path: null }));
  let click = "dispatched";
  try {
    await button.click({ timeoutMs });
  } catch {
    click = "failed";
  }
  return { status: "collect_required", click, ...await pending };
}
