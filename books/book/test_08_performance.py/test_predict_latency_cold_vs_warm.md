# _predict cold vs warm (same query twice)

First call hits cold Aito state; second runs after the
index is in memory. The gap shows Aito-side caching.


## vendor = Kardex Finland Oy

first call:
0.388 ms (was 179.316 ms)
second call:
0.449 ms (was 167.394 ms)
  same top GL: True
