import type { ReactNode } from "react";

export function ReportTable({ title, side, headers, children, foot, className = "", legend }: {
  title: string; side?: ReactNode; headers: string[]; children: ReactNode; foot?: string; className?: string; legend?: ReactNode;
}) {
  return <section className={`report-table report-card ${className}`}>
    <div className="report-table-heading"><h3>{title}</h3><span>{side}</span></div>
    <div className="report-table-scroll"><table><thead><tr>{headers.map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{children}</tbody></table></div>
    {legend && <div className="report-table-legend">{legend}</div>}
    {foot && <div className="report-table-foot">{foot}</div>}
  </section>;
}
