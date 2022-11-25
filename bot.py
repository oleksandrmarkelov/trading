from binance.client import Client
import requests
import time
import pandas as pd

import queue

import datetime

import sys

# define your API key and secret
API_KEY = "XXXX"
API_SECRET = "XXXX"

# define the client
client = Client (API_KEY, API_SECRET)

positions=["AVAXBUSD","SOLBUSD","DOTBUSD", "BTCBUSD","BNBBUSD"]
queues=[queue.Queue(3),queue.Queue(3),queue.Queue(3),queue.Queue(3),queue.Queue(3)]

leverage = 4
max_bal = 50
min_bal = 10
bet = 33

#rsi
timeinterval = 5
period = 12

sl=1
tp=0.5


def get_balance() -> float:
  futures_usd = 0.0
  for asset in client.futures_account_balance():
      name = asset["asset"]
      balance = float(asset["balance"])
      if name == "BUSD":
          futures_usd += balance
  return float(futures_usd)

def to_spot(amount):
  client.futures_account_transfer(asset="BUSD", amount=float(amount), type="2")

def get_active() -> dict:
    active = {}
    for position in client.futures_account()['positions']:
        maintMargin = position["maintMargin"]
        if maintMargin != '0':
            active[position["symbol"]] = position
    return active

def rsi(symbol) -> float:
    url = 'https://fapi.binance.com/fapi/v1/klines?symbol='+symbol+'&interval='+str(timeinterval)+'m'+'&limit=100'
    data = requests.get(url).json()

    D = pd.DataFrame(data)
    D.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades','taker_base_vol', 'taker_quote_vol', 'is_best_match']

    df=D
    df['close'] = df['close'].astype(float)
    df2=df['close'].to_numpy()

    df2 = pd.DataFrame(df2, columns = ['close'])
    delta = df2.diff()

    up, down = delta.copy(), delta.copy()
    down[down > 0] = 0
    up[up < 0] = 0

    _gain = up.ewm(com=(period - 1), min_periods=period).mean()
    _loss = down.abs().ewm(com=(period - 1), min_periods=period).mean()

    RS = _gain / _loss
    rsi=100 - (100 / (1 + RS))
    rsi=rsi['close'].iloc[-1]
    rsi=round(rsi,1)

    return rsi

def populateQ():
    rsis = []
    for p in positions:
        rsis.append(rsi(p))
    i=0
    for q in queues:
        if q.full():
            q.get()
        q.put(rsis[i])
        i+=1

def decide(q) -> str:
    is_up = True;
    is_down = True;
    is_first = True;
    prev = -1;
    for i in q.queue:
        if i > 60:
            is_up = False
        if i < 40:
            is_down = False
        if is_first:
            prev = i
            is_first = False
            continue
        if(i>prev):
            is_down = False
        if(i<prev):
            is_up = False
        prev=i
    if is_up:
        return "U"
    if is_down:
        return "D"
    return "N"

from binance.helpers import round_step_size

def trade(pos, decide):
    bal = get_balance()
    if bal > max_bal:
        bal = max_bal
    bal = bal*bet/100

    symbol_info = client.get_ticker(symbol=pos)
    symbol_price = float(symbol_info['lastPrice'])

    quantity = bal*leverage / symbol_price

    quantity = round_step_size(quantity, 0.1)
    if pos == "SOLBUSD":
        quantity = round_step_size(quantity, 1)
        if quantity == 0:
            quantity = 1

    side = "BUY"
    if decide == "D":
        side = "SELL"

    print("Trade with balance "+str(bal)+" to "+decide+" for "+pos+ " quantity "+ str(quantity)+ " side "+side)

    m_order = client.futures_create_order(symbol=pos, type='MARKET', side=side, quantity=quantity)
    print(m_order)
    time.sleep(1)
    o_id=m_order['orderId']

    o = client.futures_get_order(symbol=pos,orderId=o_id)

    while o['status'] != 'FILLED':
        print('order not yet filled '+o_id)
        time.sleep(1)
        o = client.futures_get_order(symbol=pos,orderId=o_id)

    price = float(o['avgPrice'])

    print('Order price '+str(price))

    close_side = "SELL"
    if side == "SELL":
        close_side="BUY"

    sl_price = round_step_size(price*(1-sl/100), 0.01)
    if side == "SELL":
        sl_price = round_step_size(price*(1+sl/100), 0.01)


    sl_order = client.futures_create_order(symbol=pos,side=close_side,type='STOP_MARKET',stopPrice=sl_price,closePosition='true')

    print('stop loss order ')
    print(sl_order)

    time.sleep(1)

    tp_price = round_step_size(price*(1+tp/100), 0.01)
    if side == "SELL":
        tp_price = round_step_size(price*(1-tp/100), 0.01)

    tp_order = client.futures_create_order(symbol=pos,side=close_side,type='TAKE_PROFIT_MARKET',stopPrice=tp_price,closePosition='true')

    print('take profit order ')
    print(tp_order)

