// Scraper configuration form component with Zod validation.

import { useState } from 'react';
import { z } from 'zod';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '~/components/ui/card';
import { Input } from '~/components/ui/input';
import { Label } from '~/components/ui/label';
import { Button } from '~/components/ui/button';

const scrapeSchema = z.object({
  maxProducts: z.number().int().min(1).max(1000),
  urls: z.array(z.string().url().refine(url => url.startsWith('https://www.amazon.com/s'), {
    message: 'Must be a valid Amazon search URL (https://www.amazon.com/s...)'
  })).min(1, 'At least one URL required').max(10, 'Maximum 10 URLs'),
});

interface ScraperFormProps {
  onStart: (maxProducts: number, urls: string[]) => void;
  onStop: () => void;
  isRunning: boolean;
}

export function ScraperForm({ onStart, onStop, isRunning }: ScraperFormProps) {
  const [maxProducts, setMaxProducts] = useState<number>(50);
  const [urls, setUrls] = useState<string[]>(['']);
  const [errors, setErrors] = useState<{ maxProducts?: string, urls?: string[] }>({});

  const handleAddUrl = () => {
    if (urls.length < 10) setUrls([...urls, '']);
  };

  const handleRemoveUrl = (index: number) => {
    setUrls(urls.filter((_, i) => i !== index));
  };

  const handleUrlChange = (index: number, value: string) => {
    const newUrls = [...urls];
    newUrls[index] = value;
    setUrls(newUrls);
  };

  const handleStart = () => {
    try {
      scrapeSchema.parse({ maxProducts, urls });
      setErrors({});
      onStart(maxProducts, urls.filter(u => u.trim() !== ''));
    } catch (e) {
      if (e instanceof z.ZodError) {
        const fieldErrors: any = {};
        const urlErrors: string[] = [];
        e.issues.forEach((err: z.ZodIssue) => {
          if (err.path[0] === 'maxProducts') fieldErrors.maxProducts = err.message;
          if (err.path[0] === 'urls') {
            if (typeof err.path[1] === 'number') {
              urlErrors[err.path[1]] = err.message;
            } else {
              fieldErrors.urls = err.message;
            }
          }
        });
        setErrors({ ...fieldErrors, urls: urlErrors.length > 0 ? urlErrors : undefined });
        toast.error('Please fix the form errors');
      }
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Scraper Configuration</CardTitle>
        <CardDescription>Set up the target URLs and parameters for scraping.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="maxProducts">Max Products to Scrape</Label>
          <Input 
            id="maxProducts" 
            type="number" 
            value={maxProducts}
            onChange={e => setMaxProducts(Number(e.target.value))}
            disabled={isRunning}
          />
          {errors.maxProducts && <p className="text-sm text-destructive text-red-500">{errors.maxProducts}</p>}
        </div>

        <div className="space-y-2">
          <Label>Target Amazon Search URLs</Label>
          {urls.map((url, index) => (
            <div key={index} className="flex gap-2 items-start">
              <div className="flex-1 space-y-1">
                <Input
                  value={url}
                  placeholder="https://www.amazon.com/s?k=laptop"
                  onChange={e => handleUrlChange(index, e.target.value)}
                  disabled={isRunning}
                />
                {errors.urls?.[index] && (
                  <p className="text-sm text-destructive text-red-500">{errors.urls[index]}</p>
                )}
              </div>
              <Button 
                variant="destructive" 
                size="icon" 
                onClick={() => handleRemoveUrl(index)}
                disabled={urls.length === 1 || isRunning}
              >
                X
              </Button>
            </div>
          ))}
          <Button 
            variant="outline" 
            onClick={handleAddUrl} 
            disabled={urls.length >= 10 || isRunning}
            className="mt-2"
          >
            + Add URL
          </Button>
        </div>

        <div className="pt-4 flex gap-4">
          <Button 
            className="flex-1" 
            onClick={handleStart} 
            disabled={isRunning}
          >
            Start Scrape
          </Button>
          {isRunning && (
            <Button 
              variant="destructive" 
              className="flex-1" 
              onClick={onStop}
            >
              Stop Scrape
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
