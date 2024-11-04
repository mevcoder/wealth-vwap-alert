# Discord VWAP Bot

A Discord bot to monitor cryptocurrency prices against VWAP levels and send alerts when they are within a specified range. Alerts are limited to once per 24 hours per token.

## Features
- Set VWAP price alerts for specific tokens.
- Notifies users if the price is within ±10% of the VWAP level.
- Alerts only once every 24 hours for each token.
- Commands to list and remove alerts.

## Setup

### Prerequisites
- Python 3.7+
- Discord bot token (create a bot at https://discord.com/developers)

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/DiscordVWAPBot.git
   cd DiscordVWAPBot

2. Install dependencies:

   ```bash
   pip install -r requirements.txt

3. Set up your environment variables:
Copy .env.example to .env.
Add your Discord bot token in the .env file:

    ```
    DISCORD_TOKEN=your_token_here

4. Run the bot

   ```bash
   python bot.py


Commands
!vwap <contract_address> <vwap_level> - Sets a VWAP alert for the specified token.
!list_alerts - Lists all currently set alerts.
!remove_token <contract_address> - Removes a specific alert by contract address.
