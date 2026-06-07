type ScoreRingProps = {
  score: number | null | undefined;
  size?: number;
  label?: string;
  sublabel?: string;
};

function scoreColor(score: number): string {
  if (score >= 80) return "var(--success)";
  if (score >= 50) return "#fbbf24";
  return "var(--danger)";
}

export default function ScoreRing({ score, size = 88, label, sublabel }: ScoreRingProps) {
  const value = score ?? 0;
  const display = score == null ? "—" : value;
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const color = score == null ? "var(--muted)" : scoreColor(value);

  return (
    <div className="score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth="6"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={score == null ? circumference : offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="score-ring-center">
        <strong style={{ color }}>{display}</strong>
        {label && <span>{label}</span>}
        {sublabel && <small>{sublabel}</small>}
      </div>
    </div>
  );
}
