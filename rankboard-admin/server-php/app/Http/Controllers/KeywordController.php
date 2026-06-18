<?php

namespace App\Http\Controllers;

use App\Models\Keyword;
use App\Models\Project;
use App\Services\ExcelService;
use App\Services\RankProvider;
use Illuminate\Http\Request;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use Throwable;

class KeywordController extends Controller
{
    public function store(Request $request, int $projectId)
    {
        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        $term = strtolower(trim((string) $request->input('term', '')));
        if ($term === '') {
            abort(400, 'Keyword is required.');
        }

        $current = $this->toRank($request->input('currentRank'));
        if ($current === null || $current < 1) {
            abort(400, 'Current rank must be a whole number of 1 or more.');
        }

        $previous = null;
        if ($request->input('previousRank') !== null) {
            $previous = $this->toRank($request->input('previousRank'));
            if ($previous === null || $previous < 1) {
                abort(400, 'Previous rank must be a whole number of 1 or more.');
            }
        }

        $keyword = Keyword::create([
            'project_id' => $projectId,
            'term' => $term,
            'current_rank' => $current,
            'previous_rank' => $previous,
            'last_checked' => now()->toDateString(),
        ]);

        return response()->json(['keyword' => $keyword->toApi()], 201);
    }

    /**
     * Record a NEW LOOKUP: current -> previous, new number -> current,
     * stamp the date. The automated rank-checker calls this same write
     * path — only WHO supplies the number changes.
     */
    public function recordLookup(Request $request, int $projectId, int $keywordId)
    {
        $newRank = $this->toRank($request->input('newRank'));
        if ($newRank === null || $newRank < 1) {
            abort(400, 'New rank must be a whole number of 1 or more.');
        }

        $keyword = Keyword::where('id', $keywordId)->where('project_id', $projectId)->first();
        if (! $keyword) {
            abort(404, 'Keyword not found.');
        }

        $keyword->previous_rank = $keyword->current_rank;
        $keyword->current_rank = $newRank;
        $keyword->last_checked = now()->toDateString();
        $keyword->save();

        return response()->json(['keyword' => $keyword->toApi()]);
    }

    public function destroy(int $projectId, int $keywordId)
    {
        // Both ids in the WHERE clause: a keyword can only be deleted
        // through its own project — matters once per-project access exists.
        $deleted = Keyword::where('id', $keywordId)->where('project_id', $projectId)->delete();
        if ($deleted === 0) {
            abort(404, 'Keyword not found.');
        }

        return response()->json(['ok' => true]);
    }

    /**
     * Check every keyword in the project against the rank provider and
     * record the lookups (current -> previous rotation). A future cron
     * job calls this endpoint on a schedule and the dashboard fills
     * itself in.
     */
    public function checkRanks(int $projectId)
    {
        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        $kws = Keyword::where('project_id', $projectId)
            ->orderBy('created_at')->orderBy('id')->get();
        if ($kws->isEmpty()) {
            abort(400, 'No keywords to check yet.');
        }

        $cfg = config('rankboard.dataforseo');
        $realMode = (bool) ($cfg['login'] && $cfg['password']);
        if ($realMode && ! $project->domain) {
            abort(400, "This project has no domain set, so the checker doesn't know which site to look for. "
                .'Add one when creating the project, or via PATCH /api/projects/:id {"domain": "yoursite.com"}.');
        }

        try {
            [$ranks, $source] = RankProvider::checkRanks(
                $project->domain,
                $kws->map(fn (Keyword $k) => ['term' => $k->term, 'currentRank' => $k->current_rank])->all(),
            );
        } catch (Throwable $exc) {
            abort(502, 'Rank check failed: '.$exc->getMessage());
        }

        $updated = 0;
        $notFound = [];
        foreach ($kws as $k) {
            $rank = $ranks[$k->term] ?? null;
            if ($rank === null) {
                // Not in the checked depth: report it, leave the ledger
                // row untouched rather than inventing a number.
                $notFound[] = $k->term;

                continue;
            }
            $k->previous_rank = $k->current_rank;
            $k->current_rank = $rank;
            $k->last_checked = now()->toDateString();
            $k->save();
            $updated++;
        }

        return response()->json([
            'source' => $source,
            'checked' => $kws->count(),
            'updated' => $updated,
            'notFound' => $notFound,
        ]);
    }

    // ── Bulk import via Excel ───────────────────────────────────────

    /**
     * Serve the .xlsx template. A GET that returns a file, not JSON:
     * the Content-Disposition header (set by streamDownload) tells the
     * browser to download it with a filename instead of rendering it.
     */
    public function sampleTemplate()
    {
        $spreadsheet = ExcelService::buildSampleSpreadsheet();

        return response()->streamDownload(function () use ($spreadsheet) {
            (new Xlsx($spreadsheet))->save('php://output');
        }, 'rankboard-keywords-template.xlsx', [
            'Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        ]);
    }

    /**
     * Accept an uploaded .xlsx, validate every row, insert the good
     * ones, and report a per-row reason for every skipped one.
     *
     * Partial success is intentional: importing 47 of 50 keywords and
     * naming the 3 problems beats rejecting the whole file over one typo.
     */
    public function bulkImport(Request $request, int $projectId)
    {
        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        $file = $request->file('file');
        $name = $file?->getClientOriginalName() ?? '';
        if (! $file || ! preg_match('/\.(xlsx|xlsm)$/i', $name)) {
            abort(400, 'Please upload an .xlsx file (the sample template format).');
        }

        if ($file->getSize() > 5 * 1024 * 1024) { // 5 MB ceiling
            abort(400, 'That file is too large (limit 5 MB).');
        }

        try {
            [$valid, $errors] = ExcelService::parseKeywordWorkbook($file->getRealPath());
        } catch (\InvalidArgumentException $exc) {
            abort(400, $exc->getMessage());
        }

        // Skip terms already tracked on this project (idempotent re-imports).
        $existing = Keyword::where('project_id', $projectId)->pluck('term')->flip();
        $toInsert = array_values(array_filter($valid, fn ($v) => ! isset($existing[$v['term']])));
        $skippedExisting = count($valid) - count($toInsert);

        foreach ($toInsert as $v) {
            Keyword::create([
                'project_id' => $projectId,
                'term' => $v['term'],
                'current_rank' => $v['currentRank'],
                'previous_rank' => $v['previousRank'],
                'last_checked' => now()->toDateString(),
            ]);
        }

        return response()->json([
            'imported' => count($toInsert),
            'skippedExisting' => $skippedExisting,
            'errors' => $errors, // [{row, reason}, ...]
            'totalRows' => count($valid) + count($errors),
        ]);
    }

    /** JSON numbers, whole floats, and digit-strings all become ints. */
    private function toRank(mixed $v): ?int
    {
        if (is_int($v)) {
            return $v;
        }
        if (is_float($v) && floor($v) == $v) {
            return (int) $v;
        }
        if (is_string($v) && preg_match('/^\s*\d+\s*$/', $v)) {
            return (int) trim($v);
        }

        return null;
    }
}
