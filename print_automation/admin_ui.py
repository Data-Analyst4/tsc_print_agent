ADMIN_PRINTER_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Print Server Admin</title>
  <style>
    :root {
      --bg: #f5f8fc;
      --panel: #ffffff;
      --line: #d8e0ea;
      --text: #0f2740;
      --muted: #617183;
      --accent: #0a63c7;
      --danger: #b82c2c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: radial-gradient(circle at 20% 0%, #eef5ff 0%, #f5f8fc 60%);
      color: var(--text);
    }
    .wrap {
      width: min(1180px, 96vw);
      margin: 16px auto 32px;
      display: grid;
      gap: 12px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
    }
    h1, h2 { margin: 0; }
    h1 { font-size: 22px; }
    h2 { font-size: 18px; margin-bottom: 8px; }
    p { margin: 8px 0 0; color: var(--muted); }
    .grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }
    .field { display: grid; gap: 3px; }
    .field label { font-size: 12px; color: var(--muted); }
    input,
    select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 9px;
      outline: none;
    }
    input:focus,
    select:focus { border-color: var(--accent); }
    .row-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    button {
      border: 0;
      border-radius: 8px;
      padding: 8px 11px;
      font-size: 13px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
    }
    button.small { padding: 5px 8px; font-size: 12px; }
    button.secondary { background: #4f6276; }
    button.danger { background: var(--danger); }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 6px;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 7px 5px;
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
    .mono { font-family: Consolas, "Courier New", monospace; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f8fbff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      max-height: 240px;
      overflow: auto;
      margin-top: 8px;
    }
    .status { color: var(--muted); margin-top: 4px; font-size: 13px; min-height: 18px; }
    @media (max-width: 920px) {
      .grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Central Print Server Admin</h1>
      <p>Manage workstation routing, fallback order, and printer roll-size profiles used for label routing.</p>
      <div class="grid" style="margin-top:8px;">
        <div class="field" style="grid-column: span 6;">
          <label>API Token (X-Auth-Token)</label>
          <input id="token" placeholder="Paste shared API token">
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Printer Profile</h2>
      <div class="grid">
        <div class="field" style="grid-column: span 2;">
          <label>Agent ID</label>
          <input id="p_agent_id" placeholder="agent_ws1">
        </div>
        <div class="field" style="grid-column: span 2;">
          <label>Printer Name</label>
          <input id="p_printer_name" placeholder="TSC_TE244">
        </div>
        <div class="field">
          <label>Roll Width mm</label>
          <input id="p_roll_width" type="number" min="0" placeholder="100">
        </div>
        <div class="field">
          <label>Roll Height mm</label>
          <input id="p_roll_height" type="number" min="0" placeholder="75">
        </div>
        <div class="field" style="grid-column: span 2;">
          <label>Size Code</label>
          <input id="p_size_code" placeholder="4x3 / 4x6">
        </div>
        <div class="field" style="grid-column: span 2;">
          <label>Enabled (true/false)</label>
          <input id="p_enabled" placeholder="true">
        </div>
        <div class="field" style="grid-column: span 2;">
          <label>Notes</label>
          <input id="p_notes" placeholder="optional">
        </div>
      </div>
      <div class="row-actions">
        <button id="save_printer">Save Profile</button>
        <button id="refresh_all" class="secondary">Refresh All</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Agent</th><th>Printer</th><th>Roll</th><th>Size</th><th>Enabled</th><th>Updated</th><th>Action</th>
          </tr>
        </thead>
        <tbody id="printer_rows"></tbody>
      </table>
    </div>

    <div class="card">
      <h2>Workstations</h2>
      <div class="grid">
        <div class="field" style="grid-column: span 2;">
          <label>Workstation ID</label>
          <input id="w_id" placeholder="ws_shipping_1">
        </div>
        <div class="field" style="grid-column: span 2;">
          <label>Display Name</label>
          <input id="w_name" placeholder="Shipping Desk 1">
        </div>
        <div class="field" style="grid-column: span 1;">
          <label>Location Tag</label>
          <input id="w_location" placeholder="floor-a">
        </div>
        <div class="field" style="grid-column: span 1;">
          <label>Enabled</label>
          <input id="w_enabled" placeholder="true">
        </div>
      </div>
      <div class="row-actions">
        <button id="save_ws">Save Workstation</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th><th>Name</th><th>Location</th><th>Enabled</th><th>Updated</th><th>Action</th>
          </tr>
        </thead>
        <tbody id="ws_rows"></tbody>
      </table>
    </div>

    <div class="card">
      <h2>Fallback Routing</h2>
      <div class="grid">
        <div class="field" style="grid-column: span 2;">
          <label>Primary Workstation ID</label>
          <input id="f_ws_id" placeholder="ws_shipping_1">
        </div>
        <div class="field" style="grid-column: span 4;">
          <label>Fallback IDs in priority order (comma separated)</label>
          <input id="f_order" placeholder="ws_shipping_2,ws_backup_1">
        </div>
      </div>
      <div class="row-actions">
        <button id="save_fallbacks">Save Fallback Order</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Primary</th><th>Fallback</th><th>Rank</th><th>Updated</th>
          </tr>
        </thead>
        <tbody id="fallback_rows"></tbody>
      </table>
    </div>

    <div class="card">
      <h2>Recent Jobs and Artifacts</h2>
      <div class="grid">
        <div class="field" style="grid-column: span 2;">
          <label>Status Filter</label>
          <select id="jobs_status">
            <option value="">All statuses</option>
            <option value="QUEUED">QUEUED</option>
            <option value="ASSIGNED">ASSIGNED</option>
            <option value="DOWNLOADING">DOWNLOADING</option>
            <option value="RENDERING">RENDERING</option>
            <option value="PRINTING">PRINTING</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILED">FAILED</option>
          </select>
        </div>
        <div class="field" style="grid-column: span 1;">
          <label>Limit (1-500)</label>
          <input id="jobs_limit" type="number" min="1" max="500" value="100">
        </div>
      </div>
      <div class="row-actions">
        <button id="refresh_jobs" class="secondary">Refresh Jobs</button>
        <button id="toggle_live" class="secondary">Live Refresh: OFF</button>
      </div>
      <table>
        <thead>
          <tr>
            <th>Job ID</th><th>Status</th><th>Agent</th><th>Printer</th><th>Copies</th><th>Size</th><th>Created</th><th>Error</th><th>Artifacts</th><th>Events</th>
          </tr>
        </thead>
        <tbody id="jobs_rows"></tbody>
      </table>
      <div class="field" style="margin-top:8px;">
        <label>Selected Job Events</label>
        <pre id="job_events" class="mono">Select a job and click "View Events".</pre>
      </div>
    </div>

    <div class="card">
      <h2>Active Printers (from discovery)</h2>
      <table>
        <thead>
          <tr>
            <th>Workstation</th><th>Agent</th><th>Printer</th><th>Size</th><th>Roll</th><th>Heartbeat</th>
          </tr>
        </thead>
        <tbody id="active_rows"></tbody>
      </table>
      <div class="status" id="status"></div>
    </div>
  </div>

  <script>
    const statusNode = document.getElementById("status");
    const printerRows = document.getElementById("printer_rows");
    const wsRows = document.getElementById("ws_rows");
    const fallbackRows = document.getElementById("fallback_rows");
    const activeRows = document.getElementById("active_rows");
    const jobsRows = document.getElementById("jobs_rows");
    const jobEventsNode = document.getElementById("job_events");
    const liveToggleButton = document.getElementById("toggle_live");
    let liveRefreshTimer = null;
    let liveRefreshEnabled = false;

    function token() { return document.getElementById("token").value.trim(); }
    function boolOrDefault(value, fallback=true) {
      const v = (value || "").trim().toLowerCase();
      if (!v) return fallback;
      if (["1","true","yes","on"].includes(v)) return true;
      if (["0","false","no","off"].includes(v)) return false;
      return fallback;
    }
    function say(text, isErr=false) {
      statusNode.textContent = text;
      statusNode.style.color = isErr ? "#b82c2c" : "#617183";
    }
    function safe(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
    async function api(path, method="GET", body=null) {
      const t = token();
      if (!t) throw new Error("API token required");
      const headers = {"X-Auth-Token": t};
      if (body !== null) headers["Content-Type"] = "application/json";
      const res = await fetch(path, {method, headers, body: body===null ? undefined : JSON.stringify(body)});
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
      return data;
    }

    function row(html) {
      const tr = document.createElement("tr");
      tr.innerHTML = html;
      return tr;
    }

    function jobsQueryString() {
      const status = document.getElementById("jobs_status").value.trim();
      const rawLimit = document.getElementById("jobs_limit").value.trim();
      let limit = Number(rawLimit || "100");
      if (!Number.isFinite(limit)) limit = 100;
      limit = Math.min(500, Math.max(1, Math.trunc(limit)));
      document.getElementById("jobs_limit").value = String(limit);

      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (status) params.set("status", status);
      return params.toString();
    }

    function extractJobSizeCode(job) {
      const metadata = job.metadata || {};
      const profile = job.profile || {};
      return metadata.requested_size_code || metadata.requested_label_size || profile.size_code || "-";
    }

    async function fetchArtifact(jobId, kind, openInNewTab=false) {
      const t = token();
      if (!t) throw new Error("API token required");
      const headers = {"X-Auth-Token": t};
      const url = "/v1/jobs/" + encodeURIComponent(jobId) + "/artifacts/" + kind;
      const res = await fetch(url, {method: "GET", headers});
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || ("HTTP " + res.status));
      }

      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      if (kind === "pdf" && openInNewTab) {
        window.open(blobUrl, "_blank", "noopener,noreferrer");
        setTimeout(() => URL.revokeObjectURL(blobUrl), 15000);
        return;
      }

      const suffix = kind === "pdf" ? "pdf" : "tspl";
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = jobId + "." + suffix;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 15000);
    }

    function renderJobs(jobs) {
      jobsRows.innerHTML = "";
      for (const j of (jobs || [])) {
        const hasPdf = Boolean(j.output_pdf_path);
        const hasTspl = Boolean(j.output_tspl_path);
        const actions = [
          hasPdf ? "<button class='small secondary' data-act='view-pdf'>View PDF</button>" : "<span>-</span>",
          hasTspl ? "<button class='small secondary' data-act='download-tspl'>Download TSPL</button>" : "<span>-</span>",
        ].join(" ");
        const tr = row(
          "<td class='mono'>" + safe(j.job_id) + "</td>" +
          "<td>" + safe(j.status || "") + "</td>" +
          "<td class='mono'>" + safe(j.assigned_agent_id || j.target_agent_id || "-") + "</td>" +
          "<td class='mono'>" + safe(j.target_printer || "-") + "</td>" +
          "<td>" + safe(j.copies || "") + "</td>" +
          "<td>" + safe(extractJobSizeCode(j)) + "</td>" +
          "<td>" + safe(j.created_at || "") + "</td>" +
          "<td>" + safe(j.error_message || "-") + "</td>" +
          "<td>" + actions + "</td>" +
          "<td><button class='small secondary' data-act='events'>View Events</button></td>"
        );

        const pdfBtn = tr.querySelector("[data-act='view-pdf']");
        if (pdfBtn) {
          pdfBtn.addEventListener("click", async () => {
            try {
              await fetchArtifact(j.job_id, "pdf", true);
              say("Opened PDF artifact for " + j.job_id);
            } catch (err) {
              say(err.message || String(err), true);
            }
          });
        }

        const tsplBtn = tr.querySelector("[data-act='download-tspl']");
        if (tsplBtn) {
          tsplBtn.addEventListener("click", async () => {
            try {
              await fetchArtifact(j.job_id, "tspl", false);
              say("Downloaded TSPL artifact for " + j.job_id);
            } catch (err) {
              say(err.message || String(err), true);
            }
          });
        }

        const eventsBtn = tr.querySelector("[data-act='events']");
        if (eventsBtn) {
          eventsBtn.addEventListener("click", async () => {
            try {
              const out = await api("/v1/jobs/" + encodeURIComponent(j.job_id) + "?include_events=true");
              const events = out.events || [];
              jobEventsNode.textContent = JSON.stringify(events, null, 2);
              say("Loaded " + events.length + " events for " + j.job_id);
            } catch (err) {
              say(err.message || String(err), true);
            }
          });
        }

        jobsRows.appendChild(tr);
      }
    }

    async function refreshJobs(showStatus=true) {
      const jobsResponse = await api("/v1/jobs?" + jobsQueryString());
      const jobs = jobsResponse.jobs || [];
      renderJobs(jobs);
      if (showStatus) say("Loaded " + jobs.length + " jobs");
    }

    function setLiveRefresh(enabled) {
      liveRefreshEnabled = enabled;
      if (liveRefreshTimer !== null) {
        clearInterval(liveRefreshTimer);
        liveRefreshTimer = null;
      }
      if (enabled) {
        liveRefreshTimer = setInterval(async () => {
          try {
            await refreshAll();
          } catch (err) {
            say(err.message || String(err), true);
          }
        }, 10000);
      }
      liveToggleButton.textContent = enabled ? "Live Refresh: ON (10s)" : "Live Refresh: OFF";
    }

    async function refreshAll() {
      const [profiles, workstations, fallbacks, discovery, jobsResponse] = await Promise.all([
        api("/v1/admin/printer-profiles"),
        api("/v1/admin/workstations"),
        api("/v1/admin/workstation-fallbacks"),
        api("/v1/discovery"),
        api("/v1/jobs?" + jobsQueryString()),
      ]);

      printerRows.innerHTML = "";
      for (const p of (profiles.printer_profiles || [])) {
        const roll = ((p.roll_width_mm || "-") + " x " + (p.roll_height_mm || "-"));
        const tr = row(
          "<td class='mono'>" + (p.agent_id || "") + "</td>" +
          "<td class='mono'>" + (p.printer_name || "") + "</td>" +
          "<td>" + roll + " mm</td>" +
          "<td>" + (p.size_code || "-") + "</td>" +
          "<td>" + (p.enabled ? "true" : "false") + "</td>" +
          "<td>" + (p.updated_at || "") + "</td>" +
          "<td><button class='danger'>Delete</button></td>"
        );
        tr.querySelector("button").addEventListener("click", async () => {
          try {
            await api("/v1/admin/printer-profiles/delete", "POST", {agent_id: p.agent_id, printer_name: p.printer_name});
            await refreshAll();
            say("Printer profile deleted");
          } catch (err) { say(err.message || String(err), true); }
        });
        printerRows.appendChild(tr);
      }

      wsRows.innerHTML = "";
      for (const w of (workstations.workstations || [])) {
        const tr = row(
          "<td class='mono'>" + w.workstation_id + "</td>" +
          "<td>" + (w.name || "") + "</td>" +
          "<td>" + (w.location_tag || "-") + "</td>" +
          "<td>" + (w.enabled ? "true" : "false") + "</td>" +
          "<td>" + (w.updated_at || "") + "</td>" +
          "<td><button class='danger'>Delete</button></td>"
        );
        tr.querySelector("button").addEventListener("click", async () => {
          try {
            await api("/v1/admin/workstations/delete", "POST", {workstation_id: w.workstation_id});
            await refreshAll();
            say("Workstation deleted");
          } catch (err) { say(err.message || String(err), true); }
        });
        wsRows.appendChild(tr);
      }

      fallbackRows.innerHTML = "";
      for (const f of (fallbacks.workstation_fallbacks || [])) {
        fallbackRows.appendChild(
          row(
            "<td class='mono'>" + f.workstation_id + "</td>" +
            "<td class='mono'>" + f.fallback_workstation_id + "</td>" +
            "<td>" + f.rank + "</td>" +
            "<td>" + (f.updated_at || "") + "</td>"
          )
        );
      }

      activeRows.innerHTML = "";
      for (const a of (discovery.active_printers || [])) {
        const roll = ((a.roll_width_mm || "-") + " x " + (a.roll_height_mm || "-"));
        activeRows.appendChild(
          row(
            "<td class='mono'>" + (a.workstation_id || "-") + "</td>" +
            "<td class='mono'>" + (a.agent_id || "-") + "</td>" +
            "<td class='mono'>" + (a.printer_name || "-") + "</td>" +
            "<td>" + (a.size_code || "-") + "</td>" +
            "<td>" + roll + " mm</td>" +
            "<td>" + (a.heartbeat_at || "") + "</td>"
          )
        );
      }
      renderJobs(jobsResponse.jobs || []);
      say("Loaded discovery data and jobs");
    }

    document.getElementById("save_printer").addEventListener("click", async () => {
      try {
        const data = {
          agent_id: document.getElementById("p_agent_id").value.trim(),
          printer_name: document.getElementById("p_printer_name").value.trim(),
          size_code: document.getElementById("p_size_code").value.trim() || null,
          notes: document.getElementById("p_notes").value.trim() || null,
          enabled: boolOrDefault(document.getElementById("p_enabled").value, true),
        };
        const width = document.getElementById("p_roll_width").value.trim();
        const height = document.getElementById("p_roll_height").value.trim();
        if (!data.agent_id || !data.printer_name) throw new Error("agent_id and printer_name are required");
        if (width) data.roll_width_mm = Number(width);
        if (height) data.roll_height_mm = Number(height);
        await api("/v1/admin/printer-profiles", "POST", data);
        await refreshAll();
        say("Printer profile saved");
      } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("save_ws").addEventListener("click", async () => {
      try {
        const data = {
          workstation_id: document.getElementById("w_id").value.trim(),
          name: document.getElementById("w_name").value.trim(),
          location_tag: document.getElementById("w_location").value.trim() || null,
          enabled: boolOrDefault(document.getElementById("w_enabled").value, true),
        };
        if (!data.workstation_id) throw new Error("workstation_id is required");
        if (!data.name) data.name = data.workstation_id;
        await api("/v1/admin/workstations", "POST", data);
        await refreshAll();
        say("Workstation saved");
      } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("save_fallbacks").addEventListener("click", async () => {
      try {
        const workstation_id = document.getElementById("f_ws_id").value.trim();
        const orderRaw = document.getElementById("f_order").value.trim();
        if (!workstation_id) throw new Error("workstation_id is required");
        const fallback_workstation_ids = orderRaw ? orderRaw.split(",").map(x => x.trim()).filter(Boolean) : [];
        await api("/v1/admin/workstation-fallbacks", "POST", {workstation_id, fallback_workstation_ids});
        await refreshAll();
        say("Fallback order saved");
      } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("refresh_all").addEventListener("click", async () => {
      try { await refreshAll(); } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("refresh_jobs").addEventListener("click", async () => {
      try { await refreshJobs(); } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("jobs_status").addEventListener("change", async () => {
      try { await refreshJobs(false); } catch (err) { say(err.message || String(err), true); }
    });

    document.getElementById("jobs_limit").addEventListener("change", async () => {
      try { await refreshJobs(false); } catch (err) { say(err.message || String(err), true); }
    });

    liveToggleButton.addEventListener("click", () => {
      setLiveRefresh(!liveRefreshEnabled);
      say(liveRefreshEnabled ? "Live refresh enabled" : "Live refresh disabled");
    });
  </script>
</body>
</html>
"""
