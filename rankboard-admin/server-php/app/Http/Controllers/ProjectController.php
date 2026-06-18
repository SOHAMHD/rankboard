<?php

namespace App\Http\Controllers;

use App\Models\Project;
use Illuminate\Http\Request;

class ProjectController extends Controller
{
    /**
     * Eloquent's withCount('keywords') compiles to the same LEFT JOIN +
     * GROUP BY we hand-wrote in SQL on the other backends: each project
     * with its keyword count in ONE query, projects with zero keywords
     * still included.
     */
    public function index()
    {
        $projects = Project::withCount('keywords')
            ->orderByDesc('created_at')->orderByDesc('id')
            ->get();

        return response()->json([
            'projects' => $projects->map(fn (Project $p) => $p->toApi($p->keywords_count))->all(),
        ]);
    }

    public function show(int $projectId)
    {
        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        $keywords = $project->keywords()->orderBy('created_at')->orderBy('id')->get();

        return response()->json([
            'project' => array_merge($project->toApi(), [
                'keywords' => $keywords->map->toApi()->all(),
            ]),
        ]);
    }

    public function store(Request $request)
    {
        $name = trim((string) $request->input('name', ''));
        if ($name === '') {
            abort(400, 'Project name is required.');
        }

        $project = Project::create([
            'name' => $name,
            'domain' => Project::normalizeDomain($request->input('domain')),
            'active' => true,
        ]);

        return response()->json(['project' => $project->toApi()], 201);
    }

    /**
     * Started life as the active/inactive toggle; now also updates the
     * domain. (Uses the toggleProject permission as a general "manage
     * project settings" right for now — revisit when the matrix is decided.)
     */
    public function update(Request $request, int $projectId)
    {
        $hasActive = $request->has('active') && $request->input('active') !== null;
        $hasDomain = $request->has('domain') && $request->input('domain') !== null;
        if (! $hasActive && ! $hasDomain) {
            abort(400, 'Nothing to update.');
        }

        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        if ($hasActive) {
            $project->active = (bool) $request->input('active');
        }
        if ($hasDomain) {
            $project->domain = Project::normalizeDomain($request->input('domain'));
        }
        $project->save();

        return response()->json(['ok' => true]);
    }

    /**
     * The FK cascade in the migration deletes the project's keywords
     * automatically — no manual cleanup, no orphans.
     */
    public function destroy(int $projectId)
    {
        $project = Project::find($projectId);
        if (! $project) {
            abort(404, 'Project not found.');
        }

        $project->delete();

        return response()->json(['ok' => true]);
    }
}
