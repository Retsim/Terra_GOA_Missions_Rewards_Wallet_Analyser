#!/usr/bin/python
# -*- coding: utf-8 -*-
import requests
import builtins
import traceback
import json
import uuid
import re
import datetime
import string
import sys
import os
import random
import flask
import io
from flask import request, jsonify, send_from_directory, session
import threading
import logging, logging.handlers
import collections
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as dates
from scipy.interpolate import make_interp_spline
import numpy as np
import mpld3
from mpld3 import plugins
import time
import math

pisco_lcd = "https://pisco-lcd.terra.dev/"
goa_faucet = "terra1tffmdx6lgkqst2kcvm3kmeyycfgnqdpywww89h"
ibcs = {
    "sCOR":"D7AA592A1C1C00FE7C9E15F4BB7ADB4B779627DD3FBB3C877CD4DB27F56E35B4",
    "sORD":"3FA98D26F2D6CCB58D8E4D1B332C6EB8EE4AC7E3F0AD5B5B05201155CEB1AD1D",
    "sATR":"95287CFB16A09D3FE1D0B1E34B6725A380DD2A40AEF4F496B3DAF6F0D901695B",
    "sHAR":"51B1594844CCB9438C4EF3720B7ADD4398AC5D52E073CA7E592E675C6E4163EF"
}
goa_chains = {
    "terra":{"lcd":pisco_lcd, "enabled_staking_ibcs": []},
    "harkonnen":{"lcd": "https://harkonnen.terra.dev:1317/", "enabled_staking_ibcs": ['sCOR', 'sORD', 'sATR']},
    "corrino":{"lcd": "https://corrino.terra.dev:1317/", "enabled_staking_ibcs": ['sORD', 'sATR']},
    "atreides":{"lcd": "https://atreides.terra.dev:1317/", "enabled_staking_ibcs": ['sCOR', 'sHAR', 'sORD']},
    "ordos":{"lcd": "https://ordos.terra.dev:1317/", "enabled_staking_ibcs": ['sCOR','sHAR','sATR']},
}
    
def get_alliances_infos(account, lcd, verbose=False):
  infos_url = lcd + "terra/alliances/-account-"
  url = infos_url.replace("-account-", str(account))
  if verbose:
    printC(url)
  response = requests.get(url)
  infos = response.json()
  if infos is None:
    printC("ERROR IN API CALL")
    return None
  return infos

def get_rewards(account, rewards, chains, ibcs, verbose=False):
  rewards_url = "https://goa.terra.dev/staking/validators/-chain--1/-ibc-?address=-account-"
  for chain, conf in chains.items():
    if 'terra' in chain:
      continue
    if account.startswith(chain):
      for ibc_key, ibc_value in ibcs.items():
        if ibc_key in conf['enabled_staking_ibcs']:
          rewards[chain] = {}
          url = rewards_url.replace("-account-", str(account)).replace('-chain-', chain).replace('-ibc-', ibc_value)
          if verbose:
            printC(url)
          response = requests.get(url)
          validators = response.json()
          if not 'status' in validators:
            for validator in validators:
              if len(validator['rewards']) > 0:
                if ibc_key not in rewards[chain]:
                  rewards[chain][ibc_key] = {}
                for reward in validator['rewards']:
                  if reward["symbol"] not in rewards[chain][ibc_key]:
                    rewards[chain][ibc_key][reward["symbol"]] = 0
                  rewards[chain][ibc_key][reward["symbol"]] += int(reward["amount"])
          else:
            printC("ERROR IN API CALL")
            return rewards
  return rewards

