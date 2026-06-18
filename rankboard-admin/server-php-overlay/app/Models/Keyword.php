<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Keyword extends Model
{
    protected $fillable = ['project_id', 'term', 'current_rank', 'previous_rank', 'last_checked'];

    protected $casts = ['last_checked' => 'date:Y-m-d'];

    public function project(): BelongsTo
    {
        return $this->belongsTo(Project::class);
    }

    public function toApi(): array
    {
        return [
            'id' => $this->id,
            'term' => $this->term,
            'currentRank' => $this->current_rank,
            'previousRank' => $this->previous_rank, // null = first lookup ("New")
            'lastChecked' => $this->last_checked?->format('Y-m-d'),
        ];
    }
}
