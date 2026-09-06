// Scraping progress bar component showing active job counters and elapsed time.

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Progress } from '~/components/ui/progress';
import { Badge } from '~/components/ui/badge';

interface ProgressBarProps {
  status: string;
  percentage: number;
  scraped: number;
  failed: number;
  discovered: number;
  startedAt: string | null;
}

export function ProgressBar({ status, percentage, scraped, failed, discovered, startedAt }: ProgressBarProps) {
  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if ((status === 'running' || status === 'in_progress') && startedAt) {
      interval = setInterval(() => {
        const start = new Date(startedAt).getTime();
        setElapsed(Math.floor((Date.now() - start) / 1000));
      }, 1000);
    } else {
      setElapsed(0);
    }
    return () => clearInterval(interval);
  }, [status, startedAt]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m ${s}s`;
  };

  const getStatusColor = (s: string) => {
    switch (s) {
      case 'running':
      case 'in_progress': return 'bg-blue-500';
      case 'completed': return 'bg-green-500';
      case 'failed': return 'bg-red-500';
      case 'stopped': return 'bg-yellow-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">Scraping Progress</CardTitle>
        <Badge className={getStatusColor(status)}>
          {status.toUpperCase()}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{percentage.toFixed(1)}%</span>
            {(status === 'running' || status === 'in_progress') && <span>{formatTime(elapsed)}</span>}
          </div>
          <Progress value={percentage} />
        </div>
        <div className="flex justify-between text-sm">
          <div className="flex flex-col items-center">
            <span className="text-muted-foreground">Scraped</span>
            <span className="font-medium text-green-500">{scraped}</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-muted-foreground">Failed</span>
            <span className="font-medium text-red-500">{failed}</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-muted-foreground">Discovered</span>
            <span className="font-medium text-blue-500">{discovered}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
