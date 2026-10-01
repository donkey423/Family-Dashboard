import assert from "node:assert/strict";
import test from "node:test";
import { downloadGmailAttachment } from "../gmail_browser_download.mjs";

function browser({ eventFails = true, clickFails = false, ready = true, path = null } = {}) {
  const calls = [];
  let finish;
  const pending = new Promise((resolve, reject) => {
    finish = () => eventFails ? reject(new Error("private event details")) : resolve({ path: async () => path });
  });
  const tab = {
    url: async () => "https://mail.google.com/mail/u/0/#inbox",
    playwright: {
      getByRole(role, options) {
        assert.equal(role, "button");
        assert.equal(options.exact, true);
        assert.equal(options.name, "下載附件「statement.pdf」");
        return {
          count: async () => 1,
          isVisible: async () => true,
          isEnabled: async () => ready,
          click: async () => {
            calls.push("click");
            finish();
            if (clickFails) throw new Error("private click details");
          },
        };
      },
      waitForEvent(event, options) {
        calls.push("listen");
        assert.equal(event, "download");
        assert.equal(options.timeoutMs, 20000);
        return pending;
      },
    },
  };
  return { tab, calls };
}

test("arms before exactly one click and requires collect even on event timeout", async () => {
  const { tab, calls } = browser();
  const result = await downloadGmailAttachment(tab, "statement.pdf");
  assert.deepEqual(calls, ["listen", "click"]);
  assert.deepEqual(result, { status: "collect_required", click: "dispatched", event: "not_observed", path: null });
});

test("an event path is only a candidate, never a verified receipt", async () => {
  const { tab } = browser({ eventFails: false, path: "C:/Downloads/new.tmp" });
  const result = await downloadGmailAttachment(tab, "statement.pdf");
  assert.equal(result.path, "C:/Downloads/new.tmp");
  assert.equal(result.event, "path_returned");
  assert.equal(result.status, "collect_required");
});

test("null event path still requires file verification", async () => {
  const { tab } = browser({ eventFails: false });
  assert.equal((await downloadGmailAttachment(tab, "statement.pdf")).event, "path_unavailable");
});

test("click failures drain the event and do not retry or leak raw errors", async () => {
  const { tab, calls } = browser({ clickFails: true });
  const result = await downloadGmailAttachment(tab, "statement.pdf");
  assert.equal(result.click, "failed");
  assert.equal(result.status, "collect_required");
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.deepEqual(calls, ["listen", "click"]);
});

test("a disabled attachment never starts a download", async () => {
  const { tab, calls } = browser({ ready: false });
  await assert.rejects(downloadGmailAttachment(tab, "statement.pdf"), /attachment_not_ready/);
  assert.deepEqual(calls, []);
});

test("a non-Gmail source is rejected", async () => {
  const { tab, calls } = browser();
  tab.url = async () => "https://mail.google.com.example.test/";
  await assert.rejects(downloadGmailAttachment(tab, "statement.pdf"), /gmail_source_required/);
  assert.deepEqual(calls, []);
});

test("invalid filenames and unbounded timeouts are rejected before interaction", async () => {
  const { tab, calls } = browser();
  for (const filename of ["../statement.pdf", "statement.pdf\n", "statement.exe", null]) {
    await assert.rejects(downloadGmailAttachment(tab, filename), /invalid_attachment_filename/);
  }
  for (const timeoutMs of [0, 120001, NaN]) {
    await assert.rejects(downloadGmailAttachment(tab, "statement.pdf", { timeoutMs }), /invalid_download_timeout/);
  }
  assert.deepEqual(calls, []);
});
