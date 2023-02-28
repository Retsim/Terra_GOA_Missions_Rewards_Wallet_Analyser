# Terra_GOA_Missions_Rewards_Wallet_Analyser

Small Side Project related to the Terra Game Of Alliances. (on testnet)

Based on Terra Observatory (my previous website that allowed to track airdrops and delegations rewards on Terra v1.0 - before Terra 2.0), this is a simplier app that helps to track our missions progress, as well as current balances + little rewards graphs (summed over time).

Langage: Python, using framework Flask.
Note: It does not use the Terra Python SDK !

I've made use of LCD API calls as well as GOA API calls to retrieve data I needed. 

It's not perfect, and even a bit ugly, possible errors are not fully catched.

And, it's slow ! (calling LCD for every sub-chains to analyse every detected wallets, that takes times ! Maybe 30s~)


GOA is ending in 3 days at time of writing, it's a bit too late to the party, but at least this code may inspire / be useful to some others !
(even in non-GOA context)


Feel free to take it as an inspiration or try to host it. (please give a bit of credits if you do so) :)

Discord: Wiserix#7927
(Thread in Terra Discord: https://discord.com/channels/983359798059892766/1077966832901816321)

![image](https://user-images.githubusercontent.com/9263703/221986219-4795945b-932b-40a4-bfd3-9ba41f1653d9.png)

