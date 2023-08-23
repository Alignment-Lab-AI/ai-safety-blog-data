from datetime import datetime
from itertools import islice
import logging
import time
from dataclasses import dataclass, KW_ONLY
from pathlib import Path
from typing import Iterable, List, Optional, Set
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

import jsonlines
import pytz
from dateutil.parser import parse, ParserError
from tqdm import tqdm
from align_data.db.models import Article, Summary
from align_data.db.session import make_session

INIT_DICT = {
    "source": None,
    "id": None,
    "text": None,
    "date_published": None,
    "title": None,
    "url": None,
    "authors": lambda: [],
    "source_type": None,
    "status": None,
    "comments": None,
}

logger = logging.getLogger(__name__)


@dataclass
class AlignmentDataset:
    """The base dataset class."""

    name: str
    """The name of the dataset"""

    _: KW_ONLY

    files_path = Path("")
    """The path where data can be found. Usually a folder"""

    done_key = "id"
    """The key of the entry to use as the id when checking if already processed."""

    COOLDOWN = 0
    """An optional cool down between processing entries"""

    lazy_eval = False
    """Whether to lazy fetch items. This is nice in that it will start processing, but messes up the progress bar."""
    batch_size = 20
    """The number of items to collect before flushing to the database."""

    # Internal housekeeping variables
    _entry_idx = 0
    """Used internally for writing debugging info - each file write will increment it"""
    _outputted_items = set()
    """A set of the ids of all previously processed items"""

    def __str__(self) -> str:
        return self.name

    def __post_init__(self, data_path=Path(__file__).parent / "../../data/"):
        self.data_path = data_path
        self.raw_data_path = self.data_path / "raw"

        # set the default place to look for data
        self.files_path = self.raw_data_path / self.name

    def _add_authors(self, article: Article, authors: List[str]) -> Article:
        # TODO: Don't keep adding the same authors - come up with some way to reuse them
        article.authors = ",".join(authors)
        if len(article.authors) > 1024:
            article.authors = ",".join(article.authors[:1024].split(",")[:-1])
        return article

    def make_data_entry(self, data, **kwargs) -> Article:
        data = dict(data, **kwargs)
        summary = data.pop("summary", None)
        authors = data.pop("authors", [])

        article = Article(
            pinecone_update_required=True,
            meta={k: v for k, v in data.items() if k not in INIT_DICT and v is not None},
            **{k: v for k, v in data.items() if k in INIT_DICT},
        )
        self._add_authors(article, authors)
        if summary:
            article.summaries.append(Summary(text=summary, source=self.name))
        return article

    def to_jsonl(self, out_path=None, filename=None) -> Path:
        if not out_path:
            out_path = Path(__file__).parent / "../../data/"

        if not filename:
            filename = f"{self.name}.jsonl"
        filename = Path(out_path) / filename

        with jsonlines.open(filename, "w") as jsonl_writer:
            for article in self.read_entries():
                jsonl_writer.write(article.to_dict())
        return filename.resolve()

    @property
    def _query_items(self):
        return select(Article).where(Article.source == self.name)

    def read_entries(self, sort_by=None):
        """Iterate through all the saved entries."""
        with make_session() as session:
            query = self._query_items.options(joinedload(Article.summaries))
            if sort_by is not None:
                query = query.order_by(sort_by)
            for item in session.scalars(query).unique():
                yield item

    def _add_batch(self, session, batch):
        session.add_all(batch)

    def add_entries(self, entries):
        def commit():
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()

        with make_session() as session:
            items = iter(entries)
            while batch := tuple(islice(items, self.batch_size)):
                self._add_batch(session, batch)
                # there might be duplicates in the batch, so if they cause
                # an exception, try to commit them one by one
                if not commit():
                    for entry in batch:
                        session.add(entry)
                        if not commit():
                            logger.error(f"found duplicate of {entry}")

    def setup(self):
        self._outputted_items = self._load_outputted_items()

    @property
    def items_list(self) -> Iterable:
        """Returns a collection of items to be processed."""
        return []

    def get_item_key(self, item):
        """Get the identifier of the given `item` so it can be checked to see whether it's been output.

        The default assumption is that the `item` is a Path to a file.
        """
        return item.name

    def _load_outputted_items(self) -> Set[str]:
        """Load the output file (if it exists) in order to know which items have already been output."""
        with make_session() as session:
            if hasattr(Article, self.done_key):
                # This doesn't filter by self.name. The good thing about that is that it should handle a lot more
                # duplicates. The bad thing is that this could potentially return a massive amount of data if there
                # are lots of items.
                return set(session.scalars(select(getattr(Article, self.done_key))).all())
            # TODO: Properly handle this - it should create a proper SQL JSON select
            return {item.get(self.done_key) for item in session.scalars(select(Article.meta)).all()}

    def not_processed(self, item):
        # NOTE: `self._outputted_items` reads in all items. Which could potentially be a lot. If this starts to
        # cause problems (e.g. massive RAM usage, big slow downs) then it will have to be switched around, so that
        # this function runs a query to check if the item is in the database rather than first getting all done_keys.
        # If it get's to that level, consider batching it somehow
        return self.get_item_key(item) not in self._outputted_items

    def unprocessed_items(self, items=None) -> Iterable:
        """Return a list of all items to be processed.

        This will automatically remove any items that have already been processed,
        based on the contents of the output file.
        """
        self.setup()

        filtered = filter(self.not_processed, items or self.items_list)

        # greedily fetch all items if not lazy eval. This makes the progress bar look nice
        if not self.lazy_eval:
            filtered = list(filtered)

        return filtered

    def fetch_entries(self):
        """Get all entries to be written to the file."""
        for item in tqdm(self.unprocessed_items(), desc=f"Processing {self.name}"):
            entry = self.process_entry(item)
            if not entry:
                continue

            try:
                entry.verify_id_fields()
            except AssertionError as e:
                logger.error(e)
                continue

            yield entry

            if self.COOLDOWN:
                time.sleep(self.COOLDOWN)

    def process_entry(self, entry) -> Article | None:
        """Process a single entry."""
        raise NotImplementedError

    @staticmethod
    def _format_datetime(date) -> str:
        return date.strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _get_published_date(date) -> datetime | None:
        try:
            # Totally ignore any timezone info, forcing everything to UTC
            return parse(str(date)).replace(tzinfo=pytz.UTC)
        except ParserError:
            pass
        return None


class SummaryDataset(AlignmentDataset):
    def unprocessed_items(self, items=None) -> Iterable:
        # This breaks the possible lazy loading of the items. Should be fine...
        items = list(super().unprocessed_items(items))

        urls = map(self.get_item_key, items)
        with make_session() as session:
            articles = (
                session.query(Article)
                .options(joinedload(Article.summaries))
                .filter(Article.url.in_(urls))
            )
            self.articles = {a.url: a for a in articles if a.url}

        return items

    def _load_outputted_items(self) -> Set[str]:
        """Load the output file (if it exists) in order to know which items have already been output."""
        with make_session() as session:
            return set(
                session.scalars(
                    select(Article.url).join(Article.summaries).filter(Summary.source == self.name)
                )
            )

    def _add_batch(self, session, batch):
        def merge(item):
            if prev := self.articles.get(item.url):
                return session.merge(item.update(prev))
            return item

        session.add_all(map(merge, batch))
