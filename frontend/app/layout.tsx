import type { Metadata } from "next";
import { ClerkClientProvider } from "@/components/clerk-client-provider";
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
  const clerkConfigured = Boolean(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
  );
  return (
    <html lang="en">
      <body className="antialiased">
        {clerkConfigured ? (
          <ClerkClientProvider>{children}</ClerkClientProvider>
        ) : (
          <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
            <section className="max-w-lg rounded-2xl border border-white/10 bg-white/[0.03] p-8">
              <h1 className="text-xl font-semibold text-white">Authentication setup required</h1>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                Configure the Clerk environment variables described in
                <code className="mx-1 text-blue-300">frontend/.env.example</code>
                before starting the Sekuro dashboard.
              </p>
            </section>
          </main>
        )}
      </body>
    </html>
  );
}