def get_balances(account, balances, lcd, verbose=False):
  balances_url = lcd + "cosmos/bank/v1beta1/balances/-account-"
  url = balances_url.replace("-account-", str(account))
  if verbose:
    printC(url)
  response = requests.get(url)
  balances_data = response.json()
  if balances_data is None:
    printC("ERROR IN API CALL")
    return balances
  for balance in balances_data['balances']:
    # [{'denom': 'ibc/D7AA592A1C1C00FE7C9E15F4BB7ADB4B779627DD3FBB3C877CD4DB27F56E35B4', 'amount': '100'}, {'denom': 'uatr', 'amount': '1000003785'}]
    if account not in balances:
      balances[account] = {}
    if balance['denom'] not in balances[account]:
      balances[account][balance['denom']] = int(balance['amount'])
    else:
      balances[account][balance['denom']] += int(balance['amount'])

  return balances

def get_transactions(account, lcd, verbose=False):
  #transactions_url = lcd + "v1/txs?offset=-offset-&limit=100&account=-account-"
  transactions_url = lcd + "cosmos/tx/v1beta1/txs?&pagination.offset=-offset-&pagination.limit=100&pagination.count_total=true&events=-event-"
  full_transactions = []
  events = [
      "message.sender=%27-account-%27".replace("-account-", account),
      "message.receiver=%27-account-%27".replace("-account-", account),
      "wasm.sender=%27-account-%27".replace("-account-", account),
      "transfer.recipient=%27-account-%27".replace("-account-", account),
      "wasm.receiver=%27-account-%27".replace("-account-", account)
      ]
  for event in events:
    next_page = 0
    total = None
    while next_page != None:
      url = transactions_url.replace("-event-", event).replace("-offset-", str(next_page))
      if verbose:
        printC(url)
      response = requests.get(url)
      transactions = response.json()
      if transactions is None:
        printC("ERROR IN API CALL")
        return None
      if verbose:
        printC(transactions)
      if 'pagination' not in transactions:
        printC("ERROR IN API CALL")
        return None
      else:
        if total is None:
          if transactions['pagination'] is not None:
            total = int(transactions['pagination']['total'])
          else:
            total = -1
      if 'tx_responses' in transactions:
        if len(transactions['tx_responses']) > 0:
          next_page += len(transactions['tx_responses'])
      else:
        next_page = None
      if 'tx_responses' in transactions:
        full_transactions = full_transactions + transactions['tx_responses']
      if len(full_transactions) >= total:
        next_page = None
      time.sleep(0.5)
  new_full_transactions = []
  [new_full_transactions.append(x) for x in full_transactions if x not in new_full_transactions]
  return new_full_transactions

def get_ibcs_transfers(transactions):
  ibcs_data = {'sent':[], 'received':[]}
  for transaction in transactions:
    ibc_send = False
    ibc_receive = False
    for log in transaction['logs']:
      for event in log['events']:
        if event['type'] == "send_packet" or event['type'] == "recv_packet":
          for attr in event['attributes']:
            if attr['key'] == "packet_data":
              packet_data = attr['value']
              packet_data = json.loads(packet_data)
              sender = packet_data['sender']
              receiver = packet_data['receiver']
              ibc_data = {'sender': sender, 'receiver': receiver}
              if event['type'] == "send_packet":
                ibcs_data['sent'].append(ibc_data)
              else:
                ibcs_data['received'].append(ibc_data)
  return ibcs_data

def get_delegations(transactions, native_staking_rewards):
  delegations_data = {'delegated':0, 'undelegated':0, 'redelegated':0, 'claim':0}
  for transaction in transactions:
    timestamp = transaction['timestamp'] # 2021-09-30T06:46:39Z
    timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')
    for log in transaction['logs']:
      for event in log['events']:
        if event['type'] == "alliance_delegate":
          delegations_data['delegated']+=1
        if event['type'] == "alliance_undelegate":
          delegations_data['undelegated']+=1
        if event['type'] == "alliance_redelegate":
          delegations_data['redelegated']+=1
        if event['type'] == "alliance_claim_delegation_rewards":
          delegations_data['claim']+=1
          for attr in event['attributes']:
              if attr['key'] == "amount":
                amount = attr['value']
                denom = 'unknow'
                if len(amount) > 0: 
                    if 'ibc/' in amount:
                       # '100ibc/D7AA592A1C1C00FE7C9E15F4BB7ADB4B779627DD3FBB3C877CD4DB27F56E35B4,3785'
                      denom = amount.split('ibc/')[1]
                      if ',' in denom:
                        denom = denom.split(',')[0]
                      amount = amount.split('ibc/')[0]
                    elif 'u' in amount:  #652200uhar
                      denom = amount.split('u')[1]
                      amount = amount.split('u')[0]
                    printC(transaction)
                    printC(amount)
                    if timestamp not in native_staking_rewards:
                      native_staking_rewards[timestamp] = {}
                    if denom not in native_staking_rewards[timestamp]:
                      native_staking_rewards[timestamp][denom] = float(float(amount)/1e6)
                    else:
                      native_staking_rewards[timestamp][denom] += float(float(amount)/1e6)

  return delegations_data

