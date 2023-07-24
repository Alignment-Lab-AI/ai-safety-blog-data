import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List

import fire
import requests

from align_data import ALL_DATASETS, DATASET_REGISTRY, get_dataset
from align_data.analysis.count_tokens import count_token
from align_data.sources.articles.articles import update_new_items, check_new_articles
from align_data.pinecone.update_pinecone import ARDUpdater
from align_data.settings import (
    METADATA_OUTPUT_SPREADSHEET, METADATA_SOURCE_SHEET, METADATA_SOURCE_SPREADSHEET
)


logger = logging.getLogger(__name__)


def add_summaries(summaries, dataset):
    for line in dataset.read_entries():
        url = line.get(dataset.source_key)
        summary = line.get(dataset.summary_key)
        if url and summary:
            summaries[url][dataset.name] = summary
    return summaries


def download_from_hf(dataset):
    url = f'https://huggingface.co/datasets/StampyAI/alignment-research-dataset/resolve/main/{dataset.name}.jsonl'
    res = requests.get(url, stream=True)
    if res.status_code != 200:
        logger.info(f'Error downloading {dataset.jsonl_path.name}: %s', res.status_code)
    else:
        logger.info(f'Downloading {dataset.jsonl_path.name}')
        with open(dataset.jsonl_path, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)


@dataclass
class AlignmentDataset:

    out_path: str = "data"
    """The path to the directory where the data will be downloaded, defaults to data"""

    def list(self) -> List[str]:
        """Returns a list of all the datasets"""
        return sorted(ALL_DATASETS)

    def fetch(self, *names, rebuild=False, fetch_prev=False) -> None:
        """
        > This function takes a dataset name and writes the entries of that dataset to a file

        :param str name: The name of the dataset to fetch
        :param bool rebuild: Whether to remove the previous build before running
        :param bool fetch_prev: Whether to fetch the previous dataset from Huggingface. Overrides rebuild
        :return: The path to the file that was written to.
        """
        missing = {name for name in names if name not in ALL_DATASETS}
        assert not missing, f"{missing} are not valid dataset names"
        for name in names:
            dataset = get_dataset(name)

            if fetch_prev:
                # TODO: what should this do? Download and load the data?
                download_from_hf(dataset)
            elif rebuild:
                # TODO: Get this to work properly
                dataset.jsonl_path.unlink(missing_ok=True)

            dataset.add_entries(dataset.fetch_entries())
            # TODO: Get rid of jsonl stuff here
            dataset.to_jsonl()
            print(dataset.jsonl_path)

    def fetch_all(self, *skip, rebuild=False, fetch_prev=False) -> str:
        """
        It downloads all the datasets, moves the alignment_newsletter.jsonl file to the processed
        folder, deletes the alignment_newsletter.jsonl file, adds the alignment_newsletter_summaries to
        the datasets, and merges all the files

        :param bool rebuild: Whether to remove the previous build before running
        :param str|tuple skip: a comma separated list of datasources to be skipped
        :param bool fetch_prev: Whether to fetch the previous datasets from Huggingface
        :return: The path to the merged file.
        """
        names = [name for name in ALL_DATASETS if name not in skip]
        for name in names:
            print(name)
            self.fetch(name, rebuild=rebuild, fetch_prev=fetch_prev)

        return self.merge_summaries(*names)

    def count_tokens(self, merged_dataset_path: str) -> None:
        """
        This function counts the number of tokens, words, and characters in the dataset
        :return: None
        """
        assert os.path.exists(merged_dataset_path), "The path to the merged dataset does not exist"
        count_token(merged_dataset_path)

    def update_metadata(
            self, source_spreadsheet=METADATA_SOURCE_SPREADSHEET,
            source_sheet=METADATA_SOURCE_SHEET, output_spreadsheet=METADATA_OUTPUT_SPREADSHEET
    ):
        """Go through all unprocessed items from the source worksheet, updating the appropriate metadata in the output one.

        :param str source_spreadsheet: The id of the google docs spreadsheet containing the items to be processed
        :param str source_sheet: The name of the worksheet to be processed
        :param str output_spreadsheet: The id of the output google sheet where processed metadata should be added. This sheet should have a worksheet for each expected data type (e.g. "pdf", "html")
        """
        return update_new_items(source_spreadsheet, source_sheet, output_spreadsheet)

    def fetch_new_articles(self, source_spreadsheet=METADATA_SOURCE_SPREADSHEET, source_sheet=METADATA_SOURCE_SHEET):
        """Look for unseen articles in the special indices, adding any that are found to the provided spreadsheet.

        :param str source_spreadsheet: The id of the google docs spreadsheet containing the items to be processed
        :param str source_sheet: The name of the worksheet to be processed
        """
        return check_new_articles(source_spreadsheet, source_sheet)

    def update_pinecone(self):
        """
        This function updates the Pinecone vector DB.
        """
        updater = ARDUpdater()
        updater.update()

if __name__ == "__main__":
    fire.Fire(AlignmentDataset)
