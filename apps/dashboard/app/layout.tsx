import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Tenant Shield',
  description: 'Multi-tenant isolation testing platform with SOC 2 evidence reporting.',
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
