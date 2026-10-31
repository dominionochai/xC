// Edge proxy: the browser calls /api/xc?p=<backend path>; this adds the bearer token and forwards to the backend.
// The token and the backend address live only in Vercel environment variables, never in the browser.
export const config = { runtime: "edge" };

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export default async function handler(req) {
  const base = (process.env.XC_API_BASE || "").replace(/\/$/, "");
  const token = process.env.XC_API_TOKEN || "";
  if (!base) return json(503, { detail: { message: "The backend is not configured.", missing_configuration: ["XC_API_BASE"] } });

  const url = new URL(req.url);
  let path = url.searchParams.get("p");
  url.searchParams.delete("p");
  if (path === null) path = url.pathname.replace(/^\/api\/xc\/?/, "");
  path = "/" + String(path).replace(/^\/+/, "");
  if (path.includes("..") || path.includes("//")) return json(400, { detail: "bad path" });
  const query = url.searchParams.toString();

  const headers = new Headers(req.headers);
  headers.delete("host");
  headers.delete("cookie");
  if (token) headers.set("authorization", "Bearer " + token);

  try {
    const upstream = await fetch(base + path + (query ? "?" + query : ""), {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : req.body,
      duplex: "half",
    });
    const out = new Headers(upstream.headers);
    out.delete("content-encoding");
    out.set("cache-control", "no-store");
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch (err) {
    return json(502, { detail: { message: "The backend could not be reached." } });
  }
}
