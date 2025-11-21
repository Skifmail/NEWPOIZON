import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

wc_url = os.getenv('WC_URL')
wc_key = os.getenv('WC_CONSUMER_KEY')
wc_secret = os.getenv('WC_CONSUMER_SECRET')

sku = "27635742"
url = f"{wc_url}/wp-json/wc/v3/products?sku={sku}"
response = requests.get(url, auth=(wc_key, wc_secret), verify=False)

if response.status_code == 200:
    products = response.json()
    if products:
        product = products[0]
        print(f"Found product ID: {product['id']}")
        print(f"Name: {product['name']}")
    else:
        print("Product not found")
else:
    print(f"Error: {response.status_code}")
