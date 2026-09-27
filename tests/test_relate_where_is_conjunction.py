"""A relate condition with several keys must reach Aito as an explicit $and.

Measured on 2.10.3: in a v2 `_query` relate, a `where` dict with several
keys keeps ONE of them and silently drops the rest, with a 200. Overrides,
CUST-0000, the condition field=gl_code AND corrected_value=5200 AND
customer_id=CUST-0000 (exact count 67):

    where as a plain dict   fCondition 947   <- customer_id only
    where as explicit $and  fCondition  67   <- correct

That is why every emerging-pattern row on /quality/overrides read the
identical "184 matching overrides · lift 7.7x": each row's query lost its
`corrected_value` and `field`, so all of them ran the same relate.
"""

from src.aito_v2_client import AitoV2Client


class RecordingV2Client(AitoV2Client):
    def __init__(self):
        super().__init__("https://example.invalid/db/x", "k", env=None)
        self.bodies: list[dict] = []

    def _request(self, method, path, json=None, timeout=None):
        self.bodies.append(json)
        return {"hits": []}


def test_a_multi_key_relate_condition_is_sent_as_and():
    c = RecordingV2Client()

    c.relate("overrides",
             {"field": "gl_code", "corrected_value": "5200", "customer_id": "CUST-0000"},
             "invoice_id.vendor")

    where = c.bodies[0]["where"]
    assert set(where) == {"$and"}, where
    assert {"corrected_value": "5200"} in where["$and"]
    assert {"customer_id": "CUST-0000"} in where["$and"]
    assert {"field": "gl_code"} in where["$and"]


def test_a_single_key_condition_is_left_alone():
    """One key already means what it says; wrapping it changes nothing."""
    c = RecordingV2Client()

    c.relate("overrides", {"field": "gl_code"}, "corrected_value")

    assert c.bodies[0]["where"] == {"field": "gl_code"}


def test_the_population_inside_on_is_a_conjunction_too():
    """relate_features puts the population inside `$on`; the same drop
    would silently widen the population a diagnosis is computed over."""
    c = RecordingV2Client()

    c.relate_features("invoices",
                      {"customer_id": "CUST-0000", "vendor": "Kardex Finland Oy"},
                      {"gl_code": "4400"},
                      ["category"])

    population = c.bodies[0]["where"]["$on"][1]
    assert set(population) == {"$and"}, population
