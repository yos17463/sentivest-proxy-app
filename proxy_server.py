import os
import requests
import time
import random
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# RapidAPI Key for Yahoo Finance API
# This will be injected by Render from the environment variable
RAPIDAPI_KEY_YAHOO_FINANCE = os.environ.get('RAPIDAPI_KEY_YAHOO_FINANCE')
RAPIDAPI_HOST_YAHOO_FINANCE = "yahoo-finance15.p.rapidapi.com"

# --- Mock Data Generation Functions ---
# Function to generate mock historical data for charts
def generate_mock_historical_data(start_price, num_points=30, volatility=0.015):
    data = []
    current_price = start_price
    for _ in range(num_points):
        data.append(current_price)
        change = (random.random() - 0.5) * volatility * current_price * 2
        current_price += change
        if current_price <= 0: # Ensure price doesn't go below zero
            current_price = start_price * 0.5 # Reset or set to a reasonable floor
    return data

# Function to generate mock stock data (Finnhub candle-like)
def generate_mock_stock_data(symbol):
    base_price = random.uniform(50, 250)
    return {
        "c": generate_mock_historical_data(base_price), # Close prices
        "h": [p * 1.02 for p in generate_mock_historical_data(base_price)], # High prices
        "l": [p * 0.98 for p in generate_mock_historical_data(base_price)], # Low prices
        "o": [p * 1.01 for p in generate_mock_historical_data(base_price)], # Open prices
        "v": [random.randint(100000, 5000000) for _ in range(30)], # Volume
        "t": [int(time.time()) - (29 - i) * 24 * 60 * 60 for i in range(30)], # Unix timestamps
        "s": "ok" # OK status
    }

# Function to generate mock profile data (Finnhub profile2-like)
def generate_mock_profile_data(symbol):
    return {
        "country": "US",
        "currency": "USD",
        "exchange": "NASDAQ",
        "finnhubIndustry": "Technology",
        "ipo": "2000-01-01",
        "logo": "https://placehold.co/60x60/cccccc/ffffff?text=LOGO", # Placeholder image
        "marketCapitalization": random.uniform(10000, 1000000), # In millions
        "name": f"{symbol} Corp (Mock)", # Mock name
        "phone": "1-800-MOCK",
        "shareOutstanding": random.uniform(100, 1000), # In millions
        "weburl": "https://example.com",
        "ticker": symbol,
        "peRatio": random.uniform(10, 40) # Mock P/E ratio
    }
# --- End Mock Data Generation Functions ---

@app.route('/finnhub-proxy/stock/candle')
def stock_candle():
    symbol = request.args.get('symbol')
    resolution = request.args.get('resolution')
    _from = request.args.get('from')
    _to = request.args.get('to')

    if not all([symbol, resolution, _from, _to]):
        return jsonify({"error": "Missing parameters"}), 400

    url = f"https://yahoo-finance15.p.rapidapi.com/stock/v2/get-historical-data?symbol={symbol}&region=US&range=1mo&interval=1d"
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY_YAHOO_FINANCE,
        "X-RapidAPI-Host": RAPIDAPI_HOST_YAHOO_FINANCE
    }

    try:
        print(f"DEBUG: Fetching candle data for {symbol} from Yahoo Finance: {url}") # Log the URL
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        if 'prices' in data and isinstance(data['prices'], list):
            valid_prices = [p for p in data['prices'] if 'close' in p and p['close'] is not None]
            
            if not valid_prices:
                print(f"DEBUG: No valid price data in Yahoo Finance response for {symbol}. Returning mock data.")
                return jsonify(generate_mock_stock_data(symbol)), 200

            c = [p['close'] for p in valid_prices]
            h = [p['high'] for p in valid_prices]
            l = [p['low'] for p in valid_prices]
            o = [p['open'] for p in valid_prices]
            v = [p['volume'] for p in valid_prices]
            t = [int(p['date']) for p in valid_prices]

            print(f"DEBUG: Successfully fetched and formatted candle data for {symbol}.")
            return jsonify({
                "c": c, "h": h, "l": l, "o": o, "v": v, "t": t, "s": "ok"
            }), 200 # Explicitly return 200 OK for success
        else:
            print(f"DEBUG: Unexpected Yahoo Finance response structure for {symbol}. Returning mock data.")
            return jsonify(generate_mock_stock_data(symbol)), 200

    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTPError fetching candle data from Yahoo Finance for {symbol}: {e}")
        if e.response.status_code in [403, 429]:
            print(f"DEBUG: Returning mock data for {symbol} due to {e.response.status_code} error.")
            return jsonify(generate_mock_stock_data(symbol)), 200 
        print(f"ERROR: Returning original HTTPError for {symbol}: {e.response.status_code}")
        return jsonify({"error": str(e), "status_code": e.response.status_code}), e.response.status_code
    except requests.exceptions.RequestException as e: # Catch all requests exceptions (ConnectionError, Timeout, etc.)
        print(f"ERROR: RequestException for Yahoo Finance for {symbol}: {e}")
        print(f"DEBUG: Returning mock data for {symbol} due to request error.")
        return jsonify(generate_mock_stock_data(symbol)), 200
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred for {symbol} in stock_candle: {e}")
        print(f"DEBUG: Returning mock data for {symbol} due to unexpected error.")
        return jsonify(generate_mock_stock_data(symbol)), 200

