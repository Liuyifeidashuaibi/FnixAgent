/**
 * Tauri desktop detection — ChatGPT shell is a desktop product, not a web SPA.
 */

export function isTauriDesktop(): boolean {
  try {
    return Boolean(
      (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ ||
        (window as unknown as { __TAURI__?: unknown }).__TAURI__,
    );
  } catch {
    return false;
  }
}

export async function setDesktopWindowTitle(title: string): Promise<void> {
  if (!isTauriDesktop()) return;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow().setTitle(title);
  } catch {
    /* browser / missing plugin */
  }
}
