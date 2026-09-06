// Analytics charts and key performance metric cards with responsive Recharts visuals.

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '~/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Package, DollarSign, Star, CheckCircle2, BarChart3, TrendingUp, Tag } from 'lucide-react';
import type { Metrics } from '~/lib/types';

interface MetricsChartsProps {
  metrics: Metrics | null;
}

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-popover/95 border border-border/80 backdrop-blur-md px-3 py-2 rounded-lg shadow-xl text-xs">
        <p className="font-semibold text-foreground mb-1">{label}</p>
        <div className="flex items-center gap-2 text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-primary inline-block" />
          <span>Count:</span>
          <span className="font-mono font-bold text-foreground">{payload[0].value}</span>
        </div>
      </div>
    );
  }
  return null;
}

export function MetricsCharts({ metrics }: MetricsChartsProps) {
  if (!metrics || metrics.total_products === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="p-8 text-center flex flex-col items-center justify-center space-y-2">
          <div className="p-3 bg-muted rounded-full text-muted-foreground">
            <BarChart3 className="w-6 h-6" />
          </div>
          <CardTitle className="text-base">No Analytics Data Yet</CardTitle>
          <CardDescription>Start a scraping job to populate product metrics, price distributions, and brand insights.</CardDescription>
        </CardContent>
      </Card>
    );
  }

  const minPriceStr = metrics.min_price !== null ? `$${metrics.min_price.toFixed(2)}` : 'N/A';
  const maxPriceStr = metrics.max_price !== null ? `$${metrics.max_price.toFixed(2)}` : 'N/A';

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="relative overflow-hidden border-border/60 hover:border-primary/40 transition-colors">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Total Products</CardTitle>
            <div className="p-2 bg-blue-500/10 text-blue-500 rounded-lg">
              <Package className="w-4 h-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono tracking-tight">{metrics.total_products}</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-emerald-500" /> Across all runs
            </p>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden border-border/60 hover:border-emerald-500/40 transition-colors">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Avg Price</CardTitle>
            <div className="p-2 bg-emerald-500/10 text-emerald-500 rounded-lg">
              <DollarSign className="w-4 h-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono tracking-tight">
              {metrics.avg_price !== null ? `$${metrics.avg_price.toFixed(2)}` : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1 truncate">
              Range: {minPriceStr} - {maxPriceStr}
            </p>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden border-border/60 hover:border-amber-500/40 transition-colors">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Avg Rating</CardTitle>
            <div className="p-2 bg-amber-500/10 text-amber-500 rounded-lg">
              <Star className="w-4 h-4 fill-amber-500/20" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono tracking-tight">
              {metrics.avg_rating !== null ? `${metrics.avg_rating.toFixed(1)} / 5.0` : 'N/A'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {metrics.total_reviews ? `${metrics.total_reviews.toLocaleString()} reviews` : 'Based on product ratings'}
            </p>
          </CardContent>
        </Card>

        <Card className="relative overflow-hidden border-border/60 hover:border-purple-500/40 transition-colors">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Success Rate</CardTitle>
            <div className="p-2 bg-purple-500/10 text-purple-500 rounded-lg">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono tracking-tight">
              {metrics.success_rate.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Successful requests ratio
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Star className="w-4 h-4 text-amber-500" />
              <CardTitle className="text-sm font-semibold">Rating Distribution</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="h-64 pt-2">
            {metrics.rating_distribution?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.rating_distribution} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ratingGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#d97706" stopOpacity={0.3} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                  <XAxis 
                    dataKey="rating" 
                    fontSize={11} 
                    tickLine={false} 
                    axisLine={false} 
                    tickFormatter={(val) => `★ ${val}`}
                    stroke="#9ca3af"
                  />
                  <YAxis fontSize={11} tickLine={false} axisLine={false} stroke="#9ca3af" allowDecimals={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" fill="url(#ratingGradient)" radius={[6, 6, 0, 0]} barSize={28} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No rating data</div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-emerald-500" />
              <CardTitle className="text-sm font-semibold">Price Ranges</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="h-64 pt-2">
            {metrics.price_ranges?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.price_ranges} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#059669" stopOpacity={0.3} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                  <XAxis 
                    dataKey="range" 
                    fontSize={10} 
                    tickLine={false} 
                    axisLine={false} 
                    stroke="#9ca3af"
                  />
                  <YAxis fontSize={11} tickLine={false} axisLine={false} stroke="#9ca3af" allowDecimals={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" fill="url(#priceGradient)" radius={[6, 6, 0, 0]} barSize={28} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No price range data</div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Tag className="w-4 h-4 text-blue-500" />
              <CardTitle className="text-sm font-semibold">Top Brands</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="h-64 pt-2">
            {metrics.top_brands?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.top_brands} layout="vertical" margin={{ top: 5, right: 15, left: 10, bottom: 5 }}>
                  <defs>
                    <linearGradient id="brandGradient" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#6366f1" stopOpacity={0.4} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} horizontal={false} />
                  <XAxis type="number" fontSize={11} tickLine={false} axisLine={false} stroke="#9ca3af" allowDecimals={false} />
                  <YAxis 
                    dataKey="brand" 
                    type="category" 
                    fontSize={11} 
                    tickLine={false} 
                    axisLine={false} 
                    width={90}
                    stroke="#9ca3af"
                    tickFormatter={(val) => val.length > 12 ? `${val.substring(0, 11)}…` : val}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" fill="url(#brandGradient)" radius={[0, 6, 6, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No brand data</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
