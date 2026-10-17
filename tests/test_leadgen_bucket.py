import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "metrics"))
from leadgen_bucket import leadgen_bucket as b


class LeadgenBucketTests(unittest.TestCase):
    def test_sweeper_virtual_wins(self):
        self.assertEqual(b("Sweeper", "", "Buffalo"), "Sweeper/Rehash/Virtual")
        self.assertEqual(b("Rehash", "", "Buffalo"), "Sweeper/Rehash/Virtual")
        self.assertEqual(b("Self Gen", "Diamond", "Buffalo"), "Sweeper/Rehash/Virtual")
        self.assertEqual(b("3PL", "Diamond", "Rochester"), "Sweeper/Rehash/Virtual")
        # Pipeline membership and Phones/Virtual source do not put a lead in this bucket.
        self.assertEqual(b("Phones", "", "Virtual"), "Other")
        self.assertEqual(b("Doors", "", "Rehash"), "Doors")
        self.assertEqual(b("3PL", "", "Rehash"), "3PL/Inbound")
        self.assertEqual(b("Doors", "", "Sweeper"), "Doors")

    def test_other_buckets(self):
        self.assertEqual(b("Doors", "", "Buffalo"), "Doors")
        self.assertEqual(b("Self Gen", "none", "Buffalo"), "Self Gen")
        self.assertEqual(b("3PL", None, "Buffalo"), "3PL/Inbound")
        self.assertEqual(b("Inbound", None, "Buffalo"), "3PL/Inbound")
        self.assertEqual(b("Facebook Quick Form", None, "Buffalo"), "3PL/Inbound")
        self.assertEqual(b("none", None, "Buffalo"), "Other")


if __name__ == "__main__":
    unittest.main()
