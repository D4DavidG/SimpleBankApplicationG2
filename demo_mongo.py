import json
import os

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv()
uri = os.getenv("MONGODB_URI")
if not uri:
    raise RuntimeError("MONGODB_URI is not set in the environment or .env file")

client = MongoClient(uri)

try:
    database = client.get_database("sample_analytics")
    accounts = database.get_collection("accounts")

    # Queries for the account with account_id 371138
    query = {"account_id": 371138}
    account = accounts.find_one(query)

    print(json.dumps(account, indent=4, default=str))
except Exception as error:
    raise Exception(
        "Unable to find the document due to the following error: ", error
    )
finally:
    client.close()

# Expected output:
# {
#     "_id": "5ca4bbc7a2dd94ee5816238c",
#     "account_id": 371138,
#     "limit": 9000,
#     "products": [
#         "Derivatives",
#         "InvestmentStock"
#     ]
# }