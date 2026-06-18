<?php

use App\Http\Controllers\AuthController;
use App\Http\Controllers\KeywordController;
use App\Http\Controllers\ProjectController;
use App\Http\Controllers\UserController;
use Illuminate\Support\Facades\Route;

/*
 * The same API contract as the Node and Python servers — the React
 * client cannot tell which backend is answering. That's the point.
 * Laravel automatically prefixes everything in this file with /api.
 */

// ── Auth ────────────────────────────────────────────────────────────
Route::post('/auth/login', [AuthController::class, 'login']);

Route::middleware('auth:sanctum')->group(function () {
    Route::get('/auth/me', [AuthController::class, 'me']);
    Route::post('/auth/set-password', [AuthController::class, 'setPassword']);
});

// ── People (admin panel, Super Admin only) ──────────────────────────
Route::middleware(['auth:sanctum', 'permission:manageUsers'])->group(function () {
    Route::get('/users', [UserController::class, 'index']);
    Route::post('/users', [UserController::class, 'store']);
    Route::post('/users/{userId}/resend-invite', [UserController::class, 'resendInvite']);
    Route::patch('/users/{userId}', [UserController::class, 'update']);
    Route::delete('/users/{userId}', [UserController::class, 'destroy']);
});

// ── Projects & the Rank Ledger ──────────────────────────────────────
Route::middleware('auth:sanctum')->group(function () {
    Route::get('/projects', [ProjectController::class, 'index']);

    // Declared BEFORE the {projectId} wildcard so "keywords" isn't
    // swallowed as a project id.
    Route::get('/projects/keywords/sample-template', [KeywordController::class, 'sampleTemplate']);

    Route::get('/projects/{projectId}', [ProjectController::class, 'show']);

    Route::post('/projects', [ProjectController::class, 'store'])
        ->middleware('permission:addProject');
    Route::patch('/projects/{projectId}', [ProjectController::class, 'update'])
        ->middleware('permission:toggleProject');
    Route::delete('/projects/{projectId}', [ProjectController::class, 'destroy'])
        ->middleware('permission:deleteProject');

    Route::post('/projects/{projectId}/keywords', [KeywordController::class, 'store'])
        ->middleware('permission:addKeyword');
    Route::post('/projects/{projectId}/check-ranks', [KeywordController::class, 'checkRanks'])
        ->middleware('permission:addKeyword');
    Route::post('/projects/{projectId}/keywords/bulk-import', [KeywordController::class, 'bulkImport'])
        ->middleware('permission:addKeyword');
    Route::patch('/projects/{projectId}/keywords/{keywordId}', [KeywordController::class, 'recordLookup'])
        ->middleware('permission:addKeyword');
    Route::delete('/projects/{projectId}/keywords/{keywordId}', [KeywordController::class, 'destroy'])
        ->middleware('permission:deleteKeyword');
});
