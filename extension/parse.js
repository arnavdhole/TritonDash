// PrairieLearn page parsers. Both run in the offscreen document (needs DOMParser).
// A deadline is { id, name, date: "YYYY-MM-DD", url }.

const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

// Home page: each course is a link like /pl/course_instance/223396 whose text reads
// "CSE 103: Probability and Statistics, CSE103 Fall 2026".
function parseCourseList(doc) {
  const seen = new Set();
  const courses = [];
  doc.querySelectorAll("a[href]").forEach(a => {
    const m = a.getAttribute("href").match(/\/pl\/course_instance\/(\d+)\/?$/);
    if (!m || seen.has(m[1])) return;
    seen.add(m[1]);
    const text = a.textContent.replace(/\s+/g, " ").trim();
    const label = (text.split(":")[0] || text).trim();
    courses.push({ instanceId: m[1], label });
  });
  return courses;
}

function pad(n) { return String(n).padStart(2, "0"); }

// "100% until 23:59, Mon, Oct 5" -> the date part, with the year inferred.
function dateFromCreditText(text, today) {
  const m = text.match(/until\s+\d{1,2}:\d{2}(?:\s*[ap]m)?,\s*\w{3},\s*(\w{3})\s+(\d{1,2})/i);
  if (!m) return null;
  const month = MONTHS[m[1].toLowerCase().slice(0, 3)];
  if (!month) return null;
  let year = today.getFullYear();
  // A date more than ~6 months behind us belongs to next year.
  if (new Date(year, month - 1, Number(m[2])) < new Date(year, today.getMonth() - 6, 1)) year += 1;
  return year + "-" + pad(month) + "-" + pad(Number(m[2]));
}

// The "Access details" popover holds a Credit / Start / End table. The first row is
// the highest credit window, which is the real due date.
function dateFromPopover(cell) {
  const button = cell.querySelector("button[data-bs-content]");
  if (!button) return null;
  const inner = new DOMParser().parseFromString(button.getAttribute("data-bs-content"), "text/html");
  for (const row of inner.querySelectorAll("tr")) {
    const cells = row.querySelectorAll("td");
    if (cells.length < 3) continue;
    const m = cells[2].textContent.match(/(\d{4}-\d{2}-\d{2})/);
    if (m) return m[1];
  }
  return null;
}

function parseAssessments(doc, instanceId, today = new Date()) {
  const table = doc.querySelector('table[aria-label="Assessments"]');
  if (!table) return [];
  const items = [];
  table.querySelectorAll("tr").forEach(row => {
    const badge = row.querySelector('[data-testid="assessment-set-badge"]');
    if (!badge) return; // header or group heading row
    const cells = row.querySelectorAll("td");
    const link = cells[1] && cells[1].querySelector("a");
    if (!link || !cells[2]) return;

    const name = link.textContent.replace(/\s+/g, " ").trim();
    const date = dateFromPopover(cells[2]) || dateFromCreditText(cells[2].textContent, today);
    if (!date) return; // no deadline, such as "No credit" or always open

    const label = badge.textContent.replace(/\s+/g, " ").trim();
    items.push({
      id: instanceId + ":" + (label || name),
      name,
      date,
      url: link.getAttribute("href")
    });
  });
  return items;
}

// ---------------------------------------------------------------------------
// Gradescope. Both parsers run in the offscreen document.
// ---------------------------------------------------------------------------

const GRADESCOPE_MAX_COURSES = 12;

function cleanText(node) {
  return (node ? node.textContent : "").replace(/\s+/g, " ").trim();
}

// Account page: terms are listed newest first, each followed by a group of course boxes
// that link to /courses/<id>. Only the newest term matters for deadlines.
function parseGradescopeCourses(doc) {
  const groups = doc.querySelectorAll(".courseList--coursesForTerm");
  const terms = doc.querySelectorAll(".courseList--term");
  const newestTerm = terms.length ? cleanText(terms[0]) : null;

  const scopes = [];
  groups.forEach(group => {
    const heading = group.previousElementSibling;
    const term = heading && heading.classList.contains("courseList--term") ? cleanText(heading) : null;
    if (!newestTerm || !term || term === newestTerm) scopes.push(group);
  });
  if (!scopes.length) scopes.push(doc);

  const seen = new Set();
  const courses = [];
  scopes.forEach(scope => {
    scope.querySelectorAll('a[href^="/courses/"]').forEach(a => {
      const m = a.getAttribute("href").match(/^\/courses\/(\d+)\/?$/);
      if (!m || seen.has(m[1])) return;
      seen.add(m[1]);
      const short = a.querySelector(".courseBox--shortname");
      courses.push({ courseId: m[1], label: cleanText(short || a) });
    });
  });
  return courses.slice(0, GRADESCOPE_MAX_COURSES);
}

// Course page: the student table has one row per assignment. The due date sits in a
// <time class="submissionTimeChart--dueDate" datetime="2026-10-12 23:59:00 -0700"> element,
// already expressed in the course's own timezone.
function parseGradescopeAssignments(doc, courseId) {
  const table = doc.querySelector("#assignments-student-table");
  if (!table) return [];
  const items = [];
  table.querySelectorAll("tbody tr").forEach(row => {
    const th = row.querySelector("th");
    if (!th) return;
    const link = th.querySelector("a[href]");
    const button = th.querySelector("button[data-assignment-id]");

    const name = cleanText(link || button || th);
    if (!name) return;

    // Anything already submitted or graded needs no reminder.
    const status = cleanText(row.querySelector(".submissionStatus--text")).toLowerCase();
    if (row.querySelector(".submissionStatus--score")) return;
    if (status && !/no submission/.test(status)) return;

    const due = row.querySelector("time.submissionTimeChart--dueDate");
    const m = due && (due.getAttribute("datetime") || "").match(/^(\d{4}-\d{2}-\d{2})/);
    if (!m) return; // no deadline listed

    let assignmentId = null;
    if (link) {
      const lm = link.getAttribute("href").match(/\/assignments\/(\d+)/);
      if (lm) assignmentId = lm[1];
    }
    if (!assignmentId && button) assignmentId = button.getAttribute("data-assignment-id");

    items.push({
      id: courseId + ":" + (assignmentId || name),
      name,
      date: m[1],
      url: "https://www.gradescope.com/courses/" + courseId + (assignmentId ? "/assignments/" + assignmentId : "")
    });
  });
  return items;
}

// Shared entry point. Chrome calls this from offscreen.js; Firefox calls it from background.js.
function runParser(type, msg) {
  const doc = new DOMParser().parseFromString(msg.html, "text/html");
  if (type === "parse-courses") return parseCourseList(doc);
  if (type === "parse-assessments") return parseAssessments(doc, msg.instanceId);
  if (type === "parse-gradescope-courses") return parseGradescopeCourses(doc);
  if (type === "parse-gradescope-assignments") return parseGradescopeAssignments(doc, msg.courseId);
  return null;
}
