from decimal import Decimal as Dec
from typing import Optional, Callable

import agents as ag
from core import orderbook as ob
from .feemanager import FeeManager
from .havvenmanager import HavvenManager


class MarketManager:
    """
    Handles all order books, trades, transfers, and conversions.
    """

    def __init__(self, model_manager: HavvenManager, fee_manager: FeeManager) -> None:

        self.model_manager = model_manager
        self.fee_manager = fee_manager

        # Order books
        # If a book is X_Y_market, then X is the base currency,
        #   Y is the quote currency.
        # That is, buyers hold Y and sellers hold X.
        self.havven_nomin_market = ob.OrderBook(
            model_manager, "havvens", "nomins", self.havven_nomin_match,
            self.fee_manager.transferred_nomins_fee,
            self.fee_manager.transferred_havvens_fee,
            self.fee_manager.transferred_nomins_received,
            self.fee_manager.transferred_havvens_received
        )
        self.havven_fiat_market = ob.OrderBook(
            model_manager, "havvens", "fiat", self.havven_fiat_match,
            self.fee_manager.transferred_fiat_fee,
            self.fee_manager.transferred_havvens_fee,
            self.fee_manager.transferred_fiat_received,
            self.fee_manager.transferred_havvens_received
        )
        self.nomin_fiat_market = ob.OrderBook(
            model_manager, "nomins", "fiat", self.nomin_fiat_match,
            self.fee_manager.transferred_fiat_fee,
            self.fee_manager.transferred_nomins_fee,
            self.fee_manager.transferred_fiat_received,
            self.fee_manager.transferred_nomins_received
        )

    def __bid_ask_match(
            self, bid: "ob.Bid", ask: "ob.Ask",
            bid_success: Callable[["ag.MarketPlayer", Dec, Dec], bool],
            ask_success: Callable[["ag.MarketPlayer", Dec, Dec], bool],
            bid_transfer: Callable[["ag.MarketPlayer", "ag.MarketPlayer", Dec, Dec], bool],
            ask_transfer: Callable[["ag.MarketPlayer", "ag.MarketPlayer", Dec, Dec], bool]
    ) -> Optional["ob.TradeRecord"]:
        """
        If possible, match the given bid and ask, with the given transfer
          and success functions.
        Cancel any orders which an agent cannot afford to service.
        Return a TradeRecord object if the match succeeded, otherwise None.
        """

        if ask.price > bid.price:
            return None

        # Price will be favourable to whoever went second.
        # The earlier poster trades at their posted price,
        #   while the later poster transacts at a price no worse than posted;
        #   they may do better.
        price = ask.price if ask.time < bid.time else bid.price
        quantity = HavvenManager.round_decimal(min(ask.quantity, bid.quantity))

        # Only charge a fraction of the fee if an order was not entirely filled.
        bid_fee = HavvenManager.round_decimal((quantity / bid.quantity) * bid.fee)
        ask_fee = HavvenManager.round_decimal((quantity / ask.quantity) * ask.fee)

        # Compute the buy value. The sell value is just the quantity itself.
        buy_val = HavvenManager.round_decimal(quantity * price)

        # Only perform the actual transfer if it would be successful.
        # Cancel any orders that would not succeed.
        fail = False
        if not bid_success(bid.issuer, buy_val, bid_fee):
            bid.cancel()
            fail = True
        if not ask_success(ask.issuer, quantity, ask_fee):
            ask.cancel()
            fail = True
        if fail:
            return None
        # Perform the actual transfers.
        # We have already checked above if these would succeed.
        bid_transfer(bid.issuer, ask.issuer, buy_val, bid_fee)
        ask_transfer(ask.issuer, bid.issuer, quantity, ask_fee)

        # Update the orders, cancelling any with 0 remaining quantity.
        # This will remove the amount that was transferred from issuers' used value.
        bid.update_quantity(bid.quantity - quantity, bid.fee - bid_fee)
        ask.update_quantity(ask.quantity - quantity, ask.fee - ask_fee)
        return ob.TradeRecord(bid.issuer, ask.issuer, ask.book,
                              price, quantity, bid_fee, ask_fee, self.model_manager.time,
                              bid, ask)

    def havven_nomin_match(self, bid: "ob.Bid",
                           ask: "ob.Ask") -> Optional["ob.TradeRecord"]:
        """
        Buyer offers nomins in exchange for havvens from the seller.
        Return a TradeRecord object if the match succeeded, otherwise None.
        """
        return self.__bid_ask_match(bid, ask,
                                    self.transfer_nomins_success,
                                    self.transfer_havvens_success,
                                    self.transfer_nomins,
                                    self.transfer_havvens)

    def havven_fiat_match(self, bid: "ob.Bid",
                          ask: "ob.Ask") -> Optional["ob.TradeRecord"]:
        """
        Buyer offers fiat in exchange for havvens from the seller.
        Return a TradeRecord object if the match succeeded, otherwise None.
        """
        return self.__bid_ask_match(bid, ask,
                                    self.transfer_fiat_success,
                                    self.transfer_havvens_success,
                                    self.transfer_fiat,
                                    self.transfer_havvens)

    def nomin_fiat_match(self, bid: "ob.Bid",
                         ask: "ob.Ask") -> Optional["ob.TradeRecord"]:
        """
        Buyer offers fiat in exchange for nomins from the seller.
        Return a TradeRecord object if the match succeeded, otherwise None.
        """
        return self.__bid_ask_match(bid, ask,
                                    self.transfer_fiat_success,
                                    self.transfer_nomins_success,
                                    self.transfer_fiat,
                                    self.transfer_nomins)

    def transfer_fiat_success(self, sender: "ag.MarketPlayer",
                              quantity: Dec, fee: Dec) -> bool:
        """True iff the sender could successfully send a quantity of fiat."""
        return 0 <= quantity + fee <= HavvenManager.round_decimal(sender.fiat)

    def transfer_havvens_success(self, sender: "ag.MarketPlayer",
                                 quantity: Dec, fee: Dec) -> bool:
        """True iff the sender could successfully send a quantity of havvens."""
        return 0 <= quantity + fee <= HavvenManager.round_decimal(sender.havvens)

    def transfer_nomins_success(self, sender: "ag.MarketPlayer",
                                quantity: Dec, fee: Dec) -> bool:
        """True iff the sender could successfully send a quantity of nomins."""
        return 0 <= quantity + fee <= HavvenManager.round_decimal(sender.nomins)

    def transfer_fiat(self, sender: "ag.MarketPlayer",
                      recipient: "ag.MarketPlayer", quantity: Dec, fee: Optional[Dec] = None) -> bool:
        """
        Transfer a positive quantity of fiat currency from the sender to the
          recipient, if balance is sufficient. Return True on success.
        """
        if fee is None:
            fee = self.fee_manager.transferred_fiat_fee(quantity)
        if self.transfer_fiat_success(sender, quantity, fee):
            sender.fiat -= quantity + fee
            recipient.fiat += quantity
            self.model_manager.fiat += fee
            return True
        return False

    def transfer_havvens(self, sender: 'ag.MarketPlayer',
                         recipient: 'ag.MarketPlayer', quantity: Dec, fee: Optional[Dec] = None) -> bool:
        """
        Transfer a positive quantity of havvens from the sender to the recipient,
          if balance is sufficient. Return True on success.
        """
        if fee is None:
            fee = self.fee_manager.transferred_havvens_fee(quantity)
        if self.transfer_havvens_success(sender, quantity, fee):
            sender.havvens -= quantity + fee
            recipient.havvens += quantity
            self.model_manager.havvens += fee
            return True
        return False

    def transfer_nomins(self, sender: 'ag.MarketPlayer',
                        recipient: 'ag.MarketPlayer', quantity: Dec, fee: Optional[Dec] = None) -> bool:
        """
        Transfer a positive quantity of nomins from the sender to the recipient,
          if balance is sufficient. Return True on success.
        """
        if fee is None:
            fee = self.fee_manager.transferred_nomins_fee(quantity)
        if self.transfer_nomins_success(sender, quantity, fee):
            sender.nomins -= quantity + fee
            recipient.nomins += quantity
            self.model_manager.nomins += fee
            return True
        return False

    def havvens_to_nomins(self, quantity: Dec) -> Dec:
        """Convert a quantity of havvens to its equivalent quantity in nomins."""
        return HavvenManager.round_decimal(quantity * self.havven_nomin_market.price)

    def havvens_to_fiat(self, quantity: Dec) -> Dec:
        """Convert a quantity of havvens to its equivalent quantity in fiat."""
        return HavvenManager.round_decimal(quantity * self.havven_fiat_market.price)

    def nomins_to_havvens(self, quantity: Dec) -> Dec:
        """Convert a quantity of nomins to its equivalent quantity in havvens."""
        return HavvenManager.round_decimal(quantity / self.havven_nomin_market.price)

    def nomins_to_fiat(self, quantity: Dec) -> Dec:
        """Convert a quantity of nomins to its equivalent quantity in fiat."""
        return HavvenManager.round_decimal(quantity * self.nomin_fiat_market.price)

    def fiat_to_havvens(self, quantity: Dec) -> Dec:
        """Convert a quantity of fiat to its equivalent quantity in havvens."""
        return HavvenManager.round_decimal(quantity / self.havven_fiat_market.price)

    def fiat_to_nomins(self, quantity: Dec) -> Dec:
        """Convert a quantity of fiat to its equivalent quantity in nomins."""
        return HavvenManager.round_decimal(quantity / self.nomin_fiat_market.price)

    @property
    def active_havven_value(self) -> Dec:
        return self.model_manager.active_havvens * self.havven_fiat_market.price

    @property
    def havven_value(self) -> Dec:
        return self.model_manager.havven_supply * self.havven_fiat_market.price

    @property
    def active_nomin_value(self) -> Dec:
        return self.model_manager.active_nomins * self.nomin_fiat_market.price

    @property
    def nomin_value(self) -> Dec:
        return self.model_manager.nomin_supply * self.nomin_fiat_market.price
