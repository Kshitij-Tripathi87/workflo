import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";

export const metadata: Metadata = {
  title: "Cortex Autopilot — CI/CD Impact Gate for Data Platforms",
  description:
    "Know what breaks before you deploy. Cortex Autopilot is a CI/CD Impact Gate for dbt and Snowflake teams — block risky data changes before they reach production.",
  openGraph: {
    title: "Cortex Autopilot",
    description:
      "Know what breaks before you deploy. A CI/CD Impact Gate for data platforms.",
    type: "website",
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
        <main>{children</main>
        <Footer />
     </body>
   </html>
  );
}
