// Main Amazon Scraper dashboard layout, WebSocket event listener, and state coordinator.

import { useState, useEffect, useCallback } from 'react';
import { Toaster } from '~/components/ui/sonner';
import { toast } from 'sonner';
import { useWebSocket } from '~/lib/api';
import * as api from '~/lib/api';
import { ScraperForm } from '~/components/ScraperForm';
import { ProgressBar } from '~/components/ProgressBar';
import { ProductsTable } from '~/components/ProductsTable';
import { MetricsCharts } from '~/components/MetricsCharts';
import { AiExtraction } from '~/components/AiExtraction';
import type { Product, ScrapeRun, Metrics } from '~/lib/types';
import { Separator } from '~/components/ui/separator';
import { Badge } from '~/components/ui/badge';

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [totalProducts, setTotalProducts] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [search, setSearch] = useState<string>('');
  
  const [runs, setRuns] = useState<ScrapeRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('all');

  const [currentRun, setCurrentRun] = useState<ScrapeRun | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [percentage, setPercentage] = useState<number>(0);

  const [isAiRunning, setIsAiRunning] = useState<boolean>(false);
  const [aiProgress, setAiProgress] = useState<{
    processed: number;
    total: number;
    percentage: number;
    current_asin?: string;
    error?: string;
    completed?: boolean;
    count?: number;
  } | null>(null);

  const [isLoadingProducts, setIsLoadingProducts] = useState<boolean>(false);

  const { lastMessage, isConnected, connectionStatus } = useWebSocket();

  const loadProducts = useCallback(async (p: number, s: string, rId = selectedRunId) => {
    setIsLoadingProducts(true);
    try {
      const data = await api.getProducts(p, 50, s, 'scraped_at', 'desc', rId);
      setProducts(data.products || []);
      setTotalProducts(data.total || 0);
    } catch (e) {
      console.error('Failed to load products', e);
    } finally {
      setIsLoadingProducts(false);
    }
  }, [selectedRunId]);

  const loadMetrics = async () => {
    try {
      const data = await api.getMetrics();
      setMetrics(data);
    } catch (e) {
      console.error('Failed to load metrics', e);
    }
  };

  const loadRuns = async () => {
    try {
      const data = await api.getRuns();
      setRuns(data || []);
    } catch (e) {
      console.error('Failed to load runs', e);
    }
  };

  const loadStatus = async () => {
    try {
      const data = await api.getStatus();
      const status = data.scraper_status;
      const latestRun = data.latest_run;
      if (status?.is_running && latestRun) {
        setIsRunning(true);
        setCurrentRun(latestRun);
        const scraped = latestRun.products_scraped || 0;
        const maxP = latestRun.max_products || 1;
        setPercentage(Math.min((scraped / maxP) * 100, 100));
      } else if (latestRun) {
        setCurrentRun(latestRun);
      }
    } catch (e) {
      console.error('Failed to load status', e);
    }
  };

  useEffect(() => {
    loadProducts(page, search, selectedRunId);
  }, [page, search, selectedRunId, loadProducts]);

  useEffect(() => {
    loadMetrics();
    loadStatus();
    loadRuns();
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (!isConnected && (isRunning || isAiRunning)) {
      interval = setInterval(() => {
        loadStatus();
        loadProducts(page, search, selectedRunId);
        loadMetrics();
        loadRuns();
      }, 4000);
    }
    return () => clearInterval(interval);
  }, [isConnected, isRunning, isAiRunning, page, search, selectedRunId, loadProducts]);

  useEffect(() => {
    if (!lastMessage) return;
    
    switch (lastMessage.type) {
      case 'job_started':
        setIsRunning(true);
        setSelectedRunId(lastMessage.run_id);
        setCurrentRun({
          id: lastMessage.run_id,
          status: 'running',
          max_products: lastMessage.max_products || 50,
          target_urls: lastMessage.urls || [],
          products_scraped: 0,
          products_failed: 0,
          products_discovered: 0,
          started_at: new Date().toISOString(),
          completed_at: null,
          error_message: null,
        });
        setPercentage(0);
        loadRuns();
        toast.success('Scrape job started');
        break;

      case 'progress':
        setCurrentRun(prev => prev ? {
          ...prev,
          products_scraped: lastMessage.products_scraped ?? prev.products_scraped,
          products_failed: lastMessage.products_failed ?? prev.products_failed,
          products_discovered: lastMessage.products_discovered ?? prev.products_discovered,
        } : null);
        if (typeof lastMessage.percentage === 'number') {
          setPercentage(lastMessage.percentage);
        }
        loadProducts(page, search, selectedRunId);
        break;

      case 'product_scraped':
        toast.info(`Scraped: ${lastMessage.product?.title?.substring(0, 30)}...`);
        loadProducts(page, search, selectedRunId);
        break;

      case 'product_failed':
        toast.warning(`Failed to scrape product: ${lastMessage.url}`);
        break;

      case 'job_completed':
        setIsRunning(false);
        setPercentage(100);
        setCurrentRun(prev => prev ? { ...prev, status: 'completed' } : null);
        loadMetrics();
        loadRuns();
        loadProducts(page, search, selectedRunId);
        toast.success('Scrape job completed');
        break;

      case 'job_stopped':
        setIsRunning(false);
        setCurrentRun(prev => prev ? { ...prev, status: 'stopped' } : null);
        loadRuns();
        toast.info('Scrape job stopped');
        break;

      case 'job_error':
        setIsRunning(false);
        setCurrentRun(prev => prev ? { ...prev, status: 'failed', error_message: lastMessage.error } : null);
        loadRuns();
        toast.error(`Job error: ${lastMessage.error || lastMessage.message || 'Unknown error'}`);
        break;

      case 'ai_started':
        setIsAiRunning(true);
        setAiProgress({ processed: 0, total: 0, percentage: 0 });
        toast.info('AI Extraction started');
        break;

      case 'ai_progress':
        setIsAiRunning(true);
        setAiProgress({
          processed: lastMessage.processed || 0,
          total: lastMessage.total || 0,
          percentage: lastMessage.percentage || 0,
          current_asin: lastMessage.current_asin,
        });
        break;

      case 'ai_completed':
        setIsAiRunning(false);
        setAiProgress({
          processed: lastMessage.count || 0,
          total: lastMessage.count || 0,
          percentage: 100,
          completed: true,
          count: lastMessage.count,
        });
        loadMetrics();
        toast.success('AI Extraction completed!');
        break;

      case 'ai_error':
        setIsAiRunning(false);
        setAiProgress({
          processed: 0,
          total: 0,
          percentage: 0,
          error: lastMessage.error || 'AI extraction failed',
        });
        toast.error(lastMessage.error || 'AI Extraction failed');
        break;
    }
  }, [lastMessage]);

  const handleStartScrape = async (maxProducts: number, urls: string[]) => {
    try {
      await api.startScrape(maxProducts, urls);
      toast.success('Starting scrape...');
    } catch (e: any) {
      toast.error(e.message || 'Failed to start scrape');
    }
  };

  const handleStopScrape = async () => {
    try {
      await api.stopScrape();
      toast.info('Stopping scrape...');
    } catch (e: any) {
      toast.error(e.message || 'Failed to stop scrape');
    }
  };

  const handleStartAi = async () => {
    try {
      setIsAiRunning(true);
      setAiProgress({ processed: 0, total: 0, percentage: 0 });
      await api.startAiExtraction(selectedRunId);
      toast.success('Starting AI extraction...');
    } catch (e: any) {
      setIsAiRunning(false);
      toast.error(e.message || 'Failed to start AI extraction');
    }
  };

  const handleExportCsv = () => {
    api.downloadCsv(selectedRunId);
    toast.success('Product CSV Download started');
  };

  const handleExportAiCsv = () => {
    api.downloadAiCsv(selectedRunId);
    toast.success('AI Attributes CSV Download started');
  };

  const handleClearHistory = async () => {
    await api.clearDatabase();
    setSelectedRunId('all');
    setCurrentRun(null);
    setPercentage(0);
    setAiProgress(null);
    await loadMetrics();
    await loadRuns();
    await loadProducts(1, '');
    toast.success('All history cleared from database');
  };

  return (
    <div className="min-h-screen bg-background text-foreground p-6 font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        <header className="flex items-center justify-between pb-4 border-b">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Amazon Scraper</h1>
            <p className="text-muted-foreground mt-1">Manage and monitor your Amazon scraping jobs & AI extraction.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Backend:</span>
            <Badge variant={isConnected ? 'default' : 'destructive'}>
              {connectionStatus}
            </Badge>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <ScraperForm 
              onStart={handleStartScrape} 
              onStop={handleStopScrape} 
              isRunning={isRunning} 
            />
            
            {currentRun && (
              <ProgressBar
                status={currentRun.status}
                percentage={percentage}
                scraped={currentRun.products_scraped}
                failed={currentRun.products_failed}
                discovered={currentRun.products_discovered}
                startedAt={currentRun.started_at}
              />
            )}
          </div>
          
          <div className="lg:col-span-1 space-y-6">
            <AiExtraction 
              isScraperRunning={isRunning}
              isAiRunning={isAiRunning}
              aiProgress={aiProgress}
              onStartAi={handleStartAi}
              onExportAiCsv={handleExportAiCsv}
            />
          </div>
        </div>

        <Separator className="my-8" />

        <div>
          <h2 className="text-2xl font-bold tracking-tight mb-4">Dashboard Metrics</h2>
          <MetricsCharts metrics={metrics} />
        </div>

        <Separator className="my-8" />

        <div>
          <ProductsTable 
            products={products}
            total={totalProducts}
            page={page}
            runs={runs}
            selectedRunId={selectedRunId}
            onRunChange={(runId) => { setSelectedRunId(runId); setPage(1); }}
            onPageChange={setPage}
            onSearch={(s) => { setSearch(s); setPage(1); }}
            onExportCsv={handleExportCsv}
            onExportAiCsv={handleExportAiCsv}
            onClearHistory={handleClearHistory}
            isLoading={isLoadingProducts}
            isScraperRunning={isRunning || isAiRunning}
          />
        </div>

      </div>
      <Toaster position="bottom-right" />
    </div>
  );
}
