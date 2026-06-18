<?php

namespace App\Http\Controllers;

use App\Models\User;
use App\Services\EmailService;
use App\Support\Permissions;
use Illuminate\Database\QueryException;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;

/**
 * USER ROUTES — the admin panel's API. The permission:manageUsers
 * middleware (declared on the route group) runs before every method
 * here: unauthorized callers never reach these bodies at all.
 */
class UserController extends Controller
{
    // Temp passwords skip lookalike characters (0/O, 1/l/I) — people
    // type these from an email. random_int is cryptographically
    // random, unlike rand() which is guessable.
    private const CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';

    private function generateTempPassword(): string
    {
        $out = '';
        $max = strlen(self::CHARS) - 1;
        for ($i = 0; $i < 10; $i++) {
            $out .= self::CHARS[random_int(0, $max)];
        }

        return $out;
    }

    public function index()
    {
        $users = User::orderBy('created_at')->orderBy('id')->get();

        return response()->json(['users' => $users->map->toAdminArray()->all()]);
    }

    public function store(Request $request)
    {
        $name = trim((string) $request->input('name', ''));
        $email = strtolower(trim((string) $request->input('email', '')));
        $role = (string) $request->input('role', '');

        if ($name === '') {
            abort(400, 'Name is required.');
        }
        $afterAt = str_contains($email, '@') ? substr(strrchr($email, '@'), 1) : '';
        if (! str_contains($email, '@') || ! str_contains($afterAt, '.')) {
            abort(400, 'A valid email is required.');
        }
        if (! in_array($role, Permissions::ROLES, true)) {
            abort(400, 'Unknown role.');
        }

        if (User::where('email', $email)->exists()) {
            abort(409, 'Someone with this email already exists.');
        }

        $tempPassword = $this->generateTempPassword();

        try {
            $user = User::create([
                'name' => $name,
                'email' => $email,
                'role' => $role,
                'password' => Hash::make($tempPassword),
                'must_change_password' => true,
                'status' => 'invited',
            ]);
        } catch (QueryException $e) {
            // The UNIQUE constraint on email — the DB is the final
            // guard against duplicates, even under race conditions.
            abort(409, 'Someone with this email already exists.');
        }

        $emailRecord = EmailService::sendInvite($name, $email, $role, $tempPassword);

        // The ONLY time the temp password leaves the server in plain
        // text — after hashing it cannot be read back.
        return response()->json(['user' => $user->toAdminArray(), 'email' => $emailRecord], 201);
    }

    public function resendInvite(int $userId)
    {
        $user = User::find($userId);
        if (! $user) {
            abort(404, 'User not found.');
        }
        if ($user->status !== 'invited') {
            abort(400, 'This person has already activated their account.');
        }

        // Can't re-show the old temp password — only its hash exists.
        // So "resend" = generate a NEW one, overwrite the hash, email again.
        $tempPassword = $this->generateTempPassword();
        $user->password = Hash::make($tempPassword);
        $user->save();

        $emailRecord = EmailService::sendInvite($user->name, $user->email, $user->role, $tempPassword);

        return response()->json(['email' => $emailRecord]);
    }

    public function update(Request $request, int $userId)
    {
        $role = (string) $request->input('role', '');
        if (! in_array($role, Permissions::ROLES, true)) {
            abort(400, 'Unknown role.');
        }
        if ($userId === $request->user()->id) {
            abort(400, "You can't change your own role."); // no lockouts
        }

        $user = User::find($userId);
        if (! $user) {
            abort(404, 'User not found.');
        }

        $user->role = $role;
        $user->save();

        return response()->json(['ok' => true]);
    }

    public function destroy(Request $request, int $userId)
    {
        if ($userId === $request->user()->id) {
            abort(400, "You can't remove yourself."); // no lockouts
        }

        $user = User::find($userId);
        if (! $user) {
            abort(404, 'User not found.');
        }

        $user->delete();

        return response()->json(['ok' => true]);
    }
}
