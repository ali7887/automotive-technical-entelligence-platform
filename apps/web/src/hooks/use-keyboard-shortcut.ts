"use client";

import { useEffect } from "react";

/** True on macOS/iOS, where the palette should show ⌘ and listen for Meta. */
export function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent);
}

export interface KeyboardShortcutOptions {
  /** Require the Meta key (⌘ on macOS). Default false. */
  meta?: boolean;
  /** Require the Ctrl key. Default false. */
  ctrl?: boolean;
  /** Require Shift. Default false. */
  shift?: boolean;
  /**
   * When meta or ctrl is requested, accept EITHER modifier so one shortcut
   * covers ⌘K on macOS and Ctrl+K elsewhere. Default true.
   */
  metaOrCtrl?: boolean;
  /** Fire even while an input/textarea/contentEditable is focused. Default false. */
  allowInInput?: boolean;
  /** Attach the listener at all. Default true. */
  enabled?: boolean;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * Fire `handler` when `key` is pressed with the requested modifiers. One
 * window-level keydown listener; normalizes ⌘ (macOS) vs Ctrl so a single call
 * handles both. `key` is matched case-insensitively against `event.key`.
 */
export function useKeyboardShortcut(
  key: string,
  handler: (event: KeyboardEvent) => void,
  options: KeyboardShortcutOptions = {},
): void {
  const {
    meta = false,
    ctrl = false,
    shift = false,
    metaOrCtrl = true,
    allowInInput = false,
    enabled = true,
  } = options;

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      if (!allowInInput && isEditableTarget(event.target)) return;

      // Modifier match. When either meta or ctrl is requested and metaOrCtrl is
      // on, accept whichever the platform uses.
      if ((meta || ctrl) && metaOrCtrl) {
        if (!event.metaKey && !event.ctrlKey) return;
      } else {
        if (meta && !event.metaKey) return;
        if (ctrl && !event.ctrlKey) return;
      }
      if (shift && !event.shiftKey) return;

      handler(event);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [key, handler, meta, ctrl, shift, metaOrCtrl, allowInInput, enabled]);
}
