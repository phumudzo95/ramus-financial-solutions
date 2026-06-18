import { useState } from "react";

const NAVY = "#0a2463";
const GOLD = "#FFD700";
const GOLD_LIGHT = "#FFF3A3";

// Lightweight responsive rules for the containers below that use fixed inline widths.
// Targets: .rfs-layout (sidebar + main), .rfs-sidebar (fixed 220px sidebar),
// .rfs-two-col (dashboard 2-column grids), .rfs-header (top header row).
const RESPONSIVE_CSS = `
  @media (max-width: 900px) {
    .rfs-layout { flex-direction: column; }
    .rfs-sidebar { width: 100% !important; display: flex; overflow-x: auto; padding: 8px !important; border-right: none !important; border-bottom: 1px solid #E5E7EB; }
    .rfs-sidebar button { width: auto !important; white-space: nowrap; border-left: none !important; border-bottom: 3px solid transparent; }
    .rfs-sidebar > div { display: none; }
    .rfs-two-col { grid-template-columns: 1fr !important; }
  }
  @media (max-width: 640px) {
    .rfs-header { padding: 12px 14px !important; flex-wrap: wrap; gap: 8px !important; }
    .rfs-header > div:first-child { font-size: 13px !important; }
  }
`;

function ResponsiveStyle() {
  return <style>{RESPONSIVE_CSS}</style>;
}

const mockStats = {
  applications: { submitted: 12, under_review: 28, manual_review: 7, approved: 143, declined: 31, completed: 89 },
  decisions: { approve: 143, decline: 31, manual_review: 38 },
  users: { client: 287, worker: 8, admin: 3 },
  bureau_calls_today: 34,
  active_rules: 8,
};

const mockApplications = [
  { id: "a1", ref: "RCL-X7K29MQA", applicant: "T. Mokoena", amount: 4500, status: "manual_review", worker: "S. Dlamini", submitted: "2026-06-10", score: 612 },
  { id: "a2", ref: "RCL-B4R72NWP", applicant: "N. van der Berg", amount: 2500, status: "under_review", worker: "K. Naidoo", submitted: "2026-06-10", score: 741 },
  { id: "a3", ref: "RCL-H9T56LSE", applicant: "P. Sithole", amount: 4800, status: "submitted", worker: "—", submitted: "2026-06-11", score: null },
  { id: "a4", ref: "RCL-M3W88VXC", applicant: "A. Botha", amount: 3000, status: "approved", worker: "S. Dlamini", submitted: "2026-06-09", score: 788 },
  { id: "a5", ref: "RCL-Q1Y44KDR", applicant: "F. Mahlangu", amount: 5000, status: "declined", worker: "K. Naidoo", submitted: "2026-06-08", score: 389 },
];

const mockRules = [
  { id: 1, name: "Active judgements — hard decline", type: "negative_indicator", condition: "judgements_count > 0", action: "decline", priority: 1, active: true },
  { id: 2, name: "Multiple defaults — hard decline", type: "negative_indicator", condition: "defaults_count > 1", action: "decline", priority: 2, active: true },
  { id: 3, name: "Very low credit score — hard decline", type: "score_threshold", condition: "credit_score < 400", action: "decline", priority: 3, active: true },
  { id: 4, name: "Income below minimum — hard decline", type: "income", condition: "monthly_income < 3500", action: "decline", priority: 4, active: true },
  { id: 5, name: "DTI exceeds maximum — hard decline", type: "dti", condition: "dti_ratio > 0.45", action: "decline", priority: 5, active: true },
  { id: 6, name: "Excellent score — auto approve", type: "score_threshold", condition: "credit_score >= 700", action: "approve", priority: 20, active: true },
  { id: 7, name: "Moderate score — manual review", type: "score_threshold", condition: "credit_score >= 450", action: "manual_review", priority: 50, active: true },
  { id: 8, name: "High bureau enquiries — manual review", type: "enquiry_rate", condition: "enquiries_last_90_days > 5", action: "manual_review", priority: 51, active: true },
];