def update_stats(chain, stats, sub_ibcs_data, delegations):
  printC("    " + chain + " - IBC transfers")
  printC("    " + chain + " - IBC Sent: " + str(len(sub_ibcs_data['sent'])))
  printC("    " + chain + " - IBC Received: " + str(len(sub_ibcs_data['received'])))
  printC("    " + chain + " - Staking stats")

  stats['total_ibc_sent'] += len(sub_ibcs_data['sent'])
  stats['total_ibc_received'] += len(sub_ibcs_data['received'])

  if delegations is not None:
    printC("    " + chain + " - Delegated: " + str(delegations['delegated']))
    printC("    " + chain + " - Undelegated: " + str(delegations['undelegated']))
    printC("    " + chain + " - Redelegated: " + str(delegations['redelegated']))
    printC("    " + chain + " - Claimed: " + str(delegations['claim']))
    stats['total_delegations'] += delegations['delegated']
    stats['total_undelegations'] += delegations['undelegated']
    stats['total_redelegations'] += delegations['redelegated']
    stats['total_claims'] += delegations['claim']

  return stats
  
class TopToolbar(plugins.PluginBase):
    """Plugin for moving toolbar to top of figure"""

    JAVASCRIPT = """
    mpld3.register_plugin("toptoolbar", TopToolbar);
    TopToolbar.prototype = Object.create(mpld3.Plugin.prototype);
    TopToolbar.prototype.constructor = TopToolbar;
    function TopToolbar(fig, props){
        mpld3.Plugin.call(this, fig, props);
    };

    TopToolbar.prototype.draw = function(){
      // the toolbar svg doesn't exist
      // yet, so first draw it
      this.fig.toolbar.draw();

      // then change the y position to be
      // at the top of the figure
      this.fig.toolbar.toolbar.attr("y", 2);

      // then remove the draw function,
      // so that it is not called again
      this.fig.toolbar.draw = function() {}
    }
    """
    def __init__(self):
        self.dict_ = {"type": "toptoolbar"}
        
#plt.switch_backend('agg')

base_path = ""
base_url = ""
whitelist_addresses = [
"terra1hyxq9usxp7fge5lx7qx3k0mqe2u55fv4xptqtc",
"terra1l62yvvjhnlh9gjluutf8zmcaxnn6qmpjgf2xfk",
"terra1jyut4c9japevenkxvtqlvp0tp0askz4yhr9xfa",
"terra1p9ujjc2g7zqhg2yec05mth7vhmg3qvkhvnwh34",
"terra1menyrav8sj2h2m046xq2qeqslwquhmvvjq4j5l",
"terra1dp0taj85ruc299rkdvzp4z5pfg6z6swaed74e6",
"terra1yzrmkj93q36uzhsj6afkpf4yjpz6vs5cfjsq27"
]

if __name__ == "__main__":
    base_url = "/"
    
api_key = "6957099211028924"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()
log.setLevel(logging.INFO)

rotater=logging.handlers.RotatingFileHandler(base_path+'logs.txt', maxBytes=3*1024*1024, backupCount=15)
rotater.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
rotater.setLevel(logging.INFO)
log.addHandler(rotater)

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
log.addHandler(stdout_handler)

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.INFO)
log.addHandler(stderr_handler)

application = flask.Flask(__name__)
application.config["DEBUG"] = True
application.secret_key = 'r4zé"4sf85s67f489465sf!ù$fz3f438zf4sdzaz8aaaaacccccccccv/'
application.config['SESSION_TYPE'] = 'filesystem'
application.permanent_session_lifetime = datetime.timedelta(days=3)

def printTrace():
    global log
    log.error("exception ",exc_info=1)

def printC(*args, **kwargs):
    global log
    strings = [str(arg) for arg in args]
    log.info(' '.join(strings))
    
# This hook ensures that a connection is opened to handle any queries
# generated by the request.
@application.before_request
def _db_connect():
    #database.connect()
    pass
    
# This hook ensures that the connection is closed when we've finished
# processing the request.
@application.teardown_request
def _db_close(exc):
    #global database
    #if not database.is_closed():
    #    database.close()
    pass
    
def smooth(y, box_pts):
    box = np.ones(box_pts)/box_pts
    y_smooth = np.convolve(y, box, mode='same')
    return y_smooth
    
def get_historical_data_for_wallet(wallet):
    printC('analyzing... ', wallet)
    wallet_to_analyse = wallet

    '''all_participants = []
    transactions = get_transactions(goa_faucet, pisco_lcd)
    printC("Got all faucet transactions, starting analysis...")
    for transaction in transactions:
      i = 0
      if "Faucet" in transaction['tx']['body']['memo']:
        # This is the faucet !
        for message in transaction['tx']['body']['messages']:
          if 'transfer' in message['msg']:
            if message['msg']['sender'] == goa_faucet:
              all_participants.append(message['msg']['transfer']['recipient'])
      
    printC(all_participants)'''

    
    scores = {}
    all_participants = [wallet_to_analyse]
    for terra_wallet in all_participants:
      printC("Analysing wallet: " + terra_wallet)
      stats = {'total_ibc_sent':0, 'total_ibc_received':0, 'total_delegations':0, 'total_undelegations':0, 'total_redelegations':0, 'total_claims':0}
      disqualified = False
      disqualification_reasons = []
      transactions = get_transactions(terra_wallet, pisco_lcd)
      chain = "pisco"
      balances = {}
      native_staking_rewards_all = {}
      summed_rewards_by_time_all = {}
      last_timestamp_all = {}
      if transactions is not None:
        printC("Got all transactions, starting analysis...")
        ibcs_data = get_ibcs_transfers(transactions)
        other_chains_addresses_tmp = []
        for item in ibcs_data['sent']:
          if item['sender'] != wallet_to_analyse:
            pass # That should never happens
          if not item['receiver'].startswith('terra'):
            other_chains_addresses_tmp.append(item['receiver'])
        for item in ibcs_data['received']:
          if item['receiver'] != wallet_to_analyse:
            pass # That should never happens
          if item['sender'] not in other_chains_addresses_tmp:
            disqualified = True
            disqualification_reasons.append("Received IBC transfer from another Terra wallet")
        stats = update_stats(chain, stats, ibcs_data, None)
        balances = get_balances(terra_wallet, balances, pisco_lcd, verbose=True)
        printC(balances)

        other_chains_addresses = []
        [other_chains_addresses.append(x) for x in other_chains_addresses_tmp if x not in other_chains_addresses]
        printC('Found other chains addresses based on IBC Transfers:')
        printC(other_chains_addresses)
        printC('')

        pending_rewards = {}
        found_chains = {}
        for sub_wallet in other_chains_addresses:
          native_staking_rewards = {}
          for chain, conf in goa_chains.items():
            if not sub_wallet.startswith(chain):
              continue
            if chain not in native_staking_rewards:
              native_staking_rewards = {} 
            lcd = conf['lcd']
            if chain not in found_chains:
                found_chains[chain] = sub_wallet   
            printC("Checking chain..." + chain)
            # Get transactions for this chain !
            transactions = get_transactions(sub_wallet, lcd)
            if transactions is not None:
              sub_ibcs_data = get_ibcs_transfers(transactions)
              for item in ibcs_data['received']:
                if item['receiver'] != wallet_to_analyse:
                  pass # That should never happens
                if item['sender'] not in other_chains_addresses:
                  disqualified = True
                  disqualification_reasons.append("Received IBC transfer from another wallet than original Terra address on " + chain)
              #infos = get_alliances_infos(sub_wallet, lcd, verbose=True)
              #printC(infos)
              pending_rewards = get_rewards(sub_wallet, pending_rewards, goa_chains, ibcs, verbose=True)
              # def get_rewards(account, chains, ibcs, verbose=False):
              balances = get_balances(sub_wallet, balances, lcd, verbose=True)
              printC(balances)
              delegations = get_delegations(transactions, native_staking_rewards)
              stats = update_stats(chain, stats, sub_ibcs_data, delegations)
              
              now = datetime.datetime.now()
              native_staking_rewards[now] = {}

              if sub_wallet in pending_rewards:
                for denom, balance in pending_rewards[sub_wallet].items():
                  if denom not in native_staking_rewards[now]:
                    native_staking_rewards[now][denom] = float(float(balance)/1e6)
                  else:
                    native_staking_rewards[now][denom] +=  float(float(balance)/1e6)

              # Sort to prepare calculation work
              native_staking_rewards = {k:v for k,v in sorted(native_staking_rewards.items())}
              
              # Sum by time
              summed_rewards_by_time = {}
              prev_timestamp = None
              for timestamp, data in native_staking_rewards.items():
                summed_rewards_by_time[timestamp] = dict(data)
                if prev_timestamp is not None:    
                    summed_rewards_by_time[timestamp] = dict(summed_rewards_by_time[prev_timestamp])
                    for denom, amount in data.items():
                      if denom in summed_rewards_by_time[timestamp]:
                        summed_rewards_by_time[timestamp][denom] += amount
                      else:
                        summed_rewards_by_time[timestamp][denom] = amount
                prev_timestamp = timestamp

              native_staking_rewards_all[chain] = native_staking_rewards
              summed_rewards_by_time_all[chain] = summed_rewards_by_time
              last_timestamp_all[chain] = timestamp
              
        native_staking_rewards_summed = {}
        # Sum by time
        prev_timestamp = None
        for chain in native_staking_rewards_all:
            native_staking_rewards_chain = native_staking_rewards_all[chain]
            for timestamp, data in native_staking_rewards_chain.items():
              if timestamp not in native_staking_rewards_summed:
                native_staking_rewards_summed[timestamp] = dict(data)
              else:
                native_staking_rewards_summed[timestamp] += dict(data)
            
        native_staking_rewards_summed = {k:v for k,v in sorted(native_staking_rewards_summed.items())}
        
        summed_rewards_by_time = {}
        prev_timestamp = None
        for timestamp, data in native_staking_rewards_summed.items():
          summed_rewards_by_time[timestamp] = dict(data)
          if prev_timestamp is not None:    
              summed_rewards_by_time[timestamp] = dict(summed_rewards_by_time[prev_timestamp])
              for denom, amount in data.items():
                if denom in summed_rewards_by_time[timestamp]:
                  summed_rewards_by_time[timestamp][denom] += amount
                else:
                  summed_rewards_by_time[timestamp][denom] = amount
          prev_timestamp = timestamp
        
        data = {'wallet':terra_wallet,'disqualified':disqualified, 'disqualification_reasons':disqualification_reasons, 'stats':stats,'balances':balances,'found_chains': found_chains, 'last_timestamp': timestamp, 'last_timestamp_all':last_timestamp_all,'native_staking_rewards_all':native_staking_rewards_all,'summed_rewards_by_time_all':summed_rewards_by_time_all, 'summed_rewards_by_time':summed_rewards_by_time}
    return data
  
