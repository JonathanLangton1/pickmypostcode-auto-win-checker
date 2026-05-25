"""Daily scheduler — runs the lottery checker every day at RUN_TIME (container local time)."""
import time
import schedule
from run import main, RUN_TIME

print(f"Scheduler started — will run daily at {RUN_TIME}.", flush=True)
schedule.every().day.at(RUN_TIME).do(main)

while True:
    schedule.run_pending()
    time.sleep(30)
