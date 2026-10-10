import sys
import json
import traceback
sys.path.append('d:/projects/fintech')
from app import app
from fintech import market
from fintech import trend_following

try:
    symbol = 'VPB'
    candles, _ = market.get_candles(symbol)
    tf = trend_following.analyze_trend_following(symbol, candles, {}, {})
    print("Success")
except Exception as e:
    traceback.print_exc()

