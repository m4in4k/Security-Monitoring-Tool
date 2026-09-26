"use client";

import { SignUp } from "@clerk/react";

export default function SignUpPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <SignUp routing="hash" />
    </main>
  );
}
