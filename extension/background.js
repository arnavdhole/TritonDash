const HELPER = "http://127.0.0.1:8765";
const PL_ORIGIN = "https://us.prairielearn.com";
const GS_ORIGIN = "https://www.gradescope.com";

// Firefox and Zen run the background as a page with DOMParser, so parse.js is loaded alongside
// and called directly. Chrome service workers have no DOM and parse in an offscreen document.
const HAS_DOM = typeof DOMParser !== "undefined";

async function ensureOffscreen() {
  if (HAS_DOM) return;
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: ["DOM_PARSER"],
    justification: "Parse PrairieLearn and Gradescope HTML pages"
  });
}

async function fetchHtml(site, origin, path) {
  const res = await fetch(origin + path, { credentials: "include", redirect: "follow" });
  if (/\/(login|auth)(\/|\?|$)/.test(new URL(res.url).pathname)) {
    throw new Error("Not signed in to " + site);
  }
  if (!res.ok) throw new Error(path + " returned " + res.status);
  return res.text();
}

async function parseVia(type, payload) {
  if (HAS_DOM) return runParser(type, payload);
  return chrome.runtime.sendMessage({ target: "offscreen", type, ...payload });
}

async function collectPrairieLearn() {
  const courses = await parseVia("parse-courses", { html: await fetchHtml("PrairieLearn", PL_ORIGIN, "/pl") });
  const items = [];
  for (const course of courses) {
    const html = await fetchHtml("PrairieLearn", PL_ORIGIN, "/pl/course_instance/" + course.instanceId + "/assessments");
    const found = await parseVia("parse-assessments", { html, instanceId: course.instanceId });
    for (const item of found) items.push({ ...item, course: course.label });
  }
  return items;
}

async function collectGradescope() {
  const courses = await parseVia("parse-gradescope-courses", { html: await fetchHtml("Gradescope", GS_ORIGIN, "/account") });
  const items = [];
  for (const course of courses) {
    const html = await fetchHtml("Gradescope", GS_ORIGIN, "/courses/" + course.courseId);
    const found = await parseVia("parse-gradescope-assignments", { html, courseId: course.courseId });
    for (const item of found) items.push({ ...item, course: course.label });
  }
  return items;
}

async function post(site, items) {
  const res = await fetch(HELPER + "/" + site, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items })
  });
  if (!res.ok) throw new Error("Dashboard helper returned " + res.status);
}

// A site that fails keeps its previous data on the helper, since nothing is posted.
async function syncSite(site, collect) {
  try {
    const items = await collect();
    await post(site, items);
    return { ok: true, count: items.length };
  } catch (err) {
    return { ok: false, error: String(err.message || err) };
  }
}

async function sync() {
  await ensureOffscreen();
  const sources = {
    prairielearn: await syncSite("prairielearn", collectPrairieLearn),
    gradescope: await syncSite("gradescope", collectGradescope)
  };
  const failed = Object.values(sources).filter(s => !s.ok);
  return { ok: failed.length === 0, sources, error: failed.length ? failed[0].error : undefined };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "sync") return;
  sync().then(sendResponse, err => sendResponse({ ok: false, error: String(err) }));
  return true;
});
