<?php

namespace App\Models;

use App\Support\Permissions;
use Illuminate\Database\Eloquent\Model;
use Laravel\Sanctum\HasApiTokens;

class User extends Model
{
    use HasApiTokens;

    protected $fillable = ['name', 'email', 'role', 'password', 'must_change_password', 'status'];

    /** Never serialized — what the API doesn't return can't leak. */
    protected $hidden = ['password', 'remember_token'];

    protected $casts = [
        'must_change_password' => 'boolean',
    ];

    /**
     * The exact shape the React client expects (camelCase, with the
     * role's permission row attached). One place to change it.
     */
    public function toPublicArray(): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'email' => $this->email,
            'role' => $this->role,
            'status' => $this->status,
            'mustChangePassword' => (bool) $this->must_change_password,
            'permissions' => Permissions::forRole($this->role),
        ];
    }

    /** Row shape for the admin panel's People table. */
    public function toAdminArray(): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'email' => $this->email,
            'role' => $this->role,
            'status' => $this->status,
            'createdAt' => $this->created_at?->toDateTimeString(),
        ];
    }
}
