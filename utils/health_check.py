"""
Health Check - System health monitoring
"""

import asyncio
import os
from typing import Dict
from datetime import datetime
from database.db import AsyncSessionLocal
from workers.email_worker import email_worker
from workers.followup_worker import followup_worker


class HealthCheck:
    """System health monitoring"""
    
    async def check_database(self) -> Dict:
        """Check database connectivity"""
        try:
            async with AsyncSessionLocal() as session:
                # Try a simple query
                result = await session.execute("SELECT 1")
                result.fetchone()
                
                return {
                    'status': 'healthy',
                    'latency_ms': 0,  # Could measure actual latency
                    'message': 'Database connection OK'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Database connection failed'
            }
    
    async def check_ollama(self) -> Dict:
        """Check Ollama LLM service"""
        try:
            import requests
            response = requests.get(
                'http://localhost:11434/api/tags',
                timeout=5
            )
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                return {
                    'status': 'healthy',
                    'models': [m['name'] for m in models],
                    'message': 'Ollama service OK'
                }
            else:
                return {
                    'status': 'degraded',
                    'message': 'Ollama responding but unexpected status'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Ollama service not responding'
            }
    
    async def check_email_worker(self) -> Dict:
        """Check email worker status"""
        try:
            status = email_worker.get_status()
            
            if status['running']:
                return {
                    'status': 'healthy',
                    'last_check': status.get('last_check'),
                    'message': 'Email worker running'
                }
            else:
                return {
                    'status': 'unhealthy',
                    'message': 'Email worker not running'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Email worker check failed'
            }
    
    async def check_followup_worker(self) -> Dict:
        """Check follow-up worker status"""
        try:
            status = followup_worker.get_status()
            
            if status['running']:
                return {
                    'status': 'healthy',
                    'message': 'Follow-up worker running'
                }
            else:
                return {
                    'status': 'unhealthy',
                    'message': 'Follow-up worker not running'
                }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'message': 'Follow-up worker check failed'
            }
    
    async def check_disk_space(self) -> Dict:
        """Check disk space"""
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            
            free_percent = (free / total) * 100
            
            if free_percent < 10:
                status = 'unhealthy'
                message = f'Low disk space: {free_percent:.1f}% free'
            elif free_percent < 20:
                status = 'degraded'
                message = f'Disk space getting low: {free_percent:.1f}% free'
            else:
                status = 'healthy'
                message = f'Disk space OK: {free_percent:.1f}% free'
            
            return {
                'status': status,
                'total_gb': total // (2**30),
                'used_gb': used // (2**30),
                'free_gb': free // (2**30),
                'free_percent': round(free_percent, 1),
                'message': message
            }
        except Exception as e:
            return {
                'status': 'unknown',
                'error': str(e),
                'message': 'Disk space check failed'
            }
    
    async def check_all(self) -> Dict:
        """Run all health checks"""
        checks = await asyncio.gather(
            self.check_database(),
            self.check_ollama(),
            self.check_email_worker(),
            self.check_followup_worker(),
            self.check_disk_space(),
            return_exceptions=True
        )
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'checks': {
                'database': checks[0],
                'ollama': checks[1],
                'email_worker': checks[2],
                'followup_worker': checks[3],
                'disk_space': checks[4]
            }
        }
        
        # Determine overall status
        statuses = [
            check.get('status', 'unknown') 
            for check in result['checks'].values()
            if isinstance(check, dict)
        ]
        
        if 'unhealthy' in statuses:
            result['overall_status'] = 'unhealthy'
        elif 'degraded' in statuses:
            result['overall_status'] = 'degraded'
        else:
            result['overall_status'] = 'healthy'
        
        return result


# Singleton instance
health_check = HealthCheck()