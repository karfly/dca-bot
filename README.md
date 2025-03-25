# Bitcoin DCA Bot

A Docker-based Bitcoin Dollar Cost Averaging (DCA) bot that automatically purchases Bitcoin on a daily schedule via OKX exchange and sends notifications through Telegram.

## Features

- **Automated DCA**: Buy a configurable amount of Bitcoin daily at a specified UTC time
- **Telegram Integration**: Receive notifications and check stats via Telegram bot
- **MongoDB Integration**: Track trade history and performance
- **Balance Tracking**: Monitor USDT balance and days left at current rate
- **Security Features**: Transaction limits, OKX subaccount isolation, dry-run mode
- **Docker Support**: Easy deployment and management
- **Detailed Stats**: View your DCA performance statistics

## Requirements

- Docker and Docker Compose
- OKX API credentials
- Telegram Bot Token
- MongoDB Atlas account (free tier)

## Quick Start

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/dca-bot.git
   cd dca-bot
   ```

2. Create your `.env` file:
   ```
   make init-env
   ```

3. Edit the `.env` file with your credentials.

4. Build and start the bot:
   ```
   make build
   make start
   ```

5. View logs:
   ```
   make logs
   ```

## Setting Up OKX API Access

### Creating an API Key

1. Log in to your OKX account.
2. Go to "User Center" > "API Management".
3. Click "Create API" and follow the prompts.
4. For security, set IP restrictions to only allow your server's IP.
5. Enable "Trade" permission and disable all others.
6. Save your API Key, Secret Key, and Passphrase.

### Creating a Subaccount (Recommended)

For enhanced security, create a dedicated subaccount for the DCA bot:

1. Go to "Assets" > "Subaccounts".
2. Click "Create Subaccount" and follow the prompts.
3. Once created, transfer only the USDT you want to use for DCA.
4. Create a dedicated API key for this subaccount following the steps above.

## Setting Up Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/newbot` and follow the instructions to create a new bot.
3. You'll receive a token for your bot. Save this for your `.env` file.
4. Message [@userinfobot](https://t.me/userinfobot) to get your user ID.

## Setting Up MongoDB Atlas

1. Create a free account on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. Create a new cluster (the free tier is sufficient).
3. Set up a database user and password.
4. Configure network access (allow access from anywhere or your specific IP).
5. Get your connection string and add it to your `.env` file.

**Detailed guide:**

1. Sign up or log in at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2. Click "Create" to create a new project.
3. Click "Build a Database" and select the FREE tier.
4. Choose your preferred cloud provider and region.
5. Name your cluster (e.g., "dca-bot").
6. Click "Create Cluster" (it may take a few minutes to deploy).
7. In the "Security" section:
   - Click "Database Access" > "Add New Database User".
   - Create a username and password (save these).
   - Set privileges to "Read and Write to Any Database".
8. In "Network Access":
   - Click "Add IP Address".
   - For development, you can choose "Allow Access from Anywhere" or add your specific IP.
9. Once your cluster is deployed, click "Connect":
   - Select "Connect your application".
   - Copy the connection string.
   - Replace `<username>`, `<password>`, and `<dbname>` in the string with your details.

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OKX_API_KEY` | OKX API key | `a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6` |
| `OKX_API_SECRET` | OKX API secret | `YOUR_SECRET_KEY` |
| `OKX_API_PASSPHRASE` | OKX API passphrase | `your_passphrase` |
| `OKX_SUBACCOUNT_NAME` | OKX subaccount name | `dca_bot` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | `123456789:ABCdefGhIJKlmnOPQRstUVwxYZ` |
| `TELEGRAM_USER_ID` | Your Telegram user ID | `123456789` |
| `DCA_AMOUNT_USD` | USD amount to buy daily | `100.0` |
| `DCA_PERIOD` | DCA execution period | `1_day` or `1_minute` |
| `DCA_TIME_UTC` | Time to execute DCA (UTC) | `18:00` |
| `MAX_TRANSACTION_LIMIT` | Maximum allowed transaction | `1000.0` |
| `MONGODB_URI` | MongoDB connection string | `mongodb+srv://...` |
| `DRY_RUN` | Test mode without real trades | `true` or `false` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `RUN_IMMEDIATELY` | Run DCA on startup | `true` or `false` |

## Usage

### Telegram Bot Commands

- `/start` - Show welcome message and current stats
- `/stats` - Display detailed DCA statistics
- `/balance` - Show current balance and days left

### Docker Commands

Use the provided Makefile for common operations:

```
make help            # Show all available commands
make build           # Build the Docker image
make start           # Start the container
make stop            # Stop the container
make logs            # View container logs
make restart         # Restart the container
make status          # Check container status
make clean           # Stop and remove container
make run-local       # Run application locally
make init-env        # Create .env file from example
make dry-run         # Run in dry-run mode
```

## Testing

The DCA bot includes production tests built with pytest to verify functionality in your environment.

### Running Tests

The test suite performs three key checks:

1. **Trading Test**: Purchases a small amount of Bitcoin ($1) and immediately sells it back
2. **Telegram Test**: Sends a test notification to your configured Telegram user
3. **Database Test**: Verifies MongoDB connection, creates a test collection, and performs basic operations

Run the tests in Docker with:

```bash
make test
```

This will execute all tests using your production credentials. Since it uses real accounts, it will make a small ($1) actual purchase and sale of Bitcoin.

If you want to avoid making actual trades, you can set `DRY_RUN=true` in your .env file before running the tests:

```bash
# Edit .env to set DRY_RUN=true
make test
```

### Test Framework

The tests are built using:

- **pytest**: Industry-standard Python testing framework
- **pytest-asyncio**: For testing asynchronous Telegram functionality
- **Assertions**: Clear test conditions with descriptive messages
- **Automatic skipping**: Trade tests are skipped in dry-run mode

This provides a robust verification of all system components.

## Security Considerations

This bot handles financial operations, so security is critical. Here are the security measures implemented:

1. **OKX Subaccount**: Using a dedicated subaccount isolates funds from your main account.
2. **Transaction Limits**: The `MAX_TRANSACTION_LIMIT` parameter prevents excessive purchases.
3. **Limited API Permissions**: Only enable the "Trade" permission, nothing else.
4. **IP Restrictions**: Configure OKX API to only accept requests from your server IP.
5. **Dry Run Mode**: Test the bot without making actual trades.
6. **Single User Access**: Only your Telegram user ID can interact with the bot.
7. **Isolated Docker Environment**: Containerization provides additional security.

### Potential Risks

1. **API Key Compromise**: If your API key is stolen, an attacker could trade on your behalf. Mitigate by using a subaccount with limited funds.
2. **Server Compromise**: If your server is compromised, your keys could be exposed. Regularly update your server and follow security best practices.
3. **Bugs**: Software bugs could potentially lead to incorrect trades. Start with small DCA amounts and monitor closely.

### Risk Mitigation

1. **Start Small**: Begin with small DCA amounts until you're confident in the setup.
2. **Enable Dry Run**: Test with `DRY_RUN=true` before making real trades.
3. **Regular Monitoring**: Check your Telegram notifications and OKX account regularly.
4. **Fund Management**: Only deposit enough USDT for a few weeks of DCA at a time.

## Troubleshooting

- **Bot not responding**: Check Docker logs with `make logs`
- **No trades executed**: Verify your OKX API credentials and permissions
- **MongoDB connection issues**: Check your MongoDB Atlas connection string and network settings
- **Tests failing**: Ensure you've set up the correct credentials in `.env.test`
- **Docker test issues**: Make sure Docker and Docker Compose are installed and running properly

## License

MIT License

## Acknowledgements

- [CCXT](https://github.com/ccxt/ccxt) for exchange integration
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for Telegram bot functionality
- [pymongo](https://github.com/mongodb/mongo-python-driver) for MongoDB integration