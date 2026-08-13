"""Masking live credentials out of stored email bodies.

Applied in two places, deliberately:

* **At write time** (email_service, before the INSERT) so the plaintext never
  reaches the database. Previously a temporary password or a sign-in code sat in
  `emails.body` indefinitely, which meant a database dump, a read replica, or any
  future endpoint that happened to select `body` exposed live credentials — long
  after the code they contained had expired and stopped being useful to anyone
  legitimate.

* **At read time** (email_log) because rows written before that change still hold
  the plaintext. Removing the read-side pass would expose exactly the history the
  write-side pass was added to stop accumulating.

Kept in one module so the two passes can't drift apart. The regexes are the
fragile part — they are pattern-matching prose, and a reworded template will
outrun them — which is the other reason to redact before storing rather than
relying on them at every read.
"""

import re

#: Categories whose body is a live credential rather than correspondence.
SECRET_CATEGORIES = frozenset({"login_code", "password_code", "invite"})

#: Any 4-10 digit run. Deliberately broad: a missed code is worse than an
#: over-masked figure in a message nobody reads for its numbers.
_CODE_RE = re.compile(r"\b\d{4,10}\b")

_TEMP_PW_RE = re.compile(r"(?i)(temporary password:\s*)(\S+)")

MASK = "••••••"
PW_MASK = "••••••••"


def redact(body: str | None, category: str | None) -> str | None:
    """Mask codes and temporary passwords in a message of a secret category.

    Anything outside SECRET_CATEGORIES is returned untouched — a report email's
    figures are the point of it.
    """
    if not body or category not in SECRET_CATEGORIES:
        return body
    body = _TEMP_PW_RE.sub(r"\1" + PW_MASK, body)
    return _CODE_RE.sub(MASK, body)
