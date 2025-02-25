import requests
from bs4 import BeautifulSoup
import smtplib
import time
import csv
from datetime import datetime

class PriceTracker:
    def __init__(self, url, product_name, target_price):
        self.url = url
        self.product_name = product_name
        self.target_price = target_price
        self.price_history = []
        
    def check_price(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
        }
        
        page = requests.get(self.url, headers=headers)
        soup = BeautifulSoup(page.content, 'html.parser')
        
        # This selector would need to be adjusted based on the actual website
        price_element = soup.select_one('span.price')
        if price_element:
            price_text = price_element.get_text().strip()
            price = float(price_text.replace('$', '').replace(',', ''))
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.price_history.append({"timestamp": timestamp, "price": price})
            
            self.save_to_csv()
            
            if price <= self.target_price:
                self.send_email(price)
                
            return price
        return None
    
    def save_to_csv(self):
        with open(f"{self.product_name}_price_history.csv", 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "price"])
            writer.writeheader()
            writer.writerows(self.price_history)
    
    def send_email(self, current_price):
        sender = "your_email@gmail.com"
        receiver = "your_email@gmail.com"
        password = "your_app_password"  # Use app password for Gmail
        
        subject = f"Price Alert: {self.product_name}"
        body = f"The price of {self.product_name} has dropped to ${current_price}!\nCheck it out: {self.url}"
        
        message = f"Subject: {subject}\n\n{body}"
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, receiver, message)
            print("Email alert sent!")

def main():
    # Example usage
    products = [
        {
            "url": "https://www.example.com/product1",
            "name": "Smartphone",
            "target_price": 299.99
        },
        {
            "url": "https://www.example.com/product2",
            "name": "Headphones",
            "target_price": 79.99
        }
    ]
    
    trackers = [PriceTracker(p["url"], p["name"], p["target_price"]) for p in products]
    
    while True:
        for tracker in trackers:
            price = tracker.check_price()
            if price:
                print(f"Current price of {tracker.product_name}: ${price}")
            else:
                print(f"Could not fetch price for {tracker.product_name}")
        
        # Check prices every 12 hours
        time.sleep(43200)

if __name__ == "__main__":
    main()
