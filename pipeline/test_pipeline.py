"""Offline tests for run.py and check.py (no API key or network needed).

    cd pipeline && python3 -m unittest -v test_pipeline
"""
import copy
import http.server
import json
import os
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LETTER = open(os.path.join(HERE, "sample_letter_cardiology.txt"), encoding="utf-8").read()
GOOD = json.load(open(os.path.join(HERE, "sample_output_cardiology.json"), encoding="utf-8"))

import check  # noqa: E402
import run  # noqa: E402


class CheckerTests(unittest.TestCase):
    def issues(self, out):
        return check.check(LETTER, out)[0]

    def test_sample_output_passes(self):
        self.assertEqual(self.issues(GOOD), [])

    def test_parses_all_discharge_medicines(self):
        meds = check.letter_medicines(LETTER)
        self.assertEqual(len(meds), 9)
        self.assertEqual(meds["atorvastatin"]["schedule"], (0, 0, 1, 0))
        self.assertEqual(meds["relvar"]["schedule"], (2, 0, 0, 0))

    def assertFlags(self, mutate, needle):
        out = copy.deepcopy(GOOD)
        mutate(out)
        found = self.issues(out)
        self.assertTrue(any(needle in i for i in found), f"expected '{needle}' in {found}")

    def test_wrong_schedule(self):
        self.assertFlags(lambda o: o["medicines"][2].update(morning=1), "schedule wrong")

    def test_wrong_strength(self):
        self.assertFlags(lambda o: o["medicines"][1].update(name="Clopidogrel 150 mg", dose="150 mg"), "150")

    def test_missing_medicine(self):
        self.assertFlags(lambda o: o["medicines"].pop(), "medicine left out")

    def test_invented_medicine(self):
        self.assertFlags(lambda o: o["medicines"].append(dict(
            name="Metformin", dose="", form="tablet", morning=1, midday=0, evening=0, night=0, note=None)),
            "not on the letter")

    def test_wrong_written_date(self):
        self.assertFlags(lambda o: o.update(about_one_sentence="Stent placed on 25 June 2022."), "25 June 2022")

    def test_wrong_month(self):
        self.assertFlags(lambda o: o["todos"][0].update(when="until end of June 2023"), "June 2023")

    def test_correct_written_dates_pass(self):
        out = copy.deepcopy(GOOD)
        out["about_one_sentence"] = "On 23 June 2022 a stent was placed. Keep both until May 2023."
        self.assertEqual(self.issues(out), [])

    def test_wrong_amount_with_unit(self):
        # "3" appears elsewhere in the letter, but never as litres
        self.assertFlags(lambda o: o["todos"][1].update(detail="Drink 3 litres a day."), "unit type 'volume'")

    def test_wrong_phone(self):
        self.assertFlags(lambda o: o["contacts"][0].update(phone="1234567"), "phone not in letter")

    def test_bad_source_value(self):
        self.assertFlags(lambda o: o["faq"][0].update(source="maybe"), "source")

    def test_missing_field(self):
        self.assertFlags(lambda o: o.pop("medicines"), "missing 'medicines'")


class ExtractTests(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(run.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_with_prose(self):
        self.assertEqual(run.extract_json('Here you go:\n```json\n{"a": {"b": "}"}}\n```\nDone.'), {"a": {"b": "}"}})

    def test_think_block_and_trailing_text(self):
        self.assertEqual(run.extract_json('<think>{no}</think> {"a": 2} thanks'), {"a": 2})

    def test_no_json(self):
        with self.assertRaises(ValueError):
            run.extract_json("sorry")

    def test_clean_letter_keeps_content(self):
        cleaned = run.clean_letter(LETTER)
        self.assertNotIn("\no\n", cleaned)
        self.assertIn("Dosierschema Freitext: 0 – 0 – 1 – 0; Tablette", cleaned)
        self.assertLess(len(cleaned), len(LETTER))


class FakeAPI(http.server.BaseHTTPRequestHandler):
    """Streams scripted replies. Script items: int = HTTP error code, str = reply text."""
    script, requests = [], []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        FakeAPI.requests.append(body)
        item = FakeAPI.script.pop(0)
        if isinstance(item, int):
            self.send_response(item)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for i in range(0, len(item), 50):
            chunk = {"choices": [{"delta": {"content": item[i:i + 50]}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b'data: {"choices": [], "usage": {"total_tokens": 1}}\n\ndata: [DONE]\n\n')

    def log_message(self, *a):
        pass


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        run.API_URL = f"http://127.0.0.1:{cls.server.server_port}/v1/chat/completions"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeAPI.script, FakeAPI.requests = [], []

    def go(self, script, repairs=2):
        FakeAPI.script = list(script)
        with mock.patch.object(run.time, "sleep"):
            return run.explain(LETTER, "fake-model", repairs=repairs, log=lambda *a: None)

    def test_good_first_try(self):
        out, issues, raws = self.go(["```json\n" + json.dumps(GOOD) + "\n```"])
        self.assertEqual(issues, [])
        self.assertEqual(out, GOOD)
        self.assertEqual(len(FakeAPI.requests), 1)
        self.assertNotIn("\no\n", FakeAPI.requests[0]["messages"][1]["content"])

    def test_repair_round_fixes_wrong_schedule(self):
        bad = copy.deepcopy(GOOD)
        bad["medicines"][2]["morning"] = 1
        out, issues, _ = self.go([json.dumps(bad), json.dumps(GOOD)])
        self.assertEqual(issues, [])
        repair_msg = FakeAPI.requests[1]["messages"][-1]["content"]
        self.assertIn("schedule wrong for Atorvastatin", repair_msg)

    def test_gives_up_and_reports(self):
        bad = copy.deepcopy(GOOD)
        bad["contacts"][0]["phone"] = "999"
        out, issues, _ = self.go([json.dumps(bad)] * 2, repairs=1)
        self.assertTrue(issues)

    def test_invalid_json_then_good(self):
        out, issues, _ = self.go(["I cannot comply", json.dumps(GOOD)])
        self.assertEqual(issues, [])

    def test_retries_gateway_error(self):
        out, issues, _ = self.go([502, 502, json.dumps(GOOD)])
        self.assertEqual(issues, [])
        self.assertEqual(len(FakeAPI.requests), 3)

    def test_falls_back_without_json_mode(self):
        out, issues, _ = self.go([400, json.dumps(GOOD)])
        self.assertEqual(issues, [])
        self.assertIn("response_format", FakeAPI.requests[0])
        self.assertNotIn("response_format", FakeAPI.requests[1])


if __name__ == "__main__":
    unittest.main()
