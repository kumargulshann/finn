export type Holding = {
  id: string;
  name: string;
  symbol: string;
  sector: string;
  price: string;
  change: string;
  positive: boolean;
  weight: string;
  initials: string;
  color: string;
};

export type AlertItem = {
  id: string;
  company: string;
  symbol: string;
  title: string;
  summary: string;
  type: string;
  time: string;
  impact: "High" | "Medium" | "Low";
  positive: boolean;
  initials: string;
  color: string;
  source: string;
  sourceName: string;
  sourceDate: string;
  source_exchange?: string;
  why: string;
  details: string[];
  is_demo?: boolean;
};
