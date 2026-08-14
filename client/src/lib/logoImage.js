/**
 * Turn a chosen image file into a logo-sized data URI.
 *
 * Extracted from ReportDocumentEditor, which had the only copy. The project form
 * needs the identical treatment — same size ceiling, same whitespace trim, same
 * encoding — and two implementations would drift until a logo that looked fine in
 * one place was rejected or blurry in the other.
 *
 * Everything here is deliberately client-side. The server stores the data URI
 * as-is (see services/images.py), so shrinking has to happen before upload or the
 * row and every report blob carrying a copy would hold a full-resolution photo.
 */

// The logo prints at most 230x56 CSS px on the cover and 200x40 in the running
// header. Storing it at native resolution is what pushed report content_json past
// the server's 500,000-char cap and produced "Report document is too large." on
// save. ~3x the largest print size is plenty sharp.
export const LOGO_MAX_W = 720;
export const LOGO_MAX_H = 200;
export const LOGO_MAX_CHARS = 120000;

// Rejected before decoding: a 25 MB image is a mistake, not a logo, and finding
// out after the decode means the user has already waited for it.
export const LOGO_MAX_BYTES = 8 * 1024 * 1024;

function encodeScaled(src, sx, sy, sw, sh, scale) {
  const o = document.createElement("canvas");
  o.width = Math.max(1, Math.round(sw * scale));
  o.height = Math.max(1, Math.round(sh * scale));
  const ctx = o.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(src, sx, sy, sw, sh, 0, 0, o.width, o.height);
  return o.toDataURL("image/png");
}

// Fit inside LOGO_MAX_W/H, then keep shrinking while the encoded string is over
// budget — a photo-like logo can still be heavy at 720px wide.
function encodeWithinBudget(src, sx, sy, sw, sh) {
  let scale = Math.min(1, LOGO_MAX_W / sw, LOGO_MAX_H / sh);
  let out = encodeScaled(src, sx, sy, sw, sh, scale);
  while (out.length > LOGO_MAX_CHARS && scale > 0.08) {
    scale *= 0.75;
    out = encodeScaled(src, sx, sy, sw, sh, scale);
  }
  return out;
}

/**
 * Crop surrounding whitespace and downscale. Resolves to a PNG data URI.
 *
 * Resolves to the input untouched if the browser can't decode it — callers must
 * check the returned length, because an undecodable image comes back at full size.
 */
export function trimLogo(dataUrl) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        // Downscale BEFORE scanning. This used to draw at naturalWidth x
        // naturalHeight and walk every pixel in a nested JS loop — a 12MP phone
        // photo is ~12 million iterations with four typed-array reads each, which
        // froze the tab for seconds with no spinner. The trim only needs the
        // content bounds, and those scale, so working at logo resolution gives
        // the same answer for a fraction of the work.
        const SCAN_MAX = 900;
        const scale = Math.min(1, SCAN_MAX / Math.max(img.naturalWidth, img.naturalHeight));
        const c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(img.naturalWidth * scale));
        c.height = Math.max(1, Math.round(img.naturalHeight * scale));
        const ctx = c.getContext("2d");
        ctx.drawImage(img, 0, 0, c.width, c.height);
        const { data } = ctx.getImageData(0, 0, c.width, c.height);
        let top = c.height, left = c.width, right = 0, bottom = 0, found = false;
        for (let y = 0; y < c.height; y++) {
          for (let x = 0; x < c.width; x++) {
            const i = (y * c.width + x) * 4;
            const a = data[i + 3], r = data[i], g = data[i + 1], b = data[i + 2];
            const content = a > 12 && !(r > 245 && g > 245 && b > 245);
            if (content) {
              found = true;
              if (x < left) left = x;
              if (x > right) right = x;
              if (y < top) top = y;
              if (y > bottom) bottom = y;
            }
          }
        }
        if (!found) return resolve(encodeWithinBudget(c, 0, 0, c.width, c.height));
        const pad = 2;
        left = Math.max(0, left - pad); top = Math.max(0, top - pad);
        right = Math.min(c.width - 1, right + pad); bottom = Math.min(c.height - 1, bottom + pad);
        const w = right - left + 1, h = bottom - top + 1;
        resolve(encodeWithinBudget(c, left, top, w, h));
      } catch (e) {
        resolve(dataUrl);
      }
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}

/**
 * File -> processed data URI, with the guards and messages.
 *
 * Resolves `{ ok: true, dataUrl }` or `{ ok: false, title, message }` so both
 * callers report the same thing in whatever way suits them, rather than each
 * inventing its own wording for the same failure.
 */
export function processLogoFile(file) {
  return new Promise((resolve) => {
    if (!file || !file.type || !file.type.startsWith("image/")) {
      resolve({ ok: false, title: "Not an image", message: "Choose a PNG, JPG or WebP file." });
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      resolve({
        ok: false,
        title: "Image too large",
        message: "That file is over 8 MB. Save it as a PNG or JPG a few hundred KB in size and try again.",
      });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      trimLogo(reader.result)
        .then((trimmed) => {
          // trimLogo returns the input untouched when the browser can't decode
          // it. Storing that would fail the save with an unhelpful "too large",
          // so it's caught here where the cause is still known.
          if (typeof trimmed !== "string" || trimmed.length > LOGO_MAX_CHARS * 2) {
            resolve({
              ok: false,
              title: "Logo too large",
              message: "That image couldn't be resized. Save it as a PNG or JPG under about 2 MB and try again.",
            });
            return;
          }
          resolve({ ok: true, dataUrl: trimmed });
        })
        .catch(() =>
          resolve({ ok: false, title: "Upload failed", message: "That image couldn't be read. Try a different file." })
        );
    };
    reader.onerror = () =>
      resolve({ ok: false, title: "Upload failed", message: "That image couldn't be read. Try a different file." });
    reader.readAsDataURL(file);
  });
}
