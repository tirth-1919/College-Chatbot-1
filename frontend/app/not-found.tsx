export default function NotFound() {
  return (
    <main style={{ minHeight: "100vh", background: "#000", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "32px", fontFamily: "Inter,system-ui,sans-serif" }}>
      <img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" style={{ width: "72px", height: "72px", objectFit: "contain", marginBottom: "24px", borderRadius: "12px" }} />
      <h1 style={{ color: "#fff", fontSize: "22px", fontWeight: 700, margin: "0 0 10px" }}>Page Not Found</h1>
      <p style={{ color: "#a0a0a0", margin: "0 0 24px", textAlign: "center", maxWidth: "400px" }}>That page may have moved or is unavailable.</p>
      <a href="/" style={{ background: "#eee", color: "#111", borderRadius: "9px", padding: "11px 20px", fontWeight: 600, textDecoration: "none", fontSize: "14px" }}>Return to AI FAQ College Chat Bot</a>
      <p style={{ color: "#444", fontSize: "12px", marginTop: "32px" }}>AI FAQ College Chat Bot</p>
    </main>
  );
}
