// Served at /runtime-config.js and loaded before the app bundles, so a prebuilt
// image can be pointed at its backend with env vars read when the container
// starts (NEXT_PUBLIC_* would be frozen at build time).
//   API_URL   full backend URL, e.g. http://192.168.1.10:3129
//   API_PORT  just the port; the host is the one the panel was opened from
export const dynamic = "force-dynamic";

export function GET() {
  const config = {
    apiUrl: process.env.API_URL || "",
    apiPort: process.env.API_PORT || "",
  };
  return new Response(`window.__RUNTIME_CONFIG__ = ${JSON.stringify(config)};`, {
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
