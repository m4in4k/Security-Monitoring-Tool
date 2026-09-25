import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sekuro | Security Monitoring Dashboard",
  description:
    "Monitor website availability, TLS certificates, security headers, and alerts from one dashboard.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