def get_denoms(data, summed_rewards, last_timestamp):
    denoms = []
    timestamp = last_timestamp
    summed_rewards_by_time = summed_rewards
    if timestamp in summed_rewards_by_time:
      denoms = [str(denom) for denom in summed_rewards_by_time[timestamp].keys() if summed_rewards_by_time[timestamp][denom] > 0.0009 and denom.startswith('u') or not denom.startswith('u')]
      for key, ibc in ibcs.items():
        denoms = [denom.replace(ibc, key) for denom in denoms]
      denoms = sorted(denoms)
    if 'uluna' in denoms:
        denoms.remove('uluna')
        denoms.insert(0,'uluna')
    return denoms
    
def get_html_from_data(data, chain=None):
    html = ""
    graph_shown = False
    try:            
        if chain is not None:
            if chain in data['summed_rewards_by_time_all']:
                summed_rewards_by_time = data['summed_rewards_by_time_all'][chain]
                denoms = get_denoms(data, summed_rewards_by_time, data['last_timestamp_all'][chain])
        else:
            summed_rewards_by_time = data['summed_rewards_by_time']
            denoms = get_denoms(data, summed_rewards_by_time, data['last_timestamp'])
        
        # Show graphs :)
        col = 3
        row = math.ceil(len(denoms)/3)
        num = 1
        fig = plt.figure(facecolor=(1, 1, 1))
        fig.set_size_inches(2.8*col, 3*row)     # set a suitable size
        
        for denom in denoms:
            x = []
            y = []
            previous_y = 0
            for timestamp, data in summed_rewards_by_time.items():
                x.append(timestamp)
                if denom in data:
                  y.append(data[denom])
                  previous_y = data[denom]
                else:
                  y.append(previous_y)
            
            color = 'steelblue'
            if 'uluna' in denom:
              color = 'orange'
            
            ax = plt.subplot(row, col, num)
            ax.set_title(denom + ' (summed)',fontsize=18)
            plt.plot(x, y, color=color)
            if len(x) > 0 and len(y) > 0:
                graph_shown = True

                plt.xticks(rotation=30)
            plt.legend()
            num += 1
            
        '''# Legend row
        ax = plt.subplot(row, col, num)
        plt.scatter([0],[0],marker='^', color='lightblue', label='Redelegate')
        plt.scatter([0],[0],marker='x', color='crimson', s=120, label='Undelegate')
        plt.scatter([0],[0],marker='o', color='red', label='Withdraw')
        plt.scatter([0],[0],marker='*', color='rosybrown', s=200, label='Airdrop')
        plt.scatter([0],[0],marker='^', color='blue', label='Delegate')
        leg = plt.legend(loc = "center")
        for lh in leg.legendHandles: 
            lh.set_alpha(1)'''
            
        plt.tight_layout()
        
        plugins.connect(plt.gcf(), TopToolbar())
        
        html = mpld3.fig_to_html(fig)
    except Exception as ex:
        printC('generating html graphs failed !')
        printC(traceback.format_exc())
        
    return graph_shown, html
        
