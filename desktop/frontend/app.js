/* Gencrypt Desktop — SPA controller.
   Talks only to the local bridge, which forwards to the secgen CLI engine.
   Styled to match gencrypt.xyz. Aims for full CLI parity. */

const TOKEN = window.__SG_TOKEN__;

/* ------------------------------------------------------------------ API */
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: { "X-SG-Token": TOKEN, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* --------------------------------------------------------------- helpers */
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) { if (kid == null || kid === false) continue; n.append(kid.nodeType ? kid : document.createTextNode(kid)); }
  return n;
};
const shortId = (id) => (id ? String(id).slice(0, 8) : "—");
const humanSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : b > 1024 ? (b / 1024).toFixed(1) + " KB" : b + " B");

/* Stream a File's bytes to the local server, which stages it on disk and returns
   a real path the CLI can use. Loopback only — the plaintext never leaves the box. */
async function uploadFile(file) {
  const res = await fetch("/api/upload-file", {
    method: "POST",
    headers: { "X-SG-Token": TOKEN, "X-SG-Filename": encodeURIComponent(file.name), "Content-Type": "application/octet-stream" },
    body: file,
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.error || `Upload failed (${res.status})`);
  return data; // { path, filename, size }
}

/* Reusable drag-and-drop + browse control. Calls onPath(serverPath, filename)
   once a file is staged. Works in the native window and the browser alike. */
function fileDrop(onPath, { accept = ".vcf,.vcf.gz,.gz,.txt" } = {}) {
  const input = el("input", { type: "file", accept, style: "display:none" });
  const meta = el("div", { class: "drop-meta" });
  const zone = el("div", { class: "dropzone" },
    el("div", { class: "drop-icon" }, "⬆"),
    el("div", { class: "drop-label" }, "Drag & drop a VCF here, or ", el("span", { class: "drop-link" }, "browse")),
    meta,
    el("div", { class: "drop-hint" }, "The file is encoded & FHE-encrypted locally; only ciphertext is uploaded."),
    input);
  let staged = null;
  const setFile = async (file) => {
    if (!file) return;
    zone.classList.remove("is-ready"); zone.classList.add("is-busy");
    meta.innerHTML = ""; meta.append(el("span", { class: "muted" }, `Staging ${file.name}…`));
    try {
      const { path, size } = await uploadFile(file);
      staged = path;
      zone.classList.remove("is-busy"); zone.classList.add("is-ready");
      meta.innerHTML = "";
      meta.append(el("span", { class: "drop-file" }, `✓ ${file.name}`), el("span", { class: "drop-size" }, humanSize(size)),
        el("span", { class: "drop-link", onclick: (e) => { e.stopPropagation(); staged = null; zone.classList.remove("is-ready"); meta.innerHTML = ""; onPath(null); } }, "change"));
      onPath(path, file.name);
    } catch (e) {
      zone.classList.remove("is-busy"); meta.innerHTML = ""; meta.append(el("span", { style: "color:var(--gc-error)" }, "Upload failed: " + e.message));
    }
  };
  input.addEventListener("change", () => setFile(input.files[0]));
  zone.addEventListener("click", (e) => { if (e.target !== input) input.click(); });
  ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("is-drag"); }));
  ["dragleave", "dragend"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("is-drag"); }));
  zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("is-drag"); const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) setFile(f); });
  return { zone, getPath: () => staged };
}

function toast(msg, kind = "") {
  const host = $("#toasts");
  const t = el("div", { class: `toast ${kind ? "toast--" + kind : ""}` },
    el("span", {}, msg), el("span", { class: "toast-x", onclick: () => t.remove() }, "✕"));
  host.append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 4000);
}

function modal({ title, sub, body, actions }) {
  const host = $("#modalHost"); host.hidden = false; host.innerHTML = "";
  const close = () => { host.hidden = true; host.innerHTML = ""; };
  const foot = el("div", { class: "modal-foot" });
  (actions || []).forEach((a) => foot.append(el("button", { class: a.class || "gc-button-secondary", onclick: () => a.onClick(close) }, a.label)));
  const card = el("div", { class: "modal" },
    el("div", { class: "modal-head" }, el("div", { class: "modal-title" }, title), sub ? el("div", { class: "modal-sub" }, sub) : null),
    el("div", { class: "modal-body" }, body),
    actions ? foot : null);
  host.append(card);
  host.onclick = (e) => { if (e.target === host) close(); };
  return { close, card };
}

/* --------------------------------------------------------- status badges */
function badge(label, kind = "neutral") {
  return el("span", { class: `gc-status gc-status-${kind}` }, el("span", { class: "dot" }), label);
}
const READINESS = {
  result_available: ["Result available", "success"],
  ready_to_run: ["Ready to run", "info"],
  waiting_for_submissions: ["Waiting for data", "warning"],
  missing_context: ["Missing context", "warning"],
  running: ["Running", "info"],
  queued: ["Queued", "info"],
  completed: ["Completed", "success"],
  failed: ["Failed", "error"],
  no_jobs: ["No jobs", "neutral"],
};
function readinessBadge(state) {
  const [label, kind] = READINESS[state] || [state || "Unknown", "neutral"];
  return badge(label, kind);
}

