import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import type { AnalysisRecord } from "./api";

echarts.use([BarChart, GridComponent, LegendComponent, CanvasRenderer]);

type Props = {
  records: AnalysisRecord[];
};

export function ProbabilityChart({ records }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = echarts.init(containerRef.current);
    chart.setOption({
      legend: { data: ["Market fair", "Model"] },
      xAxis: {
        type: "category",
        data: records.map((record) => record.selection),
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        axisLabel: {
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
      },
      series: [
        {
          name: "Market fair",
          type: "bar",
          data: records.map((record) => record.market_probability_fair),
        },
        {
          name: "Model",
          type: "bar",
          data: records.map((record) => record.model_probability),
        },
      ],
    });

    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [records]);

  return <div className="chart" ref={containerRef} aria-label="機率比較圖" />;
}
