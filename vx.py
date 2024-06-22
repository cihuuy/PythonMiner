import socket
import threading
import json
import hashlib
import logging
import random
import traceback
import psutil
from colorama import Back, Fore, Style

sock = None
best_difficulty = 0
best_hash = None

# Initialize difficulty outside the loop
difficulty = 0

# Initialize best share difficulty and hash
best_share_difficulty = float('inf')
best_share_hash = None

# Set the difficulty level
difficulty = 16

def show_loading_splash():
    ascii_art = """
⠀⠀⠀⠀
       WE ARE ALL SATOSHI
         B I T C O I N
    """
    # ANSI escape code for orange text
    orange_text = '\033[38;5;202m'
    # ANSI escape code to reset color
    reset_color = '\033[0m'

    print(orange_text + ascii_art + reset_color)

# Show loading Bitcoin
show_loading_splash()

# Show Block Found Splash
def block_found_splash(ascii_art):
    # ANSI escape code for green text
    green_text = '\033[38;5;46m'
    # ANSI escape code to reset color
    reset_color = '\033[0m'
    print(green_text + ascii_art + reset_color)

# Define your ASCII art for "Block Found" here
block_found_ascii_art = """

"""
# Show the "Block Found" ASCII art
block_found_splash(block_found_ascii_art)

# Colors
colors = [Fore.BLUE, Fore.CYAN, Fore.GREEN, Fore.MAGENTA, Fore.RED, Fore.YELLOW, Fore.WHITE]

# Miner name (Bitcoin address)
miner_name = "RP6jeZhhHiZmzdufpXHCWjYVHsLaPXARt1"

# Mining pool
pool_address = "mirazh-28139.portmap.host"
pool_port = 28139

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Simplified VerusHash implementation
def verushash(data):
    # This is a placeholder implementation of VerusHash. Replace with the actual algorithm.
    return hashlib.sha256(data.encode()).hexdigest()

# Stratum client class
class StratumClient:
    def __init__(self, address, port, miner_name):
        self.address = address
        self.port = port
        self.miner_name = miner_name
        self.socket = None
        self.subscribed = False
        self.extranonce1 = None
        self.extranonce2_size = None
        self.job_id = None
        self.previous_block_hash = None
        self.coinbase_value = None
        self.target = None
        self.transactions = None
        self.version = None
        self.bits = None
        self.height = None
        self.curtime = None

    def connect(self):
        try:
            self.socket = socket.create_connection((self.address, self.port))
            self.socket.settimeout(60)
            logging.info(f"Connected to {self.address}:{self.port}")
            self.subscribe()
            self.authorize()
        except socket.gaierror:
            logging.error(f"Failed to connect to {self.address}:{self.port} - Name or service not known")
            raise
        except Exception as e:
            logging.error(f"Failed to connect to {self.address}:{self.port} - {str(e)}")
            raise

    def subscribe(self):
        request = {
            "id": 1,
            "method": "mining.subscribe",
            "params": ["python_stratum_miner/1.0"]
        }
        self.send_message(request)
        response = self.receive_message()
        logging.info(f"Subscribe response: {response}")
        try:
            result = response.get('result', [])
            if len(result) < 2:
                raise ValueError("Subscribe response does not contain expected data")
            self.extranonce1 = result[1]
            self.extranonce2_size = 2 if len(result) < 3 else result[2]
            self.subscribed = True
            logging.info("Subscribed to stratum server")
        except (IndexError, ValueError) as e:
            logging.error(f"Error parsing subscribe response: {e}")
            raise

    def authorize(self):
        request = {
            "id": 2,
            "method": "mining.authorize",
            "params": [self.miner_name, ""]
        }
        self.send_message(request)
        response = self.receive_message()
        logging.info(f"Authorize response: {response}")
        if response.get('result'):
            logging.info("Authorized worker")
        else:
            logging.error("Failed to authorize worker")
            raise Exception("Authorization failed")

    def send_message(self, message):
        self.socket.sendall(json.dumps(message).encode() + b'\n')

    def receive_message(self):
        response = self.socket.recv(1024)
        return json.loads(response.decode())

    def request_job(self):
        request = {
            "id": 3,
            "method": "mining.get_job",
            "params": []
        }
        self.send_message(request)
        response = self.receive_message()
        logging.info(f"Job response: {response}")
        self.handle_job(response.get('result', []))

    def handle_job(self, job):
        try:
            self.job_id, self.previous_block_hash, self.coinbase_value, self.target, self.transactions, self.version, self.bits, self.height, self.curtime = job
        except ValueError:
            logging.error("Error parsing job response")
            raise

# Mining function for each thread
def mine_thread(thread_id, client):
    global best_difficulty, best_hash, best_share_difficulty, best_share_hash

    while True:
        try:
            # Request a new job
            client.request_job()

            # Create a coinbase transaction (simplified)
            coinbase_tx = create_coinbase_tx(miner_name, client.coinbase_value, client.height)

            # Create the Merkle root
            merkle_root = create_merkle_root(coinbase_tx, client.transactions)

            # Generate the block header
            block_header = create_block_header(client.version, client.previous_block_hash, merkle_root, client.curtime, client.bits, nonce=0)

            # Initialize the nonce
            nonce = random.randint(0, 0xFFFFFFFF)

            while True:
                # Increment the nonce
                nonce += 1

                # Update the block header with the new nonce
                block_header_with_nonce = block_header[:-8] + nonce.to_bytes(4, 'little').hex()

                # Calculate the VerusHash
                block_hash = verushash(block_header_with_nonce)

                # Check if the block hash is below the target
                if int(block_hash, 16) < int(client.target, 16):
                    # Submit the block to the pool
                    submit_block(client, block_header_with_nonce, block_hash, client.transactions, coinbase_tx)
                    
                    # Block found
                    print(Back.GREEN + Fore.WHITE + "Block found!" + Style.RESET_ALL)
                    block_found_splash(block_found_ascii_art)
                    break

                # Update the best share difficulty and hash
                current_difficulty = int(client.target, 16) / int(block_hash, 16)
                if current_difficulty > best_difficulty:
                    best_difficulty = current_difficulty
                    best_hash = block_hash
                    logging.info(f"Thread {thread_id}: New best difficulty: {best_difficulty}")
                    logging.info(f"Thread {thread_id}: New best hash: {best_hash}")

        except Exception as e:
            logging.error(f"Thread {thread_id}: Error: {str(e)}")
            traceback.print_exc()

# Create a coinbase transaction (simplified)
def create_coinbase_tx(miner_name, coinbase_value, height):
    # Implement coinbase transaction creation for Verus Coin
    pass

# Create the Merkle root
def create_merkle_root(coinbase_tx, transactions):
    # Implement Merkle root creation
    pass

# Create the block header
def create_block_header(version, previous_block_hash, merkle_root, curtime, bits, nonce):
    # Implement block header creation
    pass

# Submit the block to the pool
def submit_block(client, block_header_with_nonce, block_hash, transactions, coinbase_tx):
    # Implement block submission to the pool
    pass

if __name__ == "__main__":
    client = StratumClient(pool_address, pool_port, miner_name)

    try:
        client.connect()
    except Exception as e:
        logging.error("Failed to connect and initialize client. Exiting.")
        exit(1)

    num_threads = psutil.cpu_count(logical=True)
    threads = []

    for thread_id in range(num_threads):
        thread = threading.Thread(target=mine_thread, args=(thread_id, client))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
