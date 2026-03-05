import type { CSSProperties } from 'react'

type IconProps = {
  size?: number
  color?: string
  style?: CSSProperties
  strokeWidth?: number
}

const base = (size: number): CSSProperties => ({
  width: size,
  height: size,
  display: 'inline-block',
  verticalAlign: 'middle',
})

export function ArrowRight({ size = 16, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M5 12H19" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M12 5L19 12L12 19" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  )
}

export function ChevronRight({ size = 15, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M9 6L15 12L9 18" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  )
}

export function Menu({ size = 20, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M4 6H20" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M4 12H20" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M4 18H20" stroke={color} strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

export function X({ size = 20, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M6 6L18 18" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M18 6L6 18" stroke={color} strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

export function Lock({ size = 12, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <rect height="10" rx="2" stroke={color} width="14" x="5" y="11" />
      <path d="M8 11V8C8 5.8 9.8 4 12 4C14.2 4 16 5.8 16 8V11" stroke={color} />
    </svg>
  )
}

export function Users({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <circle cx="9" cy="8" r="3" stroke={color} />
      <circle cx="17" cy="9" r="2.5" stroke={color} />
      <path d="M3 19C3 15.7 5.7 13 9 13H10C13.3 13 16 15.7 16 19" stroke={color} />
      <path d="M14 19C14 16.7 15.7 15 18 15H18.5C20.4 15 22 16.6 22 18.5V19" stroke={color} />
    </svg>
  )
}

export function Zap({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M13 2L4 14H11L9 22L20 9H13L13 2Z" stroke={color} strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  )
}

export function ShieldCheck({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M12 3L4 7V12C4 17 7.4 20.8 12 22C16.6 20.8 20 17 20 12V7L12 3Z" stroke={color} />
      <path d="M8.5 12.5L11 15L15.5 10.5" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  )
}

export function Shield({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M12 3L4 7V12C4 17 7.4 20.8 12 22C16.6 20.8 20 17 20 12V7L12 3Z" stroke={color} />
    </svg>
  )
}

export function Server({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <rect height="5" rx="1.5" stroke={color} width="18" x="3" y="4" />
      <rect height="5" rx="1.5" stroke={color} width="18" x="3" y="10" />
      <rect height="5" rx="1.5" stroke={color} width="18" x="3" y="16" />
      <circle cx="7" cy="6.5" fill={color} r="0.8" />
      <circle cx="7" cy="12.5" fill={color} r="0.8" />
      <circle cx="7" cy="18.5" fill={color} r="0.8" />
    </svg>
  )
}

export function EyeOff({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M3 3L21 21" stroke={color} strokeLinecap="round" />
      <path d="M10.5 10.5C9.7 11.3 9.7 12.7 10.5 13.5C11.3 14.3 12.7 14.3 13.5 13.5" stroke={color} />
      <path d="M2 12C4.2 8.2 7.7 6 12 6C16.3 6 19.8 8.2 22 12C21.1 13.6 20 15 18.7 16.1" stroke={color} />
    </svg>
  )
}

export function ScrollText({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <rect height="18" rx="2" stroke={color} width="14" x="5" y="3" />
      <path d="M8 8H16" stroke={color} strokeLinecap="round" />
      <path d="M8 12H16" stroke={color} strokeLinecap="round" />
      <path d="M8 16H13" stroke={color} strokeLinecap="round" />
    </svg>
  )
}

export function MessageSquare({ size = 15, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M5 6C5 4.9 5.9 4 7 4H17C18.1 4 19 4.9 19 6V14C19 15.1 18.1 16 17 16H10L6 20V16H7C5.9 16 5 15.1 5 14V6Z" stroke={color} />
    </svg>
  )
}

export function BookOpen({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M12 6C10 4.8 7.8 4.2 5.5 4.2C4.7 4.2 4 4.9 4 5.7V18.3C4 19.1 4.7 19.8 5.5 19.8C7.8 19.8 10 20.4 12 21.6V6Z" stroke={color} />
      <path d="M12 6C14 4.8 16.2 4.2 18.5 4.2C19.3 4.2 20 4.9 20 5.7V18.3C20 19.1 19.3 19.8 18.5 19.8C16.2 19.8 14 20.4 12 21.6V6Z" stroke={color} />
    </svg>
  )
}

export function Clock({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" stroke={color} />
      <path d="M12 7V12L15 14" stroke={color} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Globe({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="9" stroke={color} />
      <path d="M3 12H21" stroke={color} />
      <path d="M12 3C14.5 5.4 16 8.6 16 12C16 15.4 14.5 18.6 12 21" stroke={color} />
      <path d="M12 3C9.5 5.4 8 8.6 8 12C8 15.4 9.5 18.6 12 21" stroke={color} />
    </svg>
  )
}

export function BarChart2({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M4 20V10" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M10 20V6" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M16 20V13" stroke={color} strokeLinecap="round" strokeWidth="2" />
      <path d="M22 20V4" stroke={color} strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

export function FlaskConical({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M10 3H14" stroke={color} strokeLinecap="round" />
      <path d="M11 3V9L5 19C4.6 19.7 5.1 20.5 6 20.5H18C18.9 20.5 19.4 19.7 19 19L13 9V3" stroke={color} />
      <path d="M8 14H16" stroke={color} />
    </svg>
  )
}

export function Microscope({ size = 18, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M9 4L13 8L11 10L7 6L9 4Z" stroke={color} />
      <path d="M13 8L17 12" stroke={color} />
      <path d="M11 10V15C11 17.2 9.2 19 7 19" stroke={color} />
      <path d="M4 20H20" stroke={color} strokeLinecap="round" />
      <path d="M15 13C16.7 13 18 14.3 18 16C18 17.7 16.7 19 15 19" stroke={color} />
    </svg>
  )
}

export function Terminal({ size = 15, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <path d="M4 6L10 12L4 18" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      <path d="M12 18H20" stroke={color} strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

export function Copy({ size = 11, color = 'currentColor', style }: IconProps): JSX.Element {
  return (
    <svg fill="none" style={{ ...base(size), ...style }} viewBox="0 0 24 24">
      <rect height="13" rx="2" stroke={color} width="10" x="9" y="7" />
      <rect height="13" rx="2" stroke={color} width="10" x="5" y="4" />
    </svg>
  )
}
