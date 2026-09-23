// The site is static assets; this script exists only for POST /api/contact, the
// contact form on /about/. wrangler.jsonc routes /api/* here and everything else
// straight to public/.
//
// A message is checked by Turnstile, then sent through the send_email binding to one
// verified Email Routing destination (the CONTACT_TO secret), with the visitor's
// address as Reply-To. Nothing is stored.

const LIMITS = { name: 100, email: 254, message: 5000 };

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/contact") return json({ error: "Not found." }, 404);
    if (request.method !== "POST") return json({ error: "Method not allowed." }, 405, { Allow: "POST" });

    let form;
    try {
      form = await request.formData();
    } catch {
      return json({ error: "The form could not be read." }, 400);
    }

    // Honeypot: a field hidden from people. Pretend it worked.
    if (field(form, "website")) return json({ ok: true });

    const name = field(form, "name").replace(/[\r\n]+/g, " ");
    const email = field(form, "email");
    const message = field(form, "message");

    if (!email || !message) return json({ error: "An email address and a message are both needed." }, 400);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json({ error: "That email address does not look right." }, 400);
    for (const [key, max] of Object.entries(LIMITS)) {
      if (field(form, key).length > max) return json({ error: `The ${key} is longer than ${max} characters.` }, 400);
    }

    const human = await verifyTurnstile(env, field(form, "cf-turnstile-response"), request.headers.get("CF-Connecting-IP"));
    if (!human) return json({ error: "The spam check did not pass. Reload the page and try again." }, 403);

    try {
      await env.CONTACT.send({
        to: env.CONTACT_TO,
        from: { email: env.CONTACT_FROM, name: "Mazatzal Hiking" },
        replyTo: name ? { email, name } : email,
        subject: `Mazatzal Hiking: message from ${name || email}`,
        text: `${message}\n\n— ${name ? `${name} <${email}>` : email}\nSent from the contact form on ${url.origin}/about/`,
      });
    } catch (err) {
      console.error("contact send failed", err?.code, err?.message);
      return json({ error: "The message could not be sent. Please try again later." }, 502);
    }

    return json({ ok: true });
  },
};

function field(form, key) {
  const v = form.get(key);
  return typeof v === "string" ? v.trim() : "";
}

async function verifyTurnstile(env, token, ip) {
  if (!token || !env.TURNSTILE_SECRET) return false;
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET);
  body.append("response", token);
  if (ip) body.append("remoteip", ip);
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body });
  const out = await res.json().catch(() => ({}));
  return out.success === true;
}

function json(data, status = 200, headers = {}) {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store", ...headers } });
}
