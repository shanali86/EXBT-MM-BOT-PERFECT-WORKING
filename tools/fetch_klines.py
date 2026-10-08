import requests
import json

def test():
    r = requests.get('https://api.lbkex.com/v2/kline.do?symbol=exbt_usdt&size=5&type=minute15', timeout=8).json()
    print("Keys in response:", r.keys())
    data = r.get('data')
    print("Type of data:", type(data))
    if isinstance(data, list) and len(data) > 0:
        print("First 3 items:")
        for item in data[:3]:
            print(item)
    elif isinstance(data, dict):
        print("Data dict keys:", data.keys())

if __name__ == '__main__':
    test()

