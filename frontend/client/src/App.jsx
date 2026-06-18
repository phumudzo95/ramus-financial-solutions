import { useState } from "react";

const NAVY = "#0a2463";
const GOLD = "#FFD700";

// Lightweight responsive rules for containers below that use fixed inline layouts.
// Targets: .rfs-c-header (top nav row), .rfs-c-steps (step indicator labels),
// .rfs-c-calc-row (loan calculator inputs).
const RESPONSIVE_CSS = `
  @media (max-width: 640px) {
    .rfs-c-header { padding: 12px 16px !important; flex-wrap: wrap; gap: 10px !important; }
    .rfs-c-header > div:nth-child(2) { font-size: 14px !important; }
    .rfs-c-nav-btns { width: 100%; justify-content: flex-start !important; overflow-x: auto; }
    .rfs-c-steps .rfs-c-step-label { display: none; }
  }
`;

function ResponsiveStyle() {
  return <style>{RESPONSIVE_CSS}</style>;
}

const STEPS = ["Personal Details", "Financial Info", "Consent", "Submit"];

const STATUS_STEPS = [
  { key: "submitted", label: "Submitted", icon: "✓" },
  { key: "under_review", label: "Under Review", icon: "🔍" },
  { key: "decision", label: "Decision", icon: "⚖" },
  { key: "completed", label: "Completed", icon: "🎉" },
];

const MOCK_APPS = [
  { ref: "RCL-X7K29MQA", amount: 3000, status: "manual_review", status_label: "Under Review", submitted: "10 Jun 2026", updated: "11 Jun 2026" },
];

