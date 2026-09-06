// GitHub-style dangerous action confirmation modal requiring text entry.

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '~/components/ui/card';
import { Button } from '~/components/ui/button';
import { Input } from '~/components/ui/input';
import { Badge } from '~/components/ui/badge';

interface DeleteConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isClearing: boolean;
}

export function DeleteConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  isClearing,
}: DeleteConfirmationModalProps) {
  const [confirmationInput, setConfirmationInput] = useState('');
  const REQUIRED_TEXT = 'Delete all history';

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (confirmationInput === REQUIRED_TEXT) {
      onConfirm();
      setConfirmationInput('');
    }
  };

  const isMatched = confirmationInput === REQUIRED_TEXT;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <Card className="w-full max-w-md border-destructive/50 bg-background shadow-2xl">
        <CardHeader className="space-y-2 pb-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Badge variant="destructive" className="px-2 py-0.5 text-xs font-semibold uppercase tracking-wider">
              🚨 Dangerous Action
            </Badge>
          </div>
          <CardTitle className="text-xl font-bold text-destructive">
            Are you absolutely sure?
          </CardTitle>
          <p className="text-xs text-muted-foreground leading-relaxed">
            This action <strong className="text-foreground font-semibold">cannot be undone</strong>. This will permanently delete all scraped product data, failed items, scrape run history, and AI extracted attributes from the database.
          </p>
        </CardHeader>

        <CardContent className="space-y-4 pt-4">
          <div className="rounded-md bg-destructive/10 p-3 border border-destructive/20 text-xs text-destructive font-mono">
            Target: SQLite Database (scrapers/storage/scraper.db)
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-foreground block">
              To confirm, type <span className="font-bold font-mono text-destructive select-all">"{REQUIRED_TEXT}"</span> below:
            </label>
            <Input
              value={confirmationInput}
              onChange={(e) => setConfirmationInput(e.target.value)}
              placeholder={REQUIRED_TEXT}
              className="font-mono text-sm border-destructive/40 focus-visible:ring-destructive"
              autoFocus
            />
          </div>
        </CardContent>

        <CardFooter className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setConfirmationInput('');
              onClose();
            }}
            disabled={isClearing}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleConfirm}
            disabled={!isMatched || isClearing}
            className="font-semibold shadow-md"
          >
            {isClearing ? 'Clearing DB...' : 'I understand, clear all history'}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