/* ------------------------------------------------------------ job runner */
async function runJob(startPromise, { title, onDone } = {}) {
  const stepsBox = el("div", { class: "steps" }, el("div", { class: "muted" }, "Starting…"));
  const consoleBox = el("pre", { class: "gc-command-block" });
  const m = modal({
    title: title || "Working…", sub: "Running through the secgen CLI engine",
    body: el("div", {}, stepsBox, el("div", { style: "height:14px" }), consoleBox),
    actions: [{ label: "Close", class: "gc-button-ghost", onClick: (c) => c() }],
  });
  let jobId;
  try { jobId = (await startPromise).job.id; }
  catch (e) { stepsBox.innerHTML = ""; stepsBox.append(badge("Failed to start", "error")); consoleBox.textContent = e.message; return; }

  const render = (job) => {
    stepsBox.innerHTML = "";
    (job.steps || []).forEach((s) => {
      const cls = s.status === "done" ? "step--done" : s.status === "running" ? "step--running" : "step--pending";
      stepsBox.append(el("div", { class: `step ${cls}` }, el("span", { class: "step-dot" }), s.name));
    });
    if (!job.steps || !job.steps.length) stepsBox.append(el("div", { class: "muted" }, "Working…"));
    consoleBox.textContent = (job.log || []).join("\n"); consoleBox.scrollTop = consoleBox.scrollHeight;
  };
  return new Promise((resolve) => {
    const poll = async () => {
      let job;
      try { ({ job } = await api(`/api/jobs/${jobId}`)); } catch (_) { return setTimeout(poll, 900); }
      render(job);
      if (job.status === "running") return setTimeout(poll, 800);
      m.card.querySelector(".modal-sub").textContent = job.status === "succeeded" ? "Completed" : "Failed";
      if (job.status === "succeeded") { toast(`${job.title} — done`, "ok"); onDone && onDone(job); }
      else toast(job.error || "Job failed", "err");
      resolve(job);
    };
    poll();
  });
}

/* ----------------------------------------------------------------- state */
const state = { system: null, user: null, view: "overview" };

/* =========================================================== AUTH SCREEN */
function renderAuth(mode = "login") {
  $("#nav").hidden = true;
  const isLogin = mode === "login";
  const email = el("input", { class: "gc-input", type: "email", placeholder: "you@lab.org", autofocus: true });
  const pass = el("input", { class: "gc-input", type: "password", placeholder: "••••••••" });
  const submit = el("button", { class: "gc-button-primary", style: "width:100%" }, isLogin ? "Sign in" : "Create account");
  const doAuth = async () => {
    submit.disabled = true; submit.textContent = isLogin ? "Signing in…" : "Creating…";
    try {
      const out = await api(isLogin ? "/api/auth/login" : "/api/auth/register", { method: "POST", body: { email: email.value.trim(), password: pass.value } });
      state.system = { ...out.system, cli_version: out.cli_version }; state.user = out.user;
      toast(isLogin ? "Signed in" : "Account created", "ok"); state.view = "overview"; renderShell();
    } catch (e) { toast(e.message, "err"); submit.disabled = false; submit.textContent = isLogin ? "Sign in" : "Create account"; }
  };
  submit.addEventListener("click", doAuth);
  pass.addEventListener("keydown", (e) => { if (e.key === "Enter") doAuth(); });
  $("#main").innerHTML = "";
  $("#main").append(el("div", { class: "auth" }, el("div", { class: "auth-card" },
    el("div", { class: "auth-brand" }, el("span", { class: "brand-mark" }), el("span", { class: "brand-word" }, "Gencrypt")),
    el("h1", { class: "auth-title" }, isLogin ? "Welcome back" : "Create your account"),
    el("p", { class: "auth-sub" }, isLogin ? "Sign in to manage encrypted genomic analyses." : "Register a Gencrypt account. Your FHE secret key is generated and stays on this device."),
    el("div", { class: "field" }, el("label", { class: "gc-label" }, "Email"), email),
    el("div", { class: "field" }, el("label", { class: "gc-label" }, "Password"), pass),
    submit,
    el("div", { class: "auth-switch" }, isLogin ? "New here? " : "Already have an account? ",
      el("button", { onclick: () => renderAuth(isLogin ? "register" : "login") }, isLogin ? "Create one" : "Sign in")),
    el("div", { class: "auth-note" }, el("span", {}, "🔒"),
      el("span", {}, "The secret key never leaves this machine. Only ciphertext and the public context are ever uploaded.")))));
}

/* ============================================================ APP SHELL */
function renderShell() {
  const nav = $("#nav"); nav.hidden = false;
  markNav();
  nav.querySelectorAll(".gc-nav-link, .gc-menu-item[data-view]").forEach((b) => {
    b.onclick = () => { state.view = b.dataset.view; $("#acctDropdown").hidden = true; renderShell(); };
  });
  $("#navHome").onclick = () => { state.view = "overview"; renderShell(); };
  // account dropdown
  const trigger = $("#acctTrigger"), dd = $("#acctDropdown");
  trigger.onclick = (e) => { e.stopPropagation(); dd.hidden = !dd.hidden; };
  document.onclick = () => { dd.hidden = true; };
  $("#menuSignOut").onclick = async (e) => {
    e.stopPropagation();
    try { const out = await api("/api/auth/logout", { method: "POST" }); state.system = out.system; state.user = null; toast("Signed out", "ok"); renderAuth("login"); }
    catch (err) { toast(err.message, "err"); }
  };
  renderConn(); renderAccount();
  const views = { overview: viewOverview, projects: viewProjects, protocols: viewProtocols, local: viewLocal, activity: viewActivity, system: viewSystem };
  (views[state.view] || viewOverview)();
}

