<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;

class AuthController extends Controller
{
    public function login(Request $request)
    {
        $email = strtolower(trim((string) $request->input('email', '')));
        $password = (string) $request->input('password', '');

        $user = User::where('email', $email)->first();

        // Same generic message whether the email or the password is
        // wrong — no account enumeration.
        if (! $user || $password === '' || ! Hash::check($password, $user->password)) {
            abort(401, 'No account matches that email and password.');
        }

        // Sanctum personal access token instead of a hand-rolled JWT.
        // The CONTRACT is unchanged: the client stores an opaque string
        // and sends it back as "Authorization: Bearer <token>".
        $token = $user->createToken('rankboard', ['*'], now()->addHours(8))->plainTextToken;

        return response()->json(['token' => $token, 'user' => $user->toPublicArray()]);
    }

    public function me(Request $request)
    {
        return response()->json(['user' => $request->user()->toPublicArray()]);
    }

    public function setPassword(Request $request)
    {
        $newPassword = (string) $request->input('newPassword', '');
        if (strlen($newPassword) < 8) {
            abort(400, 'Password needs at least 8 characters.');
        }

        $user = $request->user();
        $user->password = Hash::make($newPassword);
        $user->must_change_password = false;
        $user->status = 'active'; // first real sign-in completes onboarding
        $user->save();

        return response()->json(['ok' => true]);
    }
}
