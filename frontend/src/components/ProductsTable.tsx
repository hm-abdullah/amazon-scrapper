// Paginated products data table with search filtering and CSV exports.

import { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '~/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '~/components/ui/table';
import { Input } from '~/components/ui/input';
import { Button } from '~/components/ui/button';
import { Badge } from '~/components/ui/badge';
import { DeleteConfirmationModal } from '~/components/DeleteConfirmationModal';
import type { Product, ScrapeRun } from '~/lib/types';

interface ProductsTableProps {
  products: Product[];
  total: number;
  page: number;
  runs: ScrapeRun[];
  selectedRunId: string;
  onRunChange: (runId: string) => void;
  onPageChange: (page: number) => void;
  onSearch: (search: string) => void;
  onExportCsv: () => void;
  onExportAiCsv: () => void;
  onClearHistory: () => Promise<void>;
  isLoading: boolean;
  isScraperRunning: boolean;
}

export function ProductsTable({
  products,
  total,
  page,
  runs,
  selectedRunId,
  onRunChange,
  onPageChange,
  onSearch,
  onExportCsv,
  onExportAiCsv,
  onClearHistory,
  isLoading,
  isScraperRunning,
}: ProductsTableProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const delay = setTimeout(() => {
      onSearch(searchTerm);
    }, 400);
    return () => clearTimeout(delay);
  }, [searchTerm]);

  const handleConfirmClear = async () => {
    setIsClearing(true);
    try {
      await onClearHistory();
      setIsDeleteModalOpen(false);
    } finally {
      setIsClearing(false);
    }
  };

  const truncate = (str: string | null, len: number) => {
    if (!str) return 'N/A';
    return str.length > len ? str.substring(0, len) + '...' : str;
  };

  const totalPages = Math.ceil(total / 50);

  return (
    <>
      <Card className="w-full">
        <CardHeader className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <CardTitle className="text-xl">Scraped Products ({total})</CardTitle>
            <p className="text-xs text-muted-foreground mt-1">Filter by scrape run or search products.</p>
          </div>

          <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
            <select
              value={selectedRunId}
              onChange={(e) => onRunChange(e.target.value)}
              className="h-9 px-3 py-1 rounded-md border bg-background text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="all">All Scrape Runs</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  Run {r.id.substring(0, 8)} ({r.products_scraped} items - {r.started_at ? new Date(r.started_at).toLocaleTimeString() : 'N/A'})
                </option>
              ))}
            </select>

            <Input 
              className="max-w-xs h-9" 
              placeholder="Search title, ASIN, brand..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />

            <Button 
              variant="default" 
              size="sm" 
              onClick={onExportCsv}
              className="h-9 gap-1"
            >
              📥 Export CSV
            </Button>

            <Button 
              variant="secondary" 
              size="sm" 
              onClick={onExportAiCsv}
              className="h-9 gap-1"
            >
              ✨ Export AI CSV
            </Button>

            <Button 
              variant="outline" 
              size="sm" 
              onClick={() => setIsDeleteModalOpen(true)}
              disabled={isScraperRunning}
              className="h-9 text-destructive border-destructive/40 hover:bg-destructive/10 gap-1 font-semibold"
            >
              🗑️ Clear History
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          <div className="rounded-md border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ASIN</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Brand</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Rating</TableHead>
                  <TableHead>Availability</TableHead>
                  <TableHead>Scraped At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {products.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                      {isLoading ? 'Loading products...' : 'No products found.'}
                    </TableCell>
                  </TableRow>
                ) : (
                  products.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono font-medium">{p.asin}</TableCell>
                      <TableCell title={p.title || ''}>{truncate(p.title, 50)}</TableCell>
                      <TableCell>{p.brand || <Badge variant="secondary" className="text-muted-foreground">N/A</Badge>}</TableCell>
                      <TableCell className="font-mono">
                        {p.price !== null ? `$${p.price.toFixed(2)}` : <Badge variant="secondary" className="text-muted-foreground">N/A</Badge>}
                      </TableCell>
                      <TableCell>
                        {p.rating !== null ? `${p.rating}/5.0` : <Badge variant="secondary" className="text-muted-foreground">N/A</Badge>}
                      </TableCell>
                      <TableCell>{p.availability || <Badge variant="secondary" className="text-muted-foreground">N/A</Badge>}</TableCell>
                      <TableCell className="text-xs text-muted-foreground font-mono">
                        {p.scraped_at ? new Date(p.scraped_at).toLocaleString() : 'N/A'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between py-4">
            <div className="text-xs text-muted-foreground">
              Showing page {page} of {totalPages || 1} ({total} total products)
            </div>
            <div className="flex items-center space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(page - 1)}
                disabled={page <= 1 || isLoading}
              >
                Previous
              </Button>
              <div className="text-sm font-medium px-2">Page {page}</div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPageChange(page + 1)}
                disabled={page >= totalPages || isLoading}
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <DeleteConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleConfirmClear}
        isClearing={isClearing}
      />
    </>
  );
}
