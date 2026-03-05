export function LogoIcon({ size = 56 }: { size?: number }): JSX.Element {
  const s = size
  const cx = s / 2
  const cy = s / 2
  const r = s * 0.42

  const nodes = [
    { x: cx, y: cy - r },
    { x: cx + r * 0.866, y: cy - r * 0.5 },
    { x: cx + r * 0.866, y: cy + r * 0.5 },
    { x: cx, y: cy + r },
    { x: cx - r * 0.866, y: cy + r * 0.5 },
    { x: cx - r * 0.866, y: cy - r * 0.5 },
    { x: cx, y: cy },
  ]

  const edges = [
    [0, 1],
    [1, 2],
    [2, 3],
    [3, 4],
    [4, 5],
    [5, 0],
    [0, 6],
    [2, 6],
    [4, 6],
    [1, 3],
  ] as const

  const teal = '#2dd4bf'
  const white = '#ffffff'
  const nodeDotR = s * 0.045

  return (
    <svg fill="none" height={s} viewBox={`0 0 ${s} ${s}`} width={s} xmlns="http://www.w3.org/2000/svg">
      <circle cx={cx} cy={cy} fill="#2dd4bf" fillOpacity="0.07" r={r + s * 0.08} />
      {edges.map(([a, b], i) => {
        const na = nodes[a]
        const nb = nodes[b]
        const isTeal = [6, 7, 8, 9].includes(i)

        return (
          <line
            key={i}
            stroke={isTeal ? teal : white}
            strokeLinecap="round"
            strokeOpacity={isTeal ? 0.9 : 0.5}
            strokeWidth={s * 0.028}
            x1={na.x}
            x2={nb.x}
            y1={na.y}
            y2={nb.y}
          />
        )
      })}
      {nodes.map((n, i) => {
        const isCenter = i === 6
        const isTealNode = [0, 2, 4, 6].includes(i)

        return (
          <circle
            key={i}
            cx={n.x}
            cy={n.y}
            fill={isTealNode ? teal : white}
            fillOpacity={isCenter ? 1 : 0.9}
            r={isCenter ? nodeDotR * 1.7 : nodeDotR}
          />
        )
      })}
      <circle cx={cx} cy={cy} r={nodeDotR * 3} stroke={teal} strokeOpacity="0.35" strokeWidth={s * 0.018} />
    </svg>
  )
}

export function LogoHorizontal({
  size = 'md',
  dark = false,
}: {
  size?: 'sm' | 'md' | 'lg'
  dark?: boolean
}): JSX.Element {
  const iconSize = size === 'lg' ? 52 : size === 'md' ? 40 : 30
  const textScale = size === 'lg' ? 1 : size === 'md' ? 0.77 : 0.58

  const wordmarkFontSize = Math.round(26 * textScale)
  const domainColor = dark ? '#0f7a6e' : '#2dd4bf'
  const mainColor = dark ? '#0f1c22' : '#ffffff'

  return (
    <div style={{ alignItems: 'center', display: 'flex', gap: iconSize * 0.32 }}>
      <LogoIcon size={iconSize} />
      <svg
        fill="none"
        height={iconSize}
        viewBox={`0 0 ${Math.round(210 * textScale)} ${iconSize}`}
        xmlns="http://www.w3.org/2000/svg"
      >
        <text
          fontFamily="'Inter', 'Helvetica Neue', sans-serif"
          fontSize={wordmarkFontSize}
          fontWeight="600"
          letterSpacing="-0.5"
          y={iconSize * 0.66}
        >
          <tspan fill={mainColor}>artana</tspan>
          <tspan fill={domainColor}>.bio</tspan>
        </text>
      </svg>
    </div>
  )
}
