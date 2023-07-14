import os
from dotenv import load_dotenv
load_dotenv()


CODA_TOKEN = os.environ.get("CODA_TOKEN")
CODA_DOC_ID = os.environ.get("CODA_DOC_ID", "fau7sl2hmG")
ON_SITE_TABLE = os.environ.get('CODA_ON_SITE_TABLE', 'table-aOTSHIz_mN')

PDFS_FOLDER_ID = os.environ.get('PDF_FOLDER_ID', '1etWiXPRl0QqdgYzivVIj6wCv9xj5VYoN')

METADATA_SOURCE_SPREADSHEET = os.environ.get('METADATA_SOURCE_SPREADSHEET', '1pgG3HzercOhf4gniaqp3tBc3uvZnHpPhXErwHcthmbI')
METADATA_SOURCE_SHEET = os.environ.get('METADATA_SOURCE_SHEET', 'special_docs.csv')
METADATA_OUTPUT_SPREADSHEET = os.environ.get('METADATA_OUTPUT_SPREADSHEET', '1l3azVJVukGAvZPgg0GyeqiaQe8bEMZvycBJaA8cRXf4')


user = os.environ.get('ARD_DB_USER', 'user')
password = os.environ.get('ARD_DB_PASSWORD', 'we all live in a yellow submarine')
host = os.environ.get('ARD_DB_HOST', '127.0.0.1')
port = os.environ.get('ARD_DB_PORT', '3306')
db_name = os.environ.get('ARD_DB_NAME', 'alignment_research_dataset')
DB_CONNECTION_URI = f'mysql+mysqldb://{user}:{password}@{host}:{port}/{db_name}'
