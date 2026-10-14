import logoUrl from "./logo-sunset.svg";
import "./styles.css";

/** Один векторный ресурс для брендинга и favicon; size задаёт ширину. */
export function LogoIcon({ size = 17 }: { size?: number }) {
  return <img className="chatballs-logo" src={logoUrl} width={size} alt="" aria-hidden="true" />;
}
