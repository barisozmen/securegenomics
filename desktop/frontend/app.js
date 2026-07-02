/* SecureGenomics Desktop — SPA controller.
   Talks only to the local bridge, which forwards to the CLI engine. */

const TOKEN = window.__SG_TOKEN__;

/* ------------------------------------------------------------------ API */
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      "X-SG-Token": TOKEN,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* --------------------------------------------------------------- helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return node;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const shortId = (id) => (id ? String(id).slice(0, 8) : "—");

function toast(msg, kind = "") {
  const host = $("#toasts");
  const t = el("div", { class: `toast ${kind ? "toast--" + kind : ""}` },
    el("span", {}, msg),
    el("span", { class: "toast__x", onclick: () => t.remove() }, "✕"));
  host.append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 4000);
}

/* --------------------------------------------------------------- modal */
function modal({ title, sub, body, actions }) {
  const host = $("#modalHost");
  host.hidden = false;
  host.innerHTML = "";
  const close = () => { host.hidden = true; host.innerHTML = ""; };
  const foot = el("div", { class: "modal__foot" });
  (actions || []).forEach((a) => {
    const b = el("button", { class: `btn ${a.class || ""}`, onclick: () => a.onClick(close) }, a.label);
    foot.append(b);
  });
  const card = el("div", { class: "modal" },
    el("div", { class: "modal__head" },
      el("div", { class: "modal__title" }, title),
      sub ? el("div", { class: "modal__sub" }, sub) : null),
    el("div", { class: "modal__body" }, body),
    actions ? foot : null);
  host.append(card);
  host.onclick = (e) => { if (e.target === host) close(); };
  return { close, card };
}

/* --------------------------------------------------------- status badge */
function statusBadge(status) {
  const s = (status || "unknown").toLowerCase();
  const map = {
    completed: ["ok", "Completed"], succeeded: ["ok", "Completed"], done: ["ok", "Completed"],
    running: ["run", "Running"], pending: ["run", "Pending"], queued: ["run", "Queued"],
    failed: ["err", "Failed"], error: ["err", "Failed"],
  };
  const [cls, label] = map[s] || ["", status || "Unknown"];
  return el("span", { class: `badge ${cls ? "badge--" + cls : ""}` },
    el("span", { class: "badge__dot" }), label);
}

/* ----------------------------------------------------------------- state */
const state = { system: null, user: null, view: "overview" };

/* ------------------------------------------------------------ job runner */
/* Opens a modal that live-polls a background job and shows steps + output. */
async function runJob(startPromise, { title, onDone } = {}) {
  const stepsBox = el("div", { class: "steps" }, el("div", { class: "muted" }, "Starting…"));
  const consoleBox = el("pre", { class: "console" });
  const m = modal({
    title: title || "Working…",
    sub: "Running through the SecureGenomics CLI engine",
    body: el("div", {}, stepsBox, el("div", { style: "height:14px" }), consoleBox),
    actions: [{ label: "Close", class: "btn--ghost", onClick: (close) => close() }],
  });

  let jobId;
  try {
    const { job } = await startPromise;
    jobId = job.id;
  } catch (e) {
    stepsBox.innerHTML = "";
    stepsBox.append(el("div", { class: "badge badge--err" }, "Failed to start"));
    consoleBox.textContent = e.message;
    return;
  }

  const renderJob = (job) => {
    stepsBox.innerHTML = "";
    (job.steps || []).forEach((s) => {
      const cls = s.status === "done" ? "step--done" : s.status === "running" ? "step--running" : "step--pending";
      stepsBox.append(el("div", { class: `step ${cls}` }, el("span", { class: "step__dot" }), s.name));
    });
    if (!job.steps || !job.steps.length) stepsBox.append(el("div", { class: "muted" }, "Working…"));
    consoleBox.textContent = (job.log || []).join("\n");
    consoleBox.scrollTop = consoleBox.scrollHeight;
  };

  return new Promise((resolve) => {
    const poll = async () => {
      let job;
      try { ({ job } = await api(`/api/jobs/${jobId}`)); }
      catch (_) { return setTimeout(poll, 900); }
      renderJob(job);
      if (job.status === "running") return setTimeout(poll, 800);
      // terminal
      m.card.querySelector(".modal__sub").textContent =
        job.status === "succeeded" ? "Completed" : "Failed";
      if (job.status === "succeeded") { toast(`${job.title} — done`, "ok"); onDone && onDone(job); }
      else toast(job.error || "Job failed", "err");
      resolve(job);
    };
    poll();
  });
}

