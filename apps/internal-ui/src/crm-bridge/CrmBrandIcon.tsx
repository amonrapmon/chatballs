import type { CrmLink } from "./model";

type CrmBrand = CrmLink["provider"];

// Self-contained SVG lettermarks; no remote logos, fonts or extra dependencies.
export function CrmBrandIcon({ provider, size = 15 }: { provider: CrmBrand; size?: number }) {
  const yclients = provider === "YCLIENTS";
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="crm-brand-icon"
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
    >
      <circle cx="10" cy="10" r="10" fill={yclients ? "#FFCB00" : "#182B5F"} />
      {yclients ? (
        <path
          d="M5.8 6.1 10 10.3 14.2 6.1 M10 10.3v4"
          stroke="#000000"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : (
        <path
          d="M6.9 5.8h2.5a4.2 4.2 0 0 1 0 8.4H6.9z"
          stroke="#FFFFFF"
          strokeWidth="1.85"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}
