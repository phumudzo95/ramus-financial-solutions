import { useState } from "react";

const NAVY = "#0a2463";
const GOLD = "#FFD700";

const QUEUE = [
  { id: "a1", ref: "RCL-X7K29MQA", applicant: "T. Mokoena", amount: 15000, status: "manual_review", age_hours: 3.5, score: 612, dti: "38%", negatives: 1, priority: 2 },
  { id: "a2", ref: "RCL-B4R72NWP", applicant: "N. van der Berg", amount: 8500, status: "under_review", age_hours: 1.2, score: 741, dti: "22%", negatives: 0, priority: 1 },
  { id: "a3", ref: "RCL-K5T11QXZ", applicant: "M. Khumalo", amount: 18000, status: "under_review", age_hours: 5.1, score: 558, dti: "41%", negatives: 2, priority: 1 },
];

const CREDIT_DETAIL = {
  score: 612, risk: "medium", total_accounts: 4, open_accounts: 3, closed_accounts: 1,
  negative_listings: 1, judgements: 0, defaults: 0, outstanding_debt: 42300, monthly_obligations: 4200,
  enquiries_90d: 2, oldest_account_months: 38,
};

function Badge({ text, type }) {
  const styles = {
    manual_review: { bg: "#FEF3C7", color: "#92400E" },
    under_review:  { bg: "#DBEAFE", color: "#1D4ED8" },
    medium:        { bg: "#FFFBEB", color: "#B45309" },
    low:           { bg: "#F0FDF4", color: "#15803D" },
    high:          { bg: "#FEF2F2", color: "#B91C1C" },
    default:       { bg: "#F3F4F6", color: "#374151" },
  };
  const s = styles[type] || styles.default;
  return (
    <span style={{ background: s.bg, color: s.color, padding: "3px 10px", borderRadius: 20, fontSize: 12, fontWeight: 500, whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

export default function WorkerDashboard() {
  const [selected, setSelected] = useState(QUEUE[0]);
  const [subTab, setSubTab] = useState("credit");
  const [note, setNote] = useState("");
  const [notes, setNotes] = useState([
    { author: "K. Naidoo", time: "09:44", text: "Customer called to confirm employment. HR contact provided." },
  ]);

  const score = CREDIT_DETAIL.score;
  const scoreColor = score >= 700 ? "#15803D" : score >= 550 ? "#B45309" : "#B91C1C";
  const scoreLabel = score >= 700 ? "Good" : score >= 550 ? "Fair" : "Poor";
  const scorePct = Math.round((score / 999) * 100);

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#F9FAFB" }}>
      {/* Header */}
      <div style={{ background: NAVY, color: "#fff", display: "flex", alignItems: "center", gap: 14, padding: "12px 24px", borderBottom: `3px solid ${GOLD}` }}>
        <div style={{ background: GOLD, borderRadius: 8, width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: NAVY, fontSize: 15 }}>R</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: 0.3 }}>RAMUS CASH LOANS</div>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.6)", letterSpacing: 1 }}>CREDIT OPERATIONS — WORKER PORTAL</div>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.8)" }}>K. Naidoo</div>
          <div style={{ width: 32, height: 32, borderRadius: "50%", background: GOLD, color: NAVY, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13 }}>K</div>
        </div>
      </div>

      <div style={{ display: "flex", height: "calc(100vh - 62px)" }}>
        {/* Queue panel */}
        <div style={{ width: 310, background: "#fff", borderRight: "1px solid #E5E7EB", overflowY: "auto", flexShrink: 0 }}>
          <div style={{ padding: "16px 18px", borderBottom: "1px solid #E5E7EB" }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>My Queue</div>
            <div style={{ fontSize: 12, color: "#6B7280", marginTop: 2 }}>{QUEUE.length} applications assigned</div>
          </div>
          {QUEUE.map(app => (
            <div key={app.id} onClick={() => setSelected(app)}
              style={{ padding: "14px 18px", borderBottom: "1px solid #F3F4F6", cursor: "pointer", background: selected?.id === app.id ? "#EFF6FF" : "transparent", borderLeft: selected?.id === app.id ? `3px solid ${NAVY}` : "3px solid transparent" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                <div style={{ fontFamily: "monospace", fontSize: 12, fontWeight: 600, color: NAVY }}>{app.ref}</div>
                {app.priority === 2 && <span style={{ background: "#FEF3C7", color: "#92400E", fontSize: 10, padding: "1px 6px", borderRadius: 10, fontWeight: 600 }}>ESCALATED</span>}
              </div>
              <div style={{ fontSize: 13, color: "#111827", marginBottom: 4 }}>{app.applicant}</div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, color: "#6B7280" }}>R {app.amount.toLocaleString()}</span>
                <Badge text={app.status.replace("_", " ")} type={app.status} />
              </div>
              <div style={{ fontSize: 11, color: app.age_hours > 4 ? "#B91C1C" : "#9CA3AF", marginTop: 6 }}>
                {app.age_hours > 4 ? "⚠ " : ""}In queue {app.age_hours}h
              </div>
            </div>
          ))}
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
            {/* App header */}
            <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: "20px 24px", marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
                    <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 16, color: NAVY }}>{selected.ref}</span>
                    <Badge text={selected.status.replace("_", " ")} type={selected.status} />
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: "#111827" }}>{selected.applicant}</div>
                  <div style={{ fontSize: 14, color: "#6B7280", marginTop: 4 }}>
                    Requesting <strong style={{ color: "#111827" }}>R {selected.amount.toLocaleString()}</strong> · DTI {selected.dti}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                  <button style={{ padding: "10px 20px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>Approve</button>
                  <button style={{ padding: "10px 20px", background: "#DC2626", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>Decline</button>
                  <button style={{ padding: "10px 20px", background: "#F59E0B", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>Escalate</button>
                </div>
              </div>
            </div>

            {/* Sub-tabs */}
            <div style={{ display: "flex", gap: 4, background: "#F3F4F6", borderRadius: 10, padding: 4, marginBottom: 20, width: "fit-content" }}>
              {["credit", "notes", "documents"].map(t => (
                <button key={t} onClick={() => setSubTab(t)} style={{ padding: "8px 20px", background: subTab === t ? "#fff" : "transparent", border: "none", borderRadius: 7, cursor: "pointer", fontSize: 13, fontWeight: subTab === t ? 600 : 400, color: subTab === t ? "#111827" : "#6B7280", boxShadow: subTab === t ? "0 1px 3px rgba(0,0,0,0.1)" : "none" }}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>

            {/* Credit tab */}
            {subTab === "credit" && (
              <div>
                {/* Score card */}
                <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: "24px", marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 15, color: "#111827", marginBottom: 20 }}>TransUnion Credit Profile</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 32 }}>
                    <div style={{ textAlign: "center" }}>
                      <div style={{ fontSize: 56, fontWeight: 700, color: scoreColor, lineHeight: 1 }}>{score}</div>
                      <div style={{ fontSize: 14, color: scoreColor, fontWeight: 600, marginTop: 4 }}>{scoreLabel}</div>
                      <div style={{ fontSize: 12, color: "#9CA3AF" }}>out of 999</div>
                      <div style={{ marginTop: 10, background: "#F3F4F6", borderRadius: 4, height: 8, width: 120 }}>
                        <div style={{ width: `${scorePct}%`, background: scoreColor, borderRadius: 4, height: 8 }} />
                      </div>
                    </div>
                    <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                      {[
                        ["Total Accounts", CREDIT_DETAIL.total_accounts],
                        ["Open Accounts", CREDIT_DETAIL.open_accounts],
                        ["Negative Listings", CREDIT_DETAIL.negative_listings, CREDIT_DETAIL.negative_listings > 0 ? "#B45309" : "#15803D"],
                        ["Judgements", CREDIT_DETAIL.judgements, CREDIT_DETAIL.judgements > 0 ? "#B91C1C" : "#15803D"],
                        ["Defaults", CREDIT_DETAIL.defaults, CREDIT_DETAIL.defaults > 0 ? "#B91C1C" : "#15803D"],
                        ["Bureau Enquiries (90d)", CREDIT_DETAIL.enquiries_90d],
                        ["Monthly Obligations", `R ${CREDIT_DETAIL.monthly_obligations.toLocaleString()}`],
                        ["Total Outstanding", `R ${CREDIT_DETAIL.outstanding_debt.toLocaleString()}`],
                      ].map(([label, val, color]) => (
                        <div key={label} style={{ background: "#F9FAFB", borderRadius: 8, padding: "10px 14px" }}>
                          <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 2 }}>{label}</div>
                          <div style={{ fontSize: 16, fontWeight: 600, color: color || "#111827" }}>{val}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Decision engine result */}
                <div style={{ background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 12, padding: "18px 24px" }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "#78350F", marginBottom: 10 }}>⚙ Engine Recommendation — Manual Review</div>
                  <div style={{ fontSize: 13, color: "#92400E", lineHeight: 1.6 }}>
                    Application referred to manual review. Risk classification: MEDIUM. Credit score: 612. Debt-to-income ratio: 38%. Monthly income: R12,400. Negative listings: 1. Additional assessment required by a credit analyst.
                  </div>
                  <div style={{ marginTop: 12, fontSize: 12, color: "#B45309" }}>
                    Triggering rule: <strong>Moderate score — manual review</strong> (priority 50)
                  </div>
                </div>
              </div>
            )}

            {/* Notes tab */}
            {subTab === "notes" && (
              <div>
                <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 20, marginBottom: 16 }}>
                  {notes.map((n, i) => (
                    <div key={i} style={{ padding: "12px 0", borderBottom: i < notes.length - 1 ? "1px solid #F3F4F6" : "none" }}>
                      <div style={{ display: "flex", gap: 10, marginBottom: 6 }}>
                        <div style={{ width: 28, height: 28, borderRadius: "50%", background: NAVY, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{n.author[0]}</div>
                        <div>
                          <span style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{n.author}</span>
                          <span style={{ fontSize: 12, color: "#9CA3AF", marginLeft: 8 }}>{n.time}</span>
                        </div>
                      </div>
                      <div style={{ fontSize: 13, color: "#374151", paddingLeft: 38 }}>{n.text}</div>
                    </div>
                  ))}
                </div>
                <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 20 }}>
                  <textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Add an internal note…" rows={3}
                    style={{ width: "100%", padding: "10px 14px", border: "1px solid #D1D5DB", borderRadius: 8, fontSize: 13, resize: "vertical", boxSizing: "border-box", fontFamily: "inherit" }} />
                  <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                    <button onClick={() => { if (note.trim()) { setNotes([...notes, { author: "K. Naidoo", time: "now", text: note }]); setNote(""); } }}
                      style={{ padding: "8px 20px", background: NAVY, color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 13 }}>
                      Save Note
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Documents tab */}
            {subTab === "documents" && (
              <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 20 }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16, color: "#111827" }}>Application Documents</div>
                {[
                  { name: "South African ID", type: "id_document", status: "verified", uploaded: "2026-06-10" },
                  { name: "Latest Payslip", type: "payslip", status: "verified", uploaded: "2026-06-10" },
                  { name: "3-Month Bank Statement", type: "bank_statement", status: "pending_review", uploaded: "2026-06-11" },
                  { name: "Proof of Residence", type: "proof_of_residence", status: "requested", uploaded: null },
                ].map(doc => (
                  <div key={doc.type} style={{ display: "flex", alignItems: "center", padding: "12px 0", borderBottom: "1px solid #F3F4F6", gap: 14 }}>
                    <div style={{ width: 38, height: 38, background: "#EFF6FF", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>📄</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 500, color: "#111827" }}>{doc.name}</div>
                      <div style={{ fontSize: 12, color: "#9CA3AF" }}>{doc.uploaded ? `Uploaded ${doc.uploaded}` : "Not yet uploaded"}</div>
                    </div>
                    <span style={{
                      padding: "3px 12px", borderRadius: 20, fontSize: 12, fontWeight: 500,
                      background: doc.status === "verified" ? "#F0FDF4" : doc.status === "pending_review" ? "#FFFBEB" : "#FEF2F2",
                      color: doc.status === "verified" ? "#15803D" : doc.status === "pending_review" ? "#B45309" : "#B91C1C",
                    }}>
                      {doc.status.replace("_", " ")}
                    </span>
                    {doc.status === "pending_review" && (
                      <div style={{ display: "flex", gap: 6 }}>
                        <button style={{ padding: "4px 12px", background: "#F0FDF4", color: "#15803D", border: "1px solid #BBF7D0", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>Verify</button>
                        <button style={{ padding: "4px 12px", background: "#FEF2F2", color: "#B91C1C", border: "1px solid #FCA5A5", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>Reject</button>
                      </div>
                    )}
                    {doc.status === "requested" && (
                      <button style={{ padding: "4px 12px", background: "#F3F4F6", color: "#374151", border: "1px solid #D1D5DB", borderRadius: 6, cursor: "pointer", fontSize: 12 }}>Resend request</button>
                    )}
                  </div>
                ))}
                <button style={{ marginTop: 16, padding: "10px 20px", border: `1px dashed ${NAVY}`, background: "#fff", color: NAVY, borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600, width: "100%" }}>
                  + Request Additional Document
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
