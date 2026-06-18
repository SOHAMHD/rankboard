<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/**
 * The dev outbox — every invite email is logged here whether it was
 * actually delivered (Resend configured) or not. Same table name and
 * shape as the Node/Python servers: emails(to_email, subject, body).
 */
class EmailLog extends Model
{
    protected $table = 'emails';

    public $timestamps = false; // the table uses sent_at with a DB default

    protected $fillable = ['to_email', 'subject', 'body'];
}
