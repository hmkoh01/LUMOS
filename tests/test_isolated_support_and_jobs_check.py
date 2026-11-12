import json

from scripts.isolated_support_and_jobs_check import Tracker, fetcher


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return 200

    def read(self, _limit):
        return json.dumps(self.payload).encode("utf-8")


def test_transport_http_status_and_body_result_code_are_independent(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"resultCode": 0, "result": []}))
    tracker = Tracker()
    assert fetcher(tracker)("https://official.example", 1, {})["resultCode"] == 0
    assert tracker.http_status == 200
    assert tracker.body_result_code == "0"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Response({"resultCode": 200, "result": []}))
    tracker = Tracker()
    fetcher(tracker)("https://official.example", 1, {})
    assert tracker.http_status == 200
    assert tracker.body_result_code == "200"
