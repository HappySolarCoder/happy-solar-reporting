import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "metrics"))

import bloom_roles  # noqa: E402


class BloomRolesTests(unittest.TestCase):
    def test_parse_keeps_name_and_board_roles_only(self):
        rows = [
            {"name": " Ann Fma ", "role": "fma", "email": "a@x"},
            {"name": "Cal Closer", "role": "closer"},
            {"name": "Mo Manager", "role": "manager"},
            {"name": "", "role": "fma"},
        ]
        people = bloom_roles.parse_people(rows)
        self.assertEqual(people, [{"name": "Cal Closer", "role": "closer"}, {"name": "Ann Fma", "role": "fma"}])
        self.assertTrue(all(set(p) == {"name", "role"} for p in people))

    def test_sql_is_read_only_and_skips_demo(self):
        sql = bloom_roles.ROLES_SQL.upper()
        self.assertTrue(sql.startswith("SELECT"))
        for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER"):
            self.assertNotIn(word, sql)
        self.assertIn("IS_DEMO", sql)

    def test_no_database_url(self):
        import os
        old = {k: os.environ.pop(k, None) for k in ("DATABASE_URL", "POSTGRES_URL")}
        try:
            self.assertEqual(bloom_roles.read_bloom_roles()["available"], False)
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
