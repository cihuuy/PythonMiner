# Python Verus Coin Solo Miner
import socket
import threading
import json
import hashlib
import logging
import random
import traceback
import psutil
from datetime import datetime
from signal import SIGINT, signal
from colorama import Back, Fore, Style
from tqdm import tqdm

# Set pool address and port
pool_address = "mirazh-28139.portmap.host"
pool_port = 28139

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

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
        except Exception as e:
            logging.error(f"Failed to connect to {self.address}:{self.port} - {str(e)}")
            logging.error("Failed to connect and initialize client. Exiting.")
            raise

    def subscribe(self):
        try:
            request = {
                "id": 1,
                "method": "mining.subscribe",
                "params": ["python_stratum_miner/1.0"]
            }
            self.send_message(request)
            response = self.receive_message()
            self.extranonce1, self.extranonce2_size = response['result'][1], response['result'][2]
            self.subscribed = True
            logging.info("Subscribed to stratum server")
        except Exception as e:
            logging.error(f"Subscribe response does not contain expected data - {str(e)}")
            logging.error(f"Failed to connect to {self.address}:{self.port} - Subscribe response does not contain expected data")
            raise

    def authorize(self):
        try:
            request = {
                "id": 2,
                "method": "mining.authorize",
                "params": [self.miner_name, ""]
            }
            self.send_message(request)
            response = self.receive_message()
            if response['result']:
                logging.info("Authorized worker")
            else:
                logging.error("Failed to authorize worker")
                raise Exception("Authorization failed")
        except Exception as e:
            logging.error(f"Failed to authorize worker - {str(e)}")
            raise

    def send_message(self, message):
        self.socket.sendall(json.dumps(message).encode() + b'\n')

    def receive_message(self):
        response = self.socket.recv(1024)
        return json.loads(response.decode())

    def request_job(self):
        try:
            request = {
                "id": 3,
                "method": "mining.get_job",
                "params": []
            }
            self.send_message(request)
            response = self.receive_message()
            self.handle_job(response.get('result', []))
        except Exception as e:
            logging.error(f"Error requesting job - {str(e)}")
            raise

    def handle_job(self, response):
        method = response.get('method')
        params = response.get('params', [])

        if method == 'mining.set_target':
            if len(params) > 0:
                self.target = params[0]
                logging.info(f"Set target: {self.target}")
            else:
                logging.error("Empty target parameter in mining.set_target method")
        elif method == 'mining.notify':
            try:
                if params and len(params) >= 9:
                    (
                        self.job_id, self.previous_block_hash, self.coinbase_value, self.target,
                        self.transactions, self.version, self.bits, self.height, self.curtime
                    ) = params
                    logging.info(f"Received job: {self.job_id}")
                    logging.info(f"Previous block hash: {self.previous_block_hash}")
                    logging.info(f"Coinbase value: {self.coinbase_value}")
                    logging.info(f"Target: {self.target}")
                    logging.info(f"Transactions: {self.transactions}")
                    logging.info(f"Version: {self.version}")
                    logging.info(f"Bits: {self.bits}")
                    logging.info(f"Height: {self.height}")
                    logging.info(f"Curtime: {self.curtime}")
                else:
                    logging.error("Invalid parameters in mining.notify method")
            except ValueError as e:
                logging.error(f"Error parsing job response: {e}")
                raise
        else:
            logging.error(f"Unknown method in job response: {method}")

# Main function
if __name__ == "__main__":
    try:
        # Create Stratum client
        client = StratumClient(pool_address, pool_port, "RP6jeZhhHiZmzdufpXHCWjYVHsLaPXARt1.py1")
        
        # Connect to the pool
        client.connect()

        # Get number of CPU threads
        num_threads = psutil.cpu_count(logical=True)
        threads = []

        # Start mining threads
        for thread_id in range(num_threads):
            thread = threading.Thread(target=mine_thread, args=(thread_id, client))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

    except Exception as e:
        logging.error(f"Main thread error: {str(e)}")
        traceback.print_exc()