function markNav() {
  document.querySelectorAll(".gc-nav-link").forEach((b) => b.classList.toggle("is-active", b.dataset.view === state.view));
}
function renderConn() {
  const sys = state.system || {};
  $("#connDot").className = "conn-dot " + (sys.server_connected ? "is-ok" : "is-bad");
  $("#connLabel").textContent = sys.server_connected ? "Connected" : "Offline";
  $("#conn").title = sys.server_url || "";
}
function renderAccount() {
  $("#acctEmail").textContent = state.user?.email || "";
}

function mount(...nodes) { const m = $("#main"); m.innerHTML = ""; m.append(el("div", { class: "gc-page" }, ...nodes)); }
function head(title, sub, ...actions) {
  return el("div", { class: "view-head" },
    el("div", {}, el("h1", { class: "gc-title" }, title), sub ? el("div", { class: "view-sub" }, sub) : null),
    el("div", { class: "row wrap" }, ...actions));
}

/* ============================================================= OVERVIEW */
async function viewOverview() {
  const sys = state.system || {};
  mount(
    head("Overview", `Signed in as ${state.user?.email || "—"}`),
    el("div", { class: "grid grid--stats", id: "ovStats" },
      statCard("Projects", "…", "loading"),
      statCard("Server", sys.server_connected ? "Online" : "Offline", sys.server_url || ""),
      statCard("Cached protocols", sys.cached_protocols ?? "—", "local"),
      statCard("CLI engine", "v" + (sys.cli_version || "—"), "secgen")),
    el("div", { style: "height:22px" }),
    el("div", { class: "gc-panel" },
      el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Quick actions"), el("span", {})),
      el("div", { class: "panel-body row wrap" },
        el("button", { class: "gc-button-primary", onclick: openCreateProject }, "＋ New project"),
        el("button", { class: "gc-button-secondary", onclick: () => go("protocols") }, "Browse protocols"),
        el("button", { class: "gc-button-secondary", onclick: () => go("local") }, "Run local analysis"))),
    el("div", { style: "height:16px" }),
    custodyNote());
  try {
    const { projects } = await api("/api/projects");
    const stats = $("#ovStats"); if (!stats) return;
    stats.firstChild.querySelector(".stat-v").textContent = projects.length;
    stats.firstChild.querySelector(".stat-meta").textContent = projects.length === 1 ? "1 project" : `${projects.length} projects`;
  } catch (_) {}
}
const go = (v) => { state.view = v; renderShell(); };
function statCard(k, v, meta) {
  return el("div", { class: "stat" }, el("div", { class: "stat-k" }, k), el("div", { class: "stat-v" }, String(v)), el("div", { class: "stat-meta" }, meta || ""));
}
function custodyNote() {
  return el("div", { class: "gc-panel" },
    el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Privacy custody"), el("span", {})),
    el("div", { class: "panel-body muted", style: "font-size:14px" },
      el("p", { style: "margin:0 0 8px" }, "Encoding and FHE encryption run locally through the CLI. The secret key is generated here and never uploaded."),
      el("p", { style: "margin:0" }, "Only ciphertext, the public crypto context, and encryption stats reach the server. Results download encrypted and decrypt locally.")));
}

/* ============================================================== PROJECTS */
async function viewProjects() {
  mount(
    head("Projects", "Aggregated, encrypted analyses you own or contribute to",
      el("button", { class: "gc-button-primary", onclick: openCreateProject }, "＋ New project")),
    el("div", { id: "projList" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Loading projects…")));
  try {
    const { projects } = await api("/api/projects");
    const box = $("#projList"); if (!box) return; box.innerHTML = "";
    if (!projects.length) {
      box.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "No projects yet"),
        el("div", {}, "Create a project from a protocol to start contributing encrypted data."),
        el("div", { style: "margin-top:16px" }, el("button", { class: "gc-button-primary", onclick: openCreateProject }, "＋ New project"))));
      return;
    }
    const grid = el("div", { class: "grid grid--cards" });
    projects.forEach((p) => grid.append(projectCard(p)));
    box.append(grid);
  } catch (e) {
    const box = $("#projList"); if (box) { box.innerHTML = ""; box.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "Couldn't load projects"), el("div", {}, e.message))); }
  }
}
function projectCard(p) {
  const title = p.protocol_name || "Project";
  return el("div", { class: "gc-card gc-card--link", style: "padding:18px", onclick: () => openProject(p.id) },
    el("div", { class: "card-top" },
      el("div", {}, el("div", { class: "card-title" }, title), el("div", { class: "card-id" }, "#" + shortId(p.id))),
      readinessBadge(p.readiness || p.status || p.job_status)),
    p.protocol_description ? el("div", { class: "card-desc" }, p.protocol_description) : null,
    el("div", { class: "card-row" },
      p.has_context ? badge("Context ✓", "success") : badge("No context", "neutral"),
      typeof p.contributor_count === "number" ? badge(`${p.contributor_count} contributors`, "neutral") : null,
      typeof p.vcf_count === "number" ? badge(`${p.vcf_count} datasets`, "neutral") : null,
      p.result_available ? badge("Result", "success") : null));
}

