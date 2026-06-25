<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * RANK PROVIDER — the swappable-transport pattern, third backend.
 *
 *   DATAFORSEO_LOGIN/PASSWORD set -> real lookups via DataForSEO's
 *                                    SERP API (Live mode)
 *   not set                       -> simulated random walk around the
 *                                    current rank, clearly labeled
 *
 * Callers only know "a lookup happened, here are the numbers + the
 * source". Swapping providers later touches only this file.
 */
class RankProvider
{
    /**
     * @param  array<int, array{term: string, currentRank: int|null}>  $keywords
     * @return array{0: array<string, int|null>, 1: string}  [ranks, source]
     */
    public static function checkRanks(?string $domain, array $keywords): array
    {
        $cfg = config('rankboard.dataforseo');
        if ($cfg['login'] && $cfg['password']) {
            return [self::dataForSeo($domain, array_column($keywords, 'term')), 'dataforseo'];
        }

        return [self::simulated($keywords), 'simulated'];
    }

    private static function simulated(array $keywords): array
    {
        $out = [];
        foreach ($keywords as $k) {
            $cur = $k['currentRank'];
            $base = is_int($cur) ? $cur : random_int(8, 45);
            $out[$k['term']] = max(1, min(100, $base + random_int(-4, 3)));
        }

        return $out;
    }

    private static function domainMatches(?string $itemDomain, string $target): bool
    {
        $d = strtolower($itemDomain ?? '');

        return $d === $target || $d === 'www.'.$target || str_ends_with($d, '.'.$target);
    }

    private static function dataForSeo(string $domain, array $terms): array
    {
        $rank = config('rankboard.rank');
        $cfg = config('rankboard.dataforseo');

        // One POST carries a task per keyword — the whole project is
        // checked in a single round trip.
        $tasks = array_map(fn (string $term) => [
            'keyword' => $term,
            'location_code' => $rank['location_code'],
            'language_code' => $rank['language'],
            'device' => 'desktop',
            'depth' => $rank['depth'],
        ], $terms);

        $response = Http::withBasicAuth($cfg['login'], $cfg['password'])
            ->timeout(60)
            ->post($cfg['base'].'/v3/serp/google/organic/live/advanced', $tasks);

        if (! $response->successful()) {
            throw new RuntimeException(
                'DataForSEO HTTP '.$response->status().': '.substr($response->body(), 0, 300)
            );
        }

        $payload = $response->json();
        $out = array_fill_keys($terms, null);

        // DataForSEO echoes data.keyword back lowercased & trimmed, so map
        // from that normalized form to our original term to look up $out —
        // matching on the raw string would drop any capitalized keyword.
        $byNormalized = [];
        foreach ($terms as $term) {
            $byNormalized[strtolower(trim($term))] = $term;
        }

        foreach (($payload['tasks'] ?? []) as $task) {
            $returned = $task['data']['keyword'] ?? null;
            $term = is_string($returned) ? ($byNormalized[strtolower(trim($returned))] ?? null) : null;
            if (($task['status_code'] ?? 0) !== 20000 || $term === null) {
                continue; // 20000 = this task succeeded
            }
            foreach (($task['result'] ?? []) as $result) {
                foreach (($result['items'] ?? []) as $item) {
                    // rank_group = position among ORGANIC results only;
                    // rank_absolute would also count ads/SERP features.
                    if (($item['type'] ?? '') === 'organic' && self::domainMatches($item['domain'] ?? null, $domain)) {
                        $out[$term] = $item['rank_group'] ?? null;
                        break;
                    }
                }
                if ($out[$term] !== null) {
                    break;
                }
            }
        }

        return $out;
    }
}
