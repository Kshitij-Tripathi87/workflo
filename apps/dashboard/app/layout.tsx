import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Workflo | Voice QA Workspace",
  description: "Voice and text interface for governed software quality workflows.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