function openCreateProject() {
  const select = el("select", { class: "gc-select" }, el("option", { value: "" }, "Loading protocols…"));
  const manual = el("input", { class: "gc-input", placeholder: "or type a protocol name, e.g. alzheimers-risk" });
  modal({
    title: "New project", sub: "Pick a protocol to compute on",
    body: el("div", {},
      el("div", { class: "field" }, el("label", { class: "gc-label" }, "Protocol"), select),
      el("div", { class: "field" }, el("label", { class: "gc-label" }, "Or enter manually"), manual),
      el("div", { class: "hint" }, "Creating a project also generates your FHE keypair and uploads only the public context.")),
    actions: [
      { label: "Cancel", class: "gc-button-ghost", onClick: (c) => c() },
      { label: "Create", class: "gc-button-primary", onClick: async (close) => {
        const name = manual.value.trim() || select.value;
        if (!name) return toast("Choose a protocol", "err");
        close();
        await runJob(api("/api/projects", { method: "POST", body: { protocol_name: name } }), { title: "Creating project", onDone: () => go("projects") });
      } },
    ],
  });
  api("/api/protocols").then(({ protocols }) => {
    select.innerHTML = ""; select.append(el("option", { value: "" }, "— select a protocol —"));
    protocols.forEach((p) => select.append(el("option", { value: p.name }, `${p.name}${p.description ? " — " + p.description : ""}`)));
  }).catch(() => { select.innerHTML = ""; select.append(el("option", { value: "" }, "Could not load — type manually")); });
}

/* ------------------------------------------------------ project detail */
async function openProject(pid) {
  state.view = "projects"; markNav();
  mount(el("button", { class: "back", onclick: viewProjects }, "← All projects"),
    el("div", { id: "projDetail" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Loading…")));
  let project;
  try { ({ project } = await api(`/api/projects/${pid}`)); }
  catch (e) { const b = $("#projDetail"); if (b) { b.innerHTML = ""; b.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "Not found"), el("div", {}, e.message))); } return; }
  const box = $("#projDetail"); if (!box) return; box.innerHTML = "";
  box.append(
    el("div", { class: "view-head" },
      el("div", {}, el("h1", { class: "gc-title" }, project.protocol_name || "Project"), el("div", { class: "view-sub mono" }, "#" + project.id)),
      el("div", { class: "row wrap" }, readinessBadge(project.readiness),
        project.result_available && project.readiness !== "result_available" ? badge("Result available", "success") : null)),
    projectActions(project),
    el("div", { style: "height:16px" }),
    el("div", { id: "cryptoPanel" }),
    el("div", { id: "detailPanel" }, detailPanel(project)),
    el("div", { id: "dataAdvanced" }, dataAdvancedPanel(pid)),
    el("div", { id: "savedResults" }),
    el("div", { id: "logsPanel" }));
  loadCrypto(pid);
  loadSavedResults(pid);
  loadProjectLogs(pid);
}

function projectActions(project) {
  const pid = project.id;
  return el("div", { class: "gc-panel" },
    el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Actions"), el("span", {})),
    el("div", { class: "panel-body row wrap" },
      el("button", { class: "gc-button-primary", onclick: () => openContributeData(pid) }, "⬆ Contribute data"),
      el("button", { class: "gc-button-secondary", onclick: () => runProject(pid) }, "▶ Run computation"),
      el("button", { class: "gc-button-secondary", onclick: () => fetchResult(pid) }, "⬇ Get result"),
      el("button", { class: "gc-button-secondary", onclick: () => openAddMember(pid) }, "＋ Add member"),
      el("button", { class: "gc-button-ghost", onclick: () => stopProject(pid) }, "■ Stop"),
      el("span", { class: "spacer" }),
      el("button", { class: "gc-button-danger gc-button-sm", onclick: () => confirmDelete(project) }, "Delete project")));
}

function detailPanel(project) {
  const rows = [];
  const add = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push([k, v]); };
  add("Project ID", el("span", { class: "mono" }, project.id));
  add("Protocol", project.protocol_name);
  add("Description", project.protocol_description);
  add("Readiness", (READINESS[project.readiness] || [project.readiness])[0]);
  add("Job status", project.job_status);
  add("Public context", project.has_context ? "Uploaded" : "Not uploaded");
  add("Datasets", project.vcf_count ?? project.submission_count);
  add("Contributors", project.contributor_count);
  add("Result available", project.result_available ? "Yes" : "No");
  add("Verification", project.protocol_verification_status);
  add("Created", project.created_at);
  if (Array.isArray(project.contributors) && project.contributors.length)
    add("Contributor list", project.contributors.map((c) => c.email || c.username).join(", "));
  const dl = el("dl", { class: "dl" });
  rows.forEach(([k, v]) => { dl.append(el("dt", {}, k), el("dd", {}, v.nodeType ? v : String(v))); });
  return el("div", { class: "gc-panel" },
    el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Details"), el("span", {})),
    el("div", { class: "panel-body" }, rows.length ? dl : el("div", { class: "muted" }, "No metadata.")));
}

