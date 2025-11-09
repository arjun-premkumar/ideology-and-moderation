import csv
import os
import time
import pandas as pd
from lib import constants
from atproto import AtUri

SLEEP_SECS = 600

def extract_dids():

    labels_df = pd.read_csv(constants.LABEL_CSV)
    posts_df = pd.read_csv(constants.POST_CSV)
    exist_label_did_set = set()
    exist_post_did_set = set()
    
    if os.path.exists(constants.DID_CSV):
        did_df = pd.read_csv(constants.DID_CSV, header=None, names=['DID','labelled'])
        exist_label_did_set = set(did_df[did_df['labelled'] == 1]['DID'].tolist())
        exist_post_did_set = set(did_df[did_df['labelled'] == 0]['DID'].tolist())
        
    labels_df['DID'] = [AtUri.from_str(uri).host for uri in labels_df['uri']]
    label_did_set = set(labels_df['DID'])
    neg_label_did_set = set(labels_df[labels_df['neg'] == True]['DID'])
    label_did_set = label_did_set.difference(neg_label_did_set)

    post_did_set = set(posts_df['user_did'])
    post_did_set = post_did_set.difference(label_did_set)

    with open(constants.DID_CSV, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for did in post_did_set:
            if did not in exist_post_did_set:
                writer.writerow([did, 0])
        for did in label_did_set:
            if did not in exist_label_did_set:
                writer.writerow([did, 1])
def schedule_did_extraction():
    while True:
        print("DID_EXTRACT: Sleeping for", SLEEP_SECS/60 , "minutes...")    
        time.sleep(SLEEP_SECS)
        extract_dids()
        print("DID_EXTRACT: DIDs extracted.")