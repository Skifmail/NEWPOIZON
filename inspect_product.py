import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()

wc_url = os.getenv('WC_URL')
wc_key = os.getenv('WC_CONSUMER_KEY')
wc_secret = os.getenv('WC_CONSUMER_SECRET')

url = f"{wc_url}/wp-json/wc/v3/products/25130"
response = requests.get(url, auth=(wc_key, wc_secret), verify=False)

if response.status_code == 200:
    product = response.json()
    print(f"Name: {product['name']}")
    print(f"Slug: {product['slug']}")
    print("Attributes:")
    for attr in product['attributes']:
        print(f"  {attr['name']}: {attr['options']}")
    print("Categories:")
    for cat in product['categories']:
        print(f"  {cat['name']}")
else:
    print(f"Error: {response.status_code}")