/* =========================================================== AUTH SCREEN */
function renderAuth(mode = "login") {
  const main = $("#main");
  $("#nav").hidden = true;
  $("#acct").hidden = true;
  document.querySelector(".app").classList.remove("is-loading");

  const isLogin = mode === "login";
  const email = el("input", { class: "input", type: "email", placeholder: "you@lab.org", autofocus: true });
  const pass = el("input", { class: "input", type: "password", placeholder: "••••••••" });
  const submit = el("button", { class: "btn btn--primary", style: "width:100%;justify-content:center" },
    isLogin ? "Sign in" : "Create account");

  const doAuth = async () => {
    submit.disabled = true;
    submit.textContent = isLogin ? "Signing in…" : "Creating…";
    try {
      const out = await api(isLogin ? "/api/auth/login" : "/api/auth/register", {
        method: "POST", body: { email: email.value.trim(), password: pass.value },
      });
      state.system = out.system; state.user = out.user;
      toast(isLogin ? "Signed in" : "Account created", "ok");
      state.view = "overview";
      renderShell();
    } catch (e) {
      toast(e.message, "err");
      submit.disabled = false;
      submit.textContent = isLogin ? "Sign in" : "Create account";
    }
  };
  submit.addEventListener("click", doAuth);
  pass.addEventListener("keydown", (e) => { if (e.key === "Enter") doAuth(); });

  main.innerHTML = "";
  main.append(el("div", { class: "auth" },
    el("div", { class: "auth__card" },
      el("div", { class: "auth__brand" },
        el("span", { class: "brand__mark" }), el("span", { class: "brand__word" }, "SecureGenomics")),
      el("h1", { class: "auth__title" }, isLogin ? "Welcome back" : "Create your account"),
      el("p", { class: "auth__sub" }, isLogin
        ? "Sign in to your Gencrypt account to manage encrypted analyses."
        : "Register a Gencrypt account. Your FHE secret key is generated and stays on this device."),
      el("div", { class: "field" }, el("label", { class: "field__label" }, "Email"), email),
      el("div", { class: "field" }, el("label", { class: "field__label" }, "Password"), pass),
      submit,
      el("div", { class: "auth__switch" },
        isLogin ? "New to SecureGenomics? " : "Already have an account? ",
        el("button", { onclick: () => renderAuth(isLogin ? "register" : "login") },
          isLogin ? "Create one" : "Sign in")),
      el("div", { class: "auth__note" },
        el("span", {}, "🔒"),
        el("span", {}, "The secret key never leaves this machine. Only ciphertext and the public context are ever uploaded.")))));
}

/* ============================================================ APP SHELL */
function renderShell() {
  document.querySelector(".app").classList.remove("is-loading");
  const nav = $("#nav");
  nav.hidden = false;
  nav.querySelectorAll(".nav__item").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.view === state.view);
    b.onclick = () => { state.view = b.dataset.view; renderShell(); };
  });
  renderConn();
  renderAccount();
  const views = { overview: viewOverview, projects: viewProjects, protocols: viewProtocols, local: viewLocal, activity: viewActivity };
  (views[state.view] || viewOverview)();
}

function markNav() {
  const nav = $("#nav");
  if (!nav) return;
  nav.querySelectorAll(".nav__item").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.view === state.view));
}

function renderConn() {
  const sys = state.system || {};
  const dot = $("#connDot"), label = $("#connLabel");
  dot.className = "conn__dot " + (sys.server_connected ? "is-ok" : "is-bad");
  label.textContent = sys.server_connected ? "Connected" : "Offline";
  $("#conn").title = sys.server_url || "";
}

function renderAccount() {
  const acct = $("#acct");
  if (state.user && state.user.email) {
    acct.hidden = false;
    $("#acctEmail").textContent = state.user.email;
    $("#signOut").onclick = async () => {
      try { const out = await api("/api/auth/logout", { method: "POST" });
        state.system = out.system; state.user = null; toast("Signed out", "ok"); renderAuth("login"); }
      catch (e) { toast(e.message, "err"); }
    };
  } else { acct.hidden = true; }
}

