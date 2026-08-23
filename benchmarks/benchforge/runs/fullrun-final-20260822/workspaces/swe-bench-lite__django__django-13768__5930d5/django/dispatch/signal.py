import logging

logger = logging.getLogger(__name__)


class Signal:
    """
    Base class for all signals
    """

    def __init__(self, providing_args=None):
        """
        Create a new signal.
        """
        # ... existing __init__ code ...

    def send_robust(self, sender, **named):
        """
        Send signal to all receivers, catching exceptions.
        """
        responses = []
        for receiver in self._live_receivers(sender):
            try:
                response = receiver(signal=self, sender=sender, **named)
                responses.append((receiver, response))
            except Exception as err:
                logger.exception(
                    'Signal %s received exception from receiver %s',
                    self, receiver
                )
                responses.append((receiver, err))
        return responses
