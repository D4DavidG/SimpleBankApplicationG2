import os
from pathlib import Path
import unittest

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv(Path(__file__).with_name(".env"))


class MongoDBConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise unittest.SkipTest("MONGODB_URI is not configured")

        cls.client = MongoClient(uri, serverSelectionTimeoutMS=10_000)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "client"):
            cls.client.close()

    def test_connection_is_available(self):
        result = self.client.admin.command("ping")

        self.assertEqual(result["ok"], 1.0)

    def test_sample_analytics_accounts_are_available(self):
        account = self.client.sample_analytics.accounts.find_one(
            {"account_id": 371138}
        )

        self.assertIsNotNone(account)
        self.assertEqual(account["account_id"], 371138)