interface LogoMarkProps {
  size?: number
  className?: string
}

/** Split U logo mark — knotted left arm (zinc), clean right arm (teal) with dot */
export function LogoMark({ size = 24, className }: LogoMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 56 56"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      {/* Left arm: base to knot entry */}
      <path d="M14 36 C14 44, 28 50, 28 50" stroke="#e4e4e7" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      <path d="M14 36 L14 20" stroke="#e4e4e7" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      {/* Trefoil knot at top of left arm */}
      <path d="M14 20 C14 16, 20 14, 22 16" stroke="#e4e4e7" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M22 16 C24 18, 22 22, 18 22 C14 22, 10 20, 8 16 C6 12, 10 8, 14 8" stroke="#e4e4e7" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M14 8 C18 8, 22 6, 20 10" stroke="#e4e4e7" strokeWidth="3" strokeLinecap="round" fill="none" />
      {/* Right arm: clean teal */}
      <path d="M28 50 C28 50, 42 44, 42 36 L42 6" stroke="#2dd4bf" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      <circle cx="42" cy="6" r="2.5" fill="#2dd4bf" />
    </svg>
  )
}

/** Simplified favicon mark — split U without knot detail */
export function FaviconMark({ size = 16, className }: LogoMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 6 L12 28 C12 38, 24 44, 24 44" stroke="#e4e4e7" strokeWidth="7" strokeLinecap="round" fill="none" />
      <path d="M24 44 C24 44, 36 38, 36 28 L36 6" stroke="#2dd4bf" strokeWidth="7" strokeLinecap="round" fill="none" />
      <circle cx="36" cy="6" r="4" fill="#2dd4bf" />
    </svg>
  )
}
