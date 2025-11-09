from src.bsky_label_prof_collector.bsky_label_listener import label_listen
from src.bsky_label_prof_collector.bsky_post_listener import post_listener, run_post_async
from src.bsky_label_prof_collector.bsky_did_extractor import schedule_did_extraction
from src.bsky_label_prof_collector.bsky_prof_extractor import extract_profiles
from concurrent.futures import ThreadPoolExecutor

def main():

    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.submit(label_listen)
        executor.submit(run_post_async, post_listener)
        executor.submit(schedule_did_extraction)
        executor.submit(extract_profiles)

        print("MAIN: All threads started.")

        # Keeps main alive while threads run forever
        try:
            executor.shutdown(wait=True)
        except KeyboardInterrupt:
            print("\nStopping all threads...")

if __name__ == "__main__":
    main()