export default function ClientPortal() {
  const [view, setView] = useState("home");
  const [step, setStep] = useState(0);
  const [consentChecked, setConsentChecked] = useState(false);
  const [form, setForm] = useState({ amount: "", term: "0", purpose: "", income: "", expenses: "", employer: "", employment_type: "employed" });
  const [submitted, setSubmitted] = useState(false);

  const update = (k, v) => setForm(f => ({ ...f, [k]: v }));
  // Ramus Financial Solutions product: max R5,000, fixed 30% cost of credit.
  // term "0" = pay in full after 30 days; "1"-"6" = that many monthly instalments.
  const COST_OF_CREDIT_PERCENT = 0.30;
  const totalRepayable = form.amount ? Math.round(parseFloat(form.amount) * (1 + COST_OF_CREDIT_PERCENT)) : null;
  const monthlyPayment = totalRepayable && form.term && parseInt(form.term) > 0
    ? Math.round(totalRepayable / parseInt(form.term))
    : null;

  const inputStyle = { width: "100%", padding: "10px 14px", border: "1.5px solid #D1D5DB", borderRadius: 10, fontSize: 14, boxSizing: "border-box", fontFamily: "inherit", outline: "none" };
  const labelStyle = { display: "block", fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 6 };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#F9FAFB" }}>
      <ResponsiveStyle />
      {/* Header */}
      <div className="rfs-c-header" style={{ background: NAVY, display: "flex", alignItems: "center", gap: 14, padding: "14px 24px", borderBottom: `3px solid ${GOLD}` }}>
        <div style={{ background: GOLD, borderRadius: 8, width: 38, height: 38, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, color: NAVY, fontSize: 17 }}>R</div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 17, color: "#fff", letterSpacing: 0.5 }}>RAMUS FINANCIAL SOLUTIONS</div>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.6)", letterSpacing: 1 }}>NCR REGISTERED CREDIT PROVIDER</div>
        </div>
        <div className="rfs-c-nav-btns" style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {["home", "apply", "status"].map(v => (
            <button key={v} onClick={() => setView(v)} style={{ padding: "8px 18px", background: view === v ? GOLD : "transparent", color: view === v ? NAVY : "#fff", border: `1px solid ${view === v ? GOLD : "rgba(255,255,255,0.3)"}`, borderRadius: 8, cursor: "pointer", fontWeight: view === v ? 700 : 400, fontSize: 13, flexShrink: 0 }}>
              {v === "home" ? "Home" : v === "apply" ? "Apply Now" : "My Applications"}
            </button>
          ))}
        </div>
      </div>

      {/* HOME */}
      {view === "home" && (
        <div>
          <div style={{ background: `linear-gradient(135deg, ${NAVY} 0%, #1a3a8f 100%)`, color: "#fff", padding: "60px 24px", textAlign: "center" }}>
            <div style={{ maxWidth: 580, margin: "0 auto" }}>
              <h1 style={{ fontSize: 38, fontWeight: 800, margin: "0 0 16px", lineHeight: 1.2 }}>
                Fast, Responsible<br /><span style={{ color: GOLD }}>Cash Loans</span>
              </h1>
              <p style={{ fontSize: 17, color: "rgba(255,255,255,0.8)", margin: "0 0 36px" }}>Apply in minutes. Decision within 24 hours. Transparent terms.</p>
              <button onClick={() => setView("apply")} style={{ background: GOLD, color: NAVY, border: "none", borderRadius: 12, padding: "16px 48px", fontSize: 17, fontWeight: 800, cursor: "pointer" }}>
                Apply Now
              </button>
            </div>
          </div>

          <div style={{ maxWidth: 780, margin: "48px auto", padding: "0 24px" }}>
            <h2 style={{ textAlign: "center", fontSize: 24, fontWeight: 700, color: "#111827", marginBottom: 32 }}>How It Works</h2>
            <div style={{ display: "flex", gap: 20 }}>
              {[
                ["1", "Apply Online", "Complete your application in minutes — no branch visit required."],
                ["2", "We Review", "Our team reviews your application and credit profile securely."],
                ["3", "Get Your Funds", "Approved funds deposited directly into your bank account."],
              ].map(([num, title, desc]) => (
                <div key={num} style={{ flex: 1, background: "#fff", borderRadius: 14, padding: "24px", border: "1px solid #E5E7EB", textAlign: "center" }}>
                  <div style={{ width: 48, height: 48, borderRadius: "50%", background: NAVY, color: GOLD, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 20, margin: "0 auto 14px" }}>{num}</div>
                  <div style={{ fontWeight: 700, fontSize: 16, color: "#111827", marginBottom: 8 }}>{title}</div>
                  <div style={{ fontSize: 13, color: "#6B7280", lineHeight: 1.6 }}>{desc}</div>
                </div>
              ))}
            </div>

            <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #E5E7EB", padding: 28, marginTop: 28 }}>
              <h3 style={{ margin: "0 0 8px", color: "#111827" }}>Loan Calculator</h3>
              <p style={{ margin: "0 0 20px", color: "#6B7280", fontSize: 13 }}>See exactly what your loan will cost — fixed 30% cost of credit, no surprises</p>
              <div style={{ display: "flex", gap: 20, alignItems: "flex-end", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label style={labelStyle}>Loan Amount (ZAR, max 5,000)</label>
                  <input type="number" min="500" max="5000" value={form.amount} onChange={e => update("amount", e.target.value)} placeholder="e.g. 3000" style={inputStyle} />
                </div>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label style={labelStyle}>Repayment Option</label>
                  <select value={form.term} onChange={e => update("term", e.target.value)} style={inputStyle}>
                    <option value="0">Pay in full after 30 days</option>
                    {[1,2,3,4,5,6].map(m => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""} instalments</option>)}
                  </select>
                </div>
                {totalRepayable && (
                  <div style={{ textAlign: "center", padding: "10px 24px", background: "#F0FDF4", border: "2px solid #BBF7D0", borderRadius: 10 }}>
                    <div style={{ fontSize: 22, fontWeight: 700, color: "#15803D" }}>
                      R {(monthlyPayment || totalRepayable).toLocaleString()}
                    </div>
                    <div style={{ fontSize: 12, color: "#6B7280" }}>
                      {monthlyPayment ? `per month for ${form.term} months` : "total repayable after 30 days"}
                    </div>
                  </div>
                )}
              </div>
              <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 12 }}>Fixed cost of credit: 30% of the loan amount. Maximum loan amount: R5,000. Subject to approval.</div>
            </div>
          </div>
        </div>
      )}

      {/* APPLY */}
      {view === "apply" && !submitted && (
        <div style={{ maxWidth: 600, margin: "36px auto", padding: "0 24px" }}>
          <h2 style={{ fontWeight: 700, fontSize: 24, color: "#111827", marginBottom: 8 }}>Loan Application</h2>
          <p style={{ color: "#6B7280", fontSize: 14, marginBottom: 28 }}>Secure, encrypted. Your information is never shared without your consent.</p>

          {/* Step indicators */}
          <div className="rfs-c-steps" style={{ display: "flex", alignItems: "center", marginBottom: 36 }}>
            {STEPS.map((s, i) => (
              <div key={s} style={{ display: "flex", alignItems: "center", flex: i < STEPS.length - 1 ? 1 : 0 }}>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div style={{ width: 32, height: 32, borderRadius: "50%", background: i <= step ? NAVY : "#E5E7EB", color: i <= step ? "#fff" : "#9CA3AF", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13 }}>
                    {i < step ? "✓" : i + 1}
                  </div>
                  <div className="rfs-c-step-label" style={{ fontSize: 11, color: i === step ? NAVY : "#9CA3AF", marginTop: 4, whiteSpace: "nowrap" }}>{s}</div>
                </div>
                {i < STEPS.length - 1 && <div style={{ flex: 1, height: 2, background: i < step ? NAVY : "#E5E7EB", margin: "0 6px", marginBottom: 18 }} />}
              </div>
            ))}
          </div>

          <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #E5E7EB", padding: 30 }}>
            {step === 0 && (
              <div>
                <h3 style={{ margin: "0 0 22px", color: "#111827" }}>Personal Details</h3>
                {[["First Name", "first_name", "text", "e.g. Thabo"], ["Last Name", "last_name", "text", "e.g. Mokoena"], ["ID Number", "id_number", "text", "13-digit SA ID number"], ["Phone", "phone", "tel", "e.g. 082 123 4567"]].map(([label, key, type, ph]) => (
                  <div key={key} style={{ marginBottom: 18 }}>
                    <label style={labelStyle}>{label}</label>
                    <input type={type} placeholder={ph} style={inputStyle} />
                  </div>
                ))}
              </div>
            )}

            {step === 1 && (
              <div>
                <h3 style={{ margin: "0 0 22px", color: "#111827" }}>Loan & Financial Info</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 18 }}>
                  <div>
                    <label style={labelStyle}>Amount Requested (R, max 5,000)</label>
                    <input type="number" min="500" max="5000" value={form.amount} onChange={e => update("amount", e.target.value)} placeholder="e.g. 3000" style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Repayment Option</label>
                    <select value={form.term} onChange={e => update("term", e.target.value)} style={inputStyle}>
                      <option value="0">Pay in full after 30 days</option>
                      {[1,2,3,4,5,6].map(m => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""} instalments</option>)}
                    </select>
                  </div>
                </div>
                <div style={{ marginBottom: 18 }}>
                  <label style={labelStyle}>Loan Purpose</label>
                  <select style={inputStyle}>
                    <option>Select purpose…</option>
                    <option>Debt consolidation</option>
                    <option>Home improvement</option>
                    <option>Education</option>
                    <option>Medical expenses</option>
                    <option>Vehicle</option>
                    <option>Other</option>
                  </select>
                </div>
                {[["Gross Monthly Income (R)", "income", "e.g. 12000"], ["Monthly Expenses (R)", "expenses", "e.g. 6000"]].map(([label, key, ph]) => (
                  <div key={key} style={{ marginBottom: 18 }}>
                    <label style={labelStyle}>{label}</label>
                    <input type="number" value={form[key]} onChange={e => update(key, e.target.value)} placeholder={ph} style={inputStyle} />
                  </div>
                ))}
                <div style={{ marginBottom: 18 }}>
                  <label style={labelStyle}>Employment Type</label>
                  <select value={form.employment_type} onChange={e => update("employment_type", e.target.value)} style={inputStyle}>
                    <option value="employed">Permanently Employed</option>
                    <option value="contract">Contract / Fixed Term</option>
                    <option value="self_employed">Self-Employed</option>
                    <option value="pensioner">Pensioner</option>
                  </select>
                </div>
                <div style={{ marginBottom: 18 }}>
                  <label style={labelStyle}>Employer Name</label>
                  <input type="text" placeholder="e.g. Woolworths (Pty) Ltd" style={inputStyle} />
                </div>
              </div>
            )}

            {step === 2 && (
              <div>
                <h3 style={{ margin: "0 0 8px", color: "#111827" }}>Credit Check Consent</h3>
                <p style={{ fontSize: 13, color: "#6B7280", marginBottom: 20, lineHeight: 1.6 }}>Before we can assess your application, we need your consent to access your credit profile. Please read the following carefully.</p>
                <div style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", borderRadius: 10, padding: "16px 18px", fontSize: 13, color: "#374151", lineHeight: 1.7, marginBottom: 22, maxHeight: 150, overflowY: "auto" }}>
                  I authorise <strong>Ramus Financial Solutions</strong>, a registered credit provider (NCR Registration: NCRCP19178), to request my credit report and credit score from <strong>TransUnion Credit Bureau</strong> and/or any other registered credit bureau for the purpose of assessing my loan application. I understand that this enquiry will be recorded on my credit profile. This consent is valid for the duration of my current loan application.
                </div>
                <label style={{ display: "flex", gap: 14, cursor: "pointer", alignItems: "flex-start" }}>
                  <input type="checkbox" checked={consentChecked} onChange={e => setConsentChecked(e.target.checked)}
                    style={{ width: 18, height: 18, marginTop: 2, accentColor: NAVY, flexShrink: 0 }} />
                  <span style={{ fontSize: 14, color: "#111827", lineHeight: 1.5 }}>
                    I have read and understand the above consent declaration and <strong>authorise Ramus Financial Solutions to access my credit profile</strong>.
                  </span>
                </label>

                <div style={{ marginTop: 20, background: "#EFF6FF", borderRadius: 10, padding: "14px 18px", fontSize: 12, color: "#1D4ED8" }}>
                  🔒 Your information is encrypted and stored securely. It is never sold or shared with third parties.
                </div>
              </div>
            )}

            {step === 3 && (
              <div>
                <h3 style={{ margin: "0 0 22px", color: "#111827" }}>Review & Submit</h3>
                {[["Requested Amount", `R ${parseFloat(form.amount || 0).toLocaleString()}`], ["Repayment Option", form.term === "0" ? "Pay in full after 30 days" : `${form.term} month instalments`], ["Total Repayable", totalRepayable ? `R ${totalRepayable.toLocaleString()}` : "—"], ["Employment Type", form.employment_type], ["Consent Granted", consentChecked ? "Yes ✓" : "Not yet"]].map(([k, v]) => (
                  <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "12px 0", borderBottom: "1px solid #F3F4F6" }}>
                    <span style={{ fontSize: 14, color: "#6B7280" }}>{k}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>{v}</span>
                  </div>
                ))}
                <div style={{ background: "#FFF3A3", border: `1px solid ${GOLD}`, borderRadius: 10, padding: "14px 18px", marginTop: 20, fontSize: 13, color: "#78350F" }}>
                  By submitting, you confirm all information provided is accurate and complete. Providing false information is a criminal offence under the National Credit Act.
                </div>
              </div>
            )}

            {/* Navigation */}
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 28 }}>
              <button onClick={() => setStep(Math.max(0, step - 1))} style={{ padding: "12px 24px", border: "1.5px solid #D1D5DB", background: "#fff", borderRadius: 10, cursor: step === 0 ? "not-allowed" : "pointer", color: step === 0 ? "#D1D5DB" : "#374151", fontSize: 14 }} disabled={step === 0}>
                Back
              </button>
              {step < 3 ? (
                <button onClick={() => setStep(step + 1)}
                  disabled={step === 2 && !consentChecked}
                  style={{ padding: "12px 32px", background: (step === 2 && !consentChecked) ? "#E5E7EB" : NAVY, color: (step === 2 && !consentChecked) ? "#9CA3AF" : "#fff", border: "none", borderRadius: 10, cursor: (step === 2 && !consentChecked) ? "not-allowed" : "pointer", fontWeight: 700, fontSize: 14 }}>
                  Continue
                </button>
              ) : (
                <button onClick={() => setSubmitted(true)} style={{ padding: "12px 32px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 10, cursor: "pointer", fontWeight: 700, fontSize: 14 }}>
                  Submit Application
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* SUBMITTED */}
      {view === "apply" && submitted && (
        <div style={{ maxWidth: 520, margin: "60px auto", textAlign: "center", padding: "0 24px" }}>
          <div style={{ width: 72, height: 72, borderRadius: "50%", background: "#F0FDF4", border: "2px solid #BBF7D0", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, margin: "0 auto 24px" }}>✓</div>
          <h2 style={{ fontSize: 26, fontWeight: 700, color: "#111827", marginBottom: 12 }}>Application Submitted!</h2>
          <p style={{ color: "#6B7280", fontSize: 15, marginBottom: 24 }}>Your reference number is <strong style={{ color: NAVY, fontFamily: "monospace" }}>RCL-H9T56LSE</strong>. We've sent a confirmation to your email.</p>
          <button onClick={() => { setView("status"); setSubmitted(false); setStep(0); }} style={{ padding: "12px 32px", background: NAVY, color: "#fff", border: "none", borderRadius: 10, cursor: "pointer", fontWeight: 700, fontSize: 14 }}>
            Track My Application
          </button>
        </div>
      )}

      {/* STATUS */}
      {view === "status" && (
        <div style={{ maxWidth: 680, margin: "36px auto", padding: "0 24px" }}>
          <h2 style={{ fontWeight: 700, fontSize: 24, color: "#111827", marginBottom: 24 }}>My Applications</h2>
          {MOCK_APPS.map(app => (
            <div key={app.ref} style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 14, padding: 28, marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
                <div>
                  <div style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 15, color: NAVY, marginBottom: 4 }}>{app.ref}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#111827" }}>R {app.amount.toLocaleString()}</div>
                  <div style={{ fontSize: 13, color: "#6B7280", marginTop: 2 }}>Submitted {app.submitted}</div>
                </div>
                <span style={{ background: "#FEF3C7", color: "#92400E", padding: "5px 16px", borderRadius: 20, fontSize: 13, fontWeight: 600 }}>
                  {app.status_label}
                </span>
              </div>

              {/* Progress track */}
              <div style={{ display: "flex", alignItems: "flex-start", marginBottom: 24 }}>
                {STATUS_STEPS.map((s, i) => {
                  const isActive = i <= 1;
                  return (
                    <div key={s.key} style={{ flex: i < STATUS_STEPS.length - 1 ? 1 : 0, display: "flex", flexDirection: "column", alignItems: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
                        <div style={{ width: 32, height: 32, borderRadius: "50%", background: isActive ? NAVY : "#E5E7EB", color: isActive ? "#fff" : "#9CA3AF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>
                          {s.icon}
                        </div>
                        {i < STATUS_STEPS.length - 1 && (
                          <div style={{ flex: 1, height: 2, background: i < 1 ? NAVY : "#E5E7EB", margin: "0 4px" }} />
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: isActive ? NAVY : "#9CA3AF", marginTop: 6, textAlign: "center" }}>{s.label}</div>
                    </div>
                  );
                })}
              </div>

              <div style={{ background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 10, padding: "14px 18px", fontSize: 13, color: "#92400E" }}>
                📋 Your application is being reviewed by a credit analyst. This usually takes 1–2 business days. You'll receive an email when a decision is made.
              </div>

              <div style={{ marginTop: 16 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: "#111827", marginBottom: 10 }}>Documents</div>
                {[["South African ID", "✓ Verified"], ["Latest Payslip", "✓ Verified"], ["Bank Statement (3 months)", "⏳ Under review"]].map(([doc, status]) => (
                  <div key={doc} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #F3F4F6", fontSize: 13 }}>
                    <span style={{ color: "#374151" }}>{doc}</span>
                    <span style={{ color: status.startsWith("✓") ? "#15803D" : "#B45309", fontWeight: 500 }}>{status}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{ background: NAVY, color: "rgba(255,255,255,0.6)", padding: "20px 24px", textAlign: "center", fontSize: 12, marginTop: 40 }}>
        Ramus Financial Solutions — Registered Credit Provider | NCR Registration: NCRCP19178 | Subject to the National Credit Act 34 of 2005
      </div>
    </div>
  );
}
