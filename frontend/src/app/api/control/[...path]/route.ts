// Same-origin proxy for the public server control API (/api/control/*).
//
// The admin panel calls the backend directly on its own port, but the control
// page has to work through a single public address too (e.g. a Playit tunnel to
// the panel's port), where that second port isn't reachable. So the browser
// talks to this route and the Next server forwards to the backend over the
// internal network. Only /api/control is proxied: the admin API stays private.
//   BACKEND_INTERNAL_URL  backend as seen from this container (default http://backend:8000)
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND = (process.env.BACKEND_INTERNAL_URL || "http://backend:8000").replace(/\/$/, "");

async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const url = `${BACKEND}/api/control/${path.map(encodeURIComponent).join("/")}`;

  const headers: Record<string, string> = {};
  for (const name of ["authorization", "content-type", "x-forwarded-for", "x-real-ip"]) {
    const value = req.headers.get(name);
    if (value) headers[name] = value;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" ? undefined : await req.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "panel backend unreachable" }, { status: 502 });
  }
  return new Response(res.body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
  });
}

export { proxy as GET, proxy as POST };
