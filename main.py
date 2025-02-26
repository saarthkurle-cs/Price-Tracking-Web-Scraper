import requests
from bs4 import BeautifulSoup
import smtplib
import time
import csv
import os
import json
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import concurrent.futures
import argparse
import matplotlib.pyplot as plt
from dotenv import load_dotenv


class PriceTracker:
    def __init__(self, url, product_name, target_price, selector=None):
        self.url = url
        self.product_name = product_name
        self.target_price = target_price
        self.price_history = []
        self.selector = selector or 'span.price'
        self.data_dir = "price_data"
        
        # Create data directory if it doesn't exist
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        # Load price history if it exists
        self._load_price_history()
        
    def _load_price_history(self):
        csv_path = os.path.join(self.data_dir, f"{self.product_name}_price_history.csv")
        if os.path.exists(csv_path):
            try:
                with open(csv_path, 'r', newline='') as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        row['price'] = float(row['price'])
                        self.price_history.append(row)
                logging.info(f"Loaded {len(self.price_history)} historical price points for {self.product_name}")
            except Exception as e:
                logging.error(f"Error loading price history: {e}")

    def check_price(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"
        }
        
        try:
            page = requests.get(self.url, headers=headers, timeout=30)
            page.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            soup = BeautifulSoup(page.content, 'html.parser')
            
            # This selector would need to be adjusted based on the actual website
            price_element = soup.select_one(self.selector)
            if price_element:
                price_text = price_element.get_text().strip()
                # More robust price extraction
                price = self._extract_price(price_text)
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                current_data = {"timestamp": timestamp, "price": price}
                self.price_history.append(current_data)
                
                self.save_to_csv()
                
                # Only send email if price has dropped below target
                if price <= self.target_price:
                    self.send_email(price)
                    
                # Check if this is a price drop
                if len(self.price_history) > 1 and price < self.price_history[-2]['price']:
                    logging.info(f"Price drop detected for {self.product_name}: ${self.price_history[-2]['price']} -> ${price}")
                
                return price
            else:
                logging.warning(f"Price element not found for {self.product_name} using selector: {self.selector}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching {self.url}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error processing {self.product_name}: {e}")
            
        return None
    
    def _extract_price(self, price_text):
        """More robust price extraction that handles different formats"""
        # Remove currency symbols, commas, and spaces
        clean_text = ''.join(c for c in price_text if c.isdigit() or c == '.')
        # Find the last occurrence of a valid decimal number pattern
        parts = clean_text.split('.')
        if len(parts) > 1:
            # Take the last decimal point as the actual one
            whole = ''.join(parts[:-1])
            decimal = parts[-1]
            return float(f"{whole}.{decimal}")
        return float(clean_text)
        
    def save_to_csv(self):
        csv_path = os.path.join(self.data_dir, f"{self.product_name}_price_history.csv")
        with open(csv_path, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "price"])
            writer.writeheader()
            writer.writerows(self.price_history)
    
    def send_email(self, current_price):
        # Get email configuration from environment variables
        sender = os.getenv("EMAIL_SENDER")
        receiver = os.getenv("EMAIL_RECEIVER") or sender
        password = os.getenv("EMAIL_PASSWORD")
        
        if not all([sender, receiver, password]):
            logging.error("Email configuration incomplete. Check your .env file.")
            return False
            
        try:
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = receiver
            msg['Subject'] = f"Price Alert: {self.product_name}"
            
            # Create a nicer HTML email
            email_content = f"""
            <html>
            <body>
                <h2>Price Alert for {self.product_name}</h2>
                <p>Good news! The price has dropped to <strong>${current_price:.2f}</strong></p>
                <p>This is below your target price of <strong>${self.target_price:.2f}</strong></p>
                <p><a href="{self.url}">Click here to view the product</a></p>
                <hr>
                <p><small>This alert was sent from your Price Tracker application.</small></p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(email_content, 'html'))
            
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)
                
            logging.info(f"Email alert sent for {self.product_name}!")
            return True
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False
            
    def generate_price_chart(self):
        """Generate a price history chart"""
        if len(self.price_history) < 2:
            logging.warning(f"Not enough price data to generate chart for {self.product_name}")
            return None
            
        dates = [datetime.strptime(item['timestamp'], "%Y-%m-%d %H:%M:%S") for item in self.price_history]
        prices = [item['price'] for item in self.price_history]
        
        plt.figure(figsize=(10, 6))
        plt.plot(dates, prices, marker='o', linestyle='-')
        plt.title(f"Price History for {self.product_name}")
        plt.xlabel("Date")
        plt.ylabel("Price ($)")
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        chart_path = os.path.join(self.data_dir, f"{self.product_name}_price_chart.png")
        plt.savefig(chart_path)
        plt.close()
        
        logging.info(f"Price chart generated for {self.product_name}")
        return chart_path


class PriceTrackerManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.trackers = []
        self.load_config()
        
    def load_config(self):
        """Load product configuration from JSON file"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as file:
                    config = json.load(file)
                    
                # Reset trackers
                self.trackers = []
                
                # Create tracker for each product
                for product in config.get('products', []):
                    tracker = PriceTracker(
                        url=product['url'],
                        product_name=product['name'],
                        target_price=product['target_price'],
                        selector=product.get('selector', 'span.price')
                    )
                    self.trackers.append(tracker)
                    
                logging.info(f"Loaded {len(self.trackers)} product trackers from config")
            except Exception as e:
                logging.error(f"Error loading configuration: {e}")
        else:
            logging.warning(f"Config file {self.config_path} not found")
            
    def save_config(self):
        """Save current configuration to JSON file"""
        config = {
            "products": [
                {
                    "url": tracker.url,
                    "name": tracker.product_name,
                    "target_price": tracker.target_price,
                    "selector": tracker.selector
                }
                for tracker in self.trackers
            ]
        }
        
        with open(self.config_path, 'w') as file:
            json.dump(config, file, indent=4)
        
        logging.info(f"Configuration saved with {len(self.trackers)} products")
            
    def add_product(self, url, name, target_price, selector=None):
        """Add a new product to track"""
        tracker = PriceTracker(url, name, target_price, selector)
        self.trackers.append(tracker)
        self.save_config()
        return tracker
        
    def remove_product(self, product_name):
        """Remove a product from tracking"""
        self.trackers = [t for t in self.trackers if t.product_name != product_name]
        self.save_config()
        
    def check_all_prices(self, parallel=True):
        """Check prices for all products, optionally in parallel"""
        results = {}
        
        if parallel and len(self.trackers) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_tracker = {executor.submit(tracker.check_price): tracker for tracker in self.trackers}
                
                for future in concurrent.futures.as_completed(future_to_tracker):
                    tracker = future_to_tracker[future]
                    try:
                        price = future.result()
                        results[tracker.product_name] = price
                    except Exception as e:
                        logging.error(f"Error checking price for {tracker.product_name}: {e}")
                        results[tracker.product_name] = None
        else:
            for tracker in self.trackers:
                price = tracker.check_price()
                results[tracker.product_name] = price
                
        return results


