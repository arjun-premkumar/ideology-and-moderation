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
BATCH_SIZE = 10
SLEEP_SECS = 90
DetectorFactory.seed = 0

logging.basicConfig(filename=constants.ERROR_LOG, level=logging.ERROR, format='%(asctime)s - %(message)s')

client = Client()
client.login('bluesky username', 'bluesky password')
mbfc_df = pd.read_csv(constants.MBFC_CSV)

def extract_news_link_pol_score(text: str) -> tuple[float | None, str | None]:
    """
    Extract the political score of any news links in a post, based on the MBFC dataset.
    
    Args:
        text (str): The post text containing URLs.
    
    Returns:
        tuple: (political_score, domain) if a news link is found, otherwise (None, None)
    """
    #Use regex to find all URLs in the post text
    url_pattern = r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?::\d{2,5})?(?:/[^\s]*)?'
    matches = re.findall(url_pattern, text)

    for url in matches:
        try:
            #Expand shortened URLs
            response = requests.get(url, allow_redirects=True, timeout=20)
            url = response.url
        except requests.RequestException as e:
            logging.error(f"Error expanding URL ({type(e).__name__}): {str(e)}")
            continue
        
        #Parse the URL t oextract the domain
        parsed = urlparse(url)
        netloc = parsed.netloc.replace("www.", "")
        domain_parts = netloc.split(".")
        match_domain = domain_parts[-2] if len(domain_parts) >= 2 else netloc
        
        #Find the exact match in MBFC and return the political score
        for domain in mbfc_df['sourcedomain']:
            if domain == match_domain:
                score = float(mbfc_df[mbfc_df['sourcedomain'] == domain]['political_level'].iloc[0])
                return score, domain

    return None, None

def identify_language(text) -> str:
    """
    Identify the language of a profile description.

    Args:
        text (str): The text for which to identify the language.

    Returns:
        str: The language code or an error message.
    """
    try:
        language_code = detect(text)
        return language_code
    except LangDetectException:
        return "Could not detect language"

def burstiness_index(timestamps) -> float | None:
    """
    Compute the coefficient of variation (CV) of inter-post times.
    
    Args:
        timestamps (list): List of datetime objects (or ISO8601 strings).
    
    Returns:
        float: CV value (σ/μ) or None if insufficient data.
    """

    parsed = []
    for ts in timestamps:

        #Convert strings to datetime
        if isinstance(ts, str):
            dt = parser.isoparse(ts)
        else:
            dt = ts
        
        #Ensure UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        
        parsed.append(dt)

    #Sort timestamps
    parsed = sorted(parsed)

    #Compute inter-post intervals in seconds
    intervals = np.diff([ts.timestamp() for ts in parsed])

    #Compute account lifetime in seconds
    life = parsed[-1].timestamp() - parsed[0].timestamp()

    if len(intervals) < 2:
        #Not enough data
        return None

    #Compute burstiness index
    mu = np.mean(intervals)
    sigma = np.std(intervals)
    burst = (sigma - mu) / (sigma + mu) if mu > 0 else None

    return life, burst

def bio_sentiment_textblob(description: str) -> float:
    """
    Compute sentiment polarity score of a Bluesky bio using TextBlob.
    
    Args:
        description (str): Profile description text.
    
    Returns:
        float: Polarity score in range [-1.0, 1.0]
            (-1 very negative, 0 neutral, +1 very positive)
    """
    if not description:
        #treat empty bios as neutral
        return 0.0
    
    #Use TextBlob to compute sentiment polarity
    analysis = TextBlob(description)
    return analysis.sentiment.polarity

