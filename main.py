from app import Client
from loguru import logger

if __name__ == '__main__':
    try:
        with Client(wait_time=0.3, download_workers=5) as client:
            while True:
                client.start()

    except KeyboardInterrupt:
        logger.info("Exit!")
        exit(0)