/* ------ crypto context panel (full crypto_context CLI surface) ------ */
async function loadCrypto(pid) {
  const panel = $("#cryptoPanel"); if (!panel) return;
  panel.innerHTML = "";
  const body = el("div", { class: "panel-body" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Checking crypto context…"));
  panel.append(el("div", { class: "gc-panel" },
    el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Crypto context"), el("span", { class: "hint" }, "secret key stays local")),
    body));
  let st;
  try { st = await api(`/api/projects/${pid}/crypto`); }
  catch (e) { body.innerHTML = ""; body.append(el("div", { class: "muted" }, e.message)); return; }
  body.innerHTML = "";
  body.append(el("div", { class: "row wrap", style: "margin-bottom:16px" },
    st.has_local ? badge("Local keypair ✓", "success") : badge("No local keypair", "neutral"),
    st.has_server ? badge("Public context on server ✓", "success") : badge("Not on server", "neutral")));
  const cryptoJob = (endpoint, title) => runJob(api(`/api/projects/${pid}/crypto/${endpoint}`, { method: "POST", body: {} }), { title, onDone: () => loadCrypto(pid) });
  const cryptoDelete = async (scope) => {
    try { await api(`/api/projects/${pid}/crypto/delete`, { method: "POST", body: { scope } }); toast(`Deleted ${scope} context`, "ok"); loadCrypto(pid); }
    catch (e) { toast(e.message, "err"); }
  };
  const btns = el("div", { class: "row wrap" });
  const addBtn = (label, cls, enabled, onClick) => btns.append(el("button", { class: cls + " gc-button-sm", disabled: !enabled, onclick: enabled ? onClick : null }, label));
  addBtn("Generate keypair", "gc-button-secondary", !st.has_local && !st.has_server, () => cryptoJob("generate", "Generate crypto context"));
  addBtn("Upload public", "gc-button-secondary", st.has_local && !st.has_server, () => cryptoJob("upload", "Upload public context"));
  addBtn("Generate & upload", "gc-button-secondary", !st.has_local && !st.has_server, () => cryptoJob("generate_upload", "Generate & upload context"));
  addBtn("Download public", "gc-button-secondary", st.has_server, () => cryptoJob("download", "Download public context"));
  addBtn("Delete local", "gc-button-ghost", st.has_local, () => cryptoDelete("local"));
  addBtn("Delete server", "gc-button-ghost", st.has_server, () => cryptoDelete("server"));
  body.append(btns);
}

/* ------ granular data pipeline (encode / encrypt / upload) ------ */
function dataAdvancedPanel(pid) {
  let vcfPath = null;
  const drop = fileDrop((p) => { vcfPath = p; });
  const encoded = el("input", { class: "gc-input", placeholder: "encoded file path (auto-filled by Encode)" });
  const encrypted = el("input", { class: "gc-input", placeholder: "encrypted file path (auto-filled by Encrypt)" });
  const runStep = (input, run) => el("div", { class: "field" },
    el("div", { class: "input-row" }, input, el("button", { class: "gc-button-secondary gc-button-sm", onclick: run }, "Run")));
  return el("details", { class: "adv", style: "margin-top:16px" },
    el("summary", {}, "Advanced: run encode / encrypt / upload separately"),
    el("div", { style: "padding:8px 0 14px" },
      el("div", { class: "field" }, el("label", { class: "gc-label" }, "1 · Encode VCF"), drop.zone,
        el("div", { style: "margin-top:8px" }, el("button", { class: "gc-button-secondary gc-button-sm", onclick: async () => {
          const v = drop.getPath() || vcfPath;
          if (!v) return toast("Add a VCF file first", "err");
          await runJob(api(`/api/projects/${pid}/encode`, { method: "POST", body: { vcf_path: v } }),
            { title: "Encode VCF", onDone: (j) => { if (j.result?.encoded_path) { encoded.value = j.result.encoded_path; toast("Encoded → path filled in step 2", "ok"); } } });
        } }, "Run encode"))),
      el("label", { class: "gc-label" }, "2 · Encrypt encoded file"),
      runStep(encoded, async () => {
        if (!encoded.value.trim()) return toast("Provide the encoded file path", "err");
        await runJob(api(`/api/projects/${pid}/encrypt`, { method: "POST", body: { encoded_path: encoded.value.trim() } }),
          { title: "Encrypt", onDone: (j) => { if (j.result?.encrypted_path) { encrypted.value = j.result.encrypted_path; toast("Encrypted → path filled in step 3", "ok"); } } });
      }),
      el("label", { class: "gc-label" }, "3 · Upload ciphertext"),
      runStep(encrypted, async () => {
        if (!encrypted.value.trim()) return toast("Provide the encrypted file path", "err");
        await runJob(api(`/api/projects/${pid}/upload`, { method: "POST", body: { encrypted_path: encrypted.value.trim() } }),
          { title: "Upload ciphertext", onDone: () => openProject(pid) });
      })));
}

async function loadSavedResults(pid) {
  const panel = $("#savedResults"); if (!panel) return;
  try {
    const { results } = await api(`/api/projects/${pid}/results`);
    panel.innerHTML = "";
    if (!results || !results.length) return;
    const table = el("table", { class: "gc-table" }, el("thead", {}, el("tr", {}, el("th", {}, "Type"), el("th", {}, "File"), el("th", {}, "Size"), el("th", {}, "Saved"))));
    const tb = el("tbody", {});
    results.forEach((r) => {
      const size = r.size_bytes > 1048576 ? (r.size_bytes / 1048576).toFixed(1) + " MB" : r.size_bytes > 1024 ? (r.size_bytes / 1024).toFixed(1) + " KB" : r.size_bytes + " B";
      const when = new Date(r.created_at * 1000).toLocaleString();
      tb.append(el("tr", {}, el("td", {}, r.type === "encrypted" ? "🔒 Encrypted" : "🔓 Decrypted"), el("td", { class: "mono", style: "font-size:12px" }, r.filename), el("td", { class: "mono" }, size), el("td", { class: "muted" }, when)));
    });
    table.append(tb);
    panel.append(el("div", { class: "gc-panel", style: "margin-top:16px" },
      el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Saved results"), badge(`${results.length} files`, "neutral")),
      el("div", { style: "overflow-x:auto" }, table)));
  } catch (_) { panel.innerHTML = ""; }
}

async function loadProjectLogs(pid) {
  const panel = $("#logsPanel"); if (!panel) return;
  try {
    const { logs, message } = await api(`/api/projects/${pid}/logs`);
    panel.innerHTML = "";
    if (!logs) {
      panel.append(el("div", { class: "gc-panel", style: "margin-top:16px" },
        el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Job logs"), el("span", {})),
        el("div", { class: "panel-body muted" }, message || "No jobs have run yet.")));
      return;
    }
    const job = logs.job || {}, events = logs.events || [];
    const list = el("pre", { class: "gc-command-block" },
      events.length ? events.map((e) => `${e.occurred_at || e.timestamp || ""}  ${e.step || e.event_type || ""}  ${e.message || ""}`).join("\n") : "No events.");
    panel.append(el("div", { class: "gc-panel", style: "margin-top:16px" },
      el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Latest job"), readinessBadge(job.status)),
      el("div", { class: "panel-body" }, logs.error_summary ? el("div", { style: "margin-bottom:12px" }, badge(logs.error_summary, "error")) : null, list)));
  } catch (_) { panel.innerHTML = ""; }
}

function openContributeData(pid) {
  let vcfPath = null;
  const drop = fileDrop((p) => { vcfPath = p; });
  modal({
    title: "Contribute encrypted data", sub: "Encode → encrypt → upload. Plaintext never leaves this machine.",
    body: el("div", {}, el("div", { class: "field" }, el("label", { class: "gc-label" }, "VCF file"), drop.zone)),
    actions: [
      { label: "Cancel", class: "gc-button-ghost", onClick: (c) => c() },
      { label: "Encrypt & upload", class: "gc-button-primary", onClick: async (close) => {
        const v = drop.getPath() || vcfPath;
        if (!v) return toast("Add a VCF file first", "err"); close();
        await runJob(api(`/api/projects/${pid}/data`, { method: "POST", body: { vcf_path: v } }), { title: "Contributing data", onDone: () => openProject(pid) });
      } },
    ],
  });
}

async function runProject(pid) {
  try { const out = await api(`/api/projects/${pid}/run`, { method: "POST", body: {} }); toast(`Computation started — job #${shortId(out.job_id)}`, "ok"); setTimeout(() => loadProjectLogs(pid), 900); }
  catch (e) { toast(e.message, "err"); }
}
async function stopProject(pid) {
  try { await api(`/api/projects/${pid}/run`, { method: "POST", body: {} }); }
  catch (_) {}
  // Stop is not supported server-side; surface the CLI's graceful message.
  toast("Stopping a run isn't supported by the server yet.", "");
}
async function fetchResult(pid) {
  await runJob(api(`/api/projects/${pid}/result`, { method: "POST", body: {} }), {
    title: "Downloading & decrypting result",
    onDone: (job) => modal({ title: "Result", sub: "Decrypted locally with your secret key",
      body: el("pre", { class: "gc-command-block" }, JSON.stringify(job.result || {}, null, 2)),
      actions: [{ label: "Close", class: "gc-button-primary", onClick: (c) => c() }] }),
  });
}
function openAddMember(pid) {
  const email = el("input", { class: "gc-input", type: "email", placeholder: "colleague@lab.org" });
  modal({ title: "Add member", sub: "Grant a Gencrypt user access to contribute",
    body: el("div", { class: "field" }, el("label", { class: "gc-label" }, "Email"), email),
    actions: [
      { label: "Cancel", class: "gc-button-ghost", onClick: (c) => c() },
      { label: "Add", class: "gc-button-primary", onClick: async (close) => {
        if (!email.value.trim()) return toast("Enter an email", "err");
        try { await api(`/api/projects/${pid}/members`, { method: "POST", body: { email: email.value.trim() } }); toast(`Added ${email.value.trim()}`, "ok"); close(); openProject(pid); }
        catch (e) { toast(e.message, "err"); }
      } },
    ] });
}
function confirmDelete(project) {
  modal({ title: "Delete project?", sub: "Permanently removes the project and its data.",
    body: el("div", { class: "muted" }, el("p", { style: "margin:0 0 8px" }, "This deletes uploaded ciphertext, results, and the local crypto context. This cannot be undone."), el("p", { class: "mono", style: "margin:0" }, "#" + project.id)),
    actions: [
      { label: "Cancel", class: "gc-button-ghost", onClick: (c) => c() },
      { label: "Delete", class: "gc-button-danger", onClick: async (close) => {
        try { await api(`/api/projects/${project.id}`, { method: "DELETE" }); toast("Project deleted", "ok"); close(); go("projects"); }
        catch (e) { toast(e.message, "err"); }
      } },
    ] });
}

/* ============================================================= PROTOCOLS */
async function viewProtocols() {
  mount(
    head("Protocols", "Researcher-defined analyses from the SecureGenomics GitHub org",
      el("button", { class: "gc-button-secondary", onclick: viewProtocols }, "↻ Refresh")),
    el("div", { id: "protoList" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Discovering protocols on GitHub…")));
  try {
    const [{ protocols }, localRes] = await Promise.all([api("/api/protocols"), api("/api/protocols/local").catch(() => ({ protocols: [] }))]);
    const localSet = new Set((localRes.protocols || []).map(String));
    const box = $("#protoList"); if (!box) return; box.innerHTML = "";
    if (!protocols.length) { box.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "No protocols found"), el("div", {}, "Check your connection to GitHub."))); return; }
    const grid = el("div", { class: "grid grid--cards" });
    protocols.forEach((p) => grid.append(protocolCard(p, localSet.has(p.name))));
    box.append(grid);
  } catch (e) { const box = $("#protoList"); if (box) { box.innerHTML = ""; box.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "Couldn't load protocols"), el("div", {}, e.message))); } }
}
function protocolCard(p, cached) {
  const modes = []; if (p.local_supported) modes.push("Local"); if (p.aggregated_supported) modes.push("Aggregated");
  const fetchBtn = el("button", { class: "gc-button-secondary gc-button-sm" }, cached ? "↻ Refresh" : "⬇ Fetch");
  fetchBtn.onclick = async () => {
    fetchBtn.disabled = true; fetchBtn.textContent = cached ? "Refreshing…" : "Fetching…";
    try { await api(cached ? "/api/protocols/refresh" : "/api/protocols/fetch", { method: "POST", body: { name: p.name } }); toast(`${p.name} ${cached ? "refreshed" : "fetched"}`, "ok"); viewProtocols(); }
    catch (e) { toast(e.message, "err"); fetchBtn.disabled = false; fetchBtn.textContent = cached ? "↻ Refresh" : "⬇ Fetch"; }
  };
  const verifyBtn = el("button", { class: "gc-button-ghost gc-button-sm", disabled: !cached }, "Verify");
  verifyBtn.onclick = async () => {
    verifyBtn.disabled = true; verifyBtn.textContent = "Verifying…";
    try { const { valid } = await api("/api/protocols/verify", { method: "POST", body: { name: p.name } }); toast(`${p.name} ${valid ? "verified ✓" : "failed verification"}`, valid ? "ok" : "err"); }
    catch (e) { toast(e.message, "err"); }
    finally { verifyBtn.disabled = false; verifyBtn.textContent = "Verify"; }
  };
  return el("div", { class: "gc-card", style: "padding:18px" },
    el("div", { class: "card-top" },
      el("div", {}, el("div", { class: "card-title" }, p.name), p.version ? el("div", { class: "card-id" }, "v" + p.version) : null),
      cached ? badge("Cached", "success") : null),
    p.description ? el("div", { class: "card-desc" }, p.description) : null,
    el("div", { class: "card-row" },
      ...modes.map((m) => badge(m, "neutral")), p.analysis_type ? badge(p.analysis_type, "neutral") : null,
      el("span", { class: "spacer" }), verifyBtn, fetchBtn));
}

