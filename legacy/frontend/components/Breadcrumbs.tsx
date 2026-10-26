"use client";

/**
 * Breadcrumbs — small asset navigation trail.
 *
 * Lets the user quickly jump from an impacted downstream asset back up
 * to the source of the change.
 */

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

export function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav
      aria-label="Asset breadcrumbs"
      style={{
        display: "flex",
        gap: 6,
        alignItems: "center",
        fontSize: 12,
        color: "#94a3b8",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        flexWrap: "wrap",
      }}
    >
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1;
        return (
          <span key={idx} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            {item.href || item.onClick ? (
              <a
                href={item.href}
                onClick={(e) => {
                  if (item.onClick) {
                    e.preventDefault();
                    item.onClick();
                  }
                }}
                style={{
                  color: "#60a5fa",
                  textDecoration: "none",
                  padding: "2px 6px",
                  borderRadius: 4,
                  background: "rgba(59, 130, 246, 0.08)",
                  cursor: "pointer",
                }}
              >
                {item.label}
             </a>
            ) : (
              <span style={{ color: isLast ? "#e2e8f0" : "#94a3b8", fontWeight: isLast ? 600 : 400 }}>
                {item.label}
             </span>
            )}
            {!isLast && <span style={{ color: "#475569" }}>›</span>}
         </span>
        );
      })}
   </nav>
  );
}
