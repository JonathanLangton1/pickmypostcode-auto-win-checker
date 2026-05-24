"""Daily scheduler — runs the lottery checker every day at 14:00."""
import time
import schedule
from run import main

RUN_TIME = "14:00"

print(f"Scheduler started — will run daily at {RUN_TIME}.", flush=True)
schedule.every().day.at(RUN_TIME).do(main)

while True:
    schedule.run_pending()
    time.sleep(30)
