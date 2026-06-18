<?php

namespace App\Http\Middleware;

use App\Support\Permissions;
use Closure;
use Illuminate\Http\Request;

/**
 * Laravel's equivalent of the Express/FastAPI permission guard.
 * Registered under the alias "permission" in bootstrap/app.php, used
 * on routes as:  ->middleware('permission:addProject')
 *
 * Same two answers as always:
 *   401 = we don't know who you are (handled by auth:sanctum before us)
 *   403 = we know exactly who you are, and the answer is no
 */
class RequirePermission
{
    public function handle(Request $request, Closure $next, string $action)
    {
        $user = $request->user();

        if (! $user || ! Permissions::can($user->role, $action)) {
            return response()->json(['error' => "You don't have permission to do that."], 403);
        }

        return $next($request);
    }
}
