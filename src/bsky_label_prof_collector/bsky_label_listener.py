import csv
import os
from lib import constants
from atproto import parse_subscribe_labels_message, FirehoseSubscribeLabelsClient, models

#Fields to be extracted from the label object
LABEL_FIELDS = ['cts', 'uri', 'val', 'neg']

#Values of interest for the label's 'val' field
LABEL_VALS = ['rude', 'intolerant', 'extremist', 'intolerant-race', 'intolerant-gender',
                'intolerant-religion', 'intolerant-sexual-orientation', 'threat',
                'icon-intolerant', 'icon-nazi', 'rumor', 'misinformation', 'misleading']

def on_message_handler(message) -> None:
    """
    Handler function to process incoming label messages from the firehose
    
    Args:
        message: The incoming label message from the firehose
    
    Returns:
        None
    """
    #Parse the incoming label message
    mes = parse_subscribe_labels_message(message)

    if mes['labels']:
        label_obj = mes['labels'][0]
        label_dict = vars(label_obj)

        #Extract only the fields of interest, defaulting to empty string if not present
        filtered_dict = {field: label_dict.get(field, '') for field in LABEL_FIELDS}

        #If the label's 'val' field is in our list of values of interest, write it to the 'labels' file
        if(filtered_dict['val'] in LABEL_VALS):
            with open(constants.LABEL_CSV, mode='a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
                writer.writerow(filtered_dict)
        
        #Update the cursor file with the latest sequence number after processing the message
        with open(constants.LABEL_LISTENER_CURSOR, "w") as f:
            f.write(str(mes['seq']))
            f.flush()
            os.fsync(f.fileno())

def label_listen() -> None:
    """
    Function to start the label listener
    
    Args:
        None
    
    Returns:
        None
    """
    #Check if a cursor file exists to determine where to start listening from
    if os.path.exists(constants.LABEL_LISTENER_CURSOR):
        with open(constants.LABEL_LISTENER_CURSOR, "r") as f:
            cursor = int(f.read().strip())
    else:
        cursor = 0

    #If starting from the beginning, write the header to the 'labels' file
    if cursor == 0:
        with open(constants.LABEL_CSV, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
            writer.writeheader()

    #Start the firehose client to listen for label messages 
    print("LABEL: Starting firehose listener from cursor:", cursor)
    firehoseClient = FirehoseSubscribeLabelsClient(models.ComAtprotoLabelSubscribeLabels.Params(cursor= cursor))
    firehoseClient.start(on_message_handler)