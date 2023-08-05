from unittest.mock import patch, Mock
import pytest
from align_data.common.alignment_dataset import MySQLDB


@pytest.fixture(autouse=True, scope='session')
def mock_db():
    # This just mocks out all db calls, nothing more
    with patch('align_data.common.alignment_dataset.MySQLDB'):
        yield
