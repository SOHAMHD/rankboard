<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/*
 * RankBoard's schema on top of Laravel's default users table. Same
 * shape as the Node/Python servers: users get role + onboarding
 * columns; emails is the dev outbox; keywords cascade-delete with
 * their project.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->string('role')->default('Team');
            $table->boolean('must_change_password')->default(false);
            $table->string('status')->default('invited'); // invited -> active
        });

        Schema::create('emails', function (Blueprint $table) {
            $table->id();
            $table->string('to_email');
            $table->string('subject');
            $table->text('body');
            $table->timestamp('sent_at')->useCurrent();
        });

        Schema::create('projects', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('domain')->nullable(); // needed for real rank checks
            $table->boolean('active')->default(true);
            $table->timestamps();
        });

        Schema::create('keywords', function (Blueprint $table) {
            $table->id();
            // cascadeOnDelete = the FK cascade: delete a project and
            // its keywords vanish with it. No orphans.
            $table->foreignId('project_id')->constrained()->cascadeOnDelete();
            $table->string('term');
            $table->unsignedInteger('current_rank');
            $table->unsignedInteger('previous_rank')->nullable(); // null = first lookup ("New")
            $table->date('last_checked')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('keywords');
        Schema::dropIfExists('projects');
        Schema::dropIfExists('emails');
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['role', 'must_change_password', 'status']);
        });
    }
};
