/* Central config. In production these MUST come from environment
   variables (never commit real secrets to git). The fallbacks below
   exist only so `npm run dev` works out of the box. */
export const PORT = process.env.PORT || 4000;
export const JWT_SECRET = process.env.JWT_SECRET || "dev-secret-change-me-in-production";
export const APP_URL = process.env.APP_URL || "http://localhost:5173"; // link that goes in invite emails
