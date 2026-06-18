<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Project extends Model
{
    protected $fillable = ['name', 'domain', 'active'];

    protected $casts = ['active' => 'boolean'];

    public function keywords(): HasMany
    {
        return $this->hasMany(Keyword::class);
    }

    /**
     * "https://www.Sattva-Connect.com/about" -> "sattva-connect.com".
     * One canonical form so SERP matching is reliable.
     */
    public static function normalizeDomain(?string $raw): ?string
    {
        if ($raw === null || trim($raw) === '') {
            return null;
        }
        $d = strtolower(trim($raw));
        $parts = explode('://', $d);
        $d = end($parts);
        $d = explode('/', $d)[0];
        $d = explode('?', $d)[0];
        if (str_starts_with($d, 'www.')) {
            $d = substr($d, 4);
        }

        return $d !== '' ? $d : null;
    }

    public function toApi(?int $keywordCount = null): array
    {
        $out = [
            'id' => $this->id,
            'name' => $this->name,
            'domain' => $this->domain,
            'active' => (bool) $this->active,
            'createdAt' => $this->created_at?->toDateTimeString(),
        ];
        if ($keywordCount !== null) {
            $out['keywordCount'] = $keywordCount;
        }

        return $out;
    }
}
