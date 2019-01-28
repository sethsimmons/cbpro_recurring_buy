#!/usr/bin/env python
"""A short and sweet script to automate deposits and purchases using Coinbase Pro API,
getting around the massive Coinbase recurring purchase fees."""

import argparse
import binascii
import logging
import time
import os
import cbpro


def get_parser():

    parser = argparse.ArgumentParser(description="python3 cbpro_recurring_buy.py --amount=100 --buy --cryptocurrency='BTC-USD'")
    action = parser.add_mutually_exclusive_group(required=True)

    parser.add_argument("--amount",
                        type=int,
                        help="Amount to deposit or buy (in fiat)",
                        required=True)
    parser.add_argument("--fiat_currency", type=str,
                        help="Fiat base pair to use (default is USD)",
                        default='USD')
    parser.add_argument("--cryptocurrency",
                        type=str,
                        help="Pair to buy (only supports fiat pairs)")
    parser.add_argument("--funding_method",
                        type=str,
                        help="Payment method to use",
                        choices=['ach_bank_account'])
    action.add_argument("--deposit",
                        action='store_true',
                        help="Deposit specified amount into wallet")
    action.add_argument("--buy",
                        action='store_true',
                        help="Buy specified amount of BTC (in USD)")
    parser.add_argument("--debug",
                        action='store_true',
                        help="Output debug information to stdout")

    return parser


def get_logger(debug=False):
    # TODO revisit to simplify

    # Setup logging
    if debug:
        logger = logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                                     level=logging.DEBUG)
    else:
        logger = logging.basicConfig(filename='cbpro_recurring_buy.log',
                                     format='%(asctime)s %(levelname)s: %(message)s',
                                     level=logging.INFO)

    return logger


def cbpro_auth(key, secret, passphrase):
    """Function to handle authentication with the Coinbase Pro API"""
    # Auth with CBPro
    try:
        auth_client = cbpro.AuthenticatedClient(key, secret, passphrase)
    except binascii.Error:
        raise RuntimeError("API secret key is not in proper Base64 format!")

    return auth_client


def deposit_funds(client, account, amount, fiat_currency):
    """Function to handle depositing funds from a given payment method
    to the Coinbase Pro fiat wallet"""

    # Get Coinbase Pro funding accounts
    payment_methods = client.get_payment_methods()

    if 'Invalid API Key' in payment_methods:
        raise RuntimeError("API key is invalid!")

    # Search all payment methods for one matching the given type
    for method in payment_methods:
        if method['type'] == account:
            method_id = method['id']
            method_name = method['name']
            method_limit_remaining = method['limits']['deposit'][0]['remaining']['amount']

            logging.debug(f"Payment method name: {method_name}")
            logging.debug(f"Payment method ID: {method_id}")
            logging.debug(f"Payment method remaining limit: {float(method_limit_remaining)}")

    # Check that we got a proper payment method
    if not method_id:
        raise RuntimeError("Could not find a payment method matching the selected method")

    # Deposit with above params
    deposit_response = client.deposit(amount=amount,
                                      currency=fiat_currency,
                                      payment_method_id=method_id)

    logging.info(f"Deposited {amount} {fiat_currency} to Coinbase Pro from Coinbase account {method_name}")
    logging.info(f"Deposit will be available at {deposit_response['payout_at']}")

    return deposit_response


def buy_cryptocurrency(client, cryptocurrency, amount, fiat_currency):
    """Function to handle buying the given cryptocurrency pair
    with the payment method provided in deposit_funds"""

    # Place buy of BTC with above params
    buy_response = client.place_market_order(product_id=cryptocurrency,
                                             side='buy',
                                             funds=str(amount))

    if 'Invalid API Key' in buy_response:
        raise RuntimeError(f"API key is invalid, please check your credentials! Error: {buy_response}")
    elif 'Insufficient funds' in buy_response:
        raise RuntimeError(f"Insufficient funds to make the purchasein your fiat wallet! Error: {buy_response}")

    trade_id = buy_response.get('id', None)

    if not trade_id:
        raise RuntimeError(f"Unable to get trade ID in returned data, trade failed. Error: {buy_response}")

    # Sleep to allow time for trade to complete
    time.sleep(5)

    # Check status of trade
    executed_trade_response = client.get_order(trade_id)

    if not executed_trade_response['settled']:
        # Sleep for longer, should never need to do this unless CBPro is overloaded
        time.sleep(30)
        executed_trade_response = client.get_order(trade_id)

    # If trade was successful, gather data and log it
    fees = float(executed_trade_response['fill_fees'])
    btc_bought = float(executed_trade_response['filled_size'])

    logging.info(f"Bought {amount} {fiat_currency} of BTC, resulting in {btc_bought} BTC")
    logging.info(f"Fees: {fees} {fiat_currency}")

    return executed_trade_response


def main():

    parser = get_parser()
    args = parser.parse_args()
    get_logger()

    # Authenticate with Coinbase Pro
    if args.deposit and not args.funding_method:
        parser.error("--deposit requires --funding_method")

    client = cbpro_auth(os.environ['API_KEY'], os.environ['API_SECRET'], os.environ['API_PASSPHRASE'])

    if args.deposit:
        deposit_funds(client, args.funding_method, args.amount, args.fiat_currency)
    elif args.buy:
        buy_cryptocurrency(client, args.cryptocurrency, args.amount, args.fiat_currency)
    else:
        print("No action flags selected, doing nothing and exiting...")


if __name__ == '__main__':
    main()
