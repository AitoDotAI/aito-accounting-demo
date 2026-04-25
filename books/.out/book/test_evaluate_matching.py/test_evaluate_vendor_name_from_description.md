# _evaluate: vendor_name from description

Vendor resolution should be much easier — there are only 17
vendors and the description text contains vendor name tokens.


## Results

  Accuracy:      83.3%
  Base accuracy: 3.3%
  Accuracy gain: 80.0%
  Mean rank:     15.0 / 17 vendors
  Test samples:  30
  Geom mean p:   0.2491

Vendor resolution works well because description tokens
(kesko, telia, sok) directly identify the vendor.
