<?php

namespace App\Services;

use App\Models\EmailLog;
use Illuminate\Support\Facades\Http;
use Throwable;

/**
 * EMAIL SERVICE — same swappable transport as the Node and Python
 * versions.
 *
 *   RESEND_API_KEY set      -> actually sent via Resend's HTTP API
 *   RESEND_API_KEY not set  -> dev outbox only (the `emails` table)
 *
 * Either way the email is logged for an audit trail, and callers only
 * ever know "an invite was sent".
 */
class EmailService
{
    public static function sendInvite(string $name, string $email, string $role, string $tempPassword): array
    {
        $appUrl = config('rankboard.app_url');
        $firstName = explode(' ', $name)[0];

        $subject = "You've been added to RankBoard";
        $body = implode("\n", [
            "Hi {$firstName},",
            '',
            "You've been added to the RankBoard workspace as {$role}.",
            '',
            "Sign in here: {$appUrl}",
            "Email: {$email}",
            "Temporary password: {$tempPassword}",
            '',
            "You'll be asked to set your own password the first time you sign in.",
            '',
            "If you weren't expecting this, you can ignore this email.",
        ]);

        // ---- Real transport (active only when a key is configured) ----
        $delivery = 'outbox';
        $key = config('rankboard.resend.key');
        if ($key) {
            try {
                $response = Http::withToken($key)->timeout(10)->post('https://api.resend.com/emails', [
                    'from' => config('rankboard.resend.from'),
                    'to' => [$email],
                    'subject' => $subject,
                    'text' => $body,
                ]);
                $delivery = $response->successful() ? 'sent' : 'failed';
            } catch (Throwable $exc) { // don't break onboarding if the provider is down
                $delivery = 'failed';
                logger()->warning('Could not reach the email provider: '.$exc->getMessage());
            }
        }

        $log = EmailLog::create(['to_email' => $email, 'subject' => $subject, 'body' => $body]);
        $log->refresh(); // pick up the DB-default sent_at

        // Same keys the other backends return: id, to_email, subject,
        // body, sent_at — plus the delivery outcome.
        return array_merge($log->toArray(), ['delivery' => $delivery]);
    }
}
