import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-20">
      <h1 className="display text-3xl">Page not found</h1>
      <p className="mt-3 text-ink-soft">The page you are looking for does not exist.</p>
      <Link href="/" className="mt-6 inline-flex min-h-11 items-center font-semibold underline decoration-marigold decoration-2 underline-offset-4">
        Back to Sahayak
      </Link>
    </div>
  );
}
