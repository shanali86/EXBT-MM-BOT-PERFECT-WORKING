# EXBT/USDT Institutional Market Maker Bot (v2.0)

High-performance, multi-account Market Maker, Dynamic Quoting Engine, Candle Painter, and Risk Defense Suite designed specifically for LBank exchange.

---

## Key Features

1. **Dual-Account Zero-Gap Quoting Engine (`market_maker.py`, `quoting_engine.py`)**
   - Dual staggered ladder order placement (Account A & Account B)
   - "Place-First, Cancel-Later" zero-gap liquidity replacement
   - Organic randomized order sizing (e.g. 74.32 to 118.91 EXBT) preventing robotic patterns
   - Dynamic inventory skewing with self-trade prevention (STP)

2. **Autonomous Candle Painter (`candle_bot.py`)**
   - 5-tick intra-minute trajectory engine generating realistic OHLC candles
   - Four distinct organic patterns: *Bullish Expansion, Bearish Retracement, Hammer, Neutral Doji*
   - Micro-notional trades between coordinated accounts with zero capital loss

3. **Macro BTC Regime Engine (`reference_engine.py`)**
   - Live Binance BTC/USDT tracker adapting EXBT spreads dynamically
   - Spreads widen defensively during BTC dump regimes and tighten during calm regimes

4. **Hard Capital Defense & Anti-Sniper Protection**
   - Hard Price Floor protection (`PRICE_FLOOR = 0.3500`)
   - Pre-emptive ask sweeping and thin book detection
   - Circuit breakers and daily loss stops

5. **Live Monitoring & Executive Dashboards**
   - **Interactive Web Dashboard (`dashboard_app.py`)**: Real-time order books, spreads, inventory ratios, and trade logs
   - **Automated Daily Report Cards (`generate_report_card.py`)**: High-resolution executive PNG/PDF summary cards
   - **WhatsApp/Telegram Automated Dispatcher (`whatsapp_agent.py`)**

---

## Directory Structure

```text
├── config_example.py         # Complete configuration template (copy to config.py)
├── main.py                   # Central orchestrator and process launcher
├── market_maker.py           # Core dual-account market making engine
├── quoting_engine.py         # Adaptive spread and pricing calculations
├── candle_bot.py             # Intra-minute OHLC candle painter
├── reference_engine.py       # Macro BTC regime monitor and reference price tracker
├── wave_engine.py            # Natural wave oscillator for organic price action
├── lbank_client.py           # Authenticated LBank REST API client
├── stp_registry.py           # Self-Trade Prevention registry
├── inventory_manager.py      # Inventory balancing and position skew logic
├── circuit_breaker.py        # Volatility and error rate safeguards
├── fill_monitor.py           # Order fill tracker and execution listener
├── budget_manager.py         # Strict capital allocation limits
├── dashboard_app.py          # Real-time Dash web console
├── generate_report_card.py   # Daily visual performance report generator
├── whatsapp_agent.py         # Daily report automated messenger
├── requirements.txt          # Python dependencies
├── exbt-mm-bot.service       # Systemd service for market maker bot
├── exbt-dashboard.service    # Systemd service for dashboard
└── tools/                    # Utility scripts (audits, sweeps, order inspection)
    ├── sweep_ask.py          # Clean ask sweeper
    ├── deep_ledger_audit.py  # Historical fill reconciliation
    ├── audit_usdt_usage.py   # USDT usage breakdown
    ├── check_depth_30.py     # LBank depth inspector
    └── inspect_rates.py      # Fee & rate auditor
```

---

## Quick Setup & Deployment

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/shanali86/MM_BOT_Final.git
cd MM_BOT_Final
pip install -r requirements.txt
```

### 2. Configure Credentials
Copy `config_example.py` to `config.py` and input your LBank API credentials:
```bash
cp config_example.py config.py
nano config.py
```
> **Security Notice**: Never commit `config.py` to Git. Keep your API keys and secrets strictly private.

### 3. Verify Connectivity
Test account balances and order book connectivity:
```bash
python main.py --status
```

### 4. Run Services
#### Direct / Background:
```bash
nohup python main.py > logs/exbt_mm_bot.log 2>&1 &
```

#### Via Systemd (Production VPS):
```bash
sudo cp exbt-mm-bot.service /etc/systemd/system/
sudo cp exbt-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now exbt-mm-bot
sudo systemctl enable --now exbt-dashboard
```

---

## License & Disclaimer
Proprietary institutional software developed for EXBT market operations. Use with appropriate risk management protocols.
