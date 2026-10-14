// Runs on the dashboard page. Lets the Refresh button ask the extension to sync.
//
// The flag is set with setAttribute because Firefox-based browsers can drop writes made
// through `dataset` from a content script. The dashboard reads it as dataset.plExtension.
(document.documentElement || document).setAttribute("data-pl-extension", "1");
console.log("[TritonDash Sync] extension attached to this page");

// Firefox hides objects created by a content script from the page unless they are copied
// into the page first. Chrome has no cloneInto and needs no copy.
function forPage(value) {
  return typeof cloneInto === "function" ? cloneInto(value, window) : value;
}

document.addEventListener("dashboard:pl-refresh", async () => {
  let result = { ok: false };
  try {
    result = await chrome.runtime.sendMessage({ type: "sync" });
  } catch (e) {
    result = { ok: false, error: String(e) };
  }
  document.dispatchEvent(new CustomEvent("dashboard:pl-done", { detail: forPage(result || { ok: false, error: "No answer" }) }));
});
