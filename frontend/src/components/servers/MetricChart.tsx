"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import type { StatPoint } from "@/lib/useServerStats";

interface MetricChartProps {
  data: StatPoint[];
  dataKey: "cpu" | "memPct";
  color: string;
  /** Format a raw value for the tooltip. */
  format: (v: number) => string;
  /** Fixed Y axis max (e.g. 100 for percentages); omit to auto-scale. */
  max?: number;
}

export default function MetricChart({ data, dataKey, color, format, max }: MetricChartProps) {
  const gradientId = `grad-${dataKey}-${color.replace("#", "")}`;
  return (
    <ResponsiveContainer width="100%" height={160}>
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis
          domain={[0, max ?? "auto"]}
          width={44}
          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => format(Number(v))}
        />
        <Tooltip
          contentStyle={{
            background: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ display: "none" }}
          formatter={(v: number | string) => [format(Number(v)), ""]}
        />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
