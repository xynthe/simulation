from decimal import getcontext, ROUND_HALF_UP
from decimal import Decimal as Dec
from typing import Dict, Any


class HavvenManager:
    """
    Class to hold the Havven model's variables
    """

    currency_precision = 8
    """
    Number of decimal places for currency precision.
    The decimal context precision should be significantly higher than this.
    """

    def __init__(
            self,
            havven_settings: Dict[str, Any],
            model: '__import__("model").HavvenModel'
    ) -> None:
        """
        :param havven_settings:
         - havven_supply: the total amount of havvens in the system
         - nomin_supply: the amount of nomins the havven system begins with
         - rolling_avg_time_window: the amount of steps to consider when calculating the
         rolling price average
         - use_volume_weighted_avg: whether to use volume in calculating the rolling price average
        """
        # Set the decimal rounding mode
        getcontext().rounding = ROUND_HALF_UP

        # Initiate Time
        self.time: int = 0

        # Money Supply
        self.havven_supply = Dec(havven_settings['havven_supply'])
        self.nomin_supply = Dec(havven_settings['nomin_supply'])
        self.issued_nomins = Dec(0)

        # Havven's own capital supplies
        self.havvens: Dec = self.havven_supply
        self.nomins: Dec = self.nomin_supply
        self.fiat = Dec(0)

        self.rolling_avg_time_window: int = havven_settings['rolling_avg_time_window']
        self.volume_weighted_average: bool = havven_settings['use_volume_weighted_avg']
        """Whether to calculate the rolling average taking into account the volume of the trades"""

        self.model = model

    @classmethod
    def round_float(cls, value: float) -> Dec:
        """
        Round a float (as a Decimal) to the number of decimal places specified by
        the precision setting.
        Equivalent to Dec(value).quantize(Dec(1e(-cls.currency_precision))).
        """
        return round(Dec(value), cls.currency_precision)

    @classmethod
    def round_decimal(cls, value: Dec) -> Dec:
        """
        Round a Decimal to the number of decimal places specified by
        the precision setting.
        Equivalent to Dec(value).quantize(Dec(1e(-cls.currency_precision))).
        This function really only need be used for products and quotients.
        """
        return round(value, cls.currency_precision)

    @property
    def active_havvens(self):
        active_havvens = sum(i.havvens for i in self.model.schedule.agents if i.escrowed_havvens > 0)
        if active_havvens > 0:
            return active_havvens
        # give some initial value if there are no active ones
        return self.havven_supply

    @property
    def active_nomins(self):
        return self.nomin_supply
