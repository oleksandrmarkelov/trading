import logging
from binance.um_futures import UMFutures as Client
import requests
import time
from binance.lib.utils import config_logging

import datetime

import sys

config_logging(logging, logging.INFO)

# define your API key and secret
API_KEY = "XXXX"
API_SECRET = "XXXX"

# define the client
client = Client (API_KEY, API_SECRET)

position="XRPUSDT"
leverage=25

max_bal = 50
min_bal = 10

def get_balance() -> float:
  futures_usd = 0.0
  for asset in client.balance(recvWindow=6000):
    name = asset["asset"]
    balance = float(asset["balance"])
    if name == "USDT":
        futures_usd += balance
  return float(futures_usd)


def main():
  response = client.change_leverage(symbol=position, leverage=leverage)
  print(response)
  #response = client.cancel_open_orders(symbol=position, recvWindow=2000)
  #print(response)
  response = client.get_position_mode(recvWindow=2000)
  if not response["dualSidePosition"]:
    response = client.change_position_mode(dualSidePosition="true", recvWindow=2000)
    print(response)
  order_price=-1;
  short_o_id=-1;
  long_o_id=-1;
  updatable = False
  counter = 0;
  while True:
    time.sleep(1)
    counter +=1
    print("--------------------")
    now = datetime.datetime.now()
    print(now)
    if counter % 10 == 0:
      balance = get_balance()
      print("balance "+str(balance))
      if balance < min_bal:
        print("balance too low for trading, stop "+str(balance))
        sys.exit(0)

    already_active = client.get_orders(
        symbol=position, recvWindow=2000
    )
    print(already_active)

    if len(already_active) > 0:
      if len(already_active) == 2:
        if updatable:
          symbol_info = client.ticker_price(position)
          price = float(symbol_info['price'])
          if already_active[0]['side'] == 'SELL':
            if price > float(already_active[0]['activatePrice']):
              quantity = float(already_active[0]['origQty'])
              print('cancel order '+str(short_o_id))
              client.cancel_order(symbol=position,orderId=short_o_id,recvWindow=2000)
              response5 = client.new_order(
                symbol=position,
                positionSide="SHORT",
                side="BUY",
                type="TRAILING_STOP_MARKET",
                quantity=quantity,
                activationPrice=round(price-0.001,4),
                callbackRate=0.5
              )
              updatable=False
              print(response5)
            elif price < float(already_active[1]['activatePrice']):
              quantity = float(already_active[1]['origQty'])
              print('cancel order '+str(long_o_id))
              client.cancel_order(symbol=position,orderId=long_o_id,recvWindow=2000)
              response5 = client.new_order(
                symbol=position,
                positionSide="LONG",
                side="SELL",
                type="TRAILING_STOP_MARKET",
                quantity=quantity,
                activationPrice=round(price+0.001,4),
                callbackRate=0.5
              )
              updatable=False
              print(response5)
          else:
            if price > float(already_active[1]['activatePrice']):
              quantity = float(already_active[1]['origQty'])
              print('cancel order '+str(short_o_id))
              client.cancel_order(symbol=position,orderId=short_o_id,recvWindow=2000)
              response5 = client.new_order(
                symbol=position,
                positionSide="SHORT",
                side="BUY",
                type="TRAILING_STOP_MARKET",
                quantity=quantity,
                activationPrice=round(price-0.001,4),
                callbackRate=0.5
              )
              updatable=False
              print(response5)
            elif price < float(already_active[0]['activatePrice']):
              quantity = float(already_active[0]['origQty'])
              print('cancel order '+str(long_o_id))
              client.cancel_order(symbol=position,orderId=long_o_id,recvWindow=2000)
              response5 = client.new_order(
                symbol=position,
                positionSide="LONG",
                side="SELL",
                type="TRAILING_STOP_MARKET",
                quantity=quantity,
                activationPrice=round(price+0.001,4),
                callbackRate=0.5
              )
              updatable=False
              print(response5)
        #if len(already_active) == 1:
        #    o_id = already_active[0]["orderId"]
        #    print("cancelling single order "+o_id)
        #    client.cancel_order(symbol=position,orderId=o_id,recvWindow=2000)
        print("already orders placed, skipping")
        continue

    symbol_info = client.ticker_price(position)
    price = float(symbol_info['price'])
    logging.info(price)
    order_price=price;

    quantity = round((min_bal/2)*leverage / price, 1)

    print("quantity "+str(quantity))
    response1 = client.new_order(
        symbol=position,
        positionSide="LONG",
        side="BUY",
        type="MARKET",
        quantity=quantity
        )

    print(response1)

    response2 = client.new_order(
        symbol=position,
        positionSide="SHORT",
        side="SELL",
        type="MARKET",
        quantity=quantity
    )
    print(response2)
    time.sleep(1)
    print("activation "+str(round(price-0.002,4)))
    print("activation "+str(round(price+0.002,4)))

    response3 = client.new_order(
        symbol=position,
        positionSide="SHORT",
        side="BUY",
        type="TRAILING_STOP_MARKET",
        quantity=quantity,
        activationPrice=round(price-0.002,4),
        callbackRate=0.5
        )
    print(response3)
    short_o_id=response3['orderId']

    response4 = client.new_order(
        symbol=position,
        positionSide="LONG",
        side="SELL",
        type="TRAILING_STOP_MARKET",
        quantity=quantity,
        activationPrice=round(price+0.002,4),
        callbackRate=0.5
        )
    print(response4)
    long_o_id=response4['orderId']
    updatable = True



if __name__ == '__main__':
  main()