const mockAudit = [
  { id: 1, action: "BUREAU_REQUEST_INITIATED", actor: "S. Dlamini (worker)", target: "Application RCL-X7K29MQA", time: "2026-06-11 09:14:32", ip: "197.84.12.44" },
  { id: 2, action: "DECISION_MADE", actor: "System (engine)", target: "Application RCL-B4R72NWP", time: "2026-06-11 09:12:18", ip: "—" },
  { id: 3, action: "CONSENT_GRANTED", actor: "T. Mokoena (client)", target: "Application RCL-X7K29MQA", time: "2026-06-11 08:55:07", ip: "105.23.67.189" },
  { id: 4, action: "APPLICATION_STATUS_CHANGED", actor: "K. Naidoo (worker)", target: "Application RCL-Q1Y44KDR", time: "2026-06-10 16:44:00", ip: "197.84.12.44" },
  { id: 5, action: "RULE_UPDATED", actor: "Admin (admin)", target: "Rule: DTI exceeds maximum", time: "2026-06-10 14:22:55", ip: "197.84.15.2" },
  { id: 6, action: "USER_LOGIN", actor: "S. Dlamini (worker)", target: "User account", time: "2026-06-11 08:02:14", ip: "197.84.12.44" },
];

const STATUS_CONFIG = {
  submitted:     { bg: "#EFF6FF", color: "#1D4ED8", label: "Submitted" },
  under_review:  { bg: "#FFFBEB", color: "#B45309", label: "Under Review" },
  manual_review: { bg: "#FEF3C7", color: "#92400E", label: "Manual Review" },
  approved:      { bg: "#F0FDF4", color: "#15803D", label: "Approved" },
  declined:      { bg: "#FEF2F2", color: "#B91C1C", label: "Declined" },
  completed:     { bg: "#F0FDF4", color: "#166534", label: "Completed" },
};

const ACTION_CONFIG = {
  approve:       { bg: "#F0FDF4", color: "#15803D" },
  decline:       { bg: "#FEF2F2", color: "#B91C1C" },
  manual_review: { bg: "#FFFBEB", color: "#B45309" },
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { bg: "#F3F4F6", color: "#374151", label: status };
  return (
    <span style={{ background: cfg.bg, color: cfg.color, padding: "2px 10px", borderRadius: 20, fontSize: 12, fontWeight: 500, whiteSpace: "nowrap" }}>
      {cfg.label}
    </span>
  );
}

