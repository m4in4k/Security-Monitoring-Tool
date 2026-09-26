"use client";

import { SignIn } from "@clerk/react";

export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <SignIn routing="hash" />
    </main>
  );
}
