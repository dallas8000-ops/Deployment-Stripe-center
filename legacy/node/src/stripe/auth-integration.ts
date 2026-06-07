import type { ProjectProfile } from "../types.js";

export function generateAuthIntegration(profile: ProjectProfile): Record<string, string> {
  const files: Record<string, string> = {};
  const fw = profile.framework;

  if (["django", "flask", "rails", "laravel", "unknown"].includes(fw)) {
    files["docs/STRIPE-AUTH.md"] = authGuide(profile);
    return files;
  }

  Object.assign(files, generateMeRoute(profile));
  files["docs/STRIPE-AUTH.md"] = authGuide(profile);
  return files;
}

function generateMeRoute(profile: ProjectProfile): Record<string, string> {
  const stripeImport =
    profile.framework === "nextjs"
      ? "@/lib/stripe-db"
      : profile.framework === "remix"
        ? "~/lib/stripe-db"
        : profile.framework === "nuxt"
          ? "../../utils/stripe-db"
          : profile.framework === "sveltekit"
            ? "$lib/stripe-db"
            : "../lib/stripe-db.js";

  const tsCore = `import { getStripeCustomerId, getStripeCustomerForUser } from "${stripeImport}";

export async function resolveStripeCustomer(input: {
  email?: string | null;
  userId?: string | null;
}) {
  if (input.userId) {
    const byUser = await getStripeCustomerForUser(input.userId);
    if (byUser) return { customerId: byUser, source: "user" as const };
  }
  if (input.email) {
    const byEmail = await getStripeCustomerId(input.email);
    if (byEmail) return { customerId: byEmail, source: "email" as const };
  }
  return { customerId: null, source: null };
}
`;

  switch (profile.framework) {
    case "nextjs":
      return {
        "app/api/stripe/me/route.ts": `import { NextRequest, NextResponse } from "next/server";
${tsCore}

export async function GET(req: NextRequest) {
  const email = req.headers.get("x-user-email") ?? req.nextUrl.searchParams.get("email");
  const userId = req.headers.get("x-user-id") ?? req.nextUrl.searchParams.get("userId");
  try {
    const result = await resolveStripeCustomer({ email, userId });
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Lookup failed" },
      { status: 500 }
    );
  }
}
`,
      };
    case "remix":
      return {
        "app/routes/api.stripe.me.ts": `import type { LoaderFunctionArgs } from "@remix-run/node";
${tsCore}

export async function loader({ request }: LoaderFunctionArgs) {
  const url = new URL(request.url);
  const email = request.headers.get("x-user-email") ?? url.searchParams.get("email");
  const userId = request.headers.get("x-user-id") ?? url.searchParams.get("userId");
  try {
    return Response.json(await resolveStripeCustomer({ email, userId }));
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "Lookup failed" }, { status: 500 });
  }
}
`,
      };
    case "nuxt":
      return {
        "server/api/stripe/me.get.ts": `import { getHeader, getQuery } from "h3";
${tsCore}

export default defineEventHandler(async (event) => {
  const q = getQuery(event);
  const email = getHeader(event, "x-user-email") ?? (q.email as string | undefined);
  const userId = getHeader(event, "x-user-id") ?? (q.userId as string | undefined);
  return resolveStripeCustomer({ email, userId });
});
`,
      };
    case "sveltekit":
      return {
        "src/routes/api/stripe/me/+server.ts": `import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
${tsCore}

export const GET: RequestHandler = async ({ request, url }) => {
  const email = request.headers.get("x-user-email") ?? url.searchParams.get("email");
  const userId = request.headers.get("x-user-id") ?? url.searchParams.get("userId");
  try {
    return json(await resolveStripeCustomer({ email, userId }));
  } catch (err) {
    throw error(500, err instanceof Error ? err.message : "Lookup failed");
  }
};
`,
      };
    default:
      return {};
  }
}

function authGuide(profile: ProjectProfile): string {
  return `# Stripe + Auth integration — ${profile.framework}

## Checkout → user linking
Pass your auth user id when creating checkout:
\`\`\`json
{ "tier": "pro", "userId": "<auth-user-id>", "customerEmail": "user@example.com" }
\`\`\`
Webhook \`checkout.session.completed\` stores \`client_reference_id\` on \`stripe_customers.user_id\`.

## Lookup customer for account page
\`GET /api/stripe/me\` (or \`/stripe/me\` for Python/Ruby/PHP stacks)

Headers (preferred in production):
- \`x-user-id\` — your auth user id
- \`x-user-email\` — fallback lookup by email

Query params (dev): \`?userId=\` or \`?email=\`

## NextAuth / Clerk / Django User
1. After login, call \`/api/stripe/me\` with user headers
2. Use returned \`customerId\` for billing portal
3. Never expose STRIPE_SECRET_KEY to the client

## Database
Requires \`DATABASE_URL\` and \`db/schema.sql\` applied.
Tables: \`users\`, \`stripe_customers\`, \`subscriptions\`
`;
}
