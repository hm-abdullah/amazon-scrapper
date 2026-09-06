// TypeScript type interfaces for scraped products, runs, metrics, and WebSocket messages.

export interface Product {
  id: number;
  asin: string;
  brand: string | null;
  title: string | null;
  seller: string | null;
  price: number | null;
  currency: string | null;
  availability: string | null;
  description: string | null;
  bullet_points: string[] | null;
  specifications: Record<string, string> | null;
  images: string[] | null;
  rating: number | null;
  review_count: number | null;
  product_url: string | null;
  scraped_at: string | null;
  run_id: string | null;
}

export interface ScrapeRun {
  id: string;
  status: string;
  max_products: number;
  target_urls: string[];
  products_scraped: number;
  products_failed: number;
  products_discovered: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface Metrics {
  total_products: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  avg_rating: number | null;
  total_reviews: number;
  success_rate: number;
  top_brands: { brand: string; count: number }[];
  rating_distribution: { rating: number; count: number }[];
  price_ranges: { range: string; count: number }[];
}

export interface WsMessage {
  type: string;
  [key: string]: any;
}
