// ─── Token / session storage ──────────────────────────────────────────────────
// Single source of truth for localStorage keys. Only api.js and AuthContext
// should import from here — no other module reads auth state.

const TOKEN_KEY = 'truthmesh_token';
const USER_KEY  = 'truthmesh_user';

/** Raw JWT string, or null if not signed in. */
export const getToken = () => localStorage.getItem(TOKEN_KEY);

/** Parsed user object { username }, or null. */
export const getUser  = () => {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
  catch { return null; }
};

/** Persist token + user after login/register. */
export const setSession = (token, user) => {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};

/** Remove session — call on logout or 401. */
export const clearSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

/**
 * Returns an Authorization header object if a token exists, otherwise {}.
 * Spread into fetch `headers` — never sets Content-Type so FormData boundary
 * is set correctly by the browser.
 */
export const authHeaders = () => {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};
