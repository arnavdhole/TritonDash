// Runs on the dashboard page. Lets the Refresh button ask the extension to sync.
document.documentElement.dataset.plExtension = "1";

document.addEventListener("dashboard:pl-refresh", async () => {
  let result = { ok: false };
  try {
    result = await chrome.runtime.sendMessage({ type: "sync" });
  } catch (e) {
    result = { ok: false, error: String(e) };
  }
  document.dispatchEvent(new CustomEvent("dashboard:pl-done", { detail: result }));
});
