from app import Client
import loguru

if __name__ == '__main__':
    try:
        client = Client(wait_time=0.3)
        while True:
            client.start()

    except KeyboardInterrupt:
        loguru.logger.info("Exit!")
        exit(0)
