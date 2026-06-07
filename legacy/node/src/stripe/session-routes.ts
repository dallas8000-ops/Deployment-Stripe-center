import type { Framework, ProjectProfile } from "../types.js";
import { libDir } from "./framework-profiles.js";

/** Resolve db module import for generated stripe-db.ts */
export function stripeDbImportPath(profile: ProjectProfile): string {
  switch (profile.framework) {
    case "nextjs":
      return "@/lib/db";
    case "remix":
      return "~/lib/db";
    case "nuxt":
      return "./db";
    case "sveltekit":
      return "$lib/db";
    case "express":
    case "fastify":
    case "react":
      return "../lib/db.js";
    default:
      return "./db";
  }
}

export function sessionInfoApiPath(framework: Framework): string {
  switch (framework) {
    case "nextjs":
    case "remix":
    case "nuxt":
    case "sveltekit":
    case "react":
      return "/api/stripe/session";
    default:
      return "/stripe/session";
  }
}

export function generateSessionInfoRoute(profile: ProjectProfile): Record<string, string> {
  const stripeImport =
    profile.framework === "nextjs"
      ? "@/lib/stripe"
      : profile.framework === "remix"
        ? "~/lib/stripe"
        : profile.framework === "nuxt"
          ? "../../utils/stripe"
          : profile.framework === "sveltekit"
            ? "$lib/stripe"
            : "../lib/stripe.js";

  const tsHandler = `import { stripe } from "${stripeImport}";

export async function resolveCheckoutSession(sessionId: string) {
  const session = await stripe.checkout.sessions.retrieve(sessionId);
  const customerId =
    typeof session.customer === "string" ? session.customer : session.customer?.id ?? null;
  return {
    customerId,
    email: session.customer_email ?? session.customer_details?.email ?? null,
    status: session.status,
  };
}
`;

  const files: Record<string, string> = {};

  switch (profile.framework) {
    case "nextjs":
      files["app/api/stripe/session/route.ts"] = `import { NextRequest, NextResponse } from "next/server";
${tsHandler}

export async function POST(req: NextRequest) {
  const { sessionId } = await req.json();
  if (!sessionId) return NextResponse.json({ error: "sessionId required" }, { status: 400 });
  try {
    return NextResponse.json(await resolveCheckoutSession(sessionId));
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Invalid session" }, { status: 400 });
  }
}
`;
      break;
    case "remix":
      files["app/routes/api.stripe.session.ts"] = `import type { ActionFunctionArgs } from "@remix-run/node";
${tsHandler}

export async function action({ request }: ActionFunctionArgs) {
  const { sessionId } = await request.json();
  if (!sessionId) return Response.json({ error: "sessionId required" }, { status: 400 });
  try {
    return Response.json(await resolveCheckoutSession(sessionId));
  } catch (err) {
    return Response.json({ error: err instanceof Error ? err.message : "Invalid session" }, { status: 400 });
  }
}
`;
      break;
    case "nuxt":
      files["server/api/stripe/session.post.ts"] = `import { readBody, createError } from "h3";
${tsHandler}

export default defineEventHandler(async (event) => {
  const { sessionId } = await readBody<{ sessionId: string }>(event);
  if (!sessionId) throw createError({ statusCode: 400, statusMessage: "sessionId required" });
  try {
    return await resolveCheckoutSession(sessionId);
  } catch (err) {
    throw createError({ statusCode: 400, statusMessage: (err as Error).message });
  }
});
`;
      break;
    case "sveltekit":
      files["src/routes/api/stripe/session/+server.ts"] = `import { json, error } from "@sveltejs/kit";
import type { RequestHandler } from "./$types";
${tsHandler}

export const POST: RequestHandler = async ({ request }) => {
  const { sessionId } = await request.json();
  if (!sessionId) throw error(400, "sessionId required");
  try {
    return json(await resolveCheckoutSession(sessionId));
  } catch (err) {
    throw error(400, err instanceof Error ? err.message : "Invalid session");
  }
};
`;
      break;
    case "express":
    case "fastify":
    case "react":
      break;
    default:
      break;
  }

  return files;
}

export function successPageSessionScript(sessionApiPath: string): string {
  return `
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (!sessionId) return;
    fetch("${sessionApiPath}", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
        if (data.email) localStorage.setItem("stripe_customer_email", data.email);
      })
      .catch(() => undefined);
  }, []);
`.trim();
}

export function vanillaSuccessSessionScript(sessionApiPath: string): string {
  return `
  <script>
    (function () {
      const sessionId = new URLSearchParams(location.search).get("session_id");
      if (!sessionId) return;
      fetch("${sessionApiPath}", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.customerId) localStorage.setItem("stripe_customer_id", data.customerId);
          if (data.email) localStorage.setItem("stripe_customer_email", data.email);
        })
        .catch(function () {});
    })();
  </script>`;
}
