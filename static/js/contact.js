// The contact form on /about/: send it with fetch and report the result in place.
(function () {
  const form = document.getElementById("contact");
  if (!form) return;
  const status = form.querySelector(".contact-status");
  const button = form.querySelector("button[type=submit]");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    button.disabled = true;
    status.textContent = "Sending…";
    status.className = "contact-status";
    let ok = false, error = "The message could not be sent. Please try again later.";
    try {
      const res = await fetch(form.action, { method: "POST", body: new FormData(form) });
      const out = await res.json().catch(() => ({}));
      ok = res.ok && out.ok;
      if (out.error) error = out.error;
    } catch {}
    if (ok) {
      form.reset();
      status.textContent = "Sent. Thank you.";
      status.classList.add("is-ok");
    } else {
      status.textContent = error;
      status.classList.add("is-error");
    }
    // A Turnstile token is good for one check; get a fresh one for the next send.
    if (window.turnstile) window.turnstile.reset();
    button.disabled = false;
  });
})();