function head(title, sub, ...actions) {
  return el("div", { class: "view__head" },
    el("div", {}, el("h1", { class: "view__title" }, title), sub ? el("div", { class: "view__sub" }, sub) : null),
    el("div", { class: "row" }, ...actions));
}

function mount(...nodes) {
  const main = $("#main");
  main.innerHTML = "";
  main.append(el("div", { class: "view" }, ...nodes));
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
      statCard("CLI version", sys.cli_version || sys.version || "—", "engine")),
    el("div", { style: "height:22px" }),
    el("div", { class: "panel" },
      el("div", { class: "panel__head" },
        el("div", { class: "panel__title" }, "Quick actions"), el("span", {})),
      el("div", { class: "panel__body row", style: "flex-wrap:wrap;gap:10px" },
        el("button", { class: "btn btn--primary", onclick: openCreateProject }, "＋ New project"),
        el("button", { class: "btn", onclick: () => { state.view = "protocols"; renderShell(); } }, "Browse protocols"),
        el("button", { class: "btn", onclick: () => { state.view = "local"; renderShell(); } }, "Run local analysis"))),
    el("div", { style: "height:16px" }),
    custodyNote());

  try {
    const { projects } = await api("/api/projects");
    const stats = $("#ovStats");
    if (!stats) return; // navigated away mid-fetch
    stats.firstChild.querySelector(".stat__v").textContent = projects.length;
    stats.firstChild.querySelector(".stat__meta").textContent =
      projects.length === 1 ? "1 project" : `${projects.length} projects`;
  } catch (_) {}
}

function statCard(k, v, meta) {
  return el("div", { class: "stat" },
    el("div", { class: "stat__k" }, k),
    el("div", { class: "stat__v num" }, String(v)),
    el("div", { class: "stat__meta" }, meta || ""));
}

function custodyNote() {
  return el("div", { class: "panel" },
    el("div", { class: "panel__head" }, el("div", { class: "panel__title" }, "Privacy custody"), el("span", {})),
    el("div", { class: "panel__body", style: "color:var(--muted);font-size:13px" },
      el("p", { style: "margin:0 0 8px" },
        "Encoding and encryption happen locally on this machine using Fully Homomorphic Encryption. ",
        "The FHE secret key is generated here and never uploaded."),
      el("p", { style: "margin:0" },
        "Only ciphertext, the public crypto context, and encryption stats reach the server. ",
        "Results are downloaded encrypted and decrypted locally.")));
}