def process_did(did) -> dict | None:
    """
    Process a single DID and extract its relevant profile information
    
    Args:
        did (str): The DID of the profile to process.
    
    Returns:
        dict: A dictionary containing the extracted profile information if it contains at least one news link with a political score, otherwise None.
    """

    all_posts = []
    timestamps = []
    results = []
    cursor = None

    #Attempt to retrieve the profile information for the DID
    try:
        profileViewResult = client.get_profile(did)
    except exceptions.BadRequestError as e:
        print(f"Request Exception for DID {did} ({type(e).__name__}): {str(e)}")
    except Exception as e:
        return
    
    while True:
        try:
            #Retrieve posts for the DID in batches of 100 
            data = client.get_author_feed(
                actor=did,
                filter='posts_no_replies',
                limit=100,
                cursor=cursor
            )
            feed = data.feed

            #Extract the text and timestamp of each post, and add them to the respective lists
            posts_ts = [(content.post.record.text, content.post.record.created_at) for content in feed
                        if hasattr(content.post.record, 'text') and hasattr(content.post.record, 'created_at')
                        ]
            posts, ts = zip(*posts_ts) if posts_ts else ([], [])
            all_posts.extend(posts)
            timestamps.extend(ts)

            #Update the cursor
            cursor = data.cursor

        except exceptions.BadRequestError as e:
            logging.error(f"Bad request for DID {did}: {e}")
            return None
        except exceptions.ModelError as e:
            logging.error(f"Model error for DID {did}: {e}")
            return None
        
        #Break if there are no more posts to retrieve or if more than 10,000 posts have been retrieved
        if not cursor or len(all_posts) > 10000:
            break

    #Process each retrieved post
    for post in all_posts:

        #Extract the political score of any news links in the post
        result = extract_news_link_pol_score(post)
        if result[0] is not None:
            results.append(result)

    scores = []
    source_counts = {}

    #Aggregate the political scores and news source counts across all posts
    for score, domain in results:
        if score is not None:
            scores.append(score)
        if domain:
            source_counts[domain] = source_counts.get(domain, 0) + 1

    #Extract the language and sentiment of the profile description
    if profileViewResult.description:
        language = identify_language(profileViewResult.description)
        sentiment = bio_sentiment_textblob(profileViewResult.description)
    else:
        language = None
        sentiment = None

    #Extract the account lifetime and burstiness index of posting activity
    if timestamps:
        life, burst = burstiness_index(timestamps)
    else:
        life = None
        burst = None

    if len(scores) > 0:
        #Compute average political score
        avg_score = np.mean(scores)

        #Compile all extracted information
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

def process_batch(batch_dids) -> None:
    """
    Process a batch of DIDs and save the extracted profile information
    
    Args:
        batch_dids (list): A list of DIDs to process.
    
    Returns:
        None.
    """
    results = []
    new_domains = set()

    #Process each DID in the batch
    for did in tqdm(batch_dids, total= len(batch_dids)):
        result = process_did(did)

        if result:
            #Track any new news domains seen in this batch
            for k in result.keys():
                if k not in DATA_COLUMNS:
                    new_domains.add(k)
            results.append(result)

    if not results:
        return

    #Read the existing profile data and columns
    if os.path.exists(constants.PROFILE_DATA_CSV):
        existing_df = pd.read_csv(constants.PROFILE_DATA_CSV)
        existing_columns = set(existing_df.columns)
    else:
        existing_df = pd.DataFrame()
        existing_columns = set(DATA_COLUMNS)

    #Add the new domains to the columns for writing
    needed_columns = existing_columns.union(new_domains)

    #Write the existing data first
    all_data = []
    if not existing_df.empty:
        all_data.append(existing_df)

    #Fill not shared news domains with 0
    for r in results:
        for col in needed_columns:
            if col not in r:
                r[col] = 0

    #Append the new results to create the final dataframe
    new_df = pd.DataFrame(results)
    all_data.append(new_df)
    final_df = pd.concat(all_data, ignore_index=True)

    #Reorder columns: DID, pol_score, then news domains alphabetically
    source_cols = sorted([c for c in needed_columns if c not in DATA_COLUMNS])
    final_df = final_df[DATA_COLUMNS + source_cols]

    #Overwrite the profile data file with expanded header
    final_df.to_csv(constants.PROFILE_DATA_CSV, index=False)

    #Add the processed DIDs to the extracted DIDs file to avoid re-processing in the future
    with open(constants.EXTRACTED_DID_CSV, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows([[did] for did in batch_dids])

def extract_profiles() -> None:
    """
    Periodically extract profile information for DIDs in the DID file
    
    Args:
        None
    
    Returns:
        None
    """
    while True:

        #Sleep before each extraction cycle to allow for new DIDs to be added to the DID file
        print("PROF_EXTRACT: Sleeping for", SLEEP_SECS/60 , "minutes...")     
        time.sleep(SLEEP_SECS)

        #Read the DIDs from the DID file
        if os.path.exists(constants.DID_CSV):
            did_df = pd.read_csv(constants.DID_CSV, header=None, names=['DID','labelled'])
        else:
            print("PROF_EXTRACT: No DID file found. Skipping this cycle.")
            continue
        
        #Read the list of already extracted DIDs to avoid re-processing
        if os.path.exists(constants.EXTRACTED_DID_CSV):
            did_extracted_df = pd.read_csv(constants.EXTRACTED_DID_CSV)
        else:
            did_extracted_df = pd.DataFrame(columns=['DID'])

        #Create a list of DIDs to process
        did_set = set(did_df['DID'])
        extracted_did_set = set(did_extracted_df['DID'])
        did_list = list(did_set.difference(extracted_did_set))
        print("PROF_EXTRACT: DIDs List Ready. Total DIDs to process:", len(did_list)) 
        
        #Process the DIDs in batches to manage memory usage and API rate limits
        for i in range(0, len(did_list), BATCH_SIZE):
            batch = did_list[i:i + BATCH_SIZE]
            print(f"PROF_EXTRACT: Processing batch {i // BATCH_SIZE + 1} of {len(did_list) // BATCH_SIZE + 1}...")
            process_batch(batch)
    