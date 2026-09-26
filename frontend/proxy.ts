import { clerkMiddleware } from "@clerk/nextjs/server";

const PUBLIC_ROUTE_PREFIXES = ["/sign-in", "/sign-up"];

export default clerkMiddleware(async (auth, request) => {
  const isPublicRoute = PUBLIC_ROUTE_PREFIXES.some((prefix) =>
    request.nextUrl.pathname.startsWith(prefix),
  );
  if (!isPublicRoute) await auth.protect();
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.[a-zA-Z0-9]+).*)",
  ],
};
