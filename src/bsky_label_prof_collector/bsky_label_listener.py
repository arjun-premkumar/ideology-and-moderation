import csv
import os
import asyncio
from lib import constants
from atproto import parse_subscribe_labels_message, FirehoseSubscribeLabelsClient, models

LABEL_FIELDS = ['cts', 'uri', 'val', 'neg']
LABEL_VALS = ['rude', 'intolerant', 'extremist', 'intolerant-race', 'intolerant-gender',
                'intolerant-religion', 'intolerant-sexual-orientation', 'threat',
                'icon-intolerant', 'icon-nazi', 'rumor', 'misinformation', 'misleading']

def on_message_handler(message) -> None:
    
    mes = parse_subscribe_labels_message(message)

    if mes['labels']:
        label_obj = mes['labels'][0]
        label_dict = vars(label_obj)

        filtered_dict = {field: label_dict.get(field, '') for field in LABEL_FIELDS}

        if(filtered_dict['val'] in LABEL_VALS):
            with open(constants.LABEL_CSV, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
                writer.writerow(filtered_dict)
        with open(constants.LABEL_LISTENER_CURSOR, "w") as f:
            f.write(str(mes['seq']))
            f.flush()
            os.fsync(f.fileno())

def label_listen():
    if os.path.exists(constants.LABEL_LISTENER_CURSOR):
        with open(constants.LABEL_LISTENER_CURSOR, "r") as f:
            cursor = int(f.read().strip())
    else:
        cursor = 0

    if cursor == 0:
        with open(constants.LABEL_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
            writer.writeheader()
    print("LABEL: Starting firehose listener from cursor:", cursor)
    firehoseClient = FirehoseSubscribeLabelsClient(models.ComAtprotoLabelSubscribeLabels.Params(cursor= cursor))
    firehoseClient.start(on_message_handler)