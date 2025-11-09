from atproto import Client
from tqdm import tqdm
import re
import pandas as pd
from urllib.parse import urlparse
import numpy as np
from atproto import exceptions
import csv
import logging
import os
import requests
import time
from dateutil import parser
from datetime import timezone
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from textblob import TextBlob
from lib import constants

DATA_COLUMNS = ['DID', 'pol_score', 'language','posts_num','links_num','follow_ratio','sentiment','activity_life_sec','burstiness_index']
BATCH_SIZE = 100
SLEEP_SECS = 660
DetectorFactory.seed = 0

logging.basicConfig(filename=constants.ERROR_LOG, level=logging.ERROR, format='%(asctime)s - %(message)s')

client = Client()
client.login('testerofbluesky@gmail.com', '65Bstest@Gammaburst')
mbfc_df = pd.read_csv(constants.MBFC_CSV)

def extract_news_link_pol_score(text: str):

    url_pattern = r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d{2,5})?(?:/[^\s]*)?'
    matches = re.findall(url_pattern, text)
    for url in matches:
        try:
            response = requests.get(url, allow_redirects=True, timeout=20)
            url = response.url
        except requests.RequestException as e:
            logging.error(f"Error expanding URL ({type(e).__name__}): {str(e)}")
            continue
        
        parsed = urlparse(url)
        netloc = parsed.netloc.replace("www.", "")
        domain_parts = netloc.split(".")
        match_domain = domain_parts[-2] if len(domain_parts) >= 2 else netloc
        # Find the exact match in MBFC
        for domain in mbfc_df['sourcedomain']:
            if domain == match_domain:
                score = float(mbfc_df[mbfc_df['sourcedomain'] == domain]['political_level'].iloc[0])
                return score, domain

    return None, None

def identify_language(text):
    try:
        language_code = detect(text)
        return language_code
    except LangDetectException:
        return "Could not detect language"

def burstiness_index(timestamps):
    """
    Compute the coefficient of variation (CV) of inter-post times.
    
    Args:
        timestamps (list): List of datetime objects (or ISO8601 strings).
    
    Returns:
        float: CV value (σ/μ) or None if insufficient data.
    """
    # Convert strings to datetime and force UTC
    parsed = []
    for ts in timestamps:
        if isinstance(ts, str):
            dt = parser.isoparse(ts)
        else:
            dt = ts
        # Ensure UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        parsed.append(dt)

    # Sort timestamps (most recent APIs return reverse chronological order)
    parsed = sorted(parsed)

    # Compute inter-post intervals in seconds
    intervals = np.diff([ts.timestamp() for ts in parsed])
    life = parsed[-1].timestamp() - parsed[0].timestamp()

    if len(intervals) < 2:
        return None  # not enough data

    mu = np.mean(intervals)
    sigma = np.std(intervals)

    burst = (sigma - mu) / (sigma + mu) if mu > 0 else None

    return life, burst

def bio_sentiment_textblob(description: str):
    """
    Compute sentiment polarity score of a Bluesky bio using TextBlob.
    
    Args:
        description (str): Profile description text.
    
    Returns:
        float: Polarity score in range [-1.0, 1.0]
            (-1 very negative, 0 neutral, +1 very positive)
    """
    if not description:
        return 0.0  # treat empty bios as neutral
    
    analysis = TextBlob(description)
    return analysis.sentiment.polarity