/* ============================================================== PROJECTS */
async function viewProjects() {
  mount(
    head("Projects", "Aggregated, encrypted analyses you own or contribute to",
      el("button", { class: "btn btn--primary", onclick: openCreateProject }, "＋ New project")),
    el("div", { id: "projList" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Loading projects…")));

  try {
    const { projects } = await api("/api/projects");
    const box = $("#projList");
    if (!box) return; // navigated away mid-fetch
    box.innerHTML = "";
    if (!projects.length) {
      box.append(el("div", { class: "empty" },
        el("div", { class: "empty__title" }, "No projects yet"),
        el("div", {}, "Create a project from a protocol to start contributing encrypted data."),
        el("div", { style: "margin-top:16px" },
          el("button", { class: "btn btn--primary", onclick: openCreateProject }, "＋ New project"))));
      return;
    }
    const grid = el("div", { class: "grid grid--cards" });
    projects.forEach((p) => grid.append(projectCard(p)));
    box.append(grid);
  } catch (e) {
    $("#projList").innerHTML = "";
    $("#projList").append(el("div", { class: "empty" }, el("div", { class: "empty__title" }, "Couldn't load projects"), el("div", {}, e.message)));
  }
}

function projectCard(p) {
  const title = p.protocol_name || p.name || p.protocol || "Project";
  return el("div", { class: "card card--link", onclick: () => openProject(p.id) },
    el("div", { class: "card__top" },
      el("div", {},
        el("div", { class: "card__title" }, title),
        el("div", { class: "card__id mono" }, "#" + shortId(p.id))),
      statusBadge(p.status)),
    p.description ? el("div", { class: "card__desc" }, p.description) : null,
    el("div", { class: "card__row" },
      p.role ? el("span", { class: "badge" }, p.role) : null,
      typeof p.member_count === "number" ? el("span", { class: "badge" }, `${p.member_count} members`) : null,
      typeof p.data_count === "number" ? el("span", { class: "badge" }, `${p.data_count} datasets`) : null));
}

function openCreateProject() {
  const select = el("select", { class: "select" }, el("option", { value: "" }, "Loading protocols…"));
  const manual = el("input", { class: "input", placeholder: "or type a protocol name, e.g. alzheimers-risk" });
  const body = el("div", {},
    el("div", { class: "field" }, el("label", { class: "field__label" }, "Protocol"), select),
    el("div", { class: "field" }, el("label", { class: "field__label" }, "Or enter manually"), manual),
    el("div", { class: "hint" }, "Creating a project also generates your FHE keypair and uploads only the public context."));

  const m = modal({
    title: "New project", sub: "Pick a protocol to compute on",
    body,
    actions: [
      { label: "Cancel", class: "btn--ghost", onClick: (c) => c() },
      { label: "Create", class: "btn--primary", onClick: async (close) => {
        const name = manual.value.trim() || select.value;
        if (!name) return toast("Choose a protocol", "err");
        close();
        await runJob(api("/api/projects", { method: "POST", body: { protocol_name: name } }),
          { title: "Creating project", onDone: () => { state.view = "projects"; renderShell(); } });
      } },
    ],
  });

  api("/api/protocols").then(({ protocols }) => {
    select.innerHTML = "";
    select.append(el("option", { value: "" }, "— select a protocol —"));
    protocols.forEach((p) => select.append(el("option", { value: p.name }, `${p.name}${p.description ? " — " + p.description : ""}`)));
  }).catch(() => { select.innerHTML = ""; select.append(el("option", { value: "" }, "Could not load — type manually")); });
}

/* ------------------------------------------------------ project detail */
async function openProject(pid) {
  state.view = "projects";
  markNav();
  mount(
    el("button", { class: "back", onclick: () => viewProjects() }, "← All projects"),
    el("div", { id: "projDetail" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Loading…")));

  let project;
  try { ({ project } = await api(`/api/projects/${pid}`)); }
  catch (e) { $("#projDetail").innerHTML = ""; $("#projDetail").append(el("div", { class: "empty" }, el("div", { class: "empty__title" }, "Not found"), el("div", {}, e.message))); return; }

  const title = project.protocol_name || project.name || "Project";
  const box = $("#projDetail");
  box.innerHTML = "";
  box.append(
    el("div", { class: "view__head" },
      el("div", {},
        el("h1", { class: "view__title" }, title),
        el("div", { class: "view__sub mono" }, "#" + project.id)),
      el("div", { class: "row" }, statusBadge(project.status || project.latest_job_status))),
    projectActions(project),
    el("div", { style: "height:16px" }),
    detailPanel(project),
    el("div", { id: "logsPanel" }));

  loadProjectLogs(pid);
}

function projectActions(project) {
  const pid = project.id;
  return el("div", { class: "panel" },
    el("div", { class: "panel__head" }, el("div", { class: "panel__title" }, "Actions"), el("span", {})),
    el("div", { class: "panel__body row", style: "flex-wrap:wrap;gap:9px" },
      el("button", { class: "btn btn--primary", onclick: () => openContributeData(pid) }, "⬆ Contribute data"),
      el("button", { class: "btn", onclick: () => runProject(pid) }, "▶ Run computation"),
      el("button", { class: "btn", onclick: () => fetchResult(pid) }, "⬇ Get result"),
      el("button", { class: "btn", onclick: () => openAddMember(pid) }, "＋ Add member"),
      el("span", { class: "spacer" }),
      el("button", { class: "btn btn--danger btn--sm", onclick: () => confirmDelete(project) }, "Delete")));
}

function detailPanel(project) {
  const rows = [];
  const add = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push([k, v]); };
  add("Project ID", el("span", { class: "mono" }, project.id));
  add("Protocol", project.protocol_name || project.protocol);
  add("Status", project.status || project.latest_job_status || "—");
  add("Owner", project.owner_email || project.owner || (project.is_owner ? "You" : undefined));
  add("Members", project.member_count ?? (project.members ? project.members.length : undefined));
  add("Datasets", project.data_count ?? project.uploads_count);
  add("Crypto context", project.has_crypto_context === false ? "Not uploaded" : (project.has_crypto_context ? "Uploaded" : undefined));
  add("Created", project.created_at);
  if (project.description) add("Description", project.description);

  const dl = el("dl", { class: "dl" });
  rows.forEach(([k, v]) => { dl.append(el("dt", {}, k), el("dd", {}, v.nodeType ? v : String(v))); });
  return el("div", { class: "panel" },
    el("div", { class: "panel__head" }, el("div", { class: "panel__title" }, "Details"), el("span", {})),
    el("div", { class: "panel__body" }, rows.length ? dl : el("div", { class: "muted" }, "No metadata available.")));
}

async function loadProjectLogs(pid) {
  const panel = $("#logsPanel");
  if (!panel) return;
  try {
    const { logs, message } = await api(`/api/projects/${pid}/logs`);
    panel.innerHTML = "";
    if (!logs) {
      panel.append(el("div", { class: "panel" },
        el("div", { class: "panel__head" }, el("div", { class: "panel__title" }, "Job logs"), el("span", {})),
        el("div", { class: "panel__body muted" }, message || "No jobs have run yet.")));
      return;
    }
    const job = logs.job || {};
    const events = logs.events || [];
    const list = el("div", { class: "console" },
      events.length
        ? events.map((e) => `${e.occurred_at || e.timestamp || ""}  ${e.step || e.event_type || ""}  ${e.message || ""}`).join("\n")
        : "No events.");
    panel.append(el("div", { class: "panel" },
      el("div", { class: "panel__head" },
        el("div", { class: "panel__title" }, "Latest job"),
        statusBadge(job.status)),
      el("div", { class: "panel__body" },
        logs.error_summary ? el("div", { class: "badge badge--err", style: "margin-bottom:12px" }, esc(logs.error_summary)) : null,
        list)));
  } catch (e) {
    panel.innerHTML = "";
  }
}

function openContributeData(pid) {
  const path = el("input", { class: "input", placeholder: "/path/to/sample.vcf" });
  const browse = el("button", { class: "btn", onclick: async () => {
    try {
      const { path: picked, supported } = await api("/api/pick-file", { method: "POST", body: {} });
      if (!supported) return toast("Type the file path (native picker needs the desktop window)", "");
      if (picked) path.value = picked;
    } catch (e) { toast(e.message, "err"); }
  } }, "Browse…");

  modal({
    title: "Contribute encrypted data",
    sub: "Encode → encrypt → upload. Plaintext never leaves this machine.",
    body: el("div", {},
      el("div", { class: "field" },
        el("label", { class: "field__label" }, "VCF file"),
        el("div", { class: "input-row" }, path, browse)),
      el("div", { class: "hint" }, "The VCF is encoded and FHE-encrypted locally; only ciphertext + stats are uploaded.")),
    actions: [
      { label: "Cancel", class: "btn--ghost", onClick: (c) => c() },
      { label: "Encrypt & upload", class: "btn--primary", onClick: async (close) => {
        const v = path.value.trim();
        if (!v) return toast("Choose a VCF file", "err");
        close();
        await runJob(api(`/api/projects/${pid}/data`, { method: "POST", body: { vcf_path: v } }),
          { title: "Contributing data", onDone: () => openProject(pid) });
      } },
    ],
  });
}

async function runProject(pid) {
  try {
    const out = await api(`/api/projects/${pid}/run`, { method: "POST", body: {} });
    toast(`Computation started — job #${shortId(out.job_id)}`, "ok");
    setTimeout(() => loadProjectLogs(pid), 800);
  } catch (e) { toast(e.message, "err"); }
}

async function fetchResult(pid) {
  await runJob(api(`/api/projects/${pid}/result`, { method: "POST", body: {} }), {
    title: "Downloading & decrypting result",
    onDone: (job) => {
      const r = job.result || {};
      modal({
        title: "Result", sub: "Decrypted locally with your secret key",
        body: el("pre", { class: "console" }, JSON.stringify(r, null, 2)),
        actions: [{ label: "Close", class: "btn--primary", onClick: (c) => c() }],
      });
    },
  });
}

function openAddMember(pid) {
  const email = el("input", { class: "input", type: "email", placeholder: "colleague@lab.org" });
  modal({
    title: "Add member", sub: "Grant a Gencrypt user access to contribute",
    body: el("div", { class: "field" }, el("label", { class: "field__label" }, "Email"), email),
    actions: [
      { label: "Cancel", class: "btn--ghost", onClick: (c) => c() },
      { label: "Add", class: "btn--primary", onClick: async (close) => {
        const v = email.value.trim();
        if (!v) return toast("Enter an email", "err");
        try { await api(`/api/projects/${pid}/members`, { method: "POST", body: { email: v } });
          toast(`Added ${v}`, "ok"); close(); }
        catch (e) { toast(e.message, "err"); }
      } },
    ],
  });
}

function confirmDelete(project) {
  modal({
    title: "Delete project?", sub: "This permanently removes the project and its data.",
    body: el("div", { class: "muted" },
      el("p", { style: "margin:0 0 8px" }, "This deletes uploaded ciphertext, results, and the local crypto context. This cannot be undone."),
      el("p", { class: "mono", style: "margin:0" }, "#" + project.id)),
    actions: [
      { label: "Cancel", class: "btn--ghost", onClick: (c) => c() },
      { label: "Delete", class: "btn--danger", onClick: async (close) => {
        try { await api(`/api/projects/${project.id}`, { method: "DELETE" });
          toast("Project deleted", "ok"); close(); state.view = "projects"; renderShell(); }
        catch (e) { toast(e.message, "err"); }
      } },
    ],
  });
}

/* ============================================================= PROTOCOLS */
async function viewProtocols() {
  mount(
    head("Protocols", "Researcher-defined analyses from the SecureGenomics GitHub org",
      el("button", { class: "btn", id: "refreshProto", onclick: viewProtocols }, "↻ Refresh")),
    el("div", { id: "protoList" }, el("div", { class: "muted row" }, el("span", { class: "spinner" }), " Discovering protocols on GitHub…")));

  try {
    const [{ protocols }, localRes] = await Promise.all([
      api("/api/protocols"),
      api("/api/protocols/local").catch(() => ({ protocols: [] })),
    ]);
    const localSet = new Set((localRes.protocols || []).map(String));
    const box = $("#protoList");
    if (!box) return; // navigated away mid-fetch
    box.innerHTML = "";
    if (!protocols.length) {
      box.append(el("div", { class: "empty" }, el("div", { class: "empty__title" }, "No protocols found"), el("div", {}, "Check your connection to GitHub.")));
      return;
    }
    const grid = el("div", { class: "grid grid--cards" });
    protocols.forEach((p) => grid.append(protocolCard(p, localSet.has(p.name))));
    box.append(grid);
  } catch (e) {
    $("#protoList").innerHTML = "";
    $("#protoList").append(el("div", { class: "empty" }, el("div", { class: "empty__title" }, "Couldn't load protocols"), el("div", {}, e.message)));
  }
}

function protocolCard(p, cached) {
  const modes = [];
  if (p.local_supported) modes.push("Local");
  if (p.aggregated_supported) modes.push("Aggregated");
  const btn = el("button", { class: "btn btn--sm" }, cached ? "↻ Refresh" : "⬇ Fetch");
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = cached ? "Refreshing…" : "Fetching…";
    try {
      await api(cached ? "/api/protocols/refresh" : "/api/protocols/fetch", { method: "POST", body: { name: p.name } });
      toast(`${p.name} ${cached ? "refreshed" : "fetched"}`, "ok"); viewProtocols();
    } catch (e) { toast(e.message, "err"); btn.disabled = false; btn.textContent = cached ? "↻ Refresh" : "⬇ Fetch"; }
  };
  return el("div", { class: "card" },
    el("div", { class: "card__top" },
      el("div", {},
        el("div", { class: "card__title" }, p.name),
        p.version ? el("div", { class: "card__id" }, "v" + p.version) : null),
      cached ? el("span", { class: "badge badge--ok" }, el("span", { class: "badge__dot" }), "Cached") : null),
    p.description ? el("div", { class: "card__desc" }, p.description) : null,
    el("div", { class: "card__row" },
      ...modes.map((mo) => el("span", { class: "badge" }, mo)),
      p.analysis_type ? el("span", { class: "badge" }, p.analysis_type) : null,
      el("span", { class: "spacer" }), btn));
}

/* =========================================================== LOCAL VIEW */
async function viewLocal() {
  const protoSel = el("select", { class: "select" }, el("option", { value: "" }, "Loading cached protocols…"));
  const path = el("input", { class: "input", placeholder: "/path/to/sample.vcf" });
  const browse = el("button", { class: "btn", onclick: async () => {
    try { const { path: picked, supported } = await api("/api/pick-file", { method: "POST", body: {} });
      if (!supported) return toast("Type the file path (native picker needs the desktop window)", "");
      if (picked) path.value = picked; } catch (e) { toast(e.message, "err"); }
  } }, "Browse…");
  const run = el("button", { class: "btn btn--primary" }, "Run local analysis");
  run.onclick = async () => {
    const name = protoSel.value; const v = path.value.trim();
    if (!name) return toast("Choose a protocol", "err");
    if (!v) return toast("Choose a VCF file", "err");
    await runJob(api("/api/local/analyze", { method: "POST", body: { protocol_name: name, vcf_path: v } }),
      { title: "Local analysis (offline)", onDone: (job) => {
        modal({ title: "Local result", sub: "Computed entirely offline",
          body: el("pre", { class: "console" }, (job.result && job.result.output) || "Done."),
          actions: [{ label: "Close", class: "btn--primary", onClick: (c) => c() }] });
      } });
  };

  mount(
    head("Local analysis", "Run a protocol fully offline — no encryption, no server, no upload"),
    el("div", { class: "panel" },
      el("div", { class: "panel__head" }, el("div", { class: "panel__title" }, "Analyze a VCF on this machine"), el("span", {})),
      el("div", { class: "panel__body" },
        el("div", { class: "field" }, el("label", { class: "field__label" }, "Protocol (cached)"), protoSel),
        el("div", { class: "field" },
          el("label", { class: "field__label" }, "VCF file"),
          el("div", { class: "input-row" }, path, browse)),
        el("div", { class: "hint", style: "margin-bottom:16px" }, "Only locally cached protocols run offline. Fetch a protocol first from the Protocols tab."),
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
  mount(
    head("Activity", "Background jobs run through the CLI engine this session",
      el("button", { class: "btn", onclick: viewActivity }, "↻ Refresh")),
    el("div", { id: "actList" }, el("div", { class: "muted" }, "Loading…")));
  try {
    const { jobs } = await api("/api/jobs");
    const box = $("#actList");
    if (!box) return; // navigated away mid-fetch
    box.innerHTML = "";
    if (!jobs.length) { box.append(el("div", { class: "empty" }, el("div", { class: "empty__title" }, "Nothing yet"), el("div", {}, "Jobs you start will appear here."))); return; }
    jobs.forEach((j) => {
      const when = new Date(j.created_at * 1000).toLocaleTimeString();
      box.append(el("div", { class: "card", style: "margin-bottom:10px" },
        el("div", { class: "card__top" },
          el("div", {}, el("div", { class: "card__title" }, j.title), el("div", { class: "card__id" }, when)),
          statusBadge(j.status)),
        j.error ? el("div", { class: "card__desc", style: "color:var(--err)" }, j.error) : null));
    });
  } catch (e) { $("#actList").innerHTML = ""; $("#actList").append(el("div", { class: "empty" }, el("div", {}, e.message))); }
}

/* =============================================================== BOOT */
async function boot() {
  try {
    const data = await api("/api/bootstrap");
    state.system = { ...data.system, cli_version: data.cli_version };
    state.user = data.user;
    if (state.user && state.user.email) renderShell();
    else renderAuth("login");
  } catch (e) {
    $("#boot").innerHTML = "";
    $("#boot").textContent = "Could not reach the local engine: " + e.message;
  }
}
boot();
