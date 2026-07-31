export function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{
      border: "1px solid #23304f",
      borderRadius: 16,
      padding: 16,
      background: "#11182b",
      marginBottom: 16
    }}>
      <h2 style={{ marginTop: 0, marginBottom: 12, fontSize: 18 }}>{title}</h2>
      {children}
    </section>
  );
}
