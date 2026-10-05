# -*- coding: utf-8 -*-

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scope = load_module("pipeline_scope", ROOT / "api" / "metrics" / "pipeline_scope.py")


class PipelineScopeTests(unittest.TestCase):
    def test_sweeper_is_sweeper_and_rehash_not_phones(self):
        self.assertTrue(scope.pipeline_in_scope("Sweeper", sweeper=True))
        self.assertTrue(scope.pipeline_in_scope("Rehash", sweeper=True))
        self.assertFalse(scope.pipeline_in_scope("Buffalo", sweeper=True))
        self.assertFalse(scope.pipeline_in_scope("Phones", sweeper=True))

    def test_territory_and_sweeper_must_both_match(self):
        self.assertFalse(scope.pipeline_in_scope("Buffalo", pipeline="Buffalo", sweeper=True))
        self.assertTrue(scope.pipeline_in_scope("Sweeper", pipeline="Sweeper"))
        self.assertTrue(scope.pipeline_in_scope("Rehash", pipeline="sweeper"))
        self.assertTrue(scope.pipeline_in_scope("Buffalo", pipeline="Buffalo"))
        self.assertFalse(scope.pipeline_in_scope("Rochester", pipeline="Buffalo"))

    def test_empty_filter_keeps_every_pipeline(self):
        self.assertTrue(scope.pipeline_in_scope("Virtual"))
        self.assertTrue(scope.truthy_flag("1"))
        self.assertFalse(scope.truthy_flag("0"))


if __name__ == "__main__":
    unittest.main()