def get_head_html():
    css = '''
    <head>
        <meta name="viewport" content="initial-scale=0.45, user-scalable=yes">        
        <script>
      
        </script>
        <link rel="apple-touch-icon" sizes="180x180" href="asset/apple-touch-icon.png">
        <link rel="icon" type="image/png" sizes="32x32" href="asset/favicon-32x32.png">
        <link rel="icon" type="image/png" sizes="16x16" href="asset/favicon-16x16.png">
        <link rel="manifest" href="asset/site.webmanifest">
        <link rel="mask-icon" href="asset/safari-pinned-tab.svg" color="#5bbad5">
        <title>Terra Observatory</title>
        <meta name="apple-mobile-web-app-title" content="Terra Observatory">
        <meta name="application-name" content="Terra Observatory">
        <meta name="msapplication-TileColor" content="#da532c">
        <meta name="theme-color" content="#ffffff">

        <link href="asset/main.css" rel="stylesheet" media="all">
        <style>
            .mpld3-xaxis text{ transform: translate(18px, 8px) rotate(45deg); }
        </style>
    </head>'''
    
    return css

def get_end_html():
    return '''<script>
            const button = document.querySelector("#btn-submit");
            const form = document.querySelector("#form")
            form.addEventListener("submit", () => {
                button.disabled = true;
                button.textContent  = " Checking the stars ";
                button.classList.add("btn-submit-loading");
            });
        </script>'''
        

