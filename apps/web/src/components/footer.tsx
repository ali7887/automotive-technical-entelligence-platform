/** App-wide developer branding. Mounted once in the root layout so it flows
 *  after content on every route (public and authenticated) and settles at the
 *  bottom on short pages. Never fixed-position. Pure server component — no
 *  hooks or client JS, and the year is resolved at render time. */
export function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto w-full max-w-6xl px-6 py-6 text-xs text-muted-foreground">
        <p>
          © {new Date().getFullYear()}{" "}
          <a
            href="https://alikiani.vercel.app"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Ali Kiani
          </a>{" "}
          · AI-native systems &amp; real-time UX
        </p>
      </div>
    </footer>
  );
}
