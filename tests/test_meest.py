"""Offline API/aggregation tests; no Home Assistant runtime or Meest account needed."""

import asyncio
import importlib
import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Load the standalone client without executing the HA adapter's __init__.
ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("meest_test_package")
package.__path__ = [str(ROOT / "custom_components/meest")]
sys.modules[package.__name__] = package
api = importlib.import_module("meest_test_package.api")
models = importlib.import_module("meest_test_package.models")


def parcel(number="TEST-1", code="2", service="PostStation", direction=1, branch="A"):
    return {
        "parcelID": number,
        "parcelNumber": number,
        "direction": direction,
        "contentName": "Test contents",
        "archive": False,
        "DeliveryInfo": {
            "statusCode": code,
            "statusName": "Test status",
            "receiver": {
                "service": service,
                "branchID": branch,
                "branchNumber": "1234",
                "address": "Test address",
                "phone": "DO_NOT_EXPORT",
                "name": "DO_NOT_EXPORT",
            },
        },
    }


def page(items, count):
    return {"status": "OK", "result": [{"parcelsForRequestedPage": items, "quantitybyMode": count}]}


class Content:
    def __init__(self, document):
        self.payload = json.dumps(document).encode()

    async def iter_chunked(self, size):
        yield self.payload


class Response:
    def __init__(self, document=None, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.content = Content(document)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected extra request")
        return self.responses.pop(0)


class ModelTests(unittest.TestCase):
    def test_ready_post_station_and_branch_grouping(self):
        data = models.aggregate(
            [parcel("B"), parcel("A"), parcel("C", service="Branch", branch="B")]
        )
        self.assertEqual(len(data["ready_for_pickup"]), 3)
        self.assertEqual(len(data["locations"]), 2)
        locker = next(g for g in data["locations"] if g["type"] == "post_station")
        self.assertEqual([p["number"] for p in locker["parcels"]], ["A", "B"])
        self.assertNotIn("DO_NOT_EXPORT", json.dumps(data))

    def test_transit_and_terminal_filtering(self):
        items = [parcel(str(i), str(i)) for i in range(8)]
        data = models.aggregate(items)
        self.assertEqual(len(data["ready_for_pickup"]), 1)
        self.assertEqual([p["status_code"] for p in data["in_transit"]], ["1", "3", "7"])
        self.assertEqual(data["unclassified"], [])

    def test_outgoing_and_archive_excluded(self):
        archived = parcel("ARCHIVE")
        archived["archive"] = True
        data = models.aggregate([parcel("OUT", direction=2), archived])
        self.assertEqual(data["ready_for_pickup"], [])

    def test_unknown_and_door_not_counted_as_pickup(self):
        data = models.aggregate([parcel("UNKNOWN", "99"), parcel("DOOR", service="Door")])
        self.assertEqual(len(data["unclassified"]), 2)
        self.assertEqual(data["ready_for_pickup"], [])

    def test_snapshot_replaces_received_parcel(self):
        self.assertEqual(len(models.aggregate([parcel()])["ready_for_pickup"]), 1)
        self.assertEqual(models.aggregate([parcel(code="4")])["ready_for_pickup"], [])

    def test_malformed_delivery_raises(self):
        with self.assertRaises(ValueError):
            models.aggregate([{"direction": 1}])

    def test_secret_repr(self):
        self.assertNotIn("SECRET", repr(api.Tokens("SECRET_ACCESS", "SECRET_REFRESH")))

    def test_expiry_formats(self):
        with patch.object(api.time, "time", return_value=1700000000):
            self.assertEqual(
                api.parse_tokens({"token": "a", "refreshToken": "b", "expiresIn": 3600}).expires_at,
                1700003600,
            )
            self.assertEqual(
                api.parse_tokens(
                    {"token": "a", "refreshToken": "b", "expiresIn": 1799765466}
                ).expires_at,
                1799765466,
            )

    def test_retry_and_account_normalization(self):
        self.assertEqual(api.retry_seconds("30"), 60)
        self.assertEqual(api.retry_seconds("bad"), 900)
        self.assertEqual(
            api.account_id({}, "+380 (99) 123-45-67"), api.account_id({}, "380991234567")
        )
        self.assertEqual(api.account_id({"globalUserId": "account"}, "unused"), "account")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_request(self):
        session = Session(
            [
                Response(
                    {
                        "status": "OK",
                        "result": {"token": "a", "refreshToken": "b", "globalUserId": "id"},
                    }
                )
            ]
        )
        account, _ = await api.MeestClient(session).login("login", "password")
        self.assertEqual(account, "id")
        url, args = session.calls[0]
        self.assertTrue(url.endswith("app/login"))
        self.assertEqual(args["json"]["platform"], "Android")
        self.assertFalse(args["allow_redirects"])
        self.assertNotIn("token", args["headers"])

    async def test_zero_count_on_empty_page_and_b2b(self):
        session = Session([Response(page([parcel()], 1)), Response(page([], 0))])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            items = await api.MeestClient(session, api.Tokens("a", "b")).parcels(True)
        self.assertEqual(len(items), 1)
        self.assertIn("B2B=true&B2C=true", session.calls[0][0])
        self.assertEqual(session.calls[0][1]["headers"]["token"], "a")

    async def test_multiple_pages_deduplicate(self):
        session = Session(
            [
                Response(page([parcel("A"), parcel("B")], 3)),
                Response(page([parcel("B"), parcel("C")], 3)),
                Response(page([], 0)),
            ]
        )
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            items = await api.MeestClient(session, api.Tokens("a", "b")).parcels()
        self.assertEqual(len(items), 3)

    async def test_partial_snapshot_rejected(self):
        session = Session([Response(page([parcel()], 2)), Response(page([], 0))])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()), self.assertRaises(api.MeestError):
            await api.MeestClient(session, api.Tokens("a", "b")).parcels()

    async def test_repeated_page_rejected(self):
        session = Session([Response(page([parcel()], 1)), Response(page([parcel()], 1))])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()), self.assertRaises(api.MeestError):
            await api.MeestClient(session, api.Tokens("a", "b")).parcels()

    async def test_refresh_persisted_before_retry(self):
        session = Session(
            [
                Response(status=401),
                Response({"status": "OK", "result": {"token": "new", "refreshToken": "new_r"}}),
                Response(page([], 0)),
            ]
        )
        persisted = []

        async def save(tokens):
            self.assertEqual(len(session.calls), 2)
            persisted.append(tokens)

        client = api.MeestClient(session, api.Tokens("old", "old_r"), save)
        self.assertEqual(await client.parcels(), [])
        self.assertEqual(persisted[0].refresh_token, "new_r")
        self.assertEqual(session.calls[1][1]["json"], {"refreshToken": "old_r"})
        self.assertEqual(session.calls[2][1]["headers"]["token"], "new")

    async def test_proactive_refresh(self):
        session = Session(
            [
                Response(
                    {
                        "status": "OK",
                        "result": {"token": "new", "refreshToken": "new_r", "expiresIn": 3600},
                    }
                ),
                Response(page([], 0)),
            ]
        )
        client = api.MeestClient(session, api.Tokens("old", "old_r", time.time() - 1))
        await client.parcels()
        self.assertTrue(session.calls[0][0].endswith("app/refreshToken"))

    async def test_refresh_mutex(self):
        session = Session(
            [Response({"status": "OK", "result": {"token": "new", "refreshToken": "new_r"}})]
        )
        saved = AsyncMock()
        client = api.MeestClient(session, api.Tokens("old", "old_r"), saved)
        await asyncio.gather(client._refresh("old"), client._refresh("old"))
        self.assertEqual(len(session.calls), 1)
        saved.assert_awaited_once()

    async def test_failed_refresh_stops(self):
        session = Session([Response(status=401), Response(status=401)])
        with self.assertRaises(api.MeestAuthError):
            await api.MeestClient(session, api.Tokens("a", "b")).parcels()
        self.assertEqual(len(session.calls), 2)

    async def test_forbidden_is_not_expired_session(self):
        session = Session([Response(status=403)])
        client = api.MeestClient(session, api.Tokens("a", "b"))
        with self.assertRaises(api.MeestError) as caught:
            await client.parcels()
        self.assertNotIsInstance(caught.exception, api.MeestAuthError)
        self.assertIn("parcel request: HTTP 403", str(caught.exception))
        self.assertEqual(len(session.calls), 1)

    async def test_refresh_application_error_keeps_session_retryable(self):
        session = Session(
            [
                Response(status=401),
                Response({"status": "ERROR", "result": "SECRET"}),
                Response(page([], 0)),
            ]
        )
        client = api.MeestClient(session, api.Tokens("a", "b"))
        with self.assertRaises(api.MeestError) as caught:
            await client.parcels()
        self.assertNotIsInstance(caught.exception, api.MeestAuthError)
        self.assertIn("refresh: application error", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(client._tokens, api.Tokens("a", "b"))
        self.assertEqual(await client.parcels(), [])

    async def test_rejected_refresh_has_safe_context(self):
        session = Session([Response(status=401), Response(status=400)])
        with self.assertRaises(api.MeestAuthError) as caught:
            await api.MeestClient(session, api.Tokens("SECRET", "SECRET_R")).parcels()
        self.assertEqual(str(caught.exception), "Meest refresh: HTTP 400")

    async def test_rate_limit(self):
        session = Session([Response(status=429, headers={"Retry-After": "1234"})])
        with self.assertRaises(api.MeestRateLimitError) as caught:
            await api.MeestClient(session, api.Tokens("a", "b")).parcels()
        self.assertEqual(caught.exception.retry_after, 1234)

    async def test_server_errors_hide_body(self):
        for response in [
            Response({"private": "SECRET"}, status=500),
            Response({"status": "ERROR", "result": "SECRET"}),
            Response({"private": "SECRET"}, status=302),
        ]:
            with self.assertRaises(api.MeestError) as caught:
                await api.MeestClient(Session([response]))._post("app/test", {})
            self.assertNotIn("SECRET", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
