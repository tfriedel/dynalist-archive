from loguru import logger

from dynalist_archive import hello


def main() -> None:
    logger.info("Application started")
    print(hello())
    logger.info("Application finished")


if __name__ == "__main__":
    main()
