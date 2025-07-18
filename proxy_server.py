# proxy_server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os # ודא ששורה זו קיימת בראש הקובץ
import time
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app) # הפעלת CORS לכל הנתיבים

# הגדר את מפתח ה-API של Yahoo Finance RapidAPI כאן
# מומלץ להשתמש במשתני סביבה לאבטחה טובה יותר
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY_YAHOO_FINANCE") 
if not RAPIDAPI_KEY:
    print("Error: RAPIDAPI_KEY_YAHOO_FINANCE environment variable not set!")
    # עבור בדיקות מקומיות בלבד, אתה יכול להחזיר את המפתח כאן באופן זמני:
    # RAPIDAPI_KEY = "cbd656c561msh6baa29929286c75p19f03fjsn2c289e7e454b" # השאר את זה מוסר לפני פריסה!

RAPIDAPI_HOST_YAHOO_FINANCE = "yahoo-finance15.p.rapidapi.com"
YAHOO_FINANCE_BASE_URL = "https://yahoo-finance15.p.rapidapi.com"

# אין צורך במנגנון בקרת קצב עבור Alpha Vantage יותר

@app.route('/finnhub-proxy/stock/candle', methods=['GET'])
def get_stock_candle():
    """
    נקודת קצה לפרוקסי שמביאה נתוני נרות (candlestick data) מ-Yahoo Finance RapidAPI.
    """
    symbol = request.args.get('symbol')
    resolution = request.args.get('resolution') # D for daily
    from_timestamp = request.args.get('from')
    to_timestamp = request.args.get('to')

    if not all([symbol, resolution, from_timestamp, to_timestamp]):
        return jsonify({"error": "Missing required parameters (symbol, resolution, from, to)"}), 400

    # Yahoo Finance RapidAPI uses a different date format for historical data
    # It expects start_date and end_date in YYYY-MM-DD format
    # The resolution 'D' maps to daily data.
    from_dt = datetime.fromtimestamp(int(from_timestamp))
    to_dt = datetime.fromtimestamp(int(to_timestamp))

    # Yahoo Finance API expects dates, not timestamps, for historical data
    # And it's usually for a specific range, not just 'from' and 'to' for a resolution.
    # The endpoint is /stock/v2/get-historical-data
    # Parameters: symbol, region (e.g., US), range (e.g., 1mo, 3mo, 1y), interval (e.g., 1d, 1wk, 1mo)
    # For simplicity, let's assume 'resolution=D' means we want daily data for the last month.
    # We will fetch for '1mo' range and then filter by timestamp if necessary.
    
    # Let's adjust to use 'range' and 'interval' for Yahoo Finance, as it's more common.
    # The client-side from/to timestamps are for a 30-day range.
    # So, we can request '1mo' range with '1d' interval.
    
    # Yahoo Finance API headers
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST_YAHOO_FINANCE
    }

    try:
        # Using '1mo' range and '1d' interval to cover the client's 30-day request
        yahoo_finance_url = f"{YAHOO_FINANCE_BASE_URL}/stock/v2/get-historical-data?symbol={symbol}&region=US&range=1mo&interval=1d"
        
        print(f"Fetching candle data for {symbol} from Yahoo Finance: {yahoo_finance_url}")
        response = requests.get(yahoo_finance_url, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        yahoo_data = response.json()

        # Check for errors in Yahoo Finance API response
        if not yahoo_data or not yahoo_data.get('prices'):
            error_message = yahoo_data.get('message', 'No prices data found in Yahoo Finance response.')
            print(f"Yahoo Finance returned no prices data for {symbol}. Error: {error_message}")
            return jsonify({"error": "Failed to fetch candle data from Yahoo Finance", "details": error_message}), 500

        # Convert Yahoo Finance data to Finnhub-like format
        finnhub_format = {
            "c": [], # Close prices
            "h": [], # High prices
            "l": [], # Low prices
            "o": [], # Open prices
            "t": [], # Timestamps
            "v": [], # Volume
            "s": "ok"
        }
        
        # Filter and format data points
        for price_data in yahoo_data['prices']:
            # Skip data points that are not regular market hours (e.g., pre/post market) or are null
            if price_data.get('type') == 'regularMarket' and price_data.get('open') is not None:
                timestamp_ms = price_data['date'] # Yahoo returns timestamp in milliseconds
                timestamp_s = timestamp_ms // 1000 # Convert to seconds
                
                # Filter by client's requested timestamp range
                if int(from_timestamp) <= timestamp_s <= int(to_timestamp):
                    finnhub_format["c"].append(price_data['close'])
                    finnhub_format["h"].append(price_data['high'])
                    finnhub_format["l"].append(price_data['low'])
                    finnhub_format["o"].append(price_data['open'])
                    finnhub_format["t"].append(timestamp_s)
                    finnhub_format["v"].append(price_data['volume'])
        
        if len(finnhub_format["c"]) > 0:
            print(f"Successfully fetched and formatted candle data for {symbol} from Yahoo Finance.")
            return jsonify(finnhub_format)
        else:
            print(f"Yahoo Finance returned data but no valid candle data found for {symbol} within the specified range.")
            return jsonify({"error": "Failed to fetch candle data from Yahoo Finance (no valid data in range)", "details": "No valid candle data found within the specified range."}), 500

    except requests.exceptions.RequestException as e:
        error_message = f"Error fetching candle data from Yahoo Finance for {symbol}: {e}"
        print(error_message)
        return jsonify({"error": "Failed to fetch candle data from Yahoo Finance", "details": error_message}), 500
    except Exception as e:
        error_message = f"Unexpected error with Yahoo Finance candle data for {symbol}: {e}"
        print(error_message)
        return jsonify({"error": "Failed to process Yahoo Finance candle data", "details": error_message}), 500


@app.route('/finnhub-proxy/stock/profile2', methods=['GET'])
def get_stock_profile():
    """
    נקודת קצה לפרוקסי שמביאה נתוני פרופיל חברה מ-Yahoo Finance RapidAPI.
    """
    symbol = request.args.get('symbol')

    if not symbol:
        return jsonify({"error": "Missing required parameter (symbol)"}), 400

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST_YAHOO_FINANCE
    }

    try:
        # Using get-statistics for comprehensive profile data
        yahoo_finance_url = f"{YAHOO_FINANCE_BASE_URL}/stock/v2/get-statistics?symbol={symbol}&region=US"
        
        print(f"Fetching profile data for {symbol} from Yahoo Finance: {yahoo_finance_url}")
        response = requests.get(yahoo_finance_url, headers=headers)
        response.raise_for_status()
        yahoo_data = response.json()

        # Check for errors in Yahoo Finance API response
        if not yahoo_data or not yahoo_data.get('quoteType'):
            error_message = yahoo_data.get('message', 'No profile data found in Yahoo Finance response.')
            print(f"Yahoo Finance returned no profile data for {symbol}. Error: {error_message}")
            return jsonify({"error": "Failed to fetch profile data from Yahoo Finance", "details": error_message}), 500

        # Extracting data from Yahoo Finance response and mapping to Finnhub-like format
        # Yahoo Finance returns marketCap as a raw number (e.g., 1000000000000 for 1 Trillion)
        # Finnhub's marketCapitalization is in millions. So, we divide by 1,000,000.
        name = yahoo_data.get('quoteType', {}).get('longName', symbol)
        market_cap_raw = yahoo_data.get('summaryDetail', {}).get('marketCap', {}).get('raw', 0)
        market_capitalization_in_millions = float(market_cap_raw) / 1000000 if market_cap_raw else 0

        pe_ratio_raw = yahoo_data.get('summaryDetail', {}).get('trailingPE', {}).get('raw')
        pe_ratio = float(pe_ratio_raw) if pe_ratio_raw is not None else None

        shares_outstanding_raw = yahoo_data.get('defaultKeyStatistics', {}).get('sharesOutstanding', {}).get('raw')
        shares_outstanding = float(shares_outstanding_raw) if shares_outstanding_raw is not None else None

        finnhub_format = {
            "name": name,
            "marketCapitalization": market_capitalization_in_millions,
            "peRatio": pe_ratio,
            "shareOutstanding": shares_outstanding
        }
        
        print(f"Successfully fetched and formatted profile data for {symbol} from Yahoo Finance.")
        return jsonify(finnhub_format)

    except requests.exceptions.RequestException as e:
        error_message = f"Error fetching profile data from Yahoo Finance for {symbol}: {e}"
        print(error_message)
        return jsonify({"error": "Failed to fetch profile data from Yahoo Finance", "details": error_message}), 500
    except Exception as e:
        error_message = f"Unexpected error with Yahoo Finance profile data for {symbol}: {e}"
        print(error_message)
        return jsonify({"error": "Failed to process Yahoo Finance profile data", "details": error_message}), 500


if __name__ == '__main__':
    # הפעלת השרת על פורט 5000
    app.run(debug=True, port=5000)
