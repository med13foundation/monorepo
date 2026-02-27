import { withAuth } from "next-auth/middleware"
import type { JWT } from "next-auth/jwt"

function hasValidTokenExpiry(token: JWT): boolean {
  const now = Date.now()
  if (Number.isFinite(token.expires_at)) {
    return now < token.expires_at
  }
  const exp = token.exp
  if (typeof exp === "number" && Number.isFinite(exp)) {
    return now < exp * 1000
  }
  return false
}

export default withAuth(
  function middleware(req) {
    // Add any additional middleware logic here
  },
  {
    callbacks: {
      authorized: ({ token }) => (token ? hasValidTokenExpiry(token) : false),
    },
  }
)

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - api/auth (NextAuth.js routes)
     * - _next/* (Next.js internals: static, image, HMR, etc.)
     * - favicon.ico (favicon file)
     * - auth/* (login, register, forgot-password pages)
     * - e2e/* (Playwright-only routes)
     */
    "/((?!api/auth|auth/|_next/|favicon.ico|e2e/).*)",
  ],
}
