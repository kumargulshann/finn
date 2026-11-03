import type { SVGProps } from "react";

export type IconName =
  | "activity" | "arrowDown" | "arrowLeft" | "arrowRight" | "arrowUp"
  | "bell" | "bookmark" | "briefcase" | "calendar" | "check" | "chevronDown"
  | "clock" | "close" | "dots" | "external" | "file" | "filter" | "home"
  | "info" | "layers" | "menu" | "plus" | "search" | "send" | "settings"
  | "shield" | "spark" | "star" | "trend" | "wallet";

const paths: Record<IconName, string> = {
  activity: "M3 12h4l3-8 4 16 3-8h4",
  arrowDown: "M12 5v14m-7-7 7 7 7-7",
  arrowLeft: "M19 12H5m7 7-7-7 7-7",
  arrowRight: "M5 12h14m-7-7 7 7-7 7",
  arrowUp: "M12 19V5m-7 7 7-7 7 7",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12a2 2 0 0 0 4 0",
  bookmark: "M6 4h12v17l-6-4-6 4z",
  briefcase: "M3 7h18v13H3zM8 7V4h8v3m-13 5h18m-11 0v2h4v-2",
  calendar: "M4 6h16v15H4zM8 3v6m8-6v6M4 11h16",
  check: "m5 12 4 4L19 6",
  chevronDown: "m6 9 6 6 6-6",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-16v6l4 2",
  close: "m6 6 12 12M18 6 6 18",
  dots: "M5 12h.01M12 12h.01M19 12h.01",
  external: "M14 3h7v7m0-7L10 14m-3-9H4v15h15v-3",
  file: "M6 3h8l5 5v13H6zM14 3v5h5M9 13h7m-7 4h7",
  filter: "M4 5h16M7 12h10m-7 7h4",
  home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-14h.01M11 12h1v5h1",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5m-18 5 9 5 9-5",
  menu: "M4 6h16M4 12h16M4 18h16",
  plus: "M12 5v14m-7-7h14",
  search: "m20 20-4.5-4.5m2-5.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z",
  send: "m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v2m0 14v2m9-9h-2M5 12H3m15.36-6.36-1.42 1.42M7.06 16.94l-1.42 1.42m12.72 0-1.42-1.42M7.06 7.06 5.64 5.64",
  shield: "M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Zm-3-11 2 2 4-4",
  spark: "m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Zm7 12 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z",
  star: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z",
  trend: "M3 17 9 11l4 4 8-9m-7 0h7v7",
  wallet: "M3 6.5A2.5 2.5 0 0 1 5.5 4H21v16H5.5A2.5 2.5 0 0 1 3 17.5zM3 7h18m-5 6h5",
};

export function Icon({
  name,
  size = 18,
  strokeWidth = 1.7,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName; size?: number; strokeWidth?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
