from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.auth.transport.requests

SERVICE_ACCOUNT_JSON = "service_account_1.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_JSON,
    scopes=SCOPES
)

request = google.auth.transport.requests.Request()

creds.refresh(request)

print("TOKEN OK")

service = build(
    "sheets",
    "v4",
    credentials=creds,
)

print("SERVICE OK")