def process_did(did):

    all_posts = []
    timestamps = []
    results = []
    cursor = None
    try:
        profileViewResult = client.get_profile(did)
    except exceptions.BadRequestError as e:
        print(f"Request Exception for DID {did} ({type(e).__name__}): {str(e)}")
    except Exception as e:
        return
    while True:
        try:
            data = client.get_author_feed(
                actor=did,
                filter='posts_no_replies',
                limit=100,
                cursor=cursor
            )
            feed = data.feed
            posts_ts = [(content.post.record.text, content.post.record.created_at) for content in feed
                        if hasattr(content.post.record, 'text') and hasattr(content.post.record, 'created_at')
                        ]
            posts, ts = zip(*posts_ts) if posts_ts else ([], [])
            all_posts.extend(posts)
            timestamps.extend(ts)
            cursor = data.cursor
        except exceptions.BadRequestError as e:
            logging.error(f"Bad request for DID {did}: {e}")
            return None
        except exceptions.ModelError as e:
            logging.error(f"Model error for DID {did}: {e}")
            return None
        if not cursor or len(all_posts) > 10000:
            break

    for post in all_posts:
        result = extract_news_link_pol_score(post)
        if result[0] is not None:
            results.append(result)

    scores = []
    source_counts = {}
    for score, domain in results:
        if score is not None:
            scores.append(score)
        if domain:
            source_counts[domain] = source_counts.get(domain, 0) + 1

    if profileViewResult.description:
        language = identify_language(profileViewResult.description)
        sentiment = bio_sentiment_textblob(profileViewResult.description)
    else:
        language = None
        sentiment = None
    if timestamps:
        life, burst = burstiness_index(timestamps)
    else:
        life = None
        burst = None

    if len(scores) > 0:
        avg_score = np.mean(scores)
        row = {'DID': did,
            'pol_score': avg_score,
            'language': language,
            'posts_num': profileViewResult.posts_count,
            'links_num': sum(source_counts.values()),
            'follow_ratio': (profileViewResult.followers_count / profileViewResult.follows_count) if profileViewResult.follows_count > 0 else None,
            'sentiment': sentiment,
            'activity_life_sec': life,
            'burstiness_index': burst}
        row.update(source_counts)
        return row

    return None

def process_batch(batch_dids):
    results = []
    new_domains = set()

    for did in tqdm(batch_dids, total= len(batch_dids)):
        result = process_did(did)
        if result:
            # Track any new domains seen in this batch
            for k in result.keys():
                if k not in DATA_COLUMNS:
                    new_domains.add(k)
            results.append(result)

    if not results:
        return

    # If CSV exists, read current columns
    if os.path.exists(constants.PROFILE_DATA_CSV):
        existing_df = pd.read_csv(constants.PROFILE_DATA_CSV)
        existing_columns = set(existing_df.columns)
    else:
        existing_df = pd.DataFrame()
        existing_columns = set(DATA_COLUMNS)

    # Determine if new columns need to be added
    needed_columns = existing_columns.union(new_domains)

    # Ensure all rows (existing + new) have the same columns
    all_data = []
    if not existing_df.empty:
        all_data.append(existing_df)

    # Fill missing columns in results with 0
    for r in results:
        for col in needed_columns:
            if col not in r:
                r[col] = 0
    new_df = pd.DataFrame(results)

    all_data.append(new_df)

    final_df = pd.concat(all_data, ignore_index=True)

    # Reorder columns: DID, pol_score, then sources alphabetically
    source_cols = sorted([c for c in needed_columns if c not in DATA_COLUMNS])
    final_df = final_df[DATA_COLUMNS + source_cols]

    # Overwrite the CSV with expanded header
    final_df.to_csv(constants.PROFILE_DATA_CSV, index=False)

    # Append processed DIDs
    with open(constants.EXTRACTED_DID_CSV, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows([[did] for did in batch_dids])

def extract_profiles():
    while True:

        print("PROF_EXTRACT: Sleeping for", SLEEP_SECS, "seconds...")     
        time.sleep(SLEEP_SECS)

        did_df = pd.read_csv(constants.DID_CSV, header=None, names=['DID','labelled'])
        if os.path.exists(constants.EXTRACTED_DID_CSV):
            did_extracted_df = pd.read_csv(constants.EXTRACTED_DID_CSV)
        else:
            did_extracted_df = pd.DataFrame(columns=['DID'])

        did_set = set(did_df['DID'])
        extracted_did_set = set(did_extracted_df['DID'])
        did_list = list(did_set.difference(extracted_did_set))
        print("PROF_EXTRACT: DIDs List Ready. Total DIDs to process:", len(did_list)) 
        for i in range(0, len(did_list), BATCH_SIZE):
            batch = did_list[i:i + BATCH_SIZE]
            print(f"PROF_EXTRACT: Processing batch {i // BATCH_SIZE + 1} of {len(did_list) // BATCH_SIZE + 1}...")
            process_batch(batch)
    