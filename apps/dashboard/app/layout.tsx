import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Workflo',
  description:
    'Execution assurance for AI-assisted software changes — verified runs, evidence and signed receipts.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