def main_logic():
    data = request.form
    html = get_head_html()
    html += '<body>'
    paddingtop = '165'
    if 'wallet' in data:
        wallet = data['wallet'].lower()
        paddingtop = '35'
        wallet = wallet.strip()
    html += '<div class="page-wrapper bg-img-1 p-t-'+paddingtop+' p-b-100">'
    html += '<div class="wrapper wrapper--w680"><center><a href=' + base_url + '><img src="asset/logo2.png" alt=" " style="width: 70%;" /></a></center></div>'
    
    if 'wallet' in data:
        html+= '<div class="wrapper wrapper--w880">'
        html += '<div class="card card-1">'
        html += '<div class="card-body">'
        html += '<ul class="tab-list">'
        html += '<li class="tab-list__item active">'
        html += '<a class="tab-list__link" href="#graphs" data-toggle="tab">Results for: ' + wallet + '</a>'
        html += '</li>'
        html += '</ul>'
        html += '<div class="tab-content">'
        html += '<div class="tab-pane active" id="graphs">'
            
        data = get_historical_data_for_wallet(wallet)
        html+= "<center><h3>Here is what we found in the Terra Game Of Alliances for you ! &#127776;</h3></center>"       
        html+= "<br/> " + str(len(data['found_chains']) + 1) + " chains analysed."
        
        stats = data['stats']
        html+= "<br/> Disqualification Status: " + str(data['disqualified'])
        if data['disqualified']:
          for reason in data['disqualification_reasons']:
            html+= "<br/> " + reason
            
        html+= "<br/><br/> <b>Missions Status:</b>"
        html+= "<br/> 1 - Delegate to any validator using the Alliance module"
        if stats['total_delegations'] > 0:
          html+= "  --> OK"
        else:
          html+= "  --> NOT_OK"
        html+= "<br/> 1 - Redelegate to any validator using the Alliance module"
        if stats['total_redelegations'] > 0:
          html+= "  --> OK"
        else:
          html+= "  --> NOT_OK"
        html+= "<br/> 1 - Undelegate from any validator using the Alliance module"
        if stats['total_undelegations'] > 0:
          html+= "  --> OK"
        else:
          html+= "  --> NOT_OK"
        html+= "<br/> 1 - Claim staking rewards from any chain"
        if stats['total_claims'] > 0:
          html+= "  --> OK"
        else:
          html+= "  --> NOT_OK"
        html+= "<br/> 3 - Undelegate from one chain, send tokens through IBC, and delegate to a different chain at least ten times"
        if stats['total_ibc_sent'] >= 10 and stats['total_delegations'] >= 10:
          html+= "  --> OK - experimental -"
        else:
          html+= "  --> NOT_OK"

        html+= "<br/><br/><h4><b>Balances:</b></h4>"        
        summed_balances = {}
        for wallet, wallet_data in data['balances'].items():
            for denom, amount in wallet_data.items():
                if denom.startswith('u'):
                    denom = denom[1:]
                for key, ibc in ibcs.items():
                    denom = denom.replace('ibc/','').replace(ibc, key)
                if denom not in summed_balances:
                    summed_balances[denom] = float(float(amount)/1e6)
                else:
                    summed_balances[denom] += float(float(amount)/1e6)

        for denom, amount in summed_balances.items():
            html+= "<br/>" + denom + " :" + str(amount)
        
        html+= "<br/><br/><h4><b>Total Rewards:</b></h4>"
        status, graph_html = get_html_from_data(data)
        if status:
            html+= graph_html
        else:
            html+= "<h4>Unable to get data, does the wallet have enough transactions or delegations ?</h4>"
            
        html+= "<br/><hr><br/>"
        html+= "<h4><b>Rewards per chain:</b></h4>"
        for chain, sub_wallet in data['found_chains'].items():
            html+= "<h4>Chain: " + chain + " - Address: " + sub_wallet + "</h4>"
            status, graph_html = get_html_from_data(data, chain)
            if status:
                html+= graph_html
            else:
                html+= "<h4>Unable to get data, does the wallet have enough transactions ?</h4>"
            html+= "<br/><hr><br/>"
        html+= '</div>'
        html+= '</div>'
        html+= '</div>'
        html+= '</div>'
    else:
    
        html += '''
        <div class="wrapper wrapper--w680">
        <div class="card card-1">
        <div class="card-body">
        <ul class="tab-list">
        <li class="tab-list__item active">
        <a class="tab-list__link" href="#rewards" data-toggle="tab">Game Of Alliances Rewards</a>
        </li>
        <li class="tab-list__item disabled">
        <a class="tab-list__link" href="#habits" data-toggle="tab"></a>
        </li>
        </ul>
        <div class="tab-content">
            <div class="tab-pane active" id="rewards">
                <p>Track your summed Terra staking rewards</p>
                <br/>
                <form id="form" method="POST" action="#" wtx-context="E8143605-B986-40F0-A778-E8253976918A">
                    <div class="input-group">
                    <label class="label">Wallet Address</label>
                    <input class="input--style-1" type="text" name="wallet" placeholder="terra1..." required="required" wtx-context="EA0622CD-8417-485D-982E-3CBF0A910F37" style="background-image: url(&quot;data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABHklEQVQ4EaVTO26DQBD1ohQWaS2lg9JybZ+AK7hNwx2oIoVf4UPQ0Lj1FdKktevIpel8AKNUkDcWMxpgSaIEaTVv3sx7uztiTdu2s/98DywOw3Dued4Who/M2aIx5lZV1aEsy0+qiwHELyi+Ytl0PQ69SxAxkWIA4RMRTdNsKE59juMcuZd6xIAFeZ6fGCdJ8kY4y7KAuTRNGd7jyEBXsdOPE3a0QGPsniOnnYMO67LgSQN9T41F2QGrQRRFCwyzoIF2qyBuKKbcOgPXdVeY9rMWgNsjf9ccYesJhk3f5dYT1HX9gR0LLQR30TnjkUEcx2uIuS4RnI+aj6sJR0AM8AaumPaM/rRehyWhXqbFAA9kh3/8/NvHxAYGAsZ/il8IalkCLBfNVAAAAABJRU5ErkJggg==&quot;); background-repeat: no-repeat; background-attachment: scroll; background-size: 16px 18px; background-position: 98% 50%; cursor: auto;">
                    </div>                                                               
                    <button class="btn-submit" id="btn-submit" type="submit">Launch observation &#127756;</button>
                </form>
            </div>
        </div>
        </div>
        </div>
        </div>
        <br/>
        <div class="wrapper wrapper--w680">
        <div class="card card-1">
        <div class="card-body">
        <center>
        <br/>
        <a href="https://twitter.com/intent/tweet?screen_name=_Wiserix&ref_src=twsrc%5Etfw" class="twitter-mention-button" data-show-count="false">@_Wiserix</a><script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
        <br/>
        <br/>
        </div>
        </center>
        </div>
        </div>
        '''

    html+= '</div>'
    html+= "</body>"
    html+= get_end_html()
    return html
    
    
@application.route('/', methods=['GET','POST'])
def home():
    return main_logic()

@application.route('/asset/<path:path>')
def send_asset(path):
    return send_from_directory('asset', path)

@application.errorhandler(404)
def page_not_found(e):
    return request.path

if __name__ == "__main__":
    #whales_habits_analyse()
    application.run('0.0.0.0',port=4000,threaded=True)
    