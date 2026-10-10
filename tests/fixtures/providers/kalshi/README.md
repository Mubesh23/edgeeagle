# Kalshi fixtures

The fixed-point order-book fixture in `orderbook-v1/` is authored synthetic
data shaped from Kalshi's public order-book contract. It is not a downloaded
capture and conveys no historical availability, canonical market mapping, or
execution eligibility. Its explicit ticker and snapshot time are test bindings;
the provider response itself does not contain them.

The parser is offline and reads retained bytes through the shared raw-payload
store. It does not call Kalshi or require credentials.
