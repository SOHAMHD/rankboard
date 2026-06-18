/* ════════════════════════════════════════════════════════════════════
   EMAIL SERVICE — now with a real transport.

   How the transport is chosen (config, not code):
   • RESEND_API_KEY set      → the email is ACTUALLY sent via Resend's
                               API, and also logged to the outbox table.
   • RESEND_API_KEY not set  → dev mode: outbox only (what you see in
                               the UI). Nothing else in the app knows
                               or cares which mode is active.

   To go live:
     1. Create a free account at https://resend.com and make an API key
     2. Start the server with it:
          RESEND_API_KEY=re_xxxx npm run dev
     3. Reality check on deliverability: until you verify YOUR domain
        (adding the SPF + DKIM DNS records Resend gives you), you can
        only send from their shared test address (onboarding@resend.dev)
        and only TO the email you signed up with. Verify a domain and
        you can send from no-reply@yourdomain.com to anyone.

   Any provider works the same way — SendGrid, Amazon SES, Postmark —
   only this file would change.
   ════════════════════════════════════════════════════════════════════ */
import db from "../db.js";
import { APP_URL } from "../config.js";

const RESEND_API_KEY = process.env.RESEND_API_KEY || "";
const EMAIL_FROM = process.env.EMAIL_FROM || "RankBoard <onboarding@resend.dev>";

export async function sendInviteEmail({ name, email, role, tempPassword }) {
  const subject = "You've been added to RankBoard";
  const body = [
    `Hi ${name.split(" ")[0]},`,
    ``,
    `You've been added to the RankBoard workspace as ${role}.`,
    ``,
    `Sign in here: ${APP_URL}`,
    `Email: ${email}`,
    `Temporary password: ${tempPassword}`,
    ``,
    `You'll be asked to set your own password the first time you sign in.`,
    ``,
    `If you weren't expecting this, you can ignore this email.`,
  ].join("\n");

  /* ---- Real transport (active only when a key is configured) ---- */
  let delivery = "outbox";
  if (RESEND_API_KEY) {
    try {
      const res = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ from: EMAIL_FROM, to: [email], subject, text: body }),
      });
      if (res.ok) {
        delivery = "sent";
      } else {
        // Don't break onboarding if the provider rejects the send —
        // the account exists and the admin can still read the temp
        // password from the outbox, or hit "resend invite" later.
        delivery = "failed";
        console.error("Email provider rejected the send:", await res.text());
      }
    } catch (err) {
      delivery = "failed";
      console.error("Could not reach the email provider:", err.message);
    }
  }

  /* ---- Outbox: always logged, so there's an audit trail ---- */
  const info = db
    .prepare("INSERT INTO emails (to_email, subject, body) VALUES (?, ?, ?)")
    .run(email, subject, body);

  return { ...db.prepare("SELECT * FROM emails WHERE id = ?").get(info.lastInsertRowid), delivery };
}
