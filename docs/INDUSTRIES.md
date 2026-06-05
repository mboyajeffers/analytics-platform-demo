# Industry Coverage

11 verticals. Each has a dedicated engine, industry-specific KPIs, validated column requirements, and configured data sources.

---

## Finance

**Target clients:** Banks, investment firms, asset managers, hedge funds, family offices

**Primary data sources:** FRED (macroeconomic), Yahoo Finance (equity prices)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| yield_curve_slope | 10-Year minus 2-Year Treasury spread | bps |
| macro_composite | Weighted index of GDP, CPI, unemployment, PMI | index |
| credit_spread | High Yield OAS minus Investment Grade OAS | bps |
| fed_funds_trajectory | Rate change velocity over 6 months | bps/month |
| m2_growth_rate | Year-over-year M2 money supply growth | % |
| recession_probability | Probability model based on yield curve inversion | % |

**Required input columns:** account_id, transaction_date, amount, type

---

## Brokerage

**Target clients:** Trading platforms, broker-dealers, prime brokers, quant funds

**Primary data sources:** Yahoo Finance (OHLCV, profiles)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| sharpe_ratio | Annualised return / annualised volatility | ratio |
| max_drawdown | Peak-to-trough decline | % |
| sector_rotation_signal | Leading/lagging sector relative strength | index |
| beta | Systematic risk vs. S&P 500 | ratio |
| information_ratio | Active return / tracking error | ratio |
| vol_regime | Low / medium / high volatility classification | categorical |

**Required input columns:** trade_id, account_id, trade_date, symbol, quantity, price

---

## Crypto

**Target clients:** Crypto exchanges, funds, DeFi protocols, market makers

**Primary data sources:** CoinGecko

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| btc_dominance | BTC market cap as % of total crypto market cap | % |
| volatility_regime | 30-day volatility vs. 1-year rolling average | categorical |
| defi_tvl_growth | DeFi total value locked change | % |
| altcoin_season_index | Top 50 coins outperforming BTC vs. BTC season | score |
| realised_volatility_21d | 21-day realised volatility (annualised) | % |
| fear_greed_proxy | Composite sentiment signal | 0–100 |

**Required input columns:** timestamp, asset, amount

---

## Oil & Gas

**Target clients:** E&P companies, midstream operators, refiners, energy traders

**Primary data sources:** EIA API v2 (crude, natural gas, electric)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| production_mbbl_d | Crude oil production, thousand barrels per day | MBBL/D |
| rig_count_trend | Baker Hughes rig count 4-week moving average | count |
| crack_spread | 3-2-1 crack spread (WTI, RBOB, ULSD) | USD/bbl |
| storage_deviation | Current vs. 5-year average storage | % |
| ng_price_volatility | Henry Hub 30-day realised volatility | % |
| well_decline_rate | Year-1 production decline curve estimate | % |

**Required input columns:** date, volume

---

## Solar

**Target clients:** Solar developers, utilities, renewable funds, grid operators

**Primary data sources:** NASA NREL (PVWatts, irradiance), Open-Meteo (weather)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| capacity_factor | Actual generation / nameplate capacity | % |
| performance_ratio | Actual vs. theoretical yield | % |
| specific_yield | Annual kWh generated per kW installed | kWh/kW |
| irradiance_forecast_bias | Forecast vs. actual GHI | W/m² |
| curtailment_rate | Wasted generation as % of potential | % |
| lcoe_estimate | Levelised cost of energy (simplified) | USD/MWh |

**Required input columns:** site_id, timestamp, generation_kwh, irradiance

---

## Gaming

**Target clients:** Video game companies, iGaming operators, UGC platforms, gaming funds

**Primary data sources:** Steam (SteamSpy)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| dau_mau_ratio | Daily active users / monthly active users | ratio |
| arpu | Average revenue per user | USD |
| session_length_p50 | Median session duration | minutes |
| retention_d7 | 7-day player retention rate | % |
| conversion_rate | Free-to-paid conversion | % |
| churn_rate | Monthly churn rate | % |

**Required input columns:** session_id, player_id, game_date, wager, payout

---

## Betting

**Target clients:** Sports betting operators, DFS platforms, trading syndicates

**Primary data sources:** ESPN (scores, standings, player stats)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| model_accuracy | Win/loss prediction accuracy | % |
| kelly_fraction | Kelly criterion optimal bet size | % of bankroll |
| edge_percentage | Expected value as % of stake | % |
| vig_rate | House take / juice | % |
| closing_line_value | Model odds vs. closing line | % |
| roi_30d | 30-day return on investment | % |

**Required input columns:** bet_id, event_date, stake, odds, outcome

---

## Media

**Target clients:** Streaming platforms, content companies, ad agencies, media groups

**Primary data sources:** Custom media API / scraper

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| content_velocity | New pieces published per week | count/week |
| engagement_rate | Interactions / impressions | % |
| cpm | Cost per thousand impressions | USD |
| completion_rate | Video views to completion | % |
| share_of_voice | Brand mentions / total category mentions | % |
| earned_media_value | Equivalent ad spend for organic reach | USD |

**Required input columns:** content_id, event_date, impressions, platform

---

## Ecommerce

**Target clients:** DTC brands, marketplaces, retail chains, logistics providers

**Primary data sources:** Custom transaction data, Faker (sample generation)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| cart_abandonment_rate | Abandoned carts / initiated checkouts | % |
| customer_lifetime_value | Projected CLV (12-month) | USD |
| refund_rate | Refunds / gross orders | % |
| average_order_value | Gross revenue / order count | USD |
| repeat_purchase_rate | Customers with 2+ orders / total customers | % |
| gross_margin | (Revenue - COGS) / Revenue | % |

**Required input columns:** transaction_id, date, amount, customer_id

---

## Compliance

**Target clients:** RegTech firms, credit bureaus, banks (risk), law firms

**Primary data sources:** SEC EDGAR (XBRL filings, regulatory data)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| alert_accuracy | True positives / (true positives + false positives) | % |
| false_positive_rate | False alerts / total alerts | % |
| coverage_ratio | Entities monitored / total in scope | % |
| average_investigation_time | Hours from alert to disposition | hours |
| sar_filing_rate | Suspicious Activity Reports filed / alerts | % |
| risk_score_stability | Gini coefficient of risk score distribution | 0–1 |

**Required input columns:** entity_id, check_date, check_type, result

---

## Weather

**Target clients:** Commodity traders, ag firms, insurers, utilities, logistics

**Primary data sources:** Open-Meteo (historical), NOAA (climate normals)

**Key KPIs:**

| KPI | Description | Unit |
|-----|-------------|------|
| forecast_accuracy_mae | Mean absolute error vs. observed | °C |
| heating_degree_days | Cumulative HDD (base 65°F) | HDD |
| cooling_degree_days | Cumulative CDD (base 65°F) | CDD |
| precipitation_anomaly | Observed vs. 30-year normal | mm |
| extreme_event_count | Days with conditions exceeding 95th percentile | count |
| temperature_trend | Linear trend over rolling 90-day window | °C/decade |

**Required input columns:** station_id, observation_time, temperature, humidity