/* =========================================================== LOCAL VIEW */
async function viewLocal() {
  const protoSel = el("select", { class: "gc-select" }, el("option", { value: "" }, "Loading cached protocols…"));
  let vcfPath = null;
  const drop = fileDrop((p) => { vcfPath = p; });
  const run = el("button", { class: "gc-button-primary" }, "Run local analysis");
  run.onclick = async () => {
    if (!protoSel.value) return toast("Choose a protocol", "err");
    const v = drop.getPath() || vcfPath;
    if (!v) return toast("Add a VCF file first", "err");
    await runJob(api("/api/local/analyze", { method: "POST", body: { protocol_name: protoSel.value, vcf_path: v } }),
      { title: "Local analysis (offline)", onDone: (job) => modal({ title: "Local result", sub: "Computed entirely offline",
        body: el("pre", { class: "gc-command-block" }, (job.result && job.result.output) || "Done."),
        actions: [{ label: "Close", class: "gc-button-primary", onClick: (c) => c() }] }) });
  };
  mount(
    head("Local analysis", "Run a protocol fully offline — no encryption, no server, no upload"),
    el("div", { class: "gc-panel" },
      el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Analyze a VCF on this machine"), el("span", {})),
      el("div", { class: "panel-body" },
        el("div", { class: "field" }, el("label", { class: "gc-label" }, "Protocol (cached)"), protoSel),
        el("div", { class: "field" }, el("label", { class: "gc-label" }, "VCF file"), drop.zone),
        el("div", { class: "hint", style: "margin:6px 0 16px" }, "Only locally cached protocols run offline. Fetch a protocol first from the Protocols tab."),
        run)));
  try {
    const { protocols } = await api("/api/protocols/local");
    protoSel.innerHTML = "";
    if (!protocols.length) protoSel.append(el("option", { value: "" }, "No cached protocols — fetch one first"));
    else { protoSel.append(el("option", { value: "" }, "— select —")); protocols.forEach((n) => protoSel.append(el("option", { value: n }, n))); }
  } catch (_) { protoSel.innerHTML = ""; protoSel.append(el("option", { value: "" }, "Could not load")); }
}

