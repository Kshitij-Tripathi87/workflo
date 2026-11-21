import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";

export const metadata: Metadata = {
  title: {
    default: "Workflo — Autonomous QA with evidence",
    template: "%s — Workflo",
  },
  description:
    "Run repository-native tests, probe application behavior, and produce evidence-backed QA reports with controlled, local-first execution.",
  applicationName: "Workflo",
  openGraph: {
    title: "Workflo — Autonomous QA with evidence",
    description:
      "Repository-native QA, governed exploration, and evidence you can inspect.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Workflo — Autonomous QA with evidence",
    description:
      "Repository-native QA, governed exploration, and evidence you can inspect.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