def setup_logging():
    """Configure logging"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    log_file = os.path.join(log_dir, f"price_tracker_{datetime.now().strftime('%Y%m%d')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Price Tracker Application")
    parser.add_argument("--config", default="config.json", help="Path to configuration file")
    parser.add_argument("--interval", type=int, default=43200, help="Check interval in seconds (default: 12 hours)")
    parser.add_argument("--once", action="store_true", help="Check prices once and exit")
    parser.add_argument("--chart", action="store_true", help="Generate price history charts")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Add product command
    add_parser = subparsers.add_parser("add", help="Add a new product to track")
    add_parser.add_argument("--url", required=True, help="Product URL")
    add_parser.add_argument("--name", required=True, help="Product name")
    add_parser.add_argument("--target", type=float, required=True, help="Target price")
    add_parser.add_argument("--selector", help="CSS selector for price element")
    
    # Remove product command
    remove_parser = subparsers.add_parser("remove", help="Remove a product from tracking")
    remove_parser.add_argument("--name", required=True, help="Product name to remove")
    
    return parser.parse_args()


def main():
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging()
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Create tracker manager
    manager = PriceTrackerManager(config_path=args.config)
    
    # Handle commands
    if args.command == "add":
        tracker = manager.add_product(args.url, args.name, args.target, args.selector)
        price = tracker.check_price()
        if price:
            logging.info(f"Added {args.name} with current price: ${price}")
        else:
            logging.warning(f"Added {args.name} but could not fetch initial price")
        return
    elif args.command == "remove":
        manager.remove_product(args.name)
        logging.info(f"Removed {args.name} from tracking")
        return
    
    # Generate charts if requested
    if args.chart:
        for tracker in manager.trackers:
            chart_path = tracker.generate_price_chart()
            if chart_path:
                logging.info(f"Generated chart for {tracker.product_name} at {chart_path}")
    
    # Check prices once or run continuous monitoring
    if args.once:
        results = manager.check_all_prices()
        for name, price in results.items():
            if price:
                logging.info(f"Current price of {name}: ${price}")
            else:
                logging.warning(f"Could not fetch price for {name}")
    else:
        logging.info(f"Starting price monitoring with {len(manager.trackers)} products")
        logging.info(f"Check interval: {args.interval} seconds")
        
        try:
            while True:
                results = manager.check_all_prices()
                
                success_count = sum(1 for price in results.values() if price is not None)
                logging.info(f"Checked {len(results)} products, {success_count} successful")
                
                # Sleep until next check
                time.sleep(args.interval)
        except KeyboardInterrupt:
            logging.info("Price monitoring stopped by user")


if __name__ == "__main__":
    main()
