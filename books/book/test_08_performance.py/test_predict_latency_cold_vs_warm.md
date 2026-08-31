# _predict cold vs warm (same query twice)

First call hits cold Aito state; second runs after the
index is in memory. The gap shows Aito-side caching.


## vendor = Kardex Finland Oy

first call:
0.531 ms
second call:
2.186 ms
  same top GL: True
