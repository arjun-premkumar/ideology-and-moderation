import csv
import os
import time
import pandas as pd
from lib import constants
from atproto import AtUri

#Define the sleep time between each DID extraction cycle (in seconds)
SLEEP_SECS = 600

def extract_dids() -> None:
    """
    Extract DIDs from the collected labels and posts
    
    Args:
        None
    
    Returns:
        None
    """
    #Read the collected labels and posts from their respective CSV files
    labels_df = pd.read_csv(constants.LABEL_CSV)
    posts_df = pd.read_csv(constants.POST_CSV)
    
    exist_label_did_set = set()
    exist_post_did_set = set()
    
    #If a DID file already exists, get the already extracted DIDs
    if os.path.exists(constants.DID_CSV):
        did_df = pd.read_csv(constants.DID_CSV, header=None, names=['DID','labelled'])
        exist_label_did_set = set(did_df[did_df['labelled'] == 1]['DID'].tolist())
        exist_post_did_set = set(did_df[did_df['labelled'] == 0]['DID'].tolist())

    #Extract the DID from the labels, and remove any DIDs whose label has been negated
    labels_df['DID'] = [AtUri.from_str(uri).host for uri in labels_df['uri']]
    label_did_set = set(labels_df['DID'])
    neg_label_did_set = set(labels_df[labels_df['neg'] == True]['DID'])
    label_did_set = label_did_set.difference(neg_label_did_set)

    #Extract the DID from the posts, and remove any DIDs which appear in the labels
    post_did_set = set(posts_df['user_did'])
    post_did_set = post_did_set.difference(label_did_set)

    #Write the extracted DIDs, along with a 'labelled' flag
    with open(constants.DID_CSV, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for did in post_did_set:
            if did not in exist_post_did_set:
                writer.writerow([did, 0])
        for did in label_did_set:
            if did not in exist_label_did_set:
                writer.writerow([did, 1])

def schedule_did_extraction() -> None:
    """
    Periodically extract DIDs from the collected labels and posts
    
    Args:
        None
    
    Returns:
        None
    """
    while True:
        print("DID_EXTRACT: Sleeping for", SLEEP_SECS/60 , "minutes...")    
        time.sleep(SLEEP_SECS)
        extract_dids()
        print("DID_EXTRACT: DIDs extracted.")