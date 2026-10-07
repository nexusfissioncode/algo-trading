# Strategy: your strategy's name

Write each rule so a machine could check it: a number, a comparison, a timeframe.
Delete these two lines and fill in each section.

## Coins
BTC/USD, ETH/USD

## Numbers it needs
- price, and any of: change24h, high24h, low24h, rsiN, smaN, emaN (like rsi14, sma50)
- say the timeframe: 1-hour bars or 1-day bars

## Entry (buy)
1. A condition with a number, like: the 1-hour rsi14 is below 35.

## Do nothing when
1. A condition that overrides the entry, like: the 1-hour change24h is below -8.

## Size
250 dollars per buy.

## Exit (sell the whole position)
1. A condition with a number, like: the price is 3% or more below the average entry.
