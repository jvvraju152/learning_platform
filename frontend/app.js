/* Shared helpers for every page. No framework. */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
  });
}

function param(name) { return new URLSearchParams(location.search).get(name); }

async function api(path, body) {
  var opts = {credentials: "same-origin"};
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers = {"Content-Type": "application/json"};
    opts.body = JSON.stringify(body);
  }
  var res = await fetch("/api" + path, opts);
  var data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok) {
    var err = new Error((data && data.detail) || "Something went wrong (" + res.status + ").");
    err.status = res.status;
    throw err;
  }
  return data;
}

/* Every page after login calls this first. Sends you to the start page if not logged in. */
async function requireLogin() {
  var r = await api("/me");
  if (!r.user) { location.replace("index.html"); return null; }
  drawTop(r.user);
  return r.user;
}

function drawTop(user) {
  var el = document.getElementById("top");
  if (!el) return;
  el.innerHTML = '<span class="who">' + (user ? esc(user.name) + ' | <a href="#" id="logout">Log out</a>' : '') + '</span>' +
    '<span class="site">Personalized Learning</span>' +
    (user ? '<a href="subjects.html">Subjects</a><a href="dashboard.html">My Progress</a>' : '');
  var lo = document.getElementById("logout");
  if (lo) lo.onclick = async function (e) {
    e.preventDefault();
    await api("/logout", {});
    try { sessionStorage.clear(); } catch (x) {}
    location.href = "index.html";
  };
}

function show(el, html) { el.innerHTML = html; }
function showError(el, e) { el.innerHTML = '<div class="error">' + esc(e.message || e) + '</div>'; }

var LEVEL_NAME = {easy: "Easy", medium: "Medium", hard: "Hard", practice: "Practice"};
function pct(x) { return x == null ? "-" : Math.round(x * 100) + "%"; }

var STATUS_TEXT = {
  weak: "Weak", developing: "Developing", strong: "Strong",
  insufficient_data: "Not enough answers yet", stale: "Old results, re-test", not_started: "Not started"
};
var TREND_TEXT = {improving: "Improving", declining: "Declining", stable: "Steady"};

/* One level (Easy/Medium/Hard) of one module, as a table cell or list text. */
function levelCell(topicId, lv) {
  var link = 'quiz.html?topic=' + encodeURIComponent(topicId) + '&level=' + lv.difficulty;
  if (!lv.unlocked) return '<span class="locked">Locked</span>';
  var h = '';
  if (lv.tries > 0) {
    h += lv.passed ? '<span class="ok">Passed</span> ' : '<span class="bad">Not passed</span> ';
    h += '(best ' + lv.best_score + '/' + lv.best_total + ')<br>';
  }
  return h + '<a class="btn" href="' + link + '">' + (lv.tries > 0 ? "Retake" : "Start") + '</a>';
}
