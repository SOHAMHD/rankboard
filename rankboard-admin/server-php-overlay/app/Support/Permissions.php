<?php

namespace App\Support;

/**
 * PERMISSIONS — the single source of truth, same matrix as the Node
 * and Python servers. The React client never sees this file; it
 * receives a copy of its role's row via /api/auth/me. Enforcement
 * happens in the RequirePermission middleware on every request.
 *
 * ← provisional rows: Team and Client rules are placeholders until
 * decided. Flip booleans here and both API enforcement and the UI
 * (which renders what the server sends) follow.
 */
class Permissions
{
    public const MATRIX = [
        //                manageUsers    addProject     toggleProject   deleteProject   addKeyword     deleteKeyword
        'Super Admin' => ['manageUsers' => true,  'addProject' => true,  'toggleProject' => true,  'deleteProject' => true,  'addKeyword' => true,  'deleteKeyword' => true],
        'Admin'       => ['manageUsers' => false, 'addProject' => true,  'toggleProject' => true,  'deleteProject' => true,  'addKeyword' => true,  'deleteKeyword' => true],  // a.k.a. Manager
        'Team'        => ['manageUsers' => false, 'addProject' => false, 'toggleProject' => false, 'deleteProject' => false, 'addKeyword' => true,  'deleteKeyword' => true],  // ← provisional
        'Client'      => ['manageUsers' => false, 'addProject' => false, 'toggleProject' => false, 'deleteProject' => false, 'addKeyword' => false, 'deleteKeyword' => false], // ← provisional: read-only
    ];

    public const ROLES = ['Super Admin', 'Admin', 'Team', 'Client'];

    /** Default-deny: unknown role or unknown action → false. */
    public static function can(?string $role, string $action): bool
    {
        return self::MATRIX[$role][$action] ?? false;
    }

    /** The row a signed-in user receives so the UI knows what to draw. */
    public static function forRole(?string $role): array
    {
        return self::MATRIX[$role] ?? [];
    }
}
