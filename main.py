from app import Client
from loguru import logger

if __name__ == '__main__':
    try:
        client = Client(wait_time=0.3)
        while True:
            client.start()

    except KeyboardInterrupt:
        logger.info("Exit!")
        exit(0)
