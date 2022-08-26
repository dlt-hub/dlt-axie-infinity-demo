# Axie Contract

game mechanics:
https://medium.com/axie-infinity/axie-infinity-breeding-system-walkthrough-ec55939a7ca6

This contract combines ERC721 token contract and Axie breeding logic. What is important in the contract
1. log of token transfers in `axie_contract_logs_transfer` (from, to, token_id). Warning: _from == 0x0000000000000000000000000000000000000000 means that axie was created not transferred_
2. log of axie eggs created in `axie_contract_logs_axiegg_spawned`. new axie (called egg) (`_axie_id`) is created when two axies (`_sire_id` and `_matron_id` breed). it has a birth date. 
3. log of breed counts (`axie_contract_logs_axie_breed_count_updated`). axies can only breed 7 times. (we could do daily breed count distribution report from that - how many Axies got to which breed count, how many axies reached level 7, daily, last week)
4. axie eggs that hatched (`axie_contract_logs_axie_evolved`)

5. ronin bridge: `ronin_gateway_contract_v2_logs_deposited` and `ronin_gateway_contract_v2_logs_mainchain_withdrew`



Reports ideas:

1. number of transactions, number of failed transactions, number of transactions in axie ecosystem (join with `known_contracts`)
2. number of transferred axies (today, change, daily last week)
3. number of spawned axie eggs 
4. number of eggs hatched.
5. (we could do daily breed count distribution report from that - how many Axies got to which breed count, how many axies reached level 7, daily, last week)
6. AXS and SLP fees paid to breed axies (https://explorer.roninchain.com/tx/0x55221e82e16a480095cc16ac743023a725815b78a21fa41e0711f6606db47f8d - join TX hash with relevant SXP and SLP logs)
7. bridge activity
deposit:
```sql
SELECT token_symbol, SUM(dep.receipt__info__quantity / POW(10, kc.decimals)) FROM `axies-ronin-pipeline.axies_1.ronin_gateway_contract_v2_logs_deposited` dep
  JOIN `axies-ronin-pipeline.axies_1.known_contracts` kc ON dep.receipt__ronin__token_addr = kc.address
GROUP BY token_symbol
```
withdrawal:
```sql
SELECT token_symbol, SUM(dep.receipt__info__quantity / POW(10, kc.decimals)) FROM `axies-ronin-pipeline.axies_1.ronin_gateway_contract_v2_logs_mainchain_withdrew` dep
  JOIN `axies-ronin-pipeline.axies_1.known_contracts` kc ON dep.receipt__ronin__token_addr = kc.address
GROUP BY token_symbol;
```

8. `axs_staking_pool_contract_logs_reward_claimed` how much rewards were claimed from staking SXP

9. `smooth_love_potion_contract_logs_smooth_love_potion_checkpoint` (rewards in SLP)

10. total fees from marketplace: 
```sql
-- treasury 0xA99CACd1427F493A95B585A5C7989A08c86A616b
-- total fees from marketplace

SELECT SUM(wad) as total_fees_eth FROM `axies-ronin-pipeline.axies_1.ronin_weth_contract_logs_transfer` tra WHERE tra._tx_address = '0xffF9Ce5f71ca6178D3BEEcEDB61e7Eff1602950E' AND dst = '0xA99CACd1427F493A95B585A5C7989A08c86A616b';
```