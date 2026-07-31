"use client";

/**
 * Skeleton — animated placeholder shown while content is loading.
 * Used by the VerdictCard, ImpactPanel, and RecommendationCard to
 * eliminate the "frozen UI" feeling during heavy API calls.
 */

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  borderRadius?: number | string;
  style?: React.CSSProperties;
}

export function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = 8,
  style,
}: SkeletonProps) {
  return (
    <div
      style={{
        display: "inline-block",
        width,
        height,
        borderRadius,
        background: "rgba(148, 163, 184, 0.18)",
        animation: "skeleton-pulse 1.4s ease-in-out infinite",
        ...style,
      }}
    />
  );
}

/**
 * SkeletonGroup — multiple skeletons laid out in a column.
 */
export function SkeletonGroup({
  count = 3,
  gap = 8,
  height = 16,
}: {
  count?: number;
  gap?: number;
  height?: number;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton
          key={i}
          height={height}
          width={`${100 - i * 15}%`}
        />
      ))}
  </div>
  );
}
