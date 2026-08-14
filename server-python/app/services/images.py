"""What counts as an acceptable inline image.

One definition, shared by the API that stores logos and the renderer that embeds
them. They must agree: if the router accepted a format the renderer discards, the
upload would appear to succeed and the logo would silently be missing from the
PDF, with nothing anywhere to explain why.

SVG is deliberately absent from the allowed types. An SVG is a document — it can
carry <script>, external references and CSS — and these strings are interpolated
into HTML that headless Chromium then executes while rendering a report. PNG, JPEG,
GIF and WebP decode to pixels and cannot.
"""

import re

#: Allowed inline image formats. Anchored, and the payload character class admits
#: only base64 plus whitespace, so nothing can smuggle a quote or angle bracket
#: through into the surrounding markup.
DATA_IMAGE_RE = re.compile(
    r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I
)

#: Server-side ceiling on the encoded string.
#:
#: The client downscales to a 120,000-char budget (client/src/lib/logoImage.js),
#: which is what keeps report content_json under its own 500,000-char save cap.
#: This is deliberately looser than that — its job is to refuse a full-resolution
#: photo posted straight at the API, not to second-guess the client's encoder.
#: ~200 KB of base64 is ~150 KB of image: far more than any logo needs, far less
#: than a phone camera produces.
MAX_LOGO_CHARS = 200_000


def normalize_logo(value: str | None) -> str | None:
    """Validate and tidy a logo data URI. Returns None for "no logo".

    Raises ValueError with a message worth showing the user. Blank clears the
    field, so a caller can remove a logo by sending an empty string.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    if len(text) > MAX_LOGO_CHARS:
        raise ValueError(
            "That image is too large to store. Save it as a PNG a few hundred "
            "kilobytes in size and upload it again."
        )

    if not DATA_IMAGE_RE.match(text):
        if text.lower().startswith("data:image/svg"):
            raise ValueError(
                "SVG logos aren't supported. Export it as a PNG and upload that."
            )
        if text.lower().startswith(("http://", "https://")):
            # Worth its own message: linking is the obvious thing to try, and the
            # reason it isn't allowed isn't guessable.
            raise ValueError(
                "A link can't be used — the logo has to be uploaded, because the "
                "PDF renderer embeds it rather than fetching it."
            )
        raise ValueError(
            "That doesn't look like an uploaded image. Supported formats are PNG, "
            "JPEG, GIF and WebP."
        )

    # Whitespace is legal in base64 and browsers accept it, but it inflates every
    # row and every report blob that carries a copy.
    return re.sub(r"\s+", "", text)
