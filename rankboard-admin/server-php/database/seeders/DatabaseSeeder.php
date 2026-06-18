<?php

namespace Database\Seeders;

use App\Models\Keyword;
use App\Models\Project;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

/**
 * Same seeds as the Node/Python servers, so all three backends start
 * from an identical world: one Super Admin + demo projects/keywords.
 */
class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        if (User::count() === 0) {
            User::create([
                'name' => 'Soham Dhokiya',
                'email' => 'soham@infyappdevelopment.com',
                'role' => 'Super Admin',
                'password' => Hash::make('admin123'),
                'must_change_password' => false,
                'status' => 'active',
            ]);
            $this->command?->info('Seeded first Super Admin -> soham@infyappdevelopment.com / admin123');
        }

        if (Project::count() === 0) {
            $sattva = Project::create(['name' => 'Sattva Connect', 'domain' => 'sattvaconnect.com', 'active' => true]);
            foreach ([
                ['online yoga classes', 4, 9, '2026-06-10'],
                ['yoga teacher training online', 12, 8, '2026-06-10'],
                ['meditation app for beginners', 21, 21, '2026-06-10'],
                ['pranayama breathing course', 3, null, '2026-06-11'],
            ] as [$term, $current, $previous, $checked]) {
                Keyword::create([
                    'project_id' => $sattva->id,
                    'term' => $term,
                    'current_rank' => $current,
                    'previous_rank' => $previous,
                    'last_checked' => $checked,
                ]);
            }

            $bloom = Project::create(['name' => 'Urban Bloom Florists', 'domain' => 'urbanbloomflorists.in', 'active' => true]);
            Keyword::create([
                'project_id' => $bloom->id,
                'term' => 'same day flower delivery mumbai',
                'current_rank' => 7,
                'previous_rank' => 11,
                'last_checked' => '2026-06-09',
            ]);

            Project::create(['name' => 'Peak Performance Gym', 'domain' => 'peakperformancegym.in', 'active' => false]);
            $this->command?->info('Seeded demo projects + keywords');
        }
    }
}
