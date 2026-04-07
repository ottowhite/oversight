import logging
import itertools

def get_logger():
	logging.basicConfig(
	    level=logging.INFO,
	    format='[%(levelname)s] %(asctime)s - %(message)s',
	    handlers=[
	        logging.StreamHandler()
	    ]
	)

	return logging.getLogger(__name__)

def chunked_iterable(iterable, size):
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk