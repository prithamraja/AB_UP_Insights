import unittest

from query_router.column_metadata import build_catalog_column_metadata
from query_router.dashboard_catalog import DASHBOARD_CATALOG
from query_router.models import ColumnType
from query_router.template_catalog import TEMPLATE_CATALOG


class CatalogColumnMetadataTests(unittest.TestCase):
    def test_every_catalog_has_fully_typed_result_columns(self):
        metadata = build_catalog_column_metadata(
            DASHBOARD_CATALOG,
            TEMPLATE_CATALOG,
        )

        self.assertEqual(len(metadata), len(DASHBOARD_CATALOG) + len(TEMPLATE_CATALOG))
        self.assertFalse([query_id for query_id, columns in metadata.items() if not columns])
        self.assertFalse([
            (query_id, column.name)
            for query_id, columns in metadata.items()
            for column in columns
            if column.column_type == ColumnType.UNCLASSIFIED
        ])


if __name__ == "__main__":
    unittest.main()
