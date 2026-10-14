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

// Firefox-based browsers leave site access off after a manual install. Without this check the
// failure shows up as an unexplained network error.
async function requireSiteAccess(site, origin) {
  if (!chrome.permissions || !chrome.permissions.contains) return;
  const allowed = await chrome.permissions.contains({ origins: [origin + "/*"] });
  if (!allowed) throw new Error("Site access is off for " + site);
}

async function fetchHtml(site, origin, path) {
  const res = await fetch(origin + path, { credentials: "include", redirect: "follow" });
  if (/\/(login|auth)(\/|\?|$)/.test(new URL(res.url).pathname)) {
    throw new Error("Not signed in to " + site);
  }
  if (res.status === 401 || res.status === 403) throw new Error("Not signed in to " + site);
  if (!res.ok) throw new Error(path + " returned " + res.status);
  return res.text();
}

async function parseVia(type, payload) {
  if (HAS_DOM) return runParser(type, payload);
  return chrome.runtime.sendMessage({ target: "offscreen", type, ...payload });
}

// A page that loads fine but no longer contains what the parser looks for would otherwise look
// like "no assignments". These checks turn that into a visible failure or warning.
async function collectPrairieLearn() {
  await requireSiteAccess("PrairieLearn", PL_ORIGIN);
  const courses = await parseVia("parse-courses", { html: await fetchHtml("PrairieLearn", PL_ORIGIN, "/pl") });
  if (!courses.length) {
    throw new Error("No courses found on the PrairieLearn home page. Its layout may have changed");
  }
  const items = [];
  const warnings = [];
  let skipped = 0;
  let tables = 0;
  for (const course of courses) {
    const html = await fetchHtml("PrairieLearn", PL_ORIGIN, "/pl/course_instance/" + course.instanceId + "/assessments");
    const { items: found, rows, hasTable } = await parseVia("parse-assessments-report", { html, instanceId: course.instanceId });
    if (hasTable) tables += 1;
    skipped += Math.max(0, rows - found.length);
    for (const item of found) items.push({ ...item, course: course.label });
  }
  if (!tables) {
    warnings.push("None of the " + courses.length + " course pages had an assessments table, so PrairieLearn may have changed its layout");
  }
  return { items, skipped, warnings };
}

async function collectGradescope() {
  await requireSiteAccess("Gradescope", GS_ORIGIN);
  const courses = await parseVia("parse-gradescope-courses", { html: await fetchHtml("Gradescope", GS_ORIGIN, "/account") });
  if (!courses.length) {
    throw new Error("No courses found on the Gradescope account page. Its layout may have changed");
  }
  const items = [];
  const warnings = [];
  let tables = 0;
  for (const course of courses) {
    const html = await fetchHtml("Gradescope", GS_ORIGIN, "/courses/" + course.courseId);
    const { items: found, hasTable } = await parseVia("parse-gradescope-assignments-report", { html, courseId: course.courseId });
    if (hasTable) tables += 1;
    for (const item of found) items.push({ ...item, course: course.label });
  }
  if (!tables) {
    warnings.push("None of the " + courses.length + " course pages had an assignments table, so Gradescope may have changed its layout");
  }
  return { items, skipped: 0, warnings };
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
    const { items, skipped, warnings = [] } = await collect();
    // An empty result alongside a layout warning is more likely a broken parser than a real
    // empty list, so the last good data stays on the helper.
    if (items.length || !warnings.length) await post(site, items);
    return { ok: true, count: items.length, skipped, warnings };
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
