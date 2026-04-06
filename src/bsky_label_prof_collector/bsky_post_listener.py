import csv
import os
import asyncio
from lib import constants
from atproto import AsyncFirehoseSubscribeReposClient, parse_subscribe_repos_message, CAR, models

#Fields to be extracted from the post object
POST_FIELDS = ['created_at', 'user_did']

#Define the listen time and wait time here
LISTEN_SECS: float = 20
WAIT_SECS: float = 3600

#Async handler function to process incoming post messages from the firehose
async def on_message_handler(message) -> None:
    """
    Async handler function to process incoming post messages from the firehose
    
    Args:
        message: The incoming post message from the firehose
    
    Returns:
        None
    """
    #Parse the incoming post message
    commit = parse_subscribe_repos_message(message)

    #Only process the message if it contains a commit with blocks (i.e. new or updated records)
    if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
        return
    if not commit.blocks:
        return

    #Extract the CAR data from the commit
    car = CAR.from_bytes(commit.blocks)

    #Process each operation in the commit
    for op in commit.ops:

        #Only process 'create' operations, since we are only interested in new posts
        if op.action == 'create':
            #If the operation does not have a CID, skip it since we won't be able to retrieve the record data
            if not op.cid:
                continue

            #Retrieve the raw record data from the CAR using the CID, and parse it into a record object
            record_raw_data = car.blocks.get(op.cid)
            if not record_raw_data:
                continue

            #Use the atproto models to parse the raw record data into a record object
            record = models.get_or_create(record_raw_data, strict=False)

            #If the record is a post, extract the relevant fields and write them to the 'posts' file
            if record is not None and models.is_record_type(record, models.AppBskyFeedPost):
                with open(constants.POST_CSV, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([record.created_at, commit.repo])

# def post_listen():
#     if not os.path.exists(constants.POST_CSV):
#         with open(constants.POST_CSV, mode='w', newline='', encoding='utf-8') as f:
#             writer = csv.writer(f)
#             writer.writerow(POST_FIELDS)
    
#     firehoseClient = FirehoseSubscribeReposClient()
#     firehoseClient.start(on_message_handler)

async def stop_after_n_sec(client) -> None:
    """
    Async function to stop the listener after a certain number of seconds
    
    Args:
        client: The firehose client that is currently listening for new posts
    
    Returns:
        None
    """
    await asyncio.sleep(LISTEN_SECS)
    await client.stop()

async def post_listener() -> None:
    """
    Async function to listen for new posts and save relevant data
    
    Args:
        None
    
    Returns:
        None
    """
    while True:

        client = AsyncFirehoseSubscribeReposClient()
        #Create a task to stop the listener after a certain number of seconds
        stop_after_n_sec_task = asyncio.create_task(stop_after_n_sec(client))

        #Ensure the 'posts' file exists and has the header before starting to listen
        if not os.path.exists(constants.POST_CSV):
            with open(constants.POST_CSV, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(POST_FIELDS)

        #Start listening for new posts for a certain number of seconds, then stop and wait before starting again
        print("POST: Starting firehose listener...")
        await client.start(on_message_handler)
        await stop_after_n_sec_task
        print(f"POST: Waiting for { WAIT_SECS / 60} minutes...")
        await asyncio.sleep(WAIT_SECS)

def run_post_async(coro) -> None:
    """
    Helper function to run the async post listener in a separate thread
    
    Args:
        coro: The post listener coroutine to be run in a separate thread
    
    Returns:
        None
    """
    asyncio.run(coro())