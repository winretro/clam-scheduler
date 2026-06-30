import sys
import time
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .logger import logger
from .auth import verify_admin
from .database import DatabaseManager
from .scanner import trigger_managed_scan, trigger_update_defs
from .state import is_scan_running

# The scheduler instance MUST be declared globally
scheduler = BackgroundScheduler()
scheduler.start()

def execute_schedule_sequence(schedule_id, tasks, trigger_source="Scheduled"):
    logger.info(f"Executing sequence for schedule {schedule_id}")
    for task in tasks:
        action = task.get('action_type')
        payload = task.get('payload')
        
        try:
            if action == 'start_scan':
                logger.info(f"Sequence task: start_scan on {payload}")
                trigger_managed_scan(payload, trigger_source)
                # Wait for the background scan thread to finish before proceeding
                time.sleep(2)
                while is_scan_running():
                    time.sleep(5)
                    
            elif action == 'update_defs':
                logger.info("Sequence task: update_defs")
                trigger_update_defs(trigger_source)
                
        except Exception as e:
            logger.error(f"Error in schedule sequence task {action}: {e}")

def sync_scheduler():
    logger.info("--- RUNNING sync_scheduler() ON STARTUP ---")
    scheduler.remove_all_jobs()
    
    db = DatabaseManager()
    schedules = db.get_schedules()
    
    for sched in schedules:
        if sched.get('enabled') != 1:
            continue
            
        try:
            tasks = db.get_schedule_tasks(sched['id'])
            if not tasks:
                logger.debug(f"Skipping schedule {sched['id']}: no tasks found.")
                continue

            cron_string = sched['cron_spec']
            cron_trigger = CronTrigger.from_crontab(cron_string)
            
            scheduler.add_job(
                execute_schedule_sequence,
                trigger=cron_trigger,
                args=[sched['id'], tasks, "Scheduled"],
                id=str(sched['id']),
                replace_existing=True
            )
        except Exception as e:
            logger.error(f"Failed to load schedule {sched['id']} (Cron: {sched.get('cron_spec')}): {e}")

    logger.debug(f"--- ACTIVE SCHEDULED JOBS: {scheduler.get_jobs()} ---")

if __name__ == "__main__":
    if len(sys.argv) == 3:
        print(verify_admin(sys.argv[1], sys.argv[2]))
    else:
        sync_scheduler()
        logger.info("Module 5 Service Active on Port 3360...")
        while True: time.sleep(1)