def init_lev():
    for s in positions:
        print("updating leverage "+s)
        client.futures_change_leverage(symbol=s, leverage=leverage)

sc_list = [0,0,0]
fc_list = [0,0,0]

import time

def cancel_existing(ind):
  orders = client.futures_get_open_orders(symbol=positions[ind])
  if len(orders) == 0:
      return
  e_o = orders[0]
  e_id = e_o['orderId']
  if e_o['type'] == 'TAKE_PROFIT_MARKET':
      fc_list[ind] += 1
      print("cancelling tp order for "+positions[ind]+" id "+str(e_id))

  if e_o['type'] == 'STOP_MARKET':
      sc_list[ind] += 1
      print("cancelling sl order for "+positions[ind]+" id "+str(e_id))
  client.futures_cancel_order(symbol=positions[ind], orderId=e_id, origClientOrderId=e_o['clientOrderId'])

  print('success'+str(sc_list))
  print('failure'+str(fc_list))

p_c = 0

def close_position(pos):
  global p_c
  print("close position premature ")
  print(pos)
  sym = pos['symbol']
  quantity =abs(float(pos['positionAmt']))
  close_side = "Unknown"
  if abs(float(pos['entryPrice'])) > abs(float(pos['notional'])/float(quantity)) and float(pos['unrealizedProfit']) > p_c_limit:
      close_side = "BUY"
  if float(pos['entryPrice']) < float(pos['notional'])/float(quantity) and float(pos['unrealizedProfit']) > p_c_limit:
      close_side = "SELL"

  print('closing for '+pos['symbol']+' amount '+str(quantity)+ ' closing side '+close_side)
  if close_side == "Unknown":
    return
  cpo = client.futures_create_order(symbol=sym,side=close_side,type='MARKET',quantity=quantity)
  print('close position order')
  print(cpo)
  time.sleep(1)
  orders = client.futures_get_open_orders(symbol=sym)
  for order in orders:
      client.futures_cancel_order(symbol=sym, orderId=order['orderId'], origClientOrderId=order['clientOrderId'])
      print('cancel order with position '+str(order['orderId']))

  time.sleep(1)
  p_c += 1
  print('premature close '+str(p_c))

p_c_limit = 0.15

def main():
  init_lev()
  count = 0
  while True:
    time.sleep(20)
    print("--------------------")
    now = datetime.datetime.now()
    print(now)
    balance = get_balance()
    print("balance "+str(balance))
    if balance < min_bal:
        print("balance too low for trading, stop "+str(balance))
        sys.exit(0)

    populateQ()

    count +=1

    if count<3:
        print("Init "+str(count))
        continue

    already = get_active()
    for sym, pos in already.items():
        if float(pos['unrealizedProfit']) > p_c_limit:
            close_position(pos)


    already_active = get_active()
    if len(already_active) > 2:
        print("already 3 orders placed, skipping")
        continue

    btc_decide = decide(queues[3])
    bnb_decide = decide(queues[4])

    #for r in queues[3].queue:
    #    print("BTC "+str(r))
    #for r in queues[4].queue:
    #    print("BNB "+str(r))


    if btc_decide == "N" or bnb_decide == "N" or bnb_decide != btc_decide:
        print("skip BTC are "+btc_decide+"/"+bnb_decide)
    #if btc_decide == "N":
    #    print("skip BTC are "+btc_decide)
        continue


    for indx in 0,1,2:
        if positions[indx] in already_active.keys():
            print("Already has order, skipping "+positions[indx])
            continue
        cancel_existing(indx)
        coin_decide = decide(queues[indx])
        if coin_decide == btc_decide:
            for r in queues[3].queue:
                print("BTC "+str("%.3f"%r))
            for r in queues[4].queue:
                print("BNB "+str("%.3f"%r))
            for r in queues[indx].queue:
                print(positions[indx]+" "+str("%.3f"%r))
            # invert
            if coin_decide == "U":
                coin_decide = "D"
            else:
                coin_decide = "U"
            trade(positions[indx], btc_decide)
        else:
            print("no trade for "+positions[indx]+ " decide "+coin_decide)


if __name__ == '__main__':
  main()
