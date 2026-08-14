import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
} from "recharts";

/**
 * Every recharts usage in the Dashboard, in one lazily-loaded module.
 *
 * recharts is ~560 KB of the build, and importing it at the top of Dashboard.jsx
 * chained that chunk onto the Dashboard chunk — which App.jsx prefetches on idle
 * for every user, whether or not they ever open a chart. Pulling the charts
 * behind a dynamic import means the cost is paid by the tab that draws them.
 *
 * The tooltips and axis ticks stay in Dashboard.jsx and arrive here as elements:
 * they're plain SVG/HTML, so keeping them out avoids a circular import back into
 * the very chunk this file exists to stay out of.
 */

export function TrafficAreaChart({ data, colorActive, colorNew }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="fillActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorActive} stopOpacity={0.28} />
            <stop offset="100%" stopColor={colorActive} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="fillNew" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colorNew} stopOpacity={0.18} />
            <stop offset="100%" stopColor={colorNew} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={{ stroke: "#e7eaf0" }} minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e7eaf0", boxShadow: "0 4px 16px rgba(18,24,38,0.08)" }} />
        <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
        <Area type="monotone" dataKey="activeUsers" name="Active users" stroke={colorActive} strokeWidth={2.5} fill="url(#fillActive)" dot={false} activeDot={{ r: 4 }} />
        <Area type="monotone" dataKey="newUsers" name="New users" stroke={colorNew} strokeWidth={2} fill="url(#fillNew)" dot={false} activeDot={{ r: 4 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ExplorerChart({
  chartType,
  chartData,
  donutData,
  donutColors,
  donutTooltip,
  lineData,
  seriesName,
  colorActive,
  yAxisLabelWidth,
  yAxisTick,
}) {
  if (chartType === "donut") {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={donutData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} stroke="none">
            {donutData.map((d, i) => (
              <Cell key={d.name} fill={d.name === "Other" ? "#a8a29e" : donutColors[i % donutColors.length]} />
            ))}
          </Pie>
          <Tooltip content={donutTooltip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === "line") {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={lineData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e7e5e4" }} />
          <Line type="monotone" dataKey="value" name={seriesName} stroke={colorActive} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 44)}>
      <BarChart data={chartData} layout="vertical" barCategoryGap="30%" margin={{ top: 4, right: 12, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} />
        <YAxis
          type="category"
          dataKey="name"
          tickLine={false}
          axisLine={false}
          width={yAxisLabelWidth}
          interval={0}
          tick={yAxisTick}
        />
        <Tooltip cursor={{ fill: "#fafaf9" }} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e7e5e4" }} />
        <Bar dataKey="value" name={seriesName} fill={colorActive} radius={[0, 4, 4, 0]} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SearchConsoleTrendChart({ data, plotted, tooltip }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} minTickGap={24} />
        <YAxis yAxisId="clicks" hide allowDecimals={false} />
        <YAxis yAxisId="impressions" hide allowDecimals={false} />
        <YAxis yAxisId="ctr" hide domain={[0, "auto"]} />
        <YAxis yAxisId="position" hide reversed domain={["auto", "auto"]} />
        <Tooltip content={tooltip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {plotted.map((m) => (
          <Line
            key={m.key}
            yAxisId={m.key}
            type="monotone"
            dataKey={m.key}
            name={m.label}
            stroke={m.color}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
