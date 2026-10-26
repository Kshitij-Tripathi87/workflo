import "./globals.css";
import type { Metadata } from "next";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { AuthGuard } from "../components/AuthGuard";

export const metadata: Metadata = {
  title: "Cortex Autopilot",
  description: "Enterprise decision intelligence for data platforms",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ErrorBoundary>
          <AuthGuard>{children}</AuthGuard>
        </ErrorBoundary>
      </body>
    </html>
  );
}