@app.route('/finnhub-proxy/stock/profile2')
def stock_profile2():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"error": "Missing symbol parameter"}), 400

    url = f"https://yahoo-finance15.p.rapidapi.com/stock/v2/get-profile?symbol={symbol}"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY_YAHOO_FINANCE,
        "X-RapidAPI-Host": RAPIDAPI_HOST_YAHOO_FINANCE
    }

    try:
        print(f"DEBUG: Fetching profile data for {symbol} from Yahoo Finance: {url}") # Log the URL
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if 'assetProfile' in data and data['assetProfile']:
            profile = data['assetProfile']
            print(f"DEBUG: Successfully fetched and formatted profile data for {symbol}.")
            return jsonify({
                "country": profile.get("country"),
                "currency": profile.get("currency"),
                "exchange": profile.get("exchange"),
                "finnhubIndustry": profile.get("industry"),
                "ipo": profile.get("ipoDate"),
                "logo": profile.get("logo_url") or "https://placehold.co/60x60/cccccc/ffffff?text=LOGO",
                "marketCapitalization": profile.get("marketCap"),
                "name": profile.get("longBusinessSummary") or profile.get("shortName"),
                "phone": profile.get("phone"),
                "shareOutstanding": profile.get("sharesOutstanding"),
                "weburl": profile.get("website"),
                "ticker": symbol,
                "peRatio": random.uniform(10, 40)
            }), 200 # Explicitly return 200 OK for success
        else:
            print(f"DEBUG: No valid profile data in Yahoo Finance response for {symbol}. Returning mock data.")
            return jsonify(generate_mock_profile_data(symbol)), 200

    except requests.exceptions.HTTPError as e:
        print(f"ERROR: HTTPError fetching profile data from Yahoo Finance for {symbol}: {e}")
        if e.response.status_code in [403, 429]:
            print(f"DEBUG: Returning mock data for {symbol} due to {e.response.status_code} error.")
            return jsonify(generate_mock_profile_data(symbol)), 200 
        print(f"ERROR: Returning original HTTPError for {symbol}: {e.response.status_code}")
        return jsonify({"error": str(e), "status_code": e.response.status_code}), e.response.status_code
    except requests.exceptions.RequestException as e: # Catch all requests exceptions
        print(f"ERROR: RequestException for Yahoo Finance for {symbol}: {e}")
        print(f"DEBUG: Returning mock data for {symbol} due to request error.")
        return jsonify(generate_mock_profile_data(symbol)), 200
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred for {symbol} in stock_profile2: {e}")
        print(f"DEBUG: Returning mock data for {symbol} due to unexpected error.")
        return jsonify(generate_mock_profile_data(symbol)), 200

if __name__ == '__main__':
    # For local testing, use the port assigned by Render or a default of 8000
    # Render automatically sets the 'PORT' environment variable
    port = int(os.environ.get('PORT', 8000)) # Re-added 8000 as default for local testing
    app.run(host='0.0.0.0', port=port, debug=True)
