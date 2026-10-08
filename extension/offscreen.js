// Chrome service workers have no DOMParser, so HTML parsing happens here.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.target !== "offscreen") return;
  sendResponse(runParser(msg.type, msg));
});
