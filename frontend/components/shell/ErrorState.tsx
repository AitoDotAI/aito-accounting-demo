interface ErrorStateProps {
  title?: string;
  message?: string;
}

export default function ErrorState({
  title = "Could not load data",
  message = "Start the backend with ./do dev and reload this page.",
}: ErrorStateProps) {
  return (
    <div style={{
      padding: "48px 24px",
      textAlign: "center",
      color: "var(--text3)",
    }}>
      <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text2)", marginBottom: 8 }}>
        {title}
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.6 }}>
        {message}
      </div>
      <div style={{
        marginTop: 16,
        padding: "8px 14px",
        background: "var(--surface2)",
        borderRadius: 6,
        display: "inline-block",
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 12,
      }}>
        ./do dev
      </div>
    </div>
  );
}