function StatCard({ label, value, sub, color }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: "18px 22px", flex: "1 1 140px" }}>
      <div style={{ fontSize: 28, fontWeight: 600, color: color || NAVY }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 500, color: "#374151", marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export default function AdminDashboard() {
  const [tab, setTab] = useState("dashboard");
  const [showRuleModal, setShowRuleModal] = useState(false);

  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "applications", label: "Applications", icon: "📋" },
    { id: "rules", label: "Decision Rules", icon: "⚙️" },
    { id: "audit", label: "Audit Logs", icon: "🔍" },
    { id: "integrations", label: "Integrations", icon: "🔌" },
  ];

  const totalApps = Object.values(mockStats.applications).reduce((a, b) => a + b, 0);
  const approvalRate = Math.round((mockStats.decisions.approve / (mockStats.decisions.approve + mockStats.decisions.decline)) * 100);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#F9FAFB" }}>
      <ResponsiveStyle />
      {/* Header */}
      <div className="rfs-header" style={{ background: NAVY, color: "#fff", display: "flex", alignItems: "center", gap: 16, padding: "14px 28px", borderBottom: `3px solid ${GOLD}` }}>
        <div style={{ background: GOLD, borderRadius: 8, width: 36, height: 36, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: NAVY, fontSize: 16 }}>R</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 16, letterSpacing: 0.3 }}>RAMUS FINANCIAL SOLUTIONS</div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.65)", letterSpacing: 1 }}>CREDIT DECISIONING SYSTEM — ADMIN</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ background: "#16a34a", color: "#fff", borderRadius: 20, padding: "3px 12px", fontSize: 12, fontWeight: 500 }}>● System Healthy</div>
          <div style={{ width: 34, height: 34, borderRadius: "50%", background: GOLD, color: NAVY, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>A</div>
        </div>
      </div>

      <div className="rfs-layout" style={{ display: "flex", minHeight: "calc(100vh - 70px)" }}>
        {/* Sidebar */}
        <div className="rfs-sidebar" style={{ width: 220, background: "#fff", borderRight: "1px solid #E5E7EB", padding: "20px 0", flexShrink: 0 }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} style={{
              display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "10px 22px",
              background: tab === t.id ? "#EFF6FF" : "transparent",
              border: "none", borderLeft: tab === t.id ? `3px solid ${NAVY}` : "3px solid transparent",
              cursor: "pointer", fontSize: 14, fontWeight: tab === t.id ? 600 : 400,
              color: tab === t.id ? NAVY : "#4B5563", textAlign: "left",
            }}>
              <span style={{ fontSize: 16 }}>{t.icon}</span> {t.label}
            </button>
          ))}

          <div style={{ margin: "24px 16px 0", padding: "16px", background: "#FFF8E1", borderRadius: 10, border: `1px solid ${GOLD}` }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#78350F", marginBottom: 6 }}>QUEUE ALERTS</div>
            <div style={{ fontSize: 12, color: "#92400E" }}>⚠ 7 in manual review</div>
            <div style={{ fontSize: 12, color: "#92400E", marginTop: 4 }}>⚠ 3 SLA near breach</div>
          </div>
        </div>

        {/* Main content */}
        <div className="rfs-main" style={{ flex: 1, padding: "28px", overflowY: "auto" }}>

          {/* ── DASHBOARD ── */}
          {tab === "dashboard" && (
            <div>
              <h2 style={{ margin: "0 0 24px", fontSize: 22, fontWeight: 600, color: "#111827" }}>System Overview</h2>

              <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 28 }}>
                <StatCard label="Total Applications" value={totalApps} sub="All time" />
                <StatCard label="Approval Rate" value={`${approvalRate}%`} sub="Automated + manual" color="#15803D" />
                <StatCard label="Bureau Calls Today" value={mockStats.bureau_calls_today} sub="TransUnion" />
                <StatCard label="Active Rules" value={mockStats.active_rules} sub="Decision engine" />
                <StatCard label="Pending Review" value={mockStats.applications.manual_review + mockStats.applications.under_review} sub="Need attention" color="#B45309" />
              </div>

              {/* Application status breakdown */}
              <div className="rfs-two-col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>
                <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 22 }}>
                  <div style={{ fontWeight: 600, fontSize: 15, color: "#111827", marginBottom: 18 }}>Application Pipeline</div>
                  {Object.entries(mockStats.applications).map(([status, count]) => {
                    const cfg = STATUS_CONFIG[status] || {};
                    const pct = Math.round((count / totalApps) * 100);
                    return (
                      <div key={status} style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <span style={{ fontSize: 13, color: "#374151" }}>{cfg.label || status}</span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: cfg.color || "#374151" }}>{count}</span>
                        </div>
                        <div style={{ background: "#F3F4F6", borderRadius: 4, height: 6 }}>
                          <div style={{ width: `${pct}%`, background: cfg.color || NAVY, borderRadius: 4, height: 6 }} />
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 22 }}>
                  <div style={{ fontWeight: 600, fontSize: 15, color: "#111827", marginBottom: 18 }}>Decision Outcomes</div>
                  {Object.entries(mockStats.decisions).map(([outcome, count]) => {
                    const total = Object.values(mockStats.decisions).reduce((a, b) => a + b, 0);
                    const pct = Math.round((count / total) * 100);
                    const cfg = ACTION_CONFIG[outcome] || {};
                    return (
                      <div key={outcome} style={{ marginBottom: 16 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                          <span style={{ fontSize: 13, color: "#374151" }}>{outcome.replace("_", " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: cfg.color }}>{count} ({pct}%)</span>
                        </div>
                        <div style={{ background: "#F3F4F6", borderRadius: 4, height: 8 }}>
                          <div style={{ width: `${pct}%`, background: cfg.color, borderRadius: 4, height: 8 }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* User stats */}
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 22 }}>
                <div style={{ fontWeight: 600, fontSize: 15, color: "#111827", marginBottom: 16 }}>User Accounts</div>
                <div style={{ display: "flex", gap: 24 }}>
                  {Object.entries(mockStats.users).map(([role, count]) => (
                    <div key={role} style={{ textAlign: "center", padding: "16px 32px", background: "#F9FAFB", borderRadius: 10, border: "1px solid #E5E7EB" }}>
                      <div style={{ fontSize: 28, fontWeight: 600, color: NAVY }}>{count}</div>
                      <div style={{ fontSize: 13, color: "#6B7280", textTransform: "capitalize" }}>{role}s</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── APPLICATIONS ── */}
          {tab === "applications" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <h2 style={{ margin: 0, fontSize: 22, fontWeight: 600, color: "#111827" }}>All Applications</h2>
                <div style={{ display: "flex", gap: 8 }}>
                  <select style={{ padding: "8px 12px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 13 }}>
                    <option>All statuses</option>
                    {Object.keys(STATUS_CONFIG).map(s => <option key={s}>{s}</option>)}
                  </select>
                  <input placeholder="Search ref / applicant…" style={{ padding: "8px 14px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 13, width: 220 }} />
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#F9FAFB", borderBottom: "2px solid #E5E7EB" }}>
                      {["Reference", "Applicant", "Amount", "Status", "Credit Score", "Worker", "Submitted", ""].map(h => (
                        <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600, color: "#374151", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mockApplications.map((app, i) => (
                      <tr key={app.id} style={{ borderBottom: "1px solid #F3F4F6", background: i % 2 === 0 ? "#fff" : "#FAFAFA" }}>
                        <td style={{ padding: "12px 16px", fontFamily: "monospace", color: NAVY, fontWeight: 600 }}>{app.ref}</td>
                        <td style={{ padding: "12px 16px", color: "#111827" }}>{app.applicant}</td>
                        <td style={{ padding: "12px 16px", color: "#111827" }}>R {app.amount.toLocaleString()}</td>
                        <td style={{ padding: "12px 16px" }}><StatusBadge status={app.status} /></td>
                        <td style={{ padding: "12px 16px" }}>
                          {app.score ? (
                            <span style={{ fontWeight: 600, color: app.score >= 700 ? "#15803D" : app.score >= 500 ? "#B45309" : "#B91C1C" }}>
                              {app.score}
                            </span>
                          ) : <span style={{ color: "#9CA3AF" }}>Pending</span>}
                        </td>
                        <td style={{ padding: "12px 16px", color: "#4B5563" }}>{app.worker}</td>
                        <td style={{ padding: "12px 16px", color: "#6B7280" }}>{app.submitted}</td>
                        <td style={{ padding: "12px 16px" }}>
                          <button style={{ padding: "4px 12px", background: NAVY, color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── DECISION RULES ── */}
          {tab === "rules" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: 22, fontWeight: 600, color: "#111827" }}>Decision Rules</h2>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6B7280" }}>Rules are evaluated in priority order. First match determines the outcome. No code changes required.</p>
                </div>
                <button onClick={() => setShowRuleModal(true)} style={{ padding: "10px 20px", background: NAVY, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 14 }}>
                  + New Rule
                </button>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {mockRules.map(rule => (
                  <div key={rule.id} style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: "16px 20px", display: "flex", alignItems: "center", gap: 16 }}>
                    <div style={{ width: 36, height: 36, borderRadius: 8, background: "#F3F4F6", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: "#6B7280", fontSize: 13, flexShrink: 0 }}>
                      P{rule.priority}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>{rule.name}</div>
                      <div style={{ fontSize: 12, color: "#6B7280", marginTop: 3, fontFamily: "monospace", background: "#F9FAFB", padding: "2px 8px", borderRadius: 4, display: "inline-block" }}>
                        {rule.condition}
                      </div>
                    </div>
                    <div style={{ ...ACTION_CONFIG[rule.action], padding: "4px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      {rule.action.replace("_", " ")}
                    </div>
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <button style={{ padding: "6px 14px", border: `1px solid ${NAVY}`, color: NAVY, background: "#fff", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>Edit</button>
                      <button style={{ padding: "6px 14px", border: "1px solid #E5E7EB", color: "#9CA3AF", background: "#fff", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>Disable</button>
                    </div>
                  </div>
                ))}
              </div>

              {showRuleModal && (
                <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
                  <div style={{ background: "#fff", borderRadius: 16, padding: 32, width: 520, boxShadow: "0 20px 60px rgba(0,0,0,0.3)" }}>
                    <h3 style={{ margin: "0 0 24px", color: "#111827" }}>Create Decision Rule</h3>
                    {[["Rule name", "e.g. Income above threshold — auto approve"], ["Condition field", "e.g. credit_score"], ["Operator", ">="], ["Value", "700"], ["Priority", "20"]].map(([label, ph]) => (
                      <div key={label} style={{ marginBottom: 16 }}>
                        <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>{label}</label>
                        <input placeholder={ph} style={{ width: "100%", padding: "10px 14px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }} />
                      </div>
                    ))}
                    <div style={{ marginBottom: 20 }}>
                      <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 }}>Action</label>
                      <select style={{ width: "100%", padding: "10px 14px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 14 }}>
                        <option value="approve">Approve</option>
                        <option value="decline">Decline</option>
                        <option value="manual_review">Manual Review</option>
                      </select>
                    </div>
                    <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
                      <button onClick={() => setShowRuleModal(false)} style={{ padding: "10px 20px", border: "1px solid #D1D5DB", borderRadius: 8, cursor: "pointer", background: "#fff" }}>Cancel</button>
                      <button onClick={() => setShowRuleModal(false)} style={{ padding: "10px 24px", background: NAVY, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600 }}>Save Rule</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── AUDIT LOGS ── */}
          {tab === "audit" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: 22, fontWeight: 600, color: "#111827" }}>Audit Logs</h2>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6B7280" }}>Immutable. Timestamped. Fully traceable. Retained 7 years per NCA compliance requirements.</p>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <select style={{ padding: "8px 12px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 13 }}>
                    <option>All actions</option>
                    <option>Bureau requests</option>
                    <option>Decisions</option>
                    <option>Consent</option>
                    <option>User actions</option>
                  </select>
                  <button style={{ padding: "8px 16px", background: "#fff", border: "1px solid #D1D5DB", borderRadius: 8, cursor: "pointer", fontSize: 13 }}>Export CSV</button>
                </div>
              </div>
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, overflow: "hidden" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#F9FAFB", borderBottom: "2px solid #E5E7EB" }}>
                      {["Timestamp", "Action", "Actor", "Target", "IP Address"].map(h => (
                        <th key={h} style={{ padding: "12px 16px", textAlign: "left", fontWeight: 600, color: "#374151" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {mockAudit.map((log, i) => (
                      <tr key={log.id} style={{ borderBottom: "1px solid #F3F4F6", background: i % 2 === 0 ? "#fff" : "#FAFAFA" }}>
                        <td style={{ padding: "11px 16px", fontFamily: "monospace", fontSize: 12, color: "#6B7280", whiteSpace: "nowrap" }}>{log.time}</td>
                        <td style={{ padding: "11px 16px" }}>
                          <span style={{ fontFamily: "monospace", fontSize: 12, background: "#EFF6FF", color: "#1D4ED8", padding: "2px 8px", borderRadius: 4 }}>
                            {log.action}
                          </span>
                        </td>
                        <td style={{ padding: "11px 16px", color: "#374151" }}>{log.actor}</td>
                        <td style={{ padding: "11px 16px", color: "#374151" }}>{log.target}</td>
                        <td style={{ padding: "11px 16px", fontFamily: "monospace", fontSize: 12, color: "#9CA3AF" }}>{log.ip}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── INTEGRATIONS ── */}
          {tab === "integrations" && (
            <div>
              <h2 style={{ margin: "0 0 24px", fontSize: 22, fontWeight: 600, color: "#111827" }}>Integration Health</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {[
                  { name: "TransUnion Credit Bureau", status: "healthy", latency: "124ms", calls_today: 34, success_rate: "100%", last_check: "2 min ago", type: "Primary Bureau" },
                  { name: "AWS SES (Email)", status: "healthy", latency: "45ms", calls_today: 89, success_rate: "98.9%", last_check: "5 min ago", type: "Notification" },
                  { name: "AWS KMS (Encryption)", status: "healthy", latency: "12ms", calls_today: 1240, success_rate: "100%", last_check: "1 min ago", type: "Security" },
                  { name: "AWS S3 (Documents)", status: "healthy", latency: "67ms", calls_today: 28, success_rate: "100%", last_check: "3 min ago", type: "Storage" },
                  { name: "Experian (Future)", status: "not_configured", latency: "—", calls_today: 0, success_rate: "—", last_check: "—", type: "Secondary Bureau" },
                ].map(svc => (
                  <div key={svc.name} style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: "20px 24px", display: "flex", alignItems: "center", gap: 20 }}>
                    <div style={{ width: 12, height: 12, borderRadius: "50%", background: svc.status === "healthy" ? "#16a34a" : svc.status === "degraded" ? "#B45309" : "#9CA3AF", flexShrink: 0 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 15, color: "#111827" }}>{svc.name}</div>
                      <div style={{ fontSize: 12, color: "#6B7280", marginTop: 2 }}>{svc.type}</div>
                    </div>
                    <div style={{ display: "flex", gap: 28 }}>
                      {[["Status", svc.status], ["Latency", svc.latency], ["Calls Today", svc.calls_today], ["Success Rate", svc.success_rate], ["Last Check", svc.last_check]].map(([label, val]) => (
                        <div key={label} style={{ textAlign: "center" }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{val}</div>
                          <div style={{ fontSize: 11, color: "#9CA3AF" }}>{label}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