/* =========================================================== ACTIVITY */
async function viewActivity() {
  mount(head("Activity", "Background jobs run through the CLI engine this session", el("button", { class: "gc-button-secondary", onclick: viewActivity }, "↻ Refresh")),
    el("div", { id: "actList" }, el("div", { class: "muted" }, "Loading…")));
  try {
    const { jobs } = await api("/api/jobs"); const box = $("#actList"); if (!box) return; box.innerHTML = "";
    if (!jobs.length) { box.append(el("div", { class: "empty" }, el("div", { class: "empty-title" }, "Nothing yet"), el("div", {}, "Jobs you start will appear here."))); return; }
    jobs.forEach((j) => {
      const when = new Date(j.created_at * 1000).toLocaleTimeString();
      const kind = j.status === "succeeded" ? "success" : j.status === "failed" ? "error" : "info";
      box.append(el("div", { class: "gc-card", style: "padding:16px;margin-bottom:10px" },
        el("div", { class: "card-top" }, el("div", {}, el("div", { class: "card-title" }, j.title), el("div", { class: "card-id" }, when)), badge(j.status, kind)),
        j.error ? el("div", { class: "card-desc", style: "color:var(--gc-error)" }, j.error) : null));
    });
  } catch (e) { const box = $("#actList"); if (box) { box.innerHTML = ""; box.append(el("div", { class: "empty" }, el("div", {}, e.message))); } }
}

