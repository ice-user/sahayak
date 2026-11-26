export function LogoMark({ className = "size-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="16" fill="#1d2150" />
      <path d="M12 38h40c0 9-8.5 15-20 15S12 47 12 38z" fill="#f2a900" />
      <path d="M32 12c5 6.5 8 10 8 15a8 8 0 0 1-16 0c0-5 3-8.5 8-15z" fill="#fde7a9" />
      <path d="M32 22c2.4 3 3.6 4.7 3.6 7a3.6 3.6 0 0 1-7.2 0c0-2.3 1.2-4 3.6-7z" fill="#e8590c" />
    </svg>
  );
}
