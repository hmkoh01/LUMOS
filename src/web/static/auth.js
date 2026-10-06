/**
 * LUMOS Auth Client  (auth.js)
 *
 * Loads configuration from GET /api/v1/auth/config.
 * In supabase mode, initialises the Supabase JS client (window.supabase must
 * already be loaded from CDN before this script runs).
 * In local mode every function returns safe no-op values so the app works
 * exactly as before without any auth overhead.
 *
 * Usage
 * -----
 *   await authClient.init();          // call once at app start
 *   authClient.isAuthMode()           // true when mode=supabase
 *   authClient.isDevMode()            // true in local mode or when LUMOS_DEV_MODE=true
 *   await authClient.getAccessToken() // current Bearer token or null
 *   await authClient.getSession()     // raw Supabase session or null
 *   await authClient.getUser()        // Supabase user object or null
 *   await authClient.signOut()        // sign out + clear session
 *   authClient.onAuthStateChange(fn)  // subscribe to auth events
 *   authClient.redirectToLogin(reason)// navigate to /login (once); optional reason param
 */

const authClient = (() => {
  let _config = null;   // { auth_mode, supabase_url, supabase_publishable_key, dev_mode, public_base_url }
  let _client = null;   // Supabase JS client
  let _redirecting = false;

  /**
   * Load auth config and, if mode=supabase, initialise the Supabase client.
   * Must be called before any other method.
   */
  async function init() {
    const res = await fetch("/api/v1/auth/config");
    if (!res.ok) throw new Error("Auth config endpoint unavailable");
    _config = await res.json();

    if (_config.auth_mode === "supabase") {
      if (!window.supabase || typeof window.supabase.createClient !== "function") {
        throw new Error("Supabase JS SDK (window.supabase) not loaded");
      }
      _client = window.supabase.createClient(
        _config.supabase_url,
        _config.supabase_publishable_key,
      );
    }
    return _config;
  }

  /** True when running in Supabase auth mode. */
  function isAuthMode() {
    return _config?.auth_mode === "supabase";
  }

  /**
   * True when dev-only features (cloud status, feature gates, dev account panel)
   * should be shown. Always true in local mode; opt-in via LUMOS_DEV_MODE=true
   * in supabase mode.
   */
  function isDevMode() {
    return _config?.dev_mode === true;
  }

  /**
   * The base URL to use for OAuth redirects.
   * Returns LUMOS_PUBLIC_BASE_URL if configured, otherwise window.location.origin.
   */
  function getPublicBaseUrl() {
    return (_config?.public_base_url || "").trim() || window.location.origin;
  }

  /** Returns the raw Supabase client, or null in local mode. */
  function getClient() {
    return _client;
  }

  /** Returns the current Supabase session, or null. */
  async function getSession() {
    if (!_client) return null;
    try {
      const { data, error } = await _client.auth.getSession();
      if (error) return null;
      return data.session ?? null;
    } catch {
      return null;
    }
  }

  /**
   * Returns the current Bearer access token, or null.
   * Supabase SDK handles token refresh automatically.
   */
  async function getAccessToken() {
    const session = await getSession();
    return session?.access_token ?? null;
  }

  /** Returns the Supabase user object from the current session, or null. */
  async function getUser() {
    const session = await getSession();
    return session?.user ?? null;
  }

  /** Sign the user out and clear the Supabase session. */
  async function signOut() {
    if (!_client) return;
    try {
      await _client.auth.signOut();
    } catch {
      // Ignore network errors on sign-out
    }
  }

  /**
   * Subscribe to Supabase auth state changes.
   * Returns an unsubscribe function (call to stop listening).
   */
  function onAuthStateChange(callback) {
    if (!_client) return () => {};
    const { data } = _client.auth.onAuthStateChange(callback);
    return data?.subscription?.unsubscribe ?? (() => {});
  }

  /**
   * Navigate to /login. Idempotent — only fires once per page load to
   * prevent redirect loops.
   *
   * @param {string} [reason] - optional error reason appended as ?error=<reason>
   *   so the login page can display an appropriate message.
   */
  function redirectToLogin(reason) {
    if (_redirecting) return;
    _redirecting = true;
    const url = reason ? `/login?error=${encodeURIComponent(reason)}` : "/login";
    window.location.href = url;
  }

  return {
    init,
    isAuthMode,
    isDevMode,
    getPublicBaseUrl,
    getClient,
    getSession,
    getAccessToken,
    getUser,
    signOut,
    onAuthStateChange,
    redirectToLogin,
  };
})();
