<?php

use App\Http\Middleware\RequirePermission;
use Illuminate\Auth\AuthenticationException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;
use Symfony\Component\HttpKernel\Exception\HttpException;

/*
 * Laravel 11+ slim bootstrap. Two RankBoard-specific additions:
 *
 * 1. The "permission" middleware alias — routes declare
 *    ->middleware('permission:addProject') exactly where Express used
 *    requirePermission('addProject') and FastAPI used
 *    Depends(require_permission("addProject")).
 *
 * 2. Exception rendering so every API error speaks the same dialect
 *    as the other backends: {"error": "human-readable message"} —
 *    the React client reads data.error and nothing else.
 */
return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware) {
        $middleware->alias([
            'permission' => RequirePermission::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions) {
        // Not signed in (or token expired) -> 401, same message as the
        // other backends.
        $exceptions->render(function (AuthenticationException $e, Request $request) {
            if ($request->is('api/*')) {
                return response()->json(['error' => 'Sign in required.'], 401);
            }
        });

        // abort(400, '...'), abort(404, '...'), missing routes, wrong
        // methods — everything Laravel expresses as an HttpException.
        $exceptions->render(function (HttpException $e, Request $request) {
            if ($request->is('api/*')) {
                $status = $e->getStatusCode();
                $message = $e->getMessage();
                if ($message === '') {
                    $message = $status === 404 ? 'Not found.' : 'Something went wrong.';
                }

                return response()->json(['error' => $message], $status);
            }
        });

        // Anything unexpected: a generic 500 in production. With
        // APP_DEBUG=true Laravel's own detailed error page still shows,
        // which is what you want while developing.
        $exceptions->render(function (Throwable $e, Request $request) {
            if ($request->is('api/*') && ! config('app.debug')) {
                return response()->json(['error' => 'Something went wrong on our side.'], 500);
            }
        });
    })->create();
