import logging
import os


logger = logging.getLogger(__name__)


def greet(name: str) -> None:
    """Print greeting for person

    :param name: Name of person to greet
    :return: None
    """
    print(f"Hello {name}!")
    logger.debug("Done")


def main():
    import fire  # type: ignore

    logging.basicConfig(level=getattr(logging, os.environ.get("LEVEL", "WARNING")))
    fire.Fire({func.__name__: func for func in [greet]})
