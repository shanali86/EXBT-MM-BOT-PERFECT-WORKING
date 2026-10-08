# ============================================================
#  EXBT/USDT — Institutional Market Maker Bot (v2.0)
#  Config Template — LBank Official MM Rules Compliant
# ============================================================

# --- Execution Mode ---
DRY_RUN = False  # Set to True for paper trading without submitting live orders

# --- LBank API Credentials (Account A - Market Maker Primary) ---
API_KEY    = "YOUR_LBANK_API_KEY_ACCOUNT_A"
SECRET_KEY = "YOUR_LBANK_SECRET_KEY_ACCOUNT_A"

# --- LBank API Credentials (Account B - Secondary MM / Candle Engine) ---
API_KEY_B    = "YOUR_LBANK_API_KEY_ACCOUNT_B"
SECRET_KEY_B = "YOUR_LBANK_SECRET_KEY_ACCOUNT_B"

USE_RSA    = False

# --- Web Dashboard Credentials ---
DASHBOARD_USERNAME = "admin"
DASHBOARD_PASSWORD = "CHANGE_ME_PASSWORD"

# --- Trading Pair ---
SYMBOL = "exbt_usdt"

# --- Listing / Passive Reference ---
LISTING_PRICE = 0.0

# --- Spread & Quoting Engine ---
SPREAD_PCT         = 3.6       # 3.6% spread allows healthy candle bodies and organic wicks
MIN_SPREAD_PCT     = 2.8       # Minimum allowed spread %
MAX_SPREAD_PCT     = 6.0       # Maximum allowed spread % under normal volatility
BASE_SPREAD_PCT    = 3.6       # Base spread for dynamic quoting engine
LEVEL_SPACING_PCT  = 0.5       # Spacing between ladder levels %

# Safety guard: do not quote when the live external order book is abnormally wide
MAX_BOOK_SPREAD_PCT = 40.0
MAX_LAST_PRICE_DEVIATION_PCT = 5.0
MAX_DATA_STALENESS_SEC = 25.0

# --- Dual-Account Market Making (Account A + Account B) ---
DUAL_MM_ENABLED        = True  # Both Account A & Account B place staggered grids
MM_STAGGER_DELAY_SEC   = 5     # Account B refreshes 5s after Account A (Zero Gap)
MM_ORDERS_PER_ACCOUNT  = 5     # 5 buys + 5 sells = 10 orders per account (20 total on book)

# --- Order Grid & Size Randomization ---
ORDER_LEVELS       = 5         # 5 buy + 5 sell layers
LEVEL_STEP_PCT     = 1.2       # Per level step
BASE_ORDER_SIZE    = 85        # Nominal MM order size in EXBT
MIN_ORDER_SIZE_EXBT = 50       # Minimal randomized size to protect cash (~$18)
MAX_ORDER_SIZE_EXBT = 160      # Allow natural randomized order sizes up to 160 EXBT
SIZE_MULTIPLIER    = 1.0       # Flat granular order distribution
MIN_ORDER_USDT     = 5.0       # LBank min notional per order

MIN_BAND_VALUE_USDT = 600

# --- Price Corridor Protection (Strict MM Bounds) ---
PRICE_FLOOR             = 0.3500  # Hard floor permanently locked
PRICE_CEILING           = 0.4200  # Hard ceiling
TARGET_MID_PRICE        = 0.3800  # Upgraded macro target anchor
PRICE_FLOOR_OVERRIDE    = 0.3500  # Enforce trading floor
PRICE_PUMP_WARN_PCT     = 45.0
PRICE_PUMP_STOP_PCT     = 70.0    # Prevent false pump tripping during planned climb

# --- Living Organic Wave Engine ---
WAVE_CENTER_PRICE       = 0.3800  # Target midpoint
WAVE_AMPLITUDE          = 0.0090
WAVE_PERIOD_SEC         = 1800.0

# --- Quoting Side Controls ---
MM_BUY_ENABLED          = True    # Place buy ladder orders
MM_SELL_ENABLED         = True    # Place sell ladder orders
MIN_SELL_PRICE          = 0.3520

# --- Inventory & Risk Management ---
TARGET_INVENTORY_RATIO  = 0.50    # Target 50% EXBT / 50% USDT portfolio balance
INVENTORY_TOLERANCE     = 0.15    # Ratio deviation tolerance before aggressive skewing
MAX_EXBT_INVENTORY      = 250000.0  # Max total EXBT inventory allowed
MAX_USDT_EXPOSURE       = 25000.0   # Max open USDT bid exposure
MAX_OPEN_ORDER_NOTIONAL = 35000.0   # Max total open order notional

# --- Self-Trade Prevention (STP) ---
STP_ENABLED             = True    # Strictly prevent matching between controlled accounts

# --- Circuit Breaker ---
CIRCUIT_BREAKER_MAX_ERRORS  = 5
CIRCUIT_BREAKER_COOLDOWN_SEC = 30.0

# --- Funds ---
MIN_USDT_BALANCE   = 5000.0
MIN_EXBT_BALANCE   = 20000
TOTAL_FUND_TARGET  = 10000.0
REBALANCE_THRESHOLD = 0.35

# --- Timing ---
LOOP_INTERVAL_SEC  = 8
ORDER_REFRESH_SEC  = 45
STARTUP_DELAY_SEC  = 0.5

# --- Risk Controls ---
MAX_OPEN_ORDERS    = 20
MAX_DAILY_LOSS_USDT= 500.0
EMERGENCY_STOP     = False

# --- Volume Bot (Zero-Loss Coordinated Engine) ---
VOLUME_BOT_ENABLED    = False       # CandleBot handles volume cleanly without conflicts
DAILY_VOLUME_TARGET   = 50000       # Controlled target
VOLUME_TRADE_SIZE_MIN = 20          # 20 EXBT
VOLUME_TRADE_SIZE_MAX = 40          # 40 EXBT
VOLUME_INTERVAL_MIN   = 50          # Natural random pacing (50s - 90s)
VOLUME_INTERVAL_MAX   = 90

# --- Candle Bot (Zero-Loss 4-Pattern Engine) ---
CANDLE_BOT_ENABLED    = True        # Enabled: Paints 4 candle patterns (Doji, Bullish, Bearish, Hammer)
CANDLE_INTERVAL_SEC   = 15          # Evaluates 1-minute OHLC tick phase
CANDLE_TRADE_SIZE_MIN = 18          # Micro notional (~$6.00 USDT)
CANDLE_TRADE_SIZE_MAX = 22

# --- Telegram / WhatsApp Alerts ---
TELEGRAM_ENABLED   = False
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID   = ""

# --- Logging ---
LOG_LEVEL      = "INFO"
LOG_FILE       = "logs/exbt_mm_bot.log"
LOG_TO_CONSOLE = True