/* =========================================================== SYSTEM VIEW */
async function viewSystem() {
  mount(head("System", "CLI engine status and maintenance",
    el("button", { class: "gc-button-secondary", onclick: viewSystem }, "↻ Refresh")),
    el("div", { id: "sysBody" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Loading…")));
  let sys;
  try { sys = (await api("/api/system/status")).system; state.system = { ...sys, cli_version: state.system?.cli_version }; renderConn(); }
  catch (e) { const b = $("#sysBody"); if (b) { b.innerHTML = ""; b.append(el("div", { class: "empty" }, el("div", {}, e.message))); } return; }
  const dl = el("dl", { class: "dl" });
  const add = (k, v) => { dl.append(el("dt", {}, k), el("dd", {}, v.nodeType ? v : String(v))); };
  add("CLI version", state.system?.cli_version || "—");
  add("Server URL", el("span", { class: "mono" }, sys.server_url));
  add("Server connection", sys.server_connected ? badge("Connected", "success") : badge("Offline", "error"));
  add("Authenticated", sys.authenticated ? "Yes" : "No");
  add("Current user", sys.username || state.user?.email || "—");
  add("Config directory", el("span", { class: "mono", style: "font-size:12px" }, sys.config_dir));
  add("Cached protocols", sys.cached_protocols);
  if (sys.github_org) add("GitHub org", sys.github_org);
  const b = $("#sysBody"); if (!b) return; b.innerHTML = "";
  b.append(
    el("div", { class: "gc-panel" }, el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Status"), el("span", {})), el("div", { class: "panel-body" }, dl)),
    el("div", { class: "gc-panel", style: "margin-top:16px" },
      el("div", { class: "panel-head" }, el("div", { class: "gc-panel-title" }, "Maintenance"), el("span", {})),
      el("div", { class: "panel-body row wrap" },
        el("button", { class: "gc-button-secondary", onclick: confirmClearCache }, "Clear local cache"),
        el("button", { class: "gc-button-ghost", onclick: confirmDeleteProfile }, "Delete profile"),
        el("div", { class: "hint", style: "flex-basis:100%;margin-top:8px" }, "Clearing the cache removes all local data (tokens, protocols, crypto contexts, results) and signs you out of every account."))));
}
function confirmClearCache() {
  modal({ title: "Clear local cache?", sub: "Removes ~/.securegenomics entirely",
    body: el("div", { class: "muted" }, "This deletes all local configs, auth tokens, cached protocols, local crypto contexts (secret keys), and saved results. It cannot be undone and signs you out of all accounts."),
    actions: [
      { label: "Cancel", class: "gc-button-ghost", onClick: (c) => c() },
      { label: "Clear cache", class: "gc-button-danger", onClick: async (close) => {
        try { await api("/api/system/clear-cache", { method: "POST", body: {} }); toast("Cache cleared", "ok"); close(); state.user = null; renderAuth("login"); }
        catch (e) { toast(e.message, "err"); }
      } },
    ] });
}
function confirmDeleteProfile() {
  api("/api/account/delete-profile", { method: "POST", body: {} })
    .then((out) => modal({ title: "Delete profile", sub: "Account deletion",
      body: el("pre", { class: "gc-command-block" }, (out.console || "").trim() || "Account deletion is not available from the CLI yet."),
      actions: [{ label: "OK", class: "gc-button-primary", onClick: (c) => c() }] }))
    .catch((e) => toast(e.message, "err"));
}

/* =============================================================== BOOT */
async function boot() {
  try {
    const data = await api("/api/bootstrap");
    state.system = { ...data.system, cli_version: data.cli_version }; state.user = data.user;
    if (state.user && state.user.email) renderShell(); else renderAuth("login");
  } catch (e) { $("#boot").textContent = "Could not reach the local engine: " + e.message; }
}
boot();
