// AI data extraction component with real-time progress bar and CSV export.

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '~/components/ui/card';
import { Button } from '~/components/ui/button';
import { Progress } from '~/components/ui/progress';
import { Badge } from '~/components/ui/badge';

interface AiExtractionProps {
  isScraperRunning: boolean;
  isAiRunning: boolean;
  aiProgress: {
    processed: number;
    total: number;
    percentage: number;
    current_asin?: string;
    error?: string;
    completed?: boolean;
    count?: number;
  } | null;
  onStartAi: () => void;
  onExportAiCsv: () => void;
}

export function AiExtraction({
  isScraperRunning,
  isAiRunning,
  aiProgress,
  onStartAi,
  onExportAiCsv,
}: AiExtractionProps) {
  const percentage = aiProgress?.percentage || 0;

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-xl">AI Data Extraction</CardTitle>
          <Badge variant={isAiRunning ? 'default' : aiProgress?.completed ? 'secondary' : 'outline'}>
            {isAiRunning ? 'RUNNING' : aiProgress?.completed ? 'COMPLETED' : 'IDLE'}
          </Badge>
        </div>
        <CardDescription>
          Enrich raw product data with LLM extracted categories and structured key-value attributes.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-2">
          <Button 
            onClick={onStartAi} 
            disabled={isScraperRunning || isAiRunning}
            className="flex-1 font-semibold "
          >
            {isAiRunning ? '⚡Running...' : '✨ Run AI Extraction'}
          </Button>

          <Button
            variant="outline"
            onClick={onExportAiCsv}
            className="gap-1 border-primary/40 hover:bg-primary/10"
          >
            📥 Export AI Results (CSV)
          </Button>
        </div>

        {isAiRunning && (
          <div className="space-y-2 p-3 bg-muted/40 rounded-lg border border-border">
            <div className="flex justify-between items-center text-xs font-medium">
              <span className="text-primary font-semibold">{percentage.toFixed(1)}% Completed</span>
              <span className="text-muted-foreground">{aiProgress?.processed || 0} / {aiProgress?.total || 0} items</span>
            </div>
            <Progress value={percentage} className="h-2.5" />
            {aiProgress?.current_asin && (
              <div className="text-xs text-muted-foreground flex items-center justify-between pt-1">
                <span>Analyzing ASIN:</span>
                <span className="font-mono font-semibold text-foreground">{aiProgress.current_asin}</span>
              </div>
            )}
          </div>
        )}

        {aiProgress?.completed && !isAiRunning && (
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-md text-xs text-emerald-400 flex items-center justify-between">
            <span>✅ AI extraction finished! {aiProgress.count ?? 0} products enriched.</span>
            <Button variant="ghost" size="sm" onClick={onExportAiCsv} className="h-6 text-xs underline">
              Download CSV
            </Button>
          </div>
        )}

        {aiProgress?.error && !isAiRunning && (
          <div className="p-3 bg-destructive/10 border border-destructive/30 rounded-md text-xs text-destructive">
            ⚠️ {aiProgress.error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
