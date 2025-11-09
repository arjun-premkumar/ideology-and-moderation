from pathlib import Path

LIB_FOLDER = Path(__file__).resolve()
PROJECT_ROOT = LIB_FOLDER.parents[1]
DATA_FOLDER = PROJECT_ROOT / 'data'
LOGS_FOLDER = PROJECT_ROOT / 'logs'
MBFC_CSV = str(DATA_FOLDER / 'mediabiasfactcheck_fulldataset.csv')
LABEL_CSV = str(DATA_FOLDER / 'labels.csv')
POST_CSV = str(DATA_FOLDER / 'posts.csv')
DID_CSV = str(DATA_FOLDER / 'DIDs.csv')
EXTRACTED_DID_CSV = str(DATA_FOLDER / 'extracted_DIDs.csv')
PROFILE_DATA_CSV = str(DATA_FOLDER / 'profile_data.csv')
LABEL_LISTENER_CURSOR = str(DATA_FOLDER / 'label_listener_cursor.txt')
ERROR_LOG = str(LOGS_FOLDER / 'bluesky_did_profile_parser_errors.log')