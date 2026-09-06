// Analytics charts component displaying rating distributions, price ranges, and top brands.

import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { Metrics } from '~/lib/types';

interface MetricsChartsProps {
  metrics: Metrics | null;
}

export function MetricsCharts({ metrics }: MetricsChartsProps) {
  if (!metrics) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-muted-foreground">
          No metrics data available yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Total Products</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{metrics.total_products}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Avg Price</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.avg_price !== null ? `$${metrics.avg_price.toFixed(2)}` : 'N/A'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Avg Rating</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metrics.avg_rating !== null ? `${metrics.avg_rating.toFixed(1)} / 5` : 'N/A'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Success Rate</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{metrics.success_rate.toFixed(1)}%</div></CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="col-span-1">
          <CardHeader><CardTitle className="text-sm">Rating Distribution</CardTitle></CardHeader>
          <CardContent className="h-48">
            {metrics.rating_distribution?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.rating_distribution}>
                  <XAxis dataKey="rating" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151' }} />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground">No data</div>}
          </CardContent>
        </Card>
        
        <Card className="col-span-1">
          <CardHeader><CardTitle className="text-sm">Price Ranges</CardTitle></CardHeader>
          <CardContent className="h-48">
            {metrics.price_ranges?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.price_ranges}>
                  <XAxis dataKey="range" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151' }} />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground">No data</div>}
          </CardContent>
        </Card>

        <Card className="col-span-1">
          <CardHeader><CardTitle className="text-sm">Top Brands</CardTitle></CardHeader>
          <CardContent className="h-48">
            {metrics.top_brands?.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={metrics.top_brands} layout="vertical" margin={{ left: 20 }}>
                  <XAxis type="number" hide />
                  <YAxis dataKey="brand" type="category" fontSize={12} tickLine={false} axisLine={false} width={80} />
                  <Tooltip contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151' }} />
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <div className="text-sm text-muted-foreground">No data</div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
