"""Synthetic observations with independently stated arithmetic expectations."""
from codex_limit_tools.usage import FIELDS


def metrics(cost=0, tokens=0, unpriced=0):
    value = dict.fromkeys(FIELDS, 0)
    value.update(cost=cost, cost_input=cost, input=tokens, noncached=tokens,
                 priced_tokens=tokens-unpriced, unpriced_tokens=unpriced,
                 models={'synthetic': {'tokens': tokens, 'cost': cost, 'responses': 0}})
    return value


def snapshot(ident, ts, used, cost=0, tokens=0, unpriced=0, reset_at=9999999999):
    return dict(id=ident, ts=ts, used=used, reset_at=reset_at,
                metrics=metrics(cost, tokens, unpriced))


def segment(ident=1, run_id='run-a', reason='baseline', **keys):
    return dict(id=ident, run_id=run_id, reason=reason, label=keys.get('label', 'synthetic'),
                price_hash=keys.get('price_hash', 'price-a'),
                config={'meter_hash': keys.get('meter_hash', 'meter-a'),
                        'resolution': 1, 'min_points': 5})


# 73% -> 40% remaining: 33 pp, $132, 3,300 tokens => $400 and 10,000 tokens / 100%.
LARGE = [snapshot(1, 100, 27), snapshot(2, 400, 60, 132, 3300)]
# Unequal segments: 1 pp/$10 plus 9 pp/$18 => 10 pp/$28 => $280, not $600.
UNEVEN = [[snapshot(3, 500, 10), snapshot(4, 800, 11, 10, 100)],
          [snapshot(5, 900, 20), snapshot(6, 1200, 29, 18, 900)]]
# Reset and pause gaps have no measurable matched consumption.
RESET = [snapshot(7, 1300, 90, 30, 1000), snapshot(8, 1600, 1, 31, 1100, reset_at=9999999998)]
PAUSE = [[snapshot(9, 1700, 10), snapshot(10, 1800, 11, 2, 100)],
         [snapshot(11, 2100, 20, 10, 300), snapshot(12, 2200, 22, 14, 500)]]
# Midnight crossing belongs to the ending day; a zero-pp interval still has $2/100 tokens.
MIDNIGHT = [snapshot(13, 86300, 10), snapshot(14, 86500, 10, 2, 100),
            snapshot(15, 86800, 12, 8, 400)]
# 50% of tokens priced: $20 subtotal / 10 pp => partial $200; token estimate 2,000.
PARTIAL = [snapshot(16, 2300, 10), snapshot(17, 2600, 20, 20, 200, 100)]
