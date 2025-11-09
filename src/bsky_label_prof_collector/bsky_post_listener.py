import csv
import os
import asyncio
from lib import constants
from atproto import AsyncFirehoseSubscribeReposClient, parse_subscribe_repos_message, CAR, models

POST_FIELDS = ['created_at', 'user_did']
LISTEN_SECS: float = 20
WAIT_SECS: float = 3600

async def on_message_handler(message) -> None:

    commit = parse_subscribe_repos_message(message)

    if not isinstance(commit, models.ComAtprotoSyncSubscribeRepos.Commit):
        return

    if not commit.blocks:
        return

    car = CAR.from_bytes(commit.blocks)

    for op in commit.ops:

        if op.action == 'create':
            if not op.cid:
                continue

            record_raw_data = car.blocks.get(op.cid)
            if not record_raw_data:
                continue

            record = models.get_or_create(record_raw_data, strict=False)
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

async def stop_after_n_sec(client):
    
    await asyncio.sleep(LISTEN_SECS)
    await client.stop()

async def post_listener():
    while True:
        client = AsyncFirehoseSubscribeReposClient()
        stop_after_n_sec_task = asyncio.create_task(stop_after_n_sec(client))
        if not os.path.exists(constants.POST_CSV):
            with open(constants.POST_CSV, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(POST_FIELDS)
        print("POST: Starting firehose listener...")
        await client.start(on_message_handler)
        await stop_after_n_sec_task
        print(f"POST: Waiting for { WAIT_SECS / 60} minutes...")
        await asyncio.sleep(WAIT_SECS)

def run_post_async(coro):
        asyncio.run(coro())