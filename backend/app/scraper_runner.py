# Subprocess manager for Scrapy crawling and AI extraction tasks.

import asyncio
import subprocess
import os
import sys
import logging
from pathlib import Path
from typing import List, Optional
from .websocket_manager import manager
from . import database

logger = logging.getLogger("backend.scraper_runner")

class ScraperRunner:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.current_run_id: Optional[str] = None
        self._is_running: bool = False
        self.manager = manager
        
        root_dir = Path(__file__).resolve().parent.parent.parent
        scrapers_venv = root_dir / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        self.python_exec = str(scrapers_venv) if scrapers_venv.exists() else sys.executable
        self.cwd = str(root_dir / "scrapers")

    @property
    def is_running(self) -> bool:
        if self._is_running:
            if self.process is not None:
                poll = self.process.poll()
                if poll is not None:
                    self._is_running = False
        return self._is_running

    async def start(self, run_id: str, max_products: int, urls: List[str]):
        if self.is_running:
            raise Exception("Scraper is already running")
            
        self._is_running = True
        self.current_run_id = run_id
        
        try:
            await database.create_run(run_id, max_products, urls)
            await database.update_run_status(run_id, 'running')
            
            cmd = [self.python_exec, "run.py", "--run-id", run_id, "--max-products", str(max_products), "--urls"] + urls
            logger.info(f"Spawning scraper: {cmd} in {self.cwd}")
            
            self.process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            await self.manager.broadcast({
                'type': 'job_started',
                'run_id': run_id,
                'max_products': max_products,
                'urls': urls
            })
            
            asyncio.create_task(self._monitor_process(run_id, max_products))
        except Exception as e:
            logger.error(f"Error starting scraper process: {e}", exc_info=True)
            self._is_running = False
            self.current_run_id = None
            self.process = None
            try:
                await database.update_run_status(run_id, 'failed', error_message=str(e))
            except Exception:
                pass
            raise

    async def stop(self):
        if not self.is_running or not self.process:
            self._is_running = False
            self.current_run_id = None
            self.process = None
            return
            
        try:
            self.process.terminate()
        except Exception:
            pass
            
        run_id = self.current_run_id
        if run_id:
            await database.update_run_status(run_id, 'stopped')
            await self.manager.broadcast({
                'type': 'job_stopped',
                'run_id': run_id
            })
        
        self._is_running = False
        self.current_run_id = None
        self.process = None

    async def _monitor_process(self, run_id: str, max_products: int):
        proc = self.process
        if not proc:
            return

        try:
            while True:
                poll = proc.poll()
                if poll is not None:
                    break
                    
                run_data = await database.get_run(run_id)
                if run_data:
                    scraped = run_data.get('products_scraped', 0)
                    failed = run_data.get('products_failed', 0)
                    discovered = run_data.get('products_discovered', 0)
                    
                    percentage = (scraped / max_products) * 100 if max_products > 0 else 0
                    
                    await self.manager.broadcast({
                        'type': 'progress',
                        'run_id': run_id,
                        'products_scraped': scraped,
                        'products_failed': failed,
                        'products_discovered': discovered,
                        'percentage': percentage
                    })
                    
                await asyncio.sleep(2)
                
            returncode = proc.poll()
            run_data = await database.get_run(run_id)
            total_scraped = run_data.get('products_scraped', 0) if run_data else 0
            total_failed = run_data.get('products_failed', 0) if run_data else 0
            
            if returncode == 0:
                await database.update_run_status(run_id, 'completed')
                await self.manager.broadcast({
                    'type': 'job_completed',
                    'run_id': run_id,
                    'total_scraped': total_scraped,
                    'total_failed': total_failed
                })
            else:
                stderr_bytes = await asyncio.to_thread(proc.stderr.read) if proc.stderr else b""
                error_msg = stderr_bytes.decode('utf-8', errors='replace').strip() if stderr_bytes else f"Process exited with code {returncode}"
                logger.error(f"Scraper process failed (code {returncode}): {error_msg}")
                await database.update_run_status(run_id, 'failed', error_message=error_msg)
                await self.manager.broadcast({
                    'type': 'job_error',
                    'run_id': run_id,
                    'error': error_msg
                })
                
        except Exception as e:
            logger.error(f"Error in _monitor_process: {e}", exc_info=True)
            await database.update_run_status(run_id, 'failed', error_message=str(e))
            await self.manager.broadcast({
                'type': 'job_error',
                'run_id': run_id,
                'error': str(e)
            })
        finally:
            self._is_running = False
            self.current_run_id = None
            self.process = None

    async def start_ai_extraction(self, run_id: Optional[str] = None):
        if self.is_running:
            raise Exception("Scraper or AI task is already running")
            
        self._is_running = True
        target_id = run_id if (run_id and run_id != "all") else "all"
        self.current_run_id = target_id
        main_loop = asyncio.get_running_loop()
        
        try:
            cmd = [self.python_exec, "run.py", "--ai-only"]
            if run_id and run_id != "all":
                cmd.extend(["--run-id", run_id])
                
            logger.info(f"Spawning AI extraction: {cmd} in {self.cwd}")
            
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            self.process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env
            )
            
            await self.manager.broadcast({
                'type': 'ai_started',
                'run_id': target_id
            })
            
            asyncio.create_task(self._monitor_ai_process(target_id, main_loop))
        except Exception as e:
            logger.error(f"Error starting AI extraction: {e}", exc_info=True)
            self._is_running = False
            self.current_run_id = None
            self.process = None
            raise

    async def _monitor_ai_process(self, run_id: str, main_loop: asyncio.AbstractEventLoop):
        proc = self.process
        if not proc:
            return

        try:
            total_items = 0
            processed_items = 0
            error_line = ""

            def read_stdout():
                nonlocal total_items, processed_items, error_line
                if not proc.stdout:
                    return
                for line in proc.stdout:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    logger.info(f"[AI Process] {line_str}")
                    
                    if line_str.startswith("[AI_STARTED]"):
                        try:
                            total_items = int(line_str.split("total=")[1])
                            asyncio.run_coroutine_threadsafe(
                                self.manager.broadcast({
                                    'type': 'ai_progress',
                                    'run_id': run_id,
                                    'processed': 0,
                                    'total': total_items,
                                    'percentage': 0,
                                    'current_asin': 'Initializing...'
                                }),
                                main_loop
                            )
                        except Exception as ex:
                            logger.warning(f"Error parsing AI_STARTED line: {ex}")
                    elif line_str.startswith("[AI_PROGRESS]"):
                        try:
                            parts = line_str.split()
                            counts = parts[1].split('/')
                            p_num = int(counts[0])
                            t_num = int(counts[1])
                            asin_part = [p for p in parts if p.startswith("ASIN:")][0].replace("ASIN:", "") if any(p.startswith("ASIN:") for p in parts) else ""
                            percentage = round((p_num / t_num) * 100, 1) if t_num > 0 else 0
                            
                            asyncio.run_coroutine_threadsafe(
                                self.manager.broadcast({
                                    'type': 'ai_progress',
                                    'run_id': run_id,
                                    'processed': p_num,
                                    'total': t_num,
                                    'percentage': percentage,
                                    'current_asin': asin_part
                                }),
                                main_loop
                            )
                        except Exception as ex:
                            logger.warning(f"Error parsing AI progress line: {ex}")
                    elif line_str.startswith("[AI_ERROR]"):
                        error_line = line_str.replace("[AI_ERROR]", "").strip()

            await asyncio.to_thread(read_stdout)
            
            returncode = proc.wait()
            if returncode == 0 and not error_line:
                ai_count = await database.get_ai_attributes_count(run_id)
                await self.manager.broadcast({
                    'type': 'ai_completed',
                    'run_id': run_id,
                    'success': True,
                    'count': ai_count
                })
            else:
                stderr_text = ""
                if proc.stderr:
                    stderr_text = await asyncio.to_thread(proc.stderr.read)
                msg = error_line or stderr_text.strip() or f"Process exited with code {returncode}"
                logger.error(f"AI Extraction failed (code {returncode}): {msg}")
                await self.manager.broadcast({
                    'type': 'ai_error',
                    'run_id': run_id,
                    'error': msg
                })
        except Exception as e:
            logger.error(f"Error in _monitor_ai_process: {e}", exc_info=True)
            await self.manager.broadcast({
                'type': 'ai_error',
                'run_id': run_id,
                'error': str(e)
            })
        finally:
            self._is_running = False
            self.current_run_id = None
            self.process = None

    def get_status(self):
        return {
            'is_running': self.is_running,
            'current_run_id': self.current_run_id
        }

runner = ScraperRunner()
