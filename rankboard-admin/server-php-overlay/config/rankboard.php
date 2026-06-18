<?php

/*
 * RankBoard's own settings, all env-backed. Laravel convention: code
 * reads config('rankboard.xxx'), never env() directly — config can be
 * cached, env() calls outside config files silently break then.
 */
return [
    // Link placed in invite emails (the React app's address).
    'app_url' => env('APP_URL_FRONTEND', env('APP_URL', 'http://localhost:5173')),

    'resend' => [
        'key' => env('RESEND_API_KEY', ''),
        'from' => env('EMAIL_FROM', 'RankBoard <onboarding@resend.dev>'),
    ],

    'dataforseo' => [
        'login' => env('DATAFORSEO_LOGIN', ''),
        'password' => env('DATAFORSEO_PASSWORD', ''),
        // Point at https://sandbox.dataforseo.com to test on mock data for free.
        'base' => env('DATAFORSEO_BASE', 'https://api.dataforseo.com'),
    ],

    'rank' => [
        'location_code' => (int) env('RANK_LOCATION_CODE', 2356), // 2356 = India, 2036 = Australia, 2840 = USA
        'language' => env('RANK_LANGUAGE', 'en'),
        // Depth = how deep into Google we look. Billing is per page of
        // 10 results, so depth 30 = 3 pages; deeper costs more per check.
        'depth' => (int) env('RANK_CHECK_DEPTH', 30),
    ],
];
